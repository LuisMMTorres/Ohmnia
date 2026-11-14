import math

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.pn import (
    SILICON,
    Junction,
    Material,
    built_in_voltage,
    capacitance,
    current,
    depletion_steps,
    depletion_width,
    intrinsic_concentration,
    ni_m3,
    peak_field,
    saturation_current_step,
    spice,
)

T = q(300, "K")


def junction(na=1e17, nd=1e16):
    return Junction(
        NA=q(na, "1/cm**3"),
        ND=q(nd, "1/cm**3"),
        area=q(1e-4, "cm**2"),
        Dn=q(30, "cm**2/s"),
        Dp=q(10, "cm**2/s"),
        Ln=q(10, "um"),
        Lp=q(20, "um"),
    )


def test_built_in_voltage_by_hand():
    j = junction()
    ni = 7.3e15 * 300**1.5 * math.exp(-1.12 * 1.602176634e-19 / (2 * 1.380649e-23 * 300))
    vt = 1.380649e-23 * 300 / 1.602176634e-19
    expected = vt * math.log(1e17 * 1e16 / ni**2)
    assert built_in_voltage(j, T).value.m_as("V") == pytest.approx(expected, rel=1e-9)


def test_depletion_width_by_hand():
    """W at VR = 5 V, computed independently in SI units."""
    j = junction()
    v0 = built_in_voltage(j, T).value.m_as("V")
    eps = 11.7 * 8.8541878128e-12
    w = math.sqrt(2 * eps / 1.602176634e-19 * (1 / 1e23 + 1 / 1e22) * (v0 + 5))
    got, xn, xp = depletion_width(j, q(5, "V"), T)
    assert got.m_as("m") == pytest.approx(w, rel=1e-9)
    # charge neutrality and xn + xp = W
    assert (xn * 1e16).m_as("um") == pytest.approx((xp * 1e17).m_as("um"))
    assert (xn + xp).m_as("um") == pytest.approx(got.m_as("um"))


def test_capacitance_law_and_field():
    j = junction()
    v0 = built_in_voltage(j, T).value.m_as("V")
    c0 = capacitance(j, q(0, "V"), T).m_as("pF")
    c10 = capacitance(j, q(10, "V"), T).m_as("pF")
    assert c10 == pytest.approx(c0 / math.sqrt(1 + 10 / v0))
    w = depletion_width(j, q(10, "V"), T)[0].m_as("m")
    assert peak_field(j, q(10, "V"), T).m_as("V/m") == pytest.approx(2 * (v0 + 10) / w)


def test_vector_inputs():
    j = junction()
    w, _, _ = depletion_width(j, q(np.array([0.0, 1.0, 4.0]), "V"), T)
    assert w.magnitude.shape == (3,)
    assert np.all(np.diff(w.magnitude) > 0)


def test_shockley_current():
    j = junction()
    i0 = saturation_current_step(j, T).value.m_as("A")
    vt = 1.380649e-23 * 300 / 1.602176634e-19
    assert current(j, q(0.6, "V"), T).m_as("A") == pytest.approx(i0 * math.expm1(0.6 / vt))
    assert current(j, q(-5, "V"), T).m_as("A") == pytest.approx(-i0)


def test_ni_grows_with_temperature():
    t = np.array([250.0, 300.0, 350.0, 400.0])
    assert np.all(np.diff(ni_m3(SILICON, t)) > 0)
    assert intrinsic_concentration(SILICON, T).value.units == q(1, "1/cm**3").units


def test_steps_and_spice():
    j = junction()
    ids = [s.step.id for s in depletion_steps(j, q(5, "V"), T)]
    assert ids == ["W", "xn", "Emax", "Cj"]
    text = spice(j, q(27, "degC"))
    assert text.startswith(".model DPN D(") and "M=0.5" in text


def test_invalid_inputs():
    with pytest.raises(ValueError):
        junction(na=-1)
    with pytest.raises(ValueError):
        Material(B=q(0, "1/cm**3/K**1.5"), Eg=q(1.12, "eV"), eps_r=11.7)
    with pytest.raises(ValueError, match="V0"):
        built_in_voltage(junction(na=1e5, nd=1e5), T)
    with pytest.raises(ValueError, match="V0 \\+ VR"):
        depletion_width(junction(), q(-5, "V"), T)
