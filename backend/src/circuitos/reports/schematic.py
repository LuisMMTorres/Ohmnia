"""Schematics by template (SVG) for the rectifier modules.

Each topology has a fixed drawing; the designators, chosen part numbers and computed values are
written on it. Devices are drawn vertical with the anode at the bottom (current flows up to the
positive rail P) unless stated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from html import escape

from circuitos.core.units import Q_, format_eng

STROKE = "#1f2937"
ACCENT = "#2563eb"


@dataclass
class Svg:
    width: int
    height: int
    parts: list[str] = field(default_factory=list)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')

    def wire(self, *pts: tuple[float, float]) -> None:
        d = " ".join(f"{x},{y}" for x, y in pts)
        self.parts.append(f'<polyline points="{d}" fill="none"/>')

    def dot(self, x: float, y: float) -> None:
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="2.6" fill="{STROKE}"/>')

    def text(self, x: float, y: float, s: str, anchor: str = "start", cls: str = "lbl") -> None:
        self.parts.append(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{escape(s)}</text>'
        )

    def render(self, title: str) -> str:
        style = (
            f"line,polyline,path,circle.o,rect.o{{stroke:{STROKE};stroke-width:1.6;fill:none}}"
            f".lbl{{font:11px sans-serif;fill:{STROKE}}}.pn{{font:10px sans-serif;fill:{ACCENT}}}"
            f".ttl{{font:bold 12px sans-serif;fill:{STROKE}}}"
        )
        body = "\n".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" role="img" aria-label="{escape(title)}">'
            f'<style>{style}</style><g stroke="{STROKE}" stroke-width="1.6" fill="none">'
            f"{body}</g></svg>"
        )

    # ---------------------------------------------------------------- symbols
    def device_up(
        self,
        x: float,
        y_bot: float,
        y_top: float,
        kind: str,
        label: str,
        part: str = "",
        left: bool = False,
    ) -> None:
        """Diode or SCR between (x, y_bot) anode and (x, y_top) cathode, conducting upwards."""
        ym = (y_bot + y_top) / 2
        self.line(x, y_bot, x, ym + 8)
        self.line(x, ym - 8, x, y_top)
        self.parts.append(
            f'<path d="M{x - 8},{ym + 8} L{x + 8},{ym + 8} L{x},{ym - 6} Z" fill="none"/>'
        )
        self.line(x - 8, ym - 7, x + 8, ym - 7)
        if kind == "scr":
            self.line(x + 4, ym - 2, x + 14, ym + 8)
        tx = x - 12 if left else x + 14
        anchor = "end" if left else "start"
        self.text(tx, ym - 2, label, anchor)
        if part:
            self.text(tx, ym + 11, part, anchor, "pn")

    def device_right(
        self, x1: float, x2: float, y: float, kind: str, label: str, part: str = ""
    ) -> None:
        xm = (x1 + x2) / 2
        self.line(x1, y, xm - 8, y)
        self.line(xm + 8, y, x2, y)
        self.parts.append(f'<path d="M{xm - 8},{y - 8} L{xm - 8},{y + 8} L{xm + 6},{y} Z"/>')
        self.line(xm + 7, y - 8, xm + 7, y + 8)
        if kind == "scr":
            self.line(xm + 2, y + 4, xm - 8, y + 14)
        self.text(xm, y - 13, label, "middle")
        if part:
            self.text(xm, y + 24, part, "middle", "pn")

    def resistor_v(self, x: float, y1: float, y2: float, label: str, value: str = "") -> None:
        ym = (y1 + y2) / 2
        self.line(x, y1, x, ym - 18)
        self.line(x, ym + 18, x, y2)
        self.parts.append(f'<rect class="o" x="{x - 6}" y="{ym - 18}" width="12" height="36"/>')
        self.text(x + 12, ym - 2, label)
        if value:
            self.text(x + 12, ym + 11, value, "start", "pn")

    def cap_v(self, x: float, y1: float, y2: float, label: str, value: str = "") -> None:
        ym = (y1 + y2) / 2
        self.line(x, y1, x, ym - 4)
        self.line(x, ym + 4, x, y2)
        self.line(x - 12, ym - 4, x + 12, ym - 4)
        self.parts.append(f'<path d="M{x - 12},{ym + 7} Q{x},{ym + 1} {x + 12},{ym + 7}"/>')
        self.text(x + 16, ym - 4, label)
        self.text(x - 14, ym - 8, "+", "end")
        if value:
            self.text(x + 16, ym + 9, value, "start", "pn")

    def inductor_h(self, x1: float, x2: float, y: float, label: str, value: str = "") -> None:
        xm = (x1 + x2) / 2
        self.line(x1, y, xm - 20, y)
        self.line(xm + 20, y, x2, y)
        d = f"M{xm - 20},{y}" + " a5,5 0 0 1 10,0" * 4
        self.parts.append(f'<path d="{d}"/>')
        self.text(xm, y - 10, label, "middle")
        if value:
            self.text(xm, y + 18, value, "middle", "pn")

    def inductor_v(self, x: float, y1: float, y2: float, label: str, value: str = "") -> None:
        ym = (y1 + y2) / 2
        self.line(x, y1, x, ym - 20)
        self.line(x, ym + 20, x, y2)
        d = f"M{x},{ym - 20}" + "".join(" a5,5 0 0 1 0,10" for _ in range(4))
        self.parts.append(f'<path d="{d}"/>')
        self.text(x + 12, ym - 2, label)
        if value:
            self.text(x + 12, ym + 11, value, "start", "pn")

    def battery_v(self, x: float, y1: float, y2: float, label: str, value: str = "") -> None:
        ym = (y1 + y2) / 2
        self.line(x, y1, x, ym - 4)
        self.line(x, ym + 4, x, y2)
        self.line(x - 12, ym - 4, x + 12, ym - 4)
        self.line(x - 6, ym + 4, x + 6, ym + 4)
        self.text(x + 16, ym, label + (f" = {value}" if value else ""))

    def source(self, x: float, y: float, label: str) -> None:
        self.parts.append(f'<circle class="o" cx="{x}" cy="{y}" r="15"/>')
        self.parts.append(f'<path d="M{x - 8},{y} q4,-8 8,0 q4,8 8,0"/>')
        self.text(x, y + 30, label, "middle")

    def transformer(self, x: float, y1: float, y2: float, tap: bool = False) -> None:
        """Primary coil at x, secondary at x + 26 (both from y1 to y2)."""
        for cx, sweep in ((x, 1), (x + 26, 0)):
            n = 6
            h = (y2 - y1) / n
            d = f"M{cx},{y1}" + "".join(
                f" a{h / 2:.2f},{h / 2:.2f} 0 0 {sweep} 0,{h:.2f}" for _ in range(n)
            )
            self.parts.append(f'<path d="{d}"/>')
        self.line(x + 11, y1, x + 11, y2)
        self.line(x + 15, y1, x + 15, y2)
        if tap:
            self.dot(x + 26, (y1 + y2) / 2)


def _fmt(summary: Mapping[str, tuple[float, str]], key: str, unit: str, digits: int = 3) -> str:
    if key not in summary:
        return ""
    v, u = summary[key]
    try:
        return format_eng(Q_(v, u))
    except Exception:  # unit text pint does not parse: plain rendering
        return f"{v:.{digits}g} {unit or u}".replace(".", ",")


def single_phase(
    topology: str,
    devices: Mapping[str, tuple[str, str, str]],  # position → (kind, designator, part)
    filt: str,
    load: str,
    summary: Mapping[str, tuple[float, str]],
    title: str,
    freewheel: bool = False,
) -> str:
    """RET1 and RETC1. Positions: D1..D4 (bridge legs), or D1/D2 (center tap), D1 (half wave)."""
    svg = Svg(720, 300)
    svg.text(10, 18, title, "start", "ttl")
    top, bot = 60.0, 240.0
    svg.source(40, 150, f"{_fmt(summary, 'Vin', 'V')} rede")
    svg.wire((40, 135), (40, 90), (100, 90))
    svg.wire((40, 165), (40, 210), (100, 210))
    svg.transformer(100, 90, 210, tap=topology == "center_tap")
    svg.text(113, 82, f"N = {_fmt(summary, 'N', ' ')}".strip(), "middle")
    xs = 126.0  # secondary terminals
    svg.text(xs + 4, 230, f"Vsec {_fmt(summary, 'Vsec', 'V')}")

    def dev(pos: str) -> tuple[str, str, str]:
        return devices.get(pos, ("diode", pos, ""))

    if topology == "ponte":
        x1, x2 = 230.0, 310.0
        svg.wire((xs, 90), (180, 90), (180, 150), (x1, 150))
        svg.wire((xs, 210), (200, 210), (200, 270), (x2 - 40, 270), (x2 - 40, 150), (x2, 150))
        for x, upper, lower in ((x1, "D1", "D3"), (x2, "D2", "D4")):
            k, d, p = dev(upper)
            svg.device_up(x, 150, top, k, d, p)
            k, d, p = dev(lower)
            svg.device_up(x, bot, 150, k, d, p)
            svg.dot(x, 150)
        svg.wire((x1, top), (x2, top))
        svg.wire((x1, bot), (x2, bot))
        x_out = x2
    elif topology == "center_tap":
        x1 = 250.0
        k, d, p = dev("D1")
        svg.device_right(xs, x1, 90, k, d, p)
        k, d, p = dev("D2")
        svg.device_right(xs, x1, 210, k, d, p)
        svg.wire((x1, 90), (x1, top))
        svg.wire((x1, 210), (x1 + 20, 210), (x1 + 20, top), (x1, top))
        svg.wire((xs, 150), (160, 150), (160, bot), (x1 + 20, bot))
        x_out = x1 + 20
        svg.wire((x1, top), (x_out, top))
    else:
        x1 = 250.0
        k, d, p = dev("D1")
        svg.device_right(xs, x1, 90, k, d, p)
        svg.wire((x1, 90), (x1, top))
        svg.wire((xs, 210), (160, 210), (160, bot), (x1, bot))
        x_out = x1
    x = x_out + 40
    svg.wire((x_out, top), (x, top))
    svg.wire((x_out, bot), (x, bot))
    if freewheel:
        k, d, p = dev("DRL")
        svg.device_up(x, bot, top, "diode", d, p)
        svg.dot(x, top)
        svg.dot(x, bot)
        x += 70
        svg.wire((x - 70, top), (x, top))
        svg.wire((x - 70, bot), (x, bot))
    if filt in ("C", "pi"):
        svg.cap_v(x, top, bot, "C1", _fmt(summary, "C", "µF"))
        svg.dot(x, top)
        svg.dot(x, bot)
    if filt in ("LC", "pi"):
        svg.inductor_h(x, x + 90, top, "L1", _fmt(summary, "L", "mH"))
        x += 90
        svg.wire((x - 90, bot), (x, bot))
        svg.cap_v(
            x,
            top,
            bot,
            "C2" if filt == "pi" else "C1",
            _fmt(summary, "C2" if filt == "pi" else "C", "µF"),
        )
        svg.dot(x, top)
        svg.dot(x, bot)
    x += 90
    svg.wire((x - 90, top), (x, top))
    svg.wire((x - 90, bot), (x, bot))
    if load == "R":
        svg.resistor_v(x, top, bot, "R", _fmt(summary, "R", "Ω"))
    else:
        y1, y2 = top, bot
        has_e = load == "RLE"
        seg = (y2 - y1) / (3 if has_e else 2)
        svg.resistor_v(x, y1, y1 + seg, "R", _fmt(summary, "R", "Ω"))
        svg.inductor_v(x, y1 + seg, y1 + 2 * seg, "L", _fmt(summary, "L_load", "mH"))
        if has_e:
            svg.battery_v(x, y1 + 2 * seg, y2, "E", _fmt(summary, "E", "V"))
    svg.text(x + 40, top + 4, "+", "middle")
    svg.text(x + 40, (top + bot) / 2, f"Vo = {_fmt(summary, 'Vo', 'V')}", "start")
    svg.text(x + 40, bot, "−", "middle")
    return svg.render(title)


def three_phase(
    pulses: int,
    kind: str,
    designator: str,
    part: str,
    summary: Mapping[str, tuple[float, str]],
    title: str,
) -> str:
    """RET3: Y sources with Ls, 3-pulse star, 6-pulse bridge or two bridges in series."""
    bridges = 2 if pulses == 12 else 1
    svg = Svg(880 if bridges == 2 else 620, 320)
    svg.text(10, 18, title, "start", "ttl")
    top, bot = 60.0, 260.0
    names = "abc"
    first = designator.split("–")[0]
    prefix = first.rstrip("0123456789")
    n = 0
    x_out = 0.0
    for b in range(bridges):
        x0 = 30.0 + b * 330
        tag = "" if bridges == 1 else (" (Y)" if b == 0 else " (Δ)")
        svg.text(x0, 34, f"secundário{tag}: {_fmt(summary, 'Vll_sec', 'V')} de linha")
        ys = [120.0, 160.0, 200.0]
        for k, y in enumerate(ys):
            svg.source(x0 + 15, y, "")
            svg.text(x0 - 4, y + 4, names[k], "end")
            svg.inductor_h(
                x0 + 30, x0 + 110, y, f"Ls{names[k]}", _fmt(summary, "Ls", "mH") if k == 2 else ""
            )
        legs = [x0 + 160 + 50 * k for k in range(3)]
        y_top = top
        for x, y in zip(legs, ys, strict=True):
            svg.wire((x0 + 110, y), (x, y))
            svg.dot(x, y)
            n += 1
            svg.device_up(x, y, y_top, kind, f"{prefix}{n}", "")
            if pulses != 3:
                n += 1
                svg.device_up(x, bot, y, kind, f"{prefix}{n}", "")
        series_p = bridges == 2 and b == 1  # fed from the left, not an output rail
        svg.wire((legs[0], y_top), (legs[-1] + (0 if series_p else 40), y_top))
        if pulses != 3:
            svg.wire((legs[0], bot), (legs[-1] + 40, bot))
        x_out = legs[-1] + 40
        if bridges == 2 and b == 0:
            # P of bridge 1 goes over the top to the load; N of bridge 1 feeds P of bridge 2
            bridge2_top = x0 + 330 + 160
            svg.wire((x_out, top), (x_out, top - 14), (x0 + 690, top - 14))
            svg.wire((x_out, bot), (x_out + 15, bot), (x_out + 15, top), (bridge2_top, top))
    if part:  # legs are too close for a label on each device
        svg.text(10, 308, f"{designator}: {part}")
    if pulses == 3:
        svg.text(10, 290, "neutro do secundário → retorno da carga", "start")
        svg.wire((x_out, bot), (x_out - 150, bot))
    x = x_out + 60
    if bridges == 2:
        svg.wire((x, top - 14), (x, top))
    else:
        svg.wire((x_out, top), (x, top))
    svg.wire((x_out, bot), (x, bot))
    seg = (bot - top) / 2
    svg.resistor_v(x, top, top + seg, "R", _fmt(summary, "R_load", "Ω"))
    svg.inductor_v(x, top + seg, bot, "L", "≫ R/ω")
    svg.text(x + 50, (top + bot) / 2, f"Vo = {_fmt(summary, 'Vo', 'V')}")
    svg.text(x + 50, (top + bot) / 2 + 14, f"Io = {_fmt(summary, 'Io', 'A')}")
    return svg.render(title)
