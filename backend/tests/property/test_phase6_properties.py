"""PT-ENERGIA, PT-CC-D, PT-INV-MA and PT-FFT-PARSEVAL: properties of the Phase 6 models."""

import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from circuitos.design import registry
from circuitos.design.inverter import grid, leg_voltages, load_voltages, spectrum, switching
from circuitos.design.power import converter_model, steady_state

TOPOLOGIES = ("buck", "boost", "buckboost", "cuk", "sepic", "zeta")


def currents(top: str, x: np.ndarray, D: float) -> tuple[float, float]:
    """(average input current, switch current while on) of the averaged model."""
    if top in ("buck", "boost", "buckboost"):
        il = x[0]
        return (il if top == "boost" else D * il), il
    i_sw = x[0] + x[2]
    return (x[0] if top in ("cuk", "sepic") else D * i_sw), i_sw


@settings(max_examples=150, deadline=None)
@given(
    top=st.sampled_from(TOPOLOGIES),
    D=st.floats(0.1, 0.9),
    vin=st.floats(5, 400),
    R=st.floats(1, 100),
    ron=st.floats(0, 0.5),
    vd=st.floats(0, 1.5),
)
def test_pt_energia_averaged_models(top, D, vin, R, ron, vd):
    """PT-ENERGIA: in steady state, Pin = Pout + D·R_on·i_sw² + (1 − D)·V_D·i_d (the diode
    carries the switch current while the switch is off), for every topology (Erickson ch. 3)."""
    m = converter_model(top, 100e-6, 10e-6, R, ron, 100e-6, 10e-6)
    x = steady_state(m, D, np.array([vin, vd]))
    vo = x[m.out]
    i_in, i_sw = currents(top, x, D)
    p_in = vin * i_in
    p_out = vo**2 / R
    losses = D * ron * i_sw**2 + (1 - D) * vd * i_sw
    assert math.isclose(p_in, p_out + losses, rel_tol=1e-9, abs_tol=1e-9 * abs(p_in))


@settings(max_examples=60, deadline=None)
@given(
    top=st.sampled_from(TOPOLOGIES),
    vin=st.floats(6, 100),
    ratio=st.floats(0.2, 4.0),
    io=st.floats(0.2, 5),
)
def test_pt_cc_d_duty_in_range(top, vin, ratio, io):
    """PT-CC-D: the design always returns 0 < D < 1 and the averaged output equals Vo."""
    if top == "buck":
        ratio = min(ratio, 0.9)
    if top == "boost":
        ratio = max(ratio, 1.15)
    mod = registry.get("DM-CC")
    spec = mod.spec_schema(
        topology=top,
        Vin={"value": vin, "unit": "V"},
        Vo={"value": vin * ratio, "unit": "V"},
        Io={"value": io, "unit": "A"},
        compensator="nenhum",
        Vref={"value": min(2.5, 0.5 * vin * ratio), "unit": "V"},
    )
    sm = mod.analyse(spec, {}).summary
    d = sm["D"].m_as("")
    assert 0 < d < 1
    assert math.isclose(sm["Vo_avg"].m_as("V"), vin * ratio, rel_tol=1e-6)


@settings(max_examples=40, deadline=None)
@given(ma=st.floats(0.1, 1.0), mf=st.sampled_from([9, 15, 21, 33, 51]), uni=st.booleans())
def test_pt_inv_ma_linear(ma, mf, uni):
    """PT-INV-MA: in the linear region the fundamental is ma·Vdc (Hart ch. 8)."""
    th = grid(2**15)
    mod = "spwm_unipolar" if uni else "spwm_bipolar"
    v = load_voltages(1, leg_voltages(switching(mod, 1, ma, mf, 0.0, th), 1.0))[0]
    assert math.isclose(abs(spectrum(v)[1]), ma, rel_tol=2e-3, abs_tol=1e-3)


@settings(max_examples=40, deadline=None)
@given(
    mod=st.sampled_from(["quadrada", "spwm", "svpwm"]),
    ma=st.floats(0.1, 1.0),
    mf=st.sampled_from([9, 15, 21]),
)
def test_pt_fft_parseval(mod, ma, mf):
    """PT-FFT-PARSEVAL: the mean square of the phase voltage equals c0² + Σ|cn|²/2."""
    th = grid(2**14)
    v = load_voltages(3, leg_voltages(switching(mod, 3, ma, mf, 0.0, th), 1.0))[0]
    c = spectrum(v)
    energy = abs(c[0]) ** 2 + float(np.sum(np.abs(c[1:]) ** 2)) / 2
    # the Nyquist bin of an even-length FFT is counted twice by the doubling: correct it
    energy -= abs(c[-1]) ** 2 / 4
    assert math.isclose(float(np.mean(v**2)), energy, rel_tol=1e-9)
