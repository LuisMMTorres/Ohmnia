"""Extra schematic symbols on top of :class:`circuitos.reports.schematic.Svg`.

The drawings of the op-amp, oscillator, instrumentation, filter and power modules use these
symbols; each drawing follows the netlist that the module simulates (same nodes, same
designators), so the labels on the drawing are the element names of the simulation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from circuitos.core.units import Q_, QuantityModel, format_eng

from .schematic import Svg

Pt = tuple[float, float]


def eng(value: float, unit: str) -> str:
    """Engineering notation with the decimal comma (``4,7 kΩ``)."""
    return format_eng(Q_(value, unit))


class Canvas(Svg):
    """:class:`Svg` with the symbols the newer drawings need."""

    # ---------------------------------------------------------------- helpers
    def rotated(self, angle: float, cx: float, cy: float, draw: Callable[[], object]) -> None:
        """Draw ``draw()`` rotated by ``angle`` degrees about (cx, cy) (labels drawn apart)."""
        start = len(self.parts)
        draw()
        inner = self.parts[start:]
        del self.parts[start:]
        self.parts.append(f'<g transform="rotate({angle} {cx} {cy})">' + "".join(inner) + "</g>")

    def note(self, x: float, y: float, s: str, anchor: str = "start") -> None:
        self.text(x, y, s, anchor, "pn")

    def label(self, x: float, y: float, name: str, value: str = "", anchor: str = "start") -> None:
        self.text(x, y, name, anchor)
        if value:
            self.text(x, y + 13, value, anchor, "pn")

    def jumper(self, x: float, y1: float, y2: float, yc: float | None = None) -> None:
        """Vertical wire that crosses a horizontal one at ``yc`` (default: midpoint) with a hop."""
        ym = (y1 + y2) / 2 if yc is None else yc
        self.line(x, y1, x, ym - 6)
        self.parts.append(f'<path d="M{x},{ym - 6} a6,6 0 0 1 0,12"/>')
        self.line(x, ym + 6, x, y2)

    def hop_h(self, x1: float, x2: float, y: float, xc: float) -> None:
        """Horizontal wire that crosses a vertical one at ``xc`` with a hop."""
        self.line(x1, y, xc - 6, y)
        self.parts.append(f'<path d="M{xc - 6},{y} a6,6 0 0 1 12,0"/>')
        self.line(xc + 6, y, x2, y)

    def switch_simple_h(self, x1: float, x2: float, y: float, name: str, value: str = "") -> None:
        """Mechanical switch (open) on a horizontal wire."""
        xm = (x1 + x2) / 2
        self.line(x1, y, xm - 14, y)
        self.line(xm + 14, y, x2, y)
        self.parts.append(f'<circle class="o" cx="{xm - 14}" cy="{y}" r="2.5"/>')
        self.parts.append(f'<circle class="o" cx="{xm + 14}" cy="{y}" r="2.5"/>')
        self.line(xm - 12, y - 2, xm + 12, y - 12)
        self.text(xm, y - 16, name, "middle")
        if value:
            self.text(xm, y + 16, value, "middle", "pn")

    # ---------------------------------------------------------------- passives
    def res_v(
        self, x: float, y1: float, y2: float, name: str, value: str = "", left: bool = False
    ) -> None:
        ym = (y1 + y2) / 2
        self.line(x, y1, x, ym - 18)
        self.line(x, ym + 18, x, y2)
        self.parts.append(f'<rect class="o" x="{x - 6}" y="{ym - 18}" width="12" height="36"/>')
        if left:
            self.label(x - 11, ym - 3, name, value, "end")
        else:
            self.label(x + 11, ym - 3, name, value)

    def cap_np_v(
        self, x: float, y1: float, y2: float, name: str, value: str = "", left: bool = False
    ) -> None:
        """Non-polarised capacitor between (x, y1) and (x, y2)."""
        ym = (y1 + y2) / 2
        self.line(x, y1, x, ym - 4)
        self.line(x, ym + 4, x, y2)
        self.line(x - 11, ym - 4, x + 11, ym - 4)
        self.line(x - 11, ym + 4, x + 11, ym + 4)
        if left:
            self.label(x - 15, ym - 3, name, value, "end")
        else:
            self.label(x + 15, ym - 3, name, value)

    def ind_v(
        self, x: float, y1: float, y2: float, name: str, value: str = "", left: bool = False
    ) -> None:
        ym = (y1 + y2) / 2
        self.line(x, y1, x, ym - 20)
        self.line(x, ym + 20, x, y2)
        d = f"M{x},{ym - 20}" + "".join(" a5,5 0 0 1 0,10" for _ in range(4))
        self.parts.append(f'<path d="{d}"/>')
        if left:
            self.label(x - 11, ym - 3, name, value, "end")
        else:
            self.label(x + 12, ym - 3, name, value)

    def ind_h(self, x1: float, x2: float, y: float, name: str, value: str = "") -> None:
        xm = (x1 + x2) / 2
        self.line(x1, y, xm - 20, y)
        self.line(xm + 20, y, x2, y)
        d = f"M{xm - 20},{y}" + "".join(" a5,5 0 0 1 10,0" for _ in range(4))
        self.parts.append(f'<path d="{d}"/>')
        self.text(xm, y - 10, name, "middle")
        if value:
            self.text(xm, y + 16, value, "middle", "pn")

    def winding(
        self, x: float, y1: float, y2: float, right: bool, dot: Literal["top", "bot", ""]
    ) -> None:
        """Transformer winding (bumps towards the core at the right if ``right``), with a dot."""
        n = 4
        h = (y2 - y1) / n
        sweep = 1 if right else 0
        d = f"M{x},{y1}" + "".join(
            f" a{h / 2:.2f},{h / 2:.2f} 0 0 {sweep} 0,{h:.2f}" for _ in range(n)
        )
        self.parts.append(f'<path d="{d}"/>')
        dx = -9 if right else 9
        if dot:
            yd = y1 + 4 if dot == "top" else y2 - 4
            self.parts.append(f'<circle cx="{x + dx}" cy="{yd}" r="2.6" fill="#1f2937"/>')

    def core(self, x: float, y1: float, y2: float) -> None:
        self.line(x - 2, y1, x - 2, y2)
        self.line(x + 2, y1, x + 2, y2)

    def fuse_h(self, x1: float, x2: float, y: float, name: str, value: str = "") -> None:
        xm = (x1 + x2) / 2
        self.line(x1, y, xm - 16, y)
        self.line(xm + 16, y, x2, y)
        self.parts.append(f'<rect class="o" x="{xm - 16}" y="{y - 5}" width="32" height="10"/>')
        self.line(xm - 16, y, xm + 16, y)
        self.text(xm, y - 10, name, "middle")
        if value:
            self.text(xm, y + 18, value, "middle", "pn")

    def varistor_v(self, x: float, y1: float, y2: float, name: str, value: str = "") -> None:
        self.res_v(x, y1, y2, name, value)
        ym = (y1 + y2) / 2
        self.parts.append(f'<path d="M{x - 11},{ym + 14} L{x - 5},{ym + 14} L{x + 9},{ym - 14}"/>')

    def ntc_h(self, x1: float, x2: float, y: float, name: str, value: str = "") -> None:
        self.resistor_h(x1, x2, y, name, value)
        xm = (x1 + x2) / 2
        self.parts.append(
            f'<path d="M{xm - 20},{y + 10} L{xm - 13},{y + 10} L{xm + 14},{y - 10}"/>'
        )
        self.text(xm + 20, y + 8, "t°", "start", "pn")

    # ---------------------------------------------------------------- diodes
    def diode_h(
        self, x1: float, x2: float, y: float, name: str, part: str = "", right: bool = True
    ) -> None:
        """Diode on a horizontal wire; ``right``: anode at x1, conducts to the right."""
        xm = (x1 + x2) / 2
        self.line(x1, y, xm - 8, y)
        self.line(xm + 8, y, x2, y)
        k = 1 if right else -1
        self.parts.append(
            f'<path d="M{xm - 7 * k},{y - 8} L{xm - 7 * k},{y + 8} L{xm + 7 * k},{y} Z"/>'
        )
        self.line(xm + 8 * k, y - 8, xm + 8 * k, y + 8)
        self.text(xm, y - 12, name, "middle")
        if part:
            self.text(xm, y + 20, part, "middle", "pn")

    def zener_h(
        self, x1: float, x2: float, y: float, name: str, part: str = "", right: bool = True
    ) -> None:
        """Zener on a horizontal wire; ``right``: cathode at x2."""
        self.diode_h(x1, x2, y, name, part, right)
        xm = (x1 + x2) / 2
        k = 1 if right else -1
        xc = xm + 8 * k
        self.parts.append(
            f'<path d="M{xc - 4},{y - 12} L{xc},{y - 8} M{xc},{y + 8} L{xc + 4},{y + 12}"/>'
        )

    def diode_vert(
        self,
        x: float,
        y_top: float,
        y_bot: float,
        name: str,
        part: str = "",
        up: bool = True,
        left: bool = False,
    ) -> None:
        """Diode on a vertical wire; ``up``: anode at the bottom."""
        ym = (y_top + y_bot) / 2
        self.line(x, y_top, x, ym - 8)
        self.line(x, ym + 8, x, y_bot)
        k = -1 if up else 1
        self.parts.append(
            f'<path d="M{x - 8},{ym - 7 * k} L{x + 8},{ym - 7 * k} L{x},{ym + 7 * k} Z"/>'
        )
        self.line(x - 8, ym + 8 * k, x + 8, ym + 8 * k)
        if left:
            self.label(x - 12, ym - 2, name, part, "end")
        else:
            self.label(x + 12, ym - 2, name, part)

    def triac(self, x1: float, x2: float, y: float) -> Pt:
        """TRIAC on a horizontal wire (MT2 at x1, MT1 at x2); returns the gate point."""
        xm = (x1 + x2) / 2
        self.line(x1, y, xm - 7, y)
        self.line(xm + 7, y, x2, y)
        self.line(xm - 7, y - 16, xm - 7, y + 16)
        self.line(xm + 7, y - 16, xm + 7, y + 16)
        self.parts.append(f'<path d="M{xm - 7},{y - 15} L{xm + 7},{y - 8} L{xm - 7},{y - 1} Z"/>')
        self.parts.append(f'<path d="M{xm + 7},{y + 1} L{xm - 7},{y + 8} L{xm + 7},{y + 15} Z"/>')
        self.line(xm + 7, y + 12, xm + 16, y + 26)
        return xm + 16, y + 26

    def diac_v(self, x: float, y_top: float, y_bot: float, name: str) -> None:
        ym = (y_top + y_bot) / 2
        self.line(x, y_top, x, ym - 7)
        self.line(x, ym + 7, x, y_bot)
        self.line(x - 14, ym - 7, x + 14, ym - 7)
        self.line(x - 14, ym + 7, x + 14, ym + 7)
        self.parts.append(f'<path d="M{x - 13},{ym - 7} L{x - 6},{ym + 7} L{x + 1},{ym - 7} Z"/>')
        self.parts.append(f'<path d="M{x - 1},{ym + 7} L{x + 6},{ym - 7} L{x + 13},{ym + 7} Z"/>')
        self.text(x + 18, ym + 4, name)

    # ---------------------------------------------------------------- sources
    def _source(
        self, x: float, y_top: float, y_bot: float, name: str, value: str, glyph: str, left: bool
    ) -> None:
        ym = (y_top + y_bot) / 2
        self.line(x, y_top, x, ym - 15)
        self.line(x, ym + 15, x, y_bot)
        self.parts.append(f'<circle class="o" cx="{x}" cy="{ym}" r="15"/>')
        if glyph == "sine":
            self.parts.append(f'<path d="M{x - 8},{ym} q4,-8 8,0 q4,8 8,0"/>')
        elif glyph == "dc":
            self.text(x, ym - 3, "+", "middle")
            self.text(x, ym + 10, "−", "middle")
        elif glyph == "pulse":
            self.parts.append(
                f'<path d="M{x - 9},{ym + 5} L{x - 4},{ym + 5} L{x - 4},{ym - 5} '
                f'L{x + 3},{ym - 5} L{x + 3},{ym + 5} L{x + 9},{ym + 5}"/>'
            )
        elif glyph == "current_down":
            self.line(x, ym - 9, x, ym + 8)
            self.parts.append(f'<path d="M{x - 5},{ym + 3} L{x},{ym + 10} L{x + 5},{ym + 3}"/>')
        else:  # current, pushing upwards
            self.line(x, ym + 9, x, ym - 8)
            self.parts.append(f'<path d="M{x - 5},{ym - 3} L{x},{ym - 10} L{x + 5},{ym - 3}"/>')
        if left:
            self.label(x - 20, ym - 2, name, value, "end")
        else:
            self.label(x + 20, ym - 2, name, value)

    def sine_v(
        self, x: float, y_top: float, y_bot: float, name: str, value: str = "", left: bool = False
    ) -> None:
        self._source(x, y_top, y_bot, name, value, "sine", left)

    def isource_v(
        self,
        x: float,
        y_top: float,
        y_bot: float,
        name: str,
        value: str = "",
        left: bool = False,
        down: bool = False,
    ) -> None:
        """Current source pushing current up (out of the top terminal), or down."""
        self._source(x, y_top, y_bot, name, value, "current_down" if down else "current", left)

    def pulse_v(
        self, x: float, y_top: float, y_bot: float, name: str, value: str = "", left: bool = False
    ) -> None:
        """Pulse (PWM) voltage source, + at the top."""
        self._source(x, y_top, y_bot, name, value, "pulse", left)

    def src_v(
        self, x: float, y_top: float, y_bot: float, name: str, value: str = "", left: bool = False
    ) -> None:
        """Independent voltage source (DC or a ramp), + at the top."""
        self._source(x, y_top, y_bot, name, value, "dc", left)

    def ammeter_v(self, x: float, y_top: float, y_bot: float, name: str) -> None:
        ym = (y_top + y_bot) / 2
        self.line(x, y_top, x, ym - 11)
        self.line(x, ym + 11, x, y_bot)
        self.parts.append(f'<circle class="o" cx="{x}" cy="{ym}" r="11"/>')
        self.text(x, ym + 4, "A", "middle")
        self.text(x + 16, ym + 4, name)

    # ---------------------------------------------------------------- active parts
    def igbt(self, x: float, y: float, label: str, part: str = "") -> tuple[Pt, Pt, Pt]:
        """IGBT, gate at the left, collector up, emitter down; returns (G, C, E)."""
        gx = x - 22
        self.line(gx, y, x - 10, y)
        self.line(x - 10, y - 12, x - 10, y + 12)
        self.line(x - 5, y - 14, x - 5, y + 14)
        self.line(x - 5, y - 7, x + 8, y - 15)
        self.line(x + 8, y - 15, x + 8, y - 26)
        self.line(x - 5, y + 7, x + 8, y + 15)
        self.line(x + 8, y + 15, x + 8, y + 26)
        self.parts.append(f'<path d="M{x + 1},{y + 14} L{x + 8},{y + 15} L{x + 5},{y + 8}"/>')
        if label:
            self.label(x + 14, y - 2, label, part)
        return (gx, y), (x + 8, y - 26), (x + 8, y + 26)

    def switch_v(
        self, kind: str, x: float, y: float, label: str, part: str = ""
    ) -> tuple[Pt, Pt, Pt]:
        """MOSFET or IGBT (``kind``), vertical; returns (gate, top, bottom)."""
        if kind == "igbt":
            return self.igbt(x, y, label, part)
        return self.nmos(x, y, label, part)

    def switch_h(
        self, kind: str, x: float, y: float, label: str, part: str = ""
    ) -> tuple[Pt, Pt, Pt]:
        """Switch on a horizontal wire (drain/collector at the left), gate below.

        ``(x, y)`` is the centre of the channel; returns (gate, left, right).
        """
        self.rotated(-90, x, y, lambda: self.switch_v(kind, x - 8, y, ""))
        self.label(x, y - 32, label, part, "middle")
        return (x, y + 30), (x - 26, y), (x + 26, y)

    def npn_h(self, x: float, y: float, label: str, part: str = "") -> tuple[Pt, Pt, Pt]:
        """NPN with collector at the left, emitter at the right and base below; (B, C, E)."""
        self.parts.append(f'<circle class="o" cx="{x}" cy="{y}" r="17"/>')
        self.line(x - 10, y + 6, x + 10, y + 6)
        self.line(x, y + 6, x, y + 26)
        self.line(x - 5, y + 6, x - 14, y - 8)
        self.line(x - 14, y - 8, x - 26, y - 8)
        self.line(x + 5, y + 6, x + 14, y - 8)
        self.line(x + 14, y - 8, x + 26, y - 8)
        self.parts.append(f'<path d="M{x + 7},{y - 6} L{x + 14},{y - 8} L{x + 14},{y - 1}"/>')
        self.label(x + 24, y + 12, label, part)
        return (x, y + 26), (x - 26, y - 8), (x + 26, y - 8)

    def chip(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        name: str,
        part: str,
        pins: Mapping[str, tuple[str, float, str]],
    ) -> dict[str, Pt]:
        """IC box; ``pins``: key → (side l/r/t/b, offset along the side, text). Returns the
        outer end of each pin (16 px stubs)."""
        self.parts.append(f'<rect class="o" x="{x}" y="{y}" width="{w}" height="{h}"/>')
        self.text(x + w / 2, y + h / 2 - 4, name, "middle")
        self.text(x + w / 2, y + h / 2 + 10, part, "middle", "pn")
        out: dict[str, Pt] = {}
        for key, (side, off, txt) in pins.items():
            if side == "l":
                p0, p1 = (x, y + off), (x - 16, y + off)
                self.text(x + 4, y + off + 4, txt, "start", "pn")
            elif side == "r":
                p0, p1 = (x + w, y + off), (x + w + 16, y + off)
                self.text(x + w - 4, y + off + 4, txt, "end", "pn")
            elif side == "t":
                p0, p1 = (x + off, y), (x + off, y - 16)
                self.text(x + off, y + 13, txt, "middle", "pn")
            else:
                p0, p1 = (x + off, y + h), (x + off, y + h + 16)
                self.text(x + off, y + h - 5, txt, "middle", "pn")
            self.line(*p0, *p1)
            out[key] = p1
        return out


def si_values(summary: Mapping[str, QuantityModel], names: Mapping[str, str]) -> dict[str, float]:
    """Element name → value in SI from the summary; ``names``: element → summary key.

    The unit follows the first letter of the element (R → Ω, C → F, L → H).
    """
    unit = {"R": "ohm", "C": "F", "L": "H"}
    out: dict[str, float] = {}
    for el, key in names.items():
        if key in summary:
            out[el] = float(summary[key].to_pint().m_as(unit[el[0]]))
    return out


def pretty(q: QuantityModel) -> str:
    return format_eng(q.to_pint())
