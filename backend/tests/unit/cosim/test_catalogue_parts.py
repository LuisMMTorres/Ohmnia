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
