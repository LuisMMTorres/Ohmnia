"""DM-RETC1 analytic model: internal consistency."""

import math

import numpy as np
import pytest

from circuitos.design.plugins.retc1 import model as m

F = 60.0
W = 2 * math.pi * F


def test_load_validation():
    with pytest.raises(ValueError):
        m.Load(R=0)
    with pytest.raises(ValueError):
        m.Load(R=1, L=-1)


def test_continuous_steady_state_is_periodic():
    sol = m.solve("ponte", 100, math.radians(45), m.Load(10, 0.1), F, 1.0)
    assert sol.continuous
    seg = sol.segments[0]
    assert m.current_at(seg, seg.end, 100, sol.load, W) == pytest.approx(seg.i0, rel=1e-9)


def test_discontinuous_current_ends_at_beta():
    sol = m.solve("ponte", 100, math.radians(60), m.Load(10, 0.01), F)
    assert not sol.continuous and sol.beta is not None
    assert sol.beta > math.radians(60)
    assert m.current_at(sol.segments[0], sol.beta, 100, sol.load, W) == pytest.approx(0, abs=1e-9)


def test_mean_inductor_voltage_is_zero():
    """Vo = E + R·Io in steady state, for every topology."""
    for topo, fw in (
        ("meia_onda", False),
        ("meia_onda", True),
        ("ponte", False),
        ("semicontrolada", False),
    ):
        ld = m.Load(8, 0.05, 20)
        w = m.waves(m.solve(topo, 150, math.radians(50), ld, F, 1.2, 0.9, fw))
        assert m.mean(w.vo) == pytest.approx(ld.E + ld.R * m.mean(w.io), rel=1e-3)


def test_no_firing_when_reverse_biased():
    sol = m.solve("ponte", 50, math.radians(10), m.Load(10, 0.01, 40), F)  # fires only after 53°
    assert not sol.fired and sol.notes
    w = m.waves(sol)
    assert np.all(w.io == 0) and m.mean(w.vo) == pytest.approx(40)


def test_device_currents_split_the_load_current():
    w = m.waves(m.solve("ponte", 100, math.radians(30), m.Load(10, 0.1), F))
    assert m.mean(w.devices["T1"]) == pytest.approx(m.mean(w.io) / 2, rel=1e-3)
    assert np.allclose(w.devices["T1"], w.devices["T2"])
    w = m.waves(m.solve("semicontrolada", 100, math.radians(60), m.Load(10, 0.1), F))
    assert m.mean(w.devices["T1"] + w.devices["T2"]) == pytest.approx(m.mean(w.io), rel=1e-3)
    assert m.mean(w.devices["D1"] + w.devices["D2"]) == pytest.approx(m.mean(w.io), rel=1e-3)


def test_freewheeling_raises_the_mean_voltage():
    ld = m.Load(10, 0.1)
    without = m.mean(m.waves(m.solve("meia_onda", 100, math.radians(45), ld, F)).vo)
    with_fw = m.mean(m.waves(m.solve("meia_onda", 100, math.radians(45), ld, F, freewheel=True)).vo)
    assert with_fw > without


def test_power_factor_bounds_and_displacement():
    for a in (0, 30, 60, 90):
        w = m.waves(m.solve("ponte", 100, math.radians(a), m.Load(10, 1.0), F))
        pf = m.power_factor(w.vs, w.i_src)
        dpf = m.displacement_factor(w.vs, w.i_src)
        assert 0 <= pf <= 1
        # large L: square current; DPF = cos α, PF = 0,9·cos α
        assert dpf == pytest.approx(math.cos(math.radians(a)), abs=0.03)
        assert pf == pytest.approx(2 * math.sqrt(2) / math.pi * math.cos(math.radians(a)), abs=0.03)


def test_alpha_out_of_range():
    with pytest.raises(ValueError):
        m.solve("ponte", 100, math.pi, m.Load(10), F)
