"""Op-amp V+ and V− pins on the schematic symbol (the same legs that go to the breadboard).

Wired, the output swing follows the supply pins and the supplies deliver the output and quiescent
currents; loose (circuits drawn before the pins existed), an implicit ideal supply at the ``vcc``
and ``vee`` parameters keeps the old behaviour.
"""

from __future__ import annotations

import pytest

from circuitos.breadboard.reference import ALIM, build
from circuitos.schematic.library import pin_positions, symbol
from circuitos.schematic.model import Component, NetLabel, Schematic, Wire
from circuitos.schematic.netlist import build_netlist, connectivity
from circuitos.schematic.runs import SchematicPlan
from circuitos.simulation.backend import make_backend

from .helpers import Builder


def _comparator(supplies: tuple[str, str] | None, iq: str = "") -> Schematic:
    """Open-loop op-amp with +1 V between the inputs: the output saturates high."""
    b = Builder("ampop saturado")
    b.add("vdc", "VI", ["vi", "0"], dc="1")
    nodes = ["0", "vi", "o"] + (list(supplies) if supplies else [])
    b.add("opamp", "U1", nodes, vcc="15", vee="-15", iq=iq)
    b.add("resistor", "RL", ["o", "0"], value="1k")
    if supplies:
        b.add("vdc", "VP", [supplies[0], "0"], dc="12")
        b.add("vdc", "VN", [supplies[1], "0"], dc="-12")
    b.analysis("op")
    return b.sch


def test_symbol_has_supply_pins():
    pins = {p.name: (p.dx, p.dy) for p in symbol("opamp").pins}
    assert pins == {"inn": (-3, -1), "inp": (-3, 1), "out": (3, 0), "vcc": (0, -2), "vee": (0, 2)}


def test_loose_supply_pins_take_the_implicit_supply():
    nl = build_netlist(_comparator(None))
    assert "v_u1_vcc" in nl.text and "v_u1_vee" in nl.text
    assert any("U1: pinos V+ e V− sem ligação" in w for w in nl.warnings)
    assert not any("U1.vcc" in w or "U1.vee" in w for w in nl.warnings)


def test_wired_supply_pins_have_no_implicit_supply():
    nl = build_netlist(_comparator(("vp", "vn")))
    assert "v_u1_" not in nl.text
    assert not any("sem ligação" in w for w in nl.warnings)


@pytest.mark.ngspice
def test_loose_pins_saturate_at_the_parameter_supply():
    op = SchematicPlan(_comparator(None), {}).execute(make_backend()).plot("op")
    assert op["v(o)"].data[0] == pytest.approx(15 - 1.5, abs=1e-3)


@pytest.mark.ngspice
def test_wired_pins_set_the_swing_and_deliver_the_current():
    """±12 V on the pins: saturation at 12 − 1,5 V; V+ delivers I_load + I_Q, V− only I_Q."""
    op = SchematicPlan(_comparator(("vp", "vn"), iq="2m"), {}).execute(make_backend()).plot("op")
    vo = op["v(o)"].data[0]
    assert vo == pytest.approx(12 - 1.5, abs=1e-3)
    # ngspice: branch current positive from + to − inside the source (delivering → negative)
    assert -op["i(vp)"].data[0] == pytest.approx(vo / 1e3 + 2e-3, rel=1e-4)
    assert op["i(vn)"].data[0] == pytest.approx(2e-3, rel=1e-4)


@pytest.mark.ngspice
def test_sinking_output_returns_current_through_v_minus():
    b = Builder("ampop saturado em baixo")
    b.add("vdc", "VI", ["vi", "0"], dc="1")
    b.add("opamp", "U1", ["vi", "0", "o", "vp", "vn"])
    b.add("resistor", "RL", ["o", "0"], value="1k")
    b.add("vdc", "VP", ["vp", "0"], dc="12")
    b.add("vdc", "VN", ["vn", "0"], dc="-12")
    b.analysis("op")
    op = SchematicPlan(b.sch, {}).execute(make_backend()).plot("op")
    vo = op["v(o)"].data[0]
    assert vo == pytest.approx(-12 + 1.5, abs=1e-3)
    assert op["i(vp)"].data[0] == pytest.approx(0, abs=1e-9)
    assert op["i(vn)"].data[0] == pytest.approx(-vo / 1e3, rel=1e-4)


def _crossed() -> tuple[Schematic, Component]:
    """A wire that crosses the V+ pin point in the middle of a segment (older drawing)."""
    u = Component(id="u", kind="opamp", ref="U1", x=0, y=0)
    pos = pin_positions(u)
    (x, y) = pos["vcc"]
    sch = Schematic(
        title="fio cruzando V+",
        components=[u],
        wires=[Wire(id="w", points=[(x - 3, y), (x + 3, y)])],
        labels=[NetLabel(id="l", name="fb", x=x - 3, y=y)],
    )
    return sch, u


def test_wire_crossing_a_supply_pin_does_not_join_it():
    sch, _ = _crossed()
    conn = connectivity(sch)
    assert conn.pin_nodes["U1"]["vcc"] != "fb"


def test_wire_ending_on_a_supply_pin_joins_it():
    sch, _ = _crossed()
    x, y = sch.wires[0].points[0]
    sch.wires[0].points = [(x, y), (x + 3, y)]  # ends on the pin
    assert connectivity(sch).pin_nodes["U1"]["vcc"] == "fb"


def test_breadboard_uses_the_wired_supply_nets():
    sch = _comparator(("vp", "vn"))
    ref = build(sch, {})
    assert ALIM not in ref.parts
    assert ref.nets["U1:7"] == "vp" and ref.nets["U1:4"] == "vn"


def test_breadboard_keeps_the_implicit_supply_for_loose_pins():
    ref = build(_comparator(None), {})
    assert ALIM in ref.parts
    assert ref.nets["U1:7"].startswith("VCC") and ref.nets["U1:4"].startswith("VEE")
