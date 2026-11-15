"""SPICE netlist → schematic, so that a netlist from a book, a manufacturer or another program
can be simulated, probed and edited.

Elements the library knows become symbols placed on a grid, each pin with a short wire and a
label with its node name (the ground node gets the ground symbol). Everything else is kept as
raw SPICE in the directives: ``.model``, ``.subckt`` blocks, ``.include``, ``.options``, ``.ic``,
coupling ``K`` lines and elements without a symbol (transmission lines, XSPICE, EXP sources...).
Since the labels keep the node names and the symbols keep the element names, those raw lines
still connect to the placed parts. LTspice ``.step`` lines become the schematic sweep.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from circuitos.schematic.library import pin_defs, pin_positions, symbol
from circuitos.schematic.model import (
    Analysis,
    Component,
    NetLabel,
    Schematic,
    Sweep,
    Wire,
)
from circuitos.schematic.netlist import GROUND_NAMES
from circuitos.schematic.values import try_parse

_SAFE = re.compile(r"[^A-Za-z0-9_]")
_SAFE_NODE = re.compile(r"[^A-Za-z0-9_+\-]")


@dataclass
class ImportResult:
    schematic: Schematic
    warnings: list[str] = field(default_factory=list)


def tokenize(text: str) -> list[str]:
    """Split on blanks, parentheses and commas, keeping ``{...}`` groups and joining ``a = b``."""
    tokens: list[str] = []
    cur = ""
    depth = 0
    for ch in text:
        if depth:
            cur += ch
            depth += ch == "{"
            depth -= ch == "}"
            continue
        if ch == "{":
            depth = 1
            cur += ch
        elif ch.isspace() or ch in "(),":
            if cur:
                tokens.append(cur)
            cur = ""
        elif ch == "=":
            if cur:
                tokens.append(cur)
            tokens.append("=")
            cur = ""
        else:
            cur += ch
    if cur:
        tokens.append(cur)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 2 < len(tokens) and tokens[i + 1] == "=":
            out.append(f"{tokens[i]}={tokens[i + 2]}")
            i += 3
        else:
            out.append(tokens[i])
            i += 1
    return [t for t in out if t != "="]


def _logical_lines(text: str) -> tuple[str, list[str]]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title = raw[0].lstrip("*").strip() if raw else ""
    lines: list[str] = []
    for ln in raw[1:]:
        s = ln.rstrip()
        stripped = s.strip()
        if not stripped or stripped.startswith("*"):
            continue
        s = re.split(r"\s;|^;|\s\$\s", s, maxsplit=1)[0].rstrip()
        if not s.strip():
            continue
        if s.lstrip().startswith("+") and lines:
            lines[-1] += " " + s.lstrip()[1:].strip()
        else:
            lines.append(s.strip())
    return title, lines


class _Importer:
    def __init__(self) -> None:
        self.components: list[Component] = []
        self.directives: list[str] = []
        self.params: dict[str, str] = {}
        self.analyses: list[Analysis] = []
        self.temperature = "27"
        self.sweep = Sweep()
        self.warnings: list[str] = []
        self.models: dict[str, str] = {}  # model name (lower) -> type (lower)
        self.subckt_pins: dict[str, list[str]] = {}
        self.node_map: dict[str, str] = {}
        self.refs: set[str] = set()
        self.raw_elements: list[str] = []
        self._nodes: dict[str, list[str]] = {}

    # names ---------------------------------------------------------------------------------
    def node(self, name: str) -> str:
        low = name.lower()
        if low in GROUND_NAMES:
            return "0"
        if low not in self.node_map:
            safe = _SAFE_NODE.sub("_", name)
            if safe != name:
                self.warnings.append(f"Nó {name!r} renomeado para {safe!r}.")
            self.node_map[low] = safe
        return self.node_map[low]

    def ref(self, name: str) -> str:
        safe = _SAFE.sub("_", name)
        if safe != name:
            self.warnings.append(f"Elemento {name!r} renomeado para {safe!r}.")
        base, k = safe, 1
        while safe.lower() in self.refs:
            k += 1
            safe = f"{base}_{k}"
        self.refs.add(safe.lower())
        return safe

    def raw(self, line: str, why: str) -> None:
        self.raw_elements.append(line)
        self.warnings.append(f"{line.split()[0]}: {why}; mantido como SPICE nas diretivas.")

    # pass 1: models and subcircuits ------------------------------------------------------------
    def scan(self, lines: list[str]) -> None:
        for ln in lines:
            m = re.match(r"^\.model\s+(\S+)\s+([A-Za-z]+)", ln, re.IGNORECASE)
            if m:
                self.models[m.group(1).lower()] = m.group(2).lower()
            m = re.match(r"^\.subckt\s+(\S+)\s+(.*)$", ln, re.IGNORECASE)
            if m:
                pins = []
                for t in m.group(2).split():
                    if t.lower().startswith("params:") or "=" in t:
                        break
                    pins.append(t)
                self.subckt_pins[m.group(1).lower()] = pins

    # elements -------------------------------------------------------------------------------
    def add(self, kind: str, name: str, nodes: list[str], params: dict[str, str]) -> None:
        comp = Component(
            id=f"c{len(self.components) + 1}",
            kind=kind,
            ref=self.ref(name),
            x=0,
            y=0,
            params=params,
        )
        comp_nodes = [self.node(n) for n in nodes]
        self.components.append(comp)
        self._nodes[comp.id] = comp_nodes

    def element(self, line: str) -> None:
        letter = line[0].upper()
        b = re.match(r"^(\S+)\s+(\S+)\s+(\S+)\s+([VvIi])\s*=\s*(.+)$", line)
        if letter == "B":
            if b is None:
                return self.raw(line, "fonte B sem V= ou I=")
            name, n1, n2, typ, expr = b.groups()
            return self.add("bsource", name, [n1, n2], {"type": typ.upper(), "expr": expr})
        t = tokenize(line)
        name, args = t[0], t[1:]
        kv = [a for a in args if "=" in a]
        pos = [a for a in args if "=" not in a]
        if letter in "RCL":
            if len(pos) != 3:
                return self.raw(line, "forma não suportada")
            extra = [a for a in kv if not a.lower().startswith("ic=")]
            if extra:
                return self.raw(line, f"parâmetros {' '.join(extra)} sem campo no símbolo")
            kind = {"R": "resistor", "C": "capacitor", "L": "inductor"}[letter]
            params = {"value": pos[2]}
            ic = [a.split("=", 1)[1] for a in kv if a.lower().startswith("ic=")]
            if ic:
                params["ic"] = ic[0]
            params["tol"] = "0"  # a netlist carries no tolerance
            return self.add(kind, name, pos[:2], params)
        if letter in "VI":
            return self.source(line, name, letter, args)
        if letter == "D":
            if len(pos) != 3 or kv:
                return self.raw(line, "forma não suportada")
            return self.add("diode", name, pos[:2], {"model": pos[2]})
        if letter == "Q":
            if len(pos) != 4 or kv:
                return self.raw(line, "substrato, área ou parâmetros sem campo no símbolo")
            typ = self.models.get(pos[3].lower(), "npn")
            kind = "pnp" if typ == "pnp" else "npn"
            return self.add(kind, name, pos[:3], {"model": pos[3], "tol": "0"})
        if letter == "M":
            if len(pos) != 5 or kv or pos[3].lower() != pos[2].lower():
                return self.raw(line, "corpo separado da fonte ou W/L sem campo no símbolo")
            typ = self.models.get(pos[4].lower(), "nmos")
            if typ not in ("nmos", "pmos"):
                return self.raw(line, f"modelo {typ} sem símbolo")
            d, g, s = pos[0], pos[1], pos[2]
            return self.add(typ, name, [d, g, s], {"model": pos[4]})
        if letter == "J":
            if len(pos) != 4 or kv:
                return self.raw(line, "forma não suportada")
            typ = self.models.get(pos[3].lower(), "njf")
            kind = "pjf" if typ == "pjf" else "njf"
            return self.add(kind, name, pos[:3], {"model": pos[3]})
        if letter in "EG":
            if len(pos) != 5 or kv or (try_parse(pos[4]) is None and not pos[4].startswith("{")):
                return self.raw(line, "fonte controlada não linear (POLY/VALUE/TABLE)")
            kind, key = ("vcvs", "gain") if letter == "E" else ("vccs", "gm")
            return self.add(kind, name, pos[:4], {key: pos[4]})
        if letter in "FH":
            if len(pos) != 4 or kv:
                return self.raw(line, "fonte controlada não linear")
            kind, key = ("cccs", "gain") if letter == "F" else ("ccvs", "r")
            return self.add(kind, name, pos[:2], {"control": pos[2], key: pos[3]})
        if letter == "S":
            if len(pos) != 5 or kv:
                return self.raw(line, "forma não suportada")
            return self.add("switch", name, pos[:4], {"model": pos[4]})
        if letter == "X":
            words = [a for a in args if "=" not in a and a.lower() != "params:"]
            if len(words) < 2:
                return self.raw(line, "subcircuito sem nós")
            sub, nodes = words[-1], words[:-1]
            pins = self.subckt_pins.get(sub.lower())
            if pins is None or len(pins) != len(nodes):
                pins = [f"p{k + 1}" for k in range(len(nodes))]
            pins = [_SAFE.sub("_", p) or f"p{k}" for k, p in enumerate(pins)]
            if len(set(p.lower() for p in pins)) != len(pins):
                pins = [f"p{k + 1}" for k in range(len(nodes))]
            params = {"model": sub, "pins": " ".join(pins)}
            if kv:
                params["args"] = " ".join(kv)
            return self.add("subckt", name, nodes, params)
        if letter == "K":
            self.raw_elements.append(line)
            return None
        return self.raw(line, "elemento sem símbolo na biblioteca")

    def source(self, line: str, name: str, letter: str, args: list[str]) -> None:
        if len(args) < 2:
            return self.raw(line, "fonte sem nós")
        nodes, rest = args[:2], args[2:]
        kind = "dc"
        dc: str | None = None
        ac = "0"
        func: list[str] = []
        repeat = False
        i = 0
        while i < len(rest):
            tok = rest[i].lower()
            if tok == "dc" and i + 1 < len(rest):
                dc = rest[i + 1]
                i += 2
            elif tok == "ac":
                i += 1
                ac = "1"
                if i < len(rest) and _is_num(rest[i]):
                    ac = rest[i]
                    i += 1
                    if i < len(rest) and _is_num(rest[i]):
                        if try_parse(rest[i]) != 0:
                            self.warnings.append(f"{name}: fase AC ignorada.")
                        i += 1
            elif tok in ("sin", "pulse", "pwl"):
                kind = tok
                i += 1
                while i < len(rest) and _is_num(rest[i]):
                    func.append(rest[i])
                    i += 1
            elif tok.startswith("r=") and kind == "pwl":
                repeat = True
                if try_parse(tok[2:]) != 0:
                    self.warnings.append(f"{name}: repetição da PWL a partir de 0 s.")
                i += 1
            elif tok in ("exp", "sffm", "am", "trnoise", "trrandom", "distof1", "distof2"):
                return self.raw(line, f"forma de onda {tok.upper()} sem símbolo")
            elif dc is None and _is_num(rest[i]):
                dc = rest[i]
                i += 1
            else:
                return self.raw(line, f"termo {rest[i]!r} não reconhecido")
        k = letter.lower()
        if kind == "dc":
            return self.add(f"{k}dc", name, nodes, {"dc": dc or "0", "ac": ac, "tol": "0"})
        if kind == "sin":
            keys: tuple[str, ...] = ("offset", "amplitude", "freq", "delay", "damping", "phase")
            params = dict(zip(keys, func, strict=False))
            if "freq" not in params:
                self.warnings.append(f"{name}: SIN sem frequência; usado 1 kHz.")
            params.update(ac=ac, tol="0")
            return self.add(f"{k}sin", name, nodes, params)
        if kind == "pulse":
            keys = ("v1", "v2", "delay", "rise", "fall", "width", "period")
            params = dict(zip(keys, func, strict=False))
            if len(func) < 7:
                self.warnings.append(
                    f"{name}: PULSE incompleto; os termos faltantes vêm do símbolo."
                )
            params["ac"] = ac
            return self.add(f"{k}pulse", name, nodes, params)
        if len(func) < 2 or len(func) % 2:
            return self.raw(line, "PWL com número ímpar de termos")
        params = {"points": " ".join(func), "repeat": "sim" if repeat else "não", "ac": ac}
        return self.add(f"{k}pwl", name, nodes, params)

    # dot cards ------------------------------------------------------------------------------
    def card(self, line: str) -> None:
        t = tokenize(line)
        word = t[0].lower()
        if word == ".param":
            for a in t[1:]:
                if "=" in a:
                    k, v = a.split("=", 1)
                    self.params[k] = v
            return
        if word == ".temp":
            if len(t) > 1:
                self.temperature = t[1]
            if len(t) > 2:
                self.warnings.append(".temp com vários valores: use a varredura de temperatura.")
            return
        if word == ".op":
            self.analyses.append(Analysis(kind="op"))
            return
        if word == ".tran":
            pos = [a for a in t[1:] if a.lower() != "uic"]
            keys: tuple[str, ...] = ("tstep", "tstop", "tstart", "tmax")
            params = dict(zip(keys, pos, strict=False))
            if any(a.lower() == "uic" for a in t[1:]):
                params["uic"] = "sim"
            self.analyses.append(Analysis(kind="tran", params=params))
            return
        if word == ".ac":
            keys = ("variation", "points", "fstart", "fstop")
            self.analyses.append(Analysis(kind="ac", params=dict(zip(keys, t[1:], strict=False))))
            return
        if word == ".dc":
            keys = ("source", "start", "stop", "step", "source2", "start2", "stop2", "step2")
            params = dict(zip(keys, t[1:], strict=False))
            for key in ("source", "source2"):
                if key in params and params[key].lower() != "temp":
                    params[key] = _SAFE.sub("_", params[key])
            self.analyses.append(Analysis(kind="dc", params=params))
            return
        if word == ".noise":
            m = re.match(
                r"^\.noise\s+v\(\s*([^,\s)]+)\s*(?:,\s*([^\s)]+)\s*)?\)\s+(\S+)\s+(\S+)\s+(\S+)"
                r"\s+(\S+)\s+(\S+)",
                line,
                re.IGNORECASE,
            )
            if m is None:
                self.directives.append(line)
                self.warnings.append(".noise em forma não reconhecida; mantida como diretiva.")
                return
            out, ref, src, var, pts, f1, f2 = m.groups()
            params = {
                "output": self.node(out),
                "source": _SAFE.sub("_", src),
                "variation": var,
                "points": pts,
                "fstart": f1,
                "fstop": f2,
            }
            if ref:
                params["reference"] = self.node(ref)
            self.analyses.append(Analysis(kind="noise", params=params))
            return
        if word == ".step":
            self.step(t)
            return
        if word in (".end", ".ends"):
            return
        if word in (".print", ".plot", ".probe", ".backanno"):
            return
        known = (
            ".model",
            ".include",
            ".inc",
            ".lib",
            ".options",
            ".option",
            ".opt",
            ".ic",
            ".nodeset",
            ".func",
            ".global",
            ".save",
            ".meas",
            ".measure",
            ".csparam",
        )
        if word not in known:
            self.warnings.append(f"{t[0]}: diretiva mantida sem interpretação.")
        if word in (".include", ".inc", ".lib"):
            self.warnings.append(
                f"{t[0]} {' '.join(t[1:])}: o arquivo precisa existir na pasta de trabalho do "
                "ngspice; prefira colar o modelo nas diretivas."
            )
        self.directives.append(line)

    def step(self, t: list[str]) -> None:
        args = t[1:]
        spacing = "lin"
        if args and args[0].lower() in ("oct", "dec", "lin"):
            spacing = args[0].lower()
            args = args[1:]
        if args and args[0].lower() == "param":
            target = f"param:{args[1]}"
            args = args[2:]
        elif args and args[0].lower() == "temp":
            target = "temp"
            args = args[1:]
        elif args:
            target = f"{_SAFE.sub('_', args[0])}.dc"
            args = args[1:]
        else:
            self.warnings.append(".step sem parâmetro; ignorado.")
            return
        if target.endswith(".dc"):
            ref = target[:-3]
            comp = next((c for c in self.components if c.ref.lower() == ref.lower()), None)
            if comp is not None and comp.kind in ("resistor", "capacitor", "inductor"):
                target = f"{comp.ref}.value"
        sw = Sweep(kind="temp" if target == "temp" else "step", target=target)
        if args and args[0].lower() == "list":
            sw.spacing, sw.values = "list", args[1:]
        elif len(args) >= 3:
            sw.start, sw.stop = args[0], args[1]
            if spacing == "lin":
                sw.spacing, sw.step = "lin", args[2]
            else:
                pts = try_parse(args[2]) or 5
                sw.spacing, sw.points = spacing, max(1, round(pts))  # type: ignore[assignment]
        else:
            self.warnings.append(".step incompleto; ignorado.")
            return
        self.sweep = sw

    # placement ------------------------------------------------------------------------------
    def place(self) -> tuple[list[Component], list[Wire], list[NetLabel]]:
        n = len(self.components)
        cols = max(1, math.ceil(math.sqrt(n)))
        wires: list[Wire] = []
        labels: list[NetLabel] = []
        grounds: list[Component] = []
        for k, comp in enumerate(self.components):
            comp.x, comp.y = (k % cols) * 16, (k // cols) * 12
            nodes = self._nodes[comp.id]
            for pin, node in zip(pin_defs(comp), nodes, strict=True):
                px, py = pin_positions(comp)[pin.name]
                if abs(pin.dx) >= abs(pin.dy):
                    end = (px + (2 if pin.dx > 0 else -2), py)
                else:
                    end = (px, py + (2 if pin.dy > 0 else -2))
                wires.append(Wire(id=f"w{len(wires) + 1}", points=[(px, py), end]))
                if node == "0":
                    grounds.append(
                        Component(
                            id=f"g{len(grounds) + 1}",
                            kind="ground",
                            ref=f"GND{len(grounds) + 1}",
                            x=end[0],
                            y=end[1],
                        )
                    )
                else:
                    labels.append(NetLabel(id=f"l{len(labels) + 1}", name=node, x=end[0], y=end[1]))
        return self.components + grounds, wires, labels


def _is_num(tok: str) -> bool:
    return try_parse(tok) is not None or (tok.startswith("{") and tok.endswith("}"))


def import_netlist(text: str) -> ImportResult:
    title, lines = _logical_lines(text)
    imp = _Importer()
    if title and re.match(r"^[RCLVIDQMJEGFHBSXK]\S*\s+\S+\s+\S+", title, re.IGNORECASE):
        imp.warnings.append(
            "A primeira linha de uma netlist SPICE é o título e foi lida assim: "
            f"{title!r}. Se era um elemento, acrescente uma linha de título."
        )
    imp.scan(lines)
    depth = 0
    in_control = False
    subckt_lines: list[str] = []
    for ln in lines:
        low = ln.lower()
        if in_control:
            in_control = not low.startswith(".endc")
            continue
        if low.startswith(".control"):
            in_control = True
            imp.warnings.append("Bloco .control ignorado (as análises vêm do esquemático).")
            continue
        if low.startswith(".subckt"):
            depth += 1
        if depth:
            subckt_lines.append(ln)
            if low.startswith(".ends"):
                depth -= 1
            continue
        if low.startswith(".end"):
            break
        if ln.startswith("."):
            imp.card(ln)
        else:
            imp.element(ln)
    if not any(a.kind for a in imp.analyses):
        imp.warnings.append("A netlist não tem análise; acrescente uma no painel de análises.")
    components, wires, labels = imp.place()
    raw = imp.raw_elements
    if raw:
        rename = {k: v for k, v in imp.node_map.items() if k != v.lower()}
        if rename:
            raw = [" ".join(rename.get(tok.lower(), tok) for tok in ln.split()) for ln in raw]
    directives = "\n".join([*subckt_lines, *imp.directives, *raw])
    sch = Schematic(
        title=title or "Netlist importada",
        components=components,
        wires=wires,
        labels=labels,
        analyses=imp.analyses,
        sweep=imp.sweep,
        params=imp.params,
        temperature=imp.temperature,
        directives=directives,
    )
    for comp in components:
        symbol(comp.kind)  # every kind placed exists in the library
    return ImportResult(sch, list(dict.fromkeys(imp.warnings)))
