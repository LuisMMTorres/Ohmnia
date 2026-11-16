"""Automatic assembly: place every part on the breadboard and wire the nets.

Deterministic and readable rather than minimal:

* rails: ground on the two negative rails (``tn``, ``bn``), the positive IC supply on ``tp`` and
  the negative one on ``bp``; without IC supplies, the node of a DC source tied to ground takes
  ``tp`` (positive value) or ``bp`` (negative);
* integrated circuits straddle the centre channel, then the three-leg parts, then the two-leg
  parts, left to right with one empty row between parts;
* a two-leg part goes straight into the strips of its nodes when the legs reach (axial parts
  bend from ``min_span`` to 12 holes; to a rail, the part stands vertically); otherwise it gets
  new strips;
* the strips of each node are chained with jumpers, and rail nodes get one jumper per strip;
* instruments and supplies off the board get one lead per terminal.

The result is checked with :func:`circuitos.breadboard.check.check` by the callers and the
tests: an automatic assembly must always pass.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import count, pairwise

from circuitos.breadboard import board
from circuitos.breadboard.layout import Breadboard, Jumper, PlacedPart, WireColor
from circuitos.breadboard.packages import package
from circuitos.breadboard.pinout import Resolved
from circuitos.breadboard.reference import ALIM, Reference, key

MAX_SPAN = 12
_LEG_PREF = {"U": "edcba", "L": "fghij"}
_WIRE_PREF = {"U": "abcde", "L": "jihgf"}
_PALETTE: tuple[WireColor, ...] = ("verde", "amarelo", "laranja", "branco", "azul", "cinza")

Strip = tuple[str, int]  # (half "U"/"L", row)
NewRows = Callable[[str, int], int | None]  # half, width -> first row (negative: other half)
NetOf = Callable[[Resolved, str], str | None]


@dataclass
class _State:
    used: set[str] = field(default_factory=set)
    owner: dict[Strip, str | None] = field(default_factory=dict)  # strip -> net (None: no net)
    strips: dict[str, list[Strip]] = field(default_factory=dict)  # net -> strips, in order
    nxt: dict[str, int] = field(default_factory=lambda: {"U": 3, "L": 3})
    notes: list[str] = field(default_factory=list)
    standing: set[Strip] = field(default_factory=set)  # rows with a part standing to a rail
    busy: set[Strip] = field(default_factory=set)  # rows under a transistor or IC body

    def free(self, s: Strip) -> list[str]:
        h, row = s
        return [f"{c}{row}" for c in _LEG_PREF[h] if f"{c}{row}" not in self.used]

    def available(self, s: Strip, net: str | None, need: int = 3) -> bool:
        if not 1 <= s[1] <= board.ROWS:
            return False
        if s in self.owner and (self.owner[s] != net or net is None):
            return False
        return len(self.free(s)) >= need

    def claim(self, s: Strip, net: str | None, hole: str) -> None:
        if s not in self.owner:
            self.owner[s] = net
            if net is not None:
                self.strips.setdefault(net, []).append(s)
        self.used.add(hole)


def _strip_of(hole: str) -> Strip:
    col, row = board.parse(hole)
    return ("U" if col in board.UPPER else "L", row)


def _rails(ref: Reference) -> dict[str, dict[str, str]]:
    nets = set(ref.nets.values())
    out: dict[str, dict[str, str]] = {}
    if "0" in nets:
        out["0"] = {"U": "tn", "L": "bn"}
    alim = ref.parts.get(ALIM)
    if alim is not None:
        for term, rail in (("+", "tp"), ("-", "bp")):
            net = ref.nets.get(key(ALIM, term))
            if net and net not in out:
                out[net] = {"U": rail, "L": rail}
        return out
    for r in ref.parts.values():
        if r.kind != "vdc":
            continue
        p, n = ref.nets.get(key(r.ref, "p")), ref.nets.get(key(r.ref, "n"))
        if p and n == "0" and p not in out:
            rail = "bp" if r.supplies.get("dc", 0.0) < 0 else "tp"
            if all(rail not in v.values() for v in out.values()):
                out[p] = {"U": rail, "L": rail}
    return out


def _order(r: Resolved) -> tuple[int, str]:
    style = package(r.package).style if r.package else "offboard"
    rank = {"dip": 0, "inline": 1, "axial": 2, "radial": 2, "offboard": 3}[style]
    return rank, r.ref


def autoplace(ref: Reference) -> tuple[Breadboard, list[str]]:
    st = _State()
    rails = _rails(ref)
    placed: list[PlacedPart] = []

    def net_of(r: Resolved, pin: str) -> str | None:
        return ref.nets.get(key(r.ref, pin))

    def new_rows(h: str, width: int) -> int | None:
        for half in (h, "L" if h == "U" else "U"):
            r = st.nxt[half]
            while r + width <= board.ROWS:
                if all((half, x) not in st.owner for x in range(r, r + width + 1)):
                    st.nxt[half] = r + width + 3  # two empty rows between parts
                    if half != h:
                        st.notes.append("Metade de cima cheia: peças seguem na metade de baixo.")
                    return r if half == h else -r
                r += 1
        return None

    for r in sorted((p for p in ref.parts.values() if p.package), key=_order):
        if not (r.checkable or r.origin == "sem_pinagem"):
            continue
        pkg = package(r.package or "")
        legs: dict[str, str] = {}
        if pkg.style == "dip":
            half_n = len(pkg.pins) // 2
            row = max(st.nxt["U"], st.nxt["L"])
            if row + half_n > board.ROWS:
                st.notes.append(f"{r.ref}: não coube na protoboard.")
                continue
            for pin, (dr, dc) in zip(pkg.pins, pkg.leg_offsets(), strict=True):
                col = "e" if dc < 0 else "f"
                legs[pin] = f"{col}{row + dr}"
            st.nxt["U"] = st.nxt["L"] = row + half_n + 2
        elif pkg.style == "inline":
            offs = pkg.leg_offsets()
            width = offs[-1][0]
            got = new_rows("U", width)
            if got is None:
                st.notes.append(f"{r.ref}: não coube na protoboard.")
                continue
            h, row = ("U", got) if got > 0 else ("L", -got)
            col = "c" if h == "U" else "h"
            for pin, (dr, _) in zip(pkg.pins, offs, strict=True):
                legs[pin] = f"{col}{row + dr}"
        elif pkg.style in ("axial", "radial"):
            legs = _two_legs(
                st,
                r,
                pkg.style,
                pkg.span,
                pkg.min_span,
                pkg.pitch,
                pkg.pins,
                net_of,
                rails,
                new_rows,
            )
            if not legs:
                st.notes.append(f"{r.ref}: não coube na protoboard.")
                continue
        else:  # off the board: leads placed after the board parts
            continue
        for pin, h in legs.items():
            net = net_of(r, pin)
            if not h.startswith(board.RAILS):
                st.claim(_strip_of(h), net, h)
            else:
                st.used.add(h)
        placed.append(PlacedPart(ref=r.ref, package=pkg.id, legs=legs))
        if pkg.style in ("dip", "inline"):
            st.busy.update(_strip_of(h) for h in legs.values())
        if r.origin == "sem_pinagem":
            st.notes.append(f"{r.ref}: pinagem desconhecida, colocado sem ligações.")

    # instruments and supplies off the board
    for r in sorted((p for p in ref.parts.values() if p.package), key=_order):
        if not r.checkable or package(r.package or "").style != "offboard":
            continue
        legs = {}
        members = ref.members()
        for term in package(r.package or "").pins:
            net = net_of(r, term)
            if net is None or len(members.get(net, [])) < 2:
                continue  # terminal not wired in the schematic: no lead
            if net in rails:
                hole = _rail_hole(st, rails[net]["U"], 2)
            else:
                hole = _hole_for_net(st, net, new_rows)
            if hole is None:
                st.notes.append(f"{r.ref}: sem furo livre para o terminal {term}.")
                continue
            legs[term] = hole
        placed.append(PlacedPart(ref=r.ref, package=r.package or "", legs=legs))

    wires = _wire(st, rails)
    return Breadboard(parts=placed, wires=wires), st.notes


def _hole_for_net(st: _State, net: str, new_rows: NewRows) -> str | None:
    for s in st.strips.get(net, []):
        if st.available(s, net, need=3):
            hole = _pick(st, s, wire=True)
            st.claim(s, net, hole)
            return hole
    row = new_rows("U", 0)
    if row is None:
        return None
    fresh: Strip = ("U", row) if row > 0 else ("L", -row)
    hole = _pick(st, fresh, wire=True)
    st.claim(fresh, net, hole)
    return hole


def _pick(st: _State, s: Strip, wire: bool) -> str:
    h, row = s
    for c in (_WIRE_PREF if wire else _LEG_PREF)[h]:
        hole = f"{c}{row}"
        if hole not in st.used:
            return hole
    raise RuntimeError(f"tira {s} cheia")


def _rail_hole(st: _State, rail: str, near: int) -> str | None:
    for r in sorted(board.RAIL_ROWS, key=lambda x: (abs(x - near), x)):
        hole = f"{rail}{r}"
        if hole not in st.used:
            st.used.add(hole)
            return hole
    return None


def _two_legs(
    st: _State,
    r: Resolved,
    style: str,
    span: int,
    min_span: int,
    pitch: int,
    pins: tuple[str, ...],
    net_of: NetOf,
    rails: dict[str, dict[str, str]],
    new_rows: NewRows,
) -> dict[str, str]:
    p1, p2 = pins
    n1, n2 = net_of(r, p1), net_of(r, p2)
    lo, hi = (min_span, MAX_SPAN) if style == "axial" else (pitch, pitch)

    def homes(net: str | None) -> list[Strip]:
        if net is None or net in rails:
            return []
        return [s for s in st.strips.get(net, []) if st.available(s, net)]

    # (a) both nodes already have strips within reach, same half
    for s1 in homes(n1):
        for s2 in homes(n2):
            if s1[0] == s2[0] and lo <= abs(s1[1] - s2[1]) <= hi:
                common = [
                    c
                    for c in _LEG_PREF[s1[0]]
                    if f"{c}{s1[1]}" not in st.used and f"{c}{s2[1]}" not in st.used
                ]
                if common:
                    return {p1: f"{common[0]}{s1[1]}", p2: f"{common[0]}{s2[1]}"}
    # (b) axial part standing between a strip and a rail
    if style == "axial":
        for pa, na, pb, nb in ((p1, n1, p2, n2), (p2, n2, p1, n1)):
            if nb not in rails:
                continue
            for s in homes(na):
                near = {(s[0], s[1] - 1), s, (s[0], s[1] + 1)}
                if s[1] not in board.RAIL_ROWS or near & (st.standing | st.busy):
                    continue  # no rail hole, or a body next door (standing part, transistor, IC)
                rail = rails[nb][s[0]]
                hole_r = f"{rail}{s[1]}"
                if hole_r in st.used:
                    continue
                for c in _LEG_PREF[s[0]]:
                    hole = f"{c}{s[1]}"
                    if hole not in st.used and abs(board.Y[c] - board.Y[rail]) >= min_span:
                        st.standing.add(s)
                        return {pa: hole, pb: hole_r}
    # (c) one node has a strip: the other leg goes to a new strip at reach
    for pa, na, pb, nb in ((p1, n1, p2, n2), (p2, n2, p1, n1)):
        for s in homes(na):
            if nb is not None and nb not in rails and homes(nb):
                continue
            for d in (span or pitch, -(span or pitch)):
                t: Strip = (s[0], s[1] + d)
                if 1 <= t[1] <= board.ROWS and t not in st.owner:
                    free = [x for x in _LEG_PREF[s[0]] if f"{x}{s[1]}" not in st.used]
                    if free:
                        return {pa: f"{free[0]}{s[1]}", pb: f"{free[0]}{t[1]}"}
    # (d) fresh strips
    d = span or pitch
    got = new_rows("U", d)
    if got is None:
        return {}
    h, row = ("U", got) if got > 0 else ("L", -got)
    c = _LEG_PREF[h][0]
    return {p1: f"{c}{row}", p2: f"{c}{row + d}"}


def _wire(st: _State, rails: dict[str, dict[str, str]]) -> list[Jumper]:
    wires: list[Jumper] = []
    ids = count(1)
    palette = iter(_PALETTE * 20)

    def add(a: str, b: str, color: WireColor) -> None:
        st.used.update((a, b))
        wires.append(Jumper(id=f"w{next(ids)}", a=a, b=b, color=color))

    for net in sorted(st.strips, key=lambda n: (n not in rails, n)):
        strips = st.strips[net]
        if net in rails:
            color: WireColor = (
                "preto" if net == "0" else ("vermelho" if rails[net]["U"] == "tp" else "azul")
            )
            for s in strips:
                rail = rails[net][s[0]]
                hole_r = _rail_hole(st, rail, s[1])
                if hole_r is None:
                    st.notes.append(f"Barramento {rail} sem furo livre.")
                    continue
                st.used.discard(hole_r)
                add(_pick(st, s, wire=True), hole_r, color)
            continue
        colour = next(palette)
        for s1, s2 in pairwise(strips):
            add(_pick(st, s1, wire=True), _pick(st, s2, wire=True), colour)
    # ground on both negative rails (legs and leads may go straight into them): join them
    if (
        "0" in rails
        and any(h.startswith("tn") for h in st.used)
        and any(h.startswith("bn") for h in st.used)
    ):
        a, b = _rail_hole(st, "tn", 2), _rail_hole(st, "bn", 2)
        if a and b:
            st.used.difference_update((a, b))
            add(a, b, "preto")
    return wires
