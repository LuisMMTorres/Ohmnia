"""Schematics of the non-linear op-amp circuits (DM-OPNL), the oscillators (DM-OSC) and the
instrumentation circuits (DM-INST).

Each function draws the circuit of the module netlist: the same nodes and the same element
names, so a label on the drawing is the element of the simulation (the analysis tab makes
it clickable). Topologies as in Sedra & Smith (*Microelectronic Circuits*, ch. 2, 4 and 18),
Pertence (*Amplificadores operacionais e filtros ativos*) and the TI NE555 data sheet
(SLFS022K, typical applications).
"""

from __future__ import annotations

from collections.abc import Mapping

from .canvas import Canvas, eng

Vals = Mapping[str, float]  # element name → value in SI units
Parts = Mapping[str, str]  # designator → part number


def _r(v: Vals, k: str) -> str:
    return eng(v[k], "ohm") if k in v else ""


def _c(v: Vals, k: str) -> str:
    return eng(v[k], "F") if k in v else ""


def _load(svg: Canvas, x_from: float, y: float, x: float, rl: float, node: str = "vo") -> None:
    """Output wire to the load RL and the output terminal."""
    svg.wire((x_from, y), (x + 50, y))
    svg.res_v(x, y, y + 90, "RL", eng(rl, "ohm"))
    svg.ground(x, y + 90)
    svg.dot(x, y)
    svg.terminal(x + 50, y, node)


def _vin(svg: Canvas, x: float, y_top: float, y_bot: float, name: str, value: str) -> None:
    svg.sine_v(x, y_top, y_bot, name, value)
    svg.ground(x, y_bot)


# ============================================================================ DM-OPNL
def opnl(
    config: str,
    title: str,
    v: Vals,
    parts: Parts,
    extra: Mapping[str, str],
) -> str:
    """``extra``: texts for the sources (Vin, Vref, Vcc) and levels."""
    u1 = parts.get("U1", "")
    svg = Canvas(720, 420)
    svg.title(title)
    rl = v.get("RL", 10e3)
    vin = extra.get("Vin", "")
    if config == "comparador" and "Rp" in v:  # open-collector comparator
        inv, non, out = svg.opamp(300, 200, "U1", u1, flip=True)
        svg.wire((80, non[1]), non)
        _vin(svg, 80, non[1], 330, "Vin", vin)
        svg.wire(inv, (250, inv[1]))
        svg.src_v(250, inv[1], 330, "Vref", extra.get("Vref", ""))
        svg.ground(250, 330)
        svg.note(310, 252, "saída em coletor aberto")
        svg.wire(out, (440, out[1]))
        svg.res_v(440, 90, 200, "Rp", _r(v, "Rp"))
        svg.terminal(440, 90, f"+Vcc {extra.get('Vcc', '')}".strip())
        _load(svg, 440, 200, 440, rl)
        return svg.render(title)
    if config == "comparador":
        inv, non, out = svg.opamp(300, 200, "U1", u1, flip=True)
        svg.wire((80, non[1]), non)
        _vin(svg, 80, non[1], 330, "Vin", vin)
        svg.wire(inv, (250, inv[1]))
        svg.src_v(250, inv[1], 330, "Vref", extra.get("Vref", ""))
        svg.ground(250, 330)
        _load(svg, out[0], out[1], 440, rl)
        return svg.render(title)
    if config == "schmitt_inversor":
        inv, non, out = svg.opamp(300, 200, "U1", u1)
        svg.wire((80, inv[1]), inv)
        _vin(svg, 80, inv[1], 330, "Vin", vin)
        svg.wire(non, (250, non[1]), (250, 280))
        svg.dot(250, 280)
        svg.resistor_h(250, 420, 280, "R1", _r(v, "R1"))
        svg.wire((420, 280), (420, out[1]))
        svg.res_v(250, 280, 340, "R2", _r(v, "R2"))
        svg.src_v(250, 340, 400, "Vref", extra.get("Vref", ""))
        svg.ground(250, 400)
        _load(svg, out[0], out[1], 500, rl)
        svg.dot(420, out[1])
        return svg.render(title)
    if config == "schmitt_nao_inversor":
        inv, non, out = svg.opamp(300, 200, "U1", u1, flip=True)
        svg.wire((80, non[1]), (130, non[1]))
        _vin(svg, 80, non[1], 330, "Vin", vin)
        svg.resistor_h(130, 240, non[1], "R1", _r(v, "R1"))
        svg.wire((240, non[1]), non)
        svg.dot(260, non[1])
        svg.wire((260, non[1]), (260, 100))
        svg.resistor_h(260, 420, 100, "R2", _r(v, "R2"))
        svg.wire((420, 100), (420, out[1]))
        svg.wire(inv, (250, inv[1]))
        svg.src_v(250, inv[1], 330, "Vref", extra.get("Vref", ""))
        svg.ground(250, 330)
        _load(svg, out[0], out[1], 500, rl)
        svg.dot(420, out[1])
        return svg.render(title)
    if config in ("retificador_meia", "retificador_onda"):
        full = config == "retificador_onda"
        inv, non, out = svg.opamp(300, 230, "U1", u1)
        y_in = inv[1]
        svg.wire((60, y_in), (130, y_in))
        _vin(svg, 60, y_in, 360, "Vin", vin)
        svg.resistor_h(130, 250, y_in, "R1", _r(v, "R1"))
        svg.wire((250, y_in), inv)
        svg.wire(non, (285, non[1]), (285, 262))
        svg.ground(285, 262)
        # n column (inverting input) up to the two feedback rows
        svg.wire((260, y_in), (260, 90))
        svg.dot(260, y_in)
        svg.dot(260, 150)
        # D1 between n and the op-amp output a; D2 between a and the stage output
        svg.diode_h(260, 400, 150, "D1", parts.get("D1", ""), right=not full)
        svg.wire(out, (400, out[1]), (400, 150))
        svg.dot(400, out[1])
        svg.diode_h(400, 520, out[1], "D2", parts.get("D2", ""), right=not full)
        svg.resistor_h(260, 520, 90, "R2", _r(v, "R2"))
        svg.wire((520, 90), (520, out[1]))
        svg.dot(520, out[1])
        if not full:
            _load(svg, 520, out[1], 600, rl)
            return svg.render(title)
        svg.width = 980
        svg.height = 470
        svg.text(526, 205, "h")
        # summing amplifier: vo = −R5 (vin/R3 + h/R4)
        inv2, non2, out2 = svg.opamp(760, 245, "U2", parts.get("U2", ""))
        svg.resistor_h(520, 700, out[1], "R4", _r(v, "R4"))
        svg.wire((700, out[1]), (720, out[1]), (720, inv2[1]), inv2)
        svg.dot(720, inv2[1])
        svg.wire(non2, (745, non2[1]), (745, 277))
        svg.ground(745, 277)
        svg.wire((60, y_in), (30, y_in), (30, 420), (330, 420))
        svg.dot(60, y_in)
        svg.resistor_h(330, 560, 420, "R3", _r(v, "R3"))
        svg.wire((560, 420), (720, 420), (720, inv2[1]))
        svg.wire((720, out[1]), (720, 130))
        svg.resistor_h(720, 860, 130, "R5", _r(v, "R5"))
        svg.wire((860, 130), (860, out2[1]))
        svg.dot(860, out2[1])
        _load(svg, out2[0], out2[1], 880, rl)
        return svg.render(title)
    if config == "logaritmico":
        inv, non, out = svg.opamp(300, 230, "U1", u1)
        y_in = inv[1]
        svg.wire((80, y_in), (130, y_in))
        svg.src_v(80, y_in, 340, "Vin", extra.get("Vin_dc", ""))
        svg.ground(80, 340)
        svg.resistor_h(130, 250, y_in, "R1", _r(v, "R1"))
        svg.wire((250, y_in), inv)
        svg.wire(non, (285, non[1]), (285, 262))
        svg.ground(285, 262)
        b, c, e = svg.npn_h(340, 110, "Q1", parts.get("Q1", ""))
        svg.wire((260, y_in), (260, c[1]), c)
        svg.dot(260, y_in)
        svg.ground(*b)
        svg.wire(e, (420, e[1]), (420, out[1]))
        svg.dot(420, out[1])
        svg.wire(out, (420, out[1]))
        svg.text(170, 300, "transdiodo: coletor no terra virtual, base no terra")
        svg.wire((420, out[1]), (540, out[1]))
        svg.terminal(540, out[1], "vo")
        return svg.render(title)
    # limiter: inverting amplifier with two Zener + diode branches in parallel with R2
    inv, non, out = svg.opamp(300, 290, "U1", u1)
    y_in = inv[1]
    svg.wire((60, y_in), (130, y_in))
    _vin(svg, 60, y_in, 400, "Vin", vin)
    svg.resistor_h(130, 250, y_in, "R1", _r(v, "R1"))
    svg.wire((250, y_in), inv)
    svg.wire(non, (285, non[1]), (285, 322))
    svg.ground(285, 322)
    xn, xo = 220, 520
    svg.wire((xn, y_in), (xn, 60))
    svg.dot(xn, y_in)
    rows = (200, 130, 60)
    svg.resistor_h(xn, xo, rows[0], "R2", _r(v, "R2"))
    # o → DZ1 (cathode at o) → m1 → D1 (cathode at n): conducts from o to n
    svg.diode_h(xn, 370, rows[1], "D1", parts.get("D1", ""), right=False)
    svg.zener_h(370, xo, rows[1], "DZ1", parts.get("DZ1", ""), right=True)
    # n → DZ2 (cathode at n) → m2 → D2 (cathode at o): conducts from n to o
    svg.zener_h(xn, 370, rows[2], "DZ2", parts.get("DZ2", parts.get("DZ1", "")), right=False)
    svg.diode_h(370, xo, rows[2], "D2", parts.get("D2", ""), right=True)
    svg.wire((xo, 60), (xo, out[1]))
    for y in rows[:2]:
        svg.dot(xn, y)
        svg.dot(xo, y)
    svg.dot(xo, out[1])
    svg.wire(out, (xo, out[1]))
    _load(svg, xo, out[1], 600, rl)
    return svg.render(title)


# ============================================================================ DM-OSC
def _diode_pair(svg: Canvas, x1: float, x2: float, y1: float, y2: float, parts: Parts) -> None:
    """D1 (x1 → x2) and D2 (x2 → x1) in antiparallel on two rows: amplitude limiter."""
    svg.diode_h(x1, x2, y1, "D1", parts.get("D1", ""), right=True)
    svg.diode_h(x1, x2, y2, "D2", parts.get("D2", ""), right=False)


def osc(config: str, title: str, v: Vals, parts: Parts, extra: Mapping[str, str]) -> str:
    u1 = parts.get("U1", "")
    rl = v.get("RL", 10e3)
    if config == "wien":
        svg = Canvas(760, 500)
        svg.title(title)
        inv, non, out = svg.opamp(400, 250, "U1", u1, flip=True)
        xo = 580
        svg.wire(out, (xo, out[1]))
        svg.dot(xo, out[1])
        # positive feedback: series R1–C1 from the output, parallel R2 ∥ C2 to ground
        svg.wire((xo, out[1]), (xo, 70))
        svg.resistor_h(420, xo, 70, "R1", _r(v, "R1"))
        svg.cap_h(290, 420, 70, "C1", _c(v, "C1"))
        svg.wire((290, 70), (290, non[1]), non)
        svg.dot(290, 130)
        svg.wire((290, 130), (140, 130))
        svg.dot(210, 130)
        svg.res_v(210, 130, 210, "R2", _r(v, "R2"))
        svg.ground(210, 210)
        svg.cap_np_v(140, 130, 210, "C2", _c(v, "C2"))
        svg.ground(140, 210)
        # negative feedback: Rg to ground, R3 + R4 with D1/D2 across R4
        svg.wire(inv, (360, inv[1]), (360, 340))
        svg.dot(360, 340)
        svg.res_v(360, 340, 430, "Rg", _r(v, "Rg"), left=True)
        svg.ground(360, 430)
        svg.resistor_h(360, 460, 340, "R3", _r(v, "R3"))
        svg.resistor_h(460, xo, 340, "R4", _r(v, "R4"))
        svg.wire((460, 340), (460, 450))
        svg.dot(460, 340)
        _diode_pair(svg, 460, xo, 395, 450, parts)
        svg.wire((xo, out[1]), (xo, 450))
        svg.dot(xo, 340)
        svg.dot(xo, 395)
        svg.dot(460, 395)
        _load(svg, xo, out[1], 650, rl)
        return svg.render(title)
    if config == "deslocamento_fase":
        svg = Canvas(800, 420)
        svg.title(title)
        inv, non, out = svg.opamp(500, 290, "U1", u1)
        xo = 680
        svg.wire(out, (xo, out[1]))
        svg.dot(xo, out[1])
        # three-section RC ladder fed from the output (top wire, back to the left)
        y = inv[1]
        svg.wire((xo, out[1]), (xo, 35), (40, 35), (40, y))
        xs = [40, 140, 240, 340]
        for k in range(3):
            svg.cap_h(xs[k], xs[k + 1], y, f"C{k + 1}", _c(v, f"C{k + 1}"))
        for k in range(2):
            svg.dot(xs[k + 1], y)
            svg.res_v(xs[k + 1], y, y + 80, f"R{k + 1}", _r(v, f"R{k + 1}"))
            svg.ground(xs[k + 1], y + 80)
        svg.resistor_h(340, 450, y, "R3", _r(v, "R3"))
        svg.wire((450, y), inv)
        svg.wire(non, (480, non[1]), (480, 330))
        svg.ground(480, 330)
        # gain: R5 + R6 (D1/D2 across R6) from n to the output
        svg.dot(460, y)
        svg.wire((460, y), (460, 180))
        svg.resistor_h(460, 560, 180, "R5", _r(v, "R5"))
        svg.dot(460, 180)
        svg.resistor_h(560, xo, 180, "R6", _r(v, "R6"))
        svg.wire((560, 180), (560, 75))
        svg.dot(560, 180)
        _diode_pair(svg, 560, xo, 127, 75, parts)
        for yy in (127, 180):
            svg.dot(xo, yy)
        svg.dot(560, 127)
        _load(svg, xo, out[1], 740, rl)
        svg.width = 820
        return svg.render(title)
    if config == "astavel_ampop":
        svg = Canvas(640, 420)
        svg.title(title)
        inv, non, out = svg.opamp(300, 200, "U1", u1)
        xo = 440
        svg.wire(out, (xo, out[1]))
        svg.dot(xo, out[1])
        svg.wire(inv, (240, inv[1]), (240, 90))
        svg.dot(240, inv[1])
        svg.resistor_h(240, xo, 90, "Rt", _r(v, "Rt"))
        svg.wire((xo, 90), (xo, 300))
        svg.wire((240, inv[1]), (160, inv[1]))
        svg.cap_np_v(160, inv[1], 270, "Ct", _c(v, "Ct"), left=True)
        svg.ground(160, 270)
        svg.wire(non, (270, non[1]), (270, 300))
        svg.dot(270, 300)
        svg.resistor_h(270, xo, 300, "R1", _r(v, "R1"))
        svg.res_v(270, 300, 380, "R2", _r(v, "R2"), left=True)
        svg.ground(270, 380)
        _load(svg, xo, out[1], 530, rl)
        return svg.render(title)
    if config in ("ne555_astavel", "ne555_monoestavel"):
        mono = config == "ne555_monoestavel"
        svg = Canvas(680, 480)
        svg.title(title)
        y_rail = 60
        svg.src_v(50, y_rail, 200, "Vcc", extra.get("Vcc", ""))
        svg.ground(50, 200)
        pins = {
            "vcc": ("t", 40, "8 VCC"),
            "rst": ("t", 110, "4 RST"),
            "dis": ("l", 40, "7 DIS"),
            "thr": ("l", 90, "6 THR"),
            "trg": ("l", 190, "2 TRIG"),
            "out": ("r", 90, "3 OUT"),
            "gnd": ("b", 40, "1 GND"),
            "cv": ("b", 110, "5 CV"),
        }
        p = svg.chip(330, 120, 150, 220, "U1", u1, pins)
        svg.wire((50, y_rail), (p["rst"][0], y_rail))
        svg.wire(p["vcc"], (p["vcc"][0], y_rail))
        svg.wire(p["rst"], (p["rst"][0], y_rail))
        svg.dot(p["vcc"][0], y_rail)
        svg.ground(*p["gnd"])
        svg.note(p["cv"][0] + 6, p["cv"][1] + 4, "aberto")
        xr = 230
        svg.dot(xr, y_rail)
        if not mono:
            # RA from Vcc to DIS, RB from DIS to THR = TRIG, Ct to ground
            svg.res_v(xr, y_rail, p["dis"][1], "RA", _r(v, "RA"), left=True)
            svg.wire((xr, p["dis"][1]), p["dis"])
            svg.dot(xr, p["dis"][1])
            svg.res_v(xr, p["dis"][1], p["thr"][1], "RB", _r(v, "RB"), left=True)
            svg.wire((xr, p["thr"][1]), p["thr"])
            svg.dot(xr, p["thr"][1])
            svg.wire((xr, p["thr"][1]), (xr, 400))
            svg.wire(p["trg"], (xr, p["trg"][1]))
            svg.dot(xr, p["trg"][1])
            svg.cap_np_v(xr, 330, 400, "Ct", _c(v, "Ct"), left=True)
            svg.ground(xr, 400)
        else:
            # RA from Vcc to THR = DIS, Ct to ground, trigger pulse on TRIG
            svg.res_v(xr, y_rail, p["dis"][1], "RA", _r(v, "RA"), left=True)
            svg.wire((xr, p["dis"][1]), p["dis"])
            svg.dot(xr, p["dis"][1])
            svg.wire((xr, p["dis"][1]), (xr, p["thr"][1]), p["thr"])
            svg.dot(xr, p["thr"][1])
            svg.cap_np_v(xr, p["thr"][1], 280, "Ct", _c(v, "Ct"), left=True)
            svg.ground(xr, 280)
            svg.wire(p["trg"], (110, p["trg"][1]))
            svg.pulse_v(110, p["trg"][1], 420, "Vtr", extra.get("trigger", "disparo"))
            svg.ground(110, 420)
        _load(svg, p["out"][0], p["out"][1], 560, rl, "vo")
        return svg.render(title)
    # astable multivibrator with two BJTs (cross-coupled through C1 and C2)
    svg = Canvas(660, 440)
    svg.title(title)
    y_rail = 70
    svg.src_v(40, y_rail, 220, "Vcc", extra.get("Vcc", ""))
    svg.ground(40, 220)
    xc1, xb2, xb1, xc2 = 130, 250, 410, 530
    svg.wire((40, y_rail), (xc2, y_rail))
    for x, name in ((xc1, "RC1"), (xb2, "RB2"), (xb1, "RB1"), (xc2, "RC2")):
        if x != xc2:
            svg.dot(x, y_rail)
        svg.res_v(x, y_rail, 180, name, _r(v, name), left=x in (xc1, xb2))
    yc = 210
    svg.wire((xc1, 180), (xc1, 330 - 26))
    svg.wire((xc2, 180), (xc2, 330 - 26))
    svg.wire((xb2, 180), (xb2, 250))
    svg.wire((xb1, 180), (xb1, 250))
    svg.cap_h(xc1, xb2, yc, "C1", _c(v, "C1"))
    svg.cap_h(xb1, xc2, yc, "C2", _c(v, "C2"))
    for x in (xc1, xb2, xb1, xc2):
        svg.dot(x, yc)
    # Q1 (left) has its base at the right; Q2 (right) its base at the left
    b1, _c1, e1 = svg.bjt(xc1 + 8, 330, "Q1", parts.get("Q1", ""), mirror=True)
    b2, _c2, e2 = svg.bjt(xc2 - 8, 330, "Q2", parts.get("Q2", ""))
    svg.wire((xb1, 250), (xb1, 270), (b1[0] + 40, 310), (b1[0] + 40, b1[1]), b1)
    svg.wire((xb2, 250), (xb2, 270), (b2[0] - 40, 310), (b2[0] - 40, b2[1]), b2)
    svg.ground(*e1)
    svg.ground(*e2)
    svg.terminal(xc2 + 60, yc, "vo")
    svg.wire((xc2, yc), (xc2 + 60, yc))
    return svg.render(title)


# ============================================================================ DM-INST
def _ni_amp(
    svg: Canvas, x: float, y: float, p: str, out_node: str, v: Vals, part: str, xo: float
) -> tuple[float, float]:
    """Non-inverting amplifier U<p> with R<p>1 to ground and R<p>2 as feedback.

    The signal comes to the + input at (x, y − 15); returns the output point (xo, y)."""
    inv, _non, out = svg.opamp(x, y, f"U{p}", part, flip=True)
    svg.wire(inv, (x - 30, inv[1]), (x - 30, y + 70))
    svg.dot(x - 30, y + 70)
    svg.res_v(x - 30, y + 70, y + 140, f"R{p}1", _r(v, f"R{p}1"), left=True)
    svg.ground(x - 30, y + 140)
    svg.resistor_h(x - 30, xo, y + 70, f"R{p}2", _r(v, f"R{p}2"))
    svg.wire((xo, y + 70), (xo, y), out)
    svg.dot(xo, y)
    svg.terminal(xo + 40, y, out_node)
    svg.wire((xo, y), (xo + 40, y))
    return xo, y


def _follower_divider(
    svg: Canvas, x_in: float, y: float, p: str, out_node: str, v: Vals, part: str
) -> None:
    """Divider R<p>a/R<p>b into a voltage follower U<p>; input at (x_in, y_top)."""
    xd = x_in + 120
    svg.res_v(xd, y - 120, y, f"R{p}a", _r(v, f"R{p}a"), left=True)
    svg.wire((x_in, y - 120), (xd, y - 120))
    svg.dot(xd, y)
    svg.res_v(xd, y, y + 90, f"R{p}b", _r(v, f"R{p}b"), left=True)
    svg.ground(xd, y + 90)
    inv, non, out = svg.opamp(xd + 100, y - 15, f"U{p}", part, flip=True)
    svg.wire((xd, y), non)
    svg.wire(inv, (xd + 80, inv[1]), (xd + 80, y + 50), (out[0] + 30, y + 50))
    svg.wire((out[0] + 30, y + 50), (out[0] + 30, out[1]))
    svg.wire(out, (out[0] + 70, out[1]))
    svg.dot(out[0] + 30, out[1])
    svg.terminal(out[0] + 70, out[1], out_node)


def inst(config: str, title: str, v: Vals, parts: Parts, extra: Mapping[str, str]) -> str:
    u = [parts.get(f"U{k}", "") for k in (1, 2, 3)]
    if config in ("voltimetro", "amperimetro", "potencia"):
        two = config == "potencia"
        svg = Canvas(680, 690 if two else 380)
        svg.title(title)
        if config in ("voltimetro", "potencia"):
            name = "Vbus" if two else "Vsig"
            out_node = "ov" if two else "vo"
            svg.ground(60, 300)
            if "R1a" in v:
                svg.src_v(60, 80, 300, name, extra.get(name, ""))
                _follower_divider(svg, 60, 200, "1", out_node, v, u[0])
            else:
                svg.src_v(60, 185, 300, name, extra.get(name, ""))
                svg.wire((60, 185), (300, 185))
                _ni_amp(svg, 300, 200, "1", out_node, v, u[0], 470)
        if config in ("amperimetro", "potencia"):
            p = "2" if two else "1"
            yb = 480 if two else 185  # shunt node = + input of the amplifier
            svg.isource_v(60, yb, yb + 110, "Isig", extra.get("Isig", ""))
            svg.ground(60, yb + 110)
            svg.wire((60, yb), (300, yb))
            svg.dot(200, yb)
            svg.res_v(200, yb, yb + 110, f"R{p}sh", _r(v, f"R{p}sh"))
            svg.ground(200, yb + 110)
            _ni_amp(svg, 300, yb + 15, p, "oi" if two else "vo", v, u[1] if two else u[0], 470)
        return svg.render(title)
    if config == "transmissor_4_20":
        svg = Canvas(640, 470)
        svg.title(title)
        inv, non, out = svg.opamp(320, 200, "U1", u[0], flip=True)
        yp = non[1]
        svg.src_v(60, yp, 330, "Vsig", extra.get("Vsig", ""))
        svg.ground(60, 330)
        svg.resistor_h(60, 220, yp, "R1", _r(v, "R1"))
        svg.wire((220, yp), non)
        svg.dot(240, yp)
        svg.res_v(240, 80, yp, "R2", _r(v, "R2"), left=True)
        svg.wire((240, 80), (160, 80))
        svg.src_v(160, 80, 140, "Vref", extra.get("Vref", ""))
        svg.ground(160, 140)
        svg.wire((240, yp), (240, 245))
        svg.res_v(240, 245, 320, "R3", _r(v, "R3"), left=True)
        svg.ground(240, 320)
        # current loop: output → RL → ammeter → n (inverting input) → Rs → ground
        xn = 290
        svg.wire(inv, (xn, inv[1]), (xn, 380))
        svg.dot(xn, 380)
        svg.res_v(xn, 380, 440, "Rs", _r(v, "Rs"), left=True)
        svg.ground(xn, 440)
        xl = 470
        svg.wire(out, (xl, out[1]))
        svg.res_v(xl, out[1], 300, "RL", _r(v, "RL"))
        svg.ammeter_v(xl, 300, 360, "i (4 a 20 mA)")
        svg.wire((xl, 360), (xl, 380), (xn, 380))
        svg.note(330, 445, "malha de corrente: RL é a carga da malha")
        return svg.render(title)
    if config in ("receptor_4_20", "condicionamento"):
        svg = Canvas(640, 420)
        svg.title(title)
        inv, non, out = svg.opamp(330, 200, "U1", u[0])
        xo = 480
        # inverting side: Vref → R1 → n, R2 feedback
        svg.src_v(80, inv[1], 270, "Vref", extra.get("Vref", ""))
        svg.ground(80, 270)
        svg.wire((80, inv[1]), (130, inv[1]))
        svg.resistor_h(130, 270, inv[1], "R1", _r(v, "R1"))
        svg.wire((270, inv[1]), inv)
        svg.dot(280, inv[1])
        svg.wire((280, inv[1]), (280, 100))
        svg.resistor_h(280, xo, 100, "R2", _r(v, "R2"))
        svg.wire((xo, 100), (xo, out[1]))
        svg.wire(out, (xo + 60, out[1]))
        svg.dot(xo, out[1])
        svg.terminal(xo + 60, out[1], "vo")
        # non-inverting side: signal → R3 → p, R4 to ground
        ys = non[1] + 40
        if config == "receptor_4_20":
            svg.isource_v(110, ys, 390, "Isig", extra.get("Isig", ""), left=True)
            svg.ground(110, 390)
            svg.dot(180, ys)
            svg.res_v(180, ys, 390, "Rrx", _r(v, "Rrx"))
            svg.ground(180, 390)
            x_from = 110
        else:
            svg.src_v(150, ys, 390, "Vsig", extra.get("Vsig", ""))
            svg.ground(150, 390)
            x_from = 150
        svg.wire((x_from, ys), (230, ys))
        svg.resistor_h(230, 300, ys, "R3", _r(v, "R3"))
        svg.wire((300, ys), (300, non[1]), non)
        svg.dot(300, ys)
        svg.res_v(300, ys, 370, "R4", _r(v, "R4"))
        svg.ground(300, 370)
        return svg.render(title)
    # Wheatstone bridge (one active arm) + three-op-amp instrumentation amplifier
    svg = Canvas(880, 520)
    svg.title(title)
    svg.src_v(50, 60, 250, "Vexc", extra.get("Vexc", ""))
    svg.ground(50, 250)
    xa, xb = 160, 260  # sensor arm (b1) and reference arm (b2)
    svg.wire((50, 60), (xb, 60))
    svg.dot(xa, 60)
    svg.res_v(xa, 60, 160, "Ra", _r(v, "Ra"))
    svg.res_v(xa, 160, 260, "Rsens", _r(v, "Rsens"))
    svg.text(xa + 11, 233, "R0(1 + x)", "start", "pn")
    svg.ground(xa, 260)
    svg.res_v(xb, 60, 160, "Rb", _r(v, "Rb"))
    svg.res_v(xb, 160, 260, "Rc", _r(v, "Rc"))
    svg.ground(xb, 260)
    for x in (xa, xb):
        svg.dot(x, 160)
    # U2 (top) buffers b2, U1 (bottom) buffers b1; RG between the two inverting inputs
    inv2, non2, o2 = svg.opamp(420, 120, "U2", u[1], flip=True)
    inv1, non1, o1 = svg.opamp(420, 380, "U1", u[0])
    svg.wire((xb, 160), (330, 160), (330, non2[1]), non2)
    svg.wire((xa, 160), (110, 160), (110, non1[1]), non1)
    xi, xo = 385, 510
    svg.wire(inv2, (xi, inv2[1]), (xi, 200))
    svg.wire(inv1, (xi, inv1[1]), (xi, 300))
    svg.resistor_h(xi, xo, 200, "Rf2", _r(v, "Rf2"))
    svg.resistor_h(xi, xo, 300, "Rf1", _r(v, "Rf1"))
    svg.res_v(xi, 200, 300, "RG", _r(v, "RG"), left=True)
    svg.dot(xi, 200)
    svg.dot(xi, 300)
    svg.wire(o2, (xo, o2[1]), (xo, 200))
    svg.wire(o1, (xo, o1[1]), (xo, 300))
    svg.dot(xo, 200)
    svg.dot(xo, 300)
    # difference amplifier U3: vo = v(o1) − v(o2)
    inv3, non3, o3 = svg.opamp(660, 250, "U3", u[2])
    svg.resistor_h(xo, 620, 200, "R3", _r(v, "R3"))
    svg.wire((620, 200), (620, inv3[1]), inv3)
    svg.dot(620, 200)
    svg.wire((620, 200), (620, 140))
    svg.resistor_h(620, 760, 140, "R4", _r(v, "R4"))
    svg.wire((760, 140), (760, o3[1]))
    svg.resistor_h(xo, 620, 300, "R5", _r(v, "R5"))
    svg.wire((620, 300), (620, non3[1]), non3)
    svg.dot(620, 300)
    svg.res_v(620, 300, 380, "R6", _r(v, "R6"), left=True)
    svg.ground(620, 380)
    svg.wire(o3, (820, o3[1]))
    svg.dot(760, o3[1])
    svg.terminal(820, o3[1], "vo")
    svg.text(104, 300, "b1", "end", "pn")
    svg.text(330, 150, "b2", "start", "pn")
    return svg.render(title)
