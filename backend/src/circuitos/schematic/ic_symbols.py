"""Integrated circuits of the schematic library that are not op-amps: the 555 timer.

``timer555`` is a behavioural model of the bipolar 555 built from the functional block diagram
of the TI datasheet (SLFS022K, section 6.2): a divider from VCC to GND whose upper tap is the
CONT pin (threshold comparator reference, 2/3 VCC) and whose lower tap is the trigger reference
(1/3 VCC), an SR latch with RESET over TRIG over THRES (note under the truth table, table 6-1),
the output stage and the discharge transistor. Every default value is the one of the NE555P in
the catalogue (TI SLFS022K, Electrical characteristics, p. 5); a catalogue part placed with the
symbol brings its own values (``IC_CATALOGUE``).

Values derived from two points of the datasheet table (output resistances) say so in the help.
The divider resistance is not given by TI: it is a didactic value, marked as such; it only sets
how stiff the CONT pin is.
"""

from __future__ import annotations

from collections.abc import Callable

from circuitos.components.models import ComponentRecord
from circuitos.core.units import Q_, parse_unit
from circuitos.schematic.model import Component
from circuitos.schematic.symbols_base import ParamDef, PinDef, Symbol

Value = Callable[[str], str]

_TI = "TI NE555 (SLFS022K), p. 5"

IC_GROUP = "Circuitos integrados"

# pins on the two sides of the box, as the usual 555 drawing: inputs left, supply/output right
TIMER_PINS = (
    PinDef("TRIG", -4, -3),
    PinDef("THRES", -4, -1),
    PinDef("CONT", -4, 1),
    PinDef("DISCH", -4, 3),
    PinDef("VCC", 4, -3),
    PinDef("RESET", 4, -1),
    PinDef("OUT", 4, 1),
    PinDef("GND", 4, 3),
)

IC_SYMBOLS: list[Symbol] = [
    Symbol(
        "timer555",
        "Temporizador 555",
        IC_GROUP,
        "X",
        TIMER_PINS,
        (
            ParamDef(
                "vreset",
                "Limiar do RESET",
                "V",
                "0.7",
                help=f"{_TI}: RESET voltage level, 0,7 V típico (0,3 a 1 V).",
            ),
            ParamDef(
                "vdrop",
                "Queda da saída em nível alto (VCC − VOH)",
                "V",
                "1.7",
                help=f"{_TI}: VOH = 13,3 V típico com VCC = 15 V e IOH = −100 mA.",
            ),
            ParamDef(
                "roh",
                "Resistência de saída em nível alto",
                "Ω",
                "8",
                help=f"{_TI}: (13,3 − 12,5) V / (200 − 100) mA, de VOH a 100 e a 200 mA.",
            ),
            ParamDef(
                "vol",
                "Saída em nível baixo (VOL)",
                "V",
                "0.1",
                help=f"{_TI}: VOL = 0,1 V típico com VCC = 15 V e IOL = 10 mA.",
            ),
            ParamDef(
                "rol",
                "Resistência de saída em nível baixo",
                "Ω",
                "7.5",
                help=f"{_TI}: (0,4 − 0,1) V / (50 − 10) mA, de VOL a 10 e a 50 mA. Acima de "
                "50 mA o VOL real cresce mais depressa (2 V a 100 mA).",
            ),
            ParamDef(
                "rdis",
                "Resistência da descarga ligada",
                "Ω",
                "18.75",
                help=f"{_TI}: DISCH on-state voltage 0,15 V típico com 8 mA (VCC = 5 V).",
            ),
            ParamDef(
                "icc",
                "Corrente de alimentação com VCC = 15 V",
                "A",
                "10m",
                help=f"{_TI}: ICC = 10 mA típico com VCC = 15 V, saída baixa e sem carga; o "
                "modelo a faz proporcional a VCC (3 mA típicos a 5 V no datasheet).",
            ),
            ParamDef(
                "rdiv",
                "Resistor do divisor interno (cada um)",
                "Ω",
                "5k",
                help="Valor didático: o datasheet TI não informa os resistores internos. Só muda "
                "a impedância vista no pino CONT; os limiares continuam em 2/3 e 1/3 de VCC.",
            ),
        ),
        description="555 bipolar comportamental (diagrama de blocos do TI SLFS022K): divisor "
        "interno de VCC a GND com CONT na derivação de 2/3, comparadores de limiar (THRES > "
        "CONT) e de disparo (TRIG < CONT/2), báscula SR em que RESET vence TRIG e TRIG vence "
        "THRES, saída com VOH = VCC − queda e transistor de descarga em DISCH. Ligue RESET a "
        "VCC quando não usar (aberto ele fica em nível baixo e a saída não sobe).",
        ref_prefix="U",
    ),
]

IC_KINDS = {s.kind for s in IC_SYMBOLS}

# catalogue parts: symbol parameter <- (record parameter, unit); derived values in ic_value
IC_CATALOGUE: dict[str, tuple[tuple[str, ...], dict[str, tuple[str, str]]]] = {
    "timer555": (("timer",), {"vreset": ("V_reset", "V"), "vol": ("VOL", "V")}),
}


def _typ(record: ComponentRecord, name: str, unit: str) -> float | None:
    p = record.parameters.get(name)
    if p is None:
        return None
    if p.typ is None:
        return None
    return float(Q_(p.typ, parse_unit(p.unit)).to(parse_unit(unit)).magnitude)


def _cond(record: ComponentRecord, name: str, key: str, unit: str) -> float | None:
    """Test condition of a datasheet value (VCC, IO) in SI units, magnitude only."""
    p = record.parameters.get(name)
    q = (p.conditions or {}).get(key) if p is not None else None
    if q is None:
        return None
    return abs(float(q.to_pint().m_as(unit)))


def ic_value(kind: str, record: ComponentRecord, name: str) -> str | None:
    """Values of a catalogue 555 that come from two points of its table, not from one number."""
    if kind != "timer555":
        return None
    if name == "vdrop":
        voh, vcc = _typ(record, "VOH", "V"), _cond(record, "VOH", "VCC", "V")
        return f"{vcc - voh:.6g}" if voh is not None and vcc is not None else None
    if name == "roh":
        v1, v2 = _typ(record, "VOH", "V"), _typ(record, "VOH@200mA", "V")
        i1, i2 = _cond(record, "VOH", "IO", "A"), _cond(record, "VOH@200mA", "IO", "A")
        if None in (v1, v2, i1, i2) or i1 == i2:
            return None
        return f"{abs((v1 - v2) / (i2 - i1)):.6g}"  # type: ignore[operator]
    if name == "rol":
        v1, v2 = _typ(record, "VOL", "V"), _typ(record, "VOL@50mA", "V")
        i1, i2 = _cond(record, "VOL", "IO", "A"), _cond(record, "VOL@50mA", "IO", "A")
        if None in (v1, v2, i1, i2) or i1 == i2:
            return None
        return f"{abs((v2 - v1) / (i2 - i1)):.6g}"  # type: ignore[operator]
    if name == "rdis":
        v, i = _typ(record, "V_disch", "V"), _cond(record, "V_disch", "IO", "A")
        return f"{v / i:.6g}" if v is not None and i else None
    if name == "icc":
        i = _typ(record, "ICC", "A")
        return f"{i:.6g}" if i is not None else None
    return None


def emit_ic(comp: Component, n: dict[str, str], v: Value) -> list[str]:
    """SPICE lines of an integrated circuit (behavioural)."""
    x = comp.ref.lower()
    if comp.kind != "timer555":
        raise ValueError(f"tipo {comp.kind} sem modelo")
    vcc, gnd = n["VCC"], n["GND"]
    lo, q, qn, qb = f"{x}_lo", f"{x}_q", f"{x}_qn", f"{x}_qb"
    ob = f"{x}_ob"
    hi = f"(V({q}) > 0.5)"
    rdiv = v("rdiv")
    return [
        # internal divider: CONT is the upper tap (2/3 VCC), the lower tap feeds the trigger
        f"R{x}_d1 {vcc} {n['CONT']} {rdiv}",
        f"R{x}_d2 {n['CONT']} {lo} {rdiv}",
        f"R{x}_d3 {lo} {gnd} {rdiv}",
        # latch: RESET over TRIG over THRES (TI SLFS022K, table 6-1)
        f"B{x}_s {qn} 0 V = (V({n['RESET']},{gnd}) < ({v('vreset')})) ? 0 : "
        f"((V({n['TRIG']},{gnd}) < V({lo},{gnd})) ? 1 : "
        f"((V({n['THRES']},{gnd}) > V({n['CONT']},{gnd})) ? 0 : ({hi} ? 1 : 0)))",
        f"R{x}_l {qn} {q} 1k",
        f"C{x}_l {q} 0 1p",
        # output stage: level and output resistance of the datasheet (edges of about 1 ns,
        # faster than the 100 ns of the datasheet: an RC here rings with long time steps)
        f"B{x}_o {ob} {gnd} V = {hi} ? max(V({vcc},{gnd}) - ({v('vdrop')}), 0) : ({v('vol')})",
        # output resistance blended with the latch state (no step in the conductance)
        f"B{x}_r {ob} {n['OUT']} I = V({ob},{n['OUT']}) / (({v('rol')}) + "
        f"(({v('roh')}) - ({v('rol')}))*min(max(V({q}), 0), 1))",
        # discharge transistor: on while the output is low
        f"B{x}_qb {qb} 0 V = 1 - V({q})",
        f"S{x}_dis {n['DISCH']} {gnd} {qb} 0 sw_{x}",
        f".model sw_{x} sw vt=0.5 vh=0.1 ron={v('rdis')} roff=1g",
        # supply current: ICC less what the divider already draws
        f"B{x}_cc {vcc} {gnd} I = max(V({vcc},{gnd}), 0) * "
        f"max(({v('icc')})/15 - 1/(3*({rdiv})), 0)",
        # high-impedance inputs (nA): keep the nodes defined when left open
        f"R{x}_tr {n['TRIG']} {gnd} 1g",
        f"R{x}_th {n['THRES']} {gnd} 1g",
        f"R{x}_rs {n['RESET']} {gnd} 1g",
    ]
