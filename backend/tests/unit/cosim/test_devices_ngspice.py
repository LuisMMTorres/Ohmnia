"""Sensor and actuator models not covered by the examples (ngspice)."""

from __future__ import annotations

import numpy as np
import pytest

from circuitos.schematic.cosim_symbols import stimulus
from circuitos.schematic.model import Analysis
from circuitos.schematic.runs import SchematicPlan
from tests.unit.schematic.helpers import Builder

pytestmark = pytest.mark.ngspice


@pytest.fixture(scope="module")
def backend():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    return SharedNgspiceBackend()


def _tran(b: Builder, backend, tstop: str):  # type: ignore[no-untyped-def]
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": tstop, "tmax": "1m"})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    return tran, tran.vectors[tran.scale].data


def test_stimulus_forms():
    assert stimulus("25") == "25"
    assert stimulus("v(H1_temp)") == "v(h1_temp)"
    assert stimulus("0 25 10 80").startswith("pwl(time, -1e+09, 25, 0, 25, 10, 80, ")
    with pytest.raises(ValueError):
        stimulus("0 25 10")


def test_pt100_follows_iec_60751(backend):
    b = Builder("pt100")
    b.add("idc", "I1", ["0", "x"], dc="1m")  # 1 mA into the RTD
    b.add("pt100", "RT1", ["x", "0"], temp="0 0 1 100")
    tran, t = _tran(b, backend, "1")
    v = tran.vectors["v(x)"].data
    assert np.interp(0.0, t, v) == pytest.approx(0.100, rel=1e-3)  # 100 Ω
    assert np.interp(1.0, t, v) == pytest.approx(0.1385, rel=1e-3)  # 138,5 Ω at 100 °C


def test_potentiometer_divides_by_position(backend):
    b = Builder("pot")
    b.add("vdc", "V1", ["a", "0"], dc="10")
    b.add("potentiometer", "P1", ["a", "0", "w"], r="10k", pos="0 0.2 1 0.8")
    b.add("resistor", "RL", ["w", "0"], value="1g")
    tran, t = _tran(b, backend, "1")
    v = tran.vectors["v(w)"].data
    assert np.interp(0.0, t, v) == pytest.approx(8.0, rel=1e-3)  # 20 % from a: 80 % of 10 V
    assert np.interp(1.0, t, v) == pytest.approx(2.0, rel=1e-3)


def test_relay_switches_with_the_coil(backend):
    b = Builder("rele")
    b.add("vpwl", "V1", ["c", "0"], points="0 0 0.5 0 0.501 5")
    b.add("vdc", "V2", ["com", "0"], dc="12")
    b.add("relay", "K1", ["c", "0", "com", "na", "nf"])
    b.add("resistor", "R1", ["na", "0"], value="100")
    b.add("resistor", "R2", ["nf", "0"], value="100")
    tran, t = _tran(b, backend, "1")
    na, nf = tran.vectors["v(na)"].data, tran.vectors["v(nf)"].data
    assert np.interp(0.25, t, nf) == pytest.approx(12, rel=0.01)
    assert np.interp(0.25, t, na) == pytest.approx(0, abs=0.01)
    assert np.interp(0.9, t, na) == pytest.approx(12, rel=0.01)
    assert np.interp(0.9, t, nf) == pytest.approx(0, abs=0.01)


@pytest.mark.parametrize(
    ("kind", "before", "after"), [("tact_switch", 0.0, 5.0), ("push_nc", 5.0, 0.0)]
)
def test_push_buttons_follow_state(backend, kind, before, after):
    b = Builder(kind)
    b.add("vdc", "V1", ["a", "0"], dc="5")
    b.add(kind, "SW1", ["a", "x"], state="0 0 0.001 0 0.00101 1", ron="0.1")
    b.add("resistor", "R1", ["x", "0"], value="1k")
    tran, t = _tran(b, backend, "2m")
    v = tran.vectors["v(x)"].data
    assert np.interp(0.5e-3, t, v) == pytest.approx(before, abs=1e-2)
    assert np.interp(1.8e-3, t, v) == pytest.approx(after, abs=1e-2)


def test_tact_switch4_pairs_and_press(backend):
    b = Builder("tact4")
    b.add("vdc", "V1", ["a", "0"], dc="5")
    b.add("tact_switch4", "SW1", ["a", "a2", "x", "x2"], state="0 0 0.001 0 0.00101 1")
    b.add("resistor", "R1", ["x2", "0"], value="1k")
    b.add("resistor", "R2", ["a2", "0"], value="1k")
    tran, t = _tran(b, backend, "2m")
    assert np.interp(0.5e-3, t, tran.vectors["v(a2)"].data) == pytest.approx(5.0, abs=1e-2)
    assert np.interp(0.5e-3, t, tran.vectors["v(x2)"].data) == pytest.approx(0.0, abs=1e-2)
    assert np.interp(1.8e-3, t, tran.vectors["v(x2)"].data) == pytest.approx(5.0, abs=1e-2)
