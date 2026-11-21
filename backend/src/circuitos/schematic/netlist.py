"""Schematic → SPICE netlist: connectivity, node names, element lines, probes and analyses.

Connectivity rules (the same in the editor):

* pins, wire vertices and labels that share a grid point are connected;
* a pin, label or wire end lying on the inside of a wire segment is connected to that wire (a
  T junction); two wires that merely cross are not;
* labels with the same name are one net; the ground symbol and the labels ``0`` and ``gnd`` are
  node 0.

Nets take the name of their label (lower case, as ngspice reports vectors); the others are
numbered ``n001``, ``n002``... in the order of their first pin, so the names are stable.
"""

from __future__ import annotations

import contextlib
import itertools
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, CalcStep, record
from circuitos.core.units import Q_, parse_unit
from circuitos.cosim.controllers import ControllerSpec, SensorSpec, controller_lines
from circuitos.design.opamp import OpAmp
from circuitos.devices.thyristor import Kind as ThyristorKind
from circuitos.schematic import parts, stress, transformers
from circuitos.schematic.cosim_symbols import (
    CONTROLLER_KINDS,
    COSIM_KINDS,
    catalogue_value,
    emit_device,
)
from circuitos.schematic.drive_symbols import max_step as drive_max_step
from circuitos.schematic.library import (
    element_name,
    param,
    pin_defs,
    pin_positions,
    symbol,
)
from circuitos.schematic.model import Analysis, Component, NetRef, Point, Probe, Schematic
from circuitos.schematic.sensor_symbols import DIGITAL_SENSOR_KINDS
from circuitos.schematic.values import format_value, is_expression, parse_value, try_parse

GROUND_NAMES = {"0", "gnd"}


class SchematicError(ValueError):
    """The schematic cannot be turned into a netlist (message in Portuguese)."""


# --------------------------------------------------------------------------- connectivity


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[object, object] = {}

    def find(self, x: object) -> object:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: object, b: object) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    (px, py), (ax, ay), (bx, by) = p, a, b
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


_GND = ("gnd",)


@dataclass
class Connectivity:
    pin_nodes: dict[str, dict[str, str]]  # ref -> pin -> node
    nets: dict[str, list[str]]  # node -> ["R1.1", ...]
    point_nodes: dict[Point, str]  # every pin, vertex and label point
    labels: dict[str, str]  # label name (lower) -> node
    warnings: list[str]
    has_ground: bool

    def node_at(self, p: Point, wires: list[list[Point]]) -> str | None:
        if p in self.point_nodes:
            return self.point_nodes[p]
        for pts in wires:
            for a, b in itertools.pairwise(pts):
                if _on_segment(p, a, b):
                    return self.point_nodes.get(a)
        return None


def connectivity(sch: Schematic) -> Connectivity:
    uf = _UnionFind()
    anchors: set[Point] = set()
    pins: list[tuple[str, str, Point]] = []
    for c in sch.components:
        for name, pt in pin_positions(c).items():
            pins.append((c.ref, name, pt))
            anchors.add(pt)
            uf.find(pt)
            if c.kind == "ground":
                uf.union(_GND, pt)
    for w in sch.wires:
        for a, b in zip(w.points, w.points[1:], strict=False):
            anchors.update((a, b))
            uf.union(a, b)
    label_points: dict[str, list[Point]] = {}
    for lb in sch.labels:
        pt = (lb.x, lb.y)
        anchors.add(pt)
        uf.find(pt)
        label_points.setdefault(lb.name.lower(), []).append(pt)
    for w in sch.wires:  # T junctions: an anchor inside a segment joins that wire
        for a, b in zip(w.points, w.points[1:], strict=False):
            for p in anchors:
                if p != a and p != b and _on_segment(p, a, b):
                    uf.union(a, p)
    for name, pts in label_points.items():
        for p in pts[1:]:
            uf.union(pts[0], p)
        if name in GROUND_NAMES:
            uf.union(_GND, pts[0])
    has_ground = uf.find(_GND) in {uf.find(p) for _, _, p in pins} or any(
        n in GROUND_NAMES for n in label_points
    )

    # names
    root_labels: dict[object, list[str]] = {}
    for name, pts in label_points.items():
        root_labels.setdefault(uf.find(pts[0]), []).append(name)
    warnings: list[str] = []
    names: dict[object, str] = {uf.find(_GND): "0"}
    for root, lbs in root_labels.items():
        if root in names:
            continue
        lbs = sorted(set(lbs))
        names[root] = lbs[0]
        if len(lbs) > 1:
            warnings.append(f"Rótulos {', '.join(lbs)} estão no mesmo nó; usado {lbs[0]}.")
    taken = set(names.values())
    counter = 0
    for _ref, _pin, pt in sorted(pins, key=lambda x: (x[0].lower(), x[1])):
        root = uf.find(pt)
        if root not in names:
            while True:
                counter += 1
                candidate = f"n{counter:03d}"
                if candidate not in taken:
                    break
            names[root] = candidate
            taken.add(candidate)
    pin_nodes: dict[str, dict[str, str]] = {}
    nets: dict[str, list[str]] = {}
    for ref, pin, pt in pins:
        node = names[uf.find(pt)]
        pin_nodes.setdefault(ref, {})[pin] = node
        nets.setdefault(node, []).append(f"{ref}.{pin}")
    point_nodes = {p: names[uf.find(p)] for p in anchors if uf.find(p) in names}
    labels = {n: names[uf.find(pts[0])] for n, pts in label_points.items()}
    kinds = {c.ref: c.kind for c in sch.components}
    for node, members in sorted(nets.items()):
        real = [m for m in members if kinds[m.split(".")[0]] != "ground"]
        # spare pins of a controller board (an Arduino has 20) are expected to be free
        if (
            node != "0"
            and len(real) == 1
            and node not in labels.values()
            and kinds[real[0].split(".")[0]] not in CONTROLLER_KINDS
        ):
            warnings.append(f"Pino {real[0]} não está ligado a nada (nó {node}).")
    return Connectivity(pin_nodes, nets, point_nodes, labels, warnings, has_ground)


# ------------------------------------------------------------------------------- probes


@dataclass(frozen=True)
class ProbeVector:
    """A probe as an expression on the simulator vectors (evaluated after each run)."""

    name: str
    expr: str
    unit: str
    probe_id: str | None = None


def _v(node: str) -> str:
    return "0" if node == "0" else f"v({node})"


def _resolve(ref: NetRef, conn: Connectivity, sch: Schematic) -> str:
    if ref.net is not None:
        node = conn.labels.get(ref.net.lower())
        if node is None:
            if ref.net.lower() in conn.nets:
                return ref.net.lower()
            # internal node of a device model, documented as <ref>_x (v(m1_rpm), v(h1_temp))
            owner = ref.net.lower().split("_", 1)[0]
            if "_" in ref.net and any(
                c.ref.lower() == owner and c.kind in COSIM_KINDS for c in sch.components
            ):
                return ref.net.lower()
            raise SchematicError(f"Rótulo {ref.net!r} não existe")
        return node
    if ref.pin is not None:
        cref, _, pin = ref.pin.partition(".")
        try:
            return conn.pin_nodes[sch.component(cref).ref][pin]
        except KeyError as exc:
            raise SchematicError(f"Pino {ref.pin!r} não existe") from exc
    assert ref.at is not None
    node = conn.node_at(ref.at, [w.points for w in sch.wires])
    if node is None:
        raise SchematicError(f"Nenhum fio ou pino no ponto {ref.at} da ponteira de prova")
    return node


def _ammeter(ref: str, pin: str) -> str:
    return f"vam_{ref}_{pin}".lower()


def plan_probes(
    sch: Schematic, conn: Connectivity
) -> tuple[list[ProbeVector], set[tuple[str, str]]]:
    """Probe expressions and the pins that need a 0 V ammeter in series."""
    vectors: list[ProbeVector] = []
    ammeters: set[tuple[str, str]] = set()
    for pr in sch.probes:
        vectors.append(_probe_vector(pr, sch, conn, ammeters))
    return vectors, ammeters


def _probe_vector(
    pr: Probe, sch: Schematic, conn: Connectivity, ammeters: set[tuple[str, str]]
) -> ProbeVector:
    if pr.kind in ("v", "vdiff"):
        assert pr.target is not None
        a = _resolve(pr.target, conn, sch)
        if pr.kind == "v":
            if a == "0":
                raise SchematicError("Ponteira de tensão na terra: escolha outro nó")
            return ProbeVector(pr.name or f"v({a})", _v(a), "V", pr.id)
        assert pr.reference is not None
        b = _resolve(pr.reference, conn, sch)
        return ProbeVector(pr.name or f"v({a},{b})", f"{_v(a)}-{_v(b)}", "V", pr.id)
    assert pr.component is not None
    try:
        comp = sch.component(pr.component)
    except KeyError as exc:
        raise SchematicError(str(exc)) from exc
    pins = [p.name for p in pin_defs(comp)]
    if comp.kind == "ground" or not pins:
        raise SchematicError(f"{comp.ref} não tem corrente para medir")
    if pr.kind == "i":
        pin = pr.pin or pins[0]
        if pin not in pins:
            raise SchematicError(f"{comp.ref} não tem o pino {pin!r}")
        ammeters.add((comp.ref, pin))
        default = f"i({comp.ref.lower()})" if pin == pins[0] else f"i({comp.ref.lower()}.{pin})"
        return ProbeVector(pr.name or default, f"i({_ammeter(comp.ref, pin)})", "A", pr.id)
    # power absorbed: Σ (v_k − v_ref)·i_k over the pins but the last one
    nodes = conn.pin_nodes[comp.ref]
    ref_node = nodes[pins[-1]]
    terms = []
    for pin in pins[:-1]:
        ammeters.add((comp.ref, pin))
        dv = f"({_v(nodes[pin])}-{_v(ref_node)})"
        terms.append(f"{dv}*i({_ammeter(comp.ref, pin)})")
    return ProbeVector(pr.name or f"p({comp.ref.lower()})", "+".join(terms), "W", pr.id)


# ----------------------------------------------------------------------------- analyses


def _flag(text: str) -> bool:
    return text.strip().lower() in ("sim", "yes", "true", "1", "uic")


def analysis_card(a: Analysis, sch: Schematic, conn: Connectivity) -> str:
    p = {k: v.strip() for k, v in a.params.items() if v is not None}
    if a.kind == "op":
        return ".op"
    if a.kind == "tran":
        tstop = p.get("tstop") or "10m"
        # LTspice accepts a zero print step; ngspice does not (TSTEP must be > 0)
        tstep = p.get("tstep") or ""
        if not tstep or try_parse(tstep) == 0:
            tstep = format_value(parse_value(tstop) / 1000)
        card = f".tran {tstep} {tstop}"
        tstart, tmax = p.get("tstart", ""), p.get("tmax", "")
        cap = drive_max_step(sch.components)
        if cap is not None and (try_parse(tmax) or math.inf) > cap:
            tmax = format_value(cap, 4)
        if tstart or tmax:
            card += f" {tstart or '0'}"
        if tmax:
            card += f" {tmax}"
        if _flag(p.get("uic", "")):
            card += " uic"
        return card
    if a.kind == "ac":
        return (
            f".ac {p.get('variation') or 'dec'} {p.get('points') or '20'} "
            f"{p.get('fstart') or '10'} {p.get('fstop') or '1meg'}"
        )
    if a.kind == "dc":
        card = ".dc " + _sweep_source(p.get("source") or "", sch)
        card += f" {p.get('start') or '0'} {p.get('stop') or '1'} {p.get('step') or '0.1'}"
        if p.get("source2"):
            card += f" {_sweep_source(p['source2'], sch)} {p.get('start2') or '0'}"
            card += f" {p.get('stop2') or '1'} {p.get('step2') or '0.1'}"
        return card
    # noise
    out = p.get("output") or ""
    if not out:
        raise SchematicError("Análise de ruído sem nó de saída")
    node = _resolve(NetRef(net=out), conn, sch)
    ref = p.get("reference") or ""
    target = f"v({node},{_resolve(NetRef(net=ref), conn, sch)})" if ref else f"v({node})"
    src = _sweep_source(p.get("source") or "", sch)
    return (
        f".noise {target} {src} {p.get('variation') or 'dec'} {p.get('points') or '10'} "
        f"{p.get('fstart') or '10'} {p.get('fstop') or '1meg'}"
    )


def _sweep_source(name: str, sch: Schematic) -> str:
    if not name:
        raise SchematicError("Análise sem a fonte de varredura")
    if name.lower() == "temp":
        return "temp"
    try:
        comp = sch.component(name)
    except KeyError as exc:
        raise SchematicError(f"Fonte {name!r} não existe") from exc
    if symbol(comp.kind).prefix not in ("V", "I") or comp.kind == "v3ph":
        raise SchematicError(f"{name} não é uma fonte independente de tensão ou corrente")
    return element_name(comp)


# ----------------------------------------------------------------------------- elements


@dataclass(frozen=True)
class Indicator:
    """LED or lamp whose brightness the editor draws from a simulated current."""

    kind: str  # "led" | "lamp"
    vector: str  # current vector through it, e.g. i(vlum_led1)
    i_ref: float | None = None  # A, LED: current of 100 % brightness
    i_max: float | None = None  # A, LED: maximum DC forward current
    colour: str | None = None
    r: float | None = None  # Ω, lamp: hot resistance
    p_nom: float | None = None  # W, lamp
    v_nom: float | None = None  # V, lamp


@dataclass
class _Ctx:
    records: Mapping[str, ComponentRecord]
    overrides: Mapping[tuple[str, str], float]
    sch: Schematic
    models: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    log: CalcLog = field(default_factory=CalcLog)
    spreads: dict[str, parts.Spread] = field(default_factory=dict)
    controllers: list[ControllerSpec] = field(default_factory=list)
    digital_sensors: list[SensorSpec] = field(default_factory=list)
    indicators: dict[str, Indicator] = field(default_factory=dict)

    def value(self, comp: Component, name: str) -> str:
        o = self.overrides.get((comp.ref, name))
        if o is not None:
            return format_value(o, 9)
        return param(comp, name)

    def number(self, comp: Component, name: str) -> float:
        o = self.overrides.get((comp.ref, name))
        if o is not None:
            return o
        text = param(comp, name)
        try:
            return parse_value(text)
        except ValueError as exc:
            raise SchematicError(f"{comp.ref}.{name}: {exc}") from exc

    def override(self, comp: Component, name: str) -> float | None:
        return self.overrides.get((comp.ref, name))

    def model(self, name: str, text: str) -> str:
        self.models.setdefault(name, text)
        return name

    def record(self, comp: Component) -> ComponentRecord | None:
        if comp.part_id is None:
            return None
        rec = self.records.get(comp.part_id)
        if rec is None:
            raise SchematicError(f"{comp.ref}: peça {comp.part_id} não encontrada no catálogo")
        cats = symbol(comp.kind).catalogue
        if not any(rec.category == c or rec.category.startswith(f"{c}.") for c in cats):
            raise SchematicError(
                f"{comp.ref}: {rec.part_number} ({rec.category}) não serve para {comp.kind}"
            )
        return rec

    def use(self, comp: Component, pm: parts.PartModel) -> str:
        self.warnings += pm.warnings
        if pm.spread is not None:
            self.spreads[comp.ref] = pm.spread
        return self.model(pm.model_name, pm.model_text)


def _model_card(prefix: str, kind: str, values: dict[str, str]) -> tuple[str, str]:
    body = " ".join(f"{k.upper()}={v}" for k, v in values.items() if v != "")
    name = f"{prefix}_{parts.digest(kind + body)}"
    return name, f".model {name} {kind}({body})"


def _generic_spread(comp: Component, ctx: _Ctx) -> None:
    sym = symbol(comp.kind)
    if sym.tolerance is None or comp.part_id is not None:
        return
    tol_text = comp.params.get("tol", sym.param("tol").default) or "0"
    tol = try_parse(tol_text)
    nom = try_parse(param(comp, sym.tolerance))
    if tol is None or nom is None or tol <= 0:
        return
    span = abs(nom) * tol / 100
    ctx.spreads[comp.ref] = parts.Spread(
        sym.tolerance, nom - span, nom, nom + span, f"tolerância ±{tol:g} % ({comp.ref})"
    )


# catalogue transformer -> symbol parameters (record key per symbol parameter)
_TRANSFORMER_KEYS = {
    "transformer_1ph": {"vp": "V_pri", "vs": "V_sec", "sn": "S_rated"},
    "transformer_1ph_4": {"vp": "V_pri@2", "vs": "V_sec@2", "sn": "S_rated"},
}


def _transformer_from_record(comp: Component, rec: ComponentRecord, kind: str) -> Component:
    """Nameplate values of a catalogue transformer; the turns ratio stays the voltage ratio.
    The 4-coil symbol takes the parallel ratings (each coil's voltage)."""
    params = dict(comp.params)
    for name, key in _TRANSFORMER_KEYS[kind].items():
        p = rec.parameters.get(key)
        x = None if p is None else next((v for v in (p.typ, p.max, p.min) if v is not None), None)
        if p is None or x is None:
            raise SchematicError(
                f"{comp.ref}: {rec.part_number} não traz {key} no datasheet; não serve para "
                "este símbolo de transformador"
            )
        unit = {"vp": "V", "vs": "V", "sn": "VA"}[name]
        params[name] = f"{Q_(x, parse_unit(p.unit)).m_as(unit):.6g}"
    params.pop("turns", None)
    return comp.model_copy(update={"params": params})


def _source_lines(comp: Component, n: list[str], ctx: _Ctx) -> list[str]:
    name = element_name(comp)
    kind = comp.kind[1:]

    def v(key: str) -> str:
        return ctx.value(comp, key)

    ac = f" AC {v('ac')}"
    head = f"{name} {n[0]} {n[1]}"
    if kind == "dc":
        return [f"{head} DC {v('dc')}{ac}"]
    if kind == "sin":
        args = " ".join(v(k) for k in ("offset", "amplitude", "freq", "delay", "damping", "phase"))
        return [f"{head} DC {v('offset')}{ac} SIN({args})"]
    if kind == "pulse":
        args = " ".join(v(k) for k in ("v1", "v2", "delay", "rise", "fall", "width", "period"))
        return [f"{head} DC {v('v1')}{ac} PULSE({args})"]
    points = param(comp, "points")
    values = points.split()
    if len(values) < 2 or len(values) % 2:
        raise SchematicError(f"{comp.ref}: a PWL precisa de pares tempo/valor")
    rep = " r=0" if _flag(param(comp, "repeat")) else ""
    return [f"{head} DC {values[1]}{ac} PWL({points}){rep}"]


def _emit(comp: Component, n: list[str], ctx: _Ctx) -> list[str]:
    k = comp.kind
    name = element_name(comp)

    def v(key: str) -> str:
        return ctx.value(comp, key)

    ref = comp.ref
    if k == "ground":
        return []
    if k in ("resistor", "capacitor", "inductor"):
        rec = ctx.record(comp)
        if rec is not None:
            ctx.warnings.extend(parts.passive_check(rec, comp, k))
        line = f"{name} {n[0]} {n[1]} {v('value')}"
        ic = comp.params.get("ic", "").strip()
        if ic and k != "resistor":
            line += f" IC={ic}"
        return [line]
    if k == "rl_load":
        mid = f"{ref}_rl".lower()
        return [f"R_{ref} {n[0]} {mid} {v('r')}", f"L_{ref} {mid} {n[1]} {v('l')}"]
    if k == "transformer":
        lp, ratio = v("lp"), v("n")
        lpv, nv = try_parse(lp), try_parse(ratio)
        if lpv is not None and nv is not None:
            ls = format_value(lpv * nv * nv, 9)
        else:
            ls = "{" + f"({lp.strip('{}')})*({ratio.strip('{}')})**2" + "}"
        a, b = f"{ref}_p".lower(), f"{ref}_s".lower()
        return [
            f"R_{ref}_p {n[0]} {a} {v('rp')}",
            f"L_{ref}_p {a} {n[1]} {lp}",
            f"R_{ref}_s {n[2]} {b} {v('rs')}",
            f"L_{ref}_s {b} {n[3]} {ls}",
            f"K_{ref} L_{ref}_p L_{ref}_s {v('k')}",
            f"R_{ref}_iso {n[1]} {n[3]} 1g",
        ]
    if k in ("transformer_1ph", "transformer_1ph_4"):
        rec = ctx.record(comp)
        if rec is not None:  # a catalogue transformer: nameplate from its datasheet
            comp = _transformer_from_record(comp, rec, k)
            ctx.warnings.extend(parts.review_warning(rec, ref))
    if k in ("transformer_1ph", "transformer_3ph"):
        three = k == "transformer_3ph"
        conn_p = param(comp, "conn_p") if three else "D"
        conn_s = param(comp, "conn_s") if three else "D"
        turns = param(comp, "turns").strip()
        try:
            w = transformers.size(
                ref,
                transformers.winding_voltage(ctx.number(comp, "vp"), conn_p),
                transformers.winding_voltage(ctx.number(comp, "vs"), conn_s),
                ctx.number(comp, "turns") if turns else None,
                ctx.number(comp, "sn") / (3 if three else 1),
                ctx.number(comp, "freq"),
                ctx.number(comp, "imag"),
                ctx.number(comp, "rcu"),
                ctx.log,
            )
        except transformers.TransformerError as exc:
            raise SchematicError(str(exc)) from exc
        if three:
            return transformers.three_phase_lines(ref, n, conn_p, conn_s, w)
        return [
            *transformers.pair_lines(ref, (n[0], n[1]), (n[2], n[3]), w),
            f"R_{ref}_iso {n[1]} {n[3]} 1g",
        ]
    if k in ("transformer_1ph_4", "transformer_3ph_open"):
        try:
            w = transformers.size(
                ref,
                ctx.number(comp, "vp"),
                ctx.number(comp, "vs"),
                None,
                ctx.number(comp, "sn") / (3 if k == "transformer_3ph_open" else 1),
                ctx.number(comp, "freq"),
                ctx.number(comp, "imag"),
                ctx.number(comp, "rcu"),
                ctx.log,
            )
        except transformers.TransformerError as exc:
            raise SchematicError(str(exc)) from exc
        if k == "transformer_3ph_open":
            return transformers.open_three_phase_lines(ref, n, w)
        return transformers.four_coil_lines(ref, n, w)
    if k == "autotransformer":
        try:
            aw = transformers.size_auto(
                ref,
                ctx.number(comp, "vh"),
                ctx.number(comp, "vx"),
                ctx.number(comp, "sn"),
                ctx.number(comp, "freq"),
                ctx.number(comp, "imag"),
                ctx.number(comp, "rcu"),
                ctx.log,
            )
        except transformers.TransformerError as exc:
            raise SchematicError(str(exc)) from exc
        return transformers.auto_lines(ref, n[0], n[1], n[2], aw)
    if k[0] in "vi" and k[1:] in ("dc", "sin", "pulse", "pwl"):
        return _source_lines(comp, n, ctx)
    if k == "v3ph":
        vpk = ctx.number(comp, "vrms") * math.sqrt(2)
        f, ph = v("freq"), ctx.number(comp, "phase")
        sign = -1 if param(comp, "sequence") == "abc" else 1
        return [
            f"V_{ref}_{p} {n[i]} {n[3]} DC 0 SIN(0 {vpk:.9g} {f} 0 0 {ph + sign * 120 * i:.9g})"
            for i, p in enumerate("abc")
        ]
    if k == "bsource":
        kind = param(comp, "type").upper()
        return [f"{name} {n[0]} {n[1]} {'I' if kind == 'I' else 'V'}={param(comp, 'expr')}"]
    if k in ("vcvs", "vccs"):
        return [f"{name} {' '.join(n)} {v('gain' if k == 'vcvs' else 'gm')}"]
    if k in ("cccs", "ccvs"):
        ctl = param(comp, "control")
        with contextlib.suppress(KeyError):
            ctl = element_name(ctx.sch.component(ctl))
        return [f"{name} {n[0]} {n[1]} {ctl} {v('gain' if k == 'cccs' else 'r')}"]
    if k == "diode":
        rec = ctx.record(comp)
        if rec is not None:
            return [f"X{ref} {n[0]} {n[1]} {ctx.use(comp, parts.diode(rec, ref))}"]
        model = param(comp, "model")
        if not model:
            vals = {key: v(key) for key in ("is", "n", "rs", "cjo", "tt", "bv")}
            model = ctx.model(*_model_card("DG", "D", vals))
        return [f"{name} {n[0]} {n[1]} {model}"]
    if k == "led":
        rec = ctx.record(comp)
        if rec is not None:
            data, warn = parts.led_data(rec, ref)
            ctx.warnings += warn
        else:
            data = parts.LedData(
                ctx.number(comp, "vf"),
                ctx.number(comp, "if_ref"),
                ctx.number(comp, "if_max"),
                None,
            )
        mname = f"LED_{parts.digest(f'{data.vf:.9g}')}"
        model = ctx.model(mname, parts.constant_drop_diode(mname, data.vf))
        inner = f"{ref}_la".lower()
        ctx.indicators[ref] = Indicator(
            kind="led",
            vector=f"i(vlum_{ref.lower()})",
            i_ref=data.i_ref,
            i_max=data.i_max,
            colour=data.colour or param(comp, "color"),
        )
        return [f"Vlum_{ref} {n[0]} {inner} DC 0", f"X{ref} {inner} {n[1]} {model}"]
    if k == "lamp":
        rec = ctx.record(comp)
        if rec is not None:
            lamp, warn = parts.lamp_data(rec, ref)
            ctx.warnings += warn
        else:
            lamp = parts.LampData(ctx.number(comp, "vn"), ctx.number(comp, "pn"))
        if lamp.pn <= 0 or lamp.vn <= 0:
            raise SchematicError(f"{ref}: tensão e potência nominais devem ser positivas")
        inner = f"{ref}_la".lower()
        ctx.indicators[ref] = Indicator(
            kind="lamp",
            vector=f"i(vlum_{ref.lower()})",
            r=lamp.r_hot,
            p_nom=lamp.pn,
            v_nom=lamp.vn,
        )
        if f"{ref}_r_hot" not in {st.id for st in ctx.log}:
            ctx.log.add(
                record(
                    f"{ref}_r_hot",
                    f"Resistência a quente da lâmpada {ref}",
                    r"R_{quente} = \frac{V_n^2}{P_n}",
                    Q_(lamp.r_hot, "ohm"),
                    {"V_n": Q_(lamp.vn, "V"), "P_n": Q_(lamp.pn, "W")},
                    [
                        "Filamento como resistência constante, a de regime na tensão nominal "
                        "(P = V²/R); a resistência a frio e a corrente de partida não constam "
                        "das fichas técnicas e não são modeladas.",
                    ],
                )
            )
        return [f"Vlum_{ref} {n[0]} {inner} DC 0", f"R{ref} {inner} {n[1]} {lamp.r_hot:.9g}"]
    if k == "zener":
        rec = ctx.record(comp)
        if rec is not None:
            pm = parts.zener(rec, ref, ctx.log, ctx.override(comp, "vz"))
            return [f"{name} {n[0]} {n[1]} {ctx.use(comp, pm)}"]
        vz, rz, vf = ctx.number(comp, "vz"), ctx.number(comp, "rz"), ctx.number(comp, "vf")
        mname = f"ZG_{parts.digest(f'{vz}|{rz}|{vf}')}"
        return [f"{name} {n[0]} {n[1]} {ctx.model(mname, parts.zener_subckt(mname, vz, rz, vf))}"]
    if k in ("npn", "pnp"):
        rec = ctx.record(comp)
        if rec is not None:
            pm = parts.bjt(rec, ref, ctx.number(comp, "ic_op"), ctx.log, ctx.override(comp, "bf"))
            model = ctx.use(comp, pm)
            if pm.extra.get("darlington"):
                return [f"X{ref} {' '.join(n)} {model}"]
            return [f"{name} {' '.join(n)} {model}"]
        model = param(comp, "model")
        if not model:
            vals = {key: v(key) for key in ("bf", "is", "vaf")}
            model = ctx.model(*_model_card("QG", k.upper(), vals))
        return [f"{name} {' '.join(n)} {model}"]
    if k in ("nmos", "pmos"):
        d, g, s = n
        rec = ctx.record(comp)
        if rec is not None:
            model = ctx.use(
                comp,
                parts.mosfet(rec, ref, ctx.log, ctx.override(comp, "vto"), k == "pmos"),
            )
        else:
            model = param(comp, "model")
            if not model:
                vals = {"level": "1", **{key: v(key) for key in ("vto", "kp", "lambda")}}
                model = ctx.model(*_model_card("MG", k.upper(), vals))
        return [f"{name} {d} {g} {s} {s} {model}"]
    if k in ("njf", "pjf"):
        d, g, s = n
        rec = ctx.record(comp)
        if rec is not None:
            model = ctx.use(comp, parts.jfet(rec, ref, ctx.log, k == "pjf"))
        else:
            model = param(comp, "model")
            if not model:
                vals = {key: v(key) for key in ("vto", "beta", "lambda")}
                model = ctx.model(*_model_card("JG", k.upper(), vals))
        return [f"{name} {d} {g} {s} {model}"]
    if k == "opamp":
        inn, inp, out = n
        rec = ctx.record(comp)
        vcc, vee = ctx.number(comp, "vcc"), ctx.number(comp, "vee")
        if rec is not None:
            model = ctx.use(comp, parts.opamp(rec, ref, vcc, vee, ctx.log))
        else:
            sr_text = param(comp, "sr")
            sr = parse_value(sr_text) if sr_text else math.inf
            m = OpAmp(
                A0=ctx.number(comp, "a0"),
                GBW=ctx.number(comp, "gbw"),
                SR=sr,
                v_hi=vcc - 1.5,
                v_lo=vee + 1.5,
            )
            mname = f"OG_{parts.digest(parts.opamp_subckt('x', m))}"
            model = ctx.model(mname, parts.opamp_subckt(mname, m))
        return [f"{name} {inp} {inn} {out} {model}"]
    if k == "switch":
        model = param(comp, "model")
        if not model:
            vals = {key: v(key) for key in ("vt", "vh", "ron", "roff")}
            model = ctx.model(*_model_card("SW", "SW", vals))
        return [f"{name} {' '.join(n)} {model}"]
    if k == "igbt":
        rec = ctx.record(comp)
        diode = _flag(param(comp, "diode"))
        if rec is not None:
            model = ctx.use(comp, parts.igbt(rec, ref, ctx.number(comp, "v0"), diode))
        else:
            vth, v0, ron = (ctx.number(comp, x) for x in ("vth", "v0", "ron"))
            vf = ctx.number(comp, "vf")
            mname = f"IGG_{parts.digest(f'{vth}|{v0}|{ron}|{diode}|{vf}')}"
            model = ctx.model(mname, parts.igbt_subckt(mname, vth, v0, ron, diode, vf))
        return [f"{name} {' '.join(n)} {model}"]
    if k in ("scr", "triac"):
        a, kk, g = n
        rec = ctx.record(comp)
        vt0 = ctx.number(comp, "vt0")
        tk: ThyristorKind = "scr" if k == "scr" else "triac"
        if rec is not None:
            model = ctx.use(comp, parts.thyristor_part(rec, ref, tk, vt0, ctx.number(comp, "il")))
        else:
            rt, igt = ctx.number(comp, "rt"), ctx.number(comp, "igt")
            ih, il = ctx.number(comp, "ih"), ctx.number(comp, "il")
            gates = (igt, 1e6, 1e6, 1e6) if k == "scr" else (igt, igt, igt, igt)
            mname = f"THG_{parts.digest(f'{k}|{vt0}|{rt}|{igt}|{ih}|{il}')}"
            model = ctx.model(mname, parts.thyristor_subckt(mname, tk, vt0, rt, gates, ih, il))
        return [f"{name} {a} {kk} {g} {kk} {model}"]
    if k == "subckt":
        model = param(comp, "model")
        if not model:
            raise SchematicError(f"{ref}: informe o nome do .subckt")
        args = param(comp, "args")
        return [f"{name} {' '.join(n)} {model}" + (f" {args}" if args else "")]
    if k in COSIM_KINDS:
        pins = {p.name: node for p, node in zip(pin_defs(comp), n, strict=True)}
        try:
            if k in CONTROLLER_KINDS:
                values = {pd.name: param(comp, pd.name) for pd in symbol(k).params}
                lines, spec = controller_lines(ref, k, values, pins)
                ctx.controllers.append(spec)
                ctx.warnings += spec.warnings
                return lines
            value: Callable[[str], str] = lambda name: ctx.value(comp, name)  # noqa: E731
            rec = ctx.record(comp)
            if rec is not None:
                value = catalogue_value(k, rec, value)
            if k in DIGITAL_SENSOR_KINDS:
                values = {pd.name: value(pd.name) for pd in symbol(k).params}
                nodes = {p: node.lower() for p, node in pins.items()}
                ctx.digital_sensors.append(SensorSpec(ref, k, values, nodes))
            return emit_device(comp, pins, value)
        except SchematicError:
            raise
        except ValueError as exc:
            raise SchematicError(f"{ref}: {exc}") from exc
    raise SchematicError(f"Tipo de componente sem netlist: {k}")


# ------------------------------------------------------------------------------- netlist


@dataclass
class Netlist:
    text: str
    nets: dict[str, list[str]]
    pin_nodes: dict[str, dict[str, str]]
    probes: list[ProbeVector]
    warnings: list[str]
    spreads: dict[str, parts.Spread]
    steps: list[CalcStep]
    elements: dict[str, str]  # designator -> SPICE element name
    controllers: list[ControllerSpec] = field(default_factory=list)  # co-simulation (Fase 11)
    digital_sensors: list[SensorSpec] = field(default_factory=list)  # read by the boards
    indicators: dict[str, Indicator] = field(default_factory=dict)  # LEDs and lamps
    limits: list[stress.Limit] = field(default_factory=list)  # ratings checked after a run


def build_netlist(
    sch: Schematic,
    records: Mapping[str, ComponentRecord] | None = None,
    *,
    overrides: Mapping[tuple[str, str], float] | None = None,
    params: Mapping[str, str] | None = None,
    temperature: float | None = None,
    title_suffix: str = "",
) -> Netlist:
    """Netlist of the schematic; ``overrides`` replace component parameters (sweeps, Monte
    Carlo), ``params`` replace ``.param`` values and ``temperature`` the ``.temp`` card."""
    if not any(c.kind != "ground" for c in sch.components):
        raise SchematicError("O esquemático não tem componentes")
    conn = connectivity(sch)
    if not conn.has_ground:
        raise SchematicError("O circuito não tem terra: coloque o símbolo de terra (nó 0)")
    probes, ammeters = plan_probes(sch, conn)
    ctx = _Ctx(records or {}, overrides or {}, sch)
    warnings = list(conn.warnings)
    lines = [f"* {sch.title}{title_suffix}", "* gerado pelo Ohmnia"]
    all_params = {**sch.params, **(params or {})}
    for pname, pval in all_params.items():
        lines.append(f".param {pname}={pval}")
    elements: dict[str, str] = {}
    limits: list[stress.Limit] = []
    t_amb = temperature if temperature is not None else try_parse(sch.temperature)
    for comp in sch.components:
        if comp.kind == "ground":
            continue
        nodes_by_pin = conn.pin_nodes.get(comp.ref, {})
        pins = [p.name for p in pin_defs(comp)]
        rec = ctx.records.get(comp.part_id) if comp.part_id else None
        sensed = stress.sense_pin(comp, rec)
        sense: dict[str, str] = {}
        nodes = []
        for pin in pins:
            node = nodes_by_pin[pin]
            if (comp.ref, pin) in ammeters:
                inner = f"am_{comp.ref}_{pin}".lower()
                lines.append(f"{_ammeter(comp.ref, pin)} {node} {inner} DC 0")
                sense[pin] = f"i({_ammeter(comp.ref, pin)})"
                node = inner
            elif pin == sensed:
                # 0 V source that measures the current into the pin (damage check)
                inner = f"sn_{comp.ref}_{pin}".lower()
                lines.append(f"v{inner} {node} {inner} DC 0")
                sense[pin] = f"i(v{inner})"
                node = inner
            nodes.append(node)
        limits += stress.limits_for(comp, nodes_by_pin, rec, sense, t_amb)
        _generic_spread(comp, ctx)
        lines += _emit(comp, nodes, ctx)
        elements[comp.ref] = element_name(comp)
    lines += list(ctx.models.values())
    if sch.directives.strip():
        lines += [ln for ln in sch.directives.strip().splitlines() if ln.strip()]
    temp = temperature if temperature is not None else try_parse(sch.temperature)
    if temp is None and not is_expression(sch.temperature):
        raise SchematicError(f"Temperatura inválida: {sch.temperature!r}")
    lines.append(f".temp {temp:.9g}" if temp is not None else f".temp {sch.temperature}")
    active = [a for a in sch.analyses if a.enabled]
    if not active:
        raise SchematicError("Escolha pelo menos uma análise")
    lines += [analysis_card(a, sch, conn) for a in active]
    lines.append(".end")
    return Netlist(
        text="\n".join(lines) + "\n",
        nets=conn.nets,
        pin_nodes=conn.pin_nodes,
        probes=probes,
        warnings=list(dict.fromkeys(warnings + ctx.warnings)),
        spreads=ctx.spreads,
        steps=list(ctx.log),
        elements=elements,
        controllers=ctx.controllers,
        digital_sensors=ctx.digital_sensors,
        indicators=ctx.indicators,
        limits=limits,
    )
