"""The integrated examples run and do what their description says (ngspice co-simulation)."""

from __future__ import annotations

import re

import numpy as np
import pytest

from circuitos.cosim import examples as ex
from circuitos.schematic.runs import SchematicPlan

pytestmark = pytest.mark.ngspice


@pytest.fixture(scope="module")
def backend():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    return SharedNgspiceBackend()


def run(backend, make):  # type: ignore[no-untyped-def]
    res = SchematicPlan(make()).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    t = tran.vectors[tran.scale].data
    return res, tran, t


def at(tran, t, name, when):  # type: ignore[no-untyped-def]
    return float(np.interp(when, t, tran.vectors[name].data))


def test_e1_arduino_pi_reaches_the_set_point(backend):
    res, tran, t = run(backend, ex.arduino_pwm_temperature)
    temp = tran.vectors["v(h1_temp)"].data
    late = temp[t > 45]
    assert abs(late.mean() - 60.0) < 1.5, late.mean()
    assert temp.max() < 75  # no large overshoot
    assert any("T = " in line[1] for line in res.summary["cosim"]["serial"]["U1"])
    # slow PWM: the MOSFET is driven fully on or off, never held in its linear region
    gate = tran.vectors["v(gate)"].data
    assert np.mean((gate < 0.5) | (gate > 4.5)) > 0.99
    # the duty the program computes is the duty the circuit sees (uniform grid, last 20 s)
    grid = np.arange(40.0, 60.0, 1e-3)
    duty_circuit = np.mean(np.interp(grid, t, gate) > 2.5)
    duty_program = np.mean(np.interp(grid, t, tran.vectors["u1.pwm"].data)) / 255
    assert duty_circuit == pytest.approx(duty_program, abs=0.03)


def test_e2_esp32_energy_meter_matches_the_load(backend):
    res, _, _ = run(backend, ex.esp32_energy_meter)
    lines = [line[1] for line in res.summary["cosim"]["serial"]["U1"]]
    assert lines, "sem saída serial"
    v, i, p, fp = map(float, re.findall(r"[-\d.]+", lines[-1].replace(" V", ""))[:4])
    z = complex(50, 2 * np.pi * 60 * 0.1)
    i_exp = 127.0 / abs(z)
    assert v == pytest.approx(127.0, rel=0.04)
    assert i == pytest.approx(i_exp, rel=0.06)
    assert fp == pytest.approx(50 / abs(z), abs=0.05)
    assert p == pytest.approx(i_exp**2 * 50, rel=0.1)


def test_e3_plc_holds_the_temperature_in_the_band(backend):
    _, tran, t = run(backend, ex.plc_4_20ma_loop)
    temp = tran.vectors["v(h1_temp)"].data
    band = temp[(t > 20) & (t < 39)]
    assert band.min() > 54 and band.max() < 66, (band.min(), band.max())
    q0 = tran.vectors["clp1.q0"].data
    assert q0[(t > 20) & (t < 39)].min() == 0 and q0[(t > 20) & (t < 39)].max() == 1
    assert q0[t > 41].max() == 0  # stop button at 40 s
    assert at(tran, t, "v(h1_temp)", 59.9) < 50


def test_e4_plc_switches_the_fan_from_the_esp32_signal(backend):
    _, tran, t = run(backend, ex.esp32_plc_conditioner)
    # LM35 ramp 20 -> 90 °C in 20 s: 70 °C at about 14,3 s
    q0 = tran.vectors["clp1.q0"].data
    on = t[np.argmax(q0 > 0.5)]
    assert 13.8 < on < 15.0, on
    assert at(tran, t, "v(ai)", 10.0) == pytest.approx(5.5, abs=0.25)  # 55 °C -> 5,5 V
    assert at(tran, t, "v(m1_w)", 19.0) > 1.0  # fan spinning


def test_e5_pid_keeps_the_pressure(backend):
    res, tran, t = run(backend, ex.pump_constant_pressure)
    p = tran.vectors["v(pl1_p)"].data
    assert at(tran, t, "v(pl1_p)", 28.0) == pytest.approx(3.0, abs=0.1)
    assert at(tran, t, "v(pl1_p)", 59.0) == pytest.approx(3.0, abs=0.1)  # after the demand step
    assert p[(t > 31) & (t < 33)].min() < 2.9  # the disturbance is visible
    assert at(tran, t, "v(pl1_f)", 59.0) > at(tran, t, "v(pl1_f)", 28.0)  # more speed, more flow
    assert res.summary["cosim"]["serial"]["U1"]


def test_every_example_assembles_on_the_breadboard():
    from circuitos.breadboard.autoplace import autoplace
    from circuitos.breadboard.check import check
    from circuitos.breadboard.reference import build

    for name, (_, make) in ex.EXAMPLES.items():
        ref = build(make(), {})
        bb, notes = autoplace(ref)
        report = check(ref, bb)
        assert report.ok, (name, [i.message for i in report.issues if i.kind != "aviso"], notes)
