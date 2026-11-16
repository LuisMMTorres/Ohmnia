"""KiCad netlist export: structure, connectivity, pin mapping, filtering of model elements."""

from __future__ import annotations

import re

from circuitos.reports.kicad import parse, to_kicad

NETLIST = """ponte de teste
V1 ac1 ac2 SIN(0 17 60)
Rsec ac1 a 0.2
D1 a out DMOD
D2 ac2 out DMOD
D3 0 a DMOD
D4 0 ac2 DMOD
C1 out 0 2200u
Rload out 0 12
Q1 c b e QMOD
M1 d g s s MMOD
X1 in- in+ out OPAMP params: gain=1
.model DMOD D(IS=1n)
.subckt OPAMP a b c
R1 a b 1k
.ends
.tran 1u 1m
.end
"""


def _sexpr_balanced(text: str) -> bool:
    depth = 0
    in_str = False
    prev = ""
    for ch in text:
        if ch == '"' and prev != "\\":
            in_str = not in_str
        elif not in_str:
            depth += ch == "("
            depth -= ch == ")"
            if depth < 0:
                return False
        prev = ch
    return depth == 0 and not in_str


def test_parse_keeps_physical_parts_only() -> None:
    parts, skipped, _ = parse(NETLIST)
    refs = [p.ref for p in parts]
    assert refs == ["Rsec", "D1", "D2", "D3", "D4", "C1", "Rload", "Q1", "M1", "X1"]
    assert skipped == ["V1"]
    x1 = parts[-1]
    assert x1.nodes == ["in-", "in+", "out"] and x1.value == "OPAMP"


def test_export_is_balanced_and_maps_pins() -> None:
    text = to_kicad(NETLIST, "Ponte", keep={"D1-D4", "C1"}, packages={"D1-D4": "DO-41 (DO-204AL)"})
    assert _sexpr_balanced(text)
    assert '(ref "D3")' in text and '(ref "Rsec")' not in text and '(ref "Rload")' not in text
    assert "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal" in text
    assert "encapsulamento do catálogo (DO-41 (DO-204AL))" in text
    # D1 anode on node "a" → KiCad pin 2 (anode); cathode on "out" → pin 1
    out_net = re.search(r'\(name "/out"\)(.*)', text)
    assert out_net is not None
    assert '(node (ref "D1") (pin "1"))' in out_net.group(1)
    a_net = re.search(r'\(name "/a"\)(.*)', text)
    assert a_net is not None and '(node (ref "D1") (pin "2"))' in a_net.group(1)
    assert '(name "/GND")' in text  # node 0
    assert "Rload" in text and "Rsec" in text  # listed as left out in the header comment


def test_transistors_ask_for_pinout_confirmation() -> None:
    text = to_kicad(NETLIST, "t")
    assert _sexpr_balanced(text)
    assert text.count("confirmar a ordem dos terminais") == 2  # Q1 and M1
    assert '(part "Q_NPN_BCE")' in text and '(part "Q_NMOS_GDS")' in text


DESIGN = """retificador
VS a b SIN(0 12 60)
VSD1 a d1 0
XD1 d1 p DIODE
XD2 b p DIODE
XD3 0 a DIODE
XD4 0 b DIODE
C1 p 0 0.015 IC=12
RL p 0 12
XQ in sw g QSW
.subckt DIODE a k
BD a k I = 0
.ends
.subckt QSW d s g
S1 d s g 0 SW
.ends
"""


def test_design_netlist_subcircuits_ammeters_and_bom_names() -> None:
    text = to_kicad(DESIGN, "Ponte", keep={"D1–D4", "C1", "Q1", "TR1"})
    assert _sexpr_balanced(text)
    for ref in ("D1", "D2", "D3", "D4", "C1", "Q1"):
        assert f'(comp (ref "{ref}")' in text, ref
    assert '(ref "RL")' not in text.split("(nets")[0]
    # VSD1 is a 0 V ammeter: D1's anode and D3's cathode are the same node
    a_net = re.search(r'\(name "/a"\)(.*)', text)
    assert a_net is not None
    assert '(node (ref "D1") (pin "2"))' in a_net.group(1)
    assert '(node (ref "D3") (pin "1"))' in a_net.group(1)
    assert "/d1" not in text
    # MOSFET switch subcircuit mapped by its pin names d, s, g
    assert '(part "Q_NMOS_GDS")' in text
    sw = re.search(r'\(name "/sw"\)(.*)', text)
    assert sw is not None and '(node (ref "Q1") (pin "3"))' in sw.group(1)
