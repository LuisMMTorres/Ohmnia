"""Component damage: simulated voltage, current, power and junction temperature against limits.

Every limit comes from the catalogue record of the part (absolute maximum ratings, with the
datasheet and page it was read from) or from a rating the user typed on a generic part (the
resistor's power, the capacitor's voltage). A generic part without a rating is not checked: the
program never makes a limit up.

What is measured, after a transient (or at the operating point):

- voltage limits (VRRM, VCEO, VDS, VGS, ...): the peak of the blocking voltage;
- continuous current limits (IF(AV), IC, ID, IT(RMS), ...): the mean (or RMS) of the second
  half of the run, so the start-up does not count; repetitive peak ratings (IFSM, ICM, IDM,
  ITSM): the peak over the whole run;
- power (Ptot, P_rated): mean of v·i over the second half;
- junction temperature: Tj = Ta + P·Rθja (no heat sink, steady state), against Tj max.

The currents are read from 0 V sources the netlist puts in series with one pin of each checked
part (``vsn_<ref>_<pin>``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from circuitos.components.models import ComponentRecord
from circuitos.core.units import Q_
from circuitos.schematic.model import Component
from circuitos.schematic.values import try_parse

Measure = Literal["peak", "mean", "rms", "peak_abs"]
Quantity = Literal["V", "I", "P", "T"]


@dataclass(frozen=True)
class Limit:
    """One rating of one part and how to measure the matching simulated quantity."""

    ref: str
    quantity: Quantity
    name: str  # rating as printed in the datasheet: VRRM, IC, Ptot, Tj max
    limit: float  # SI: V, A, W, °C
    unit: str
    measure: Measure
    v_pos: str | None = None  # node of the voltage (blocking polarity), None = ground
    v_neg: str | None = None
    current: str | None = None  # current vector into the part
    current_sign: float = 1.0  # +1: current into the pin; -1: out of it
    resistance: float | None = None  # resistor: P = v²/R, no current needed
    rth: float | None = None  # K/W, junction to ambient: quantity T
    t_amb: float | None = None  # °C
    source: str = ""  # where the rating comes from
    advice: str = ""  # how to avoid it (pt-BR)
    reviewed: bool = True  # False: the rating is still "a verificar" in the catalogue


@dataclass(frozen=True)
class Damage:
    ref: str
    quantity: Quantity
    name: str
    value: float
    limit: float
    unit: str
    cause: str
    advice: str
    source: str
    reviewed: bool


# --------------------------------------------------------------------------- the ratings


def _rating(rec: ComponentRecord, key: str, unit: str) -> tuple[float, str, bool] | None:
    """Absolute maximum rating ``key`` in SI ``unit`` with its source text, or None."""
    p = rec.parameters.get(key)
    if p is None:
        return None
    value = next((v for v in (p.max, p.typ, p.min) if v is not None), None)
    if value is None:
        return None
    try:
        si = float(Q_(value, p.unit).to(unit).magnitude) if p.unit != unit else float(value)
    except Exception:
        return None
    where = ""
    if p.source is not None:
        doc = next((d for d in rec.datasheets if d.id == p.source.datasheet_id), None)
        bits = [doc.document_number or doc.manufacturer] if doc else []
        if doc and doc.revision:
            rev = doc.revision
            bits.append(rev if rev.lower().startswith("rev") else f"rev. {rev}")
        if p.source.page:
            bits.append(f"p. {p.source.page}")
        where = f" ({', '.join(bits)})" if bits else ""
    text = f"{rec.manufacturer} {rec.part_number}: {key} = {_fmt(si, unit)}{where}"
    return si, text, p.status == "revisado"


def _fmt(value: float, unit: str) -> str:
    if unit == "°C":
        return f"{value:.0f} °C"
    prefixes = [(1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n")]
    a = abs(value)
    for scale, p in prefixes:
        if a >= scale or scale == 1e-9:
            return f"{value / scale:.3g} {p}{unit}".replace(".", ",")
    return f"{value:g} {unit}"


# advice per rating family (pt-BR)
_ADVICE: dict[str, str] = {
    "Vrev": "Escolha uma peça com tensão reversa maior (folga de pelo menos 50 %) ou limite a "
    "tensão aplicada; confira a polaridade de montagem.",
    "Vblock": "Escolha uma peça com tensão de bloqueio maior ou use um grampeador (snubber, "
    "diodo de roda livre, TVS) para limitar os picos.",
    "Vgate": "A porta suporta pouca tensão: limite-a com um divisor ou um zener entre porta e "
    "fonte/emissor.",
    "Vbe": "A junção base-emissor reversa suporta poucos volts: proteja a base com um diodo em "
    "antiparalelo ou reduza a tensão aplicada.",
    "Icont": "Reduza a corrente (resistor em série maior ou carga menor) ou escolha uma peça "
    "com corrente nominal maior.",
    "Ipeak": "Limite o pico de corrente (resistor de partida, NTC, indutor em série) ou escolha "
    "uma peça com corrente de surto maior.",
    "P": "Reduza a potência dissipada (menos tensão ou corrente) ou escolha uma peça de "
    "potência maior.",
    "T": "A junção passa da temperatura máxima: use dissipador, reduza a potência ou escolha "
    "uma peça com menor resistência térmica.",
    "Res": "Use um resistor de potência maior (folga de 2×) ou aumente a resistência para "
    "reduzir a corrente.",
    "Cap": "Use um capacitor com tensão nominal maior (folga de 20 a 50 %).",
    "Vid": "A diferença entre as entradas passa do máximo: limite-a com resistores em série e "
    "diodos de proteção.",
    "Ind": "Use um indutor com corrente nominal (e de saturação) maior ou reduza a corrente; "
    "acima de I_sat a indutância cai e o pico de corrente cresce.",
    "Sw": "Use uma chave com corrente nominal maior ou acione a carga por relé ou transistor.",
}

_CAUSE: dict[Quantity, str] = {
    "V": "tensão",
    "I": "corrente",
    "P": "potência",
    "T": "temperatura de junção",
}


@dataclass(frozen=True)
class _Spec:
    key: str
    quantity: Quantity
    measure: Measure
    pos: str | None = None  # pin at the positive side of the blocking voltage
    neg: str | None = None
    current_pin: str | None = None
    sign: float = 1.0
    advice: str = ""


# current sensed in series with this pin (into the pin) for each schematic kind
SENSE_PIN: dict[str, str] = {
    "diode": "a",
    "zener": "k",
    "npn": "c",
    "pnp": "e",
    "nmos": "d",
    "pmos": "s",  # current into the source is positive when a P channel conducts
    "njf": "d",
    "pjf": "s",
    "inductor": "1",
    "igbt": "c",
    "scr": "a",
    "triac": "mt2",
    "switch_manual": "1",
    "tact_switch": "1",
    "push_nc": "1",
    "relay": "COM",
}


def _diode_specs() -> list[_Spec]:
    return [
        _Spec("VRRM", "V", "peak", "k", "a", advice="Vrev"),
        _Spec("IF(AV)", "I", "mean", current_pin="a", advice="Icont"),
        _Spec("IFSM", "I", "peak", current_pin="a", advice="Ipeak"),
        _Spec("Ptot", "P", "mean", "a", "k", current_pin="a", advice="P"),
    ]


def _bjt_specs(npn: bool) -> list[_Spec]:
    c, e = ("c", "e") if npn else ("e", "c")
    # pnp: the sensed pin is the emitter (current into it is +IC); VCE blocking is v(e)-v(c)
    pin, sign = ("c", 1.0) if npn else ("e", 1.0)
    return [
        _Spec("VCEO", "V", "peak", c, e, advice="Vblock"),
        _Spec("VEBO", "V", "peak", "e" if npn else "b", "b" if npn else "e", advice="Vbe"),
        _Spec("IC", "I", "mean", current_pin=pin, sign=sign, advice="Icont"),
        _Spec("ICM", "I", "peak", current_pin=pin, sign=sign, advice="Ipeak"),
        _Spec("Ptot", "P", "mean", c, e, current_pin=pin, sign=sign, advice="P"),
    ]


_SPECS: dict[str, Callable[[], list[_Spec]]] = {
    "diode": _diode_specs,
    "zener": lambda: [
        _Spec("Ptot", "P", "mean", "k", "a", current_pin="k", advice="P"),
        _Spec("IZM", "I", "mean", current_pin="k", advice="Icont"),
    ],
    "led": lambda: [_Spec("VR", "V", "peak", "k", "a", advice="Vrev")],
    "npn": lambda: _bjt_specs(True),
    "pnp": lambda: _bjt_specs(False),
    "nmos": lambda: [
        _Spec("VDS", "V", "peak", "d", "s", advice="Vblock"),
        _Spec("VGS", "V", "peak_abs", "g", "s", advice="Vgate"),
        _Spec("ID", "I", "mean", current_pin="d", advice="Icont"),
        _Spec("IDM", "I", "peak", current_pin="d", advice="Ipeak"),
        _Spec("Ptot", "P", "mean", "d", "s", current_pin="d", advice="P"),
    ],
    "pmos": lambda: [  # catalogue values in magnitude: blocking is v(s) − v(d)
        _Spec("VDS", "V", "peak", "s", "d", advice="Vblock"),
        _Spec("VGS", "V", "peak_abs", "g", "s", advice="Vgate"),
        _Spec("ID", "I", "mean", current_pin="s", advice="Icont"),
        _Spec("IDM", "I", "peak", current_pin="s", advice="Ipeak"),
        _Spec("Ptot", "P", "mean", "s", "d", current_pin="s", advice="P"),
    ],
    "njf": lambda: [
        _Spec("VDG", "V", "peak", "d", "g", advice="Vblock"),
        _Spec("Ptot", "P", "mean", "d", "s", current_pin="d", advice="P"),
    ],
    "pjf": lambda: [
        _Spec("VDG", "V", "peak", "g", "d", advice="Vblock"),
        _Spec("Ptot", "P", "mean", "s", "d", current_pin="s", advice="P"),
    ],
    "capacitor": lambda: [_Spec("V_rated", "V", "peak_abs", "1", "2", advice="Cap")],
    "inductor": lambda: [
        _Spec("I_rms", "I", "rms", current_pin="1", advice="Ind"),
        _Spec("I_sat", "I", "peak", current_pin="1", advice="Ind"),
    ],
    "igbt": lambda: [
        _Spec("VCES", "V", "peak", "c", "e", advice="Vblock"),
        _Spec("VGES", "V", "peak_abs", "g", "e", advice="Vgate"),
        _Spec("IC", "I", "mean", current_pin="c", advice="Icont"),
        _Spec("ICM", "I", "peak", current_pin="c", advice="Ipeak"),
        _Spec("Ptot", "P", "mean", "c", "e", current_pin="c", advice="P"),
    ],
    "scr": lambda: [
        _Spec("VDRM", "V", "peak", "a", "k", advice="Vblock"),
        _Spec("VRRM", "V", "peak", "k", "a", advice="Vrev"),
        _Spec("IT(RMS)", "I", "rms", current_pin="a", advice="Icont"),
        _Spec("ITSM", "I", "peak", current_pin="a", advice="Ipeak"),
    ],
    "triac": lambda: [
        _Spec("VDRM", "V", "peak_abs", "mt2", "mt1", advice="Vblock"),
        _Spec("IT(RMS)", "I", "rms", current_pin="mt2", advice="Icont"),
        _Spec("ITSM", "I", "peak", current_pin="mt2", advice="Ipeak"),
    ],
    "opamp": lambda: [_Spec("VID_max", "V", "peak_abs", "inp", "inn", advice="Vid")],
    "potentiometer": lambda: [
        _Spec("V_max", "V", "peak_abs", "a", "b", advice="Res"),
    ],
    "switch_manual": lambda: [_Spec("I_rated", "I", "rms", current_pin="1", advice="Sw")],
    "tact_switch": lambda: [_Spec("I_rated", "I", "rms", current_pin="1", advice="Sw")],
    "push_nc": lambda: [_Spec("I_rated", "I", "rms", current_pin="1", advice="Sw")],
    "relay": lambda: [_Spec("I_contact", "I", "rms", current_pin="COM", advice="Sw")],
}

_UNIT: dict[Quantity, str] = {"V": "V", "I": "A", "P": "W", "T": "°C"}


def _node(nodes: Mapping[str, str], pin: str | None) -> str | None:
    if pin is None:
        return None
    n = nodes.get(pin)
    return None if n in (None, "0") else n


# catalogue records of passives describe a series (values from min to max); a rating given as
# a range belongs to different models of the series and is not checked
_SERIES_KINDS = {"resistor", "capacitor", "inductor"}


def _is_range(rec: ComponentRecord, key: str) -> bool:
    p = rec.parameters.get(key)
    return p is not None and p.min is not None and p.max is not None and p.min != p.max


def limits_for(
    comp: Component,
    nodes: Mapping[str, str],
    rec: ComponentRecord | None,
    sense: Mapping[str, str],
    t_amb: float | None,
) -> list[Limit]:
    """Ratings of one part, ready to be checked against the simulated vectors.

    ``nodes``: pin → net; ``sense``: pin → current vector into that pin."""
    ref = comp.ref
    out: list[Limit] = []
    if rec is None:
        return _generic_limits(comp, nodes)
    for sp in _SPECS.get(comp.kind, lambda: [])():
        if comp.kind in _SERIES_KINDS and _is_range(rec, sp.key):
            continue  # a range over the models of a series: not this part's rating
        r = _rating(rec, sp.key, _UNIT[sp.quantity])
        if r is None:
            continue  # the datasheet does not give this rating
        value, src, reviewed = r
        cur = sense.get(sp.current_pin) if sp.current_pin else None
        if sp.current_pin and cur is None:
            continue
        out.append(
            Limit(
                ref,
                sp.quantity,
                sp.key,
                value,
                _UNIT[sp.quantity],
                sp.measure,
                _node(nodes, sp.pos),
                _node(nodes, sp.neg),
                cur,
                sp.sign,
                source=src,
                advice=_ADVICE[sp.advice],
                reviewed=reviewed,
            )
        )
        # junction temperature from the same power, free air
        if sp.key == "Ptot":
            tj = _rating(rec, "Tj_max", "°C")
            rth = _rating(rec, "Rth_ja", "K/W")
            if tj and rth and t_amb is not None:
                out.append(
                    Limit(
                        ref,
                        "T",
                        "Tj max",
                        tj[0],
                        "°C",
                        "mean",
                        _node(nodes, sp.pos),
                        _node(nodes, sp.neg),
                        cur,
                        sp.sign,
                        rth=rth[0],
                        t_amb=t_amb,
                        source=f"{tj[1]}; {rth[1]}",
                        advice=_ADVICE["T"],
                        reviewed=tj[2] and rth[2],
                    )
                )
    if comp.kind == "resistor":  # a series: the value is the one in the schematic
        pr = None if _is_range(rec, "P_rated") else _rating(rec, "P_rated", "W")
        r_ohm = try_parse(comp.params.get("value", "") or "")
        if pr and r_ohm and r_ohm > 0:
            out.append(
                Limit(
                    ref,
                    "P",
                    "P_rated",
                    pr[0],
                    "W",
                    "mean",
                    _node(nodes, "1"),
                    _node(nodes, "2"),
                    resistance=r_ohm,
                    source=pr[1],
                    advice=_ADVICE["Res"],
                    reviewed=pr[2],
                )
            )
        vm = None if _is_range(rec, "V_max") else _rating(rec, "V_max", "V")
        if vm:
            out.append(
                Limit(
                    ref,
                    "V",
                    "V_max",
                    vm[0],
                    "V",
                    "peak_abs",
                    _node(nodes, "1"),
                    _node(nodes, "2"),
                    source=vm[1],
                    advice=_ADVICE["Res"],
                    reviewed=vm[2],
                )
            )
    if comp.kind == "potentiometer":
        pr = _rating(rec, "P_rated", "W")
        rv = _rating(rec, "R", "ohm")
        if pr and rv and rv[0] > 0:
            out.append(
                Limit(
                    ref,
                    "P",
                    "P_rated",
                    pr[0],
                    "W",
                    "mean",
                    _node(nodes, "a"),
                    _node(nodes, "b"),
                    resistance=rv[0],
                    source=pr[1],
                    advice=_ADVICE["Res"],
                    reviewed=pr[2],
                )
            )
    return out


def _generic_limits(comp: Component, nodes: Mapping[str, str]) -> list[Limit]:
    """A generic resistor or capacitor with the rating the user typed."""
    p = comp.params
    if comp.kind == "resistor":
        pr, r = try_parse(p.get("p_rated", "") or ""), try_parse(p.get("value", "") or "")
        if pr and pr > 0 and r and r > 0:
            return [
                Limit(
                    comp.ref,
                    "P",
                    "P nominal",
                    pr,
                    "W",
                    "mean",
                    _node(nodes, "1"),
                    _node(nodes, "2"),
                    resistance=r,
                    source=f"{comp.ref}: potência nominal informada no esquemático",
                    advice=_ADVICE["Res"],
                )
            ]
    if comp.kind == "capacitor":
        vr = try_parse(p.get("v_rated", "") or "")
        if vr and vr > 0:
            return [
                Limit(
                    comp.ref,
                    "V",
                    "V nominal",
                    vr,
                    "V",
                    "peak_abs",
                    _node(nodes, "1"),
                    _node(nodes, "2"),
                    source=f"{comp.ref}: tensão nominal informada no esquemático",
                    advice=_ADVICE["Cap"],
                )
            ]
    return []


def sense_pin(comp: Component, rec: ComponentRecord | None) -> str | None:
    """Pin that gets a 0 V current sense source (only parts that are checked)."""
    if rec is None:
        return None
    return SENSE_PIN.get(comp.kind)


# ------------------------------------------------------------------------- the checking


def _second_half(
    t: NDArray[Any] | None, y: NDArray[Any]
) -> tuple[NDArray[Any] | None, NDArray[Any]]:
    if t is None or y.size < 4:
        return t, y
    k = y.size // 2
    return t[k:], y[k:]


def _mean(t: NDArray[Any] | None, y: NDArray[Any]) -> float:
    if t is None or y.size < 2 or t[-1] <= t[0]:
        return float(np.mean(y))
    return float(np.trapezoid(y, t) / (t[-1] - t[0]))


def _rms(t: NDArray[Any] | None, y: NDArray[Any]) -> float:
    return math.sqrt(max(_mean(t, y * y), 0.0))


def evaluate(
    limits: list[Limit], vectors: Mapping[str, NDArray[Any]], time: NDArray[Any] | None
) -> list[Damage]:
    """Ratings exceeded in the simulated vectors (missing vectors: limit skipped)."""
    out: list[Damage] = []

    def volt(node: str | None) -> NDArray[Any] | float | None:
        if node is None:
            return 0.0
        return vectors.get(f"v({node.lower()})")

    for lim in limits:
        vp, vn = volt(lim.v_pos), volt(lim.v_neg)
        v = None if vp is None or vn is None else np.real(np.asarray(vp) - np.asarray(vn))
        i = None
        if lim.current is not None:
            raw = vectors.get(lim.current.lower())
            if raw is None:
                continue
            i = lim.current_sign * np.real(np.asarray(raw))
        if lim.quantity == "V":
            if v is None or np.ndim(v) == 0:
                continue
            value = float(np.max(np.abs(v)) if lim.measure == "peak_abs" else np.max(v))
        elif lim.quantity == "I":
            if i is None:
                continue
            if lim.measure == "peak":
                value = float(np.max(np.abs(i)))
            else:
                t2, i2 = _second_half(time, i)
                value = abs(_mean(t2, i2)) if lim.measure == "mean" else _rms(t2, i2)
        else:
            if v is None:
                continue
            if lim.resistance is not None:
                p = np.broadcast_to(v, np.shape(v)) ** 2 / lim.resistance
            elif i is not None:
                p = np.abs(v * i)
            else:
                continue
            t2, p2 = _second_half(time, np.asarray(p, dtype=float))
            power = _mean(t2, p2)
            value = power if lim.quantity == "P" else (lim.t_amb or 0.0) + power * (lim.rth or 0.0)
        if value > lim.limit:
            out.append(_damage(lim, value))
    return out


def _damage(lim: Limit, value: float) -> Damage:
    what = {
        "peak": "pico",
        "peak_abs": "pico",
        "mean": "valor médio",
        "rms": "valor eficaz",
    }[lim.measure]
    if lim.quantity == "T":
        cause = (
            f"{lim.ref}: a junção chegaria a {_fmt(value, '°C')} (Ta + P·Rθja, sem dissipador), "
            f"acima de Tj máx = {_fmt(lim.limit, '°C')}."
        )
    else:
        cause = (
            f"{lim.ref}: {_CAUSE[lim.quantity]} ({what}) de {_fmt(value, lim.unit)}, acima de "
            f"{lim.name} = {_fmt(lim.limit, lim.unit)}."
        )
    return Damage(
        lim.ref,
        lim.quantity,
        lim.name,
        value,
        lim.limit,
        lim.unit,
        cause,
        lim.advice,
        lim.source,
        lim.reviewed,
    )
