"""PT-BB: any circuit the automatic assembly fits on the board passes the breadboard check.

The check is an independent reading of the assembly (strips, jumpers, legs) against the
schematic connectivity, so this property exercises both: a wrong placement or a wrong check
shows up as a failure.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from circuitos.breadboard.autoplace import autoplace
from circuitos.breadboard.check import check
from circuitos.breadboard.reference import build
from tests.unit.schematic.helpers import Builder

PARTS = {
    "resistor": (2, {"value": "1k"}),
    "capacitor": (2, {"value": "100n"}),
    "inductor": (2, {"value": "1m"}),
    "diode": (2, {}),
    "npn": (3, {}),
    "pnp": (3, {}),
    "nmos": (3, {}),
    "opamp": (3, {}),
    "vdc": (2, {"dc": "5"}),
    "vsin": (2, {"amplitude": "1", "freq": "1k"}),
}


@st.composite
def circuits(draw):  # type: ignore[no-untyped-def]
    nets = ["0"] + [f"n{i}" for i in range(draw(st.integers(1, 7)))]
    kinds = draw(st.lists(st.sampled_from(sorted(PARTS)), min_size=1, max_size=12))
    b = Builder("aleatório")
    for i, kind in enumerate(kinds):
        n, params = PARTS[kind]
        nodes = draw(st.lists(st.sampled_from(nets), min_size=n, max_size=n))
        b.add(kind, f"X{i}", nodes, **params)
    return b.sch


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(sch=circuits())
def test_pt_bb_automatic_assembly_always_checks(sch):
    ref = build(sch, {})
    bb, notes = autoplace(ref)
    if any("não coube" in n or "sem furo" in n for n in notes):
        return  # too big for one board: reported to the user, nothing to check
    report = check(ref, bb)
    assert report.ok, [i.message for i in report.issues if i.kind != "aviso"]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(sch=circuits())
def test_pt_bb_tidiest_never_worse_than_reading_order(sch):
    """The chosen assembly is never worse than the plain reading order: first fewer parts left
    out, then fewer jumpers over bodies, legs or other jumpers, then fewer jumpers."""
    from circuitos.breadboard.autoplace import _assemble

    def lost(notes):  # type: ignore[no-untyped-def]
        return sum("não coube" in n or "sem furo" in n for n in notes)

    ref = build(sch, {})
    plain, plain_notes, plain_tangled = _assemble(ref, None)
    bb, notes = autoplace(ref)
    assert lost(notes) <= lost(plain_notes)
    if lost(notes) == lost(plain_notes):
        assert (_tangles(bb), len(bb.wires)) <= (plain_tangled, len(plain.wires))


def _tangles(bb):  # type: ignore[no-untyped-def]
    """Jumpers drawn over a body, a leg or another jumper."""
    from circuitos.breadboard.packages import package
    from circuitos.breadboard.routing import Clearance, body

    clr = Clearance([], set(), [])
    for p in bb.parts:
        clr.add_part(body(package(p.package), p.legs), list(p.legs.values()))
    n = 0
    for w in bb.wires:
        n += not clr.wire_clear(w.a, w.b)
        clr.add_wire(w.a, w.b)
    return n


def test_bb_parts_never_overlap_and_jumpers_stay_clear():
    """Pushbuttons, LEDs and a resistor (the circuit of the screenshot that showed parts on top
    of each other): no body overlaps another, and no jumper crosses a body, a leg or a jumper."""
    from circuitos.breadboard.packages import package
    from circuitos.breadboard.routing import Clearance, body

    b = Builder("botões")
    b.add("vdc", "V1", ["vcc", "0"], dc="12")
    b.add("tact_switch", "SW1", ["vcc", "a"])
    b.add("resistor", "R1", ["a", "b"], value="470")
    b.add("led", "LED1", ["b", "0"])
    b.add("tact_switch4", "SW3", ["vcc", "n1", "q", "n2"])
    b.add("led", "LED2", ["q", "r"])
    b.add("resistor", "R2", ["r", "0"], value="1k")
    ref = build(b.sch, {})
    bb, notes = autoplace(ref)
    assert check(ref, bb).ok and not notes
    clr = Clearance([], set(), [])
    for p in bb.parts:
        rect = body(package(p.package), p.legs)
        assert clr.part_fits(rect, list(p.legs.values())), p.ref
        clr.add_part(rect, list(p.legs.values()))
    for w in bb.wires:
        assert clr.wire_clear(w.a, w.b), (w.a, w.b)
        clr.add_wire(w.a, w.b)
    # the circuit sits on the lower board and the supply plugs into its bottom rails, next to
    # the instruments: no lead crosses a board
    v1 = next(p for p in bb.parts if p.ref == "V1")
    assert sorted(h.split(":")[1][:2] for h in v1.legs.values()) == ["bn", "bp"]
    assert all(h.startswith("2:") for p in bb.parts for h in p.legs.values())
