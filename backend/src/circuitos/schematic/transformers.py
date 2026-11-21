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

from circuitos.core.calc import CalcLog, record
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
