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
from circuitos.breadboard.check import check
from circuitos.breadboard.layout import Breadboard, Jumper, PlacedPart, WireColor
from circuitos.breadboard.packages import package
from circuitos.breadboard.pinout import Resolved
from circuitos.breadboard.reference import ALIM, Reference, key
from circuitos.breadboard.routing import Clearance, body

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
    clr: Clearance = field(default_factory=lambda: Clearance([], set(), [], place=final))
    tangled: int = 0  # jumpers that could not avoid a body, a leg or another jumper

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
    best: tuple[tuple[int, int, int], Breadboard, list[str]] | None = None
    for order in orders:
        bb, notes, tangled = _assemble(ref, order)
        unplaced = sum("não coube" in n or "sem furo" in n for n in notes)
        score = (unplaced, tangled, len(bb.wires))
        if best is not None and score >= best[0]:
            continue
        if order is not None and not check(ref, bb).ok:
            continue  # an alternative must never be worse than the plain layout
        best = (score, bb, notes)
    assert best is not None
    return best[1], best[2]


def _autoplace(ref: Reference, order: list[str] | None) -> tuple[Breadboard, list[str]]:
    bb, notes, _ = _assemble(ref, order)
    return bb, notes


def _assemble(ref: Reference, order: list[str] | None) -> tuple[Breadboard, list[str], int]:
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
                        st.notes.append(
                            "Metade de baixo cheia: peças seguem na metade de cima."
                            if h == "L"
                            else "Metade de cima cheia: peças seguem na metade de baixo."
                        )
                    return r if half == h else -r
                r += 1
        return None

    seq = sorted((p for p in ref.parts.values() if p.package), key=_order)
    if order is not None:
        seq = [ref.parts[x] for x in order]
    for r in seq:
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
        elif pkg.style == "board":
            offs = pkg.leg_offsets()
            lo = min(dr for dr, _ in offs)
            hi = max(dr for dr, _ in offs)
            row = max(st.nxt["U"], st.nxt["L"]) - lo
            if row + hi > board.ROWS:
                st.notes.append(f"{r.ref}: não coube na protoboard.")
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
                st.notes.append(f"{r.ref}: não coube na protoboard.")
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
                if st.clr.part_fits(body(pkg, cand, final), list(cand.values())):
                    legs = cand
                    if stand is not None:
                        st.standing.add(stand)
                    break
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
        st.clr.add_part(body(pkg, legs, final), list(legs.values()))
        if pkg.style in ("dip", "inline", "board"):
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
    return Breadboard(parts=placed, wires=wires), st.notes, st.tangled


# The circuit goes on the lower board, starting with its lower half: that is the side the
# instruments sit on, so their leads stay short and never cross the boards. The code works on
# board 1 names; ``final`` moves them to board 2 at the end.
# vertical-bus row level with each rail of the lower board (y + 22 + 1)
_BUS_ROW = {"tp": 23, "tn": 24, "bn": 39, "bp": 40}


def final(hole: str) -> str:
    """Where an assembled hole goes on the board drawn to the user."""
    if hole.startswith(("vp", "vn", "2:")):
        return hole
    return f"2:{hole}"


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


def _wire(st: _State, rails: dict[str, dict[str, str]]) -> list[Jumper]:
    """Jumpers that keep clear of bodies, legs and each other where the board allows: a strip
    goes to its rail in the same row (a short vertical wire), the strips of a node are joined
    nearest first, and the rails reach the vertical bus at the left end of the board."""
    wires: list[Jumper] = []
    ids = count(1)
    palette = iter(_PALETTE * 20)

    def add(a: str, b: str, color: WireColor) -> None:
        if not st.clr.wire_clear(a, b):
            st.tangled += 1
        st.used.update((a, b))
        st.clr.add_wire(a, b)
        wires.append(Jumper(id=f"w{next(ids)}", a=a, b=b, color=color))

    def free_in(s: Strip) -> list[str]:
        return [f"{c}{s[1]}" for c in _WIRE_PREF[s[0]] if f"{c}{s[1]}" not in st.used]

    def best(pairs: list[tuple[str, str]]) -> tuple[str, str] | None:
        for a, b in pairs:
            if st.clr.wire_clear(a, b):
                return a, b
        return pairs[0] if pairs else None

    for net in sorted(st.strips, key=lambda n: (n not in rails, n)):
        strips = st.strips[net]
        if net in rails:
            color: WireColor = (
                "preto" if net == "0" else ("vermelho" if rails[net]["U"] == "tp" else "azul")
            )
            for s in strips:
                rail = rails[net][s[0]]
                rows = sorted(board.RAIL_ROWS, key=lambda x: (abs(x - s[1]), x))
                pairs = [
                    (h, f"{rail}{r}")
                    for r in rows
                    if f"{rail}{r}" not in st.used
                    for h in free_in(s)
                ][:30]
                got = best(pairs)
                if got is None:
                    st.notes.append(f"Barramento {rail} sem furo livre.")
                    continue
                add(*got, color)
            continue
        colour = next(palette)
        # minimum spanning tree over the strips of the node (nearest strips first)
        joined = [strips[0]]
        rest = list(strips[1:])
        while rest:
            # nearest pair of strips that still have a free hole each (a full strip is
            # skipped as an end, the node is reached through another of its strips)
            cands = sorted(
                ((a, b) for a in joined for b in rest),
                key=lambda ab: abs(ab[0][1] - ab[1][1]) + (ab[0][0] != ab[1][0]) * 6,
            )
            s1, s2 = next(((a, b) for a, b in cands if free_in(a) and free_in(b)), cands[0])
            pairs = [(a, b) for a in free_in(s1) for b in free_in(s2)]
            got = best(pairs)
            if got is None:
                st.notes.append(f"Faixa da linha {s2[1]} sem furo livre.")
            else:
                add(*got, colour)
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
        bus = f"{col}{_BUS_ROW[rail]}"
        hole = next((f"{rail}{r}" for r in board.RAIL_ROWS if f"{rail}{r}" not in st.used), None)
        if hole is None or bus in st.used:
            continue
        add(bus, hole, "preto" if net == "0" else "vermelho")
    return wires
