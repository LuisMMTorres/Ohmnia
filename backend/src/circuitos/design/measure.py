"""Quantities measured on the simulated steady state: peak, mean and RMS values of every probe,
and the powers (S, P, Q, D) with the power factor at each power port of the circuit.

Every value comes from the ngspice run (the last source period of the transient), never from
the analytic model, so the results table shows what the simulated circuit actually does.

Definitions (single phase, periodic signals of period T):

- mean ``X = (1/T)∫x dt``; RMS ``X_ef = √((1/T)∫x² dt)``; peak ``max |x|``;
- active power ``P = (1/T)∫v·i dt``; apparent power ``S = V_ef·I_ef``;
- reactive power of the fundamental ``Q₁ = V₁·I₁·sin(φv₁ − φi₁)`` (V₁, I₁ RMS of the first
  harmonic); distortion power ``D = √(S² − P² − Q₁²)`` (Budeanu's decomposition);
- power factor ``FP = P/S`` and displacement factor ``cos φ₁``.

IEEE Std 1459-2010, "Definitions for the Measurement of Electric Power Quantities Under
Sinusoidal, Nonsinusoidal, Balanced, or Unbalanced Conditions", sections 3.1 and 3.2 (the
standard recommends the non-active power N = √(S² − P²); Budeanu's Q and D are kept here because
they are the textbook split, and N follows from them as √(Q₁² + D²)).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from circuitos.core.units import QuantityModel

from .base import Circuit, PowerPort
from .verify import SteadyState

FloatArray = NDArray[np.float64]
_FIRST = re.compile(r"([vi])\(")


def probe_unit(expression: str) -> str:
    """V for a sum of node voltages, A for a sum of branch currents."""
    m = _FIRST.search(expression.lower())
    return "A" if m and m.group(1) == "i" else "V"


class WaveMeasure(BaseModel):
    label: str
    unit: str
    peak: QuantityModel  # max |x|
    max: QuantityModel
    min: QuantityModel
    avg: QuantityModel
    rms: QuantityModel


class PowerMeasure(BaseModel):
    label: str
    V_rms: QuantityModel
    I_rms: QuantityModel
    S: QuantityModel
    P: QuantityModel
    Q: QuantityModel  # reactive power of the fundamental
    D: QuantityModel  # distortion power
    PF: QuantityModel  # P / S
    DPF: QuantityModel  # cos φ1


def _avg(t: FloatArray, y: FloatArray) -> float:
    span = float(t[-1] - t[0])
    return float(np.trapezoid(y, t) / span) if span > 0 else float(np.mean(y))


def _q(value: float, unit: str) -> QuantityModel:
    return QuantityModel(value=float(value), unit=unit)


def wave_measure(label: str, unit: str, t: FloatArray, x: FloatArray) -> WaveMeasure:
    hi, lo = float(np.max(x)), float(np.min(x))
    return WaveMeasure(
        label=label,
        unit=unit,
        peak=_q(max(abs(hi), abs(lo)), unit),
        max=_q(hi, unit),
        min=_q(lo, unit),
        avg=_q(_avg(t, x), unit),
        rms=_q(math.sqrt(max(_avg(t, x * x), 0.0)), unit),
    )


def _fundamental(x: FloatArray) -> complex:
    """Phasor (RMS) of the first harmonic of one period sampled uniformly."""
    return complex(np.fft.rfft(x)[1] / x.size * 2 / math.sqrt(2))


def power_measure(
    label: str,
    t: FloatArray,
    v: FloatArray,
    i: FloatArray,
    v_uniform: FloatArray,
    i_uniform: FloatArray,
) -> PowerMeasure:
    v_rms = math.sqrt(max(_avg(t, v * v), 0.0))
    i_rms = math.sqrt(max(_avg(t, i * i), 0.0))
    s = v_rms * i_rms
    p = _avg(t, v * i)
    v1, i1 = _fundamental(v_uniform), _fundamental(i_uniform)
    q = float((v1 * i1.conjugate()).imag)
    p1 = float((v1 * i1.conjugate()).real)
    s1 = abs(v1) * abs(i1)
    d = math.sqrt(max(s * s - p * p - q * q, 0.0))
    return PowerMeasure(
        label=label,
        V_rms=_q(v_rms, "V"),
        I_rms=_q(i_rms, "A"),
        S=_q(s, "V*A"),
        P=_q(p, "W"),
        Q=_q(q, "var"),
        D=_q(d, "V*A"),
        PF=_q(p / s if s > 0 else 0.0, ""),
        DPF=_q(p1 / s1 if s1 > 0 else 0.0, ""),
    )


class Measurements(BaseModel):
    waves: list[WaveMeasure]
    powers: list[PowerMeasure]


def probe_arrays(
    circuit: Circuit, ss: SteadyState
) -> tuple[dict[str, FloatArray], dict[str, FloatArray]]:
    """Each probe on the simulator points and on the uniform grid (mean removed if AC)."""
    raw: dict[str, FloatArray] = {}
    uni: dict[str, FloatArray] = {}
    for label, expr in circuit.probes.items():
        r, u = ss.raw[expr], ss.traces[expr]
        if label in circuit.ac_probes:
            mean = _avg(ss.t_raw, r)
            r, u = r - mean, u - mean
        raw[label], uni[label] = r, u
    return raw, uni


def port_arrays(
    port: PowerPort, ss: SteadyState
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    v, i = ss.raw[port.voltage], ss.raw[port.current]
    vu, iu = ss.traces[port.voltage], ss.traces[port.current]
    if port.ac:
        mean = _avg(ss.t_raw, i)
        i, iu = i - mean, iu - mean
    return v, i, vu, iu


def measure_all(circuit: Circuit, ss: SteadyState) -> Measurements:
    raw, _ = probe_arrays(circuit, ss)
    waves = [
        wave_measure(label, probe_unit(expr), ss.t_raw, raw[label])
        for label, expr in circuit.probes.items()
    ]
    powers = []
    for label, port in circuit.powers.items():
        v, i, vu, iu = port_arrays(port, ss)
        powers.append(power_measure(label, ss.t_raw, v, i, vu, iu))
    return Measurements(waves=waves, powers=powers)


def expressions(circuit: Circuit) -> list[str]:
    """Every vector sum the measurements need (probes and both sides of each port)."""
    out: set[str] = set(circuit.probes.values())
    for port in circuit.powers.values():
        out |= {port.voltage, port.current}
    return sorted(out)


def scale(expression: str, k: float) -> str:
    """``k·(expression)`` written as a weighted sum the measurement parser understands."""
    terms = re.findall(
        r"([+-]?)((?:\d+(?:\.\d*)?(?:e[+-]?\d+)?\*)?)([vi]\([^()]+\))",
        expression.replace(" ", "").lower(),
    )
    if not terms:
        raise ValueError(f"Expressão de medida inválida: {expression!r}")
    parts: list[str] = []
    for sign, coef, name in terms:
        c = (float(coef[:-1]) if coef else 1.0) * k * (-1.0 if sign == "-" else 1.0)
        parts.append(f"{'-' if c < 0 else '+'}{abs(c):.9g}*{name}")
    return "".join(parts).lstrip("+")


def measured_traces(
    circuit: Circuit, ss: SteadyState, extra_powers: Sequence[str] = ()
) -> Mapping[str, tuple[str, FloatArray]]:
    """Probe traces on the uniform grid plus the instantaneous power v·i of the given ports."""
    _, uni = probe_arrays(circuit, ss)
    out: dict[str, tuple[str, FloatArray]] = {
        label: (probe_unit(expr), uni[label]) for label, expr in circuit.probes.items()
    }
    for label in extra_powers:
        _, _, vu, iu = port_arrays(circuit.powers[label], ss)
        out[f"Potência instantânea: {label}"] = ("W", vu * iu)
    return out
