"""Schematic of the active filters (DM-FIL): one row per section of the cascade.

The rows follow the netlist that the module simulates: the designators and the nodes come
from the circuit builder (``o1``, ``o2``… are the outputs of the sections). Sections as in
Pertence (*Amplificadores operacionais e filtros ativos*): Sallen-Key and multiple feedback
(MFB) biquads, the state-variable (KHN) biquad with a summing amplifier, first-order RC
sections with a follower; the passive LC ladder is doubly terminated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .canvas import Canvas, eng

KIND_TEXT = {
    "sk_lp": "Sallen-Key passa-baixas (ganho unitário)",
    "sk_hp": "Sallen-Key passa-altas (ganho unitário)",
    "mfb_lp": "realimentação múltipla (MFB) passa-baixas",
    "mfb_bp": "realimentação múltipla (MFB) passa-faixa",
    "khn": "variáveis de estado (KHN) + somador",
    "lp1": "1ª ordem passa-baixas + seguidor",
    "hp1": "1ª ordem passa-altas + seguidor",
}
UNIT = {"R": "ohm", "C": "F", "L": "H"}


@dataclass(frozen=True)
class SectionInfo:
    kind: str
    k: int  # index in the cascade (node names use it)
    f0: float  # Hz
    Q: float


class _Net:
    """Lookup of the designator between two nodes, with its value text."""

    def __init__(self, values: Mapping[str, float], nodes: Mapping[str, tuple[str, str]]):
        self.values = values
        self.nodes = nodes

    def find(self, kind: str, a: str, b: str) -> tuple[str, str] | None:
        for d, (n1, n2) in self.nodes.items():
            if d[0] == kind and {n1, n2} == {a, b}:
                return d, eng(self.values[d], UNIT[kind])
        return None

    def get(self, kind: str, a: str, b: str) -> tuple[str, str]:
        found = self.find(kind, a, b)
        return found if found else (f"{kind}?", "")


def _header(svg: Canvas, y: float, sec: SectionInfo, opamps: str) -> None:
    q = "" if sec.kind in ("lp1", "hp1") else f", Q = {sec.Q:.3g}".replace(".", ",")
    svg.text(
        10,
        y,
        f"Seção {sec.k}: {KIND_TEXT[sec.kind]}, f0 = {eng(sec.f0, 'Hz')}{q}  ({opamps})",
        "start",
        "ttl",
    )


def _follower(svg: Canvas, x: float, yb: float, name: str, part: str, out: str) -> float:
    """Unity-gain follower with + at (x, yb); returns the x of the output node."""
    inv, _non, o = svg.opamp(x, yb + 15, name, part, flip=True)
    svg.wire(inv, (x - 12, inv[1]), (x - 12, yb + 62), (x + 80, yb + 62), (x + 80, o[1]))
    svg.wire(o, (x + 120, o[1]))
    svg.dot(x + 80, o[1])
    svg.terminal(x + 120, o[1], out)
    return x + 80


def _sk(svg: Canvas, net: _Net, x0: float, yb: float, k: int, a: str, hp: bool, u: str) -> None:
    m, x, o = f"m{k}", f"x{k}", f"o{k}"
    ser = "C" if hp else "R"
    sh = "R" if hp else "C"
    d1, v1 = net.get(ser, a, m)
    d2, v2 = net.get(ser, m, x)
    df, vf = net.get(sh, m, o)
    dg, vg = net.get(sh, x, "0")
    first = svg.cap_h if hp else svg.resistor_h
    first(x0 + 20, x0 + 120, yb, d1, v1)
    first(x0 + 120, x0 + 220, yb, d2, v2)
    svg.wire((x0 + 220, yb), (x0 + 260, yb))
    svg.dot(x0 + 235, yb)
    if hp:
        svg.res_v(x0 + 235, yb, yb + 80, dg, vg, left=True)
    else:
        svg.cap_np_v(x0 + 235, yb, yb + 80, dg, vg, left=True)
    svg.ground(x0 + 235, yb + 80)
    xo = _follower(svg, x0 + 260, yb, f"U{u}", "", o)
    svg.dot(x0 + 120, yb)
    svg.wire((x0 + 120, yb), (x0 + 120, yb - 60))
    (svg.resistor_h if hp else svg.cap_h)(x0 + 120, xo, yb - 60, df, vf)
    svg.wire((xo, yb - 60), (xo, yb + 15))


def _mfb(svg: Canvas, net: _Net, x0: float, yb: float, k: int, a: str, bp: bool, u: str) -> None:
    m, n, o = f"m{k}", f"n{k}", f"o{k}"
    xm, xn, xo = x0 + 130, x0 + 245, x0 + 380
    inv, non, out = svg.opamp(x0 + 270, yb + 15, f"U{u}", "")
    d1, v1 = net.get("R", a, m)
    svg.resistor_h(x0 + 20, xm, yb, d1, v1)
    svg.dot(xm, yb)
    if bp:
        dg, vg = net.get("R", m, "0")
        svg.res_v(xm, yb, yb + 80, dg, vg, left=True)
        d3, v3 = net.get("C", m, n)
        svg.cap_h(xm, xn, yb, d3, v3)
        di, vi = net.get("R", n, o)
        do, vo = net.get("C", m, o)
        inner, outer = svg.resistor_h, svg.cap_h
    else:
        dg, vg = net.get("C", m, "0")
        svg.cap_np_v(xm, yb, yb + 80, dg, vg, left=True)
        d3, v3 = net.get("R", m, n)
        svg.resistor_h(xm, xn, yb, d3, v3)
        di, vi = net.get("C", n, o)
        do, vo = net.get("R", m, o)
        inner, outer = svg.cap_h, svg.resistor_h
    svg.ground(xm, yb + 80)
    svg.wire((xn, yb), inv)
    svg.dot(xn, yb)
    svg.wire(non, (x0 + 255, non[1]), (x0 + 255, non[1] + 12))
    svg.ground(x0 + 255, non[1] + 12)
    svg.wire((xn, yb), (xn, yb - 50))
    inner(xn, xo, yb - 50, di, vi)
    svg.wire((xm, yb), (xm, yb - 100))
    outer(xm, xo, yb - 100, do, vo)
    svg.wire((xo, yb - 100), (xo, out[1]), out)
    svg.dot(xo, out[1])
    svg.dot(xo, yb - 50)
    svg.wire((xo, out[1]), (xo + 40, out[1]))
    svg.terminal(xo + 40, out[1], o)


def _first(svg: Canvas, net: _Net, x0: float, yb: float, k: int, a: str, hp: bool, u: str) -> None:
    x, o = f"x{k}", f"o{k}"
    if hp:
        d1, v1 = net.get("C", a, x)
        svg.cap_h(x0 + 20, x0 + 140, yb, d1, v1)
        dg, vg = net.get("R", x, "0")
        svg.res_v(x0 + 160, yb, yb + 80, dg, vg, left=True)
    else:
        d1, v1 = net.get("R", a, x)
        svg.resistor_h(x0 + 20, x0 + 140, yb, d1, v1)
        dg, vg = net.get("C", x, "0")
        svg.cap_np_v(x0 + 160, yb, yb + 80, dg, vg, left=True)
    svg.ground(x0 + 160, yb + 80)
    svg.wire((x0 + 140, yb), (x0 + 260, yb))
    svg.dot(x0 + 160, yb)
    _follower(svg, x0 + 260, yb, f"U{u}", "", o)


def _khn(svg: Canvas, net: _Net, x0: float, yb: float, k: int, a: str, u0: int) -> None:
    hp, bp, lp, p, na, nb, nc, nd, o = (
        f"{t}{k}" for t in ("hp", "bp", "lp", "p", "na", "nb", "nc", "nd", "o")
    )
    xp, xna, xhp, xbp, xlp, xnd = x0 + 120, x0 + 135, x0 + 245, x0 + 425, x0 + 605, x0 + 705
    # U(a): difference/summing amplifier giving the high-pass output
    inv, non, out = svg.opamp(x0 + 160, yb, f"U{u0}", "")
    d, val = net.get("R", a, p)
    svg.resistor_h(x0 + 10, xp, non[1], d, val)
    svg.wire((xp, non[1]), non)
    svg.dot(xp, non[1])
    svg.wire(inv, (xna, inv[1]))
    svg.dot(xna, inv[1])
    svg.wire((xna, inv[1]), (xna, yb - 115))
    svg.dot(xna, yb - 65)
    d, val = net.get("R", na, hp)
    svg.resistor_h(xna, xhp, yb - 65, d, val)
    svg.wire(out, (xhp, yb), (xhp, yb - 65))
    svg.dot(xhp, yb)
    # two inverting integrators: hp → bp → lp
    for xi, xo, src, dst, nn, ui in ((xhp, xbp, hp, bp, nb, 1), (xbp, xlp, bp, lp, nc, 2)):
        ia, ib, io = svg.opamp(xi + 95, yb, f"U{u0 + ui}", "")
        d, val = net.get("R", src, nn)
        svg.resistor_h(xi, xi + 75, yb, d, val)
        svg.wire((xi + 75, yb), (xi + 80, yb), (xi + 80, ia[1]), ia)
        svg.dot(xi + 80, ia[1])
        svg.wire(ib, (xi + 88, ib[1]), (xi + 88, ib[1] + 6))
        svg.ground(xi + 88, ib[1] + 6)
        svg.wire((xi + 80, ia[1]), (xi + 80, yb - 65))
        d, val = net.get("C", nn, dst)
        svg.cap_h(xi + 80, xo, yb - 65, d, val)
        svg.wire(io, (xo, yb), (xo, yb - 65))
        svg.dot(xo, yb)
    # feedback lanes: bp → p (Q) and lp → na (ω0)
    d, val = net.get("R", bp, p)
    svg.wire((xp, non[1]), (xp, yb + 90))
    svg.resistor_h(xp, xbp, yb + 90, d, val)
    svg.wire((xbp, yb), (xbp, yb + 90))
    svg.dot(xbp, yb + 90)
    d, val = net.get("R", lp, na)
    svg.resistor_h(xna, xlp, yb - 115, d, val)
    svg.wire((xlp, yb - 65), (xlp, yb - 115))
    svg.dot(xlp, yb - 65)
    # summing amplifier U(d): o = −(hp/Rh + bp/Rb + lp/Rl)·Rf
    ia, ib, io = svg.opamp(xnd + 40, yb + 40, f"U{u0 + 3}", "")
    lanes = ((lp, xlp, yb + 130), (bp, xbp, yb + 160), (hp, xhp, yb + 190))
    bottom = yb + 40
    for src, xs, y in lanes:
        found = net.find("R", src, nd)
        if not found:
            continue
        if src == hp:  # the hp column crosses the bp → p lane
            svg.jumper(xs, yb, yb + 180)
            svg.wire((xs, yb + 180), (xs, y))
        else:
            svg.wire((xs, yb + (90 if src == bp else 0)), (xs, y))
        svg.resistor_h(xs, xnd, y, *found)
        svg.dot(xnd, y)
        bottom = max(bottom, y)
    svg.wire(ia, (xnd, ia[1]), (xnd, bottom))
    svg.dot(xnd, ia[1])
    svg.wire(ib, (xnd + 25, ib[1]), (xnd + 25, ib[1] + 6))
    svg.ground(xnd + 25, ib[1] + 6)
    d, val = net.get("R", nd, o)
    svg.wire((xnd, ia[1]), (xnd, yb - 30))
    svg.resistor_h(xnd, xnd + 130, yb - 30, d, val)
    svg.wire((xnd + 130, yb - 30), (xnd + 130, io[1]))
    svg.wire(io, (xnd + 170, io[1]))
    svg.dot(xnd + 130, io[1])
    svg.terminal(xnd + 170, io[1], o)


def active(
    title: str,
    description: str,
    sections: Sequence[SectionInfo],
    values: Mapping[str, float],
    nodes: Mapping[str, tuple[str, str]],
    part: str,
) -> str:
    net = _Net(values, nodes)
    heights = {"khn": 400, "mfb_lp": 270, "mfb_bp": 270, "lp1": 180, "hp1": 180}
    total = 60 + sum(heights.get(s.kind, 230) for s in sections)
    wide = any(s.kind == "khn" for s in sections)
    svg = Canvas(960 if wide else 600, total)
    svg.title(title)
    svg.text(10, 36, f"{description}; ampops {part} (U1 a U{_count(sections)})", "start", "pn")
    y = 60
    a = "in"
    u = 1
    for sec in sections:
        n_ops = 4 if sec.kind == "khn" else 1
        ops = f"U{u}" if n_ops == 1 else f"U{u} a U{u + n_ops - 1}"
        _header(svg, y + 12, sec, ops)
        if sec.kind == "khn":
            yb = y + 165
        elif sec.kind.startswith("mfb"):
            yb = y + 150
        elif sec.kind in ("lp1", "hp1"):
            yb = y + 70
        else:
            yb = y + 115
        svg.terminal(10, yb if sec.kind != "khn" else yb + 15, a)
        if sec.kind in ("sk_lp", "sk_hp"):
            _sk(svg, net, 10, yb, sec.k, a, sec.kind == "sk_hp", str(u))
        elif sec.kind in ("mfb_lp", "mfb_bp"):
            _mfb(svg, net, 10, yb, sec.k, a, sec.kind == "mfb_bp", str(u))
        elif sec.kind in ("lp1", "hp1"):
            _first(svg, net, 10, yb, sec.k, a, sec.kind == "hp1", str(u))
        else:
            _khn(svg, net, 10, yb, sec.k, a, u)
        y += heights.get(sec.kind, 230)
        a = f"o{sec.k}"
        u += n_ops
    if sections:
        svg.text(
            10, total - 8, f"Entrada: fonte Vsig no nó in; saída do filtro: {a}.", "start", "pn"
        )
    return svg.render(title)


def _count(sections: Sequence[SectionInfo]) -> int:
    return sum(4 if s.kind == "khn" else 1 for s in sections)


def ladder(
    title: str,
    description: str,
    parts: Sequence[tuple[str, str, float]],
    nodes: Mapping[str, tuple[str, str]],
) -> str:
    """Doubly terminated LC ladder: source resistor, alternating shunt and series elements."""
    svg = Canvas(230 + 120 * len(parts), 280)
    svg.title(title)
    svg.text(10, 36, description, "start", "pn")
    y, yg = 110, 220
    svg.sine_v(40, y, yg, "Vsig", "", left=False)
    svg.ground(40, yg)
    x = 40.0
    node = "in"
    shunt_here = False
    for d, kind, value in parts:
        a, b = nodes[d]
        text = eng(value, UNIT[kind])
        if "0" in (a, b):  # shunt element at the current node
            if shunt_here:  # a second one on the same node (the load): beside the first
                svg.wire((x, y), (x + 90, y))
                x += 90
            svg.dot(x, y)
            draw = {"R": svg.res_v, "C": svg.cap_np_v, "L": svg.ind_v}[kind]
            draw(x, y, yg, d, text)
            svg.ground(x, yg)
            shunt_here = True
            continue
        shunt_here = False
        nxt = b if a == node else a
        x2 = x + 120
        draw_h = {"R": svg.resistor_h, "C": svg.cap_h, "L": svg.ind_h}[kind]
        draw_h(x, x2, y, d, text)
        x, node = x2, nxt
    svg.terminal(x + 30, y, f"vo ({node})")
    svg.wire((x, y), (x + 30, y))
    return svg.render(title)
