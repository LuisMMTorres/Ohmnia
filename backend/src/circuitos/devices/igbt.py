"""IGBT model for the device bench (BD-IGBT).

Didactic piecewise model: a MOSFET in saturation limits the collector current by the gate
voltage, and the output stage conducts like a junction knee V0 plus an on-state resistance:

    VGE ≤ VT:  IC = 0
    VGE > VT:  IC = min( max(VCE − V0, 0) / r_on ,  K/2·(VGE − VT)² )

Fit to the datasheet: VT from VGE(th), r_on from VCE(sat) at the test current with the knee V0
given by the user. Losses of a hard-switched chopper at (V_CC, I_C, f_s, D):
P_cond = D·(V0·I_C + r_on·I_C²), P_sw = (E_on + E_off)·(V/V_test)·(I/I_test)·f_s, the switching
energies scaled linearly from the datasheet test point.

References: Mohan, Undeland & Robbins, *Power Electronics*, 3rd ed., ch. 25 (insulated gate
bipolar transistors); Hart, *Power Electronics*, 1st ed., ch. 10 (switching losses).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pint

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, require

IGBT_REF = BibRef(
    book="Mohan, Undeland & Robbins, Power Electronics",
    edition="3rd",
    chapter="25 (insulated gate bipolar transistors)",
)
LOSS_REF = BibRef(book="Hart, Power Electronics", edition="1st", chapter="10 (switching losses)")


@dataclass(frozen=True)
class IgbtModel:
    VT: pint.Quantity
    V0: pint.Quantity
    R_on: pint.Quantity
    K: pint.Quantity  # A/V²

    def __post_init__(self) -> None:
        require(self.VT, "V", "VT")
        require(self.V0, "V", "V0")
        require(self.R_on, "ohm", "R_on")
        require(self.K, "A/V**2", "K")
        if not self.R_on.magnitude > 0 or not self.K.magnitude > 0 or self.V0.magnitude < 0:
            raise ValueError("R_on e K devem ser positivos e V0 não negativo")


def collector_current(m: IgbtModel, vge: pint.Quantity, vce: pint.Quantity) -> pint.Quantity:
    require(vge, "V", "VGE")
    require(vce, "V", "VCE")
    vov = np.asarray(vge.m_as("V") - m.VT.m_as("V"), dtype=float)
    v = np.asarray(vce.m_as("V"), dtype=float)
    vov, v = np.broadcast_arrays(vov, v)
    lin = np.maximum(v - m.V0.m_as("V"), 0.0) / m.R_on.m_as("ohm")
    sat = m.K.m_as("A/V**2") / 2 * np.maximum(vov, 0.0) ** 2
    i = np.where(vov <= 0, 0.0, np.minimum(lin, sat))
    return Q_(i if i.ndim else float(i), "A")


def fit_r_on(
    vce_sat: pint.Quantity, ic: pint.Quantity, v0: pint.Quantity
) -> Calculated[pint.Quantity]:
    require(vce_sat, "V", "VCE(sat)")
    require(ic, "A", "IC")
    require(v0, "V", "V0")
    r: pint.Quantity = (vce_sat - v0) / ic
    if r.magnitude <= 0:
        raise ValueError("V0 deve ser menor que VCE(sat)")
    return record(
        "R_on_fit",
        "Resistência em condução a partir de VCE(sat)",
        r"r_{on} = \frac{V_{CE(sat)} - V_0}{I_C}",
        output=r.to("ohm"),
        inputs={"V_{CE(sat)}": vce_sat, "I_C": ic, "V_0": v0},
        assumptions=["joelho V0 informado pelo usuário", "característica linear acima do joelho"],
        reference=IGBT_REF,
    )


def chopper_losses(
    m: IgbtModel,
    vcc: pint.Quantity,
    ic: pint.Quantity,
    fs: pint.Quantity,
    duty: float,
    e_on: pint.Quantity,
    e_off: pint.Quantity,
    v_test: pint.Quantity,
    i_test: pint.Quantity,
) -> tuple[Calculated[pint.Quantity], Calculated[pint.Quantity]]:
    """Conduction and switching losses of the IGBT in a hard-switched chopper."""
    p_cond: pint.Quantity = duty * (m.V0 * ic + m.R_on * ic**2)
    k: pint.Quantity = (vcc / v_test) * (ic / i_test)
    p_sw: pint.Quantity = (e_on + e_off) * k * fs
    cond = record(
        "P_cond",
        "Perda de condução",
        r"P_{cond} = D\,(V_0 I_C + r_{on} I_C^2)",
        output=p_cond.to("W"),
        inputs={"D": Q_(duty, ""), "V_0": m.V0, "r_{on}": m.R_on, "I_C": ic},
        reference=LOSS_REF,
    )
    sw = record(
        "P_sw",
        "Perda de comutação (energias do datasheet escaladas)",
        r"P_{sw} = (E_{on} + E_{off})\frac{V_{CC}}{V_{teste}}\frac{I_C}{I_{teste}} f_s",
        output=p_sw.to("W"),
        inputs={"E_on": e_on, "E_off": e_off, "V_CC": vcc, "V_teste": v_test, "I_teste": i_test},
        assumptions=["energia proporcional à tensão e à corrente comutadas", "mesmo R_g do ensaio"],
        reference=LOSS_REF,
    )
    return cond, sw
