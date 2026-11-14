"""Bipolar transistor model for the device bench (BD-TBJ).

Gummel-Poon transport model reduced to the parameters taught in the course (IS, BF, BR, NF = NR
= 1, VAF), which is exactly what SPICE evaluates when the other model parameters keep their
defaults (IKF = IKR = ∞, VAR = ∞, ISE = ISC = 0, no resistances). Verified against ngspice in
tests/analytic_vs_sim.

    Ibe = IS/BF·(exp(VBE/Vt) − 1)        Ibc = IS/BR·(exp(VBC/Vt) − 1)
    Ict = IS·(exp(VBE/Vt) − exp(VBC/Vt))·(1 − VBC/VAF)
    IC = Ict − Ibc                         IB = Ibe + Ibc

References: Sedra & Smith, *Microelectronic Circuits* (BJT chapter: Ebers-Moll and Early effect);
ngspice manual, BJT model. Chapter and equation numbers still to be checked against the
printed book (BibRef.verified = False).

All quantities refer to an NPN device; the bench shows PNP curves in magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pint
from numpy.typing import NDArray

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, require
from circuitos.devices.diode import thermal_voltage

BJT_REF = BibRef(book="Sedra & Smith, Microelectronic Circuits", chapter="Bipolar transistors")


@dataclass(frozen=True)
class BjtModel:
    IS: pint.Quantity
    BF: float
    BR: float
    VAF: pint.Quantity  # forward Early voltage

    def __post_init__(self) -> None:
        require(self.IS, "A", "IS")
        require(self.VAF, "V", "VAF")
        if not (self.IS.magnitude > 0 and self.BF > 0 and self.BR > 0 and self.VAF.magnitude > 0):
            raise ValueError("IS, BF, BR e VAF devem ser positivos")

    def spice(self, name: str = "QMOD") -> str:
        return (
            f".model {name} NPN(IS={self.IS.m_as('A'):.6g} BF={self.BF:.6g} "
            f"BR={self.BR:.6g} VAF={self.VAF.m_as('V'):.6g})"
        )


def _currents(
    m: BjtModel, vbe: NDArray[np.float64], vce: NDArray[np.float64], vt: float
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """IC, IB and dIB/dVBE (at fixed VCE)."""
    is_ = m.IS.m_as("A")
    vaf = m.VAF.m_as("V")
    vbc = vbe - vce
    ebe = np.exp(np.minimum(vbe / vt, 200))
    ebc = np.exp(np.minimum(vbc / vt, 200))
    q = 1 - vbc / vaf
    ict = is_ * (ebe - ebc) * q
    ibe = is_ / m.BF * (ebe - 1)
    ibc = is_ / m.BR * (ebc - 1)
    dib = is_ / m.BF * ebe / vt + is_ / m.BR * ebc / vt
    return ict - ibc, ibe + ibc, dib


def output_characteristic(
    m: BjtModel, ib: pint.Quantity, vce: pint.Quantity, T: pint.Quantity
) -> tuple[pint.Quantity, pint.Quantity]:
    """IC(VCE) at constant base current IB. Returns (IC, VBE)."""
    require(ib, "A", "IB")
    require(vce, "V", "VCE")
    vt = thermal_voltage(T).m_as("V")
    ib_a = ib.m_as("A")
    v = np.atleast_1d(np.asarray(vce.m_as("V"), dtype=float))
    # start from the forward-active estimate VBE = Vt·ln(BF·IB/IS + 1)
    vbe = np.full_like(v, vt * np.log1p(m.BF * ib_a / m.IS.m_as("A")))
    for _ in range(200):
        _, ib_now, dib = _currents(m, vbe, v, vt)
        step = (ib_now - ib_a) / dib
        step = np.clip(step, -0.1, 0.1)
        vbe = vbe - step
        if np.all(np.abs(step) < 1e-12):
            break
    ic, _, _ = _currents(m, vbe, v, vt)
    if np.ndim(vce.magnitude) == 0:
        return Q_(float(ic[0]), "A"), Q_(float(vbe[0]), "V")
    return Q_(ic, "A"), Q_(vbe, "V")


def forward_gain(m: BjtModel, ic: pint.Quantity, ib: pint.Quantity) -> Calculated[pint.Quantity]:
    beta = Q_(ic.m_as("A") / ib.m_as("A"), "dimensionless")
    return record(
        "beta",
        "Ganho de corrente no ponto de operação",
        r"\beta = \frac{I_C}{I_B}",
        output=beta,
        inputs={"I_C": ic, "I_B": ib},
        assumptions=["região ativa direta"],
        reference=BJT_REF,
    )


def output_resistance(
    m: BjtModel, ic: pint.Quantity, vce: pint.Quantity
) -> Calculated[pint.Quantity]:
    ro = Q_((m.VAF.m_as("V") + vce.m_as("V")) / ic.m_as("A"), "ohm").to("kohm")
    return record(
        "ro",
        "Resistência de saída (efeito Early)",
        r"r_o \approx \frac{V_A + V_{CE}}{I_C}",
        output=ro,
        inputs={"V_A": m.VAF, "V_{CE}": vce, "I_C": ic},
        assumptions=["região ativa direta", "V_A = VAF do modelo"],
        reference=BJT_REF,
    )
