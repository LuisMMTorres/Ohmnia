"""AS-SIM: free simulator (schematic → netlist → ngspice) against closed-form circuit theory.

Every case goes through the same route as the editor: Schematic model, SchematicPlan, shared
ngspice backend, probe vectors. The formulas are standard first/second-order circuit results
(Sedra & Smith, Microelectronic Circuits, 7th ed., appendix E "s-domain analysis"; Hayt, Kemmerly
& Durbin, Engineering Circuit Analysis, 8th ed., ch. 9 "the RLC circuit").
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.schematic.model import NetRef, Probe, ScalarMeasure, Sweep
from circuitos.schematic.runs import SchematicPlan, scalar_measure
from circuitos.simulation.backend import make_backend
from circuitos.simulation.post.measures import overshoot
from tests.unit.schematic.helpers import Builder

pytestmark = pytest.mark.ngspice


def _run(b: Builder):
    return SchematicPlan(b.sch, {}).execute(make_backend())


def test_as_sim_01_rc_lowpass_corner():
    """AS-SIM-01: |H(fc)| = −10·log10(2) dB and ∠H(fc) = −45° at fc = 1/(2πRC).

    Tolerance 0,01 dB and 0,1°.
    """
    r, c = 1e3, 100e-9
    fc = 1 / (2 * math.pi * r * c)
    b = Builder()
    b.add("vsin", "V1", ["in", "0"], amplitude="1", freq="1k", ac="1")
    b.add("resistor", "R1", ["in", "out"], value="1k")
    b.add("capacitor", "C1", ["out", "0"], value="100n")
    b.analysis("ac", variation="dec", points="200", fstart="10", fstop="1meg")
    plot = _run(b).plot("ac")
    db = scalar_measure(
        plot, ScalarMeasure(analysis="ac", vector="v(out)", kind="mag_db_at", at=str(fc))
    )
    ph = scalar_measure(
        plot, ScalarMeasure(analysis="ac", vector="v(out)", kind="phase_at", at=str(fc))
    )
    assert db == pytest.approx(-10 * math.log10(2), abs=0.01)
    assert ph == pytest.approx(-45.0, abs=0.1)


def test_as_sim_02_series_rlc_step_overshoot():
    """AS-SIM-02: series RLC step, ζ = (R/2)·√(C/L) = 0,1 → Mp = exp(−ζπ/√(1−ζ²)) = 72,9 %.

    Tolerance 1 percentage point (time step 0,5 µs against a 628 µs natural period).
    """
    r, ind, cap = 20.0, 10e-3, 1e-6
    zeta = r / 2 * math.sqrt(cap / ind)
    mp = math.exp(-zeta * math.pi / math.sqrt(1 - zeta**2))
    b = Builder()
    b.add(
        "vpulse",
        "V1",
        ["in", "0"],
        v1="0",
        v2="1",
        delay="0.1m",
        rise="1n",
        fall="1n",
        width="10m",
        period="20m",
    )
    b.add("resistor", "R1", ["in", "a"], value="20")
    b.add("inductor", "L1", ["a", "out"], value="10m")
    b.add("capacitor", "C1", ["out", "0"], value="1u")
    b.analysis("tran", tstop="5m", tmax="0.5u")
    plot = _run(b).plot("tran")
    t = np.real(plot.vectors[plot.scale].data)
    v = np.real(plot["v(out)"].data)
    assert float(np.max(v)) - 1.0 == pytest.approx(mp, abs=0.01)
    os_ = overshoot(q(t, "s"), q(v, "V")).m_as("")
    assert os_ == pytest.approx(mp, abs=0.02)


def test_as_sim_03_current_power_and_differential_probes():
    """AS-SIM-03: divider 10 V, 1 kΩ + 4 kΩ: I = 2 mA, P(R2) = I²·R2 = 16 mW, v(a,out) = 2 V.

    Tolerance 1e-6 relative.
    """
    b = Builder()
    b.add("vdc", "V1", ["a", "0"], dc="10")
    b.add("resistor", "R1", ["a", "out"], value="1k")
    b.add("resistor", "R2", ["out", "0"], value="4k")
    b.sch.probes += [
        Probe(id="p1", kind="i", component="R1", pin="1"),
        Probe(id="p2", kind="p", component="R2"),
        Probe(id="p3", kind="vdiff", target=NetRef(net="a"), reference=NetRef(net="out")),
    ]
    b.analysis("op")
    plot = _run(b).plot("op")
    assert float(np.real(plot["i(r1)"].data[0])) == pytest.approx(2e-3, rel=1e-6)
    assert float(np.real(plot["p(r2)"].data[0])) == pytest.approx(16e-3, rel=1e-6)
    assert float(np.real(plot["v(a,out)"].data[0])) == pytest.approx(2.0, rel=1e-6)


def test_as_sim_04_worst_case_divider_is_exact():
    """AS-SIM-04: divider 10 V, R1 = R2 = 10 kΩ ±1 %: extremes 10·R2/(R1+R2) at (R1∓, R2±).

    Linear monotonic measure, so the sensitivity method is exact. Tolerance 1e-6 relative.
    """
    b = Builder()
    b.add("vdc", "V1", ["a", "0"], dc="10")
    b.add("resistor", "R1", ["a", "out"], value="10k", tol="1")
    b.add("resistor", "R2", ["out", "0"], value="10k", tol="1")
    b.analysis("op")
    b.sch.sweep = Sweep(
        kind="worstcase", measure=ScalarMeasure(analysis="op", vector="v(out)", kind="final")
    )
    res = _run(b)
    hi = 10 * 10.1 / (9.9 + 10.1)
    lo = 10 * 9.9 / (10.1 + 9.9)
    assert res.summary["max"] == pytest.approx(hi, rel=1e-6)
    assert res.summary["min"] == pytest.approx(lo, rel=1e-6)
    assert res.summary["nominal"] == pytest.approx(5.0, rel=1e-6)


def test_as_sim_05_monte_carlo_bounds():
    """AS-SIM-05: 40 Monte Carlo runs of the ±1 % divider stay inside the analytic extremes
    10·R2/(R1+R2) with R1, R2 ∈ [9,9 kΩ; 10,1 kΩ]; run 0 is the nominal circuit.
    """
    b = Builder()
    b.add("vdc", "V1", ["a", "0"], dc="10")
    b.add("resistor", "R1", ["a", "out"], value="10k", tol="1")
    b.add("resistor", "R2", ["out", "0"], value="10k", tol="1")
    b.analysis("op")
    b.sch.sweep = Sweep(kind="montecarlo", runs=40, seed=3, distribution="uniform")
    res = _run(b)
    outs = [float(np.real(p["v(out)"].data[0])) for p in res.plots if p.kind == "op"]
    assert len(outs) == 41
    lo, hi = 10 * 9.9 / 20, 10 * 10.1 / 20
    assert all(lo - 1e-9 <= v <= hi + 1e-9 for v in outs)
    assert np.std(outs) > 0
