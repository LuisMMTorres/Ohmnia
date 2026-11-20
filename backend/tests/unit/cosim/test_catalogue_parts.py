"""A catalogue part placed with a co-simulation symbol brings its datasheet values."""

from __future__ import annotations

from pathlib import Path

import pytest

from circuitos.components.repository import load_record_file
from circuitos.schematic.cosim_symbols import CATALOGUE_PARAMS
from circuitos.schematic.library import SYMBOLS
from circuitos.schematic.model import Analysis
from circuitos.schematic.netlist import SchematicError, build_netlist
from tests.unit.schematic.helpers import Builder

CATALOG = Path(__file__).parents[4] / "data" / "components"


def test_potentiometer_takes_the_resistance_of_the_part():
    """Bourns 3296W-1-103LF: code 103 = 10 kΩ (Standard Resistance Table, p. 1)."""
    rec = load_record_file(CATALOG / "resistor" / "bourns-3296w-1-103lf.yaml")
    assert rec.parameters["R"].typ == 10000
    b = Builder("pot")
    b.add("vdc", "V1", ["a", "0"], dc="5")
    # the symbol default (10k) is replaced on purpose by a wrong value: the part must win
    b.add("potentiometer", "P1", ["a", "0", "w"], part_id=str(rec.id), r="1", pos="0.5")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "1m"})]
    nl = build_netlist(b.sch, {str(rec.id): rec})
    line = next(x for x in nl.text.splitlines() if x.lower().startswith("bp1_a"))
    assert "((10000)*(" in line


def test_part_of_another_category_is_refused():
    rec = load_record_file(CATALOG / "resistor" / "bourns-3296w-1-103lf.yaml")
    b = Builder("pot")
    b.add("vdc", "V1", ["a", "0"], dc="5")
    b.add("acs712", "S1", ["a", "0", "v5", "out", "0"], part_id=str(rec.id))
    with pytest.raises(SchematicError, match="não serve"):
        build_netlist(b.sch, {str(rec.id): rec})


def test_every_mapped_symbol_lists_its_categories():
    for kind, (cats, mapping) in CATALOGUE_PARAMS.items():
        assert SYMBOLS[kind].catalogue == cats
        names = {p.name for p in SYMBOLS[kind].params}
        assert set(mapping) <= names, kind


@pytest.mark.ngspice
def test_dc_motor_no_load_speed_matches_its_equation():
    """FAULHABER 2224U012SR (eShop table): at 12 V without load the simulated speed equals the
    steady state of the model, ω = V / (kE + R·b/kM) with b = kM·I0/ω0 (AS-, tol. 0,5 %), and
    stays within 2 % of the published no-load speed n0 = 7810 min⁻¹."""
    import math

    import numpy as np

    from circuitos.schematic.runs import SchematicPlan
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")

    rec = load_record_file(CATALOG / "motor" / "faulhaber-2224u012sr.yaml")
    b = Builder("motor")
    b.add("vdc", "V1", ["a", "0"], dc="12")
    b.add("dc_motor", "M1", ["a", "0"], part_id=str(rec.id))
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "0.2", "tmax": "100u"})]
    res = SchematicPlan(b.sch, {str(rec.id): rec}).execute(SharedNgspiceBackend())
    tran = next(p for p in res.plots if p.kind == "tran")
    w = float(np.asarray(tran.vectors["v(m1_w)"].data)[-1])
    p = rec.parameters
    r, ke = p["R_a"].typ, p["k_E"].typ * 1e-3 * 60 / (2 * math.pi)
    km, i0, w0 = p["k_M"].typ * 1e-3, p["I0"].typ, p["n0"].typ * 2 * math.pi / 60
    bv = km * i0 / w0
    assert w == pytest.approx(12 / (ke + r * bv / km), rel=5e-3)
    assert w * 60 / (2 * math.pi) == pytest.approx(7810, rel=0.02)
