import numpy as np
import pytest

from circuitos.schematic.importer import import_netlist, tokenize
from circuitos.schematic.netlist import build_netlist
from circuitos.simulation.backend import make_backend

CE = """Amplificador emissor comum
VCC vcc 0 DC 12
VIN in 0 DC 0 AC 1 SIN(0 10m 1k)
C1 in b 10u
R1 vcc b 47k
R2 b 0 10k
RC vcc c 2.2k
RE e 0 1k
CE e 0 100u
Q1 c b e QN
.model QN NPN(IS=1e-14 BF=150)
.tran 10u 5m
.ac dec 10 10 10meg
.op
.end
"""


def test_tokenize():
    assert tokenize("V1 a 0 SIN(0, 1 , 1k) ac = 1") == [
        "V1",
        "a",
        "0",
        "SIN",
        "0",
        "1",
        "1k",
        "ac=1",
    ]
    assert tokenize("R1 a b {max(r0, 2)}") == ["R1", "a", "b", "{max(r0, 2)}"]


def test_import_maps_elements_and_cards():
    r = import_netlist(CE)
    sch = r.schematic
    assert r.warnings == []
    assert sch.title == "Amplificador emissor comum"
    kinds = {c.ref: c.kind for c in sch.components}
    assert kinds["Q1"] == "npn" and kinds["VIN"] == "vsin" and kinds["CE"] == "capacitor"
    assert sch.component("VIN").params["amplitude"] == "10m"
    assert [a.kind for a in sch.analyses] == ["tran", "ac", "op"]
    assert ".model QN" in sch.directives
    assert {lb.name for lb in sch.labels} == {"vcc", "in", "b", "c", "e"}


@pytest.mark.ngspice
def test_roundtrip_gives_the_same_simulation():
    backend = make_backend()
    nl = build_netlist(import_netlist(CE).schematic)
    direct, again = backend.run(CE), backend.run(nl.text)
    for kind in ("op", "ac", "tran"):
        a, b = direct.plot(kind), again.plot(kind)
        for v in ("v(c)", "v(b)", "v(e)"):
            assert np.allclose(a[v].data, b[v].data, rtol=1e-9, atol=1e-12), (kind, v)


def test_raw_lines_subckt_param_step_and_warnings():
    text = """titulo
.param R0=1k
.subckt DIV a b o
R1 a o 1k
R2 o b 1k
.ends
V1 in 0 PULSE(0 5 0 1n 1n 1m 2m)
V2 x 0 EXP(0 1 0 1m)
I1 0 y PWL(0 0 1m 1m) r=0
X1 in 0 out DIV
R5 out 0 {R0}
L1 out m 1m
L2 m 0 1m
K1 L1 L2 0.9
E1 e 0 POLY(1) in 0 0 1
G1 g 0 in 0 1m
F1 f 0 V1 2
B1 bb 0 V=v(in)*2
S1 out 0 in 0 SWM
.model SWM SW(VT=1 RON=1 ROFF=1meg)
T1 a 0 b 0 Z0=50 TD=1n
.control
run
.endc
.step param R0 list 1k 2k 4k
.noise v(out) V1 dec 10 1 1meg
.dc V1 0 5 1
.temp 50
.options reltol=1e-4
.include modelos.lib
.end
"""
    r = import_netlist(text)
    sch = r.schematic
    kinds = {c.ref: c.kind for c in sch.components if c.kind != "ground"}
    assert kinds == {
        "V1": "vpulse",
        "I1": "ipwl",
        "X1": "subckt",
        "R5": "resistor",
        "L1": "inductor",
        "L2": "inductor",
        "G1": "vccs",
        "F1": "cccs",
        "B1": "bsource",
        "S1": "switch",
    }
    assert sch.component("X1").params["pins"] == "a b o"
    assert sch.component("I1").params["repeat"] == "sim"
    assert sch.params == {"R0": "1k"}
    assert sch.temperature == "50"
    assert sch.sweep.kind == "step" and sch.sweep.target == "param:R0"
    assert sch.sweep.values == ["1k", "2k", "4k"]
    for raw in ("V2 x 0 EXP", "K1 L1 L2 0.9", "E1 e 0 POLY", "T1 a 0 b 0", ".subckt DIV"):
        assert raw in sch.directives
    joined = " ".join(r.warnings)
    for w in ("EXP", "POLY", ".control", ".include", "T1"):
        assert w in joined
    nl = build_netlist(sch)
    assert "X1 in 0 out DIV" in nl.text and "R5 out 0 {R0}" in nl.text
    assert ".noise v(out) V1 dec 10 1 1meg" in nl.text


def test_first_line_is_the_title():
    r = import_netlist("R1 a 0 1k\nV1 a 0 1\n.op\n")
    assert "título" in r.warnings[0]
    assert [c.ref for c in r.schematic.components if c.kind != "ground"] == ["V1"]
