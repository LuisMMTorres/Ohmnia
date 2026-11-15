"""SPICE model files: parsing and the ngspice load check. Models here are fictitious."""

from __future__ import annotations

import pytest

from circuitos.datasheets.spice_import import check_model, check_netlist, parse_models

LIB = """\
* Fictitious model library for tests
.MODEL DTESTE D(IS=2.5n RS=0.04 N=1.75
+ BV=400 IBV=5u CJO=30p TT=4u) ; comment
.model QTESTE NPN (IS=1e-14 BF=150 VAF=80)
.SUBCKT XTESTE D G S
M1 D G S S MINT L=1u W=1u
.MODEL MINT NMOS (VTO=3 KP=10)
.ENDS XTESTE
"""


def test_parse_models_and_parameters() -> None:
    models = parse_models(LIB, source_note="teste.lib")
    names = [(m.name, m.kind, m.device) for m in models]
    assert names == [
        ("DTESTE", "model", "D"),
        ("QTESTE", "model", "NPN"),
        ("XTESTE", "subckt", "subckt"),
    ]
    d = models[0]
    assert d.params["IS"] == pytest.approx(2.5e-9)
    assert d.params["CJO"] == pytest.approx(30e-12)
    assert d.params["TT"] == pytest.approx(4e-6)
    assert models[2].pins == ["D", "G", "S"]
    assert ".ENDS" in models[2].text
    assert all(m.origin == "fabricante" and m.source_note == "teste.lib" for m in models)


def test_check_netlists_instantiate_each_kind() -> None:
    models = parse_models(LIB)
    assert "D1 a 0 DTESTE" in check_netlist(models[0])
    assert "Q1 c b 0 QTESTE" in check_netlist(models[1])
    assert "X1 n0 n1 n2 XTESTE" in check_netlist(models[2])


@pytest.mark.ngspice
def test_models_load_in_ngspice() -> None:
    models = parse_models(LIB)
    for m in models:
        result = check_model(m, library=LIB)
        assert result.ok, (m.name, result.log)


@pytest.mark.ngspice
def test_broken_model_is_reported() -> None:
    (bad,) = parse_models(".model DRUIM D(IS=1e-14)")
    bad = bad.model_copy(update={"name": "OUTRO"})  # instance refers to a model that is absent
    assert not check_model(bad, library=".model DRUIM D(IS=1e-14)").ok
