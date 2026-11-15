"""Shared models of the power-electronics modules (phase 6).

* Semiconductor losses from datasheet values: conduction (RDS(on), VCE(sat), VF) and switching
  (tr/tf of a MOSFET, Eon/Eoff of an IGBT scaled to the operating point, Qrr of a diode).
* Averaged state-space models (Middlebrook & Ćuk) of the six non-isolated PWM converters in
  continuous conduction: steady state and the control-to-output transfer function.
* Type II and type III error-amplifier compensators by the K factor (Venable) and the margins
  of the resulting loop.
* Magnetic design of the inductors of a module with the catalogue cores (SV-MAG).

References: Erickson & Maksimović, *Fundamentals of Power Electronics*, 2nd ed. (ch. 2-3
steady state, ch. 4 switching losses, ch. 7 averaged models, ch. 8 transfer functions, ch. 9
loop design); Mohan, Undeland & Robbins, *Power Electronics*, 3rd ed., ch. 2 (switching
losses); H. D. Venable, "The K factor: a new mathematical tool for stability analysis and
synthesis", Proc. Powercon 10, 1983.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pint
from numpy.typing import NDArray

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.core.calc import BibRef, CalcLog, CalcStep, record
from circuitos.core.eseries import snap
from circuitos.core.units import Q_, parse_unit
from circuitos.design.base import DesignWarning, Trace

ERICKSON = BibRef(book="Erickson & Maksimović, Fundamentals of Power Electronics", edition="2nd")
MOHAN = BibRef(book="Mohan, Undeland & Robbins, Power Electronics", edition="3rd", chapter="2")
HART = BibRef(book="Hart, Power Electronics", edition="1st")
VENABLE = BibRef(
    book="Venable, The K factor: a new mathematical tool for stability analysis and synthesis",
    edition="Powercon 10, 1983",
)

FloatArray = NDArray[np.float64]


def ref(book: BibRef, chapter: str) -> BibRef:
    return book.model_copy(update={"chapter": chapter})


# --------------------------------------------------------------------------- datasheet values
def pval(
    rec: ComponentRecord | None, key: str, unit: str, prefer: Sequence[str] = ("max", "typ")
) -> float | None:
    """Value of parameter ``key`` in ``unit`` (first of ``prefer`` present), or None."""
    if rec is None:
        return None
    p = rec.parameters.get(key)
    if p is None:
        return None
    for name in prefer:
        v = getattr(p, name)
        if v is not None:
            return float(Q_(v, parse_unit(p.unit)).m_as(unit))
    return None


def pcond(rec: ComponentRecord | None, key: str, cond: str, unit: str) -> float | None:
    if rec is None:
        return None
    p: Parameter | None = rec.parameters.get(key)
    if p is None or cond not in p.conditions:
        return None
    return float(p.conditions[cond].to_pint().m_as(unit))


@dataclass
class SwitchData:
    """What the loss model uses from the chosen transistor."""

    kind: str  # "mosfet" | "igbt" | "ideal"
    r_on: float = 0.0  # Ω (MOSFET)
    v_on: float = 0.0  # V (IGBT, constant VCE(sat))
    tr: float = 0.0
    tf: float = 0.0
    coss: float = 0.0
    e_on: float = 0.0  # J at (v_test, i_test)
    e_off: float = 0.0
    v_test: float = 0.0
    i_test: float = 0.0
    qg: float = 0.0
    part: str = "ideal"


def switch_data(rec: ComponentRecord | None) -> SwitchData:
    if rec is None:
        return SwitchData(kind="ideal")
    if rec.category.startswith("igbt"):
        vt = pcond(rec, "Eon", "VCC", "V") or 0.0
        it = pcond(rec, "Eon", "IC", "A") or 0.0
        return SwitchData(
            kind="igbt",
            v_on=pval(rec, "VCE(sat)", "V") or 0.0,
            tr=pval(rec, "tr", "s", ("typ", "max")) or 0.0,
            tf=pval(rec, "tf", "s", ("typ", "max")) or 0.0,
            e_on=pval(rec, "Eon", "J") or 0.0,
            e_off=pval(rec, "Eoff", "J") or 0.0,
            v_test=vt,
            i_test=it,
            qg=pval(rec, "Qg", "C") or 0.0,
            part=rec.part_number,
        )
    return SwitchData(
        kind="mosfet",
        r_on=pval(rec, "RDS(on)", "ohm") or 0.0,
        tr=pval(rec, "tr", "s", ("typ", "max")) or 0.0,
        tf=pval(rec, "tf", "s", ("typ", "max")) or 0.0,
        coss=pval(rec, "Coss", "F", ("typ", "max")) or 0.0,
        qg=pval(rec, "Qg", "C") or 0.0,
        part=rec.part_number,
    )


@dataclass
class SwitchLoss:
    p_cond: float
    p_sw: float
    p_gate: float

    @property
    def total(self) -> float:
        return self.p_cond + self.p_sw


def switch_losses(
    log: CalcLog,
    des: str,
    sw: SwitchData,
    v_off: float,
    i_on: float,
    i_off: float,
    i_rms: float,
    i_avg: float,
    fs: float,
    v_gate: float = 15.0,
    hard_on: bool = True,
) -> tuple[SwitchLoss, list[str]]:
    """Conduction and hard-switching losses of one transistor (W)."""
    warn: list[str] = []
    if sw.kind == "ideal":
        return SwitchLoss(0.0, 0.0, 0.0), warn
    if sw.kind == "mosfet":
        pc = log.add(
            record(
                f"Pcond_{des}",
                f"Perda em condução de {des} ({sw.part})",
                r"P_{cond} = I_{rms}^2 R_{DS(on)}",
                output=Q_(i_rms**2 * sw.r_on, "W"),
                inputs={"I_rms": Q_(i_rms, "A"), "R_DS(on)": Q_(sw.r_on, "ohm")},
                assumptions=[
                    "R_DS(on) máximo do datasheet a 25 °C; a quente ele cresce (curva "
                    "normalizada do datasheet), então esta perda é otimista"
                ],
                reference=ref(ERICKSON, "4 (switching losses)"),
            )
        ).m_as("W")
        t_on = sw.tr if hard_on else 0.0
        psw = 0.5 * v_off * (i_on * t_on + i_off * sw.tf) * fs + 0.5 * sw.coss * v_off**2 * fs * (
            1.0 if hard_on else 0.0
        )
        ps = log.add(
            record(
                f"Psw_{des}",
                f"Perda de comutação de {des}",
                r"P_{sw} = \tfrac12 V_{off}(I_{on} t_r + I_{off} t_f) f_s"
                r" + \tfrac12 C_{oss} V_{off}^2 f_s",
                output=Q_(psw, "W"),
                inputs={
                    "V_off": Q_(v_off, "V"),
                    "I_on": Q_(i_on, "A"),
                    "I_off": Q_(i_off, "A"),
                    "t_r": Q_(sw.tr, "s").to("ns"),
                    "t_f": Q_(sw.tf, "s").to("ns"),
                    "C_oss": Q_(sw.coss, "F").to("pF"),
                    "f_s": Q_(fs, "Hz").to("kHz"),
                },
                assumptions=[
                    "comutação dura com transições lineares (aproximação de livro)",
                    "t_r e t_f típicos do ensaio do datasheet (mesmo R_G e tensão de porta)",
                    "C_oss medido a 25 V: superestima a energia em tensão alta",
                ]
                + ([] if hard_on else ["entrada em condução com corrente nula (MCD): sem perda"]),
                reference=MOHAN,
            )
        ).m_as("W")
    else:
        pc = log.add(
            record(
                f"Pcond_{des}",
                f"Perda em condução de {des} ({sw.part})",
                r"P_{cond} = V_{CE(sat)} I_{avg}",
                output=Q_(sw.v_on * i_avg, "W"),
                inputs={"V_CE(sat)": Q_(sw.v_on, "V"), "I_avg": Q_(i_avg, "A")},
                assumptions=[
                    "V_CE(sat) máximo no I_C de ensaio, tomado constante (o datasheet tabela "
                    "um só ponto; abaixo dele é conservador)"
                ],
                reference=ref(ERICKSON, "4 (switching losses)"),
            )
        ).m_as("W")
        if sw.v_test <= 0 or sw.i_test <= 0:
            warn.append(f"{des}: Eon/Eoff sem condições de ensaio; perda de comutação ignorada.")
            ps = 0.0
        else:
            kv = v_off / sw.v_test
            e = (
                sw.e_on * (i_on / sw.i_test) * (1.0 if hard_on else 0.0)
                + sw.e_off * i_off / sw.i_test
            ) * kv
            ps = log.add(
                record(
                    f"Psw_{des}",
                    f"Perda de comutação de {des} (energias do datasheet)",
                    r"P_{sw} = f_s \frac{V_{off}}{V_{ens}}\left(E_{on}\frac{I_{on}}{I_{ens}}"
                    r" + E_{off}\frac{I_{off}}{I_{ens}}\right)",
                    output=Q_(e * fs, "W"),
                    inputs={
                        "E_on": Q_(sw.e_on, "J").to("mJ"),
                        "E_off": Q_(sw.e_off, "J").to("mJ"),
                        "V_ens": Q_(sw.v_test, "V"),
                        "I_ens": Q_(sw.i_test, "A"),
                        "V_off": Q_(v_off, "V"),
                        "I_on": Q_(i_on, "A"),
                        "I_off": Q_(i_off, "A"),
                        "f_s": Q_(fs, "Hz").to("kHz"),
                    },
                    assumptions=[
                        "energias máximas a 25 °C escaladas linearmente com V e I (as curvas "
                        "E×I_C do datasheet não estão no catálogo)",
                        "E_on do ensaio já inclui a recuperação do diodo do ensaio",
                    ],
                    reference=MOHAN,
                )
            ).m_as("W")
    pg = sw.qg * v_gate * fs
    return SwitchLoss(pc, ps, pg), warn


@dataclass
class DiodeData:
    vf: float = 0.0
    qrr: float | None = None
    part: str = "ideal"
    schottky: bool = False


def diode_data(rec: ComponentRecord | None, vf: float) -> DiodeData:
    if rec is None:
        return DiodeData(vf=vf)
    return DiodeData(
        vf=vf,
        qrr=pval(rec, "Qrr", "C", ("typ", "max")),
        part=rec.part_number,
        schottky=rec.category.startswith("diode.schottky"),
    )


def diode_losses(
    log: CalcLog, des: str, d: DiodeData, i_avg: float, v_rev: float, fs: float, hard: bool = True
) -> tuple[float, list[str]]:
    warn: list[str] = []
    pc = d.vf * i_avg
    prr = 0.0
    note = "diodo Schottky: sem carga de recuperação"
    if not d.schottky and hard:
        if d.qrr is not None:
            prr = d.qrr * v_rev * fs
            note = "Q_rr típico do ensaio do datasheet (di/dt e I_F de ensaio)"
        elif d.part != "ideal":
            note = "o datasheet não traz Q_rr: perda de recuperação não calculada"
            warn.append(
                f"{des}: {d.part} não traz Q_rr; a perda de recuperação reversa não foi calculada."
            )
    elif not hard:
        note = "desliga com corrente nula (MCD): sem recuperação"
    p = log.add(
        record(
            f"Pd_{des}",
            f"Perdas de {des} ({d.part})",
            r"P_D = V_F I_{F(AV)} + Q_{rr} V_R f_s",
            output=Q_(pc + prr, "W"),
            inputs={
                "V_F": Q_(d.vf, "V"),
                "I_F(AV)": Q_(i_avg, "A"),
                "Q_rr": Q_(d.qrr or 0.0, "C").to("nC"),
                "V_R": Q_(v_rev, "V"),
                "f_s": Q_(fs, "Hz").to("kHz"),
            },
            assumptions=["V_F máximo do datasheet como queda constante", note],
            reference=ref(ERICKSON, "4 (switching losses)"),
        )
    ).m_as("W")
    return p, warn


# --------------------------------------------------------------------------- state space
@dataclass(frozen=True)
class SwitchedModel:
    """dx/dt = A_k x + B_k u for the two intervals of a CCM converter (u = [Vin, VD])."""

    states: tuple[str, ...]
    A1: FloatArray
    B1: FloatArray
    A2: FloatArray
    B2: FloatArray
    out: int  # index of the output-voltage state


def converter_model(
    topology: str, L1: float, C1: float, R: float, ron: float, L2: float = 1.0, C2: float = 1.0
) -> SwitchedModel:
    """Averaged-model matrices; the output state is the output-voltage magnitude.

    Buck, boost and buck-boost: x = [iL, vo]. Ćuk, SEPIC and Zeta: x = [iL1, vC1, iL2, vo],
    with the switch modelled as R_on and the diode as a constant drop VD.
    """
    if topology == "buck":
        A1 = np.array([[-ron / L1, -1 / L1], [1 / C1, -1 / (R * C1)]])
        B1 = np.array([[1 / L1, 0.0], [0.0, 0.0]])
        A2 = np.array([[0.0, -1 / L1], [1 / C1, -1 / (R * C1)]])
        B2 = np.array([[0.0, -1 / L1], [0.0, 0.0]])
        return SwitchedModel(("iL", "vo"), A1, B1, A2, B2, 1)
    if topology == "boost":
        A1 = np.array([[-ron / L1, 0.0], [0.0, -1 / (R * C1)]])
        B1 = np.array([[1 / L1, 0.0], [0.0, 0.0]])
        A2 = np.array([[0.0, -1 / L1], [1 / C1, -1 / (R * C1)]])
        B2 = np.array([[1 / L1, -1 / L1], [0.0, 0.0]])
        return SwitchedModel(("iL", "vo"), A1, B1, A2, B2, 1)
    if topology == "buckboost":
        A1 = np.array([[-ron / L1, 0.0], [0.0, -1 / (R * C1)]])
        B1 = np.array([[1 / L1, 0.0], [0.0, 0.0]])
        A2 = np.array([[0.0, -1 / L1], [1 / C1, -1 / (R * C1)]])
        B2 = np.array([[0.0, -1 / L1], [0.0, 0.0]])
        return SwitchedModel(("iL", "vo"), A1, B1, A2, B2, 1)
    # fourth order: x = [i1, v1, i2, vo]; C1 is the coupling capacitor, C2 the output one
    if topology == "cuk":
        A1 = np.array(
            [
                [-ron / L1, 0.0, -ron / L1, 0.0],
                [0.0, 0.0, -1 / C1, 0.0],
                [-ron / L2, 1 / L2, -ron / L2, -1 / L2],
                [0.0, 0.0, 1 / C2, -1 / (R * C2)],
            ]
        )
        B1 = np.array([[1 / L1, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]])
        A2 = np.array(
            [
                [0.0, -1 / L1, 0.0, 0.0],
                [1 / C1, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, -1 / L2],
                [0.0, 0.0, 1 / C2, -1 / (R * C2)],
            ]
        )
        B2 = np.array([[1 / L1, -1 / L1], [0.0, 0.0], [0.0, -1 / L2], [0.0, 0.0]])
        return SwitchedModel(("iL1", "vC1", "iL2", "vo"), A1, B1, A2, B2, 3)
    if topology == "sepic":
        A1 = np.array(
            [
                [-ron / L1, 0.0, -ron / L1, 0.0],
                [0.0, 0.0, -1 / C1, 0.0],
                [-ron / L2, 1 / L2, -ron / L2, 0.0],
                [0.0, 0.0, 0.0, -1 / (R * C2)],
            ]
        )
        B1 = np.array([[1 / L1, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]])
        A2 = np.array(
            [
                [0.0, -1 / L1, 0.0, -1 / L1],
                [1 / C1, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, -1 / L2],
                [1 / C2, 0.0, 1 / C2, -1 / (R * C2)],
            ]
        )
        B2 = np.array([[1 / L1, -1 / L1], [0.0, 0.0], [0.0, -1 / L2], [0.0, 0.0]])
        return SwitchedModel(("iL1", "vC1", "iL2", "vo"), A1, B1, A2, B2, 3)
    if topology == "zeta":
        A1 = np.array(
            [
                [-ron / L1, 0.0, -ron / L1, 0.0],
                [0.0, 0.0, -1 / C1, 0.0],
                [-ron / L2, 1 / L2, -ron / L2, -1 / L2],
                [0.0, 0.0, 1 / C2, -1 / (R * C2)],
            ]
        )
        B1 = np.array([[1 / L1, 0.0], [0.0, 0.0], [1 / L2, 0.0], [0.0, 0.0]])
        A2 = np.array(
            [
                [0.0, -1 / L1, 0.0, 0.0],
                [1 / C1, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, -1 / L2],
                [0.0, 0.0, 1 / C2, -1 / (R * C2)],
            ]
        )
        B2 = np.array([[0.0, -1 / L1], [0.0, 0.0], [0.0, -1 / L2], [0.0, 0.0]])
        return SwitchedModel(("iL1", "vC1", "iL2", "vo"), A1, B1, A2, B2, 3)
    raise ValueError(f"topologia desconhecida: {topology}")


def steady_state(m: SwitchedModel, D: float, u: FloatArray) -> FloatArray:
    """X = −A⁻¹ B U of the averaged model (Erickson ch. 7, state-space averaging)."""
    A = D * m.A1 + (1 - D) * m.A2
    B = D * m.B1 + (1 - D) * m.B2
    return np.asarray(-np.linalg.solve(A, B @ u), dtype=np.float64)


def solve_duty(m_of: Callable[[float], SwitchedModel], vo: float, u: FloatArray) -> float:
    """Smallest duty cycle whose averaged steady state gives ``vo``.

    With R_on the gain of the boost-type converters peaks and falls again at high D; the
    rising branch (the useful one) is searched on a grid, then refined by bisection.
    """

    def err(d: float) -> float:
        m = m_of(d)
        return float(steady_state(m, d, u)[m.out]) - vo

    grid = np.linspace(1e-4, 0.98, 400)
    prev_d, prev_e = float(grid[0]), err(float(grid[0]))
    for d in grid[1:]:
        e = err(float(d))
        if prev_e <= 0 <= e:
            lo, hi = prev_d, float(d)
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                if err(mid) < 0:
                    lo = mid
                else:
                    hi = mid
            return 0.5 * (lo + hi)
        prev_d, prev_e = float(d), e
    raise ValueError(
        "A tensão de saída pedida não é alcançável com essas perdas (o ganho máximo do "
        "conversor com R_on e V_F fica abaixo do pedido)."
    )


def gvd(m: SwitchedModel, D: float, u: FloatArray, f: FloatArray) -> NDArray[np.complex128]:
    """Control-to-output transfer v̂o/d̂ of the averaged small-signal model (Erickson ch. 7-8)."""
    A = D * m.A1 + (1 - D) * m.A2
    X = steady_state(m, D, u)
    Bd = (m.A1 - m.A2) @ X + (m.B1 - m.B2) @ u
    n = A.shape[0]
    out = np.empty(f.size, dtype=np.complex128)
    for k, fk in enumerate(f):
        s = 2j * math.pi * fk
        out[k] = np.linalg.solve(s * np.eye(n) - A, Bd)[m.out]
    return out


# --------------------------------------------------------------------------- compensator
@dataclass
class Compensator:
    kind: str  # "II" | "III"
    R1: float
    R2: float
    C1: float
    C2: float
    R3: float = math.inf
    C3: float = 0.0
    K: float = 1.0

    def h(self, f: FloatArray) -> NDArray[np.complex128]:
        """Inverting error amplifier gain magnitude/phase (sign removed: 180° of the inverter
        is the reference of the negative feedback)."""
        s = 2j * math.pi * f
        zf = (
            (self.R2 + 1 / (s * self.C1))
            * (1 / (s * self.C2))
            / (self.R2 + 1 / (s * self.C1) + 1 / (s * self.C2))
        )
        if self.kind == "II":
            zi = self.R1 + 0 * s
        else:
            zi = self.R1 * (self.R3 + 1 / (s * self.C3)) / (self.R1 + self.R3 + 1 / (s * self.C3))
        return np.asarray(zf / zi, dtype=np.complex128)


def boost_needed(pm: float, phase: float) -> float:
    """Phase boost (degrees) the error amplifier must add at fc: PM − 90° − ∠plant.

    ``phase`` is the plant phase unwrapped from low frequency (0° at DC); the inverting
    integrator contributes −90° (its 180° sign is the negative feedback itself).
    """
    return pm - 90.0 - phase


def k_factor(
    log: CalcLog, kind: str, fc: float, mag: float, phase: float, pm: float, R1: float
) -> Compensator:
    """Venable's K-factor synthesis for crossover ``fc`` and phase margin ``pm`` (degrees).

    ``mag`` and ``phase`` (degrees, unwrapped from DC) are those of the plant at ``fc``.
    """
    boost = max(boost_needed(pm, phase), 5.0)
    limit = 89.0 if kind == "II" else 178.0
    if boost > limit:
        raise ValueError(
            f"O compensador tipo {kind} não dá o avanço de fase necessário ({boost:.0f}°); "
            "use o tipo III ou reduza a frequência de cruzamento."
        )
    g = 1 / mag
    if kind == "II":
        K = math.tan(math.radians(boost / 2 + 45))
        C2 = 1 / (2 * math.pi * fc * g * K * R1)
        C1 = C2 * (K**2 - 1)
        R2 = K / (2 * math.pi * fc * C1)
        comp = Compensator("II", R1, R2, C1, C2, K=K)
        latex = (
            r"K = \tan\left(\frac{\phi_{boost}}{2} + 45°\right),\;"
            r"C_2 = \frac{1}{2\pi f_c G K R_1},\;C_1 = C_2(K^2-1),\;R_2 = \frac{K}{2\pi f_c C_1}"
        )
    else:
        K = math.tan(math.radians(boost / 4 + 45)) ** 2
        C2 = 1 / (2 * math.pi * fc * g * R1)
        C1 = C2 * (K - 1)
        R2 = math.sqrt(K) / (2 * math.pi * fc * C1)
        R3 = R1 / (K - 1)
        C3 = 1 / (2 * math.pi * fc * math.sqrt(K) * R3)
        comp = Compensator("III", R1, R2, C1, C2, R3, C3, K)
        latex = (
            r"K = \tan^2\left(\frac{\phi_{boost}}{4} + 45°\right),\;"
            r"C_2 = \frac{1}{2\pi f_c G R_1},\;C_1 = C_2(K-1),\;"
            r"R_2 = \frac{\sqrt K}{2\pi f_c C_1},\;"
            r"R_3 = \frac{R_1}{K-1},\;C_3 = \frac{1}{2\pi f_c \sqrt K R_3}"
        )
    log.add(
        record(
            "comp_K",
            f"Compensador tipo {kind} pelo fator K",
            latex,
            output=Q_(K, ""),
            inputs={
                "f_c": Q_(fc, "Hz").to("kHz"),
                "φ_boost": Q_(boost, "degree"),
                "|G_planta(f_c)|": Q_(mag, ""),
                "∠G_planta(f_c)": Q_(phase, "degree"),
                "R_1": Q_(R1, "ohm").to("kohm"),
                "MF": Q_(pm, "degree"),
            },
            assumptions=[
                "planta = H·G_vd/V_m (divisor, modulador e conversor)",
                "o amplificador inversor contribui −90° do integrador além do avanço",
            ],
            reference=VENABLE,
        )
    )
    return comp


def round_comp(c: Compensator) -> Compensator:
    """Resistors to E24 and capacitors to E12 (nearest)."""

    def r(v: float) -> float:
        return float(snap(Q_(v, "ohm"), "E24", "nearest").m_as("ohm")) if math.isfinite(v) else v

    def cap(v: float) -> float:
        return float(snap(Q_(v, "F"), "E12", "nearest").m_as("F")) if v > 0 else v

    return Compensator(c.kind, r(c.R1), r(c.R2), cap(c.C1), cap(c.C2), r(c.R3), cap(c.C3), c.K)


@dataclass
class Margins:
    fc: float
    pm: float
    gm_db: float | None


def margins(f: FloatArray, T: NDArray[np.complex128]) -> tuple[Margins, int]:
    """Phase margin at the last downward crossing of |T| = 1 and the gain margin at the first
    −180° crossing above it (phase unwrapped from the lowest frequency of the grid).

    Also returns the number of crossings of |T| = 1 (more than one: resonant peaks above unity
    gain, a conditionally stable loop).
    """
    mag = np.abs(T)
    deg = np.degrees(np.unwrap(np.angle(T)))
    lm = np.log10(mag)
    down = np.nonzero((lm[:-1] >= 0) & (lm[1:] < 0))[0]
    up = np.nonzero((lm[:-1] < 0) & (lm[1:] >= 0))[0]
    if down.size == 0:
        return Margins(float("nan"), float("nan"), None), 0
    i = int(down[-1])
    lf = np.log10(f)
    x = -lm[i] / (lm[i + 1] - lm[i])
    fc = float(10 ** (lf[i] + x * (lf[i + 1] - lf[i])))
    pm = 180.0 + float(deg[i] + x * (deg[i + 1] - deg[i]))
    gm = None
    rel = deg + 180.0
    for k in range(i, f.size - 1):
        if rel[k] > 0 >= rel[k + 1]:
            y = rel[k] / (rel[k] - rel[k + 1])
            gm = -20 * float(lm[k] + y * (lm[k + 1] - lm[k]))
            break
    return Margins(fc, pm, gm), int(down.size + up.size)


# --------------------------------------------------------------------------- magnetics
@dataclass
class InductorNeed:
    designator: str
    L: float
    I_pk: float
    I_rms: float
    dI_pp: float
    f: float


@dataclass
class MagneticsOut:
    steps: list[CalcStep] = field(default_factory=list)
    summary: dict[str, pint.Quantity] = field(default_factory=dict)
    losses: dict[str, float] = field(default_factory=dict)
    warnings: list[DesignWarning] = field(default_factory=list)
    traces: dict[str, Trace] = field(default_factory=dict)


MAG_LABELS = {
    "core": "Núcleo de {d}",
    "N": "Espiras de {d}",
    "gap": "Entreferro de {d}",
    "wire": "Fio de {d}",
    "P": "Perdas em {d} (cobre + núcleo)",
    "dT": "Elevação de temperatura de {d}",
}


def mag_labels(designators: Sequence[str]) -> dict[str, str]:
    out = {}
    for d in designators:
        out[f"{d}_N"] = f"Espiras de {d}"
        out[f"{d}_gap"] = f"Entreferro de {d}"
        out[f"{d}_P"] = f"Perdas em {d} (cobre + núcleo)"
        out[f"{d}_dT"] = f"Elevação de temperatura de {d}"
        out[f"{d}_R"] = f"Resistência do enrolamento de {d}"
        out[f"{d}_Bpk"] = f"Indução de pico em {d}"
    return out


def design_inductors(
    needs: Sequence[InductorNeed],
    catalogue: Callable[[str], list[ComponentRecord]],
    TA: float,
    J: float = 4e6,
) -> MagneticsOut:
    """SV-MAG for each inductor; failures become warnings (the design still shows)."""
    from circuitos.magnetics.design import MagSpec, Winding, design

    out = MagneticsOut()
    cores = catalogue("magnetic.core")
    mats = catalogue("magnetic.material")
    bobs = catalogue("magnetic.bobbin")
    for n in needs:
        spec = MagSpec(
            kind="indutor",
            f=n.f,
            windings=(Winding(n.designator, 1.0, n.I_rms),),
            L=n.L,
            I_pk=n.I_pk,
            dI_pp=n.dI_pp,
            J=J,
            TA=TA,
        )
        log = CalcLog()
        try:
            r = design(spec, cores, mats, bobs, log)
        except ValueError as e:
            out.warnings.append(DesignWarning(code="magnetico", message=f"{n.designator}: {e}"))
            continue
        for st in log:
            out.steps.append(
                st.model_copy(
                    update={
                        "id": f"{n.designator}_{st.id}",
                        "description": f"{n.designator}: {st.description}",
                    }
                )
            )
        w = r.windings[0]
        out.summary |= {
            f"{n.designator}_N": Q_(w.N, ""),
            f"{n.designator}_gap": Q_(r.gap, "m").to("mm"),
            f"{n.designator}_R": Q_(w.R, "ohm").to("mohm"),
            f"{n.designator}_Bpk": Q_(r.B_pk, "T").to("mT"),
            f"{n.designator}_P": Q_(r.P_total, "W"),
            f"{n.designator}_dT": Q_(r.dT, "K"),
        }
        out.losses[n.designator] = r.P_total
        out.warnings.append(
            DesignWarning(
                code="magnetico_ok",
                message=f"{n.designator}: núcleo {r.core.size} ({r.core.material}, "
                f"{r.core.record.part_number}), {w.N} espiras de {w.strand.n}× AWG {w.strand.awg}, "
                f"entreferro {r.gap * 1e3:.2f} mm, ocupação da janela {r.fill:.0%}.",
            )
        )
        for msg in r.warnings:
            out.warnings.append(
                DesignWarning(code="magnetico_premissa", message=f"{n.designator}: {msg}")
            )
    return out


@dataclass
class TransformerNeed:
    """A transformer (kind "transformador") or a flyback coupled inductor (kind "flyback").

    ``windings``: (name, turns ratio to the first winding, rms current).
    """

    designator: str
    kind: str
    f: float
    windings: tuple[tuple[str, float, float], ...]
    lam: float = 0.0  # V·s per half cycle (transformer)
    bipolar: bool = True
    L: float = 0.0  # magnetising inductance (flyback)
    I_pk: float = 0.0
    dI_pp: float = 0.0


def design_transformer(
    need: TransformerNeed,
    catalogue: Callable[[str], list[ComponentRecord]],
    TA: float,
    J: float = 4e6,
) -> MagneticsOut:
    """SV-MAG for a transformer or flyback inductor; also returns its magnetising inductance
    (N1²·AL of the ungapped set, or the gapped design L) as ``<des>_Lm``."""
    from typing import cast

    from circuitos.magnetics.design import Kind, MagSpec, Winding, design

    out = MagneticsOut()
    spec = MagSpec(
        kind=cast(Kind, need.kind),
        f=need.f,
        windings=tuple(Winding(n, r, i) for n, r, i in need.windings),
        L=need.L,
        I_pk=need.I_pk,
        dI_pp=need.dI_pp,
        lam=need.lam,
        bipolar=need.bipolar,
        J=J,
        TA=TA,
    )
    log = CalcLog()
    d = need.designator
    try:
        r = design(
            spec,
            catalogue("magnetic.core"),
            catalogue("magnetic.material"),
            catalogue("magnetic.bobbin"),
            log,
        )
    except ValueError as e:
        out.warnings.append(DesignWarning(code="magnetico", message=f"{d}: {e}"))
        return out
    for st in log:
        out.steps.append(
            st.model_copy(update={"id": f"{d}_{st.id}", "description": f"{d}: {st.description}"})
        )
    n1 = r.windings[0].N
    lm = need.L if need.kind == "flyback" else n1**2 * r.core.AL
    out.summary |= {f"{d}_N{k + 1}": Q_(w.N, "") for k, w in enumerate(r.windings)} | {
        f"{d}_Lm": Q_(lm, "H").to("mH"),
        f"{d}_Bpk": Q_(r.B_pk, "T").to("mT"),
        f"{d}_P": Q_(r.P_total, "W"),
        f"{d}_dT": Q_(r.dT, "K"),
        f"{d}_ratio": Q_(r.windings[1].N / n1 if len(r.windings) > 1 else 1.0, ""),
    }
    if need.kind == "flyback":
        out.summary[f"{d}_gap"] = Q_(r.gap, "m").to("mm")
    out.losses[d] = r.P_total
    wtxt = ", ".join(f"{w.name}: {w.N} esp. {w.strand.n}× AWG {w.strand.awg}" for w in r.windings)
    out.warnings.append(
        DesignWarning(
            code="magnetico_ok",
            message=f"{d}: núcleo {r.core.size} ({r.core.material}); {wtxt}"
            + (f"; entreferro {r.gap * 1e3:.2f} mm" if need.kind == "flyback" else "")
            + f"; ocupação {r.fill:.0%}.",
        )
    )
    want = need.windings[1][1] if len(need.windings) > 1 else 1.0
    got = r.windings[1].N / n1 if len(r.windings) > 1 else 1.0
    if abs(got / want - 1) > 0.03:
        out.warnings.append(
            DesignWarning(
                code="relacao_espiras",
                message=f"{d}: a relação de espiras inteira ({got:.4g}) difere "
                f"{abs(got / want - 1):.1%} da calculada ({want:.4g}); a razão cíclica do "
                "controle corrige, mas confira a faixa de D.",
            )
        )
    for msg in r.warnings:
        out.warnings.append(DesignWarning(code="magnetico_premissa", message=f"{d}: {msg}"))
    return out


def merge_magnetics(
    log: CalcLog,
    summary: dict[str, pint.Quantity],
    warnings: list[DesignWarning],
    mag: MagneticsOut,
) -> float:
    for st in mag.steps:
        log.add_step(st)
    summary |= mag.summary
    warnings += mag.warnings
    return sum(mag.losses.values())


def efficiency_step(
    log: CalcLog, po: float, losses: Mapping[str, float], step_id: str = "eta"
) -> float:
    total = sum(losses.values())
    return float(
        log.add(
            record(
                step_id,
                "Rendimento estimado",
                r"\eta = \frac{P_o}{P_o + \sum P_{perdas}}",
                output=Q_(100 * po / (po + total), "percent"),
                inputs={"P_o": Q_(po, "W")} | {f"P_{k}": Q_(v, "W") for k, v in losses.items()},
                assumptions=[
                    "sem perdas em capacitores (RSE), trilhas e circuito de comando",
                ],
                reference=ref(ERICKSON, "3 (efficiency)"),
            )
        ).m_as("percent")
    )


# --------------------------------------------------------------------------- spice helpers
def spice_diode(name: str, vf: float) -> str:
    """Constant-drop diode (1 mΩ above VF, 1 µS reverse leakage), as in DM-RETC1."""
    return "\n".join(
        [
            f".subckt {name} a k",
            f"BD a k I = (v(a,k) > {vf:.9g}) ? (v(a,k) - {vf:.9g}) / 1m : v(a,k) * 1u",
            ".ends",
        ]
    )


def spice_switch(name: str, sw: SwitchData) -> str:
    """Voltage-controlled switch: R_on (MOSFET) or R_on plus a constant VCE(sat) (IGBT)."""
    ron = sw.r_on if sw.kind == "mosfet" and sw.r_on > 0 else 1e-3
    lines = [f".model {name}_SW SW(VT=2.5 VH=0.1 RON={ron:.9g} ROFF=1e7)"]
    lines += [f".subckt {name} d s g", f"S1 d x g 0 {name}_SW"]
    lines.append(f"VCE x s DC {sw.v_on:.9g}" if sw.kind == "igbt" else "VCE x s DC 0")
    lines.append(".ends")
    return "\n".join(lines)


def pwm_source(name: str, node: str, D: float, fs: float, delay: float = 0.0) -> str:
    T = 1 / fs
    edge = T / 1000
    on = max(D * T - edge, edge)
    return f"{name} {node} 0 PULSE(0 5 {delay:.9g} {edge:.9g} {edge:.9g} {on:.9g} {T:.9g})"


def ipp(values: Sequence[float]) -> float:
    return float(max(values) - min(values))
