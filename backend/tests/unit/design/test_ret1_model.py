"""DM-RET1 analytic model: internal consistency and limits."""

import math

import numpy as np
import pytest

from circuitos.design.plugins.ret1 import model as m

TOPOLOGIES = ["meia_onda", "center_tap", "ponte"]


@pytest.mark.parametrize("topo", TOPOLOGIES)
@pytest.mark.parametrize("VF", [0.0, 0.7])
def test_unfiltered_closed_form_matches_waveform(topo, VF):
    w = m.unfiltered(topo, 20.0, VF, 10.0)
    assert m.mean(w.vo) == pytest.approx(m.unfiltered_average(topo, 20.0, VF), rel=1e-6)


def test_ideal_unfiltered_values():
    # VF = 0: Vm/π (half wave) and 2Vm/π (full wave)
    assert m.unfiltered_average("meia_onda", 10, 0) == pytest.approx(10 / math.pi)
    assert m.unfiltered_average("ponte", 10, 0) == pytest.approx(20 / math.pi)
    assert m.unfiltered_average("ponte", 1.0, 0.6) == 0.0  # the peak does not overcome 2·VF


@pytest.mark.parametrize("topo", TOPOLOGIES)
def test_cap_filter_charge_balance(topo):
    """Steady state: the mean capacitor current is zero, so mean diode current = Io / p."""
    w = m.cap_filter(topo, 17.0, 0.8, 12.0, 2200e-6, 60.0)
    io = m.mean(w.vo) / 12.0
    assert w.i_cap is not None
    assert abs(m.mean(w.i_cap)) < 1e-3 * io
    assert m.mean(w.i_diode) == pytest.approx(io / m.pulses(topo), rel=2e-3)


@pytest.mark.parametrize("topo", TOPOLOGIES)
def test_cap_filter_large_C_tends_to_linear_ripple(topo):
    """ωRC ≫ 1: ripple → Io/(p·f·C) (Hart's approximation used for sizing)."""
    C, R, f = 1.0, 10.0, 60.0
    w = m.cap_filter(topo, 20.0, 0.0, R, C, f)
    ripple = float(np.ptp(w.vo))
    approx = m.mean(w.vo) / R / (m.pulses(topo) * f * C)
    assert ripple == pytest.approx(approx, rel=0.02)


def test_cap_filter_angles_ideal_diode():
    """VF = 0: θoff = π − arctan(ωRC) exactly."""
    R, C, f = 12.0, 1000e-6, 60.0
    s = m.solve_cap("ponte", 17.0, 0.0, R, C, f)
    assert s.theta_off == pytest.approx(math.pi - math.atan(2 * math.pi * f * R * C), abs=1e-9)
    assert 0 < s.theta_on < math.pi / 2


def test_lc_filter_mean_and_continuity():
    R, f = 12.0, 60.0
    L = 3 * m.critical_inductance(R, f)
    w = m.lc_filter("ponte", 20.0, 0.7, R, L, 2200e-6, f)
    assert m.mean(w.vo) == pytest.approx(2 * 20 / math.pi - 1.4, rel=1e-6)
    assert w.i_ind is not None and float(np.min(w.i_ind)) > 0


def test_pi_filter_reduces_ripple_and_balances_charge():
    R, f, C = 12.0, 60.0, 2200e-6
    L = 5 / ((4 * math.pi * f) ** 2 * C)
    w = m.pi_filter("ponte", 17.0, 0.8, R, L, C, C, f)
    assert w.v_c1 is not None and w.i_ind is not None
    assert np.ptp(w.vo) < 0.5 * np.ptp(w.v_c1)
    assert m.mean(w.vo) == pytest.approx(m.mean(w.v_c1), rel=1e-6)  # ideal inductor
    assert m.mean(w.i_ind) == pytest.approx(m.mean(w.vo) / R, rel=1e-6)


def test_harmonics_of_sine_and_square():
    theta = np.linspace(0, 2 * math.pi, 4096, endpoint=False)
    assert m.thd(np.sin(theta)) < 1e-9
    square = np.sign(np.sin(theta))
    # odd harmonics 4/(πh); the THD is summed up to the 50th
    expected = math.sqrt(sum(1 / h**2 for h in range(3, 51, 2)))
    assert m.thd(square) == pytest.approx(expected, rel=1e-3)


def test_filters_reject_half_wave():
    with pytest.raises(ValueError):
        m.lc_filter("meia_onda", 10, 0, 10, 1e-3, 1e-3, 60)
    with pytest.raises(ValueError):
        m.pi_filter("meia_onda", 10, 0, 10, 1e-3, 1e-3, 1e-3, 60)
    with pytest.raises(ValueError):
        m.solve_cap("ponte", 1.0, 0.6, 10, 1e-3, 60)
