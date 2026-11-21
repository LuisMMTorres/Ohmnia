"""Nameplate transformers: sizing (unit) and wye/delta behaviour in ngspice."""

from __future__ import annotations

import math

import numpy as np
import pytest

from circuitos.core.calc import CalcLog
from circuitos.schematic import transformers as tr
from circuitos.schematic.model import Analysis
from circuitos.schematic.runs import SchematicPlan
from tests.unit.schematic.helpers import Builder


def test_size_from_nameplate():
    log = CalcLog()
    w = tr.size("T1", 220, 12, None, 50, 60, 5, 2, log)
    assert w.turns == pytest.approx(220 / 12)
    # Im = 5 % of 50/220 A; Lm = Vp/(2πf·Im)
    assert w.lp == pytest.approx(220 / (2 * math.pi * 60 * 0.05 * 50 / 220))
    assert w.ls == pytest.approx(w.lp / (220 / 12) ** 2)
    # 1 W of copper losses, half in each winding
    assert w.rp * (50 / 220) ** 2 == pytest.approx(0.5)
    assert w.rs * (50 / 12) ** 2 == pytest.approx(0.5)
    assert {s.id for s in log} == {"T1_a", "T1_lm", "T1_rcu"}


def test_given_turns_ratio_wins():
    w = tr.size("T1", 220, 12, 10, 50, 60, 5, 2, CalcLog())
    assert w.vs == pytest.approx(22)


def test_winding_voltage():
    assert tr.winding_voltage(380, "D") == 380
    assert tr.winding_voltage(380, "Y") == pytest.approx(380 / math.sqrt(3))


@pytest.mark.parametrize("bad", [dict(vp=0), dict(imag_pct=0), dict(turns=-1)])
def test_size_rejects(bad):
    args = dict(vp=220, vs=12, turns=None, s_winding=50, freq=60, imag_pct=5, rcu_pct=2)
    args.update(bad)
    with pytest.raises(tr.TransformerError):
        tr.size("T1", log=CalcLog(), **args)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def backend():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    return SharedNgspiceBackend()


def _rms_phase(t, v, f=60.0, cycles=3):  # type: ignore[no-untyped-def]
    """RMS and phase (degrees, sine reference) over the last `cycles` periods."""
    t0 = t[-1] - cycles / f
    tt = np.linspace(t0, t[-1], 4000)
    vv = np.interp(tt, t, v)
    w = 2 * np.pi * f
    a = 2 * np.mean(vv * np.sin(w * tt))
    b = 2 * np.mean(vv * np.cos(w * tt))
    return math.hypot(a, b) / math.sqrt(2), math.degrees(math.atan2(b, a))


@pytest.mark.ngspice
@pytest.mark.parametrize(
    ("conn_p", "conn_s", "shift"), [("D", "Y", 30), ("Y", "D", -30), ("Y", "Y", 0)]
)
def test_three_phase_groups(backend, conn_p, conn_s, shift):
    """380 V → 220 V, 3 kVA, 100 Ω per phase in wye: secondary line voltage near 220 V and the
    angle of the vector group (Dyn11 leads 30°, Yd1 lags 30°, Yy0 in phase)."""
    b = Builder("t3")
    b.add("v3ph", "V1", ["a", "b", "c", "0"], vrms=str(380 / math.sqrt(3)))
    b.add("transformer_3ph", "T1", ["a", "b", "c", "h0", "x1", "x2", "x3", "x0"],
          conn_p=conn_p, conn_s=conn_s)  # fmt: skip
    for i, x in enumerate(("x1", "x2", "x3")):
        b.add("resistor", f"R{i}", [x, "n"], value="100")
    b.add("resistor", "RG", ["n", "0"], value="1m")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "0.3", "tmax": "50u"})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    t = tran.vectors[tran.scale].data
    vx = tran.vectors["v(x1)"].data - tran.vectors["v(x2)"].data
    va = tran.vectors["v(a)"].data - tran.vectors["v(b)"].data
    rms, ph_x = _rms_phase(t, vx)
    _, ph_a = _rms_phase(t, va)
    assert rms == pytest.approx(220, rel=0.03)
    d = (ph_x - ph_a + 180) % 360 - 180
    assert d == pytest.approx(shift, abs=2)


@pytest.mark.ngspice
def test_single_phase_ratio(backend):
    b = Builder("t1")
    b.add("vsin", "V1", ["p", "0"], amplitude=str(220 * math.sqrt(2)), freq="60")
    b.add("transformer_1ph", "T1", ["p", "0", "s", "0"], vp="220", vs="12", sn="50")
    b.add("resistor", "RL", ["s", "0"], value="1k")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "0.2", "tmax": "50u"})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    t = tran.vectors[tran.scale].data
    rms, _ = _rms_phase(t, tran.vectors["v(s)"].data)
    assert rms == pytest.approx(12, rel=0.01)
