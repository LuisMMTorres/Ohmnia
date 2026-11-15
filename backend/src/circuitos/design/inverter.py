"""Voltage-source inverter waveforms, spectra, load currents and semiconductor losses.

Every waveform is synthesised over one fundamental period on a uniform grid: the switching
function of each leg comes from the modulation (square wave, quasi-square wave, sinusoidal PWM
with natural sampling, space-vector PWM by min-max zero-sequence injection), the dead time
shifts each turn-on edge and the current sign decides the leg voltage during the blanking
interval. Spectra come from the FFT of these waveforms, so Parseval holds by construction; the
closed forms of the square and quasi-square waves are kept for the golden tests.

References: Hart, *Power Electronics*, 1st ed., ch. 8 (inverters: square wave, amplitude and
harmonic control, PWM); Mohan, Undeland & Robbins, *Power Electronics*, 3rd ed., ch. 8
(switch-mode DC-AC inverters, blanking time); Rashid, *Power Electronics*, 4th ed., ch. 6
(DC-AC converters, space vector modulation).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from circuitos.core.calc import BibRef

FloatArray = NDArray[np.float64]
ComplexArray = NDArray[np.complex128]

HART8 = BibRef(book="Hart, Power Electronics", edition="1st", chapter="8 (inverters)")
MOHAN8 = BibRef(
    book="Mohan, Undeland & Robbins, Power Electronics",
    edition="3rd",
    chapter="8 (switch-mode DC-AC inverters)",
)
RASHID6 = BibRef(book="Rashid, Power Electronics", edition="4th", chapter="6 (DC-AC converters)")

N_GRID = 2**15


def grid(n: int = N_GRID) -> FloatArray:
    """θ = ωt over one period, endpoint excluded."""
    return np.asarray(2 * math.pi * np.arange(n) / n, dtype=np.float64)


def triangle(theta: FloatArray, mf: int) -> FloatArray:
    """Unit carrier between −1 and 1 at mf times the fundamental, −1 at θ = 0."""
    x = (theta * mf / (2 * math.pi)) % 1.0
    return np.asarray(np.where(x < 0.5, -1 + 4 * x, 3 - 4 * x), dtype=np.float64)


def references(phases: int, ma: float, theta: FloatArray, svpwm: bool = False) -> list[FloatArray]:
    """Modulating signals of each leg (per unit of the carrier peak)."""
    if phases == 1:
        r = ma * np.sin(theta)
        return [r, -r]
    refs = [ma * np.sin(theta - k * 2 * math.pi / 3) for k in range(3)]
    if svpwm:
        # min-max zero-sequence injection: same volt-seconds as symmetric SVPWM
        stack = np.vstack(refs)
        zs = -(stack.max(axis=0) + stack.min(axis=0)) / 2
        refs = [r + zs for r in refs]
    return refs


@dataclass
class Waveforms:
    theta: FloatArray
    legs: list[FloatArray]  # switching function of each leg (1: upper on), before dead time
    v_load: list[FloatArray]  # voltage across each load phase (1ph: one entry)
    v_out: FloatArray  # first load phase voltage (or the single-phase output)


def switching(
    modulation: str, phases: int, ma: float, mf: int, alpha: float, theta: FloatArray
) -> list[FloatArray]:
    """Upper-switch state of each leg (bipolar SPWM in one phase: leg b is the complement)."""
    if modulation == "quadrada":
        if phases == 1:
            a = (theta < math.pi).astype(np.float64)
            return [a, 1 - a]
        return [
            (((theta - k * 2 * math.pi / 3) % (2 * math.pi)) < math.pi).astype(np.float64)
            for k in range(3)
        ]
    if modulation == "quase_quadrada":
        # leg b lags leg a by δ = π − 2α: v_ab = +Vdc during δ, zero for α on each side
        a = (theta < math.pi).astype(np.float64)
        delta = math.pi - 2 * alpha
        b = (((theta - delta) % (2 * math.pi)) < math.pi).astype(np.float64)
        return [a, b]
    tri = triangle(theta, mf)
    if modulation == "spwm_bipolar":
        a = (ma * np.sin(theta) > tri).astype(np.float64)
        return [a, 1 - a]
    refs = references(phases, ma, theta, modulation == "svpwm")
    return [(r > tri).astype(np.float64) for r in refs]


def leg_voltages(
    states: Sequence[FloatArray],
    vdc: float,
    i_leg: Sequence[FloatArray] | None = None,
    dead_samples: int = 0,
    v_on: float = 0.0,
    r_on: float = 0.0,
    vf: float = 0.0,
    synchronous: bool = False,
) -> list[FloatArray]:
    """Leg voltages to the negative DC rail.

    Dead time: both switches are off in a window of ``dead_samples`` centred on each ideal
    edge; the conducting diode then fixes the leg at −V_F (current leaving the leg, i > 0) or
    at Vdc + V_F (i < 0) (Mohan ch. 8, blanking time). With the current known, the on-state
    drops are applied: transistor V_CE(sat) + R_on·|i|, diode V_F. ``synchronous`` (MOSFET):
    a gated channel also conducts the reverse current, with R_on·|i| instead of the diode.
    """
    out = []
    for k, s in enumerate(states):
        if i_leg is None:
            out.append(vdc * s)
            continue
        i = i_leg[k]
        on = s > 0.5
        if dead_samples > 0:
            win = np.zeros(s.size, dtype=bool)
            edges = np.nonzero(s != np.roll(s, 1))[0]
            half = dead_samples // 2
            for e in edges:
                win[(e - half + np.arange(dead_samples)) % s.size] = True
        else:
            win = np.zeros(s.size, dtype=bool)
        drop_t = v_on + r_on * np.abs(i)
        pos = i > 0
        # upper on: transistor (i > 0) drops, diode (i < 0) adds; lower on: the mirror
        rev = drop_t if synchronous else vf
        v_upper = np.where(pos, vdc - drop_t, vdc + rev)
        v_lower = np.where(pos, -rev, drop_t)
        v_blank = np.where(pos, -vf, vdc + vf)
        out.append(np.where(win, v_blank, np.where(on, v_upper, v_lower)))
    return out


def load_voltages(phases: int, v_legs: Sequence[FloatArray]) -> list[FloatArray]:
    if phases == 1:
        return [v_legs[0] - v_legs[1]]
    vn = (v_legs[0] + v_legs[1] + v_legs[2]) / 3  # floating star point
    return [v - vn for v in v_legs]


def spectrum(x: FloatArray) -> ComplexArray:
    """Complex Fourier coefficients c_n (peak amplitude |c_n|, n = 0 … N/2)."""
    c = np.fft.rfft(x) / x.size
    c[1:] *= 2
    return np.asarray(c, dtype=np.complex128)


def amplitudes(x: FloatArray) -> FloatArray:
    return np.asarray(np.abs(spectrum(x)), dtype=np.float64)


def thd(amp: FloatArray, n_max: int | None = None) -> float:
    """Total harmonic distortion relative to the fundamental (up to n_max, all if None)."""
    h = amp[2 : (n_max + 1 if n_max else None)]
    return float(np.sqrt(np.sum(h**2)) / amp[1])


def rms(x: FloatArray) -> float:
    return float(np.sqrt(np.mean(x**2)))


def square_harmonic(vdc: float, n: int, alpha: float = 0.0) -> float:
    """Peak of harmonic n of the ±Vdc quasi-square wave with zero intervals α (Hart ch. 8):
    V_n = 4Vdc/(nπ)·cos(nα), odd n."""
    return 0.0 if n % 2 == 0 else 4 * vdc / (n * math.pi) * math.cos(n * alpha)


def response(
    v: FloatArray,
    w1: float,
    R: float,
    L: float,
    Lf: float = 0.0,
    Cf: float = 0.0,
    Rd: float = 0.0,
    Cd: float = 0.0,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Steady-state load current, load voltage and inverter current for the voltage ``v``
    (one period), harmonic by harmonic: series RL load, optional L-C filter (L in series,
    C across the load) with an optional parallel R_d-C_d damping branch."""
    c = np.fft.rfft(v)
    n = np.arange(c.size, dtype=np.float64)
    s = 1j * n * w1
    zl = R + s * L
    if Cf > 0:
        with np.errstate(divide="ignore", invalid="ignore"):
            yc = s * Cf
            if Cd > 0:
                yc = yc + s * Cd / (1 + s * Cd * Rd)
            zp = zl / (1 + zl * yc)
        zin = s * Lf + zp
        h = zp / zin
    else:
        zin = zl
        h = np.ones_like(zl)
    h[0] = 1.0  # DC: ideal inductors, capacitor open
    zin[0] = R
    vl = c * h
    il = vl / zl
    iin = c / zin
    return (
        np.asarray(np.fft.irfft(il, v.size), dtype=np.float64),
        np.asarray(np.fft.irfft(vl, v.size), dtype=np.float64),
        np.asarray(np.fft.irfft(iin, v.size), dtype=np.float64),
    )


@dataclass
class LegLosses:
    p_cond_sw: float  # W per transistor
    p_cond_d: float  # W per diode
    p_sw: float  # W per transistor (on + off)
    p_rr: float  # W per diode (reverse recovery)
    i_avg_sw: float
    i_avg_d: float
    i_rms_sw: float
    i_pk: float

    @property
    def per_device(self) -> float:
        """Transistor plus its antiparallel diode (same package)."""
        return self.p_cond_sw + self.p_cond_d + self.p_sw + self.p_rr


def leg_losses(
    s: FloatArray,
    i: FloatArray,
    f1: float,
    vdc: float,
    kind: str,
    v_on: float,
    r_on: float,
    vf: float,
    e_on: float,
    e_off: float,
    v_test: float,
    i_test: float,
    tr: float,
    tf: float,
    qrr: float,
) -> LegLosses:
    """Losses of one leg (upper and lower devices are symmetric over a period; the values are
    the average of the two, per device)."""
    n = s.size
    up_t = (s > 0.5) & (i > 0)
    up_d = (s > 0.5) & (i < 0)
    lo_t = (s < 0.5) & (i < 0)
    lo_d = (s < 0.5) & (i > 0)
    ai = np.abs(i)
    if kind == "mosfet":
        # the channel conducts in both directions while the gate is on (synchronous)
        pc_t = (
            float(np.sum(ai[up_t | up_d] ** 2 * r_on) + np.sum(ai[lo_t | lo_d] ** 2 * r_on)) / n / 2
        )
        pc_d = 0.0
    else:
        pc_t = float(np.sum(ai[up_t]) + np.sum(ai[lo_t])) * v_on / n / 2
        pc_d = float(np.sum(ai[up_d]) + np.sum(ai[lo_d])) * vf / n / 2
    e_sw = 0.0
    e_rr = 0.0
    edges = np.nonzero(s != np.roll(s, 1))[0]
    for e in edges:
        ie = ai[e]
        if kind == "mosfet":
            e_on_x = 0.5 * vdc * ie * tr
            e_off_x = 0.5 * vdc * ie * tf
        else:
            k = (vdc / v_test) * (ie / i_test) if v_test > 0 and i_test > 0 else 0.0
            e_on_x, e_off_x = e_on * k, e_off * k
        rising = s[e] > 0.5
        current_out = i[e] > 0
        if rising == current_out:
            # the incoming transistor takes the current from the opposite diode
            e_sw += e_on_x
            e_rr += qrr * vdc
        else:
            # the conducting transistor turns off; the opposite diode takes over
            e_sw += e_off_x
    p_sw = e_sw * f1 / 2
    p_rr = e_rr * f1 / 2 if kind != "mosfet" or qrr > 0 else 0.0
    i_avg_sw = float(np.sum(ai[up_t]) + np.sum(ai[lo_t])) / n / 2
    i_avg_d = float(np.sum(ai[up_d]) + np.sum(ai[lo_d])) / n / 2
    i_rms_sw = math.sqrt(float(np.sum(ai[up_t] ** 2) + np.sum(ai[lo_t] ** 2)) / n / 2)
    return LegLosses(pc_t, pc_d, p_sw, p_rr, i_avg_sw, i_avg_d, i_rms_sw, float(ai.max()))
