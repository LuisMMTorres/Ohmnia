"""Equivalent circuit of a catalogue induction motor, fitted to its data sheet.

Manufacturers' data sheets (WEG among them) do not publish R1, X1, R2, X2 and Xm; they give
the rated point (current, power factor, speed, torque), the no-load current, the locked-rotor
current and torque and the breakdown torque. The single-cage circuit of
:mod:`circuitos.machines.induction` has four unknowns (R1, R2, X1 + X2, Xm, with the split of
the leakage reactance taken from IEEE Std 112), so it is fitted by least squares to those
data points; each point that the circuit cannot reproduce shows up in ``residuals`` and as a
warning. A single cage cannot match the locked-rotor torque and current of a deep-bar rotor
and the rated point at the same time: the rated point and the breakdown torque weigh more.

Iron and mechanical losses are not in the circuit; matching the rated current, power factor
and shaft torque puts them in R1 and R2 (premise stated in the result).

References: Chapman, *Electric Machinery Fundamentals*, 5th ed., ch. 6 (equivalent circuit,
determining the circuit parameters from tests); IEEE Std 112 (empirical distribution of X1 and
X2 by NEMA design: A, D and wound rotor 0,5/0,5; B 0,4/0,6; C 0,3/0,7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_
from circuitos.machines.induction import InductionParams, breakdown_slip, operating_point

# X1 / (X1 + X2) by NEMA design letter (IEEE Std 112); IEC design N is like NEMA B
X1_SHARE = {"A": 0.5, "B": 0.4, "C": 0.3, "D": 0.5, "N": 0.4, "H": 0.3}
WARN_LIMIT = 0.15  # relative misfit that becomes a warning


@dataclass(frozen=True)
class MotorData:
    """Data-sheet values at one rated voltage (SI units)."""

    p_out: float  # W, rated output
    v_line: float  # V rms, rated line voltage
    f: float  # Hz
    poles: int
    i_n: float  # A, rated current
    n_n: float  # rpm, rated speed
    pf: float  # power factor at rated load
    i_lr: float  # A, locked-rotor current
    i_0: float | None = None  # A, no-load current
    t_lr: float | None = None  # locked-rotor torque / rated torque
    t_bd: float | None = None  # breakdown torque / rated torque
    design: str = "B"
    j: float = 0.0  # kg·m²


@dataclass(frozen=True)
class Fit:
    params: InductionParams
    residuals: dict[str, tuple[float, float]]  # name -> (data sheet, circuit)
    warnings: list[str] = field(default_factory=list)


def _model(x: np.ndarray, d: MotorData, share: float) -> InductionParams:
    r1, r2, xl, xm = np.exp(x)
    return InductionParams(
        rs=float(r1),
        rr=float(r2),
        xls=float(xl * share),
        xlr=float(xl * (1 - share)),
        xm=float(xm),
        poles=d.poles,
        fnom=d.f,
        j=d.j,
    )


def _points(m: InductionParams, d: MotorData) -> dict[str, float]:
    ws = 2 * math.pi * d.f / (d.poles // 2)
    s_n = 1 - d.n_n * 2 * math.pi / 60 / ws
    t_n = d.p_out / (d.n_n * 2 * math.pi / 60)
    rated = operating_point(m, d.v_line, d.f, s_n)
    out = {"I_n": rated.i1, "pf": rated.pf, "T_n": rated.torque}
    if d.i_0 is not None:
        out["I_0"] = operating_point(m, d.v_line, d.f, 1e-9).i1
    locked = operating_point(m, d.v_line, d.f, 1.0)
    out["I_lr"] = locked.i1
    if d.t_lr is not None:
        out["T_lr/T_n"] = locked.torque / t_n
    if d.t_bd is not None:
        s_bd = breakdown_slip(m, d.f)
        out["T_bd/T_n"] = operating_point(m, d.v_line, d.f, s_bd).torque / t_n
    return out


def _targets(d: MotorData) -> dict[str, tuple[float, float]]:
    """Data-sheet value and weight of each point."""
    t_n = d.p_out / (d.n_n * 2 * math.pi / 60)
    out = {"I_n": (d.i_n, 1.0), "pf": (d.pf, 1.0), "T_n": (t_n, 2.0), "I_lr": (d.i_lr, 0.7)}
    if d.i_0 is not None:
        out["I_0"] = (d.i_0, 1.0)
    if d.t_lr is not None:
        out["T_lr/T_n"] = (d.t_lr, 0.0)
    if d.t_bd is not None:
        out["T_bd/T_n"] = (d.t_bd, 1.0)
    return out


def fit_circuit(d: MotorData) -> Calculated[Fit]:
    """Least-squares fit of R1, R2, X1 + X2 and Xm to the data-sheet points."""
    share = X1_SHARE.get(d.design.upper(), 0.5)
    targets = _targets(d)
    v_ph = d.v_line / math.sqrt(3)
    ws = 2 * math.pi * d.f / (d.poles // 2)
    s_n = 1 - d.n_n * 2 * math.pi / 60 / ws
    if not 0 < s_n < 0.5:
        raise ValueError("rotação nominal incompatível com o número de polos e a frequência")
    z_n = v_ph / d.i_n
    x0 = np.log(
        [
            0.5 * s_n * z_n,
            0.8 * s_n * z_n,
            0.8 * v_ph / d.i_lr,
            v_ph / (d.i_0 if d.i_0 else 0.4 * d.i_n),
        ]
    )

    def residual(x: np.ndarray) -> np.ndarray:
        got = _points(_model(x, d, share), d)
        return np.array([w * (got[k] / t - 1) for k, (t, w) in targets.items()])

    sol = least_squares(residual, x0, method="lm", xtol=1e-12, ftol=1e-12, max_nfev=4000)
    m = _model(sol.x, d, share)
    got = _points(m, d)
    residuals = {k: (t, got[k]) for k, (t, _) in targets.items()}
    warnings = [
        f"{k}: o circuito equivalente dá {g:.4g}, o datasheet {t:.4g} ({100 * (g / t - 1):+.0f} %)"
        for k, (t, g) in residuals.items()
        if abs(g / t - 1) > WARN_LIMIT
    ]
    step = record(
        "motor_circuito_equivalente",
        "Circuito equivalente por fase (estrela) ajustado aos dados do datasheet",
        r"\min_{R_1,R_2,X_\ell,X_m}\sum_k w_k\left(\frac{y_k^{\mathrm{circ}}}"
        r"{y_k^{\mathrm{ds}}}-1\right)^2",
        Q_(m.rs, "ohm"),
        inputs={
            "P_n": Q_(d.p_out, "W"),
            "V_n": Q_(d.v_line, "V"),
            "I_n": Q_(d.i_n, "A"),
            "n_n": Q_(d.n_n, "rpm"),
            "I_p": Q_(d.i_lr, "A"),
        },
        assumptions=[
            f"X1/(X1+X2) = {share:g} (IEEE Std 112, categoria {d.design.upper()})",
            "perdas no ferro e mecânicas embutidas em R1 e R2 (o circuito não as tem)",
            "gaiola simples: conjugado e corrente de partida têm peso menor que o ponto nominal",
            *(f"R2 = {m.rr:.4g} Ω, X1 = {m.xls:.4g} Ω, X2 = {m.xlr:.4g} Ω, Xm = {m.xm:.4g} Ω",),
        ],
        reference=BibRef(
            book="Chapman, Electric Machinery Fundamentals",
            edition="5th",
            chapter="6 (Determining the circuit model parameters)",
        ),
    )
    return Calculated(Fit(m, residuals, warnings), step.step)
