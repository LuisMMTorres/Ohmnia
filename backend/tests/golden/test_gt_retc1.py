"""GT-RETC1: DM-RETC1 against closed-form textbook results (ideal devices).

Source: Hart, *Power Electronics*, 1st ed. (McGraw-Hill, 2011), ch. 3 (controlled half-wave
rectifier, resistive and RL loads) and ch. 4 (controlled full-wave rectifiers, continuous and
discontinuous current; the semicontrolled bridge appears in Rashid, *Power Electronics*,
controlled rectifiers chapter). These are the books' formulas evaluated here; the numbered
worked examples and pages are pending the user's check (decision D6).

Tolerance 1e-3: the model samples the exact piecewise solution on a 14 400-point grid, and the
jump of the load voltage at α costs up to half a step (0,0125°) in the averages.
"""

import math

import pytest

from circuitos.design.plugins.retc1 import model as m

VM, F = 100.0, 60.0
W = 2 * math.pi * F


@pytest.mark.parametrize("deg", [0, 30, 60, 90, 120])
def test_gt_retc1_half_wave_resistive(deg):
    a = math.radians(deg)
    w = m.waves(m.solve("meia_onda", VM, a, m.Load(10), F))
    assert m.mean(w.vo) == pytest.approx(VM / (2 * math.pi) * (1 + math.cos(a)), rel=1e-3)
    # Vrms = (Vm/2)·√(1 − α/π + sin 2α/(2π))
    vrms = VM / 2 * math.sqrt(1 - a / math.pi + math.sin(2 * a) / (2 * math.pi))
    assert m.rms(w.vo) == pytest.approx(vrms, rel=1e-3)


def test_gt_retc1_half_wave_rl_extinction():
    """i(β) = (Vm/Z)[sin(β − θ) − sin(α − θ)·e^{(α−β)/ωτ}] = 0 and Vo = Vm/2π·(cos α − cos β)."""
    R, L, a = 10.0, 0.05, math.radians(45)
    sol = m.solve("meia_onda", VM, a, m.Load(R, L), F)
    z = math.hypot(R, W * L)
    th = math.atan2(W * L, R)
    b = sol.beta
    assert b is not None
    expr = VM / z * (math.sin(b - th) - math.sin(a - th) * math.exp((a - b) / (W * L / R)))
    assert expr == pytest.approx(0, abs=1e-9)
    vo = m.mean(m.waves(sol).vo)
    assert vo == pytest.approx(VM / (2 * math.pi) * (math.cos(a) - math.cos(b)), rel=1e-3)


@pytest.mark.parametrize("deg", [0, 30, 60, 85])
def test_gt_retc1_bridge_continuous(deg):
    a = math.radians(deg)
    sol = m.solve("ponte", VM, a, m.Load(10, 1.0), F)
    assert sol.continuous
    assert m.mean(m.waves(sol).vo) == pytest.approx(2 * VM / math.pi * math.cos(a), abs=1e-3 * VM)


def test_gt_retc1_bridge_discontinuous_rle():
    a, E = math.radians(60), 30.0
    sol = m.solve("ponte", VM, a, m.Load(10, 0.01, E), F)
    assert not sol.continuous and sol.beta is not None
    expected = m.ideal_average_discontinuous("ponte", VM, a, sol.beta, E)
    assert m.mean(m.waves(sol).vo) == pytest.approx(expected, rel=1e-3)


@pytest.mark.parametrize("deg", [0, 45, 90, 135])
def test_gt_retc1_semicontrolled(deg):
    a = math.radians(deg)
    sol = m.solve("semicontrolada", VM, a, m.Load(10, 0.5), F)
    assert m.mean(m.waves(sol).vo) == pytest.approx(VM / math.pi * (1 + math.cos(a)), rel=1e-3)
