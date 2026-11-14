"""AS-TIR-01 and AS-TIR-02: bench thyristor switching rules × ngspice behavioural subcircuit.

Circuit: 100 V peak, 60 Hz source, resistive load, gate pulses at α. Two periods are simulated
and compared on the second period.

AS-TIR-01 (SCR): α = 30°, 60°, 90°, 135°; plus a gate pulse below IGT (must not fire) and a
pulse too short to reach IL (must turn off after the pulse).
AS-TIR-02 (TRIAC): gate modes "positivo" (Q1/Q4), "negativo" (Q2/Q3) and "acompanha" (Q1/Q3),
with IGT of Q4 set above IG so the device only conducts in the half cycles it should.

Tolerances: switching instants within 20 µs (0,43° at 60 Hz: RC of the latch, 1 µs, plus the
simulator time step); average and RMS load voltage within 0,5 % of the peak value.
"""

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.thyristor import Drive, ThyristorModel, last_period_metrics, simulate
from circuitos.simulation.backend import make_backend

pytestmark = pytest.mark.ngspice

F = 60.0
T = 1 / F


def _model(kind, igt=(5e-3, 5e-3, 5e-3, 7e-3), ih=5e-3, il=10e-3):
    return ThyristorModel(
        kind=kind,
        VT0=q(1.0, "V"),
        rT=q(0.05, "ohm"),
        IGT=tuple(q(x, "A") for x in igt),
        IH=q(ih, "A"),
        IL=q(il, "A"),
    )


def _drive(alpha, ig=10e-3, tw=100e-6, mode="positivo", r=100.0):
    return Drive(
        Vm=q(100, "V"),
        f=q(F, "Hz"),
        R=q(r, "ohm"),
        alpha=q(alpha, "deg"),
        IG=q(ig, "A"),
        tw=q(tw, "s"),
        gate_mode=mode,
    )


def _ngspice(m, d):
    s1, s2 = d.pulse_signs(m.kind)
    t_alpha = d.alpha.m_as("deg") / 360 * T
    ig = d.IG.m_as("A")
    tw = d.tw.m_as("s")
    gates = [f"IG1 0 g PULSE(0 {s1 * ig:.9g} {t_alpha:.9g} 10n 10n {tw:.9g} {T:.9g})"]
    if s2:
        gates.append(
            f"IG2 0 g PULSE(0 {s2 * ig:.9g} {t_alpha + T / 2:.9g} 10n 10n {tw:.9g} {T:.9g})"
        )
    netlist = "\n".join(
        [
            "AS-TIR",
            m.spice(),
            f"VS s 0 SIN(0 {d.Vm.m_as('V'):.9g} {F:.9g})",
            f"RL s a {d.R.m_as('ohm'):.9g}",
            "X1 a 0 g 0 XTIR",
            *gates,
            f".tran 5u {2 * T:.9g} 0 5u",
            "",
        ]
    )
    plot = make_backend().run(netlist).plot("tran")
    t = np.real(plot.vectors[plot.scale].data)
    v_load = np.real(plot["v(s)"].data) - np.real(plot["v(a)"].data)
    return t, v_load


def _edges(t, v, thr):
    on = np.abs(v) > thr
    idx = np.nonzero(np.diff(on.astype(int)))[0]
    return [("on" if on[k + 1] else "off", float(t[k + 1])) for k in idx]


def _second_period(events):
    return [(kind, round(t, 9)) for kind, t in events if t > T]


def _compare(m, d):
    w = simulate(m, d)
    t_sim, vl_sim = _ngspice(m, d)
    thr = 0.5 * m.IH.m_as("A") * d.R.m_as("ohm")
    ev_model = _second_period(_edges(w.t, w.v_load, thr))
    ev_sim = _second_period(_edges(t_sim, vl_sim, thr))
    assert [k for k, _ in ev_model] == [k for k, _ in ev_sim], (ev_model, ev_sim)
    for (_, a), (_, b) in zip(ev_model, ev_sim, strict=True):
        assert abs(a - b) < 20e-6, (ev_model, ev_sim)
    avg_m, rms_m = last_period_metrics(w, d)
    sel = t_sim >= T
    span = t_sim[sel][-1] - t_sim[sel][0]
    avg_s = np.trapezoid(vl_sim[sel], t_sim[sel]) / span
    rms_s = np.sqrt(np.trapezoid(vl_sim[sel] ** 2, t_sim[sel]) / span)
    vm = d.Vm.m_as("V")
    assert abs(avg_m - avg_s) < 5e-3 * vm
    assert abs(rms_m - rms_s) < 5e-3 * vm
    return ev_model


@pytest.mark.parametrize("alpha", [30, 60, 90, 135])
def test_scr_firing_angle(alpha):
    events = _compare(_model("scr"), _drive(alpha))
    assert [k for k, _ in events] == ["on", "off"]


def test_scr_gate_below_igt_does_not_fire():
    assert _compare(_model("scr"), _drive(60, ig=4e-3)) == []


def test_scr_short_pulse_does_not_latch():
    # IL = 1,5 A cannot be reached (peak ≈ 0,99 A at 100 V / 100 Ω):
    # the SCR conducts only during the pulse
    events = _compare(_model("scr", il=1.5), _drive(60, tw=500e-6))
    assert [k for k, _ in events] == ["on", "off"]
    assert events[1][1] - events[0][1] == pytest.approx(500e-6, abs=20e-6)


@pytest.mark.parametrize(
    ("mode", "n_on"),
    [("positivo", 1), ("negativo", 2), ("acompanha", 2)],
)
def test_triac_quadrants(mode, n_on):
    # Q4 needs 12 mA > IG = 10 mA: with positive pulses the negative half cycle does not fire
    m = _model("triac", igt=(5e-3, 5e-3, 5e-3, 12e-3))
    events = _compare(m, _drive(45, mode=mode))
    assert sum(1 for k, _ in events if k == "on") == n_on
