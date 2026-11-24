"""Drawing of the DM-RETC1 firing circuit (synchronised ramp, LM393, BC337, MOC3021).

Drawn as a second panel below the power circuit; the two SVGs are nested in one drawing so the
labels stay clickable in the design page (each label matches a netlist element).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .schematic import Svg, _fmt

PANEL_W, PANEL_H = 1080, 440


def _cap(svg: Svg, x: float, y1: float, y2: float, label: str, value: str) -> None:
    """Non-polarised capacitor, vertical."""
    ym = (y1 + y2) / 2
    svg.line(x, y1, x, ym - 4)
    svg.line(x, ym + 4, x, y2)
    svg.line(x - 12, ym - 4, x + 12, ym - 4)
    svg.line(x - 12, ym + 4, x + 12, ym + 4)
    svg.text(x + 16, ym - 3, label)
    if value:
        svg.text(x + 16, ym + 10, value, "start", "pn")


def _pot(svg: Svg, x: float, y1: float, y2: float, label: str, value: str) -> float:
    """Potentiometer between y1 and y2; returns the y of the wiper (arrow from the right)."""
    svg.resistor_v(x, y1, y2, label, value)
    ym = (y1 + y2) / 2
    svg.line(x + 22, ym, x + 7, ym)
    svg.parts.append(f'<path d="M{x + 7},{ym} l6,-4 l0,8 Z"/>')
    return ym


def _coupler(svg: Svg, x: float, y: float, label: str, part: str, scr: str) -> None:
    """Optocoupler box: LED between (x, y) and (x + 70, y), output drawn as a TRIAC mark."""
    svg.parts.append(f'<rect class="o" x="{x}" y="{y - 22}" width="70" height="44"/>')
    svg.line(x, y, x + 25, y)
    svg.line(x + 45, y, x + 70, y)
    svg.parts.append(f'<path d="M{x + 27},{y - 7} L{x + 27},{y + 7} L{x + 39},{y} Z"/>')
    svg.line(x + 40, y - 7, x + 40, y + 7)
    svg.line(x + 33, y + 10, x + 38, y + 16)
    svg.line(x + 37, y + 10, x + 42, y + 16)
    svg.text(x + 35, y - 27, label, "middle")
    svg.text(x + 35, y + 34, part, "middle", "pn")
    svg.text(x + 35, y + 47, f"→ {scr}", "middle")


def panel(
    topology: str,
    summary: Mapping[str, tuple[float, str]],
    parts: Mapping[str, str],
    scrs: list[str],
) -> str:
    n = len(scrs)
    svg = Svg(PANEL_W, PANEL_H)
    svg.title(
        "Circuito de disparo: rampa sincronizada com a rede, comparador e optoacopladores "
        f"(α = {summary['alpha_fire'][0]:.1f}°)".replace(".", ",")
    )

    def v(key: str, unit: str) -> str:
        if unit == "°":
            return f"{summary[key][0]:.1f}°".replace(".", ",") if key in summary else ""
        return _fmt(summary, key, unit)

    vcc_y = 50.0
    svg.wire((190, vcc_y), (680 + 90 * n, vcc_y))
    svg.text(185, vcc_y + 4, f"+VCC = {v('fd_Vcc', 'V')}", "end")

    # synchronism: transformer, diode bridge, divider
    svg.transformer(20, 230, 300)
    svg.text(33, 222, "TS1", "middle")
    svg.text(10, 318, f"rede → {v('fd_Vsync', 'V')} (sincronismo)")
    svg.wire((46, 230), (60, 230), (60, 245), (75, 245))
    svg.wire((46, 300), (60, 300), (60, 285), (75, 285))
    svg.box(75, 228, 75, 74, "DS1–DS4", parts.get("DS1–DS4", ""))
    svg.wire((150, 245), (160, 245))
    svg.resistor_h(160, 230, 245, "R1", v("fd_R1", "Ω"))
    svg.dot(230, 245)
    svg.resistor_v(230, 245, 330, "R2", v("fd_R2", "Ω"))
    svg.ground(230, 330)
    svg.wire((150, 285), (165, 285), (165, 330))
    svg.ground(165, 330)

    # zero-crossing threshold and comparator U1A
    svg.resistor_v(200, vcc_y, 150, "R3", v("fd_R3", "Ω"))
    svg.dot(200, 150)
    svg.resistor_v(200, 150, 205, "R4", v("fd_R4", "Ω"))
    svg.ground(200, 205)
    inv, non, out = svg.opamp(260, 175, "U1A", parts.get("U1", ""))
    svg.wire((200, 150), (245, 150), (245, inv[1]), inv)
    svg.wire((230, 245), (250, 245), (250, non[1]), non)
    svg.text(262, 120, f"Vth = {v('fd_Vth', 'V')}")

    # ramp: Rd, R5, C1
    svg.resistor_h(out[0], 390, out[1], "Rd", v("fd_Rd", "Ω"))
    svg.resistor_v(400, vcc_y, out[1], "R5", v("fd_R5", "Ω"))
    svg.wire((390, out[1]), (400, out[1]))
    svg.dot(400, out[1])
    _cap(svg, 400, out[1], 265, "C1", v("fd_C1", "F"))
    svg.ground(400, 265)
    svg.text(330, 300, f"rampa: {v('fd_V0', 'V')} → {v('fd_Vpk', 'V')}")

    # control potentiometer and comparator U1B
    wiper = _pot(svg, 450, vcc_y, 150, "RV1", v("fd_RV1", "Ω"))
    svg.ground(450, 150)
    inv2, non2, out2 = svg.opamp(500, 190, "U1B", parts.get("U1", ""))
    svg.wire((472, wiper), (485, wiper), (485, inv2[1]), inv2)
    svg.wire((400, out[1]), (420, out[1]), (420, non2[1]), non2)
    svg.text(455, 250, f"Vc = {v('fd_Vctrl', 'V')} ({v('fd_x', '%')} do curso)")

    # pull-up, transistor, LED string
    svg.resistor_v(580, vcc_y, out2[1], "R7", v("fd_R7", "Ω"))
    svg.wire(out2, (580, out2[1]))
    svg.dot(580, out2[1])
    b, c, e = svg.bjt(625, out2[1], "Q1", parts.get("Q1", ""))
    svg.wire((580, out2[1]), b)
    svg.ground(e[0], e[1])
    svg.resistor_v(660, vcc_y, 110, "RLED", v("fd_RLED", "Ω"))
    x = 680.0
    svg.wire((660, 110), (x, 110))
    moc_part = next((p for d, p in parts.items() if d.startswith("U") and d != "U1"), "")
    step = 90.0
    for i, scr in enumerate(scrs):
        _coupler(svg, x, 110, f"U{i + 2}", moc_part if i == 0 else "", scr)
        x2 = x + 70
        if i < n - 1:
            svg.wire((x2, 110), (x2 + step - 70, 110))
        x = x2 + step - 70
    x_end = x - step + 70
    svg.wire((x_end, 110), (x_end + 10, 110), (x_end + 10, 140), (c[0], 140), c)
    svg.text(700, 172, f"I_F nos LEDs = {v('fd_IF', 'A')}")

    # gate network (drawn for T1; the same for each SCR)
    y = 370.0
    svg.text(560, 318, "Ligação de porta de cada tiristor (desenhada para T1):")
    svg.terminal(565, y, f"anodo de {scrs[0]}", "end")
    svg.parts.append(f'<rect class="o" x="575" y="{y - 16}" width="60" height="32"/>')
    svg.text(605, y + 4, "saída U2", "middle")
    svg.line(568, y, 575, y)
    dg = next((d for d in parts if d.startswith("DG")), "")
    svg.device_right(635, 705, y, "diode", "DG1", parts.get(dg, ""))
    svg.resistor_h(705, 785, y, "RG1", v("fd_RG", "Ω"))
    svg.line(785, y, 800, y)
    svg.dot(800, y)
    svg.terminal(812, y, f"porta de {scrs[0]}")
    svg.resistor_v(800, y, y + 45, "RGK1", v("fd_RGK", "Ω"))
    svg.terminal(800, y + 48, f"catodo de {scrs[0]}")
    pairs = ", ".join(f"U{i + 2}/DG{i + 1}/RG{i + 1}/RGK{i + 1} → {t}" for i, t in enumerate(scrs))
    svg.text(10, 350, pairs if n > 1 else "")
    svg.text(
        10,
        366,
        f"Faixa de α do circuito: {v('fd_alpha_lo', '°')} a {v('fd_alpha_hi', '°')}; "
        f"corrente de porta garantida a partir de {v('fd_alpha_gate', '°')}.",
    )
    return svg.render("Circuito de disparo")


def combine(power: str, firing_panel: str) -> str:
    """Power circuit on top, firing circuit below, as one SVG."""

    def size(s: str) -> tuple[float, float]:
        m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', s)
        assert m is not None
        return float(m.group(1)), float(m.group(2))

    w1, h1 = size(power)
    w2, h2 = size(firing_panel)
    w, h = max(w1, w2), h1 + h2
    inner2 = firing_panel.replace("<svg ", f'<svg x="0" y="{h1:g}" ', 1)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" width="{w:g}" '
        f'height="{h:g}" role="img" aria-label="Retificador e circuito de disparo">'
        f"{power}{inner2}</svg>"
    )
