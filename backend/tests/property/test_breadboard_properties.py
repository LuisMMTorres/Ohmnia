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
