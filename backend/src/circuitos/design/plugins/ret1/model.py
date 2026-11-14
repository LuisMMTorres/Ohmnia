"""Analytic model of single-phase uncontrolled rectifiers (DM-RET1).

Model: ideal transformer and source, diodes as a constant drop VF (the same model the circuit
uses in the simulator), resistive load, filters C, LC or π (CLC).

Capacitor-input filter: exact periodic solution of the model, the method of Hart, *Power
Electronics* (ch. 3, half-wave and full-wave rectifiers with capacitor filter), extended to the
constant diode drop:

    conduction  (θon ≤ θ ≤ θoff):  vo = Vm·|sin θ| − n·VF
                                   iD = ωC·Vm·cos θ + (Vm·sin θ − n·VF)/R
    turn-off:   iD(θoff) = 0       ⇒ ωRC·Vm·cos θoff + Vm·sin θoff − n·VF = 0
    blocking:   vo = vo(θoff)·exp(−(θ − θoff)/(ωRC))
    turn-on:    the decaying vo meets Vm·|sin θ| − n·VF again (θon, next half cycle)

Choke-input (LC) filter with continuous inductor current: vo,avg = 2Vm/π − n·VF; the design
uses the second harmonic V2 = 4Vm/(3π) (Hart, ch. 4, LC filter; continuous if L ≥ R/(3ω)), the
waveforms solve the linear LC stage with all harmonics of the rectified voltage. The π filter
adds the same LC stage after the capacitor C1.

All periodic waveforms are built on a grid over one source period and the averages, RMS values
and harmonics are integrated numerically from them (the model, not a simulation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq

Topology = Literal["meia_onda", "center_tap", "ponte"]
Filter = Literal["nenhum", "C", "LC", "pi"]

N_GRID = 28800  # points per source period (current pulses of a C filter are steep)

FloatArray = NDArray[np.float64]


def pulses(topology: Topology) -> int:
    """Output pulses per source period."""
    return 1 if topology == "meia_onda" else 2


def diodes_in_path(topology: Topology) -> int:
    return 2 if topology == "ponte" else 1


def diode_count(topology: Topology) -> int:
    return {"meia_onda": 1, "center_tap": 2, "ponte": 4}[topology]


@dataclass
class Waves:
    """One source period, θ = ωt ∈ [0, 2π)."""

    theta: FloatArray
    vs: FloatArray  # secondary (for center tap: each half) voltage
    vo: FloatArray  # output (load) voltage
    i_load: FloatArray
    i_diode: FloatArray  # current of one diode (D1)
    i_sec: FloatArray  # secondary winding current (center tap: one half)
    i_in: FloatArray  # primary current referred to the secondary (multiply by 1/N)
    i_cap: FloatArray | None = None
    i_ind: FloatArray | None = None
    v_c1: FloatArray | None = None  # π filter: voltage on the first capacitor
    theta_on: float | None = None
    theta_off: float | None = None
    vr_diode_max: float = 0.0


def _grid() -> FloatArray:
    return np.linspace(0, 2 * math.pi, N_GRID, endpoint=False)


def mean(x: FloatArray) -> float:
    return float(np.mean(x))


def rms(x: FloatArray) -> float:
    return float(np.sqrt(np.mean(x**2)))


def harmonic_amplitudes(x: FloatArray, n: int = 50) -> FloatArray:
    """Peak amplitude of harmonics 0..n of a waveform sampled over exactly one period."""
    spec = np.fft.rfft(x) / x.size
    amp = np.abs(spec[: n + 1])
    amp[1:] *= 2
    return np.asarray(amp)


def thd(x: FloatArray) -> float:
    h = harmonic_amplitudes(x)
    return float(np.sqrt(np.sum(h[2:] ** 2)) / h[1])


def _distribute(
    topology: Topology, theta: FloatArray, i_out: FloatArray
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Diode, secondary and (secondary-referred) primary currents from the output current.

    For center tap and bridge, the positive half cycle conducts through D1 (and D4), the negative
    through D2 (and D3).
    """
    pos = np.sin(theta) >= 0
    if topology == "meia_onda":
        i_d = i_out
        i_sec = i_out
        i_in = i_out - np.mean(i_out)  # the DC part does not reflect to the primary
        return i_d, i_sec, i_in
    i_d = np.where(pos, i_out, 0.0)
    i_other = np.where(pos, 0.0, i_out)
    if topology == "center_tap":
        # each half winding carries one diode current; the primary sees the difference
        return i_d, i_d, i_d - i_other
    i_sec = i_d - i_other
    return i_d, i_sec, i_sec


def unfiltered(topology: Topology, Vm: float, VF: float, R: float) -> Waves:
    theta = _grid()
    n_vf = diodes_in_path(topology) * VF
    src = np.sin(theta) * Vm
    rect = src if topology == "meia_onda" else np.abs(src)
    vo = np.maximum(rect - n_vf, 0.0)
    i_out = vo / R
    i_d, i_sec, i_in = _distribute(topology, theta, i_out)
    return Waves(
        theta=theta,
        vs=src,
        vo=vo,
        i_load=i_out,
        i_diode=i_d,
        i_sec=i_sec,
        i_in=i_in,
        vr_diode_max=_piv(topology, Vm, src, vo),
    )


def _piv(topology: Topology, Vm: float, src: FloatArray, vo: FloatArray) -> float:
    """Peak reverse voltage on one diode (D1, whose anode follows the + half winding)."""
    if topology == "ponte":
        return Vm  # the blocking pair sees the whole secondary voltage
    return float(np.max(vo - src))


def unfiltered_average(topology: Topology, Vm: float, VF: float) -> float:
    """Exact mean output voltage of the unfiltered rectifier with constant drop (R load).

    vo = Vm·sin θ − n·VF for θ1 ≤ θ ≤ π − θ1, θ1 = arcsin(n·VF/Vm):
    Vo = (p/2π)·[2Vm·cos θ1 − n·VF·(π − 2θ1)]
    """
    n_vf = diodes_in_path(topology) * VF
    if n_vf >= Vm:
        return 0.0
    t1 = math.asin(n_vf / Vm)
    return pulses(topology) / (2 * math.pi) * (2 * Vm * math.cos(t1) - n_vf * (math.pi - 2 * t1))


@dataclass
class CapSolution:
    theta_off: float
    theta_on: float  # in (0, π/2], measured in the half cycle of the next pulse
    v_off: float
    v_min: float


def solve_cap(
    topology: Topology, Vm: float, VF: float, R: float, C: float, f: float
) -> CapSolution:
    w = 2 * math.pi * f
    wrc = w * R * C
    n_vf = diodes_in_path(topology) * VF
    if n_vf >= Vm:
        raise ValueError("A tensão de pico não vence a queda nos diodos")

    def off(t: float) -> float:
        return wrc * Vm * math.cos(t) + Vm * math.sin(t) - n_vf

    t_off = brentq(off, math.pi / 2, math.pi - 1e-12)
    v_off = Vm * math.sin(t_off) - n_vf
    period = 2 * math.pi / pulses(topology)

    def on(t: float) -> float:
        decayed = v_off * math.exp(-(t + period - t_off) / wrc)
        return decayed - (Vm * math.sin(t) - n_vf)

    lo = math.asin(n_vf / Vm) + 1e-12
    # if on(lo) <= 0 the output decays to zero before the source rises again
    t_on = lo if on(lo) <= 0 else brentq(on, lo, math.pi / 2)
    v_min = max(Vm * math.sin(t_on) - n_vf, 0.0)
    return CapSolution(theta_off=t_off, theta_on=t_on, v_off=v_off, v_min=v_min)


def cap_filter(topology: Topology, Vm: float, VF: float, R: float, C: float, f: float) -> Waves:
    s = solve_cap(topology, Vm, VF, R, C, f)
    w = 2 * math.pi * f
    wrc = w * R * C
    n_vf = diodes_in_path(topology) * VF
    theta = _grid()
    period = 2 * math.pi / pulses(topology)
    local = np.mod(theta, period)  # angle inside the current output pulse
    src = Vm * np.sin(theta)
    conducting = (local >= s.theta_on) & (local <= s.theta_off)
    # blocking: after θoff of this pulse, or before θon (tail of the previous pulse)
    since_off = np.where(local > s.theta_off, local - s.theta_off, local + period - s.theta_off)
    vo = np.where(conducting, Vm * np.sin(local) - n_vf, s.v_off * np.exp(-since_off / wrc))
    i_out = np.where(conducting, w * C * Vm * np.cos(local) + (Vm * np.sin(local) - n_vf) / R, 0.0)
    i_out = np.maximum(i_out, 0.0)
    i_d, i_sec, i_in = _distribute(topology, theta, i_out)
    return Waves(
        theta=theta,
        vs=src,
        vo=vo,
        i_load=vo / R,
        i_diode=i_d,
        i_sec=i_sec,
        i_in=i_in,
        i_cap=i_out - vo / R,
        theta_on=s.theta_on,
        theta_off=s.theta_off,
        vr_diode_max=_piv(topology, Vm, src, vo),
    )


def lc_response(
    v_in: FloatArray, w: float, R: float, L: float, C: float
) -> tuple[FloatArray, FloatArray]:
    """Output voltage and inductor current of the LC stage (series L, then C ∥ R).

    Linear and periodic, so it is solved harmonic by harmonic on one period of v_in:
    Vo,h = V_in,h·Z_h/(jhωL + Z_h), Z_h = R ∥ 1/(jhωC); I_L,h = V_in,h/(jhωL + Z_h).
    Harmonics up to the grid's Nyquist limit are kept.
    """
    spec = np.fft.rfft(v_in)
    h = np.arange(spec.size)
    s_h = 1j * h * w
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(h == 0, R, R / (1 + s_h * R * C))
    z_total = s_h * L + z
    vo = np.fft.irfft(spec * z / z_total, n=v_in.size)
    i_l = np.fft.irfft(spec / z_total, n=v_in.size)
    return np.asarray(vo, dtype=np.float64), np.asarray(i_l, dtype=np.float64)


def lc_filter(
    topology: Topology, Vm: float, VF: float, R: float, L: float, C: float, f: float
) -> Waves:
    """Choke-input filter with continuous inductor current.

    While the inductor current does not vanish one diode (pair) always conducts, so the input of
    the filter is exactly vr = Vm·|sin θ| − n·VF and the linear LC stage is solved by harmonics
    (:func:`lc_response`). If the current reaches zero the result is not valid; the caller
    checks ``min(i_ind) > 0``.
    """
    if topology == "meia_onda":
        raise ValueError("Filtro LC só para retificador de onda completa nesta versão")
    w = 2 * math.pi * f
    n_vf = diodes_in_path(topology) * VF
    theta = _grid()
    src = Vm * np.sin(theta)
    vr = np.abs(src) - n_vf
    vo, i_ind = lc_response(vr, w, R, L, C)
    i_d, i_sec, i_in = _distribute(topology, theta, i_ind)
    return Waves(
        theta=theta,
        vs=src,
        vo=vo,
        i_load=vo / R,
        i_diode=i_d,
        i_sec=i_sec,
        i_in=i_in,
        i_cap=i_ind - vo / R,
        i_ind=i_ind,
        vr_diode_max=_piv(topology, Vm, src, vr),
    )


def pi_filter(
    topology: Topology,
    Vm: float,
    VF: float,
    R: float,
    L: float,
    C1: float,
    C2: float,
    f: float,
    tol: float = 1e-10,
    max_iter: int = 400,
) -> Waves:
    """π (C1-L-C2) filter, periodic steady state of the model.

    C1 is charged by the diodes and discharged by the inductor current, which in turn depends on
    v_C1 through the linear L-C2-R stage. Fixed point on one period:

    1. given i_L(θ), the diodes conduct while i_D = ωC1·Vm·cos θ + i_L > 0 (v_C1 = Vm|sin θ| − nVF);
       from θoff on, C1 discharges: v_C1 = v_C1(θoff) − ∫ i_L dθ/(ωC1), until it meets the
       rectified voltage again (θon);
    2. i_L and v_o follow from v_C1 by harmonics (:func:`lc_response`);
    3. repeat, with relaxation, until v_C1 stops changing.

    ``Waves.vo`` is the load voltage, ``i_cap`` the current in C1.
    """
    if topology == "meia_onda":
        raise ValueError("Filtro π só para retificador de onda completa nesta versão")
    w = 2 * math.pi * f
    n_vf = diodes_in_path(topology) * VF
    if n_vf >= Vm:
        raise ValueError("A tensão de pico não vence a queda nos diodos")
    theta = _grid()
    n_pulse = N_GRID // 2  # one output pulse = half a source period
    phi = theta[:n_pulse]
    dphi = float(theta[1] - theta[0])
    vr = Vm * np.sin(phi) - n_vf
    dvr = Vm * np.cos(phi)
    i_l_pulse = np.full(n_pulse, (2 * Vm / math.pi - n_vf) / R * 0.9)
    v_c1 = np.tile(vr, 2)
    t_on = t_off = 0.0
    for _ in range(max_iter):
        i_d = w * C1 * dvr + i_l_pulse
        after_peak = np.nonzero((phi >= math.pi / 2) & (i_d <= 0))[0]
        k_off = int(after_peak[0]) if after_peak.size else n_pulse - 1
        # blocking from k_off over the rest of this pulse and into the next one
        i_two = np.concatenate([i_l_pulse, i_l_pulse])
        vr_two = np.concatenate([vr, vr])
        idx = np.arange(k_off, 2 * n_pulse)
        v_block = vr[k_off] - np.cumsum(i_two[idx]) * dphi / (w * C1)
        v_block = np.concatenate([[vr[k_off]], v_block[:-1]])
        meet = np.nonzero((idx >= n_pulse) & (v_block <= vr_two[idx]))[0]
        k_on = int(idx[meet[0]] - n_pulse) if meet.size else k_off
        new = vr.copy()
        block_this = phi >= phi[k_off]
        new[block_this] = v_block[: int(np.sum(block_this))]
        tail = v_block[n_pulse - k_off : n_pulse - k_off + k_on]
        new[:k_on] = tail
        v_full = np.tile(new, 2)
        vo, i_l = lc_response(v_full, w, R, L, C2)
        change = float(np.max(np.abs(v_full - v_c1)))
        v_c1 = v_full
        i_l_pulse = 0.5 * i_l_pulse + 0.5 * i_l[:n_pulse]
        t_on, t_off = float(phi[k_on]), float(phi[k_off])
        if change <= tol * Vm:
            break
    else:
        raise ValueError("O modelo do filtro π não convergiu")
    local = np.mod(theta, math.pi)
    conducting = (local >= t_on) & (local <= t_off)
    i_out = np.where(conducting, np.maximum(w * C1 * Vm * np.cos(local) + i_l, 0.0), 0.0)
    i_d_full, i_sec, i_in = _distribute(topology, theta, i_out)
    src = Vm * np.sin(theta)
    return Waves(
        theta=theta,
        vs=src,
        vo=vo,
        i_load=vo / R,
        i_diode=i_d_full,
        i_sec=i_sec,
        i_in=i_in,
        i_cap=i_out - i_l,
        i_ind=i_l,
        v_c1=v_c1,
        theta_on=t_on,
        theta_off=t_off,
        vr_diode_max=_piv(topology, Vm, src, v_c1),
    )


def critical_inductance(R: float, f: float) -> float:
    """L ≥ R/(3ω) keeps the inductor current continuous (full wave, C ≫)."""
    return R / (3 * 2 * math.pi * f)
