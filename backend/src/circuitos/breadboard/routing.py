"""Footprints of the parts drawn on the board and the clearance tests of the automatic assembly.

Coordinates are those of :func:`circuitos.breadboard.board.xy`: x along the rows (one unit per
hole), y down the columns (rails and strips, one unit per 0.1"). A body is the rectangle its
drawing covers (the editor draws a radial capacitor or LED just above its legs, a DIP across
the centre channel, a TO-92 or TO-220 above its row of legs); the automatic assembly keeps
bodies apart, keeps legs out of other bodies and draws no jumper over a body, a leg or another
jumper.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from circuitos.breadboard import board
from circuitos.breadboard.packages import Package

Pt = tuple[float, float]
Seg = tuple[Pt, Pt]
_EPS = 0.05


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def overlaps(self, o: Rect) -> bool:
        return (
            self.x0 < o.x1 - _EPS
            and o.x0 < self.x1 - _EPS
            and self.y0 < o.y1 - _EPS
            and o.y0 < self.y1 - _EPS
        )

    def holds(self, p: Pt, margin: float = 0.1) -> bool:
        return (
            self.x0 + margin < p[0] < self.x1 - margin
            and self.y0 + margin < p[1] < self.y1 - margin
        )


Place = Callable[[str], str]  # hole as assembled -> hole where it is drawn


def _same(hole: str) -> str:
    return hole


def pt(hole: str, place: Place = _same) -> Pt:
    x, y = board.xy(place(hole))
    return float(x), float(y)


def body(pkg: Package, legs: dict[str, str], place: Place = _same) -> Rect | None:
    """Rectangle covered by the drawing of a part on the board (``None`` off the board)."""
    if pkg.style == "offboard" or not legs:
        return None
    pts = [pt(h, place) for h in legs.values()]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if pkg.style == "axial":
        if y0 == y1:
            return Rect(x0, y0 - 0.35, x1, y0 + 0.35)
        return Rect(x0 - 0.35, y0, x0 + 0.35, y1)
    if pkg.style == "radial":
        # a tact switch is square; an electrolytic can stands taller than a LED or ceramic disc
        up, down = {"tact": (1.6, 0.7), "electrolytic": (2.4, 0.25)}.get(pkg.body, (0.8, 0.25))
        if y0 == y1:
            return Rect(x0 - 0.45, y0 - up, x1 + 0.45, y0 + down)
        return Rect(x0 - up, y0 - 0.45, x0 + down, y1 + 0.45)
    if pkg.style == "inline":
        up = 1.4 if pkg.body in ("to220", "to247") else 1.0
        return Rect(x0 - 0.45, y0 - up, x1 + 0.45, y0 + 0.25)
    # dip and board: everything between the two rows of legs
    return Rect(x0 - 0.45, y0, x1 + 0.45, y1)


def _cross(o: Pt, a: Pt, b: Pt) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _near(p: Pt, a: Pt, b: Pt, d: float) -> bool:
    """Point within ``d`` of the segment a-b."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    vx, vy = bx - ax, by - ay
    n2 = vx * vx + vy * vy
    t = 0.0 if n2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * vx + (p[1] - ay) * vy) / n2))
    cx, cy = ax + t * vx, ay + t * vy
    return (p[0] - cx) ** 2 + (p[1] - cy) ** 2 < d * d


def segments_meet(s: Seg, t: Seg) -> bool:
    """Two jumpers cross or run over each other (touching at a shared end is allowed only
    when they do not overlap)."""
    (a, b), (c, d) = s, t
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and 0 not in (d1, d2, d3, d4):
        return True
    shared = {a, b} & {c, d}
    for p, (q0, q1) in ((a, t), (b, t), (c, s), (d, s)):
        if p not in shared and _near(p, q0, q1, 0.2):
            return True
    return False


def _hits_rect(a: Pt, b: Pt, r: Rect) -> bool:
    """Segment crosses the rectangle (shrunk a little, so running along an edge is fine)."""
    shrunk = Rect(r.x0 + 0.1, r.y0 + 0.1, r.x1 - 0.1, r.y1 - 0.1)
    if shrunk.x0 >= shrunk.x1 or shrunk.y0 >= shrunk.y1:
        return False
    lo_x, hi_x = sorted((a[0], b[0]))
    lo_y, hi_y = sorted((a[1], b[1]))
    if hi_x <= shrunk.x0 or lo_x >= shrunk.x1 or hi_y <= shrunk.y0 or lo_y >= shrunk.y1:
        return False  # bounding boxes apart
    if a[0] == b[0] or a[1] == b[1]:  # along a row or a column: the boxes overlap, so it does
        return True
    steps = max(2, int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 8))
    for i in range(steps + 1):
        t = i / steps
        p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if shrunk.x0 < p[0] < shrunk.x1 and shrunk.y0 < p[1] < shrunk.y1:
            return True
    return False


@dataclass
class Clearance:
    """Bodies, legs and jumpers already on the board."""

    bodies: list[Rect]
    legs: set[Pt]
    wires: list[Seg]
    place: Place = field(default=_same)

    def part_fits(self, rect: Rect | None, legs: list[str]) -> bool:
        pts = [pt(h, self.place) for h in legs]
        if rect is not None:
            if any(rect.overlaps(b) for b in self.bodies):
                return False
            if any(rect.holds(p) for p in self.legs if p not in pts):
                return False
            if any(_hits_rect(a, b, rect) for a, b in self.wires):
                return False
        return not any(b.holds(p) for b in self.bodies for p in pts)

    def add_part(self, rect: Rect | None, legs: list[str]) -> None:
        if rect is not None:
            self.bodies.append(rect)
        self.legs.update(pt(h, self.place) for h in legs)

    def wire_clear(self, a_hole: str, b_hole: str) -> bool:
        a, b = pt(a_hole, self.place), pt(b_hole, self.place)
        if any(_hits_rect(a, b, r) or r.holds(a) or r.holds(b) for r in self.bodies):
            return False
        x0, x1 = min(a[0], b[0]) - 0.3, max(a[0], b[0]) + 0.3
        y0, y1 = min(a[1], b[1]) - 0.3, max(a[1], b[1]) + 0.3
        if any(
            x0 < p[0] < x1 and y0 < p[1] < y1 and p not in (a, b) and _near(p, a, b, 0.3)
            for p in self.legs
        ):
            return False
        return not any(
            min(w[0][0], w[1][0]) < x1
            and max(w[0][0], w[1][0]) > x0
            and min(w[0][1], w[1][1]) < y1
            and max(w[0][1], w[1][1]) > y0
            and segments_meet((a, b), w)
            for w in self.wires
        )

    def add_wire(self, a_hole: str, b_hole: str) -> None:
        a, b = pt(a_hole, self.place), pt(b_hole, self.place)
        self.wires.append((a, b))
        self.legs.update((a, b))
