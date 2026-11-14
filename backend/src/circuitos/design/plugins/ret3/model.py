"""Analytic model of three-phase rectifiers (DM-RET3): 3, 6 and 12 pulses, with commutation.

Assumptions (the classic design model of Hart, *Power Electronics*, ch. 4, three-phase
rectifiers and commutation; Mohan, Undeland and Robbins, *Power Electronics*, ch. 6):

- the load current is constant, Io (load inductance large enough);
- balanced sinusoidal source with an inductance Ls per phase (secondary side); devices are
  constant drops (VT per conducting group);
- commutation from phase j to phase k starts at the firing instant (natural point + α) and
  lasts μ:  cos α − cos(α + μ) = 2ωLs·Io / V_LL,m; during it the incoming current is
  i_k = Io·(cos α − cos φ)/(cos α − cos(α + μ)), φ measured from the natural point, and the
  rail voltage is the mean of the two commutating phases.

Mean output voltage (exact in this model):
    3 pulses:  Vo = (3/2π)·V_LL,m·cos α − (3ωLs/2π)·Io − VT
    6 pulses:  Vo = (3/π)·V_LL,m·cos α − (3ωLs/π)·Io − 2VT
    12 pulses: two 6-pulse bridges in series, one fed by a Y and one by a Δ secondary with the
               same line voltage (30° apart): twice the 6-pulse value.

Phase voltages: e_k = V_ph,m·sin(θ − shift − k·2π/3), k = 0, 1, 2 (a, b, c).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

Pulses = Literal[3, 6, 12]
FloatArray = NDArray[np.float64]
N_GRID = 14400
TWO_THIRDS_PI = 2 * math.pi / 3


def overlap_angle(alpha: float, Io: float, Ls: float, Vll_m: float, f: float) -> float:
    """μ from cos α − cos(α + μ) = 2ωLs·Io/V_LL,m."""
    x = math.cos(alpha) - 2 * (2 * math.pi * f) * Ls * Io / Vll_m
    if x < -1:
        raise ValueError("Comutação não termina: indutância da fonte grande demais para Io")
    return max(math.acos(x) - alpha, 0.0)


def mean_output(
    pulses: Pulses, Vll_m: float, alpha: float, Io: float, Ls: float, f: float, VT: float
) -> float:
    w = 2 * math.pi * f
    if pulses == 3:
        return 3 / (2 * math.pi) * Vll_m * math.cos(alpha) - 3 * w * Ls / (2 * math.pi) * Io - VT
    six = 3 / math.pi * Vll_m * math.cos(alpha) - 3 * w * Ls / math.pi * Io - 2 * VT
    return six if pulses == 6 else 2 * six


def peak_line_voltage_for(
    pulses: Pulses, Vo: float, alpha: float, Io: float, Ls: float, f: float, VT: float
) -> float:
    """Invert :func:`mean_output` for V_LL,m (secondary)."""
    w = 2 * math.pi * f
    if math.cos(alpha) <= 0:
        raise ValueError("α nominal deve ser menor que 90° para retificar")
    if pulses == 3:
        return (Vo + 3 * w * Ls / (2 * math.pi) * Io + VT) * 2 * math.pi / (3 * math.cos(alpha))
    six = Vo if pulses == 6 else Vo / 2
    return (six + 3 * w * Ls / math.pi * Io + 2 * VT) * math.pi / (3 * math.cos(alpha))


def _grid() -> FloatArray:
    return np.linspace(0, 2 * math.pi, N_GRID, endpoint=False)


def phases(theta: FloatArray, Vll_m: float, shift: float = 0.0) -> list[FloatArray]:
    vph = Vll_m / math.sqrt(3)
    return [vph * np.sin(theta - shift - k * TWO_THIRDS_PI) for k in range(3)]


def _group(
    theta: FloatArray,
    e: list[FloatArray],
    natural0: float,
    alpha: float,
    mu: float,
    Io: float,
) -> tuple[FloatArray, list[FloatArray]]:
    """Rail voltage and per-phase currents of one commutating group (top or bottom)."""
    ca = math.cos(alpha)
    denom = ca - math.cos(alpha + mu)
    rail = np.zeros_like(theta)
    currents: list[FloatArray] = []
    for k in range(3):
        u = np.mod(theta - natural0 - k * TWO_THIRDS_PI, 2 * math.pi)
        if mu > 0:
            rise = np.clip((ca - np.cos(u)) / denom, 0.0, 1.0)
            fall = 1 - np.clip((ca - np.cos(u - TWO_THIRDS_PI)) / denom, 0.0, 1.0)
        else:
            rise = np.ones_like(u)
            fall = np.zeros_like(u)
        i = np.where(
            (u >= alpha) & (u < alpha + mu),
            rise,
            np.where(
                (u >= alpha + mu) & (u < alpha + TWO_THIRDS_PI),
                1.0,
                np.where(
                    (u >= alpha + TWO_THIRDS_PI) & (u < alpha + TWO_THIRDS_PI + mu), fall, 0.0
                ),
            ),
        )
        currents.append(Io * i)
        prev = e[(k - 1) % 3]
        own = (u >= alpha) & (u < alpha + TWO_THIRDS_PI)
        overlap = (u >= alpha) & (u < alpha + mu)
        rail = np.where(own, np.where(overlap, (e[k] + prev) / 2, e[k]), rail)
    return rail, currents


@dataclass
class Bridge:
    vo: FloatArray  # output voltage of the bridge (drops included)
    e: list[FloatArray]  # source EMFs (secondary, per phase)
    i_line: list[FloatArray]  # line currents into the bridge
    i_dev: FloatArray  # current of one device (top device of phase a)
    shift: float


def bridge(
    theta: FloatArray,
    Vll_m: float,
    alpha: float,
    mu: float,
    Io: float,
    VT: float,
    shift: float = 0.0,
    six_pulse: bool = True,
) -> Bridge:
    e = phases(theta, Vll_m, shift)
    top, i_top = _group(theta, e, math.pi / 6 + shift, alpha, mu, Io)
    if not six_pulse:
        return Bridge(vo=top - VT, e=e, i_line=i_top, i_dev=i_top[0], shift=shift)
    neg = [-x for x in e]
    # the bottom group follows the most negative phase, i.e. the largest of −e: natural point of
    # phase a at 210°; its "rail" is −v_n
    bottom_neg, i_bot = _group(theta, neg, 7 * math.pi / 6 + shift, alpha, mu, Io)
    vo = top + bottom_neg - 2 * VT
    i_line = [i_top[k] - i_bot[k] for k in range(3)]
    return Bridge(vo=vo, e=e, i_line=i_line, i_dev=i_top[0], shift=shift)


@dataclass
class Waves:
    theta: FloatArray
    vo: FloatArray
    e: list[FloatArray]  # reference phase EMFs (Y secondary, or the primary referred to it)
    i_ref: list[FloatArray]  # line currents referred to the reference windings (no DC)
    bridges: list[Bridge]
    mu: float


def waves(
    pulses: Pulses, Vll_m: float, alpha: float, Io: float, Ls: float, f: float, VT: float
) -> Waves:
    theta = _grid()
    mu = overlap_angle(alpha, Io, Ls, Vll_m, f)
    if pulses == 3:
        b = bridge(theta, Vll_m, alpha, mu, Io, VT, six_pulse=False)
        i_ref = [
            i - np.mean(i) for i in b.i_line
        ]  # the DC of each phase does not pass to the primary
        return Waves(theta, b.vo, b.e, i_ref, [b], mu)
    b1 = bridge(theta, Vll_m, alpha, mu, Io, VT)
    if pulses == 6:
        return Waves(theta, b1.vo, b1.e, b1.i_line, [b1], mu)
    # 12 pulses: bridge 2 on a Δ secondary whose line voltages are in phase with the primary
    # phase voltages, i.e. 30° behind those of the Y secondary
    b2 = bridge(theta, Vll_m, alpha, mu, Io, VT, shift=math.pi / 6)
    # ampere-turns per primary phase, referred to the Y secondary (Δ winding has √3 turns)
    i2 = b2.i_line
    i_ref = [b1.i_line[k] + (i2[k] - i2[(k + 1) % 3]) / math.sqrt(3) for k in range(3)]
    return Waves(theta, b1.vo + b2.vo, b1.e, i_ref, [b1, b2], mu)


def mean(x: FloatArray) -> float:
    return float(np.mean(x))


def rms(x: FloatArray) -> float:
    return float(np.sqrt(np.mean(x**2)))


def thd(x: FloatArray, n: int = 50) -> float:
    spec = np.fft.rfft(x - np.mean(x)) / x.size
    amp = np.abs(spec[: n + 1]) * 2
    return float(np.sqrt(np.sum(amp[2:] ** 2)) / amp[1])


def input_power(w: Waves) -> float:
    """Power delivered by the source EMFs (all bridges)."""
    return float(sum(np.mean(e * i) for b in w.bridges for e, i in zip(b.e, b.i_line, strict=True)))


def power_factor(w: Waves) -> float:
    s = 3 * rms(w.e[0]) * rms(w.i_ref[0])
    return input_power(w) / s if s > 0 else 0.0


def displacement_factor(w: Waves) -> float:
    v1 = np.fft.rfft(w.e[0])[1]
    i1 = np.fft.rfft(w.i_ref[0])[1]
    return float(math.cos(np.angle(i1) - np.angle(v1)))
