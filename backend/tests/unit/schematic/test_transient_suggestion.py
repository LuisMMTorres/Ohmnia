"""Suggested .tran settings read from the circuit (schematic/transient.py).

The time scales are textbook results: T = 1/f, τ = RC and τ = L/R (Hayt, Kemmerly & Durbin,
Engineering Circuit Analysis, 8th ed., ch. 8), T₀ = 2π√(LC) (ch. 9). The rules (5 periods,
5 τ, T/50, τ/10, 1-2-5 rounding) are those of the module docstring.
"""

from __future__ import annotations

import math

import pytest

from circuitos.schematic.netlist import build_netlist, connectivity
from circuitos.schematic.transient import nice_down, nice_up, suggest_tran

from .helpers import Builder


def _suggest(b: Builder):
    return suggest_tran(b.sch, connectivity(b.sch).pin_nodes)


def test_nice_rounding():
    assert nice_up(83.3e-3) == pytest.approx(100e-3)
    assert nice_up(2.5e-3) == pytest.approx(5e-3)
    assert nice_up(1e-3) == pytest.approx(1e-3)
    assert nice_down(333e-6) == pytest.approx(200e-6)
    assert nice_down(1e-6) == pytest.approx(1e-6)


def test_sine_source_sets_five_periods_and_fifty_steps_per_period():
    b = Builder()
    b.add("vsin", "V1", ["in", "0"], amplitude="180", freq="60")
    b.add("resistor", "R1", ["in", "0"], value="1k")
    s = _suggest(b)
    assert s.tstop == pytest.approx(100e-3)  # 5 × 16,7 ms = 83 ms → 100 ms
    assert s.tmax == pytest.approx(200e-6)  # 16,7 ms / 50 = 333 µs → 200 µs
    assert s.params == {
        "tstop": "100m",
        "tstep": "100u",
        "tstart": "0",
        "tmax": "200u",
        "uic": "não",
    }
    assert any(st.id == "T_V1" for st in s.steps)


def test_rc_time_constant_with_thevenin_resistance():
    """R1 = 1 kΩ in series, R2 = 1 kΩ shunt: τ = C·(R1‖R2) = 1 µF · 500 Ω = 0,5 ms."""
    b = Builder()
    b.add("vdc", "V1", ["in", "0"], dc="5")
    b.add("resistor", "R1", ["in", "out"], value="1k")
    b.add("resistor", "R2", ["out", "0"], value="1k")
    b.add("capacitor", "C1", ["out", "0"], value="1u")
    s = _suggest(b)
    tau = next(st for st in s.steps if st.id == "tau_C1")
    assert tau.output.value == pytest.approx(0.5e-3)
    assert s.tstop == pytest.approx(5e-3)  # 5τ = 2,5 ms → 5 ms
    assert s.tmax == pytest.approx(50e-6)  # τ/10


def test_buck_switching_limits_the_step():
    b = Builder()
    b.add("vdc", "V1", ["vin", "0"], dc="24")
    b.add("vpulse", "V2", ["g", "0"], v1="0", v2="5", width="25u", period="50u")
    b.add("switch", "S1", ["vin", "sw", "g", "0"])
    b.add("diode", "D1", ["0", "sw"])
    b.add("inductor", "L1", ["sw", "out"], value="100u")
    b.add("capacitor", "C1", ["out", "0"], value="100u")
    b.add("resistor", "R1", ["out", "0"], value="5")
    s = _suggest(b)
    t0 = 2 * math.pi * math.sqrt(100e-6 * 100e-6)
    assert next(st for st in s.steps if st.id == "T_L1_C1").output.value == pytest.approx(t0)
    assert s.tmax == pytest.approx(500e-9)  # 50 µs / 100
    assert s.tstop >= 5 * t0


def test_no_time_scale_keeps_the_default_and_initial_conditions_ask_for_uic():
    b = Builder()
    b.add("vdc", "V1", ["in", "0"], dc="5")
    b.add("resistor", "R1", ["in", "0"], value="1k")
    s = _suggest(b)
    assert s.params["tstop"] == "10m" and s.params["tmax"] == ""
    b.add("capacitor", "C1", ["in", "0"], value="1u", ic="2")
    assert _suggest(b).params["uic"] == "sim"


def test_long_run_warns():
    b = Builder()
    b.add("vpulse", "V1", ["g", "0"], width="0.5u", period="1u")
    b.add("resistor", "R1", ["g", "x"], value="1k")
    b.add("capacitor", "C1", ["x", "0"], value="1")  # τ = 1000 s
    assert _suggest(b).warnings


def test_blank_max_step_uses_the_circuit_suggestion():
    """1 kHz sine in a 100 ms run: ngspice alone would take 100 µs steps (10 per period)."""
    b = Builder()
    b.add("vsin", "V1", ["in", "0"], amplitude="1", freq="1k")
    b.add("resistor", "R1", ["in", "0"], value="1k")
    b.analysis("tran", tstop="100m")
    nl = build_netlist(b.sch)
    assert ".tran 100u 100m 0 20u" in nl.text
    assert any("Passo máximo em branco" in w for w in nl.warnings)
    # a value typed by the user is kept
    b.sch.analyses[0].params["tmax"] = "50u"
    assert ".tran 100u 100m 0 50u" in build_netlist(b.sch).text


def test_blank_max_step_stays_blank_when_ngspice_default_is_fine():
    b = Builder()
    b.add("vsin", "V1", ["in", "0"], amplitude="1", freq="60")
    b.add("resistor", "R1", ["in", "0"], value="1k")
    b.analysis("tran", tstop="100m")
    assert ".tran 100u 100m\n" in build_netlist(b.sch).text


@pytest.mark.ngspice
def test_bridge_with_filter_after_transformer_simulates():
    """Regression (user report, 22/11/2026): transformer + diode bridge + filter capacitor
    stopped with "timestep too small" because the secondary, isolated by four blocked diodes,
    hung on 1 GΩ only. The 100 pF inter-winding capacitance keeps it defined."""
    from circuitos.schematic.runs import SchematicPlan
    from circuitos.simulation.backend import make_backend

    b = Builder()
    b.add("vsin", "V1", ["in", "0"], amplitude="179.6", freq="60")
    b.add("transformer", "T1", ["in", "0", "a", "b"], lp="100m", ratio="10")
    b.add("diode", "D1", ["a", "p"])
    b.add("diode", "D2", ["b", "p"])
    b.add("diode", "D3", ["0", "a"])
    b.add("diode", "D4", ["0", "b"])
    b.add("resistor", "R1", ["p", "0"], value="1k")
    b.add("capacitor", "C1", ["p", "0"], value="1000u")
    b.analysis("tran", tstop="100m")
    plot = SchematicPlan(b.sch, {}).execute(make_backend()).plot("tran")
    assert plot.scale
