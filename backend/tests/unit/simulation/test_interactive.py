"""State continuity is checked against the analytic first-order RC response."""

import math

import pytest

from circuitos.simulation.interactive import TransientBench, prepare
from tests.unit.schematic.helpers import Builder


def circuit(source="vdc", **params):
    b = Builder("Bancada RC")
    b.add(source, "V1", ["in", "0"], **params)
    b.add("resistor", "R1", ["in", "out"], value="1k")
    b.add("capacitor", "C1", ["out", "0"], value="1u")
    return b.sch


@pytest.mark.ngspice
def test_source_step_preserves_capacitor_state_and_time():
    bench = TransientBench(prepare(circuit(dc="0"), {}, 0.001))
    first = bench.advance({})
    second = bench.advance({"V1": {"dc": "5"}})
    third = bench.advance({})
    assert first["time"] == pytest.approx(0.001)
    assert second["time"] == pytest.approx(0.002)
    assert third["time"] == pytest.approx(0.003)
    assert second["data"]["traces"]["v(out)"]["values"][-1] == pytest.approx(
        5 * (1 - math.exp(-1)), rel=0.005
    )
    assert third["data"]["traces"]["v(out)"]["values"][-1] == pytest.approx(
        5 * (1 - math.exp(-2)), rel=0.005
    )
    assert third["data"]["traces"]["i(r1)"]["values"][-1] == pytest.approx(
        5 * math.exp(-2) / 1000, rel=0.01
    )


@pytest.mark.ngspice
def test_manual_switch_can_close_and_open_without_resetting_time():
    b = Builder("Chave")
    b.add("vdc", "V1", ["in", "0"], dc="5")
    b.add("switch_manual", "SW1", ["in", "out"], state="0")
    b.add("resistor", "R1", ["out", "0"], value="1k")
    bench = TransientBench(prepare(b.sch, {}, 0.001))
    assert bench.advance({})["data"]["traces"]["v(out)"]["values"][-1] < 0.001
    assert bench.advance({"SW1": {"state": "1"}})["data"]["traces"]["v(out)"]["values"][-1] > 4.99
    assert bench.advance({"SW1": {"state": "0"}})["data"]["traces"]["v(out)"]["values"][-1] < 0.001


@pytest.mark.ngspice
def test_generator_amplitude_can_change_during_transient():
    bench = TransientBench(prepare(circuit("vsin", amplitude="1", freq="1k"), {}, 0.001))
    bench.advance({})
    out = bench.advance({"V1": {"amplitude": "3", "freq": "2k"}})
    times = out["data"]["x"]["values"]
    values = out["data"]["traces"]["v(in)"]["values"]
    for t, value in zip(times, values, strict=True):
        if t > 0.00101:
            assert value == pytest.approx(3 * math.sin(2 * math.pi * 2000 * t), abs=1e-5)


def test_unbounded_acquisition_is_rejected():
    with pytest.raises(ValueError):
        prepare(circuit(dc="5"), {}, float("inf"))


@pytest.mark.ngspice
def test_current_source_adjustment_keeps_branch_orientation():
    b = Builder("Fonte de corrente")
    b.add("idc", "I1", ["in", "0"], dc="1m")
    b.add("resistor", "R1", ["in", "0"], value="1k")
    bench = TransientBench(prepare(b.sch, {}, 0.001))
    bench.advance({})
    data = bench.advance({"I1": {"dc": "2m"}})["data"]["traces"]
    assert data["v(in)"]["values"][-1] == pytest.approx(-2)
    assert data["i(i1)"]["values"][-1] == pytest.approx(0.002)
    assert data["i(r1)"]["values"][-1] == pytest.approx(-0.002)


@pytest.mark.ngspice
def test_pulse_level_and_duty_change_without_resetting():
    sch = circuit("vpulse", v1="0", v2="5", rise="1u", fall="1u", width="200u", period="500u")
    bench = TransientBench(prepare(sch, {}, 0.001))
    bench.advance({})
    out = bench.advance({"V1": {"v2": "3", "width": "100u"}})
    times, values = out["data"]["x"]["values"], out["data"]["traces"]["v(in)"]["values"]
    high = [v for t, v in zip(times, values, strict=True) if 0.00102 < t < 0.00108]
    low = [v for t, v in zip(times, values, strict=True) if 0.0012 < t < 0.0014]
    assert high and low
    assert all(v == pytest.approx(3) for v in high)
    assert all(v == pytest.approx(0) for v in low)


@pytest.mark.ngspice
def test_repeating_pwl_can_be_adjusted_without_losing_repeat():
    sch = circuit("vpwl", points="0 0 100u 5 200u 0", repeat="1")
    bench = TransientBench(prepare(sch, {}, 0.001))
    bench.advance({})
    out = bench.advance({"V1": {"points": "0 0 100u 3 200u 0"}})
    values = [
        v
        for t, v in zip(
            out["data"]["x"]["values"], out["data"]["traces"]["v(in)"]["values"], strict=True
        )
        if 0.00101 < t < 0.00109
    ]
    assert values and max(values) > 2
