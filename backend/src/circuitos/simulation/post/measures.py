"""Waveform measurements on simulation results (prompt, section 8).

Transient results from SPICE have a non-uniform time step, so averages and RMS values are
computed by trapezoidal integration over the actual samples, and spectra are computed after
resampling to a uniform grid.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pint
from numpy.typing import NDArray

from circuitos.core.errors import UnitError
from circuitos.core.units import Q_, require

FloatArray = NDArray[np.float64]


def _xy(t: pint.Quantity, y: pint.Quantity) -> tuple[FloatArray, FloatArray, Any]:
    require(t, "s", "t")
    if not isinstance(y, pint.Quantity):
        raise UnitError("O sinal deve ter unidade")
    tm = np.asarray(t.m_as("s"), dtype=float)
    ym = np.asarray(y.magnitude, dtype=float)
    if tm.shape != ym.shape or tm.ndim != 1 or tm.size < 2:
        raise ValueError("t e y devem ser vetores 1-D do mesmo tamanho (≥ 2 pontos)")
    if np.any(np.diff(tm) < 0):
        raise ValueError("t deve ser crescente")
    return tm, ym, y.units


def window(
    t: pint.Quantity,
    y: pint.Quantity,
    start: pint.Quantity | None = None,
    stop: pint.Quantity | None = None,
) -> tuple[pint.Quantity, pint.Quantity]:
    """Slice [start, stop], interpolating the end points so the interval is exact."""
    tm, ym, unit = _xy(t, y)
    a = tm[0] if start is None else float(require(start, "s").m_as("s"))
    b = tm[-1] if stop is None else float(require(stop, "s").m_as("s"))
    if not tm[0] <= a < b <= tm[-1] + 1e-15:
        raise ValueError("Janela fora do intervalo simulado")
    inner = (tm > a) & (tm < b)
    tt = np.concatenate(([a], tm[inner], [b]))
    yy = np.concatenate(([np.interp(a, tm, ym)], ym[inner], [np.interp(b, tm, ym)]))
    return Q_(tt, "s"), Q_(yy, unit)


def last_periods(
    t: pint.Quantity, y: pint.Quantity, period: pint.Quantity, n: int = 1
) -> tuple[pint.Quantity, pint.Quantity]:
    """Steady-state window: the last ``n`` whole periods (discards the start-up transient)."""
    end = t[-1]
    return window(t, y, end - n * require(period, "s"), end)


def mean(t: pint.Quantity, y: pint.Quantity) -> pint.Quantity:
    tm, ym, unit = _xy(t, y)
    return Q_(np.trapezoid(ym, tm) / (tm[-1] - tm[0]), unit)


def rms(t: pint.Quantity, y: pint.Quantity) -> pint.Quantity:
    tm, ym, unit = _xy(t, y)
    return Q_(np.sqrt(np.trapezoid(ym**2, tm) / (tm[-1] - tm[0])), unit)


def peak(y: pint.Quantity) -> pint.Quantity:
    return Q_(float(np.max(np.abs(y.magnitude))), y.units)


def peak_to_peak(y: pint.Quantity) -> pint.Quantity:
    m = np.asarray(y.magnitude)
    return Q_(float(m.max() - m.min()), y.units)


def average_power(t: pint.Quantity, v: pint.Quantity, i: pint.Quantity) -> pint.Quantity:
    require(v, "V", "v")
    require(i, "A", "i")
    return mean(t, (v * i).to("W"))


def resample(t: pint.Quantity, y: pint.Quantity, n: int) -> tuple[pint.Quantity, pint.Quantity]:
    """Uniform grid of ``n`` points over the same interval, without repeating the end point."""
    tm, ym, unit = _xy(t, y)
    tu = tm[0] + (tm[-1] - tm[0]) * np.arange(n) / n
    return Q_(tu, "s"), Q_(np.interp(tu, tm, ym), unit)


def spectrum(
    t: pint.Quantity,
    y: pint.Quantity,
    n: int = 2**14,
    window_kind: Literal["rect", "hann"] = "rect",
) -> tuple[pint.Quantity, pint.Quantity]:
    """Single-sided amplitude spectrum (peak amplitude of each component).

    Use ``rect`` when the record spans an integer number of periods (coherent sampling, exact
    harmonic amplitudes); ``hann`` otherwise, to limit leakage.
    """
    tu, yu = resample(t, y, n)
    tm = tu.m_as("s")
    ym = yu.magnitude
    w = np.ones(n) if window_kind == "rect" else np.hanning(n)
    spec = np.fft.rfft(ym * w) / np.sum(w)
    amp = np.abs(spec)
    amp[1:] *= 2.0
    if n % 2 == 0:
        amp[-1] /= 2.0
    dt = tm[1] - tm[0]
    freqs = np.fft.rfftfreq(n, dt)
    return Q_(freqs, "Hz"), Q_(amp, yu.units)


def harmonics(
    t: pint.Quantity, y: pint.Quantity, f0: pint.Quantity, n_harmonics: int = 50
) -> pint.Quantity:
    """Peak amplitude of harmonics 0..n of ``f0`` by direct Fourier integration.

    The record should span an integer number of periods of ``f0`` (see :func:`last_periods`).
    Index 0 is the mean value.
    """
    tm, ym, unit = _xy(t, y)
    f = float(require(f0, "Hz", "f0").m_as("Hz"))
    span = tm[-1] - tm[0]
    out = np.empty(n_harmonics + 1)
    out[0] = np.trapezoid(ym, tm) / span
    for k in range(1, n_harmonics + 1):
        arg = 2 * np.pi * k * f * tm
        a = 2 * np.trapezoid(ym * np.cos(arg), tm) / span
        b = 2 * np.trapezoid(ym * np.sin(arg), tm) / span
        out[k] = np.hypot(a, b)
    return Q_(out, unit)


def thd(
    t: pint.Quantity, y: pint.Quantity, f0: pint.Quantity, n_harmonics: int = 50
) -> pint.Quantity:
    """Total harmonic distortion relative to the fundamental (dimensionless ratio)."""
    h = harmonics(t, y, f0, n_harmonics).magnitude
    if h[1] == 0:
        raise ValueError("Fundamental nula: THD indefinida")
    return Q_(float(np.sqrt(np.sum(h[2:] ** 2)) / h[1]), "")


def frequency(
    t: pint.Quantity, y: pint.Quantity, level: pint.Quantity | None = None
) -> pint.Quantity:
    """Fundamental frequency from rising crossings of ``level`` (default: the mean value)."""
    tm, ym, unit = _xy(t, y)
    lv = float(mean(t, y).magnitude) if level is None else float(level.m_as(unit))
    s = ym - lv
    idx = np.where((s[:-1] < 0) & (s[1:] >= 0))[0]
    if idx.size < 2:
        raise ValueError("Menos de dois cruzamentos: frequência indeterminada")
    crossings = tm[idx] - s[idx] * (tm[idx + 1] - tm[idx]) / (s[idx + 1] - s[idx])
    return Q_(1.0 / float(np.mean(np.diff(crossings))), "Hz")


def duty_cycle(
    t: pint.Quantity, y: pint.Quantity, level: pint.Quantity | None = None
) -> pint.Quantity:
    """Fraction of time above ``level`` (default: midpoint between minimum and maximum)."""
    tm, ym, unit = _xy(t, y)
    lv = (ym.max() + ym.min()) / 2 if level is None else float(level.m_as(unit))
    tu = np.linspace(tm[0], tm[-1], max(20 * tm.size, 10_000))
    yu = np.interp(tu, tm, ym)
    return Q_(float(np.mean(yu > lv)), "")
