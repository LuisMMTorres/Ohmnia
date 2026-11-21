"""Transformers sized by nameplate data (Vp, Vs, S), single-phase and three-phase.

Each winding pair is two coupled inductors (magnetising inductance on the primary, the secondary
scaled by the turns ratio squared) with the copper resistance in series: the simplified
equivalent circuit, without core losses. The turns ratio comes from the winding voltages (or is
given); the magnetising current and copper losses are percentages the user sets, so the
model is only as good as those numbers (no-load and short-circuit test data).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_

COUPLING = 0.9999  # k < 1: ngspice needs it; leakage ≈ 2(1 − k)·Xm, negligible
_ASSUMPTIONS = [
    "Circuito equivalente simplificado: indutância de magnetização no primário, resistências "
    "dos enrolamentos em série, sem perdas no núcleo nem saturação.",
    "Dispersão desprezada (acoplamento k = 0,9999).",
]


@dataclass(frozen=True)
class Winding:
    """One core leg: primary and secondary winding of the same phase."""

    vp: float  # primary winding voltage, V rms
    vs: float  # secondary winding voltage, V rms (from the turns ratio)
    turns: float  # Np/Ns
    lp: float  # H
    ls: float  # H
    rp: float  # ohm
    rs: float  # ohm


_CHAPMAN = BibRef(
    book="Chapman, Electric Machinery Fundamentals",
    edition="5th",
    chapter="2 (autotransformador)",
)


class TransformerError(ValueError):
    pass


def winding_voltage(v_line: float, conn: str) -> float:
    """Voltage across one winding: line voltage in delta, line/√3 in wye."""
    return v_line if conn == "D" else v_line / math.sqrt(3)


def size(
    ref: str,
    vp: float,
    vs: float,
    turns: float | None,
    s_winding: float,
    freq: float,
    imag_pct: float,
    rcu_pct: float,
    log: CalcLog,
) -> Winding:
    """Inductances and resistances of one winding pair; adds the steps to ``log`` once."""
    if min(vp, s_winding, freq) <= 0 or (turns is None and vs <= 0):
        raise TransformerError(f"{ref}: tensões, potência e frequência devem ser positivas")
    if not 0 < imag_pct < 100 or not 0 <= rcu_pct < 50:
        raise TransformerError(f"{ref}: magnetização entre 0 e 100 %, perdas entre 0 e 50 %")
    a = turns if turns is not None else vp / vs
    if a <= 0:
        raise TransformerError(f"{ref}: relação de espiras deve ser positiva")
    vs_eff = vp / a
    ip, is_ = s_winding / vp, s_winding / vs_eff
    imag = imag_pct / 100 * ip
    lp = vp / (2 * math.pi * freq * imag)
    ls = lp / a**2
    pcu = rcu_pct / 100 * s_winding
    rp = 0.5 * pcu / ip**2
    rs = 0.5 * pcu / is_**2
    if f"{ref}_lm" not in {st.id for st in log}:
        log.add(
            record(
                f"{ref}_a",
                f"Relação de espiras de {ref} (por enrolamento)",
                r"a = \frac{N_p}{N_s} = \frac{V_p}{V_s}",
                Q_(a, "dimensionless"),
                {"V_p": Q_(vp, "V"), "V_s": Q_(vs_eff, "V")},
                ["Dada pelo usuário." if turns is not None else "Das tensões de placa."],
            )
        )
        log.add(
            record(
                f"{ref}_lm",
                f"Indutância de magnetização de {ref}",
                r"L_m = \frac{V_p}{2 \pi f \, I_m}, \quad I_m = i_m \frac{S}{V_p}",
                Q_(lp, "H"),
                {"V_p": Q_(vp, "V"), "f": Q_(freq, "Hz"), "I_m": Q_(imag, "A")},
                _ASSUMPTIONS,
            )
        )
        log.add(
            record(
                f"{ref}_rcu",
                f"Resistência dos enrolamentos de {ref}",
                r"R_p = \frac{P_{cu}/2}{I_p^2}, \quad R_s = \frac{P_{cu}/2}{I_s^2}, "
                r"\quad P_{cu} = p_{cu} S",
                Q_(rp, "ohm"),
                {
                    "P_cu": Q_(pcu, "W"),
                    "I_p": Q_(ip, "A"),
                    "I_s": Q_(is_, "A"),
                    "R_s": Q_(rs, "ohm"),
                },
                ["Perdas no cobre divididas igualmente entre primário e secundário."],
            )
        )
    return Winding(vp, vs_eff, a, lp, ls, rp, rs)


def pair_lines(name: str, p: tuple[str, str], s: tuple[str, str], w: Winding) -> list[str]:
    """Coupled-inductor netlist of one winding pair; dots on p[0] and s[0]."""
    a, b = f"{name}_p".lower(), f"{name}_s".lower()
    return [
        f"R_{name}_p {p[0]} {a} {w.rp:.9g}",
        f"L_{name}_p {a} {p[1]} {w.lp:.9g}",
        f"R_{name}_s {s[0]} {b} {w.rs:.9g}",
        f"L_{name}_s {b} {s[1]} {w.ls:.9g}",
        f"K_{name} L_{name}_p L_{name}_s {COUPLING}",
    ]


def three_phase_lines(
    ref: str, nodes: list[str], conn_p: str, conn_s: str, w: Winding
) -> list[str]:
    """Three winding pairs (one per core leg) connected in wye (Y) or delta (D)."""
    h, x = nodes[0:3], nodes[4:7]
    h0, x0 = nodes[3], nodes[7]

    def ends(t: list[str], neutral: str, conn: str, i: int) -> tuple[str, str]:
        return (t[i], neutral) if conn == "Y" else (t[i], t[(i + 1) % 3])

    lines: list[str] = []
    for i, ph in enumerate("ABC"):
        lines += pair_lines(f"{ref}_{ph}", ends(h, h0, conn_p, i), ends(x, x0, conn_s, i), w)
    lines.append(f"R_{ref}_iso {h[0]} {x[0]} 1g")
    # an unused neutral (delta) still needs a DC path if the user wired it
    if conn_p == "D":
        lines.append(f"R_{ref}_h0 {h0} {h[0]} 1g")
    if conn_s == "D":
        lines.append(f"R_{ref}_x0 {x0} {x[0]} 1g")
    return lines


@dataclass(frozen=True)
class AutoWinding:
    """Autotransformer: series winding (H to X) and common winding (X to N) on one core."""

    vh: float  # high side voltage, V rms
    vx: float  # tap voltage, V rms
    l_series: float  # H
    l_common: float  # H
    r_series: float  # ohm
    r_common: float  # ohm


def size_auto(
    ref: str,
    vh: float,
    vx: float,
    s_rated: float,
    freq: float,
    imag_pct: float,
    rcu_pct: float,
    log: CalcLog,
) -> AutoWinding:
    """Inductances and resistances of a single-phase autotransformer from its nameplate.

    The full winding (H to N) takes the magnetising current; the series part has
    (Vh − Vx)/Vh of the turns and the common part Vx/Vh, so with tight coupling the
    inductances split as the squares of those fractions. The series winding carries the
    high side current Ih = S/Vh, the common winding the difference Ix − Ih (Chapman,
    *Electric Machinery Fundamentals*, 5th ed., ch. 2, autotransformer section).
    """
    if min(vh, vx, s_rated, freq) <= 0:
        raise TransformerError(f"{ref}: tensões, potência e frequência devem ser positivas")
    if vx >= vh:
        raise TransformerError(f"{ref}: a tensão da derivação deve ser menor que a de entrada")
    if not 0 < imag_pct < 100 or not 0 <= rcu_pct < 50:
        raise TransformerError(f"{ref}: magnetização entre 0 e 100 %, perdas entre 0 e 50 %")
    ih, ix = s_rated / vh, s_rated / vx
    imag = imag_pct / 100 * ih
    l_full = vh / (2 * math.pi * freq * imag)
    fs, fc = (vh - vx) / vh, vx / vh
    pcu = rcu_pct / 100 * s_rated
    r_series = 0.5 * pcu / ih**2
    r_common = 0.5 * pcu / (ix - ih) ** 2
    if f"{ref}_lm" not in {st.id for st in log}:
        log.add(
            record(
                f"{ref}_a",
                f"Relação de transformação de {ref}",
                r"a = \frac{N_{serie} + N_{comum}}{N_{comum}} = \frac{V_H}{V_X}",
                Q_(vh / vx, "dimensionless"),
                {"V_H": Q_(vh, "V"), "V_X": Q_(vx, "V")},
                ["Das tensões de placa."],
                reference=_CHAPMAN,
            )
        )
        log.add(
            record(
                f"{ref}_lm",
                f"Indutâncias dos enrolamentos de {ref}",
                r"L_{HN} = \frac{V_H}{2 \pi f \, I_m}, \quad "
                r"L_{serie} = L_{HN} \left(\frac{V_H - V_X}{V_H}\right)^2, \quad "
                r"L_{comum} = L_{HN} \left(\frac{V_X}{V_H}\right)^2",
                Q_(l_full, "H"),
                {
                    "V_H": Q_(vh, "V"),
                    "f": Q_(freq, "Hz"),
                    "I_m": Q_(imag, "A"),
                    "L_serie": Q_(l_full * fs**2, "H"),
                    "L_comum": Q_(l_full * fc**2, "H"),
                },
                _ASSUMPTIONS,
            )
        )
        log.add(
            record(
                f"{ref}_rcu",
                f"Resistência dos enrolamentos de {ref}",
                r"R_{serie} = \frac{P_{cu}/2}{I_H^2}, \quad "
                r"R_{comum} = \frac{P_{cu}/2}{(I_X - I_H)^2}, \quad P_{cu} = p_{cu} S",
                Q_(r_series, "ohm"),
                {
                    "P_cu": Q_(pcu, "W"),
                    "I_H": Q_(ih, "A"),
                    "I_X": Q_(ix, "A"),
                    "R_comum": Q_(r_common, "ohm"),
                },
                ["Perdas no cobre divididas igualmente entre os enrolamentos série e comum."],
            )
        )
    return AutoWinding(vh, vx, l_full * fs**2, l_full * fc**2, r_series, r_common)


def auto_lines(name: str, h: str, x: str, n: str, w: AutoWinding) -> list[str]:
    """Series winding H to X and common winding X to N, both dotted at the top (aiding)."""
    a, b = f"{name}_s".lower(), f"{name}_c".lower()
    return [
        f"R_{name}_s {h} {a} {w.r_series:.9g}",
        f"L_{name}_s {a} {x} {w.l_series:.9g}",
        f"R_{name}_c {x} {b} {w.r_common:.9g}",
        f"L_{name}_c {b} {n} {w.l_common:.9g}",
        f"K_{name} L_{name}_s L_{name}_c {COUPLING}",
    ]


def _float_paths(ref: str, nodes: list[str]) -> list[str]:
    """1 GΩ from each coil end to ground: coils the user leaves open still have a DC path."""
    return [
        f"R_{ref}_g{i} {node} 0 1g"
        for i, node in enumerate(dict.fromkeys(nd for nd in nodes if nd != "0"))
    ]


def open_three_phase_lines(ref: str, nodes: list[str], w: Winding) -> list[str]:
    """Six coils with both ends free (1U1-1U2, 1V1-1V2, 1W1-1W2 / 2U1 … 2W2): the user
    connects wye or delta outside; one winding pair per core leg."""
    lines: list[str] = []
    for i, ph in enumerate("UVW"):
        p = (nodes[2 * i], nodes[2 * i + 1])
        s = (nodes[6 + 2 * i], nodes[6 + 2 * i + 1])
        lines += pair_lines(f"{ref}_{ph}", p, s, w)
    return lines + _float_paths(ref, nodes)


def four_coil_lines(ref: str, nodes: list[str], w: Winding) -> list[str]:
    """Two primary coils (P1-P2, P3-P4) and two secondary coils (S1-S2, S3-S4) on one core.

    Each coil has the inductance of the whole winding at Vp (in parallel the pair takes the
    rated current, in series twice the voltage and half the current) and twice its resistance,
    so the copper losses at rated load are the same in series and in parallel.
    """
    coils = [
        (f"L_{ref}_p1", nodes[0], nodes[1], w.lp, 2 * w.rp),
        (f"L_{ref}_p2", nodes[2], nodes[3], w.lp, 2 * w.rp),
        (f"L_{ref}_s1", nodes[4], nodes[5], w.ls, 2 * w.rs),
        (f"L_{ref}_s2", nodes[6], nodes[7], w.ls, 2 * w.rs),
    ]
    lines: list[str] = []
    for name, a, b, ind, res in coils:
        mid = f"{name[2:]}_r".lower()
        lines += [f"R{name[1:]} {a} {mid} {res:.9g}", f"{name} {mid} {b} {ind:.9g}"]
    for i in range(4):
        for j in range(i + 1, 4):
            lines.append(f"K_{ref}_{i}{j} {coils[i][0]} {coils[j][0]} {COUPLING}")
    return lines + _float_paths(ref, nodes)
