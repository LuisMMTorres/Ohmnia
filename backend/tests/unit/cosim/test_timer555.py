"""555 timer of the schematic library (behavioural model, TI NE555 SLFS022K).

The astable period is checked against the textbook result for thresholds at 2/3 and 1/3 VCC:
t_H = (RA + RB) C ln 2 (TI SLFS022K, section 7.2.2, with 0.693 = ln 2). During t_L the
capacitor discharges through RB towards the voltage left on DISCH, V_D = VCC r_dis/(RA + r_dis)
(the RA current through the 18,75 Ω switch), so t_L = RB C ln((2/3 VCC − V_D)/(1/3 VCC − V_D)),
which is RB C ln 2 when r_dis → 0. Tolerance 1 %: the 1 ns latch and the time step.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from circuitos.components.repository import load_record_file
from circuitos.schematic.cosim_symbols import catalogue_value
from circuitos.schematic.library import SYMBOLS
from circuitos.schematic.model import Analysis
from circuitos.schematic.netlist import build_netlist
from circuitos.schematic.runs import SchematicPlan
from tests.unit.schematic.helpers import Builder

CATALOG = Path(__file__).parents[4] / "data" / "components"
NE555 = CATALOG / "timer" / "ti-ne555.yaml"


def _astable(b: Builder, vcc: str = "15", reset: str = "vcc") -> None:
    # pins: TRIG, THRES, CONT, DISCH, VCC, RESET, OUT, GND
    b.add("vdc", "V1", ["vcc", "0"], dc=vcc)
    b.add("resistor", "RA", ["vcc", "dis"], value="1k")
    b.add("resistor", "RB", ["dis", "cap"], value="10k")
    b.add("capacitor", "C1", ["cap", "0"], value="100n")
    b.add("capacitor", "C2", ["ctl", "0"], value="10n")
    b.add("resistor", "RL", ["out", "0"], value="1k")
    b.add("timer555", "U1", ["cap", "cap", "ctl", "dis", "vcc", reset, "out", "0"])


def test_symbol_is_listed_with_the_integrated_circuits():
    assert SYMBOLS["timer555"].group == "Circuitos integrados"
    assert SYMBOLS["opamp"].group == "Circuitos integrados"
    assert SYMBOLS["timer555"].catalogue == ("timer",)
    assert [p.name for p in SYMBOLS["timer555"].pins] == [
        "TRIG",
        "THRES",
        "CONT",
        "DISCH",
        "VCC",
        "RESET",
        "OUT",
        "GND",
    ]


def test_catalogue_part_brings_its_datasheet_values():
    """NE555P, TI SLFS022K p. 5 (typical column): values derived from two table points."""
    rec = load_record_file(NE555)
    v = catalogue_value("timer555", rec, lambda name: "?")
    assert float(v("vdrop")) == pytest.approx(15 - 13.3)  # VOH at 100 mA, VCC = 15 V
    assert float(v("roh")) == pytest.approx((13.3 - 12.5) / 0.1)  # VOH at 100 and 200 mA
    assert float(v("rol")) == pytest.approx((0.4 - 0.1) / 0.04)  # VOL at 10 and 50 mA
    assert float(v("rdis")) == pytest.approx(0.15 / 0.008)  # DISCH on at 8 mA
    assert float(v("icc")) == pytest.approx(0.010)
    assert float(v("vreset")) == pytest.approx(0.7)
    assert v("rdiv") == "?"  # not in the datasheet: the symbol default stays


def test_netlist_uses_the_part():
    rec = load_record_file(NE555)
    b = Builder("555")
    _astable(b)
    b.sch.components[-1].part_id = str(rec.id)
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "1m"})]
    nl = build_netlist(b.sch, {str(rec.id): rec})
    assert "ron=18.75" in nl.text


@pytest.mark.ngspice
def test_astable_period_matches_the_datasheet_equations():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    b = Builder("555")
    _astable(b)
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "10m", "tmax": "2u"})]
    res = SchematicPlan(b.sch).execute(SharedNgspiceBackend())
    tran = next(p for p in res.plots if p.kind == "tran")
    t = tran.vectors[tran.scale].data
    out = tran.vectors["v(out)"].data
    cap = tran.vectors["v(cap)"].data
    hi = out > 7
    rise = t[1:][hi[1:] & ~hi[:-1]]
    fall = t[1:][~hi[1:] & hi[:-1]]
    rise, fall = rise[rise > 3e-3], fall[fall > 3e-3]  # after the first (longer) charge
    period = float(np.mean(np.diff(rise)))
    t_high = float(np.mean([f - r for r in rise for f in fall if 0 < f - r < period]))
    th = (1e3 + 10e3) * 100e-9 * math.log(2)
    vd = 15 * 18.75 / (1e3 + 18.75)
    tl = 10e3 * 100e-9 * math.log((10 - vd) / (5 - vd))
    assert t_high == pytest.approx(th, rel=0.01)
    assert period == pytest.approx(th + tl, rel=0.01)
    # capacitor swings between 1/3 and 2/3 of VCC
    late = t > 3e-3
    assert float(cap[late].max()) == pytest.approx(10.0, rel=0.02)
    assert float(cap[late].min()) == pytest.approx(5.0, rel=0.02)
    # output high = VCC − 1,7 V less the drop on 8 Ω at about 13 mA (1 kΩ load)
    assert float(out[late].max()) == pytest.approx(15 - 1.7 - 8 * 13.3 / 1008, rel=0.01)


@pytest.mark.ngspice
def test_reset_low_holds_the_output_low():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    b = Builder("555")
    _astable(b, reset="0")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "5m", "tmax": "5u"})]
    res = SchematicPlan(b.sch).execute(SharedNgspiceBackend())
    tran = next(p for p in res.plots if p.kind == "tran")
    assert float(np.max(tran.vectors["v(out)"].data)) < 0.2
