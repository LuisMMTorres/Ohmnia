"""DC operating point of single-transistor bias networks, solved with the device equations.

The base-emitter junction follows the exponential model of :class:`devmodels.Bjt` (the same
one SPICE evaluates), so the Q-point is the exact solution of the network, not the VBE = 0,7 V
approximation; Boylestad & Nashelsky, 11th ed., ch. 4 (DC biasing — BJTs) give the network
equations, solved here for the exponential junction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq

from .devmodels import Bjt, Mos


@dataclass(frozen=True)
class QPoint:
    IB: float
    IC: float
    IE: float
    VBE: float
    VB: float  # node voltages to ground
    VE: float
    VC: float

    @property
    def VCE(self) -> float:
        return self.VC - self.VE


def bjt_q(
    m: Bjt,
    vcc: float,
    vth: float,
    rth: float,
    rc: float,
    re: float,
    collector_feedback: bool = False,
) -> QPoint:
    """Q-point of an NPN stage: Thevenin base drive (vth, rth), RC to vcc, RE to ground.

    With ``collector_feedback`` the base resistor rth goes from the collector (vth ignored).
    Forward-active operation is assumed; the caller checks VCE.
    """

    def currents(vbe: float) -> tuple[float, float, float]:
        ic = m.ic(vbe)
        ib = ic / m.BF
        return ib, ic, ic + ib

    def residual(vbe: float) -> float:
        ib, ic, ie = currents(vbe)
        if collector_feedback:
            vc = vcc - (ic + ib) * rc
            return vc - ib * rth - vbe - ie * re
        return vth - ib * rth - vbe - ie * re

    top = vth if not collector_feedback else vcc
    vbe = brentq(residual, 0.0, min(max(top, 0.1), 1.5), xtol=1e-15, rtol=1e-14)
    ib, ic, ie = currents(vbe)
    ve = ie * re
    vc = vcc - ((ic + ib) * rc if collector_feedback else ic * rc)
    return QPoint(IB=ib, IC=ic, IE=ie, VBE=vbe, VB=ve + vbe, VE=ve, VC=vc)


@dataclass(frozen=True)
class MosQ:
    ID: float
    VGS: float
    VG: float
    VS: float
    VD: float

    @property
    def VDS(self) -> float:
        return self.VD - self.VS


def mos_q(m: Mos, vdd: float, vg: float, rd: float, rs: float) -> MosQ:
    """Saturation Q-point of an N-MOSFET with gate at vg, RD to vdd and RS to ground."""
    if vg <= m.VT:
        return MosQ(0.0, vg, vg, 0.0, vdd)

    def residual(vgs: float) -> float:
        return vg - vgs - m.id_sat(vgs) * rs

    vgs = brentq(residual, m.VT, vg, xtol=1e-15, rtol=1e-14) if rs > 0 else vg
    i = m.id_sat(vgs)
    return MosQ(ID=i, VGS=vgs, VG=vg, VS=i * rs, VD=vdd - i * rd)


def thevenin(vcc: float, r1: float, r2: float) -> tuple[float, float]:
    """(VTh, RTh) of the divider R1 (top) – R2 (bottom)."""
    return vcc * r2 / (r1 + r2), r1 * r2 / (r1 + r2)


def parallel(*rs: float) -> float:
    g = sum(1 / r for r in rs if math.isfinite(r) and r > 0)
    return 1 / g if g > 0 else math.inf
