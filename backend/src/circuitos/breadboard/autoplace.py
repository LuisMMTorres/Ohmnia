"""Automatic assembly: place every part on the breadboard and wire the nets.

Deterministic and readable. Several part orders are tried (plain reading order, parts that
share nodes kept together, and a fixed set of shuffles) and the assembly with the fewest
jumpers wins; each one follows the same rules:

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

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from itertools import count

from circuitos.breadboard import board
from circuitos.breadboard.check import ERRORS, check
from circuitos.breadboard.layout import Breadboard, Jumper, PlacedPart, WireColor
from circuitos.breadboard.packages import package
from circuitos.breadboard.pinout import Resolved
from circuitos.breadboard.reference import ALIM, Reference, key
from circuitos.breadboard.routing import Clearance, Place, body

MAX_SPAN = 12
_NEAR, _FAR = "L", "U"  # half facing the instruments, filled first
RANDOM_TRIES = 40  # extra part orders tried by autoplace, keeping the one with fewest jumpers
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
    tangled: int = 0  # jumpers that could not avoid a body, a leg or another jumper
    stacked: int = 0  # jumpers lying along another jumper (drawn one over the other)
    place: Place = field(default_factory=lambda: final)  # hole as assembled -> hole drawn
    clr: Clearance = field(init=False)

    def __post_init__(self) -> None:
        self.clr = Clearance([], set(), [], place=self.place)

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
            neg = r.supplies.get("dc", 0.0) < 0
            rail = "bp" if neg else "tp"
            if all(rail not in v.values() for v in out.values()):
                # positive supply on both + rails (top and bottom), joined at the left end
                out[p] = {"U": rail, "L": rail} if neg else {"U": "tp", "L": "bp"}
    return out


def _order(r: Resolved) -> tuple[int, str]:
    style = package(r.package).style if r.package else "offboard"
    rank = {"board": 0, "dip": 0, "inline": 1, "axial": 2, "radial": 2, "offboard": 3}[style]
    return rank, r.ref


def _greedy(ref: Reference, rails: dict[str, dict[str, str]], start: str | None) -> list[str]:
    """Part order that keeps connected parts together: after the ICs and transistors, the next
    two-leg part is the one sharing most nodes (not rails) with the parts already placed, so
    it can go straight into their strips instead of needing a jumper."""
    parts = sorted((p for p in ref.parts.values() if p.package), key=_order)
    nets = {
        p.ref: {n for pin in p.pinmap if (n := ref.nets.get(key(p.ref, pin))) and n not in rails}
        for p in parts
    }
    order = [p.ref for p in parts if _order(p)[0] < 2]
    rest = [p.ref for p in parts if _order(p)[0] == 2]
    tail = [p.ref for p in parts if _order(p)[0] > 2]
    seen: set[str] = set().union(*(nets[x] for x in order)) if order else set()
    if start in rest:
        rest.remove(start)
        order.append(start)
        seen |= nets[start]
    while rest:
        best = max(rest, key=lambda x: (len(nets[x] & seen), -rest.index(x)))
        rest.remove(best)
        order.append(best)
        seen |= nets[best]
    return order + tail


def autoplace(ref: Reference) -> tuple[Breadboard, list[str]]:
    """Try a few part orders and keep the assembly with the fewest jumpers (all parts placed
    first); the reading order of the plain layout breaks ties."""
    rails = _rails(ref)
    two_leg = [p.ref for p in sorted(ref.parts.values(), key=lambda p: p.ref)
               if p.package and _order(p)[0] == 2]  # fmt: skip
    orders: list[list[str] | None] = [None, _greedy(ref, rails, None)]
    orders += [_greedy(ref, rails, s) for s in two_leg[:12]]
    # plus a fixed set of shuffles (seeded: the same circuit always gives the same assembly)
    rng = random.Random(len(two_leg))
    base = _greedy(ref, rails, None)
    head = [x for x in base if x not in two_leg]
    for _ in range(RANDOM_TRIES if len(two_leg) > 2 else 0):
        mid = [x for x in base if x in two_leg]
        rng.shuffle(mid)
        orders.append([x for x in head if _order(ref.parts[x])[0] < 2] + mid
                      + [x for x in head if _order(ref.parts[x])[0] > 2])  # fmt: skip
    best: tuple[tuple[int, ...], Breadboard, list[str]] | None = None
    for order in orders:
        bb, notes, tangled = _assemble(ref, order)
        unplaced = sum("não coube" in n or "sem furo" in n for n in notes)
        score = (unplaced, *tangled, len(bb.wires))
        if best is not None and score >= best[0]:
            continue
        if order is not None and any(i.kind in ERRORS for i in check(ref, bb).issues):
            continue  # an alternative must never be worse than the plain layout
        best = (score, bb, notes)
    assert best is not None
    return best[1], best[2]


def _autoplace(ref: Reference, order: list[str] | None) -> tuple[Breadboard, list[str]]:
    bb, notes, _ = _assemble(ref, order)
    return bb, notes


def _assemble(
    ref: Reference, order: list[str] | None
) -> tuple[Breadboard, list[str], tuple[int, int]]:
    rails = _rails(ref)
    st = _State()  # lower board (board 2, drawn next to the instruments)
    placed: list[PlacedPart] = []
    seq = sorted((p for p in ref.parts.values() if p.package), key=_order)
    if order is not None:
        seq = [ref.parts[x] for x in order]
    left = _place(st, ref, seq, rails, placed)
    # parts that did not fit go on the upper board (board 1), joined to the lower one by wires
    up: _State | None = None
    up_placed: list[PlacedPart] = []
    if left:
        up = _State(place=_upper)
        up.notes.append(
            "Protoboard de baixo cheia: "
            + ", ".join(r.ref for r in left)
            + " vão na protoboard de cima, ligadas à de baixo por fios."
        )
        for r in _place(up, ref, left, rails, up_placed):
            up.notes.append(f"{r.ref}: não coube na protoboard.")

    # instruments and supplies off the board (their leads go to the lower board)
    def net_of(r: Resolved, pin: str) -> str | None:
        return ref.nets.get(key(r.ref, pin))

    def new_rows(h: str, width: int) -> int | None:
        return _new_rows(st, h, width)

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
                hole = _rail_hole(st, rails[net][_NEAR], 2)
            else:
                hole = _hole_for_net(st, net, new_rows)
            if hole is None:
                st.notes.append(f"{r.ref}: sem furo livre para o terminal {term}.")
                continue
            legs[term] = hole
        placed.append(PlacedPart(ref=r.ref, package=r.package or "", legs=legs))
        st.clr.add_part(None, list(legs.values()))

    wires = _wire(st, rails)
    placed = [p.model_copy(update={"legs": {k: final(h) for k, h in p.legs.items()}})
              for p in placed]  # fmt: skip
    wires = [w.model_copy(update={"a": final(w.a), "b": final(w.b)}) for w in wires]
    notes, tangled = st.notes, (st.stacked, st.tangled)
    if up is not None:
        wires += _wire(up, rails, _BUS_ROW_UP) + _link(st, up, rails)
        wires = [w.model_copy(update={"id": f"w{i}"}) for i, w in enumerate(wires, 1)]
        placed = up_placed + placed
        notes = notes + up.notes
        tangled = (tangled[0] + up.stacked, tangled[1] + up.tangled)
    return Breadboard(parts=placed, wires=wires), notes, tangled


def _place(
    st: _State,
    ref: Reference,
    seq: list[Resolved],
    rails: dict[str, dict[str, str]],
    placed: list[PlacedPart],
) -> list[Resolved]:
    """Put the board parts of ``seq`` on the board of ``st``; returns those that did not fit."""
    left: list[Resolved] = []

    def net_of(r: Resolved, pin: str) -> str | None:
        return ref.nets.get(key(r.ref, pin))

    def new_rows(h: str, width: int) -> int | None:
        return _new_rows(st, h, width)

    for r in seq:
        if not (r.checkable or r.origin == "sem_pinagem"):
            continue
        pkg = package(r.package or "")
        legs: dict[str, str] = {}
        if pkg.style == "dip":
            half_n = len(pkg.pins) // 2
            row = max(st.nxt["U"], st.nxt["L"])
            if row + half_n > board.ROWS:
                left.append(r)
                continue
            for pin, (dr, dc) in zip(pkg.pins, pkg.leg_offsets(), strict=True):
                col = "e" if dc < 0 else "f"
                legs[pin] = f"{col}{row + dr}"
            st.nxt["U"] = st.nxt["L"] = row + half_n + 2
        elif pkg.style == "board":
            offs = pkg.leg_offsets()
            lo = min(dr for dr, _ in offs)
            hi = max(dr for dr, _ in offs)
            row = max(st.nxt["U"], st.nxt["L"]) - lo
            if row + hi > board.ROWS:
                left.append(r)
                continue
            low_col, up_col = pkg.cols
            for pin, (dr, dc) in zip(pkg.pins, offs, strict=True):
                legs[pin] = f"{up_col if dc < 0 else low_col}{row + dr}"
            # the board covers the holes between its two rows: no legs or wires there
            inner = board.COLUMNS[board.COLUMNS.index(up_col) + 1 : board.COLUMNS.index(low_col)]
            for x in range(row + lo, row + hi + 1):
                st.used.update(f"{c}{x}" for c in inner)
            st.nxt["U"] = st.nxt["L"] = row + hi + 3
        elif pkg.style == "inline":
            offs = pkg.leg_offsets()
            width = offs[-1][0]
            got = new_rows(_NEAR, width)
            if got is None:
                left.append(r)
                continue
            h, row = (_NEAR, got) if got > 0 else (_FAR, -got)
            col = "c" if h == "U" else "h"
            for pin, (dr, _) in zip(pkg.pins, offs, strict=True):
                legs[pin] = f"{col}{row + dr}"
        elif pkg.style in ("axial", "radial"):
            legs = {}
            for cand, stand in _two_legs(
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
            ):
                if st.clr.part_fits(body(pkg, cand, st.place), list(cand.values())):
                    legs = cand
                    if stand is not None:
                        st.standing.add(stand)
                    break
            if not legs:
                left.append(r)
                continue
        else:  # off the board: leads placed after the board parts
            continue
        joined_roles: set[str] = set()
        for pin, h in legs.items():
            net = net_of(r, pin)
            role = r.pinmap.get(pin)
            if pkg.style == "board" and role is not None and role in joined_roles:
                # another pin of the same function (a second GND): the board itself joins
                # them, so its strip needs no jumper
                st.owner.setdefault(_strip_of(h), net)
                st.used.add(h)
                continue
            if pkg.style == "board" and role is not None:
                joined_roles.add(role)
            if not h.startswith(board.RAILS):
                st.claim(_strip_of(h), net, h)
            else:
                st.used.add(h)
        placed.append(PlacedPart(ref=r.ref, package=pkg.id, legs=legs))
        st.clr.add_part(body(pkg, legs, st.place), list(legs.values()))
        if pkg.style in ("dip", "inline", "board"):
            st.busy.update(_strip_of(h) for h in legs.values())
        if r.origin == "sem_pinagem":
            st.notes.append(f"{r.ref}: pinagem desconhecida, colocado sem ligações.")
    return left


def _new_rows(st: _State, h: str, width: int) -> int | None:
    """First of ``width + 1`` fresh rows, in half ``h`` or else in the other one (negative)."""
    for half in (h, "L" if h == "U" else "U"):
        r = st.nxt[half]
        while r + width <= board.ROWS:
            if all((half, x) not in st.owner for x in range(r, r + width + 1)):
                st.nxt[half] = r + width + 3  # two empty rows between parts
                if half != h:
                    st.notes.append(
                        "Metade de baixo cheia: peças seguem na metade de cima."
                        if h == "L"
                        else "Metade de cima cheia: peças seguem na metade de baixo."
                    )
                return r if half == h else -r
            r += 1
    return None


# The circuit goes on the lower board, starting with its lower half: that is the side the
# instruments sit on, so their leads stay short and never cross the boards. The code works on
# board 1 names; ``final`` moves them to board 2 at the end.
# vertical-bus row level with each rail of the lower board (y + 22 + 1)
_BUS_ROW = {"tp": 23, "tn": 24, "bn": 39, "bp": 40}
# and with each rail of the upper board, which takes the parts that do not fit below (y + 1)
_BUS_ROW_UP = {"tp": 1, "tn": 2, "bn": 17, "bp": 18}


def final(hole: str) -> str:
    """Where an assembled hole goes on the board drawn to the user."""
    if hole.startswith(("vp", "vn", "2:")):
        return hole
    return f"2:{hole}"


def _straight(a: str, b: str) -> bool:
    """A jumper drawn along a row or a column of the board (not diagonal)."""
    (xa, ya), (xb, yb) = board.xy(a), board.xy(b)
    return xa == xb or ya == yb


def _upper(hole: str) -> str:
    """Holes of the upper board keep their board 1 names."""
    return hole


def _vbus_col(rails: dict[str, dict[str, str]], net: str) -> str | None:
    """Vertical bus beside the board: ``vn`` carries ground, ``vp`` the net of the top + rail."""
    if net == "0" and "0" in rails:
        return "vn"
    if rails.get(net, {}).get("U") == "tp":
        return "vp"
    return None


def _hole_for_net(st: _State, net: str, new_rows: NewRows) -> str | None:
    # upper-half strips first: they face the instruments once the board is turned
    for s in sorted(st.strips.get(net, []), key=lambda x: x[0] != _NEAR):
        if st.available(s, net, need=3):
            hole = _pick(st, s, wire=True)
            st.claim(s, net, hole)
            return hole
    row = new_rows(_NEAR, 0)
    if row is None:
        return None
    fresh: Strip = (_NEAR, row) if row > 0 else (_FAR, -row)
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
) -> Iterator[tuple[dict[str, str], Strip | None]]:
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
                for c in common:
                    yield {p1: f"{c}{s1[1]}", p2: f"{c}{s2[1]}"}, None
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
                        yield {pa: hole, pb: hole_r}, s
    # (c) one node has a strip: the other leg goes to a new strip at reach
    for pa, na, pb, nb in ((p1, n1, p2, n2), (p2, n2, p1, n1)):
        for s in homes(na):
            if nb is not None and nb not in rails and homes(nb):
                continue
            for d in (span or pitch, -(span or pitch)):
                t: Strip = (s[0], s[1] + d)
                if 1 <= t[1] <= board.ROWS and t not in st.owner:
                    free = [x for x in _LEG_PREF[s[0]] if f"{x}{s[1]}" not in st.used]
                    for x in free:
                        yield {pa: f"{x}{s[1]}", pb: f"{x}{t[1]}"}, None
    # (d) fresh strips (asked again while the body does not fit there)
    d = span or pitch
    for _ in range(board.ROWS):
        got = new_rows(_NEAR, d)
        if got is None:
            return
        h, row = (_NEAR, got) if got > 0 else (_FAR, -got)
        for c in _LEG_PREF[h][:3]:
            yield {p1: f"{c}{row}", p2: f"{c}{row + d}"}, None


def _wire(
    st: _State, rails: dict[str, dict[str, str]], bus_row: dict[str, int] = _BUS_ROW
) -> list[Jumper]:
    """Jumpers that keep clear of bodies, legs and each other where the board allows: a strip
    goes to its rail in the same row (a short vertical wire), the strips of a node are joined
    nearest first, and the rails reach the vertical bus at the left end of the board."""
    wires: list[Jumper] = []
    ids = count(1)
    palette = iter(_PALETTE * 20)

    def add(a: str, b: str, color: WireColor) -> None:
        st.stacked += _overlaps(st, a, b)
        if not st.clr.wire_clear(a, b):
            st.tangled += 1
        st.used.update((a, b))
        st.clr.add_wire(a, b)
        wires.append(Jumper(id=f"w{next(ids)}", a=a, b=b, color=color))

    for net in sorted(st.strips, key=lambda n: (n not in rails, n)):
        strips = st.strips[net]
        if net in rails:
            color: WireColor = (
                "preto" if net == "0" else ("vermelho" if rails[net]["U"] == "tp" else "azul")
            )
            for s in strips:
                path = _to_rail(st, s, rails[net][s[0]], net)
                if path is None:
                    st.notes.append(f"Barramento {rails[net][s[0]]} sem furo livre.")
                    continue
                for a, b in path:
                    add(a, b, color)
            continue
        colour = next(palette)
        # minimum spanning tree over the strips of the node (nearest strips first)
        joined = [strips[0]]
        rest = list(strips[1:])
        while rest:
            # nearest pair of strips joined by straight wires (along one column of holes, or
            # across the channel in one row, through a spare strip when the rows differ)
            cands = sorted(
                ((a, b) for a in joined for b in rest),
                key=lambda ab: abs(ab[0][1] - ab[1][1]) + (ab[0][0] != ab[1][0]) * 6,
            )
            found: tuple[Strip, list[tuple[str, str]]] | None = None
            for tier in (0, 1, 2):  # the cleanest route between any nearby pair of strips
                for s1, s2 in cands[: (16 if tier < 2 else 1)]:
                    route = _between(st, s1, s2, net, tier)
                    if route is not None:
                        found = (s2, route)
                        break
                if found is not None:
                    break
            if found is None:
                s2 = cands[0][1]
                st.notes.append(f"Faixa da linha {s2[1]} sem caminho reto livre.")
            else:
                s2, route = found
                for a, b in route:
                    add(a, b, colour)
            rest.remove(s2)
            joined.append(s2)
    # rails of one node (top and bottom of the board) are joined through the vertical bus,
    # with short wires at the left end
    rail_net = {rail: net for net, rr in rails.items() for rail in rr.values()}
    for rail in ("tp", "tn", "bn", "bp"):
        rnet = rail_net.get(rail)
        col = _vbus_col(rails, rnet) if rnet else None
        if rnet is None or col is None:
            continue
        net = rnet
        same = {r for r, n in rail_net.items() if n == net}
        used_rails = {r for r in same if any(h.startswith(r) for h in st.used)}
        if rail not in used_rails or len(used_rails) < 2:
            continue
        bus = f"{col}{bus_row[rail]}"
        hole = next((f"{rail}{r}" for r in board.RAIL_ROWS if f"{rail}{r}" not in st.used), None)
        if hole is None or bus in st.used:
            continue
        add(bus, hole, "preto" if net == "0" else "vermelho")
    return wires


def _free_cols(st: _State, s: Strip) -> list[str]:
    """Column letters of strip ``s`` still free, nearest the wire side first."""
    return [c for c in _WIRE_PREF[s[0]] if f"{c}{s[1]}" not in st.used]


def _usable(st: _State, s: Strip, net: str) -> bool:
    """A strip a wire may pass through for ``net``: on the board, not under a body, not another
    node's, with two free holes."""
    if not 1 <= s[1] <= board.ROWS or s in st.busy:
        return False
    if s in st.owner and st.owner[s] != net:
        return False
    return len(_free_cols(st, s)) >= 2


def _overlaps(st: _State, a: str, b: str) -> int:
    """Wires already on the board that this one would lie on (same line, overlapping): two
    wires drawn one over the other look like one and hide a connection."""
    (xa, ya), (xb, yb) = board.xy(st.place(a)), board.xy(st.place(b))
    n = 0
    for p, q in st.clr.wires:
        if ya == yb == p[1] == q[1]:
            lo, hi = sorted((xa, xb))
            if min(hi, max(p[0], q[0])) - max(lo, min(p[0], q[0])) > 0:
                n += 1
        elif xa == xb == p[0] == q[0]:
            lo, hi = sorted((ya, yb))
            if min(hi, max(p[1], q[1])) - max(lo, min(p[1], q[1])) > 0:
                n += 1
    return n


def _score(st: _State, path: list[tuple[str, str]]) -> tuple[int, int, int]:
    """Lower is better: wires lying on other wires, wires over bodies, legs or across other
    wires, and the number of wires."""
    return (
        sum(_overlaps(st, a, b) for a, b in path),
        sum(not st.clr.wire_clear(a, b) for a, b in path),
        len(path),
    )


def _choose(
    st: _State, options: list[list[tuple[str, str]]], tier: int = 2
) -> list[tuple[str, str]] | None:
    """Among options made of straight wires only: the first one clear of bodies, legs and
    other wires (tier 0); else the first one lying on no other wire, crossings allowed as a
    real jumper lies over another (tier 1); else the one with the fewest problems (tier 2)."""
    for path in options:
        if all(st.clr.wire_clear(a, b) for a, b in path):
            return path
    if tier == 0 or not options:
        return None
    for path in options:
        if not any(_overlaps(st, a, b) for a, b in path):
            return path
    if tier == 1:
        return None
    return min(options, key=lambda path: _score(st, path))


def _relay(st: _State, s: Strip, net: str) -> None:
    st.owner.setdefault(s, net)


def _between(
    st: _State, s1: Strip, s2: Strip, net: str, tier: int = 2
) -> list[tuple[str, str]] | None:
    """Straight wires from strip ``s1`` to strip ``s2``. The five holes of a strip are one
    conductor, so the holes are chosen to line up: the same column letter in two strips of one
    half (a wire along the column), or one row across the channel. Two halves at different
    rows go through a spare strip in the row of the other end (an L of two wires), or through
    two spare strips facing each other across the channel in a free row (three wires)."""

    def free(x: Strip) -> list[str]:
        return _free_cols(st, x)

    options: list[list[tuple[str, str]]] = []
    relays: list[list[Strip]] = []
    if s1[0] == s2[0]:
        for c in free(s1):
            if c in free(s2):
                options.append([(f"{c}{s1[1]}", f"{c}{s2[1]}")])
                relays.append([])
        # or across the channel and along the other half (when this half's columns are taken)
        other = "L" if s1[0] == "U" else "U"
        m1: Strip = (other, s1[1])
        m2: Strip = (other, s2[1])
        if _usable(st, m1, net) and _usable(st, m2, net):
            for c in free(m1):
                if c not in free(m2):
                    continue
                x1 = next((x for x in free(m1) if x != c), None)
                x2 = next((x for x in free(m2) if x != c), None)
                if x1 is None or x2 is None or not free(s1) or not free(s2):
                    continue
                options.append(
                    [
                        (f"{free(s1)[0]}{s1[1]}", f"{x1}{s1[1]}"),
                        (f"{c}{s1[1]}", f"{c}{s2[1]}"),
                        (f"{x2}{s2[1]}", f"{free(s2)[0]}{s2[1]}"),
                    ]
                )
                relays.append([m1, m2])
    elif s1[1] == s2[1]:
        for a in free(s1):
            for b in free(s2):
                options.append([(f"{a}{s1[1]}", f"{b}{s2[1]}")])
                relays.append([])
    else:
        for first, second in ((s1, s2), (s2, s1)):
            mid: Strip = (first[0], second[1])  # same half as first, same row as second
            if not _usable(st, mid, net):
                continue
            for c in free(first):
                if c not in free(mid):
                    continue
                for d in free(mid):
                    if d == c:
                        continue
                    for e in free(second):
                        along = (f"{c}{first[1]}", f"{c}{mid[1]}")
                        options.append([along, (f"{d}{mid[1]}", f"{e}{second[1]}")])
                        relays.append([mid])
        rows = sorted(
            (r for r in range(1, board.ROWS + 1) if r not in (s1[1], s2[1])),
            key=lambda r: (abs(r - s1[1]) + abs(r - s2[1]), r),
        )
        for r in rows[:16]:
            m1 = (s1[0], r)
            m2 = (s2[0], r)
            if not (_usable(st, m1, net) and _usable(st, m2, net)):
                continue
            c1 = next((c for c in free(s1) if c in free(m1)), None)
            c2 = next((c for c in free(s2) if c in free(m2)), None)
            if c1 is None or c2 is None:
                continue
            x1 = next(c for c in free(m1) if c != c1)
            x2 = next(c for c in free(m2) if c != c2)
            options.append(
                [
                    (f"{c1}{s1[1]}", f"{c1}{r}"),
                    (f"{x1}{r}", f"{x2}{r}"),
                    (f"{c2}{r}", f"{c2}{s2[1]}"),
                ]
            )
            relays.append([m1, m2])
    path = _choose(st, options, tier)
    if path is not None:
        for m in relays[options.index(path)]:
            _relay(st, m, net)
    return path


def _to_rail(st: _State, s: Strip, rail: str, net: str) -> list[tuple[str, str]] | None:
    """Straight wires from strip ``s`` to ``rail``: one wire in the strip's own row when the
    rail has a hole there, else along the strip's column to a spare strip in the nearest row
    that has one, and from there to the rail."""

    def free(x: Strip) -> list[str]:
        return _free_cols(st, x)

    options: list[list[tuple[str, str]]] = []
    relays: list[Strip | None] = []
    rows = sorted(board.RAIL_ROWS, key=lambda x: (abs(x - s[1]), x))
    for r in rows:
        hole_r = f"{rail}{r}"
        if hole_r in st.used:
            continue
        if r == s[1]:
            for c in free(s):
                options.append([(f"{c}{s[1]}", hole_r)])
                relays.append(None)
            continue
        mid: Strip = (s[0], r)
        if not _usable(st, mid, net):
            continue
        for c in free(s):
            if c not in free(mid):
                continue
            for d in free(mid):
                if d != c:
                    options.append([(f"{c}{s[1]}", f"{c}{r}"), (f"{d}{r}", hole_r)])
                    relays.append(mid)
    # the strip's own row first, then the nearest spare strip
    path = _choose(st, options)
    if path is not None:
        mid_used = relays[options.index(path)]
        if mid_used is not None:
            _relay(st, mid_used, net)
    return path


def _link(low: _State, up: _State, rails: dict[str, dict[str, str]]) -> list[Jumper]:
    """Wires that join the upper board to the lower one: each node with strips on both boards
    gets one wire (from the lower half of the upper board to the upper half of the lower board,
    the nearest pair of rows), and each rail used above is wired to the nearest rail of its node
    below that is in use. Holes come out with their drawn names."""
    wires: list[Jumper] = []

    def free(st: _State, s: Strip) -> list[str]:
        return [c for c in _WIRE_PREF[s[0]] if f"{c}{s[1]}" not in st.used]

    def add(a: tuple[_State, str], b: tuple[_State, str], color: WireColor) -> None:
        for st, h in (a, b):
            st.used.add(h)
        name = f"x{len(wires) + 1}"
        wires.append(Jumper(id=name, a=a[0].place(a[1]), b=b[0].place(b[1]), color=color))

    def straight_link(net: str, sa: Strip, sb: Strip) -> bool:
        """Straight wires from strip ``sa`` above to ``sb`` below: one vertical wire when the
        rows match, else through a spare strip in the row of the other end."""
        colour = next(palette)
        if sa[1] == sb[1]:
            if free(up, sa) and free(low, sb):
                add((up, f"{free(up, sa)[0]}{sa[1]}"), (low, f"{free(low, sb)[0]}{sb[1]}"), colour)
                return True
            return False
        for st, mid, far in ((low, (sb[0], sa[1]), sb), (up, (sa[0], sb[1]), sa)):
            if not _usable(st, mid, net):
                continue
            common = [c for c in free(st, far) if c in free(st, mid)]
            cross = [c for c in free(st, mid) if not common or c != common[0]]
            if not common or not cross:
                continue
            st.owner.setdefault(mid, net)
            c, d = common[0], cross[0]
            along = ((st, f"{c}{far[1]}"), (st, f"{c}{mid[1]}"))
            if st is low:  # up sa -> low mid (vertical), low mid -> low sb (along a column)
                add((up, f"{free(up, sa)[0]}{sa[1]}"), (low, f"{d}{mid[1]}"), colour)
            else:  # up sa -> up mid (along a column), up mid -> low sb (vertical)
                add((up, f"{d}{mid[1]}"), (low, f"{free(low, sb)[0]}{sb[1]}"), colour)
            add(along[0], along[1], colour)
            return True
        return False

    palette = iter(_PALETTE * 20)
    for net in sorted(set(up.strips) & set(low.strips)):
        if net in rails:
            continue
        pairs = sorted(
            ((a, b) for a in up.strips[net] for b in low.strips[net]
             if free(up, a) and free(low, b)),
            key=lambda ab: ((ab[0][0], ab[1][0]) != ("L", "U"), abs(ab[0][1] - ab[1][1])),
        )  # fmt: skip
        if not any(straight_link(net, a, b) for a, b in pairs):
            up.notes.append(f"Nó {net}: sem furo livre para ligar as duas protoboards.")
    for net, by_half in rails.items():
        mine = {r for r in by_half.values() if any(h.startswith(r) for h in up.used)}
        theirs = {r for r in by_half.values() if any(h.startswith(r) for h in low.used)}
        if not mine:
            continue
        theirs = theirs or set(by_half.values())
        # nearest pair: rail y on the upper board, rail y + 22 on the lower one
        ra, rb = min(
            ((a, b) for a in mine for b in theirs),
            key=lambda ab: (abs(board.Y[ab[0]] - board.Y[ab[1]] - 22), ab),
        )
        row = next(
            (r for r in reversed(board.RAIL_ROWS)
             if f"{ra}{r}" not in up.used and f"{rb}{r}" not in low.used),
            None,
        )  # fmt: skip
        if row is None:
            up.notes.append(f"Barramento {ra} sem furo livre para ligar as duas protoboards.")
            continue
        tone: WireColor = "vermelho" if by_half["U"] == "tp" else "azul"
        add((up, f"{ra}{row}"), (low, f"{rb}{row}"), "preto" if net == "0" else tone)
    return wires
