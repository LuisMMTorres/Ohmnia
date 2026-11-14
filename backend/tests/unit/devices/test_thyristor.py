import math

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.thyristor import (
    Drive,
    ThyristorModel,
    gate_current,
    ideal_load_voltage,
    last_period_metrics,
    latch_current,
    on_state_fit,
    simulate,
    turn_off_angle,
)


def model(kind="scr", vt0=1.0, ih=5e-3, il=10e-3, igt=(5e-3, 5e-3, 5e-3, 7e-3)):
    return ThyristorModel(
        kind=kind,
        VT0=q(vt0, "V"),
        rT=q(0.05, "ohm"),
        IGT=tuple(q(x, "A") for x in igt),
        IH=q(ih, "A"),
        IL=q(il, "A"),
    )


def drive(alpha=60, mode="positivo", ig=20e-3, tw=100e-6):
    return Drive(
        Vm=q(100, "V"),
        f=q(60, "Hz"),
        R=q(100, "ohm"),
        alpha=q(alpha, "deg"),
        IG=q(ig, "A"),
        tw=q(tw, "s"),
        gate_mode=mode,
    )


@pytest.mark.parametrize("alpha", [0, 30, 90, 150])
def test_near_ideal_scr_matches_closed_form(alpha):
    m = model(vt0=1e-6, ih=1e-9, il=1e-9)
    d = drive(alpha)
    w = simulate(m, d, points_per_period=20000)
    avg, rms = last_period_metrics(w, d)
    avg_ideal, rms_ideal = (c.value.m_as("V") for c in ideal_load_voltage("scr", d))
    assert avg == pytest.approx(avg_ideal, rel=2e-3, abs=1e-3)
    assert rms == pytest.approx(rms_ideal, rel=2e-3, abs=1e-3)


def test_near_ideal_triac_rms():
    m = model("triac", vt0=1e-6, ih=1e-9, il=1e-9)
    d = drive(45, mode="acompanha")
    w = simulate(m, d, points_per_period=20000)
    avg, rms = last_period_metrics(w, d)
    (ideal,) = ideal_load_voltage("triac", d)
    assert rms == pytest.approx(ideal.value.m_as("V"), rel=2e-3)
    assert avg == pytest.approx(0, abs=0.05)


def test_turn_off_angle_matches_waveform():
    m, d = model(), drive()
    w = simulate(m, d, points_per_period=20000)
    t_off = next(t for k, t in w.events if k == "off")
    angle = t_off * 60 * 360
    assert angle == pytest.approx(turn_off_angle(m, d).value.m_as("deg"), abs=0.05)


def test_turn_off_angle_requires_reachable_ih():
    with pytest.raises(ValueError, match="IH"):
        turn_off_angle(model(ih=2.0), drive())


def test_latch_current_window():
    m = model()
    # pulse spans 90°: peak current
    assert latch_current(m, drive(80, tw=1e-3)).value.m_as("A") == pytest.approx(99 / 100.05)
    # after 90°: current is largest at the start of the pulse
    i = latch_current(m, drive(120)).value.m_as("A")
    assert i == pytest.approx((100 * math.sin(math.radians(120)) - 1) / 100.05)
    # before 90°: largest at the end of the pulse
    i = latch_current(m, drive(30, tw=1e-3)).value.m_as("A")
    assert i == pytest.approx((100 * math.sin(math.radians(30 + 21.6)) - 1) / 100.05)


def test_scr_ignores_negative_gate_and_reverse_voltage():
    w = simulate(model(), drive(60, mode="negativo"))
    assert w.i.min() >= 0
    assert gate_current(drive(), "scr", np.array([0.0])).item() == 0


def test_triac_quadrant_logic():
    m = model("triac", igt=(5e-3, 50e-3, 5e-3, 50e-3))
    # positive pulses: Q1 fires, Q4 (50 mA) does not
    w = simulate(m, drive(45, mode="positivo"))
    assert w.i.max() > 0 and w.i.min() == 0
    # negative pulses: Q2 does not fire, Q3 does
    w = simulate(m, drive(45, mode="negativo"))
    assert w.i.max() == 0 and w.i.min() < 0


def test_short_pulse_without_latching():
    m = model(il=2.0)
    w = simulate(m, drive(60, tw=300e-6))
    on_time = np.sum(w.on) * (w.t[1] - w.t[0])
    assert on_time == pytest.approx(2 * 300e-6, rel=0.05)


def test_on_state_fit():
    step = on_state_fit(q(1.7, "V"), q(1.2, "A"), q(1.0, "V"))
    assert step.value.m_as("ohm") == pytest.approx(0.7 / 1.2)
    with pytest.raises(ValueError):
        on_state_fit(q(0.8, "V"), q(1.2, "A"), q(1.0, "V"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vt0": -1},
        {"ih": 0},
        {"igt": (0, 1e-3, 1e-3, 1e-3)},
        {"igt": (1e-3, 1e-3, 1e-3)},
    ],
)
def test_model_validation(kwargs):
    with pytest.raises(ValueError):
        model(**kwargs)


@pytest.mark.parametrize("kwargs", [{"alpha": 180}, {"ig": -1e-3}, {"tw": 0.01}])
def test_drive_validation(kwargs):
    with pytest.raises(ValueError):
        drive(**kwargs)


def test_spice_subcircuit_text():
    text = model("triac").spice()
    assert text.startswith(".subckt XTIR a k g gk") and text.endswith(".ends")
    assert "abs(i(VKS))" in text
