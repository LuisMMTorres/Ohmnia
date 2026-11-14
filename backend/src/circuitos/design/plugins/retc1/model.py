"""Analytic model of single-phase controlled rectifiers (DM-RETC1).

Circuits: half-wave (one SCR, optional freewheeling diode), fully controlled bridge (four SCRs)
and symmetric semicontrolled bridge (two SCRs on the top, two diodes on the bottom: the load
freewheels through the SCR and the diode of the same leg). Load R, L and a counter-EMF E (RLE).
Devices are constant drops (VT of the SCRs, VD of the diodes); the source is ideal (no
commutation inductance in single phase; DM-RET3 handles the overlap angle μ).

Each conduction interval obeys the linear equation (θ = ωt)

    ωL·di/dθ + R·i = s·Vm·sin θ + Vc,      s ∈ {+1, 0},  Vc = −(drops) − E

whose solution, as in Hart, *Power Electronics* (ch. 3: half-wave with RL and RL-source loads,
freewheeling diode; ch. 4: controlled full-wave rectifiers), is

    i(θ) = ip(θ) + [i(θ0) − ip(θ0)]·exp(−(θ − θ0)/(ωτ)),   τ = L/R
    ip(θ) = s·(Vm/Z)·sin(θ − φ) + Vc/R,  Z = √(R² + (ωL)²),  φ = atan(ωL/R)

The extinction angle β (i(β) = 0) comes from a root search on this expression and the periodic
steady state in continuous conduction from the affine map i(α) → i(α + period), so the model
is exact for its assumptions. Firing is a single short pulse at α (bridges: α and α + π): a
device that is not forward biased at α fires when it becomes so within the 5° gate pulse,
otherwise it does not fire (single pulse).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq

Topology = Literal["meia_onda", "ponte", "semicontrolada"]
FloatArray = NDArray[np.float64]
N_GRID = 14400

DEVICES: dict[str, tuple[str, ...]] = {
    "meia_onda": ("T1", "D1"),
    "ponte": ("T1", "T2", "T3", "T4"),
    "semicontrolada": ("T1", "T2", "D1", "D2"),
}
# who carries the current in the second output pulse of a bridge (source reversed)
SECOND_PULSE = {
    "ponte": {"T1": "T3", "T2": "T4"},
    "semicontrolada": {"T1": "T2", "D2": "D1", "D1": "D2"},
}


@dataclass(frozen=True)
class Load:
    R: float
    L: float = 0.0
    E: float = 0.0

    def __post_init__(self) -> None:
        if not self.R > 0 or self.L < 0 or self.E < 0:
            raise ValueError("R deve ser positivo; L e E não podem ser negativos")


@dataclass(frozen=True)
class Segment:
    """One conduction interval with a fixed current path."""

    start: float
    end: float
    s: int  # source in the load loop (+1) or freewheeling (0)
    vc: float  # constant term of the loop: −drops − E
    i0: float
    devices: tuple[str, ...]  # devices carrying the load current


def _ip(theta: FloatArray, s: int, vc: float, Vm: float, ld: Load, w: float) -> FloatArray:
    xl = w * ld.L
    z = math.hypot(ld.R, xl)
    phi = math.atan2(xl, ld.R)
    return np.asarray(s * Vm / z * np.sin(theta - phi) + vc / ld.R, dtype=np.float64)


def current(seg: Segment, theta: FloatArray, Vm: float, ld: Load, w: float) -> FloatArray:
    ip = _ip(theta, seg.s, seg.vc, Vm, ld, w)
    if ld.L == 0:
        return ip
    q = w * ld.L / ld.R
    ip0 = float(_ip(np.array([seg.start]), seg.s, seg.vc, Vm, ld, w)[0])
    return np.asarray(ip + (seg.i0 - ip0) * np.exp(-(theta - seg.start) / q), dtype=np.float64)


def current_at(seg: Segment, theta: float, Vm: float, ld: Load, w: float) -> float:
    return float(current(seg, np.array([theta]), Vm, ld, w)[0])


def extinction(seg: Segment, Vm: float, ld: Load, w: float) -> float | None:
    """First θ in [start, end] where the current reaches zero, or None if it stays positive."""
    th = np.linspace(seg.start, seg.end, 2001)
    i = current(seg, th, Vm, ld, w)
    if i[0] < 0 or (ld.L == 0 and i[0] <= 0):
        return seg.start
    # with L the current starts at i0 (possibly 0) and rises while the source drives it
    neg = np.nonzero(i[1:] <= 0)[0]
    if neg.size == 0:
        return None
    k = int(neg[0]) + 1
    return float(brentq(lambda t: current_at(seg, t, Vm, ld, w), th[k - 1], th[k], xtol=1e-13))


def commutation_angle(Vm: float, VT: float, VD: float) -> float:
    """Half wave with freewheeling diode: the diode takes over when vs − VT = −VD."""
    x = (VT - VD) / Vm
    return math.pi - math.asin(max(-1.0, min(1.0, x)))


def _pulse_segments(
    topology: Topology, Vm: float, alpha: float, VT: float, VD: float, E: float, freewheel: bool
) -> list[Segment]:
    """Conduction segments of one output period, from α, assuming the current never vanishes."""
    if topology == "meia_onda":
        if freewheel:
            tc = max(commutation_angle(Vm, VT, VD), alpha)
            return [
                Segment(alpha, tc, 1, -VT - E, 0.0, ("T1",)),
                Segment(tc, alpha + 2 * math.pi, 0, -VD - E, 0.0, ("D1",)),
            ]
        return [Segment(alpha, alpha + 2 * math.pi, 1, -VT - E, 0.0, ("T1",))]
    if topology == "ponte":
        return [Segment(alpha, alpha + math.pi, 1, -2 * VT - E, 0.0, ("T1", "T2"))]
    # semicontrolled: T1 + D2 from α to π, then freewheeling through T1 + D1 until α + π
    return [
        Segment(alpha, math.pi, 1, -VT - VD - E, 0.0, ("T1", "D2")),
        Segment(math.pi, alpha + math.pi, 0, -VT - VD - E, 0.0, ("T1", "D1")),
    ]


def _chain(segs: list[Segment], Vm: float, ld: Load, w: float, i0: float) -> list[Segment]:
    out: list[Segment] = []
    i = i0
    for s in segs:
        seg = Segment(s.start, s.end, s.s, s.vc, i, s.devices)
        out.append(seg)
        i = current_at(seg, seg.end, Vm, ld, w)
    return out


@dataclass
class Solution:
    topology: Topology
    alpha: float
    Vm: float
    load: Load
    w: float
    VT: float
    VD: float
    segments: list[Segment]  # one output period (2π half wave, π bridges), starting at α
    continuous: bool
    fired: bool
    beta: float | None  # extinction angle when discontinuous (rad, absolute)
    notes: list[str] = field(default_factory=list)


PULSE_WIDTH = math.radians(5.0)  # gate pulse (the simulated circuit uses the same width)


def firing_angle(Vm: float, alpha: float, threshold: float) -> float | None:
    """Instant the device turns on from zero current: the first θ in [α, α + pulse] where
    Vm·sin θ exceeds the threshold (drops + E); None if it never does during the pulse."""
    if Vm * math.sin(alpha) > threshold:
        return alpha
    if threshold >= Vm:
        return None
    t_min = math.asin(max(threshold, 0.0) / Vm)
    if alpha <= t_min <= alpha + PULSE_WIDTH:
        return t_min + 1e-9
    return None


def forward_drop(topology: Topology, VT: float, VD: float) -> float:
    """Drops in the source path while the source feeds the load."""
    return {"meia_onda": VT, "ponte": 2 * VT, "semicontrolada": VT + VD}[topology]


def solve(
    topology: Topology,
    Vm: float,
    alpha: float,
    ld: Load,
    f: float,
    VT: float = 0.0,
    VD: float = 0.0,
    freewheel: bool = False,
) -> Solution:
    if not (0 <= alpha < math.pi):
        raise ValueError("α deve estar entre 0° e 180°")
    if Vm <= 0 or f <= 0:
        raise ValueError("Vm e f devem ser positivos")
    if topology != "meia_onda":
        freewheel = False  # the semicontrolled bridge freewheels by itself
    w = 2 * math.pi * f
    base = _pulse_segments(topology, Vm, alpha, VT, VD, ld.E, freewheel)
    args = (topology, alpha, Vm, ld, w, VT, VD)
    if ld.L > 0:
        # continuous candidate: i(α + period) = a·i0 + b  ⇒  i0 = b / (1 − a)
        b = current_at(_chain(base, Vm, ld, w, 0.0)[-1], base[-1].end, Vm, ld, w)
        a = current_at(_chain(base, Vm, ld, w, 1.0)[-1], base[-1].end, Vm, ld, w) - b
        i0 = b / (1 - a) if a < 1 else -1.0
        if i0 > 0:
            segs = _chain(base, Vm, ld, w, i0)
            if all(extinction(s, Vm, ld, w) is None for s in segs):
                return Solution(*args, segs, continuous=True, fired=True, beta=None)
    fire = firing_angle(Vm, alpha, forward_drop(topology, VT, VD) + ld.E)
    if fire is None:
        return Solution(
            *args,
            [],
            continuous=False,
            fired=False,
            beta=None,
            notes=[
                "O tiristor não dispara: durante o pulso de porta a fonte não supera E e as quedas."
            ],
        )
    first = base[0]
    base[0] = Segment(fire, first.end, first.s, first.vc, 0.0, first.devices)
    out: list[Segment] = []
    beta: float | None = None
    for s in _chain(base, Vm, ld, w, 0.0):
        z = extinction(s, Vm, ld, w)
        if z is None:
            out.append(s)
            continue
        if z > s.start:
            out.append(Segment(s.start, z, s.s, s.vc, s.i0, s.devices))
        beta = z
        break
    return Solution(*args, out, continuous=False, fired=True, beta=beta)


@dataclass
class Waves:
    theta: FloatArray  # one source period [0, 2π)
    vs: FloatArray
    vo: FloatArray  # load voltage (E while the current is zero)
    io: FloatArray
    i_src: FloatArray  # secondary current
    devices: dict[str, FloatArray]  # current of each device
    vt1: FloatArray  # anode-to-cathode voltage of T1 (blocking stress)


def waves(sol: Solution) -> Waves:
    """Sample the solution over one source period."""
    theta = np.linspace(0, 2 * math.pi, N_GRID, endpoint=False)
    vm, ld, w = sol.Vm, sol.load, sol.w
    vs = vm * np.sin(theta)
    io = np.zeros_like(theta)
    src_sign = np.zeros_like(theta)  # +1/−1 source in the loop, 0 freewheeling or off
    conducting = np.zeros(theta.shape, dtype=bool)
    vo = np.full_like(theta, ld.E)
    dev = {n: np.zeros_like(theta) for n in DEVICES[sol.topology]}
    pulses = 1 if sol.topology == "meia_onda" else 2
    for k in range(pulses):
        shift = k * math.pi
        rename = SECOND_PULSE.get(sol.topology, {}) if k == 1 else {}
        for seg in sol.segments:
            a, b = seg.start + shift, seg.end + shift
            for wrap in (-2 * math.pi, 0.0, 2 * math.pi):
                sel = (theta >= a + wrap) & (theta < b + wrap)
                if not np.any(sel):
                    continue
                local = theta[sel] - wrap - shift
                i = np.maximum(current(seg, local, vm, ld, w), 0.0)
                io[sel] = i
                conducting[sel] = True
                src_sign[sel] = seg.s * (1 if k == 0 else -1)
                vo[sel] = seg.s * vm * np.sin(local) + seg.vc + ld.E
                for d in seg.devices:
                    dev[rename.get(d, d)][sel] = i
    i_src = src_sign * io
    if sol.topology == "meia_onda":
        on = conducting & (src_sign != 0)
        vt1 = np.where(on, sol.VT, vs - vo)
    else:
        # T1 conducts in the first pulse; otherwise it sees the secondary voltage (opposite pair
        # on) or, with the bridge empty, at most that
        vt1 = np.where(dev["T1"] > 0, sol.VT, vs)
    return Waves(theta=theta, vs=vs, vo=vo, io=io, i_src=i_src, devices=dev, vt1=vt1)


def mean(x: FloatArray) -> float:
    return float(np.mean(x))


def rms(x: FloatArray) -> float:
    return float(np.sqrt(np.mean(x**2)))


def harmonic_amplitudes(x: FloatArray, n: int = 50) -> FloatArray:
    spec = np.fft.rfft(x) / x.size
    amp = np.abs(spec[: n + 1])
    amp[1:] *= 2
    return np.asarray(amp)


def thd(x: FloatArray) -> float:
    h = harmonic_amplitudes(x - np.mean(x))
    return float(np.sqrt(np.sum(h[2:] ** 2)) / h[1])


def power_factor(vs: FloatArray, i: FloatArray) -> float:
    """P/(Vrms·Irms) with the mean of the current removed (a transformer passes no DC)."""
    ac = i - np.mean(i)
    s = rms(vs) * rms(ac)
    return float(np.mean(vs * ac)) / s if s > 0 else 0.0


def displacement_factor(vs: FloatArray, i: FloatArray) -> float:
    """cos φ1 between the fundamentals of the source voltage and current."""
    v1 = np.fft.rfft(vs)[1]
    i1 = np.fft.rfft(i)[1]
    return float(math.cos(np.angle(i1) - np.angle(v1)))


# ------------------------------------------------------------- closed forms, ideal devices
def ideal_average_continuous(topology: Topology, Vm: float, alpha: float) -> float:
    """Hart ch. 4: 2Vm/π·cos α (full bridge, continuous); Vm/π·(1 + cos α) (semicontrolled)."""
    if topology == "ponte":
        return 2 * Vm / math.pi * math.cos(alpha)
    if topology == "semicontrolada":
        return Vm / math.pi * (1 + math.cos(alpha))
    raise ValueError("meia onda não tem condução contínua sem diodo de roda livre")


def ideal_average_discontinuous(
    topology: Topology, Vm: float, alpha: float, beta: float, E: float = 0.0
) -> float:
    """Hart ch. 3/4: Vo = (p·Vm/2π)(cos α − cos β) + E·(fraction of the period with i = 0)."""
    p = 1 if topology == "meia_onda" else 2
    period = 2 * math.pi / p
    return (
        p * Vm / (2 * math.pi) * (math.cos(alpha) - math.cos(beta))
        + E * (period - (beta - alpha)) / period
    )
