"""Inductor, coupled-inductor (flyback) and transformer design with catalogue cores.

The smallest core (by area product Ap = Wa·Ae) that meets every constraint is chosen:

1. Turns. Energy-storing parts (inductor, flyback): N = ⌈L·Ipk/(Bmax·Ae)⌉. Transformers:
   N1 = ⌈λ/(ΔBmax·Ae)⌉ with λ the volt-seconds of one half cycle and ΔBmax = 2·Bmax for a
   bipolar (push-pull, bridge) or Bmax for a unipolar (forward) excitation.
2. Air gap of the energy-storing parts: lg = μ0·N²·Ae/L − le/μi (fringing neglected).
3. Window: Σ N·A_cu ≤ Ku·Wa (Ku is the window utilisation factor).
4. Losses: copper N·MLT·ρ(T)/A_cu·Irms² for each winding (strands thinner than 2δ, so Rac ≈ Rdc);
   core from the Steinmetz form anchored on the datasheet loss of the core.
5. Temperature rise ΔT = 450·(P/At)^0,826 (P in W, At in cm², natural convection) with At the
   outside area of the assembled core.

References: McLyman, *Transformer and Inductor Design Handbook*, 4th ed., chapters on the area
product (Ap) method, inductor design with an air gap, and temperature rise (ΔT = 450·ψ^0,826);
Erickson & Maksimović, *Fundamentals of Power Electronics*, 2nd ed., ch. 14 (inductor design)
and ch. 15 (transformer design).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_
from circuitos.magnetics.cores import Core, Steinmetz, core_from, steinmetz
from circuitos.magnetics.wire import MU0, Strand, awg_diameter, choose_strand, rho_cu, skin_depth

MCLYMAN = BibRef(book="McLyman, Transformer and Inductor Design Handbook", edition="4th")
ERICKSON = BibRef(
    book="Erickson & Maksimović, Fundamentals of Power Electronics", edition="2nd", chapter="14-15"
)

Kind = Literal["indutor", "flyback", "transformador"]


@dataclass(frozen=True)
class Winding:
    name: str
    ratio: float  # turns relative to the first winding
    I_rms: float  # A


@dataclass(frozen=True)
class MagSpec:
    kind: Kind
    f: float  # Hz
    windings: tuple[Winding, ...]
    L: float = 0.0  # H (inductor / flyback primary)
    I_pk: float = 0.0  # A, peak of the first winding (inductor / flyback)
    dI_pp: float = 0.0  # A, peak-to-peak ripple of the first winding (AC flux)
    lam: float = 0.0  # V·s per half cycle (transformer)
    bipolar: bool = True  # transformer flux swings both ways
    B_max: float = 0.25  # T
    J: float = 4e6  # A/m²
    Ku: float = 0.4
    TA: float = 40.0  # °C
    dT_max: float = 40.0  # K
    T_wire: float = 100.0  # °C for the copper resistance


@dataclass
class WindingOut:
    name: str
    N: int
    strand: Strand
    R: float  # Ω
    P: float  # W


@dataclass
class MagResult:
    core: Core
    windings: list[WindingOut]
    B_pk: float  # T, peak flux density
    B_ac: float  # T, peak AC flux density
    gap: float  # m (0 for a transformer)
    AL_gapped: float  # H/turn²
    P_cu: float
    P_core: float
    dT: float
    fill: float  # copper area / Wa
    warnings: list[str] = field(default_factory=list)

    @property
    def P_total(self) -> float:
        return self.P_cu + self.P_core


def _materials(mats: Sequence[ComponentRecord]) -> dict[str, Steinmetz]:
    out = {}
    for m in mats:
        try:
            out[m.part_number] = steinmetz(m)
        except ValueError:
            continue
    return out


def _at_turns(
    s: MagSpec, core: Core, n1: int, m: Steinmetz | None, alpha_default: float | None
) -> tuple[MagResult | None, str]:
    w0 = s.windings[0]
    if s.kind == "transformador":
        b_ac = s.lam / (2 * n1 * core.Ae)
        b_pk = b_ac if s.bipolar else 2 * b_ac
        gap = 0.0
        al = core.AL
    else:
        b_pk = s.L * s.I_pk / (n1 * core.Ae)
        b_ac = s.L * s.dI_pp / (2 * n1 * core.Ae)
        gap = MU0 * n1**2 * core.Ae / s.L - core.le / core.mu_e
        al = s.L / n1**2
        if gap <= 0:
            return None, "não precisa de entreferro com esse número de espiras (AL alto demais)"
    outs: list[WindingOut] = []
    cu_area = 0.0
    for w in s.windings:
        n = n1 if w is w0 else max(1, round(n1 * w.ratio))
        st_ = choose_strand(w.I_rms, s.J, s.f, s.T_wire)
        r = n * core.MLT * rho_cu(s.T_wire) / st_.area
        outs.append(WindingOut(w.name, n, st_, r, w.I_rms**2 * r))
        cu_area += n * st_.area
    fill = cu_area / core.Wa
    if fill > s.Ku:
        return None, f"enrolamentos ocupam {fill:.0%} da janela (Ku = {s.Ku:.0%})"
    try:
        p_core = core.core_loss(s.f, b_ac, m, alpha_default)
    except ValueError as e:
        return None, str(e)
    p_cu = sum(o.P for o in outs)
    dT = 450 * ((p_cu + p_core) / (core.area_surface * 1e4)) ** 0.826
    return MagResult(core, outs, b_pk, b_ac, gap, al, p_cu, p_core, dT, fill), ""


def _evaluate(
    s: MagSpec, core: Core, st: dict[str, Steinmetz], log: CalcLog | None
) -> tuple[MagResult | None, str]:
    """Design on one core; (None, reason) when it does not fit.

    The minimum number of turns keeps B below the limit; more turns lower the AC flux (core
    loss) and raise the copper loss, so the count with the lowest total loss that still fits
    the window is kept (the loss optimum of Erickson ch. 15, searched on integer turns).
    """
    b_lim = min(s.B_max, 0.9 * core.Bsat)
    if s.kind == "transformador":
        db = (2 if s.bipolar else 1) * b_lim
        n_min = max(1, math.ceil(s.lam / (db * core.Ae) - 1e-9))
    else:
        n_min = max(1, math.ceil(s.L * s.I_pk / (b_lim * core.Ae) - 1e-9))
    m = st.get(core.material)
    alpha_default = None
    warnings: list[str] = []
    if m is not None and m.alpha is None:
        alpha_default = next((x.alpha for x in st.values() if x.alpha is not None), None)
        if alpha_default is not None:
            warnings.append(
                f"{core.material} só tem pontos de perdas a 100 kHz: o expoente de frequência "
                f"α = {alpha_default:.2f} veio de outro material do catálogo (premissa)."
            )
    best: MagResult | None = None
    why = ""
    for n1 in range(n_min, 4 * n_min + 40):
        res, reason = _at_turns(s, core, n1, m, alpha_default)
        if res is None:
            if best is None:
                why = reason
            if "janela" in reason:
                break
            continue
        if best is None or res.P_total < best.P_total:
            best = res
    if best is None:
        return None, why
    if best.dT > s.dT_max:
        return None, f"ΔT = {best.dT:.0f} K acima de {s.dT_max:.0f} K"
    best.warnings = warnings
    if log is not None:
        _log(s, best, b_lim, n_min, log)
    return best, ""


def _log(s: MagSpec, r: MagResult, b_lim: float, n_min: int, log: CalcLog) -> None:
    c = r.core
    n1 = r.windings[0].N
    if s.kind == "transformador":
        log.add(
            record(
                "mag_N1_min",
                "Espiras mínimas do primário pela variação de fluxo",
                r"N_{1,min} = \left\lceil \frac{\lambda}{\Delta B_{max} A_e} \right\rceil",
                output=Q_(n_min, ""),
                inputs={
                    "λ": Q_(s.lam, "V*s").to("V*us"),
                    "ΔB_max": Q_((2 if s.bipolar else 1) * b_lim, "T").to("mT"),
                    "A_e": Q_(c.Ae, "m**2").to("mm**2"),
                },
                assumptions=[
                    "excitação bipolar: ΔB = 2·B_max"
                    if s.bipolar
                    else "excitação unipolar (reset)",
                    f"B_max = mín(B_max pedido, 0,9·Bsat a 100 °C = {0.9 * c.Bsat * 1e3:.0f} mT)",
                ],
                reference=MCLYMAN,
            )
        )
    else:
        log.add(
            record(
                "mag_N1_min",
                "Espiras mínimas pelo fluxo de pico",
                r"N_{min} = \left\lceil \frac{L I_{pk}}{B_{max} A_e} \right\rceil",
                output=Q_(n_min, ""),
                inputs={
                    "L": Q_(s.L, "H").to("uH"),
                    "I_{pk}": Q_(s.I_pk, "A"),
                    "B_max": Q_(b_lim, "T").to("mT"),
                    "A_e": Q_(c.Ae, "m**2").to("mm**2"),
                },
                assumptions=[
                    f"B_max = mín(B_max pedido, 0,9·Bsat a 100 °C = {0.9 * c.Bsat * 1e3:.0f} mT)"
                ],
                reference=MCLYMAN,
            )
        )
        log.add(
            record(
                "mag_gap",
                "Entreferro (perna central retificada)",
                r"l_g = \frac{\mu_0 N^2 A_e}{L} - \frac{l_e}{\mu_e}",
                output=Q_(r.gap, "m").to("mm"),
                inputs={
                    "N": Q_(n1, ""),
                    "A_e": Q_(c.Ae, "m**2").to("mm**2"),
                    "L": Q_(s.L, "H").to("uH"),
                    "l_e": Q_(c.le, "m").to("mm"),
                    "μ_e": Q_(c.mu_e, ""),
                },
                assumptions=[
                    "μ_e do conjunto sem entreferro, calculado do AL do datasheet",
                    "espraiamento (fringing) desprezado: a indutância real fica um pouco maior",
                ],
                reference=ERICKSON,
            )
        )
    log.add(
        record(
            "mag_N1",
            "Espiras escolhidas (menor perda total que cabe na janela)",
            r"N_1 = \arg\min_{N \ge N_{min}} \left(P_{cu}(N) + P_{fe}(N)\right)",
            output=Q_(n1, ""),
            inputs={
                "N_min": Q_(n_min, ""),
                "B̂_ca": Q_(r.B_ac, "T").to("mT"),
                "B_pk": Q_(r.B_pk, "T").to("mT"),
                "ocupação": Q_(r.fill * 100, "percent"),
            },
            assumptions=[
                "mais espiras reduzem o fluxo (perda no núcleo) e aumentam a perda no cobre",
                "busca em números inteiros de espiras",
            ],
            reference=ERICKSON,
        )
    )
    for w in r.windings:
        log.add(
            record(
                f"mag_R_{w.name}",
                f"Resistência do enrolamento {w.name} "
                f"({w.N} esp., {w.strand.n}× AWG {w.strand.awg})",
                r"R = \frac{N \cdot MLT \cdot \rho_{Cu}(T)}{A_{Cu}}",
                output=Q_(w.R, "ohm").to("mohm"),
                inputs={
                    "N": Q_(w.N, ""),
                    "MLT": Q_(c.MLT, "m").to("mm"),
                    "A_Cu": Q_(w.strand.area, "m**2").to("mm**2"),
                    "d_fio": Q_(awg_diameter(w.strand.awg), "m").to("mm"),
                    "δ": Q_(skin_depth(s.f, s.T_wire), "m").to("mm"),
                },
                assumptions=[
                    f"cobre a {s.T_wire:.0f} °C; fios mais finos que 2δ, R_ca ≈ R_cc",
                    f"comprimento médio da espira: {c.window_from}",
                ],
                reference=ERICKSON,
            )
        )
    log.add(
        record(
            "mag_Pcore",
            "Perdas no núcleo (Steinmetz ancorado na perda máxima do datasheet)",
            r"P_{fe} = P_{ref} \left(\frac{f}{f_{ref}}\right)^{\alpha}"
            r"\left(\frac{\hat B_{ca}}{B_{ref}}\right)^{\beta}",
            output=Q_(r.P_core, "W"),
            inputs={
                "P_ref": Q_(c.P_ref or 0.0, "W"),
                "f": Q_(s.f, "Hz").to("kHz"),
                "f_ref": Q_(c.f_ref or 0.0, "Hz").to("kHz"),
                "B̂_ca": Q_(r.B_ac, "T").to("mT"),
                "B_ref": Q_(c.B_ref or 0.0, "T").to("mT"),
            },
            assumptions=[
                "excitação senoidal equivalente; com onda quadrada a perda real difere (iGSE)",
                "α e β ajustados aos pontos de perdas do material no datasheet",
            ],
            reference=ERICKSON,
        )
    )
    log.add(
        record(
            "mag_dT",
            "Elevação de temperatura do magnético (convecção natural)",
            r"\Delta T = 450 \left(\frac{P_{cu} + P_{fe}}{A_t}\right)^{0{,}826}",
            output=Q_(r.dT, "K"),
            inputs={
                "P_cu": Q_(r.P_cu, "W"),
                "P_fe": Q_(r.P_core, "W"),
                "A_t": Q_(c.area_surface, "m**2").to("cm**2"),
            },
            assumptions=[
                "A_t = superfície externa do núcleo montado (sem o volume do enrolamento)"
            ],
            reference=MCLYMAN,
        )
    )


def design(
    s: MagSpec,
    cores: Sequence[ComponentRecord],
    materials: Sequence[ComponentRecord],
    bobbins: Sequence[ComponentRecord],
    log: CalcLog,
) -> MagResult:
    """Smallest core that meets the specification; ValueError with the reasons otherwise."""
    # rule 5: only released records take part in an automatic choice
    st = _materials([m for m in materials if m.selectable])
    released = [c for c in cores if c.selectable]
    if not released:
        raise ValueError("Nenhum núcleo liberado no catálogo (revise e libere os núcleos).")
    bob = [b for b in bobbins if b.selectable]
    candidates = sorted((core_from(c, bob) for c in released), key=lambda c: c.Ap)
    reasons: list[str] = []
    for core in candidates:
        res, why = _evaluate(s, core, st, None)
        if res is not None:
            final, _ = _evaluate(s, core, st, log)
            assert final is not None
            return final
        reasons.append(f"{core.size}: {why}")
    raise ValueError("Nenhum núcleo do catálogo atende: " + "; ".join(reasons[-3:]))
