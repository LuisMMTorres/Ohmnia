"""KiCad netlist (``.net``, S-expression "E" format) from a SPICE netlist.

The SPICE netlist is the one place where the connectivity of a design (or of a circuit drawn in
the free simulator) is complete, so the KiCad netlist is derived from it. Pcbnew imports the
result (File → Import → Netlist) to start the board.

What is exported:

* physical parts: R, C, L, D, Q, M, J and subcircuits (X);
* sources (V, I), behavioural and controlled sources (B, E, F, G, H) and ideal switches (S, W)
  are simulation devices, not parts: they are left out and listed in the header comment;
* for a design module, only the parts that are in its bill of materials (``keep``): the design
  netlists contain model elements (winding resistance, load, snubber of an ideal switch) that are
  not components to place.

Footprints are *suggestions* from the package in the catalogue (DO-41, TO-220…) or a generic
through-hole footprint by type, marked in the ``Footprint_origem`` field. Transistor pin order
varies between parts: the ``Pinagem`` field asks for confirmation against the datasheet.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

# SPICE node order → KiCad symbol pin numbers (Device library)
_SYMBOLS: dict[str, tuple[str, list[str], str]] = {
    # type: (symbol, pin number for each SPICE node in order, description)
    "R": ("R", ["1", "2"], "Resistor"),
    "C": ("C", ["1", "2"], "Capacitor"),
    "L": ("L", ["1", "2"], "Indutor"),
    "D": ("D", ["2", "1"], "Diodo (pino 1 = catodo, 2 = anodo)"),
    "Q": ("Q_NPN_BCE", ["2", "1", "3"], "Transistor bipolar"),
    "M": ("Q_NMOS_GDS", ["2", "1", "3"], "MOSFET"),
    "J": ("Q_NJFET_DGS", ["1", "2", "3"], "JFET"),
}

_GENERIC_FOOTPRINT = {
    "R": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
    "C": "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
    "L": "Inductor_THT:L_Axial_L9.5mm_D4.0mm_P15.24mm_Horizontal_Fastron_SMCC",
    "D": "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
    "Q": "Package_TO_SOT_THT:TO-92_Inline",
    "M": "Package_TO_SOT_THT:TO-220-3_Vertical",
    "J": "Package_TO_SOT_THT:TO-92_Inline",
}

# catalogue package (start of the text) → KiCad footprint
_PACKAGE_FOOTPRINT = [
    ("DO-41", "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"),
    ("DO-201", "Diode_THT:D_DO-201AD_P15.24mm_Horizontal"),
    ("DO-15", "Diode_THT:D_DO-15_P10.16mm_Horizontal"),
    ("DO-35", "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal"),
    ("TO-92", "Package_TO_SOT_THT:TO-92_Inline"),
    ("TO-220", "Package_TO_SOT_THT:TO-220-3_Vertical"),
    ("TO-247", "Package_TO_SOT_THT:TO-247-3_Vertical"),
    ("TO-3P", "Package_TO_SOT_THT:TO-3P-3_Vertical"),
    ("TO-126", "Package_TO_SOT_THT:TO-126-3_Vertical"),
    ("TO-3", "Package_TO_SOT_THT:TO-3"),
    ("DIP-8", "Package_DIP:DIP-8_W7.62mm"),
    ("DIP-14", "Package_DIP:DIP-14_W7.62mm"),
]

_SIM_ONLY = set("VIBEFGHSWAKT")

# subcircuits recognised by their pin names: kind, KiCad symbol, pin name → KiCad pin, description
_BY_PIN_NAMES: dict[frozenset[str], tuple[str, str, dict[str, str], str]] = {
    frozenset({"a", "k"}): ("D", "D", {"k": "1", "a": "2"}, "Diodo (pino 1 = catodo, 2 = anodo)"),
    frozenset({"c", "b", "e"}): (
        "Q",
        "Q_NPN_BCE",
        {"b": "1", "c": "2", "e": "3"},
        "Transistor bipolar",
    ),
    frozenset({"c", "g", "e"}): ("M", "Q_NIGBT_GCE", {"g": "1", "c": "2", "e": "3"}, "IGBT"),
    frozenset({"d", "s", "g"}): ("M", "Q_NMOS_GDS", {"g": "1", "d": "2", "s": "3"}, "MOSFET"),
    frozenset({"a", "k", "g"}): ("T", "Q_SCR_AKG", {"a": "1", "k": "2", "g": "3"}, "SCR"),
}


@dataclass
class Part:
    ref: str
    kind: str
    nodes: list[str]
    value: str
    symbol: str = "Subcircuito"
    pins: list[str] = field(default_factory=list)  # KiCad pin number of each node
    description: str = ""
    footprint: str = ""
    footprint_origin: str = ""
    fields: dict[str, str] = field(default_factory=dict)


def _logical(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+") and out:
            out[-1] += " " + line[1:].strip()
        else:
            out.append(line)
    return out


def _is_zero_source(tokens: list[str]) -> bool:
    rest = [t.lower() for t in tokens[3:]]
    return rest in (["0"], ["dc", "0"], ["0v"], ["dc", "0v"])


def parse(netlist: str) -> tuple[list[Part], list[str], list[tuple[str, str]]]:
    """Physical parts, simulation-only elements and the node pairs shorted by 0 V ammeters."""
    lines = _logical(netlist)
    subckt_pins: dict[str, list[str]] = {}
    for line in lines:
        m = re.match(r"^\.subckt\s+(\S+)\s+(.*)$", line, re.IGNORECASE)
        if m:
            pins = [t for t in m.group(2).split() if "=" not in t and t.lower() != "params:"]
            subckt_pins[m.group(1).lower()] = [p.lower() for p in pins]
    parts: list[Part] = []
    skipped: list[str] = []
    shorts: list[tuple[str, str]] = []
    depth = 0
    for i, line in enumerate(lines):
        low = line.lower()
        if i == 0 and not low.startswith((".", "r", "c", "l", "d", "q", "m", "j", "x")):
            continue  # title line
        if low.startswith(".subckt"):
            depth += 1
            continue
        if low.startswith(".ends"):
            depth = max(depth - 1, 0)
            continue
        if depth or line.startswith("."):
            continue
        tokens = re.split(r"\s+", line.split(";")[0].strip())
        name = tokens[0]
        kind = name[0].upper()
        if kind == "V" and len(tokens) >= 4 and _is_zero_source(tokens):
            shorts.append((tokens[1], tokens[2]))  # current sense: same physical node
            continue
        if kind in _SIM_ONLY:
            skipped.append(name)
            continue
        if kind in "RCLD" and len(tokens) >= 4:
            part = Part(name, kind, tokens[1:3], tokens[3])
        elif kind in "QJ" and len(tokens) >= 5:
            part = Part(name, kind, tokens[1:4], tokens[4])
        elif kind == "M" and len(tokens) >= 6:
            part = Part(name, kind, tokens[1:4], tokens[5])  # body node not exported
        elif kind == "X":
            positional = [t for t in tokens[1:] if "=" not in t and t.lower() != "params:"]
            part = Part(name, kind, positional[:-1], positional[-1])
            pin_names = subckt_pins.get(part.value.lower(), [])
            known = _BY_PIN_NAMES.get(frozenset(pin_names))
            if known and len(pin_names) == len(part.nodes):
                part.kind, part.symbol, mapping, part.description = known
                part.pins = [mapping[n] for n in pin_names]
                part.ref = name[1:] or name  # XD1 → D1
            else:
                part.pins = [str(k + 1) for k in range(len(part.nodes))]
                part.description = f"Subcircuito {part.value}"
            parts.append(part)
            continue
        else:
            skipped.append(name)
            continue
        part.symbol, part.pins, part.description = _SYMBOLS[kind]
        parts.append(part)
    return parts, skipped, shorts


def _norm(text: str) -> str:
    return text.upper().replace("–", "-").replace("—", "-").replace("_", "").replace(" ", "")


def _match(ref: str, keep: set[str]) -> str | None:
    """BOM designator for ``ref``: ``D3`` ∈ ``D1–D4``, ``CO`` = ``C_o``, ``Q`` = ``Q1``."""
    candidates = [ref] if any(c.isdigit() for c in ref) else [ref, f"{ref}1"]
    for cand in candidates:
        r = _norm(cand)
        for k in keep:
            for piece in _norm(k).split(","):
                m = re.fullmatch(r"([A-Z]+)(\d+)-(?:[A-Z]+)?(\d+)", piece)
                if m:
                    mm = re.fullmatch(r"([A-Z]+)(\d+)", r)
                    if (
                        mm
                        and mm.group(1) == m.group(1)
                        and int(m.group(2)) <= int(mm.group(2)) <= int(m.group(3))
                    ):
                        return cand
                elif piece == r:
                    return cand
    return None


def _sexpr(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _union(shorts: list[tuple[str, str]]) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in shorts:
        ra, rb = find(a), find(b)
        if ra != rb:
            # keep the more readable name (ground first, then the shorter one)
            keep, drop = sorted((ra, rb), key=lambda n: (n not in ("0", "gnd", "GND"), len(n), n))
            parent[drop] = keep
    return {n: find(n) for n in list(parent)}


def to_kicad(
    netlist: str,
    title: str,
    keep: set[str] | None = None,
    packages: dict[str, str] | None = None,
) -> str:
    """``keep``: designators to export (None = every physical part). ``packages``: ref → package."""
    parts, skipped, shorts = parse(netlist)
    if keep is not None:
        kept = []
        for p in parts:
            m = _match(p.ref, keep)
            if m is None:
                skipped.append(p.ref)
            else:
                p.ref = m
                kept.append(p)
        parts = kept
    packages = packages or {}
    for p in parts:
        package = next((v for k, v in packages.items() if _match(p.ref, {k})), "")
        fp = next((f for prefix, f in _PACKAGE_FOOTPRINT if package.upper().startswith(prefix)), "")
        if fp:
            p.footprint, p.footprint_origin = fp, f"encapsulamento do catálogo ({package})"
        elif p.kind in _GENERIC_FOOTPRINT:
            p.footprint = _GENERIC_FOOTPRINT[p.kind]
            p.footprint_origin = "genérico pelo tipo: escolha o definitivo no KiCad"
        if p.kind in "QMJT":
            p.fields["Pinagem"] = "confirmar a ordem dos terminais no datasheet antes do layout"
    alias = _union(shorts)
    nets: dict[str, list[tuple[str, str]]] = {}
    for p in parts:
        for node, pin in zip(p.nodes, p.pins, strict=False):
            node = alias.get(node, node)
            name = "GND" if node in ("0", "gnd", "GND") else node
            nets.setdefault(name, []).append((p.ref, pin))
    comps = []
    for p in parts:
        symbol, desc = p.symbol, p.description
        extra = "".join(
            f" (property (name {_sexpr(k)}) (value {_sexpr(v)}))" for k, v in p.fields.items()
        )
        origin = (
            f' (property (name "Footprint_origem") (value {_sexpr(p.footprint_origin)}))'
            if p.footprint_origin
            else ""
        )
        comps.append(
            f"    (comp (ref {_sexpr(p.ref)}) (value {_sexpr(p.value)})"
            f" (footprint {_sexpr(p.footprint)})"
            f' (libsource (lib "Device") (part {_sexpr(symbol)}) (description {_sexpr(desc)}))'
            f"{origin}{extra})"
        )
    net_lines = []
    for code, (name, nodes) in enumerate(sorted(nets.items(), key=lambda kv: kv[0]), start=1):
        node_s = " ".join(f"(node (ref {_sexpr(r)}) (pin {_sexpr(pin)}))" for r, pin in nodes)
        net_lines.append(f'    (net (code "{code}") (name {_sexpr("/" + name)}) {node_s})')
    note = (
        "Fora da netlist (elementos de simulação ou do modelo): " + ", ".join(sorted(skipped))
        if skipped
        else "Todos os elementos são componentes físicos."
    )
    return (
        '(export (version "E")\n'
        "  (design\n"
        f"    (source {_sexpr(title)})\n"
        f"    (date {_sexpr(dt.datetime.now().strftime('%Y-%m-%d %H:%M'))})\n"
        '    (tool "Ohmnia")\n'
        '    (sheet (number "1") (name "/") (tstamps "/")\n'
        f"      (title_block (title {_sexpr(title)})\n"
        f'        (comment (number "1") (value {_sexpr(note)})))))\n'
        "  (components\n" + "\n".join(comps) + ")\n"
        "  (nets\n" + "\n".join(net_lines) + "))\n"
    )


__all__ = ["Part", "parse", "to_kicad"]
