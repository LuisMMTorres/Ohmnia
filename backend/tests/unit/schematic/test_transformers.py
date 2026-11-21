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


def test_size_autotransformer():
    """220 V / 127 V, 1 kVA: the series part has (220 − 127)/220 of the turns, the common
    part 127/220; copper losses split between them by their own currents."""
    log = CalcLog()
    w = tr.size_auto("T1", 220, 127, 1000, 60, 3, 1, log)
    l_full = 220 / (2 * math.pi * 60 * 0.03 * 1000 / 220)
    assert w.l_series == pytest.approx(l_full * (93 / 220) ** 2)
    assert w.l_common == pytest.approx(l_full * (127 / 220) ** 2)
    ih, ix = 1000 / 220, 1000 / 127
    assert w.r_series * ih**2 == pytest.approx(5)
    assert w.r_common * (ix - ih) ** 2 == pytest.approx(5)
    assert {s.id for s in log} == {"T1_a", "T1_lm", "T1_rcu"}


@pytest.mark.parametrize("bad", [dict(vx=220), dict(vx=300), dict(vh=0), dict(imag_pct=0)])
def test_size_autotransformer_rejects(bad):
    args = dict(vh=220, vx=127, s_rated=1000, freq=60, imag_pct=3, rcu_pct=1)
    args.update(bad)
    with pytest.raises(tr.TransformerError):
        tr.size_auto("T1", log=CalcLog(), **args)  # type: ignore[arg-type]


def _auto_run(backend, feed: str, load_node: str, load: str):  # type: ignore[no-untyped-def]
    b = Builder("auto")
    vin = 220 if feed == "h" else 127
    b.add("vsin", "V1", [feed, "0"], amplitude=str(vin * math.sqrt(2)), freq="60")
    b.add("autotransformer", "T1", ["h", "x", "0"])
    b.add("resistor", "RL", [load_node, "0"], value=load)
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "0.2", "tmax": "50u"})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    return tran, tran.vectors[tran.scale].data


@pytest.mark.ngspice
def test_autotransformer_steps_down_at_rated_load(backend):
    """220 V → 127 V with the rated 1 kVA load (127²/1000 Ω): output within 2 % (1 % of
    copper losses), and the input current S/VH = 4,55 A (Chapman, 5th ed., ch. 2)."""
    tran, t = _auto_run(backend, "h", "x", f"{127**2 / 1000:.6g}")
    rms, _ = _rms_phase(t, tran.vectors["v(x)"].data)
    assert rms == pytest.approx(127, rel=0.02)
    i_in, _ = _rms_phase(t, tran.vectors["i(v1)"].data)
    assert i_in == pytest.approx(1000 / 220 * rms / 127, rel=0.03)


@pytest.mark.ngspice
def test_autotransformer_steps_up(backend):
    """127 V fed at X, light load (10 kΩ) on H: 220 V within 1 %."""
    tran, t = _auto_run(backend, "x", "h", "10k")
    rms, _ = _rms_phase(t, tran.vectors["v(h)"].data)
    assert rms == pytest.approx(220, rel=0.01)


def _tran_rms(backend, b, node_pairs):  # type: ignore[no-untyped-def]
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "0.2", "tmax": "50u"})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    t = tran.vectors[tran.scale].data

    def v(n):  # type: ignore[no-untyped-def]
        return tran.vectors[f"v({n})"].data if n != "0" else 0 * t

    return [_rms_phase(t, v(a) - v(c))[0] for a, c in node_pairs]


@pytest.mark.ngspice
@pytest.mark.parametrize(
    ("series", "vin", "vout", "load"),
    [(True, 230, 24, "57.6"), (False, 115, 12, "2.88")],
)
def test_four_coil_series_and_parallel(backend, series, vin, vout, load):
    """115 V + 115 V / 12 V + 12 V, 50 VA: primary and secondary both in series (230 V → 24 V)
    or both in parallel (115 V → 12 V), rated load (V²/S): output within 3 % (2 % of copper
    losses split between the coils)."""
    b = Builder("t4")
    b.add("vsin", "V1", ["p", "0"], amplitude=str(vin * math.sqrt(2)), freq="60")
    if series:
        pins = ["p", "m", "m", "0", "s", "k", "k", "0"]
    else:
        pins = ["p", "0", "p", "0", "s", "0", "s", "0"]
    b.add("transformer_1ph_4", "T1", pins)
    b.add("resistor", "RL", ["s", "0"], value=load)
    (rms,) = _tran_rms(backend, b, [("s", "0")])
    assert rms == pytest.approx(vout, rel=0.03)


@pytest.mark.ngspice
def test_open_three_phase_closed_delta_wye(backend):
    """Coils of 380 V / 127 V closed outside in delta (primary, 380 V line) and wye
    (secondary): 220 V line on the secondary, as the Dyn transformer, within 3 %."""
    b = Builder("t3o")
    b.add("v3ph", "V1", ["a", "b", "c", "0"], vrms=str(380 / math.sqrt(3)))
    # delta: 1U2-1V1, 1V2-1W1, 1W2-1U1; wye: 2U2-2V2-2W2 = n
    b.add("transformer_3ph_open", "T1",
          ["a", "b", "b", "c", "c", "a", "x1", "n", "x2", "n", "x3", "n"])  # fmt: skip
    for i, x in enumerate(("x1", "x2", "x3")):
        b.add("resistor", f"R{i}", [x, "n"], value="100")
    b.add("resistor", "RG", ["n", "0"], value="1m")
    (rms,) = _tran_rms(backend, b, [("x1", "x2")])
    assert rms == pytest.approx(127 * math.sqrt(3), rel=0.03)
