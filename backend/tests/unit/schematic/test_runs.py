import math

import numpy as np
import pytest

from circuitos.schematic.model import ScalarMeasure, Sweep
from circuitos.schematic.netlist import SchematicError
from circuitos.schematic.runs import SchematicPlan, scalar_measure, statistics, sweep_values
from circuitos.simulation.backend import make_backend

from .helpers import Builder


def divider(r1="1k", r2="1k", tol="5"):
    b = Builder("divisor")
    b.add("vdc", "V1", ["in", "0"], dc="10")
    b.add("resistor", "R1", ["in", "out"], value=r1, tol=tol)
    b.add("resistor", "R2", ["out", "0"], value=r2, tol=tol)
    b.analysis("op")
    return b


def test_sweep_values():
    assert sweep_values(Sweep(spacing="lin", start="1", stop="2", step="0.25")) == pytest.approx(
        [1, 1.25, 1.5, 1.75, 2]
    )
    assert sweep_values(Sweep(spacing="dec", start="1", stop="100", points=2)) == pytest.approx(
        [1, math.sqrt(10), 10, 10 * math.sqrt(10), 100]
    )
    assert sweep_values(Sweep(spacing="list", values=["1k", "2.2k"])) == [1000, 2200]
    with pytest.raises(SchematicError, match="passo"):
        sweep_values(Sweep(spacing="lin", start="1", stop="2"))
    with pytest.raises(SchematicError, match="positivos"):
        sweep_values(Sweep(spacing="oct", start="0", stop="2"))
    with pytest.raises(SchematicError, match="máximo"):
        sweep_values(Sweep(spacing="lin", start="0", stop="1", step="1u"))


@pytest.mark.ngspice
def test_step_temperature_and_param_runs():
    b = divider()
    b.sch.sweep = Sweep(kind="step", target="R2.value", spacing="list", values=["1k", "3k"])
    res = SchematicPlan(b.sch).execute(make_backend())
    assert [r.label for r in res.runs] == ["R2.value = 1k", "R2.value = 3k"]
    outs = [p["v(out)"].data[0] for p in res.plots]
    assert outs == pytest.approx([5.0, 7.5])
    assert [p.name for p in res.plots] == [f"{res.plots[0].base} r0", f"{res.plots[0].base} r1"]

    b.sch.params = {"RX": "1k"}
    b.sch.components[2].params["value"] = "{RX}"
    b.sch.sweep = Sweep(kind="step", target="param:RX", spacing="list", values=["1k", "9k"])
    res = SchematicPlan(b.sch).execute(make_backend())
    assert [p["v(out)"].data[0] for p in res.plots] == pytest.approx([5.0, 9.0])

    t = Builder("diodo")
    t.add("idc", "I1", ["0", "a"], dc="1m")
    t.add("diode", "D1", ["a", "0"])
    t.analysis("op")
    t.sch.sweep = Sweep(kind="temp", spacing="list", values=["0", "100"])
    res = SchematicPlan(t.sch).execute(make_backend())
    v0, v100 = (p["v(a)"].data[0] for p in res.plots)
    assert v100 < v0  # VF falls with temperature
    with pytest.raises(SchematicError, match="parâmetro"):
        b.sch.sweep = Sweep(kind="step", target="R1.nada", spacing="list", values=["1"])
        SchematicPlan(b.sch).runs()


@pytest.mark.ngspice
def test_monte_carlo_stays_within_tolerances_and_is_reproducible():
    b = divider()
    b.sch.sweep = Sweep(kind="montecarlo", runs=40, seed=7, distribution="uniform")
    plan = SchematicPlan(b.sch)
    res = plan.execute(make_backend())
    assert len(res.runs) == 41 and res.runs[0].label == "nominal"
    m = ScalarMeasure(analysis="op", vector="v(out)")
    values = [scalar_measure(p, m) for p in res.plots]
    assert values[0] == pytest.approx(5.0)
    # analytic limits: R2/(R1+R2) with ±5 % on each
    lo, hi = 10 * 0.95 / (0.95 + 1.05), 10 * 1.05 / (1.05 + 0.95)
    assert all(lo - 1e-9 <= v <= hi + 1e-9 for v in values)
    assert len(set(np.round(values, 9))) > 30
    again = SchematicPlan(b.sch).execute(make_backend())
    assert [r.values for r in again.runs] == [r.values for r in res.runs]
    st = statistics(values)
    assert st["min"] >= lo and st["max"] <= hi and st["n"] == 41
    assert res.summary["spreads"][0]["parameter"] == "R1.value"


@pytest.mark.ngspice
def test_worst_case_reaches_the_analytic_extremes():
    b = divider()
    b.sch.sweep = Sweep(kind="worstcase", measure=ScalarMeasure(analysis="op", vector="v(out)"))
    res = SchematicPlan(b.sch).execute(make_backend())
    s = res.summary
    assert s["nominal"] == pytest.approx(5.0)
    assert s["max"] == pytest.approx(10 * 1.05 / (1.05 + 0.95))
    assert s["min"] == pytest.approx(10 * 0.95 / (0.95 + 1.05))
    dirs = {r["parameter"]: r["direction"] for r in s["sensitivities"]}
    assert dirs == {"R1.value": "−", "R2.value": "+"}
    assert [r.label for r in res.runs][-2:] == ["pior caso máx.", "pior caso mín."]


def test_errors_without_tolerance_or_measure():
    b = divider(tol="0")
    b.sch.sweep = Sweep(kind="montecarlo", runs=3)
    with pytest.raises(SchematicError, match="tolerância"):
        SchematicPlan(b.sch).runs()
    b.sch.sweep = Sweep(kind="worstcase")
    with pytest.raises(SchematicError, match="medida"):
        SchematicPlan(b.sch).execute(None)


@pytest.mark.ngspice
def test_scalar_measures_on_tran_and_ac():
    b = Builder("rc")
    b.add("vsin", "V1", ["in", "0"], amplitude="1", freq="1k")
    b.add("resistor", "R1", ["in", "out"], value="1k")
    b.add("capacitor", "C1", ["out", "0"], value="159.155n")
    b.analysis("tran", tstop="10m", tmax="5u").analysis("ac", points="100")
    res = SchematicPlan(b.sch).execute(make_backend())
    tran, ac = res.plot("tran"), res.plot("ac")

    def m(kind, plot, **kw):
        return scalar_measure(
            plot, ScalarMeasure(analysis=plot.kind, vector="v(out)", kind=kind, **kw)
        )

    # fc = 1/(2πRC) = 1 kHz: |H| = −3,01 dB and −45° (first-order low-pass)
    assert m("mag_db_at", ac, at="1k") == pytest.approx(-3.0103, abs=0.01)
    assert m("phase_at", ac, at="1k") == pytest.approx(-45.0, abs=0.1)
    assert m("frequency", tran, start="5m") == pytest.approx(1000.0, rel=1e-3)
    assert m("pp", tran, start="5m") == pytest.approx(2 / math.sqrt(2), rel=2e-3)
    assert m("rms", tran, start="5m") == pytest.approx(0.5, rel=2e-3)
    assert m("mean", tran, start="5m") == pytest.approx(0.0, abs=2e-3)
    assert m("at", tran, at="5m") == pytest.approx(m("at", tran, at="5m"))
    with pytest.raises(SchematicError, match="não existe"):
        scalar_measure(tran, ScalarMeasure(analysis="tran", vector="v(x)"))
