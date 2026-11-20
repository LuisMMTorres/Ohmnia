"""Measurements on the simulated steady state: peak, mean, RMS, S, P, Q, D and power factor.

Closed forms of sinusoidal circuit theory (any circuits textbook; IEEE Std 1459-2010, 3.1):
a sine of amplitude A has RMS A/√2 and mean 0; for v = Vm·sin ωt and i = Im·sin(ωt − φ),
P = (VmIm/2)·cos φ, Q = (VmIm/2)·sin φ, S = VmIm/2. Tolerance 1e-9 (exact on the grid).
"""

import math

import numpy as np
import pytest

from circuitos.design.measure import power_measure, probe_unit, scale, wave_measure

N = 4096
T = np.linspace(0, 1, N + 1)  # one period, endpoints included (trapezoidal rule)
TU = T[:-1]  # uniform grid without the repeated endpoint (spectrum)
W = 2 * math.pi


def test_sine_peak_mean_rms():
    m = wave_measure("v", "V", T, 10 * np.sin(W * T) + 2)
    assert m.peak.value == pytest.approx(12, rel=1e-6)
    assert m.avg.value == pytest.approx(2, abs=1e-9)
    assert m.rms.value == pytest.approx(math.sqrt(50 + 4), rel=1e-9)
    assert m.min.value == pytest.approx(-8, rel=1e-6)


@pytest.mark.parametrize("phi_deg", [0, 30, 90, -45])
def test_powers_of_a_phase_shift(phi_deg):
    phi = math.radians(phi_deg)

    def v(t):
        return 100 * np.sin(W * t)

    def i(t):
        return 2 * np.sin(W * t - phi)

    m = power_measure("x", T, v(T), i(T), v(TU), i(TU))
    assert m.S.value == pytest.approx(100, rel=1e-9)
    assert m.P.value == pytest.approx(100 * math.cos(phi), abs=1e-7)
    assert m.Q.value == pytest.approx(100 * math.sin(phi), abs=1e-7)  # inductive: Q > 0
    assert m.D.value == pytest.approx(0, abs=1e-3)
    assert m.PF.value == pytest.approx(math.cos(phi), abs=1e-9)
    assert m.S.unit == "V*A" and m.P.unit == "W" and m.Q.unit == "var"


def test_distortion_power_of_a_harmonic_current():
    # sine voltage, current with a 3rd harmonic: the harmonic adds S but no P nor Q1
    def v(t):
        return 100 * np.sin(W * t)

    def i(t):
        return 2 * np.sin(W * t) + 1 * np.sin(3 * W * t)

    m = power_measure("x", T, v(T), i(T), v(TU), i(TU))
    v_rms, i_rms = 100 / math.sqrt(2), math.sqrt((4 + 1) / 2)
    assert m.S.value == pytest.approx(v_rms * i_rms, rel=1e-9)
    assert m.P.value == pytest.approx(100, rel=1e-9)
    assert m.Q.value == pytest.approx(0, abs=1e-7)
    assert m.D.value == pytest.approx(math.sqrt((v_rms * i_rms) ** 2 - 100**2), rel=1e-6)
    assert m.DPF.value == pytest.approx(1, rel=1e-9)
    assert m.PF.value == pytest.approx(100 / (v_rms * i_rms), rel=1e-9)


def test_scale_distributes_the_coefficient():
    assert scale("v(a)-v(b)", 2) == "2*v(a)-2*v(b)"
    assert scale("-i(vs)", 0.5) == "-0.5*i(vs)"
    assert scale("i(x)+0.5*i(y)", -2) == "-2*i(x)-1*i(y)"
    with pytest.raises(ValueError):
        scale("abc", 2)


def test_probe_unit():
    assert probe_unit("v(a)-v(b)") == "V"
    assert probe_unit("0.1*i(vs)") == "A"
