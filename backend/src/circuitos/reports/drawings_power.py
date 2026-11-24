"""Schematics of the power modules: DC-DC (DM-CC), isolated DC-DC (DM-CCI), inverters
(DM-INV), AC voltage controllers (DM-CACA) and drive/protection (DM-CMD).

Each drawing follows the netlist the module simulates (same nodes; the netlist element names
appear on the drawing where the part is the same). Topologies as in Hart (*Power
Electronics*, 1st ed., ch. 6, 7, 8 and 10), Mohan, Undeland & Robbins (*Power Electronics*,
3rd ed., ch. 7, 8, 10 and 23) and the IR2110 data sheet (typical connection).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from .canvas import Canvas, Pt, eng

Txt = Mapping[str, str]  # element → value text
Parts = Mapping[str, str]


def _gate(svg: Canvas, g: Pt, name: str, right: bool = False) -> None:
    """Gate terminal with its signal name (the simulation drives it with a pulse source)."""
    if right:
        svg.wire(g, (g[0] + 14, g[1]))
        svg.terminal(g[0] + 14, g[1], name)
    else:
        svg.wire(g, (g[0] - 14, g[1]))
        svg.terminal(g[0] - 14, g[1], name, "end")


def _gate_below(svg: Canvas, g: Pt, name: str) -> None:
    svg.wire(g, (g[0], g[1] + 12))
    svg.parts.append(f'<circle class="o" cx="{g[0]}" cy="{g[1] + 15}" r="3.5" fill="#fff"/>')
    svg.text(g[0] + 8, g[1] + 20, name, "start", "pn")


def _output(svg: Canvas, x: float, top: float, bot: float, v: Txt, negative: bool = False) -> None:
    """Output capacitor Co and load RL between the top wire and the return rail."""
    if negative:  # + plate at the return rail
        svg.rotated(180, x, (top + bot) / 2, lambda: svg.cap_v(x, top, bot, ""))
        svg.label(x + 16, (top + bot) / 2 - 4, "Co", v.get("Co", ""))
    else:
        svg.cap_v(x, top, bot, "Co", v.get("Co", ""))
    svg.dot(x, top)
    svg.dot(x, bot)
    svg.wire((x, top), (x + 90, top))
    svg.wire((x, bot), (x + 90, bot))
    svg.res_v(x + 90, top, bot, "RL", v.get("RL", ""))
    svg.wire((x + 90, top), (x + 140, top))
    svg.terminal(x + 140, top, "vo" + (" (negativa)" if negative else ""))


def _vin(svg: Canvas, x: float, top: float, bot: float, value: str, left: bool = True) -> None:
    svg.src_v(x, top, bot, "VIN", value, left=left)


# ============================================================================ DM-CC
def dcdc(topology: str, title: str, kind: str, v: Txt, parts: Parts, note: str, comp: Txt) -> str:
    """``kind``: mosfet / igbt; ``v``: element → value text; ``comp``: compensator values."""
    svg = Canvas(720, 640 if comp else 400)
    svg.title(title)
    svg.text(10, 36, note, "start", "pn")
    top, bot = 100.0, 300.0
    q, d = parts.get("Q1", ""), parts.get("D1", "")
    _vin(svg, 60, top, bot, v.get("VIN", ""))
    svg.ground(60, bot)
    xo = 0.0
    neg = topology in ("buckboost", "cuk")
    if topology in ("buck", "buckboost", "zeta"):
        g, a, b = svg.switch_h(kind, 170, top, "Q1", q)
        svg.wire((60, top), a)
        _gate_below(svg, g, "g (PWM)")
        xs = 290
        svg.wire(b, (xs, top))
        svg.dot(xs, top)
        if topology == "buck":
            svg.diode_vert(xs, top, bot, "D1", d, up=True)
            svg.ind_h(xs, xs + 120, top, "L1", v.get("L1", ""))
            xo = xs + 150
        elif topology == "buckboost":
            svg.ind_v(xs, top, bot, "L1", v.get("L1", ""), left=True)
            svg.diode_h(xs, xs + 120, top, "D1", d, right=False)
            xo = xs + 150
        else:  # zeta: L1 to ground, C1 in series, D1 to ground, L2 to the output
            svg.ind_v(xs, top, bot, "L1", v.get("L1", ""), left=True)
            svg.cap_h(xs, xs + 90, top, "C1", v.get("C1", ""))
            xb = xs + 90
            svg.dot(xb, top)
            svg.diode_vert(xb, top, bot, "D1", d, up=True)
            svg.ind_h(xb, xb + 110, top, "L2", v.get("L2", ""))
            xo = xb + 140
    else:  # boost, cuk, sepic: L1 from the input, Q1 to ground
        xs = 230
        svg.ind_h(60, xs, top, "L1", v.get("L1", ""))
        svg.dot(xs, top)
        g, dr, src = svg.switch_v(kind, xs - 8, 200, "Q1", q)
        svg.wire((xs, top), dr)
        svg.wire(src, (xs, bot))
        _gate(svg, g, "g (PWM)")
        if topology == "boost":
            svg.diode_h(xs, xs + 120, top, "D1", d)
            xo = xs + 150
        else:
            svg.cap_h(xs, xs + 100, top, "C1", v.get("C1", ""))
            xb = xs + 100
            svg.dot(xb, top)
            if topology == "cuk":
                svg.diode_vert(xb + 0, top, bot, "D1", d, up=False)
                svg.ind_h(xb, xb + 110, top, "L2", v.get("L2", ""))
                xo = xb + 140
            else:  # sepic
                svg.ind_v(xb, top, bot, "L2", v.get("L2", ""), left=True)
                svg.diode_h(xb, xb + 110, top, "D1", d)
                xo = xb + 140
    svg.wire((xo - 30, top), (xo, top))
    svg.wire((60, bot), (xo, bot))
    _output(svg, xo, top, bot, v, negative=neg)
    if comp:
        _compensator(svg, comp)
    return svg.render(title)


def _compensator(svg: Canvas, c: Txt) -> None:
    """Error amplifier with the type II/III network (Venable): the loop the design closes."""
    y0 = 380
    three = "Rc3" in c
    svg.text(
        10,
        y0,
        f"Compensador tipo {'III' if three else 'II'} (malha de tensão projetada; a simulação "
        "usa D fixo, em malha aberta)",
        "start",
        "ttl",
    )
    inv, non, out = svg.opamp(420, 520, "EA", "amplificador de erro")
    fb = 300
    yi = inv[1]
    svg.terminal(60, yi, "vo", "end")
    svg.resistor_h(60, fb, yi, "Rc1", c.get("Rc1", ""))
    svg.wire((fb, yi), inv)
    svg.dot(fb, yi)
    svg.res_v(fb, yi, 610, "Rb", c.get("Rb", ""), left=True)
    svg.ground(fb, 610)
    if three:
        svg.wire((90, yi), (90, 450))
        svg.dot(90, yi)
        svg.resistor_h(90, 190, 450, "Rc3", c.get("Rc3", ""))
        svg.cap_h(190, fb, 450, "Cc3", c.get("Cc3", ""))
    svg.wire((fb, yi), (fb, 410))
    xo = out[0] + 30
    svg.resistor_h(fb, 420, 450, "Rc2", c.get("Rc2", ""))
    svg.cap_h(420, xo, 450, "Cc1", c.get("Cc1", ""))
    svg.cap_h(fb, xo, 410, "Cc2", c.get("Cc2", ""))
    svg.dot(fb, 450)
    svg.wire((xo, 410), (xo, out[1]), out)
    svg.dot(xo, 450)
    svg.dot(xo, out[1])
    svg.wire((xo, out[1]), (xo + 50, out[1]))
    svg.terminal(xo + 50, out[1], "vc → PWM")
    svg.wire(non, (390, non[1]), (390, 560))
    svg.src_v(390, 560, 620, "Vref", c.get("Vref", ""), left=False)
    svg.ground(390, 620)


# ============================================================================ DM-CCI
def _wname(svg: Canvas, x: float, y1: float, y2: float, name: str, right: bool) -> None:
    """Name of a winding (as in the netlist), outside the core side."""
    if right:
        svg.text(x + 12, (y1 + y2) / 2 + 4, name, "start", "pn")
    else:
        svg.text(x - 12, (y1 + y2) / 2 + 4, name, "end", "pn")


def _ct_secondary(
    svg: Canvas, x: float, y1: float, yc: float, y2: float, v: Txt, parts: Parts
) -> None:
    """Centre-tapped secondary (x), D1 from the top end, D2 from the bottom one, LO, Co, RL."""
    svg.winding(x, y1, yc, right=False, dot="top")
    svg.winding(x, yc, y2, right=False, dot="top")
    _wname(svg, x, y1, yc, "LS1", right=True)
    _wname(svg, x, yc, y2, "LS2", right=True)
    xd = x + 130
    d = parts.get("D1", "")
    svg.diode_h(x, xd, y1, "D1", d)
    svg.diode_h(x, xd, y2, "D2", d)
    svg.wire((xd, y2), (xd, y1))
    svg.dot(xd, y1)
    svg.wire((x, yc), (x + 40, yc))
    svg.ground(x + 40, yc)
    svg.ind_h(xd, xd + 110, y1, "LO", v.get("LO", ""))
    xo = xd + 140
    svg.wire((xd + 110, y1), (xo, y1))
    yb = y2 + 60
    svg.wire((xo, yb), (xo + 90, yb))
    svg.ground(xo + 45, yb)
    _output(svg, xo, y1, yb, v)


def isolated(topology: str, title: str, kind: str, v: Txt, parts: Parts, note: str) -> str:
    svg = Canvas(820, 420)
    svg.title(title)
    svg.text(10, 36, note, "start", "pn")
    q = parts.get("Q1", "")
    top, bot = 100.0, 360.0
    xv = 40 if topology == "pushpull" else 60
    _vin(svg, xv, top, bot, v.get("VIN", ""), left=topology != "pushpull")
    svg.ground(xv, bot)
    svg.text(
        10,
        404,
        "Os terras do primário e do secundário são separados no circuito real "
        "(na simulação, o mesmo nó 0).",
        "start",
        "pn",
    )
    if topology in ("flyback", "forward"):
        xp, xs = 230, 270
        svg.wire((60, top), (xp, top))
        svg.winding(xp, top, 180, right=True, dot="top")
        _wname(svg, xp, top, 180, "LP", right=False)
        svg.core(250, top, 180)
        svg.text(250, top - 10, f"T1 {v.get('T1', '')}".strip(), "middle")
        g, dr, src = svg.switch_v(kind, xp - 8, 300, "Q1", q)
        svg.wire((xp, 180), dr)
        svg.wire(src, (xp, bot))
        svg.wire((60, bot), (xp, bot))
        _gate(svg, g, "g")
        if topology == "flyback":
            # secondary with the opposite dot: energy goes out while Q1 is off
            svg.winding(xs, top, 180, right=False, dot="bot")
            _wname(svg, xs, top, 180, "LS", right=True)
            svg.diode_h(xs, 400, top, "D1", parts.get("D1", ""))
            svg.wire((xs, 180), (xs, 195))
            svg.ground(xs, 195)
            svg.wire((400, top), (430, top))
            svg.wire((430, 260), (520, 260))
            svg.ground(475, 260)
            _output(svg, 430, top, 260, v)
            return svg.render(title)
        # forward: reset winding N3 with D3 back to the input
        svg.winding(130, 190, 270, right=True, dot="bot")  # dotted end at ground
        _wname(svg, 130, 190, 270, "LR", right=False)
        svg.core(150, 190, 270)
        svg.text(160, 236, "N3 (reset)", "start", "pn")
        svg.diode_vert(130, top, 190, "D3", parts.get("D3", ""), up=True, left=True)
        svg.dot(130, top)
        svg.wire((130, 270), (130, bot))
        svg.dot(130, bot)
        svg.winding(xs, top, 180, right=False, dot="top")
        _wname(svg, xs, top, 180, "LS", right=True)
        xd = 400
        svg.diode_h(xs, xd, top, "D1", parts.get("D1", ""))
        svg.dot(xd, top)
        svg.diode_vert(xd, top, 260, "D2", parts.get("D2", ""), up=True)
        svg.wire((xs, 180), (xs, 260), (xd, 260))
        svg.ground(xs, 260)
        svg.ind_h(xd, xd + 110, top, "LO", v.get("LO", ""))
        svg.wire((xd + 110, top), (540, top))
        svg.wire((xd, 260), (540, 260))
        _output(svg, 540, top, 260, v)
        svg.width = 840
        return svg.render(title)
    if topology == "pushpull":
        # centre-tapped primary: Vin at the tap, Q1 and Q2 to ground
        xp = 230
        yc = 180
        svg.wire((xv, top), (100, top), (100, yc), (xp, yc))
        svg.winding(xp, top, yc, right=True, dot="top")
        svg.winding(xp, yc, 260, right=True, dot="top")
        _wname(svg, xp, top, yc, "LP1", right=False)
        _wname(svg, xp, yc, 260, "LP2", right=False)
        svg.core(250, top, 260)
        svg.text(250, 58, f"T1 {v.get('T1', '')}".strip(), "middle")
        svg.dot(xp, yc)
        # Q1 from the top end (its lead hops over the supply wire), Q2 from the bottom end
        x1 = 120
        svg.wire((xp, top), (xp, 70), (x1, 70))
        svg.jumper(x1, 70, 284, yc)
        g1, d1, s1 = svg.switch_v(kind, x1 - 8, 310, "Q1", q)
        svg.wire(s1, (x1, bot))
        svg.dot(x1, bot)
        _gate(svg, g1, "g1")
        g2, d2, s2 = svg.switch_v(kind, xp - 8, 310, "Q2", q)
        svg.wire((xp, 260), d2)
        svg.wire(s2, (xp, bot))
        _gate(svg, g2, "g2", right=False)
        svg.wire((xv, bot), (xp, bot))
        _ct_secondary(svg, 270, top, yc, 260, v, parts)
        return svg.render(title)
    # half bridge (VH1 = Vin/2 stands for the capacitor divider) and full bridge
    full = topology == "fullbridge"
    xa, xb = 170, 300
    svg.wire((60, top), (xb, top))
    g1, d1, s1 = svg.switch_v(kind, xa - 8, 150, "Q1", q)
    g2, d2, s2 = svg.switch_v(kind, xa - 8, 290, "Q2", q)
    svg.wire((xa, top), d1)
    svg.wire(s1, d2)
    svg.wire(s2, (xa, bot))
    _gate(svg, g1, "g1")
    _gate(svg, g2, "g2")
    svg.dot(xa, top)
    ya = 210
    svg.dot(xa, ya)
    if full:
        g3, d3, s3 = svg.switch_v(kind, xb - 8, 150, "Q3", q)
        g4, d4, s4 = svg.switch_v(kind, xb - 8, 290, "Q4", q)
        svg.wire((xb, top), d3)
        svg.wire(s3, d4)
        svg.wire(s4, (xb, bot))
        _gate(svg, g3, "g2")
        _gate(svg, g4, "g1")
        nb = "b"
    else:
        svg.src_v(xb, top, 250, "VH1", v.get("VH1", "VIN/2"), left=False)
        nb = "m"
    yb = 250
    svg.dot(xb, yb)
    svg.wire((60, bot), (xb, bot))
    xp = 400
    svg.hop_h(xa, xp - 20, ya, xb)
    svg.wire((xp - 20, ya), (xp - 20, 150), (xp, 150))
    svg.wire((xb, yb), (xp - 20, yb), (xp - 20, 290), (xp, 290))
    svg.winding(xp, 150, 290, right=True, dot="top")
    _wname(svg, xp, 150, 290, "LP", right=False)
    svg.text(xb + 6, yb - 6, nb, "start", "pn")
    svg.text(xa + 6, ya - 6, "a", "start", "pn")
    svg.core(420, 150, 290)
    svg.text(420, 140, f"T1 {v.get('T1', '')}".strip(), "middle")
    _ct_secondary(svg, 440, 150, 220, 290, v, parts)
    svg.width = 900
    return svg.render(title)


# ============================================================================ DM-INV
def _leg(svg: Canvas, kind: str, x: float, top: float, bot: float, ph: str) -> float:
    """Inverter leg with antiparallel diodes; returns the y of the midpoint."""
    ym = (top + bot) / 2
    for yq, pos in ((top + 80, "U"), (bot - 80, "L")):
        g, dr, src = svg.switch_v(kind, x - 8, yq, "")
        svg.text(x - 40, yq - 12, f"Q{pos}{ph}", "end")
        _gate(svg, g, f"g{pos.lower()}{ph}")
        svg.wire((x, yq - 50), dr)
        svg.wire(src, (x, yq + 50))
        svg.wire((x, yq - 40), (x + 40, yq - 40))
        svg.wire((x, yq + 40), (x + 40, yq + 40))
        svg.diode_vert(x + 40, yq - 40, yq + 40, "", up=True)
        svg.text(x + 52, yq + 4, f"D{pos}{ph}", "start", "pn")
        svg.dot(x, yq - 40)
        svg.dot(x, yq + 40)
    svg.wire((x, top), (x, top + 30))
    svg.wire((x, top + 130), (x, bot - 130))
    svg.wire((x, bot - 30), (x, bot))
    svg.dot(x, ym)
    return ym


def inverter(phases: int, title: str, kind: str, v: Txt, parts: Parts, note: str, flt: bool) -> str:
    top = 80.0
    bot = 400.0
    q = parts.get("Q1", "")
    if phases == 1:
        svg = Canvas(820, 470)
        svg.title(title)
        svg.text(10, 36, note, "start", "pn")
        svg.src_v(60, top, bot, "VDC", v.get("VDC", ""), left=True)
        svg.ground(60, bot)
        xa, xb = 200, 700
        for x in (xa, xb):
            svg.dot(x, top)
            svg.dot(x, bot)
        svg.wire((60, top), (xb, top))
        svg.wire((60, bot), (xb, bot))
        ym = _leg(svg, kind, xa, top, bot, "a")
        _leg(svg, kind, xb, top, bot, "b")
        x = xa
        if flt:
            svg.ind_h(xa, 330, ym, "LFa", v.get("LF", ""))
            svg.dot(350, ym)
            svg.wire((330, ym), (350, ym))
            svg.cap_np_v(350, ym, 330, "CFa", v.get("CF", ""))
            svg.res_v(420, ym, 285, "RDa", v.get("RD", ""))
            svg.cap_np_v(420, 285, 330, "CDa", v.get("CD", ""))
            svg.dot(420, ym)
            svg.wire((350, 330), (620, 330), (620, ym))
            svg.dot(620, ym)
            svg.wire((350, ym), (440, ym))
            x = 440
        svg.resistor_h(x, x + 80, ym, "RLa", v.get("R", ""))
        svg.ind_h(x + 80, x + 160, ym, "LLa", v.get("L", ""))
        svg.wire((x + 160, ym), (xb, ym))
        svg.text(
            10, 455, f"Chaves {q}" + (" com diodo em antiparalelo" if q else ""), "start", "pn"
        )
        return svg.render(title)
    # three phases: outputs go down (hopping over the negative rail) to a star load
    svg = Canvas(870, 780 if flt else 690)
    svg.title(title)
    svg.text(10, 36, note, "start", "pn")
    svg.src_v(60, top, bot, "VDC", v.get("VDC", ""), left=True)
    svg.ground(60, bot)
    xs = [190, 400, 610]
    svg.wire((60, top), (xs[-1], top))
    svg.wire((60, bot), (xs[-1], bot))
    y_star = 740 if flt else 650
    for x, ph in zip(xs, "abc", strict=True):
        svg.dot(x, top)
        svg.dot(x, bot)
        ym = _leg(svg, kind, x, top, bot, ph)
        xo = x + 75
        svg.wire((x, ym), (xo, ym))
        svg.jumper(xo, ym, 450, bot)
        svg.terminal(xo, 450, ph)
        y = 450.0
        if flt:
            svg.ind_v(xo, y, 520, f"LF{ph}", v.get("LF", "") if ph == "a" else "", left=True)
            svg.dot(xo, 530)
            svg.wire((xo, 520), (xo, 530), (xo + 45, 530), (xo + 45, 545))
            svg.cap_np_v(xo + 45, 545, y_star, f"CF{ph}", v.get("CF", "") if ph == "a" else "")
            svg.wire((xo + 45, 530), (xo + 100, 530))
            svg.res_v(xo + 100, 530, 600, f"RD{ph}", v.get("RD", "") if ph == "a" else "")
            svg.cap_np_v(xo + 100, 600, y_star, f"CD{ph}", v.get("CD", "") if ph == "a" else "")
            y = 530
        svg.res_v(xo, y, y + 80, f"RL{ph}", v.get("R", "") if ph == "a" else "", left=True)
        svg.ind_v(xo, y + 80, y_star, f"LL{ph}", v.get("L", "") if ph == "a" else "", left=True)
    svg.wire((xs[0] + 75, y_star), (xs[-1] + 175 if flt else xs[-1] + 75, y_star))
    svg.text(xs[-1] + 85, y_star + 16, "n (estrela)", "start", "pn")
    extra = "; filtros ligados a n (RCN = 1 mΩ)" if flt else ""
    svg.text(
        10,
        y_star + 34,
        f"Chaves {q} com diodo em antiparalelo; n ligado ao terra por 1 MΩ na simulação{extra}",
        "start",
        "pn",
    )
    svg.height = int(y_star + 46)
    return svg.render(title)


# ============================================================================ DM-CACA
def ac_controller(title: str, v: Txt, parts: Parts, note: str, diac: bool, inductive: bool) -> str:
    svg = Canvas(640, 380)
    svg.title(title)
    svg.text(10, 36, note, "start", "pn")
    top, bot = 100.0, 320.0
    svg.sine_v(80, top, bot, "VS", v.get("VS", ""))
    svg.ground(80, bot)
    x1, x2 = 200, 320
    svg.wire((80, top), (x1, top))
    g = svg.triac(x1, x2, top)
    svg.text((x1 + x2) / 2, top - 24, "T1", "middle")
    svg.text((x1 + x2) / 2, top - 38, parts.get("T1", ""), "middle", "pn")
    svg.text(x1 - 4, top - 6, "MT2", "end", "pn")
    svg.text(x2 + 4, top - 6, "MT1", "start", "pn")
    xl = 440
    svg.wire((x2, top), (xl, top))
    if inductive:
        svg.res_v(xl, top, 210, "RL", v.get("R", ""))
        svg.ind_v(xl, 210, bot, "LL", v.get("L", ""))
    else:
        svg.res_v(xl, top, bot, "RL", v.get("R", ""))
    svg.wire((80, bot), (xl, bot))
    if diac:
        # RC network across the controller; the DIAC fires the gate when vC reaches V_BO
        yr = 180
        svg.dot(150, top)
        svg.wire((150, top), (150, yr))
        svg.resistor_h(150, 250, yr, "R_trig", v.get("R_trig", ""))
        svg.wire((250, yr), (360, yr))
        svg.dot(g[0], yr)
        svg.cap_np_v(360, top, yr, "C_trig", v.get("C_trig", ""))
        svg.dot(360, top)
        svg.diac_v(g[0], g[1], yr, "DIAC")
        svg.text(
            10,
            360,
            "Na simulação o gate recebe o pulso no ângulo calculado da rede RC + DIAC.",
            "start",
            "pn",
        )
    else:
        svg.wire(g, (g[0], g[1] + 20))
        svg.terminal(g[0], g[1] + 23, v.get("gate", "G"))
    svg.text(10, 374, "TRIAC simulado como dois SCRs em antiparalelo (XTA, XTB).", "start", "pn")
    return svg.render(title)


# ============================================================================ DM-CMD
def _bridge(svg: Canvas, cx: float, cy: float, r: float, name: str, part: str) -> None:
    """Diode bridge drawn as a diamond: AC at left/right, + at the top, − at the bottom."""
    pts = {"t": (cx, cy - r), "b": (cx, cy + r), "l": (cx - r, cy), "r": (cx + r, cy)}
    # (from, to) with the anode first: AC → + and − → AC
    for a, k in (("l", "t"), ("r", "t"), ("b", "l"), ("b", "r")):
        (x1, y1), (x2, y2) = pts[a], pts[k]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        half = math.hypot(x2 - x1, y2 - y1) / 2
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))

        def draw(mx: float = mx, my: float = my, half: float = half) -> None:
            svg.diode_h(mx - half, mx + half, my, "")

        svg.rotated(ang, mx, my, draw)
    svg.text(cx + r + 6, cy - r + 6, f"{name} {part}".strip(), "start")


def drive(title: str, kind: str, v: Txt, parts: Parts, note: str, snubber: bool) -> str:
    svg = Canvas(1050, 700)
    svg.title(title)
    svg.text(10, 36, note, "start", "pn")
    # ---- input: line, fuse, varistor, inrush switch, bridge, NTC, bus capacitor
    svg.text(10, 62, "Entrada e proteção", "start", "ttl")
    top, bot = 100.0, 270.0
    svg.sine_v(50, top, bot, "VAC", v.get("VAC", ""), left=False)
    svg.ground(50, bot + 40)
    svg.wire((50, bot), (50, bot + 40))
    svg.fuse_h(50, 150, top, "F1", v.get("F1", ""))
    svg.varistor_v(170, top, bot, "MOV", v.get("MOV", ""))
    svg.dot(170, top)
    svg.wire((150, top), (170, top))
    svg.switch_simple_h(170, 260, top, "SL", "liga na crista")
    cx, cy, r = 330, 185, 55
    svg.wire((260, top), (cx - r, top), (cx - r, cy))
    svg.wire((50, bot), (170, bot))
    svg.dot(170, bot)
    _bridge(svg, cx, cy, r, "B1", parts.get("B1", ""))
    # the line return goes to the right corner, hopping over the − rail
    svg.wire((170, bot), (170, bot + 30), (cx + r + 20, bot + 30))
    svg.jumper(cx + r + 20, bot + 30, cy, bot)
    svg.wire((cx + r + 20, cy), (cx + r, cy))
    svg.wire((cx, cy - r), (cx, top - 10), (400, top - 10))
    svg.ntc_h(400, 500, top - 10, "RNTC", v.get("RNTC", ""))
    svg.wire((cx, cy + r), (cx, bot), (600, bot))
    svg.wire((500, top - 10), (600, top - 10))
    svg.cap_v(530, top - 10, bot, "CBUS", v.get("CBUS", ""))
    svg.res_v(600, top - 10, bot, "RBL", v.get("RBL", ""))
    for x in (530,):
        svg.dot(x, top - 10)
        svg.dot(x, bot)
    svg.terminal(640, top - 10, "+Vbus")
    svg.wire((600, top - 10), (640, top - 10))
    svg.text(
        180,
        bot + 48,
        "F1 e MOV: proteção (não simulados); RREF = 1 MΩ do − ao terra "
        "só referencia o barramento no ngspice",
        "start",
        "pn",
    )
    # ---- gate driver with bootstrap supply
    svg.text(10, 345, "Comando de meia ponte com bootstrap", "start", "ttl")
    pins: dict[str, tuple[str, float, str]] = {
        "vcc": ("l", 25, "VCC"),
        "hin": ("l", 70, "HIN"),
        "lin": ("l", 110, "LIN"),
        "vss": ("l", 160, "VSS"),
        "ho": ("r", 25, "HO"),
        "vb": ("r", 60, "VB"),
        "vs": ("r", 100, "VS"),
        "lo": ("r", 140, "LO"),
        "com": ("r", 170, "COM"),
    }
    p = svg.chip(200, 380, 140, 190, "U1", parts.get("U1", ""), pins)
    y_vcc = 362
    svg.src_v(80, y_vcc, 600, "Vcc", v.get("Vcc", ""), left=True)
    svg.ground(80, 600)
    svg.wire((80, y_vcc), (250, y_vcc))
    svg.wire(p["vcc"], (165, p["vcc"][1]), (165, y_vcc))
    svg.dot(165, y_vcc)
    xb = 390
    svg.diode_h(250, xb, y_vcc, "D1", parts.get("D1", ""))
    svg.wire((xb, y_vcc), (xb, p["vb"][1]))
    svg.wire(p["vb"], (xb, p["vb"][1]))
    svg.dot(xb, p["vb"][1])
    svg.cap_np_v(xb, p["vb"][1], p["vs"][1], "C_boot", v.get("C_boot", ""))
    xq = 560
    svg.hop_h(p["ho"][0], 420, p["ho"][1], xb)
    svg.resistor_h(420, 510, p["ho"][1], "Rg", v.get("Rg", ""))
    gh, dh, sh = svg.switch_v(kind, xq - 8, p["ho"][1], "Q1", parts.get("Q1", ""))
    svg.wire((510, p["ho"][1]), gh)
    svg.wire(p["vs"], (xq, p["vs"][1]))
    svg.dot(xb, p["vs"][1])
    svg.resistor_h(p["lo"][0], 510, p["lo"][1], "Rg", v.get("Rg", ""))
    gl, dl, sl = svg.switch_v(kind, xq - 8, p["lo"][1], "Q2", "igual a Q1")
    svg.wire((510, p["lo"][1]), gl)
    svg.wire(sh, dl)
    svg.dot(xq, p["vs"][1])
    svg.wire(dh, (xq, 365))
    svg.terminal(xq, 362, "+Vbus")
    svg.wire(sl, (xq, 610))
    svg.ground(xq, 610)
    svg.wire(p["com"], (370, p["com"][1]), (370, 600))
    svg.ground(370, 600)
    svg.wire(p["vss"], (170, p["vss"][1]), (170, 600))
    svg.ground(170, 600)
    svg.terminal(p["hin"][0], p["hin"][1], "PWM alto", "end")
    svg.terminal(p["lin"][0], p["lin"][1], "PWM baixo", "end")
    svg.wire((xq, p["vs"][1]), (xq + 50, p["vs"][1]))
    svg.terminal(xq + 50, p["vs"][1], "carga")
    svg.text(
        10,
        640,
        "O comando segue a ligação típica do datasheet do driver; a simulação "
        "confere o snubber e o pico de partida.",
        "start",
        "pn",
    )
    if snubber:
        # ---- RCD turn-off snubber test: clamped inductive load as a current source
        x0 = 680
        svg.text(x0, 345, "Snubber RCD (ensaio de desligamento)", "start", "ttl")
        yv, ys, y0 = 390.0, 480.0, 640.0
        svg.src_v(x0 + 20, yv, y0, "VB", v.get("VB", ""), left=False)
        svg.ground(x0 + 20, y0)
        xs = x0 + 140
        svg.wire((x0 + 20, yv), (xs + 60, yv))
        svg.isource_v(xs, yv, ys, "IO", v.get("IO", ""), left=True, down=True)
        svg.dot(xs, yv)
        svg.diode_vert(xs + 60, yv, ys, "", up=True)
        svg.text(xs + 72, (yv + ys) / 2, "roda livre", "start", "pn")
        svg.wire((xs, ys), (xs + 150, ys))
        svg.dot(xs + 60, ys)
        svg.dot(xs, ys)
        gq, dq, sq = svg.switch_v(kind, xs - 8, 550, "SQ", "")
        svg.wire((xs, ys), dq)
        svg.wire(sq, (xs, y0))
        svg.ground(xs, y0)
        _gate(svg, gq, "desliga")
        xd = xs + 100
        svg.dot(xd, ys)
        svg.diode_vert(xd, ys, 550, "D2", parts.get("D2", ""), up=False, left=True)
        svg.res_v(xs + 150, ys, 550, "RS", v.get("RS", ""))
        svg.wire((xd, 550), (xs + 150, 550))
        svg.dot(xd + 25, 550)
        svg.cap_np_v(xd + 25, 550, y0, "CS", v.get("CS", ""))
        svg.ground(xd + 25, y0)
    return svg.render(title)


__all__ = ["ac_controller", "dcdc", "drive", "eng", "inverter", "isolated"]
