import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.diode import DiodeModel
from circuitos.devices.zener import (
    ZenerModel,
    dynamic_resistance,
    fit_to_datasheet,
    reverse_current,
    zener_voltage,
    zener_voltage_step,
)

FWD = DiodeModel(Is=q(10, "nA"), n=1.8, Rs=q(0.05, "ohm"))
T25 = q(25, "degC")


def make(**kw):
    base = dict(
        VZ0=q(5.0, "V"),
        Rz=q(2.0, "ohm"),
        Is_r=q(1, "uA"),
        n_r=1.5,
        TC=q(0.03, "percent/K"),
        forward=FWD,
    )
    return ZenerModel(**(base | kw))


def test_voltage_and_current_are_inverse():
    m = make()
    iz = q(20, "mA")
    vz = zener_voltage(m, iz, T25)
    assert reverse_current(m, vz, T25).m_as("mA") == pytest.approx(20, rel=1e-6)


def test_below_breakdown_only_leakage():
    m = make()
    assert abs(reverse_current(m, q(1.0, "V"), T25).m_as("A")) < 2e-6


def test_tc_shifts_vz0():
    m = make()
    assert m.vz0_at(q(127, "degC")).m_as("V") == pytest.approx(5.0 * (1 + 0.0003 * 100))
    assert m.vz0_at(q(27, "degC")).m_as("V") == pytest.approx(5.0)


def test_dynamic_resistance_matches_numerical_slope():
    m = make()
    iz = q(10, "mA")
    rz = dynamic_resistance(m, iz, T25).value.m_as("ohm")
    di = 1e-6
    slope = (
        zener_voltage(m, q(10e-3 + di, "A"), T25) - zener_voltage(m, q(10e-3 - di, "A"), T25)
    ).m_as("V") / (2 * di)
    assert rz == pytest.approx(slope, rel=1e-5)


def test_fit_reproduces_test_point():
    # Synthetic test point (not a datasheet value): VZ = 5.1 V, ZZT = 7 ohm at 49 mA
    fit = fit_to_datasheet(
        q(5.1, "V"),
        q(49, "mA"),
        q(7, "ohm"),
        q(30, "degC"),
        n_r=1.5,
        Is_r=q(1, "uA"),
        TC=q(0.03, "percent/K"),
        forward=FWD,
    )
    assert not fit.warnings
    t = q(30, "degC")
    assert zener_voltage(fit.model, q(49, "mA"), t).m_as("V") == pytest.approx(5.1, rel=1e-9)
    assert dynamic_resistance(fit.model, q(49, "mA"), t).value.m_as("ohm") == pytest.approx(
        7, rel=1e-9
    )
    assert [s.step.id for s in fit.steps] == ["Rz_fit", "VZ0_fit"]


def test_fit_clamps_negative_rz():
    fit = fit_to_datasheet(
        q(3.3, "V"),
        q(1, "mA"),
        q(1, "ohm"),
        T25,
        n_r=1.5,
        Is_r=q(1, "uA"),
        TC=q(0, "percent/K"),
        forward=FWD,
    )
    assert fit.model.Rz.m_as("ohm") == 0
    assert fit.warnings


def test_vector_input_and_step():
    m = make()
    out = reverse_current(m, q(np.array([0.0, 5.5, 6.0]), "V"), T25)
    assert out.shape == (3,)
    assert np.all(np.diff(out.m_as("A")) > 0)
    assert zener_voltage_step(m, q(10, "mA"), T25).step.id == "VZ"


def test_spice_subcircuit_text():
    text = make().spice()
    assert text.startswith(".subckt DZENER a k") and "temper" in text and text.endswith(".ends")


def test_invalid_parameters():
    with pytest.raises(ValueError):
        make(VZ0=q(-1, "V"))
    with pytest.raises(ValueError):
        make(n_r=0)
