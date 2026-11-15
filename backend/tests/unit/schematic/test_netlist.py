import pytest

from circuitos.schematic.library import SYMBOLS, transform
from circuitos.schematic.model import (
    Analysis,
    Component,
    NetLabel,
    NetRef,
    Probe,
    Schematic,
    Wire,
)
from circuitos.schematic.netlist import SchematicError, build_netlist, connectivity
from circuitos.schematic.values import format_value, parse_value, try_parse

from .helpers import Builder


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1k", 1e3),
        ("4.7u", 4.7e-6),
        ("10meg", 1e7),
        ("1M", 1e-3),  # SPICE: M is milli
        ("2.2kOhm", 2.2e3),
        ("100nF", 100e-9),
        ("1e-3", 1e-3),
        ("-5V", -5.0),
        (".5", 0.5),
        ("3µ", 3e-6),
        ("1mil", 25.4e-6),
    ],
)
def test_parse_value(text, value):
    assert parse_value(text) == pytest.approx(value)


def test_parse_value_errors_and_format():
    with pytest.raises(ValueError, match="notação SPICE"):
        parse_value("abc")
    assert try_parse("x") is None
    assert format_value(4700) == "4.7k"
    assert format_value(1e6) == "1meg"
    assert format_value(1e-5) == "10u"
    assert format_value(0) == "0"
    assert parse_value(format_value(123.456e-9, 9)) == pytest.approx(123.456e-9)


def test_transform_rotation_and_mirror():
    assert transform(2, 0, 90, False) == (0, 2)
    assert transform(2, 0, 180, False) == (-2, 0)
    assert transform(2, 0, 270, False) == (0, -2)
    assert transform(2, 1, 0, True) == (-2, 1)
    assert transform(2, 1, 90, True) == (-1, -2)  # mirror first, then rotate


def test_every_symbol_has_unique_pins_on_grid():
    for sym in SYMBOLS.values():
        names = [p.name for p in sym.pins]
        assert len(names) == len(set(names)), sym.kind
        for p in sym.params:
            assert p.name.isidentifier(), (sym.kind, p.name)


def _rc_wired():
    """V1 – R1 – C1 to ground with wires, a T junction and a crossing that must not connect."""
    return Schematic(
        title="RC",
        components=[
            Component(id="1", kind="vdc", ref="V1", x=0, y=0),
            Component(id="2", kind="resistor", ref="R1", x=4, y=-2),
            Component(id="3", kind="capacitor", ref="C1", x=8, y=2, rot=90),
            Component(id="4", kind="resistor", ref="R2", x=12, y=-6, rot=90),
            Component(id="5", kind="ground", ref="G1", x=0, y=6),
        ],
        wires=[
            Wire(id="a", points=[(0, -2), (2, -2)]),
            # from R1 to C1 top with an end on (8, -2) and a T-branch up to R2
            Wire(id="b", points=[(6, -2), (8, -2), (8, 0)]),
            Wire(id="c", points=[(8, -2), (12, -2)]),
            Wire(id="d", points=[(12, -4), (12, -2)]),
            Wire(id="e", points=[(0, 2), (0, 6)]),
            Wire(id="f", points=[(8, 4), (8, 6), (0, 6)]),
            # crosses wire "c" at (10, -2) without a junction
            Wire(id="g", points=[(10, -4), (10, 0)]),
            # R2 bottom pin is (12,-4); top pin (12,-8) left open on purpose
        ],
        labels=[NetLabel(id="l1", name="out", x=8, y=-2)],
        analyses=[Analysis(kind="op")],
    )


def test_connectivity_rules():
    sch = _rc_wired()
    conn = connectivity(sch)
    assert conn.pin_nodes["V1"] == {"p": "n001", "n": "0"}
    assert conn.pin_nodes["R1"] == {"1": "n001", "2": "out"}
    assert conn.pin_nodes["C1"] == {"1": "out", "2": "0"}
    assert conn.pin_nodes["R2"]["2"] == "out"
    assert conn.pin_nodes["R2"]["1"] not in ("out", "0", "n001")
    assert any("R2.1" in w for w in conn.warnings)  # open pin reported
    # the crossing wire is a net of its own (no pins): never merged with "out"
    assert conn.node_at((10, -2), [w.points for w in sch.wires]) == "out"
    assert conn.point_nodes.get((10, -4)) != "out"


def test_netlist_lines_and_probes():
    sch = _rc_wired()
    sch.probes = [
        Probe(id="p1", kind="v", target=NetRef(at=(8, -2))),
        Probe(id="p2", kind="vdiff", target=NetRef(pin="R1.1"), reference=NetRef(net="out")),
        Probe(id="p3", kind="i", component="C1"),
        Probe(id="p4", kind="p", component="R1", name="PR1"),
    ]
    nl = build_netlist(sch)
    lines = nl.text.splitlines()
    assert lines[0] == "* RC"
    assert "V1 n001 0 DC 5 AC 0" in lines
    assert "R1 am_r1_1 out 1k" in lines
    assert "vam_r1_1 n001 am_r1_1 DC 0" in lines
    assert "C1 am_c1_1 0 1u" in lines
    assert lines[-2:] == [".op", ".end"]
    assert [(p.name, p.expr, p.unit) for p in nl.probes] == [
        ("v(out)", "v(out)", "V"),
        ("v(n001,out)", "v(n001)-v(out)", "V"),
        ("i(c1)", "i(vam_c1_1)", "A"),
        ("PR1", "(v(n001)-v(out))*i(vam_r1_1)", "W"),
    ]
    assert set(nl.spreads) == {"R1", "R2", "C1"}  # default tolerances 5 % and 10 %


def test_netlist_errors():
    b = Builder()
    b.add("resistor", "R1", ["a", "b"])
    with pytest.raises(SchematicError, match="terra"):
        build_netlist(b.sch)
    b.add("vdc", "V1", ["a", "0"])
    with pytest.raises(SchematicError, match="análise"):
        build_netlist(b.sch)
    b.analysis("dc", source="R1")
    with pytest.raises(SchematicError, match="não é uma fonte"):
        build_netlist(b.sch)
    with pytest.raises(SchematicError, match="componentes"):
        build_netlist(Schematic())
    with pytest.raises(ValueError, match="repetido"):
        Schematic(
            components=[
                Component(id="1", kind="resistor", ref="R1", x=0, y=0),
                Component(id="2", kind="resistor", ref="r1", x=9, y=0),
            ]
        )


def test_every_kind_emits_a_netlist():
    b = Builder()
    for sym in SYMBOLS.values():
        if sym.kind in ("ground", "subckt"):
            continue
        nodes = [f"{sym.kind}_{p.name}" for p in sym.pins]
        nodes[-1] = "0"
        b.add(sym.kind, f"{sym.ref_prefix or sym.prefix}{sym.kind}", nodes)
    b.add("subckt", "Xs", ["s1", "0"], model="FOO", pins="a b")
    b.sch.directives = ".subckt FOO a b\nR1 a b 1k\n.ends"
    b.analysis("op").analysis("tran", tstop="1m").analysis("ac")
    nl = build_netlist(b.sch)
    text = nl.text
    for frag in (
        "SIN(0 179.6",  # three-phase: 127 V rms
        "PULSE(0 5 0 1n 1n 0.5m 1m)",
        "PWL(0 0 1m 1 2m 1)",
        "K_Ttransformer L_Ttransformer_p L_Ttransformer_s 0.999",
        ".model SW_",
        "NPN(BF=100 IS=1e-14)",
        "NMOS(LEVEL=1 VTO=2 KP=20m LAMBDA=0)",
        "NJF(VTO=-2 BETA=1m LAMBDA=0)",
        ".subckt OG_",
        ".subckt THG_",
        ".subckt IGG_",
        ".subckt ZG_",
        "Xs s1 0 FOO",
    ):
        assert frag in text, frag


def test_noise_and_dc_cards():
    b = Builder()
    b.add("vsin", "VIN", ["in", "0"])
    b.add("resistor", "R1", ["in", "out"], value="10k")
    b.add("resistor", "R2", ["out", "0"], value="10k")
    b.analysis("noise", output="out", source="VIN", points="5").analysis(
        "dc",
        source="VIN",
        start="0",
        stop="1",
        step="0.5",
        source2="temp",
        start2="0",
        stop2="50",
        step2="25",
    )
    b.analysis("tran", tstop="1m", tmax="1u", uic="sim")
    text = build_netlist(b.sch).text
    assert ".noise v(out) VIN dec 5 10 1meg" in text
    assert ".dc VIN 0 1 0.5 temp 0 50 25" in text
    assert ".tran 1u 1m 0 1u uic" in text


def test_zero_tran_step_is_replaced():
    """LTspice netlists often write `.tran 0 3m`; ngspice requires TSTEP > 0."""
    b = Builder()
    b.add("vdc", "V1", ["in", "0"], dc="1")
    b.add("resistor", "R1", ["in", "0"], value="1k")
    b.analysis("tran", tstep="0", tstop="3m")
    text = build_netlist(b.sch, {}).text
    assert ".tran 3u 3m" in text
