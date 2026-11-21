"""Elements of a design netlist, value edits and probes added by the user."""

import pytest

from circuitos.design.base import Circuit
from circuitos.design.netlist_edit import UserProbe, add_probes, apply_overrides, elements, nodes

NET = "\n".join(
    [
        ".subckt DIODE a k",
        "BD a k I = v(a,k) * 1u",
        ".ends",
        "VS a b SIN(0 17 60)",
        "VSD1 a d1 0",
        "XD1 d1 p DIODE",
        "XD2 b p DIODE",
        "C1 p 0 1000u IC=15",
        "RL p 0 12",
        "Q1 c bb e QMOD",
    ]
)


def test_elements_outside_subcircuits():
    els = {e.name: e for e in elements(NET)}
    assert "BD" not in els  # inside the .subckt
    assert els["XD1"].nodes == ["d1", "p"] and els["XD1"].edit == "none"
    assert els["C1"].value == "1000u" and els["C1"].edit == "value"
    assert els["VS"].edit == "source" and els["VS"].value == "SIN(0 17 60)"
    assert els["VSD1"].sense and els["VSD1"].edit == "none"
    assert els["Q1"].pins == ["coletor", "base", "emissor"]
    assert nodes(NET)[:3] == ["a", "b", "d1"]


def test_override_keeps_the_initial_condition():
    out = apply_overrides(NET, {"C1": "2200u", "VS": "SIN(0 20 50)"})
    assert "C1 p 0 2200u IC=15" in out
    assert "VS a b SIN(0 20 50)" in out
    with pytest.raises(ValueError):
        apply_overrides(NET, {"XD1": "1"})
    with pytest.raises(ValueError):
        apply_overrides(NET, {"R9": "1k"})
    with pytest.raises(ValueError):
        apply_overrides(NET, {"RL": ".include x"})


def test_probes_add_sense_sources_and_ports():
    circuit = Circuit(title="t", netlist=NET)
    out, powers = add_probes(
        circuit,
        [
            UserProbe(kind="v", a="p"),
            UserProbe(kind="vdiff", a="a", b="b"),
            UserProbe(kind="i", a="RL"),
            UserProbe(kind="p", a="C1"),
            UserProbe(kind="i", a="VS"),
        ],
    )
    assert out.probes["Tensão no nó p"] == "v(p)"
    assert out.probes["Tensão a − b"] == "v(a)-v(b)"
    assert out.probes["Corrente em RL"] == "i(vprb1)"
    assert out.probes["Corrente em VS"] == "i(vs)"
    assert "RL p_prb1 0 12" in out.netlist and "VPRB1 p p_prb1 0" in out.netlist
    assert powers == ["C1"]
    port = out.powers["C1"]
    assert port.voltage == "v(p)" and port.current == "i(vprb2)"
    assert "C1 p_prb2 0 1000u IC=15" in out.netlist
    with pytest.raises(ValueError):
        add_probes(circuit, [UserProbe(kind="v", a="nada")])
    with pytest.raises(ValueError):
        add_probes(circuit, [UserProbe(kind="vdiff", a="0", b="0")])
