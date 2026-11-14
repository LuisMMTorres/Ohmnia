"""Junction diode model for the device bench (BD-DIODO).

Shockley equation with series resistance and the SPICE temperature dependence of the saturation
current, so bench curves and ngspice agree (verified in tests/analytic_vs_sim).

    V = n·Vt·ln(I/Is + 1) + I·Rs
    Vt = k·T/q
    Is(T) = Is(T0)·(T/T0)^(XTI/n)·exp[(Eg/(n·Vt(T)))·(T/T0 − 1)]

References: Sedra & Smith, *Microelectronic Circuits* (diode chapter: Shockley equation and
temperature effects); ngspice manual, diode model (IS, N, RS, XTI, EG). Chapter and equation
numbers still to be checked against the printed books (BibRef.verified = False).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pint
from numpy.typing import NDArray

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, magnitudes, require

K_B = 1.380649e-23  # J/K (exact, SI 2019)
Q_E = 1.602176634e-19  # C (exact, SI 2019)
T_NOM = 300.15  # K: SPICE TNOM default (27 °C)

SHOCKLEY_REF = BibRef(book="Sedra & Smith, Microelectronic Circuits", chapter="Diodes")


@dataclass(frozen=True)
class DiodeModel:
    """Model parameters. They are *model* values, not datasheet ratings."""

    Is: pint.Quantity  # saturation current at T_NOM
    n: float  # emission coefficient
    Rs: pint.Quantity  # series resistance
    Eg: pint.Quantity = field(default_factory=lambda: Q_(1.11, "eV"))  # silicon
    XTI: float = 3.0  # saturation-current temperature exponent (junction diode)

    def __post_init__(self) -> None:
        require(self.Is, "A", "Is")
        require(self.Rs, "ohm", "Rs")
        require(self.Eg, "eV", "Eg")
        if not self.Is.magnitude > 0 or not self.n > 0 or self.Rs.magnitude < 0:
            raise ValueError("Is e n devem ser positivos e Rs não negativo")

    def spice(self, name: str = "DMOD") -> str:
        return (
            f".model {name} D(IS={self.Is.m_as('A'):.6g} N={self.n:.6g} "
            f"RS={self.Rs.m_as('ohm'):.6g} EG={self.Eg.m_as('eV'):.6g} XTI={self.XTI:.6g})"
        )


def thermal_voltage(T: pint.Quantity) -> pint.Quantity:
    require(T, "K", "T")
    return Q_(K_B * T.m_as("K") / Q_E, "V")


@magnitudes(inputs={"T": "K"}, output="A")
def _is_at(model: DiodeModel, T: float) -> float:
    is0 = model.Is.m_as("A")
    vt = K_B * T / Q_E
    eg = model.Eg.m_as("eV")
    return float(
        is0 * (T / T_NOM) ** (model.XTI / model.n) * np.exp(eg / (model.n * vt) * (T / T_NOM - 1))
    )


def saturation_current(model: DiodeModel, T: pint.Quantity) -> Calculated[pint.Quantity]:
    value = _is_at(model, T)
    return record(
        "Is_T",
        "Corrente de saturação na temperatura",
        r"I_S(T) = I_S(T_0)\left(\frac{T}{T_0}\right)^{X_{TI}/n}"
        r"\exp\left[\frac{E_g}{n V_T}\left(\frac{T}{T_0}-1\right)\right]",
        output=value,
        inputs={"I_S(T_0)": model.Is, "T": T.to("K"), "T_0": Q_(T_NOM, "K"), "E_g": model.Eg},
        assumptions=[f"X_TI = {model.XTI:g}", f"n = {model.n:g}", "modelo SPICE do diodo"],
        reference=SHOCKLEY_REF,
    )


def forward_voltage(model: DiodeModel, current: pint.Quantity, T: pint.Quantity) -> pint.Quantity:
    """V(I): explicit, valid for I > −Is (forward and small reverse bias)."""
    require(current, "A", "I")
    i = np.asarray(current.m_as("A"), dtype=float)
    vt = thermal_voltage(T).m_as("V")
    is_t = _is_at(model, T).m_as("A")
    v = model.n * vt * np.log1p(i / is_t) + i * model.Rs.m_as("ohm")
    return Q_(v, "V")


def current(model: DiodeModel, voltage: pint.Quantity, T: pint.Quantity) -> pint.Quantity:
    """I(V) with series resistance, solved by Newton iteration on the monotone V(I)."""
    require(voltage, "V", "V")
    v = np.atleast_1d(np.asarray(voltage.m_as("V"), dtype=float))
    vt = thermal_voltage(T).m_as("V")
    is_t = _is_at(model, T).m_as("A")
    rs = model.Rs.m_as("ohm")
    nvt = model.n * vt
    # Start from the smaller of the ideal-diode and the resistor-limited currents.
    with np.errstate(over="ignore"):
        ideal = is_t * np.expm1(np.minimum(v / nvt, 700))
    i = np.minimum(ideal, np.where(rs > 0, np.maximum(v, 0) / max(rs, 1e-30), ideal))
    i = np.maximum(i, -is_t * (1 - 1e-12))
    for _ in range(200):
        f = nvt * np.log1p(i / is_t) + i * rs - v
        df = nvt / (is_t + i) + rs
        step = f / df
        i_new = i - step
        # keep inside the domain I > −Is
        i_new = np.where(i_new <= -is_t, (i - is_t) / 2, i_new)
        if np.all(np.abs(i_new - i) <= 1e-12 * np.maximum(np.abs(i_new), is_t)):
            i = i_new
            break
        i = i_new
    out: NDArray[np.float64] = i
    return Q_(out if np.ndim(voltage.magnitude) else float(out[0]), "A")


def vf_temperature_coefficient(
    model: DiodeModel, current_: pint.Quantity, T: pint.Quantity
) -> Calculated[pint.Quantity]:
    """dVF/dT at constant current (numerical derivative, ±0,5 K)."""
    dT = Q_(0.5, "K")
    t_k = T.to("K")
    v_hi = forward_voltage(model, current_, Q_(t_k.m_as("K") + 0.5, "K"))
    v_lo = forward_voltage(model, current_, Q_(t_k.m_as("K") - 0.5, "K"))
    coeff: pint.Quantity = ((v_hi - v_lo) / (2 * dT)).to("mV/K")
    return record(
        "dVF_dT",
        "Coeficiente de temperatura da tensão direta",
        r"\frac{dV_F}{dT}\Big|_{I_F} \approx \frac{V_F(T+\Delta T) - V_F(T-\Delta T)}{2\,\Delta T}",
        output=coeff,
        inputs={"I_F": current_, "T": t_k, r"\Delta T": dT},
        assumptions=["derivada numérica do modelo de Shockley com Rs"],
        reference=SHOCKLEY_REF,
    )
