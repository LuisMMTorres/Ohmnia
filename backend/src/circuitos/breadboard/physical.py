"""The circuit you assemble, recovered from a design module's verification netlist.

Design netlists are simulation models: ammeters (0 V sources), op-amp macromodels, behavioural
diodes. This turns one into the physical circuit for the breadboard:

* a 0 V source with no AC part is an ammeter: its two nodes are one;
* an op-amp macromodel ``U1`` (``RU1in`` between the inputs, ``EU1o`` driving the output, internal
  nodes ``u1...``) becomes one op-amp with its three pins; its supply pins take the module's
  symmetric supply (spec ``VCC``, "±");
* subcircuits are recognised by their pin names (``a k`` diode, ``a k g`` SCR, ``c b e`` BJT,
  ``d s g`` MOSFET, ``c g e`` IGBT, ``mt2 mt1 g`` TRIAC);
* a source with only an AC magnitude (small-signal input) becomes a function generator.

Anything else (controlled sources, behavioural sources, switches) has no physical counterpart in
this model: the module is reported as not assemblable rather than guessed. Parts that match a
bill-of-materials designator take the chosen catalogue part (and so its datasheet pinout).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from circuitos.components.models import ComponentRecord
from circuitos.schematic.importer import import_netlist
from circuitos.schematic.library import pin_defs, pin_positions, symbol
from circuitos.schematic.model import Component, NetLabel, Schematic
from circuitos.schematic.netlist import connectivity
from circuitos.schematic.values import try_parse

_SUBCKT_KIND = {
    ("a", "k"): "diode",
    ("a", "g", "k"): "scr",
    ("b", "c", "e"): "npn",
    ("d", "g", "s"): "nmos",
    ("c", "e", "g"): "igbt",
    ("g", "mt1", "mt2"): "triac",
}
_CATEGORY_OF = {
    "diode": ("diode.",),
    "zener": ("diode.zener",),
    "npn": ("bjt.npn",),
    "pnp": ("bjt.pnp",),
    "nmos": ("mosfet.n",),
    "njf": ("jfet.n",),
    "opamp": ("opamp",),
    "scr": ("thyristor.scr",),
    "triac": ("thyristor.triac",),
    "igbt": ("igbt.n",),
}
_PHYSICAL = {
    "resistor", "capacitor", "inductor", "diode", "zener", "npn", "pnp", "nmos", "pmos", "njf",
    "pjf", "vdc", "vsin", "vpulse", "vpwl", "idc", "isin", "ipulse", "ipwl", "transformer",
}  # fmt: skip


@dataclass
class Physical:
    schematic: Schematic | None
    notes: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


@dataclass
class _Part:
    kind: str
    ref: str
    nodes: dict[str, str]  # symbol pin -> node
    params: dict[str, str]
    part_id: str | None = None


class _UF:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if ra == "0":  # ground keeps its name
            ra, rb = rb, ra
        self.p[ra] = rb


def _build(title: str, parts: list[_Part]) -> Schematic:
    sch = Schematic(title=title)
    for i, part in enumerate(parts, start=1):
        comp = Component(
            id=f"c{i}",
            kind=part.kind,
            ref=part.ref,
            x=(i % 6) * 16,
            y=(i // 6) * 16,
            params=part.params,
            part_id=part.part_id,
        )
        pos = pin_positions(comp)
        sch.components.append(comp)
        for p in pin_defs(comp):
            x, y = pos[p.name]
            sch.labels.append(NetLabel(id=f"l{len(sch.labels)}", name=part.nodes[p.name], x=x, y=y))
    return sch


def _safe_ref(ref: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", ref) or "X"
    out, n = base, 1
    while out.lower() in taken:
        n += 1
        out = f"{base}_{n}"
    taken.add(out.lower())
    return out


def physical_circuit(
    netlist: str,
    title: str,
    record_for: Callable[[str], ComponentRecord | None],
    supply: float | None = None,
) -> Physical:
    """``record_for(designator)`` gives the catalogue part chosen for a BOM designator."""
    imp = import_netlist(netlist).schematic
    conn = connectivity(imp)
    nodes: Mapping[str, dict[str, str]] = conn.pin_nodes
    comps = [c for c in imp.components if c.kind != "ground"]
    out: list[_Part] = []
    notes: list[str] = []
    unsupported: list[str] = []
    uf = _UF()

    # op-amp macromodels
    consumed: set[str] = set()
    # anchor: the output stage E<U>o; inputs from the bias sources, R<U>in or the input stage
    macros = {
        m.group(1).lower(): c
        for c in comps
        if c.kind == "vcvs" and (m := re.fullmatch(r"E(U\d+)o", c.ref, re.I))
    }

    def owner(name: str) -> str | None:
        """Macromodel an element belongs to: the longest designator after its letter."""
        rest = name[1:].lower()
        return max((u for u in macros if rest.startswith(u)), key=len, default=None)

    for u, e_out in macros.items():
        mine = {x.ref.lower(): x for x in comps if owner(x.ref) == u}

        def node(name: str, pin: str, u: str = u, mine: dict[str, Component] = mine) -> str | None:
            x = mine.get(name.format(u=u))
            return nodes[x.ref].get(pin) if x is not None else None

        inp = node("i{u}bp", "p") or node("r{u}in", "1") or node("e{u}ca", "cp")
        inn = node("i{u}bn", "p") or node("r{u}in", "2") or node("e{u}cb", "cp")
        if inp is None or inn is None:
            continue
        consumed.update(x.ref for x in mine.values())
        pins = {"inp": inp, "inn": inn, "out": nodes[e_out.ref]["op"]}
        params = {}
        if supply:
            params = {"vcc": f"{supply:g}", "vee": f"{-supply:g}"}
        else:
            notes.append(f"{u}: tensões de alimentação do amp-op não informadas; confira V+ e V−.")
        out.append(_Part("opamp", u.upper(), pins, params))

    for c in comps:
        if c.ref in consumed:
            continue
        pn = nodes.get(c.ref, {})
        if c.kind == "vdc" and (try_parse(c.params.get("dc", "0")) or 0) == 0:
            ac = try_parse(c.params.get("ac", "0")) or 0
            if ac == 0:  # ammeter
                uf.union(pn["p"], pn["n"])
                continue
            out.append(_Part("vsin", c.ref, dict(pn), {"amplitude": f"{ac:g}", "freq": "1k"}))
            notes.append(
                f"{c.ref}: fonte de pequeno sinal do projeto, montada como gerador de funções "
                "(senoide de teste de 1 kHz: ajuste amplitude e frequência na bancada)."
            )
            continue
        if c.kind == "subckt":
            names = tuple(sorted(c.params.get("pins", "").split()))
            kind = _SUBCKT_KIND.get(names)
            model = c.params.get("model", "")
            if kind == "diode" and re.search(r"^Z|ZEN", model, re.I):
                kind = "zener"
            if kind is None:
                unsupported.append(f"{c.ref} (subcircuito {model or '?'})")
                continue
            ref = c.ref[1:] if c.ref[:1].upper() == "X" and len(c.ref) > 1 else c.ref
            out.append(_Part(kind, ref, dict(pn), {}))
            continue
        if c.kind not in _PHYSICAL:
            unsupported.append(f"{c.ref} ({symbol(c.kind).label})")
            continue
        params = {k: v for k, v in c.params.items() if k not in ("ic", "tol")}
        out.append(_Part(c.kind, c.ref, dict(pn), params))

    if unsupported:
        return Physical(None, notes, unsupported)
    taken: set[str] = set()
    for part in out:
        part.nodes = {pin: uf.find(n) for pin, n in part.nodes.items()}
        part.ref = _safe_ref(part.ref, taken)
        rec = record_for(part.ref)
        if rec is not None and rec.category.startswith(_CATEGORY_OF.get(part.kind, ("-",))):
            part.part_id = str(rec.id)
    return Physical(_build(title, out), notes)
