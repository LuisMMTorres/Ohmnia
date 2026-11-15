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


def levels(t: pint.Quantity, y: pint.Quantity) -> tuple[pint.Quantity, pint.Quantity]:
    """Base and top levels as an oscilloscope finds them (histogram mode of each half).

    The signal is resampled uniformly (time weighting); the most frequent value below the
    midpoint is the base and above it the top. A step with overshoot keeps its final value as
    the top, because the ringing is brief.
    """
    tm, ym, unit = _xy(t, y)
    tu = np.linspace(tm[0], tm[-1], max(20 * tm.size, 20_000))
    yu = np.interp(tu, tm, ym)
    lo, hi = float(yu.min()), float(yu.max())
    if hi - lo <= 0:
        raise ValueError("Sinal constante: sem níveis de base e topo")
    mid = (lo + hi) / 2
    counts, edges = np.histogram(yu, bins=200, range=(lo, hi))
    centers = (edges[:-1] + edges[1:]) / 2
    k_lo = int(np.argmax(np.where(centers < mid, counts, -1)))
    k_hi = int(np.argmax(np.where(centers >= mid, counts, -1)))

    def level(k: int) -> float:
        # mean of the samples in the modal bin: no quantisation to the bin centre
        sel = (yu >= edges[k]) & (yu <= edges[k + 1])
        return float(yu[sel].mean())

    return Q_(level(k_lo), unit), Q_(level(k_hi), unit)


def _edge_time(tm: FloatArray, ym: FloatArray, a: float, b: float, rising: bool) -> float:
    """Time of the first transition from level a to level b (linear interpolation)."""
    s = ym if rising else -ym
    la, lb = (a, b) if rising else (-a, -b)

    def cross(level: float, after: float) -> float | None:
        d = s - level
        idx = np.where((d[:-1] < 0) & (d[1:] >= 0) & (tm[1:] >= after))[0]
        if idx.size == 0:
            return None
        k = int(idx[0])
        return float(tm[k] - d[k] * (tm[k + 1] - tm[k]) / (d[k + 1] - d[k]))

    start = tm[0]
    while True:
        ta = cross(la, start)
        if ta is None:
            raise ValueError("Transição não encontrada no intervalo")
        tb = cross(lb, ta)
        if tb is None:
            raise ValueError("Transição não encontrada no intervalo")
        # the signal must not fall back below a between the two crossings
        sel = (tm > ta) & (tm < tb)
        if not np.any(s[sel] < la):
            return tb - ta
        start = float(tm[sel][np.where(s[sel] < la)[0][-1]])


def rise_time(
    t: pint.Quantity, y: pint.Quantity, low: float = 0.1, high: float = 0.9
) -> pint.Quantity:
    """First 10–90 % rise between the base and top levels (:func:`levels`)."""
    tm, ym, _ = _xy(t, y)
    base, top = (q.magnitude for q in levels(t, y))
    span = top - base
    return Q_(_edge_time(tm, ym, base + low * span, base + high * span, True), "s")


def fall_time(
    t: pint.Quantity, y: pint.Quantity, low: float = 0.1, high: float = 0.9
) -> pint.Quantity:
    """First 90–10 % fall between the top and base levels."""
    tm, ym, _ = _xy(t, y)
    base, top = (q.magnitude for q in levels(t, y))
    span = top - base
    return Q_(_edge_time(tm, ym, base + high * span, base + low * span, False), "s")


def overshoot(t: pint.Quantity, y: pint.Quantity) -> pint.Quantity:
    """(max − top)/(top − base): overshoot above the top level, dimensionless ratio."""
    _, ym, _ = _xy(t, y)
    base, top = (q.magnitude for q in levels(t, y))
    return Q_(max(float(ym.max()) - top, 0.0) / (top - base), "")


def undershoot(t: pint.Quantity, y: pint.Quantity) -> pint.Quantity:
    """(base − min)/(top − base): undershoot below the base level."""
    _, ym, _ = _xy(t, y)
    base, top = (q.magnitude for q in levels(t, y))
    return Q_(max(base - float(ym.min()), 0.0) / (top - base), "")
