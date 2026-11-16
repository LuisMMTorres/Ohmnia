"""Analytic models of the drives and the thermocouple (Fase 11 leftovers, decision D12)."""

from __future__ import annotations

import math

import pytest

from circuitos.machines import thermocouple as tc
from circuitos.machines.induction import (
    InductionParams,
    breakdown_slip,
    operating_point,
    steady_state,
)
from circuitos.machines.stepper import load_angle_deg, rotor_teeth, torque_constant

MOTOR = InductionParams(rs=1.5, rr=1.2, xls=2.5, xlr=2.5, xm=60, poles=4, fnom=60)


@pytest.mark.parametrize(
    ("kind", "temp", "mv"),
    [
        # Omega Z-204, type K (NIST Monograph 175, ITS-90), p. 1 and p. 2
        ("K", -100, -3.554),
        ("K", 100, 4.096),
        ("K", 500, 20.644),
        ("K", 1000, 41.276),
        # Omega Z-206, type E, p. 1
        ("E", -100, -5.237),
        ("E", 100, 6.319),
        ("E", 500, 37.005),
        ("E", 1000, 76.373),
    ],
)
def test_thermocouple_matches_the_printed_tables(kind, temp, mv):
    """The tables print 3 decimals: agreement within half of the last digit."""
    assert tc.emf_mv(kind, temp) == pytest.approx(mv, abs=5e-4)


def test_thermocouple_zero_at_the_reference_and_out_of_range():
    for kind in tc.TYPES:
        assert tc.emf_mv(kind, 0.0) == pytest.approx(0.0, abs=1e-12)
    with pytest.raises(ValueError, match="fora da faixa"):
        tc.emf_mv("T", 500)


def test_power_balance_of_the_equivalent_circuit():
    """P_in = P_mech + stator copper + rotor copper (no iron losses in the model)."""
    s = 0.04
    op = operating_point(MOTOR, 380, 60, s)
    p_ag = op.torque * 2 * math.pi * 60 / 2
    p_cu1 = 3 * op.i1**2 * MOTOR.rs
    assert op.p_in == pytest.approx(p_ag + p_cu1, rel=1e-9)
    assert op.p_mech == pytest.approx(p_ag * (1 - s), rel=1e-9)


def test_breakdown_slip_gives_the_maximum_torque():
    s_max = breakdown_slip(MOTOR, 60)
    t_max = operating_point(MOTOR, 380, 60, s_max).torque
    for s in (0.9 * s_max, 1.1 * s_max):
        assert operating_point(MOTOR, 380, 60, s).torque < t_max


def test_steady_state_balances_the_load():
    op = steady_state(MOTOR, 380, 60, 20)
    assert op.torque == pytest.approx(20, rel=1e-9)
    assert 1700 < op.speed_rpm < 1800
    fan = steady_state(MOTOR, 380, 60, 20, quadratic=True)
    w = fan.speed_rpm * 2 * math.pi / 60
    assert fan.torque == pytest.approx(20 * (w / (2 * math.pi * 30)) ** 2, rel=1e-9)


def test_stepper_relations():
    """1,8° → 50 teeth; 17HS19-2004S1: 0,59 N·m at 2,0 A → K = 0,2086 N·m/A."""
    assert rotor_teeth(1.8) == pytest.approx(50)
    k = torque_constant(0.59, 2.0)
    assert k == pytest.approx(0.2086, rel=1e-3)
    assert load_angle_deg(0.0, k, 2.0, 1.8) == 0.0
    # at the holding torque the lag is a quarter of the electrical period: one full step
    assert load_angle_deg(k * 2.0, k, 2.0, 1.8) == pytest.approx(1.8)
    with pytest.raises(ValueError, match="perde passo"):
        load_angle_deg(1.0, k, 2.0, 1.8)
