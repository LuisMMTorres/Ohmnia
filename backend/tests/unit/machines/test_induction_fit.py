"""Equivalent circuit fitted to a WEG data sheet (machines.induction_fit).

Source of the data: WEG, data sheet of the W22 motor, product code 16616834 (3 HP, 6 poles,
230/460 V, 60 Hz, design B), dated 08/09/2023, p. 1, column 460 V. Tolerances: the single-cage
circuit must reproduce the rated torque within 1 %, rated and no-load current within 6 %,
power factor within 10 % and breakdown torque within 8 %; the locked-rotor torque of a
deep-bar rotor is out of its reach and must come out as a warning, not be hidden (rule 4).
"""

import math

import pytest

from circuitos.machines.induction import operating_point
from circuitos.machines.induction_fit import MotorData, fit_circuit

HP = 745.6998715822701
W22 = MotorData(
    p_out=3 * HP,
    v_line=460,
    f=60,
    poles=6,
    i_n=4.41,
    n_n=1175,
    pf=0.70,
    i_lr=30.9,
    i_0=2.75,
    t_lr=2.00,
    t_bd=2.80,
    design="B",
)


@pytest.fixture(scope="module")
def fit():
    return fit_circuit(W22)


def test_rated_point_reproduced(fit):
    r = fit.value.residuals
    assert r["T_n"][1] == pytest.approx(r["T_n"][0], rel=0.01)
    assert r["I_n"][1] == pytest.approx(4.41, rel=0.06)
    assert r["I_0"][1] == pytest.approx(2.75, rel=0.06)
    assert r["pf"][1] == pytest.approx(0.70, rel=0.10)
    assert r["T_bd/T_n"][1] == pytest.approx(2.80, rel=0.08)


def test_locked_rotor_torque_misfit_is_reported(fit):
    assert any(w.startswith("T_lr/T_n") for w in fit.value.warnings)


def test_leakage_split_and_audit_trail(fit):
    p = fit.value.params
    assert p.xls / (p.xls + p.xlr) == pytest.approx(0.4)  # IEEE Std 112, design B
    assert fit.step.reference is not None and "Chapman" in fit.step.reference.book
    assert any("IEEE Std 112" in a for a in fit.step.assumptions)


def test_rated_speed_at_rated_torque(fit):
    p = fit.value.params
    t_n = W22.p_out / (W22.n_n * 2 * math.pi / 60)
    ws = 2 * math.pi * 60 / 3
    s = 1 - W22.n_n * 2 * math.pi / 60 / ws
    assert operating_point(p, 460, 60, s).torque == pytest.approx(t_n, rel=0.01)


def test_rejects_inconsistent_speed():
    bad = MotorData(**{**W22.__dict__, "n_n": 1900})
    with pytest.raises(ValueError):
        fit_circuit(bad)
