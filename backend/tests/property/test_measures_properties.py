"""PT-RMS: properties of waveform measurements."""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from circuitos.core.eseries import snap
from circuitos.core.units import q
from circuitos.simulation.post import measures as m

amps = st.floats(0.01, 1e3)
offsets = st.floats(-1e3, 1e3)


@settings(max_examples=40, deadline=None)
@given(amp=amps, offset=offsets)
def test_rms_squared_is_dc_plus_ac(amp, offset):
    t = np.linspace(0, 1, 4001)
    v = q(offset + amp * np.sin(2 * np.pi * t), "V")
    rms = m.rms(q(t, "s"), v).m_as("V")
    assert np.isclose(rms**2, offset**2 + amp**2 / 2, rtol=1e-5)
    assert rms >= abs(m.mean(q(t, "s"), v).m_as("V")) - 1e-9  # RMS ≥ |média|


@settings(max_examples=40, deadline=None)
@given(amp=amps, k=st.integers(2, 9), ratio=st.floats(0, 1))
def test_thd_recovers_single_harmonic(amp, k, ratio):
    t = np.linspace(0, 1, 20001)
    y = amp * (np.sin(2 * np.pi * t) + ratio * np.sin(2 * np.pi * k * t))
    thd = m.thd(q(t, "s"), q(y, "V"), q(1, "Hz"), 10).magnitude
    assert np.isclose(thd, ratio, atol=1e-4)


@settings(max_examples=200, deadline=None)
@given(value=st.floats(1e-12, 1e12))
def test_snap_stays_within_half_step(value):
    """PT-ESERIES: snapping never moves more than half a step of the series (log scale)."""
    for name, n in (("E12", 12), ("E24", 24), ("E96", 96)):
        out = snap(q(value, "ohm"), name).m_as("ohm")  # type: ignore[arg-type]
        assert abs(np.log10(out / value)) <= 0.5 / n + 0.02
        assert snap(q(value, "ohm"), name, "up").m_as("ohm") >= value * (1 - 1e-9)  # type: ignore[arg-type]
        assert snap(q(value, "ohm"), name, "down").m_as("ohm") <= value * (1 + 1e-9)  # type: ignore[arg-type]
