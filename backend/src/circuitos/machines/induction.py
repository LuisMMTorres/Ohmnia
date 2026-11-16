"""Three-phase squirrel-cage induction motor: steady state by the per-phase equivalent circuit.

The SPICE model (:mod:`circuitos.schematic.drive_symbols`) solves the dynamic model in the
stationary αβ frame; in steady state with a balanced sinusoidal supply it must reduce to the
equivalent circuit below (rule 4, ``tests/analytic_vs_sim/test_as_drives.py``).

Equivalent circuit per phase (star equivalent), referred to the stator, iron losses neglected:

    V1 -- R1 -- jX1 --+-- jX2 -- R2/s --
                      |
                     jXm

Air-gap power P_ag = 3 I2² R2/s; electromagnetic torque T = P_ag / ω_s with
ω_s = 2π f / p (mechanical synchronous speed, p = pole pairs).
Chapman, *Electric Machinery Fundamentals*, 5th ed., ch. 6 (equivalent circuit, eq. of the
induced torque); Krause, Wasynczuk and Sudhoff, *Analysis of Electric Machinery and Drive
Systems*, 2nd ed., ch. 4 (machine variables and the stationary reference frame).

Reactances are given at the rated frequency ``fnom`` and scale with the supply frequency, so
the same parameters serve the V/f drive.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

from scipy.optimize import brentq


@dataclass(frozen=True)
class InductionParams:
    rs: float  # Ω, stator resistance per phase (star)
    rr: float  # Ω, rotor resistance referred to the stator
    xls: float  # Ω, stator leakage reactance at fnom
    xlr: float  # Ω, rotor leakage reactance at fnom
    xm: float  # Ω, magnetising reactance at fnom
    poles: int  # number of poles (4 = 2 pole pairs)
    fnom: float  # Hz
    j: float = 0.0  # kg·m², rotor + load
    b: float = 0.0  # N·m·s/rad, viscous friction

    @property
    def pairs(self) -> int:
        return self.poles // 2

    def inductances(self) -> tuple[float, float, float]:
        """Ls, Lr, Lm in H (stator, rotor and magnetising), from the reactances at fnom."""
        w = 2 * math.pi * self.fnom
        lm = self.xm / w
        return (self.xls / w + lm, self.xlr / w + lm, lm)


@dataclass(frozen=True)
class OperatingPoint:
    slip: float
    speed_rpm: float
    torque: float  # N·m, electromagnetic
    i1: float  # A rms, stator line current
    pf: float
    p_in: float  # W
    p_mech: float  # W, at the shaft before friction (T·ω)


def operating_point(m: InductionParams, v_line: float, f: float, slip: float) -> OperatingPoint:
    """Steady state at the given line voltage (rms), frequency and slip."""
    if f <= 0:
        raise ValueError("frequência deve ser positiva")
    k = f / m.fnom
    v1 = v_line / math.sqrt(3)
    z1 = complex(m.rs, m.xls * k)
    zm = complex(0, m.xm * k)
    z2 = complex(m.rr / slip, m.xlr * k) if slip != 0 else complex(math.inf, 0)
    z_par = zm if slip == 0 else zm * z2 / (zm + z2)
    i1 = v1 / (z1 + z_par)
    e1 = i1 * z_par
    i2 = 0j if slip == 0 else e1 / z2
    ws = 2 * math.pi * f / m.pairs
    p_ag = 3 * abs(i2) ** 2 * m.rr / slip if slip != 0 else 0.0
    torque = p_ag / ws
    s_in = 3 * v1 * i1.conjugate()
    speed = (1 - slip) * ws
    return OperatingPoint(
        slip=slip,
        speed_rpm=speed * 60 / (2 * math.pi),
        torque=torque,
        i1=abs(i1),
        pf=math.cos(cmath.phase(s_in)),
        p_in=s_in.real,
        p_mech=torque * speed,
    )


def steady_state(
    m: InductionParams,
    v_line: float,
    f: float,
    load: float,
    quadratic: bool = False,
    w_load: float | None = None,
) -> OperatingPoint:
    """Operating point where the motor torque balances load + friction (stable branch).

    ``load`` is the load torque in N·m; with ``quadratic`` it is the torque at the speed
    ``w_load`` (rad/s, default the synchronous speed at fnom), as fans and pumps:
    T_L = load (ω/w_load)².
    """
    ws = 2 * math.pi * f / m.pairs
    wl = w_load or 2 * math.pi * m.fnom / m.pairs

    def balance(s: float) -> float:
        w = (1 - s) * ws
        tl = load * (w / wl) ** 2 if quadratic else load
        return operating_point(m, v_line, f, s).torque - tl - m.b * w

    s_max = breakdown_slip(m, f)
    return operating_point(m, v_line, f, brentq(balance, 1e-9, s_max, xtol=1e-12))


def breakdown_slip(m: InductionParams, f: float) -> float:
    """Slip of maximum torque: R2 / sqrt(R_th² + (X_th + X2)²) (Thévenin of the stator side)."""
    k = f / m.fnom
    z1 = complex(m.rs, m.xls * k)
    zm = complex(0, m.xm * k)
    zth = z1 * zm / (z1 + zm)
    return m.rr / math.hypot(zth.real, zth.imag + m.xlr * k)
