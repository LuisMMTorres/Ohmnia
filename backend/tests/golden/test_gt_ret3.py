"""GT-RET3: DM-RET3 against closed-form textbook results.

Sources: Hart, *Power Electronics*, 1st ed. (McGraw-Hill, 2011), ch. 4 (three-phase rectifiers:
Vo = 3V_LL,m/π, controlled Vo = 3V_LL,m/π·cos α, commutation); Mohan, Undeland and Robbins,
*Power Electronics*, 3rd ed. (Wiley, 2003), ch. 6 (effect of Ls: cos α − cos(α + μ) =
2ωLs·Io/V_LL,m, ΔVo = 3ωLs·Io/π; ideal 6-pulse line current: PF = 3/π, THD = 31 %). Formulas
evaluated here; the worked examples and pages are pending the user's check (decision D6).

Tolerances: 1e-3 for the averages (grid of 14 400 points: the jump at α costs half a step);
the THD is summed up to the 50th harmonic, so the ideal square-wave values are those sums.
"""

import math

import pytest

from circuitos.design.plugins.ret3 import model as m

VLL, F, IO = 500.0, 60.0, 20.0


@pytest.mark.parametrize("deg", [0, 30, 60])
def test_gt_ret3_six_pulse_controlled(deg):
    a = math.radians(deg)
    w = m.waves(6, VLL, a, IO, 0.0, F, 0.0)
    assert m.mean(w.vo) == pytest.approx(3 * VLL / math.pi * math.cos(a), rel=1e-3, abs=0.1)


def test_gt_ret3_three_pulse():
    w = m.waves(3, VLL, 0.0, IO, 0.0, F, 0.0)
    vph = VLL / math.sqrt(3)
    assert m.mean(w.vo) == pytest.approx(3 * math.sqrt(3) / (2 * math.pi) * vph, rel=1e-6)


def test_gt_ret3_commutation():
    Ls, a = 2e-3, math.radians(30)
    w = m.waves(6, VLL, a, IO, Ls, F, 0.0)
    om = 2 * math.pi * F
    assert math.cos(a) - math.cos(a + w.mu) == pytest.approx(2 * om * Ls * IO / VLL, rel=1e-9)
    expected = 3 * VLL / math.pi * math.cos(a) - 3 * om * Ls * IO / math.pi
    assert m.mean(w.vo) == pytest.approx(expected, rel=1e-3)


def test_gt_ret3_ideal_line_current():
    w = m.waves(6, VLL, 0.0, IO, 0.0, F, 0.0)
    assert m.power_factor(w) == pytest.approx(3 / math.pi, rel=1e-3)
    # 120° square wave: harmonics 6k ± 1 with amplitude 1/h
    h = [n for n in range(2, 51) if n % 6 in (1, 5)]
    assert m.thd(w.i_ref[0]) == pytest.approx(math.sqrt(sum(1 / n**2 for n in h)), rel=1e-3)
    assert m.rms(w.bridges[0].i_line[0]) == pytest.approx(IO * math.sqrt(2 / 3), rel=1e-3)


def test_gt_ret3_twelve_pulse_cancels_5th_and_7th():
    w = m.waves(12, VLL, 0.0, IO, 0.0, F, 0.0)
    h = [n for n in range(2, 51) if n % 12 in (1, 11)]
    assert m.thd(w.i_ref[0]) == pytest.approx(math.sqrt(sum(1 / n**2 for n in h)), rel=1e-3)
    assert m.mean(w.vo) == pytest.approx(6 * VLL / math.pi, rel=1e-6)
