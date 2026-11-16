"""Drive symbols in the netlist: catalogue parts, time step, contactor (Fase 11 leftovers)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from circuitos.components.repository import load_record_file
from circuitos.schematic.drive_symbols import DRIVE_SYMBOLS, max_step
from circuitos.schematic.library import SYMBOLS
from circuitos.schematic.model import Analysis
from circuitos.schematic.netlist import build_netlist
from circuitos.schematic.runs import SchematicPlan
from tests.unit.schematic.helpers import Builder

CATALOG = Path(__file__).parents[4] / "data" / "components"


def test_drive_symbols_are_in_the_library():
    for sym in DRIVE_SYMBOLS:
        assert SYMBOLS[sym.kind] is not None
    assert SYMBOLS["stepper_motor"].catalogue == ("motor.stepper",)


def test_stepper_part_brings_its_datasheet_values():
    """17HS19-2004S1 (StepperOnline, p. 1): 1,40 Ω, 3,00 mH, 82 g·cm², 0,59 N·m at 2,00 A."""
    rec = load_record_file(CATALOG / "motor" / "stepperonline-omc-17hs19-2004s1.yaml")
    b = Builder("passo")
    b.add("stepper_motor", "M1", ["a1", "a2", "b1", "b2"], part_id=str(rec.id), r="99", km="9")
    b.add("resistor", "R1", ["a1", "a2"], value="1")
    b.add("resistor", "R2", ["b1", "b2"], value="1")
    b.add("resistor", "R3", ["a2", "0"], value="1")
    b.add("resistor", "R4", ["b2", "0"], value="1")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "1m"})]
    text = build_netlist(b.sch, {str(rec.id): rec}).text.lower()
    assert "- 1.4*v(m1_ia)" in text
    assert "/0.003" in text
    assert "c m1_j m1_w 0 8.2e-06".replace(" ", "", 1) in text
    km = 0.59 / (math.sqrt(2) * 2.0)
    assert f"{km:.6g}*(-v(m1_ia)" in text


def test_max_step_follows_the_drives():
    b = Builder("passo")
    b.add("vfd", "INV1", ["ai", "0", "run", "0", "u", "v", "w"])
    assert max_step(b.sch.components) == pytest.approx(1 / 4800)
    b.sch.components[0].params["mode"] = "SPWM"
    assert max_step(b.sch.components) == pytest.approx(1 / (40 * 5000))
    assert max_step([]) is None


@pytest.mark.ngspice
def test_contactor_closes_at_75_and_opens_at_40_percent():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    b = Builder("contator")
    # coil: 0 → 24 V in 1 s, then back to 0 in 1 s
    b.add("vpwl", "V1", ["k", "0"], points="0 0 1 24 2 0")
    b.add("vdc", "V2", ["l", "0"], dc="10")
    b.add("contactor", "K1", ["k", "0", "l", "t1", "l", "t2", "l", "t3"])
    for i in (1, 2, 3):
        b.add("resistor", f"R{i}", [f"t{i}", "0"], value="100")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "2", "tmax": "1m"})]
    res = SchematicPlan(b.sch).execute(SharedNgspiceBackend())
    tran = next(p for p in res.plots if p.kind == "tran")
    t = np.asarray(tran.vectors[tran.scale].data)
    v = np.asarray(tran.vectors["v(t2)"].data)
    closed = t[v > 5]
    assert closed[0] == pytest.approx(0.75, abs=0.01)  # 75 % of 24 V on the rising ramp
    assert closed[-1] == pytest.approx(1.6, abs=0.01)  # 40 % on the falling ramp
