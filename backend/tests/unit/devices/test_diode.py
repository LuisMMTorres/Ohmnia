import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from circuitos.core.units import q
from circuitos.devices.diode import (
    DiodeModel,
    current,
    forward_voltage,
    saturation_current,
    thermal_voltage,
    vf_temperature_coefficient,
)

# Didactic model parameters (not a real part).
MODEL = DiodeModel(Is=q(10, "nA"), n=1.8, Rs=q(0.05, "ohm"))
T27 = q(27, "degC")


def test_thermal_voltage_at_300k():
    assert thermal_voltage(q(300, "K")).m_as("mV") == pytest.approx(25.85, abs=0.01)


def test_saturation_current_at_tnom_and_growth():
    assert saturation_current(MODEL, q(300.15, "K")).value.m_as("nA") == pytest.approx(10)
    hot = saturation_current(MODEL, q(100, "degC"))
    assert hot.value.m_as("nA") > 100 * 10  # grows by orders of magnitude
    assert hot.step.latex and hot.step.reference is not None


def test_forward_voltage_ideal_limit():
    ideal = DiodeModel(Is=q(1e-14, "A"), n=1.0, Rs=q(0, "ohm"))
    vt = thermal_voltage(q(300.15, "K")).m_as("V")
    v = forward_voltage(ideal, q(1, "mA"), q(300.15, "K")).m_as("V")
    assert v == pytest.approx(vt * np.log(1e-3 / 1e-14 + 1), rel=1e-12)


def test_current_inverts_forward_voltage_vector():
    i = q(np.logspace(-9, 1, 41), "A")
    v = forward_voltage(MODEL, i, T27)
    back = current(MODEL, v, T27)
    np.testing.assert_allclose(back.m_as("A"), i.m_as("A"), rtol=1e-8)


def test_reverse_bias_tends_to_minus_is():
    i = current(MODEL, q(-5, "V"), T27).m_as("A")
    assert i == pytest.approx(-saturation_current(MODEL, T27).value.m_as("A"), rel=1e-6)


@settings(max_examples=60, deadline=None)
@given(
    log_i=st.floats(-9, 1),
    is_exp=st.floats(-15, -6),
    n=st.floats(1.0, 2.5),
    rs=st.floats(0, 1),
    t_c=st.floats(-40, 150),
)
def test_property_roundtrip(log_i, is_exp, n, rs, t_c):
    """PT-DIODO: I(V(I)) = I for any valid model and temperature."""
    model = DiodeModel(Is=q(10**is_exp, "A"), n=n, Rs=q(rs, "ohm"))
    t = q(t_c, "degC")
    i = q(10**log_i, "A")
    assert current(model, forward_voltage(model, i, t), t).m_as("A") == pytest.approx(
        10**log_i, rel=1e-6
    )


def test_vf_decreases_with_temperature():
    """Silicon diodes: dVF/dT is negative, around −1 to −2,5 mV/K at small currents."""
    coeff = vf_temperature_coefficient(MODEL, q(10, "mA"), T27).value.m_as("mV/K")
    assert -2.5 < coeff < -1.0


def test_model_validation_and_spice_card():
    with pytest.raises(ValueError):
        DiodeModel(Is=q(-1, "nA"), n=1, Rs=q(0, "ohm"))
    assert MODEL.spice("D1").startswith(".model D1 D(IS=1e-08 N=1.8 RS=0.05")
