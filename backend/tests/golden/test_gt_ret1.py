"""GT-RET1: DM-RET1 against closed-form textbook results.

Source: Hart, *Power Electronics*, 1st ed. (McGraw-Hill, 2011), ch. 3 and 4: ideal half-wave
and full-wave rectifiers with resistive load, capacitor filter (θoff and the linear-discharge
ripple approximation) and choke-input LC filter (Vo = 2Vm/π, Lcrit = R/(3ω)).

These are the book's formulas evaluated here, not numbered worked examples: the example numbers
and pages are pending the user's check with the book (decision D6, docs/validacao/
retificadores.md). Tolerances: 1e-6 for closed forms the model reproduces exactly; 2 % for the
ripple approximation with ωRC ≈ 1900 (it neglects the
conduction interval, about 1,3 % of the period here).
"""

import math

import pytest

from circuitos.design.plugins.ret1 import model as m

VM, R, F = 100.0, 10.0, 60.0
W = 2 * math.pi * F


def test_gt_ret1_half_wave_resistive():
    w = m.unfiltered("meia_onda", VM, 0.0, R)
    assert m.mean(w.vo) == pytest.approx(VM / math.pi, rel=1e-6)  # Vo = Vm/π
    assert m.rms(w.vo) == pytest.approx(VM / 2, rel=1e-6)  # Vrms = Vm/2
    assert m.rms(w.i_sec) == pytest.approx(VM / (2 * R), rel=1e-6)


def test_gt_ret1_full_wave_resistive():
    for topo in ("center_tap", "ponte"):
        w = m.unfiltered(topo, VM, 0.0, R)
        assert m.mean(w.vo) == pytest.approx(2 * VM / math.pi, rel=1e-6)  # Vo = 2Vm/π
        assert m.rms(w.vo) == pytest.approx(VM / math.sqrt(2), rel=1e-6)
    assert m.unfiltered("ponte", VM, 0.0, R).vr_diode_max == pytest.approx(VM)
    assert m.unfiltered("center_tap", VM, 0.0, R).vr_diode_max == pytest.approx(2 * VM, rel=1e-6)


def test_gt_ret1_capacitor_filter_theta_off_and_ripple():
    C = 0.5  # ωRC ≈ 1885
    s = m.solve_cap("meia_onda", VM, 0.0, R, C, F)
    assert s.theta_off == pytest.approx(math.pi - math.atan(W * R * C), abs=1e-9)
    w = m.cap_filter("meia_onda", VM, 0.0, R, C, F)
    assert max(w.vo) - min(w.vo) == pytest.approx(VM / (F * R * C), rel=0.02)  # ΔVo ≈ Vm/(fRC)
    w = m.cap_filter("ponte", VM, 0.0, R, C, F)
    assert max(w.vo) - min(w.vo) == pytest.approx(VM / (2 * F * R * C), rel=0.02)


def test_gt_ret1_lc_filter():
    L = 2 * m.critical_inductance(R, F)
    assert m.critical_inductance(R, F) == pytest.approx(R / (3 * W))
    w = m.lc_filter("ponte", VM, 0.0, R, L, 10e-3, F)
    assert m.mean(w.vo) == pytest.approx(2 * VM / math.pi, rel=1e-6)
    # with C large the ripple is the second harmonic 4Vm/(3π) attenuated by (2ω)²LC − 1
    v2 = 4 * VM / (3 * math.pi)
    approx = 2 * v2 / ((2 * W) ** 2 * L * 10e-3 - 1)
    assert max(w.vo) - min(w.vo) == pytest.approx(approx, rel=0.05)
