"""What the schematic says each leg must touch: the reference for the breadboard check.

Legs are keyed ``"Q1:3"`` (designator and package pin). A leg's net is the schematic node of the
symbol pin it carries. Supply pins of integrated circuits (V+, V-) are not drawn in the schematic
symbol: their voltage is a parameter (``vcc``, ``vee``). They join implicit supply nets, fed by
an implicit bench supply ``ALIM`` (``+``, ``-``, ``0``) that the assembly must include.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from circuitos.breadboard.pinout import Resolved, resolve
from circuitos.components.models import ComponentRecord
from circuitos.schematic.model import Schematic
from circuitos.schematic.netlist import connectivity

ALIM = "ALIM"


def key(ref: str, pin: str) -> str:
    return f"{ref}:{pin}"


def _volts(v: float) -> str:
    return f"{v:+g} V".replace("-", "−").replace(".", ",")


@dataclass
class Reference:
    parts: dict[str, Resolved]  # designator -> resolved package/pinout (with ALIM if needed)
    nets: dict[str, str]  # leg key -> net name
    net_labels: dict[str, str] = field(default_factory=dict)  # net -> readable name
    warnings: list[str] = field(default_factory=list)

    def leg_label(self, leg: str) -> str:
        ref, pin = leg.split(":", 1)
        r = self.parts.get(ref)
        label = r.labels.get(pin) if r else None
        if not pin.isdigit():  # terminals and polarized legs: "C1 (+)", "V1 (P)"
            return f"{ref} ({label or pin})"
        return f"{ref} pino {pin}" + (f" ({label})" if label and label != pin else "")

    def members(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for leg, net in self.nets.items():
            out.setdefault(net, []).append(leg)
        return out


def build(sch: Schematic, records: Mapping[str, ComponentRecord | None]) -> Reference:
    conn = connectivity(sch)
    parts: dict[str, Resolved] = {}
    nets: dict[str, str] = {}
    labels: dict[str, str] = {"0": "terra (0 V)"}
    warnings: list[str] = []
    vcc: set[float] = set()
    vee: set[float] = set()
    for comp in sch.components:
        if comp.kind == "ground":
            continue
        r = resolve(comp, records.get(comp.ref))
        parts[comp.ref] = r
        if r.package is None:
            continue
        for pin, role in r.pinmap.items():
            if role in ("vcc", "vee"):
                v = r.supplies.get(role, 0.0)
                if v == 0:
                    nets[key(comp.ref, pin)] = "0"
                    continue
                (vcc if role == "vcc" else vee).add(v)
                net = f"{role.upper()} {_volts(v)}"
                nets[key(comp.ref, pin)] = net
                labels[net] = f"alimentação {_volts(v)}"
                continue
            node = conn.pin_nodes.get(comp.ref, {}).get(role)
            if node is not None:
                nets[key(comp.ref, pin)] = node
    if vcc or vee:
        alim = Resolved(ALIM, "alim", "alim", "implicito", title="Fonte simétrica")
        alim.pinmap = {"0": "gnd"}
        alim.labels = {"0": "0 V"}
        nets[key(ALIM, "0")] = "0"
        for role, volts, term in (("vcc", vcc, "+"), ("vee", vee, "-")):
            if not volts:
                continue
            v = sorted(volts)[-1 if role == "vcc" else 0]
            alim.pinmap[term] = role
            alim.labels[term] = _volts(v)
            nets[key(ALIM, term)] = f"{role.upper()} {_volts(v)}"
            if len(volts) > 1:
                warnings.append(
                    "Integrados com tensões de alimentação diferentes "
                    f"({', '.join(_volts(x) for x in sorted(volts))}): a fonte implícita usa "
                    f"{_volts(v)}; acrescente outra fonte no esquemático se precisar das duas."
                )
        alim.notes.append(
            "Fonte de bancada da alimentação dos integrados (no esquemático ela está nos "
            "parâmetros vcc e vee do símbolo, não desenhada)."
        )
        parts[ALIM] = alim
    for node in conn.nets:
        labels.setdefault(node, node)
    return Reference(parts, nets, labels, warnings + conn.warnings)
