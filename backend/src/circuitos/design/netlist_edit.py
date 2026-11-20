"""Elements of a design netlist, edits of their values and probes the user adds on them.

The design page shows the circuit the simulator runs; from it the user can change the value of
a passive part or of a source (the simulation then runs that edited circuit) and ask for the
voltage at a node, the voltage between two nodes, the current through a terminal of an element
or the power of an element. A current is sensed with a 0 V source in series with the terminal,
which leaves the circuit unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from .base import Circuit, PowerPort

# number of nodes of each element letter (X: every token up to the subcircuit name)
_NODES = {
    "R": 2,
    "C": 2,
    "L": 2,
    "V": 2,
    "I": 2,
    "D": 2,
    "B": 2,
    "F": 2,
    "H": 2,
    "W": 2,
    "E": 4,
    "G": 4,
    "S": 4,
    "Q": 3,
    "J": 3,
    "M": 4,
    "T": 4,
    "O": 4,
    "K": 0,
}
_PIN_NAMES = {
    "Q": ["coletor", "base", "emissor"],
    "J": ["dreno", "porta", "fonte"],
    "M": ["dreno", "porta", "fonte", "corpo"],
}
EditKind = Literal["value", "source", "none"]


class Element(BaseModel):
    name: str
    letter: str
    nodes: list[str]
    pins: list[str]  # name of each terminal, same order as nodes
    value: str  # editable text: the value of R/C/L, the whole description of a source
    edit: EditKind
    sense: bool = False  # 0 V current-sense source added by the module (not a real part)


@dataclass
class _Line:
    index: int  # line number in the netlist (continuations joined)
    tokens: list[str]


def _logical_lines(netlist: str) -> list[str]:
    out: list[str] = []
    for raw in netlist.splitlines():
        if raw.startswith("+") and out:
            out[-1] += " " + raw[1:]
        else:
            out.append(raw)
    return out


def _top_level(lines: Sequence[str]) -> list[_Line]:
    """Element lines outside ``.subckt`` blocks."""
    out: list[_Line] = []
    depth = 0
    for k, line in enumerate(lines):
        s = line.strip()
        low = s.lower()
        if low.startswith(".subckt"):
            depth += 1
            continue
        if low.startswith(".ends"):
            depth = max(depth - 1, 0)
            continue
        if depth or not s or s[0] in "*.;":
            continue
        out.append(_Line(k, s.split()))
    return out


def _node_count(tokens: list[str]) -> int:
    letter = tokens[0][0].upper()
    if letter == "X":
        n = 0
        for tok in tokens[1:]:
            if "=" in tok or tok.lower() == "params:":
                break
            n += 1
        return max(n - 1, 0)  # the last one is the subcircuit name
    return min(_NODES.get(letter, 2), len(tokens) - 1)


def _element(line: _Line) -> Element:
    tokens = line.tokens
    name = tokens[0]
    letter = name[0].upper()
    n = _node_count(tokens)
    nodes = tokens[1 : 1 + n]
    rest = tokens[1 + n :]
    if letter in "RCL" and rest:
        value, edit = rest[0], "value"
    elif letter in "VI":
        value, edit = " ".join(rest), "source"
    else:
        value, edit = " ".join(rest), "none"
    pins = _PIN_NAMES.get(letter, [f"terminal {i + 1}" for i in range(n)])[:n]
    sense = letter == "V" and value.strip() in ("0", "DC 0", "dc 0")
    return Element(
        name=name,
        letter=letter,
        nodes=nodes,
        pins=pins,
        value=value,
        edit=edit if not sense else "none",
        sense=sense,
    )


def elements(netlist: str) -> list[Element]:
    return [_element(line) for line in _top_level(_logical_lines(netlist))]


def nodes(netlist: str) -> list[str]:
    seen: dict[str, None] = {}
    for el in elements(netlist):
        for n in el.nodes:
            seen.setdefault(n, None)
    return list(seen)


_SAFE_VALUE = re.compile(r"^[^\n\r]*$")


def apply_overrides(netlist: str, overrides: Mapping[str, str]) -> str:
    """Netlist with new values: R/C/L keep their other options (``IC=``), a source is replaced."""
    if not overrides:
        return netlist
    lines = _logical_lines(netlist)
    wanted = {k.lower(): v for k, v in overrides.items()}
    found: set[str] = set()
    for line in _top_level(lines):
        el = _element(line)
        new = wanted.get(el.name.lower())
        if new is None:
            continue
        new = new.strip()
        if not new or not _SAFE_VALUE.match(new) or new.startswith("."):
            raise ValueError(f"{el.name}: valor inválido")
        if el.edit == "none":
            raise ValueError(f"{el.name}: este elemento não tem valor editável")
        head = line.tokens[: 1 + len(el.nodes)]
        tail = line.tokens[2 + len(el.nodes) :] if el.edit == "value" else []
        lines[line.index] = " ".join([*head, new, *tail])
        found.add(el.name.lower())
    missing = set(wanted) - found
    if missing:
        raise ValueError(f"Elemento não encontrado no circuito: {', '.join(sorted(missing))}")
    return "\n".join(lines)


class UserProbe(BaseModel):
    """A waveform the user asks for by clicking the schematic."""

    kind: Literal["v", "vdiff", "i", "p"]
    a: str  # node (v, vdiff) or element (i, p)
    b: str | None = None  # second node (vdiff)
    pin: int = 0  # terminal of the element whose current is sensed (i)


def _v(node: str) -> str:
    return "" if node in ("0", "gnd", "GND") else f"v({node.lower()})"


def _diff(a: str, b: str) -> str:
    va, vb = _v(a), _v(b)
    if not va and not vb:
        raise ValueError("Os dois nós são a referência (terra)")
    if not vb:
        return va
    return f"{va}-{vb}" if va else f"-{vb}"


def add_probes(circuit: Circuit, probes: Sequence[UserProbe]) -> tuple[Circuit, list[str]]:
    """Circuit with the user's probes; returns the labels of the power ports added."""
    if not probes:
        return circuit, []
    lines = _logical_lines(circuit.netlist)
    by_name = {el.name.lower(): (ln, el) for ln in _top_level(lines) for el in [_element(ln)]}
    known_nodes = {n.lower() for _, el in by_name.values() for n in el.nodes}
    probe_map = dict(circuit.probes)
    powers = dict(circuit.powers)
    power_labels: list[str] = []
    extra: list[str] = []

    def element(name: str) -> tuple[_Line, Element]:
        hit = by_name.get(name.lower())
        if hit is None:
            raise ValueError(f"Elemento não encontrado no circuito: {name}")
        return hit

    def node(name: str) -> str:
        if name.lower() not in known_nodes and name not in ("0",):
            raise ValueError(f"Nó não encontrado no circuito: {name}")
        return name

    def sense(name: str, pin: int) -> str:
        line, el = element(name)
        if el.letter == "V":
            return f"i({el.name.lower()})" if pin == 0 else f"-i({el.name.lower()})"
        if not 0 <= pin < len(el.nodes):
            raise ValueError(f"{el.name}: terminal {pin + 1} inexistente")
        k = len(extra) + 1
        src = f"VPRB{k}"
        original = el.nodes[pin]
        inner = f"{original}_prb{k}"
        line.tokens[1 + pin] = inner
        el.nodes[pin] = inner
        lines[line.index] = " ".join(line.tokens)
        extra.append(f"{src} {original} {inner} 0")
        return f"i({src.lower()})"

    for p in probes:
        if p.kind == "v":
            expr = _v(node(p.a))
            if not expr:
                raise ValueError("O nó escolhido é a referência (terra)")
            probe_map[f"Tensão no nó {p.a}"] = expr
        elif p.kind == "vdiff":
            if p.b is None:
                raise ValueError("Tensão diferencial precisa de dois nós")
            probe_map[f"Tensão {p.a} − {p.b}"] = _diff(node(p.a), node(p.b))
        elif p.kind == "i":
            _, el = element(p.a)
            pin_name = el.pins[p.pin] if 0 <= p.pin < len(el.pins) else str(p.pin + 1)
            label = f"Corrente em {el.name}" + (f" ({pin_name})" if len(el.nodes) > 2 else "")
            probe_map[label] = sense(p.a, p.pin)
        else:
            _, el = element(p.a)
            if len(el.nodes) < 2:
                raise ValueError(f"{el.name}: potência só para elementos de dois terminais")
            n1, n2 = el.nodes[0], el.nodes[1]
            label = f"{el.name}"
            powers[label] = PowerPort(voltage=_diff(n1, n2), current=sense(p.a, 0))
            power_labels.append(label)
    netlist = "\n".join([*lines, *extra])
    return (
        circuit.model_copy(update={"netlist": netlist, "probes": probe_map, "powers": powers}),
        power_labels,
    )
