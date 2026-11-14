import numpy as np
import pytest

from circuitos.core.errors import UnitError
from circuitos.core.units import q
from circuitos.simulation.post import measures as m

F0 = 60.0


def sine(n=2001, amp=10.0, offset=0.0, periods=2):
    t = np.linspace(0, periods / F0, n)
    return q(t, "s"), q(offset + amp * np.sin(2 * np.pi * F0 * t), "V")


def test_mean_rms_peak():
    t, v = sine(offset=2.0)
    assert m.mean(t, v).m_as("V") == pytest.approx(2.0, abs=1e-6)
    assert m.rms(t, v).m_as("V") == pytest.approx(np.sqrt(4 + 50), rel=1e-5)
    assert m.peak(v).m_as("V") == pytest.approx(12.0, rel=1e-4)
    assert m.peak_to_peak(v).m_as("V") == pytest.approx(20.0, rel=1e-4)


def test_nonuniform_time_step():
    rng = np.random.default_rng(1)
    t = np.sort(np.concatenate(([0, 1 / F0], rng.uniform(0, 1 / F0, 5000))))
    v = q(10 * np.sin(2 * np.pi * F0 * t), "V")
    assert m.rms(q(t, "s"), v).m_as("V") == pytest.approx(10 / np.sqrt(2), rel=1e-4)


def test_square_wave_harmonics_and_thd():
    """Fourier series of a ±1 square wave: b_k = 4/(πk) for odd k."""
    t = np.linspace(0, 1 / F0, 200_001)
    v = q(np.where(t < 0.5 / F0, 1.0, -1.0), "V")
    h = m.harmonics(q(t, "s"), v, q(F0, "Hz"), 9).m_as("V")
    for k in (1, 3, 5, 7, 9):
        assert h[k] == pytest.approx(4 / (np.pi * k), rel=1e-3)
    for k in (2, 4, 6, 8):
        assert h[k] == pytest.approx(0, abs=1e-3)
    # Analytical THD of a square wave: sqrt(π²/8 − 1) ≈ 0.4834 (all harmonics).
    thd = m.thd(q(t, "s"), v, q(F0, "Hz"), 999).magnitude
    assert thd == pytest.approx(np.sqrt(np.pi**2 / 8 - 1), rel=1e-2)


def test_thd_of_pure_sine_is_zero():
    t, v = sine(periods=1, n=20001)
    assert m.thd(t, v, q(F0, "Hz"), 20).magnitude < 1e-4
    with pytest.raises(ValueError):
        m.thd(t, v * 0, q(F0, "Hz"))


def test_spectrum_coherent():
    t, v = sine(periods=4, n=40001, amp=3.0)
    f, a = m.spectrum(t, v, n=4096)
    k = int(np.argmax(a.magnitude))
    assert f[k].m_as("Hz") == pytest.approx(F0)
    assert a[k].m_as("V") == pytest.approx(3.0, rel=1e-3)
    _, ah = m.spectrum(t, v, n=4096, window_kind="hann")
    assert ah.magnitude.max() == pytest.approx(3.0, rel=1e-2)  # amplitude-normalised window
    _, odd = m.spectrum(t, v, n=4095)
    assert odd.magnitude.max() == pytest.approx(3.0, rel=1e-2)


def test_frequency_and_duty():
    t = np.linspace(0, 10e-3, 100_001)
    v = q(np.where((t * 1e3) % 1 < 0.25, 5.0, 0.0), "V")
    assert m.frequency(q(t, "s"), v).m_as("Hz") == pytest.approx(1000, rel=1e-3)
    assert m.duty_cycle(q(t, "s"), v).magnitude == pytest.approx(0.25, abs=2e-3)
    assert m.duty_cycle(q(t, "s"), v, level=q(1, "V")).magnitude == pytest.approx(0.25, abs=2e-3)
    assert m.frequency(q(t, "s"), v, level=q(2, "V")).m_as("kHz") == pytest.approx(1, rel=1e-3)
    with pytest.raises(ValueError):
        m.frequency(q([0, 1, 2], "s"), q([0, 1, 2], "V"))


def test_window_and_last_periods():
    t, v = sine(periods=3)
    tw, vw = m.last_periods(t, v, q(1 / F0, "s"), 1)
    assert tw[0].m_as("s") == pytest.approx(2 / F0)
    assert m.mean(tw, vw).m_as("V") == pytest.approx(0, abs=1e-4)
    with pytest.raises(ValueError):
        m.window(t, v, q(1, "s"), q(2, "s"))


def test_average_power():
    t, v = sine(periods=1)
    i = q(np.sin(2 * np.pi * F0 * t.m_as("s")), "A")
    assert m.average_power(t, v, i).m_as("W") == pytest.approx(5.0, rel=1e-4)
    with pytest.raises(UnitError):
        m.average_power(t, i, i)


def test_input_validation():
    with pytest.raises(UnitError):
        m.mean(q([0, 1], "V"), q([0, 1], "V"))
    with pytest.raises(UnitError):
        m.mean(q([0, 1], "s"), [0, 1])
    with pytest.raises(ValueError):
        m.mean(q([0, 1, 2], "s"), q([0, 1], "V"))
    with pytest.raises(ValueError):
        m.mean(q([1, 0], "s"), q([0, 1], "V"))
