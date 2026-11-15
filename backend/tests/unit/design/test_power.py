"""Shared power-electronics models: averaged state space, compensators, loop margins."""

import math

import numpy as np
import pytest

from circuitos.core.calc import CalcLog
from circuitos.design.power import (
    Compensator,
    converter_model,
    gvd,
    k_factor,
    margins,
    solve_duty,
    steady_state,
)

U = np.array([12.0, 0.0])
L, C, R = 100e-6, 100e-6, 10.0


@pytest.mark.parametrize(
    ("top", "gain"),
    [
        ("buck", lambda d: d),
        ("boost", lambda d: 1 / (1 - d)),
        ("buckboost", lambda d: d / (1 - d)),
        ("cuk", lambda d: d / (1 - d)),
        ("sepic", lambda d: d / (1 - d)),
        ("zeta", lambda d: d / (1 - d)),
    ],
)
def test_ideal_conversion_ratios(top, gain):
    # Erickson & Maksimović, 2nd ed., ch. 2: M(D) of the ideal converters
    m = converter_model(top, L, C, R, 0.0, 2 * L, C / 2)
    for d in (0.2, 0.4, 0.6):
        assert steady_state(m, d, U)[m.out] == pytest.approx(12 * gain(d), rel=1e-12)


def test_fourth_order_capacitor_voltages():
    d = 0.4
    vo = 12 * d / (1 - d)
    for top, vc1 in (("cuk", 12 + vo), ("sepic", 12.0), ("zeta", vo)):
        m = converter_model(top, L, C, R, 0.0, L, C)
        assert steady_state(m, d, U)[1] == pytest.approx(vc1, rel=1e-12)


def test_buck_with_losses_matches_closed_form():
    # Erickson ch. 3: buck with R_on and V_D: Vo = (D·Vin − D'·VD)/(1 + R_on·D/R)... solved
    # from the averaged equations: D(Vin − R_on·I) − D'·VD = Vo, I = Vo/R
    ron, vd, vin = 0.2, 0.6, 24.0
    m = converter_model("buck", L, C, R, ron)
    d = 0.5
    vo = steady_state(m, d, np.array([vin, vd]))[1]
    assert vo == pytest.approx((d * vin - (1 - d) * vd) / (1 + d * ron / R), rel=1e-12)
    assert solve_duty(lambda _d: m, vo, np.array([vin, vd])) == pytest.approx(d, abs=1e-9)


@pytest.mark.parametrize("f", [50.0, 1e3, 5e3, 20e3])
def test_gvd_buck_and_boost(f):
    # Erickson ch. 8: buck Gvd = V/D / (1 + sL/R + s²LC); boost
    # Gvd = V/D' · (1 − sL/(D'²R)) / (1 + sL/(D'²R) + s²LC/D'²)
    s = 2j * math.pi * f
    d = 0.4
    buck = converter_model("buck", L, C, R, 0.0)
    assert gvd(buck, d, U, np.array([f]))[0] == pytest.approx(12 / (1 + s * L / R + s**2 * L * C))
    dp = 1 - d
    v = 12 / dp
    boost = converter_model("boost", L, C, R, 0.0)
    want = v / dp * (1 - s * L / (dp**2 * R)) / (1 + s * L / (dp**2 * R) + s**2 * L * C / dp**2)
    assert gvd(boost, d, U, np.array([f]))[0] == pytest.approx(want)


@pytest.mark.parametrize(("kind", "boost"), [("II", 30), ("II", 70), ("III", 120), ("III", 160)])
def test_k_factor_gives_gain_and_phase_at_fc(kind, boost):
    fc, mag, pm = 2e3, 0.3, 60
    ph = pm - 90 - boost
    c = k_factor(CalcLog(), kind, fc, mag, ph, pm, 10e3)
    h = c.h(np.array([fc]))[0]
    assert abs(h) == pytest.approx(1 / mag, rel=1e-9)
    assert math.degrees(np.angle(h)) == pytest.approx(boost - 90, abs=1e-6)


def test_margins_of_an_integrator_with_a_pole():
    # T = wc/s · 1/(1 + s/wp) with wp = wc: |T| = 1 at ≈ 0,786 wc, PM = 90° − atan(0,786)
    f = np.logspace(1, 6, 4000)
    s = 2j * math.pi * f
    wc = 2 * math.pi * 1e3
    T = wc / s / (1 + s / wc)
    m, n = margins(f, T)
    x = math.sqrt((math.sqrt(5) - 1) / 2)
    assert n == 1
    assert m.fc == pytest.approx(1e3 * x, rel=1e-3)
    assert m.pm == pytest.approx(90 - math.degrees(math.atan(x)), abs=0.05)
    assert m.gm_db is None


def test_compensator_type_ii_shape():
    c = Compensator("II", 10e3, 50e3, 10e-9, 1e-9)
    f = np.array([1.0, 1e9])
    h = c.h(f)
    assert abs(h[0]) > 1e3  # integrator at low frequency
    assert abs(h[1]) < 1e-2
