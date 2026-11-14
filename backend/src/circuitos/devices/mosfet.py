"""MOSFET model for the device bench (BD-FET).

Square-law (Shichman-Hodges) model, the same as SPICE MOS level 1 with W = L, no body effect and
no series resistances. Verified against ngspice in tests/analytic_vs_sim.

    cut-off   VGS ≤ VT:              ID = 0
    triode    VDS < VGS − VT:        ID = KP·[(VGS − VT)·VDS − VDS²/2]·(1 + λ·VDS)
    saturação VDS ≥ VGS − VT:        ID = KP/2·(VGS − VT)²·(1 + λ·VDS)

Fit to a power-MOSFET datasheet (didactic): VT from VGS(th), KP from RDS(on) in deep triode,
RDS(on) ≈ 1/[KP·(VGS − VT)]. A real power MOSFET deviates strongly from the square law at high
current; the bench says so.

References: Sedra & Smith, *Microelectronic Circuits* (MOSFET chapter: square-law model and
channel-length modulation); ngspice manual, MOS level 1. Chapter and equation numbers still to be
checked against the printed book (BibRef.verified = False).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pint

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, require

MOS_REF = BibRef(
    book="Sedra & Smith, Microelectronic Circuits", chapter="MOS field-effect transistors"
)


@dataclass(frozen=True)
class MosfetModel:
    VTO: pint.Quantity
    KP: pint.Quantity  # A/V²
    LAMBDA: pint.Quantity  # 1/V

    def __post_init__(self) -> None:
        require(self.VTO, "V", "VTO")
        require(self.KP, "A/V**2", "KP")
        require(self.LAMBDA, "1/V", "LAMBDA")
        if not self.KP.magnitude > 0 or self.LAMBDA.magnitude < 0:
            raise ValueError("KP deve ser positivo e LAMBDA não negativo")

    def spice(self, name: str = "MMOD") -> str:
        return (
            f".model {name} NMOS(LEVEL=1 VTO={self.VTO.m_as('V'):.6g} "
            f"KP={self.KP.m_as('A/V**2'):.6g} LAMBDA={self.LAMBDA.m_as('1/V'):.6g})"
        )


def drain_current(m: MosfetModel, vgs: pint.Quantity, vds: pint.Quantity) -> pint.Quantity:
    require(vgs, "V", "VGS")
    require(vds, "V", "VDS")
    vov = np.asarray(vgs.m_as("V") - m.VTO.m_as("V"), dtype=float)
    v = np.asarray(vds.m_as("V"), dtype=float)
    kp = m.KP.m_as("A/V**2")
    lam = m.LAMBDA.m_as("1/V")
    vov, v = np.broadcast_arrays(vov, v)
    triode = kp * (vov * v - v**2 / 2) * (1 + lam * v)
    sat = kp / 2 * vov**2 * (1 + lam * v)
    i = np.where(vov <= 0, 0.0, np.where(v < vov, triode, sat))
    return Q_(i if i.ndim else float(i), "A")


def fit_to_datasheet(
    vth: pint.Quantity, rds_on: pint.Quantity, vgs: pint.Quantity, lam: pint.Quantity
) -> tuple[MosfetModel, list[Calculated[pint.Quantity]]]:
    require(vth, "V", "VGS(th)")
    require(rds_on, "ohm", "RDS(on)")
    require(vgs, "V", "VGS")
    vov: pint.Quantity = vgs - vth
    if vov.magnitude <= 0:
        raise ValueError("VGS do ensaio de RDS(on) deve ser maior que VGS(th)")
    kp = Q_(1 / (rds_on.m_as("ohm") * vov.m_as("V")), "A/V**2")
    step = record(
        "KP_fit",
        "Parâmetro de transcondutância a partir de RDS(on) (triodo profundo)",
        r"K_P = \frac{1}{R_{DS(on)}\,(V_{GS} - V_T)}",
        output=kp,
        inputs={"R_{DS(on)}": rds_on, "V_{GS}": vgs, "V_T": vth},
        assumptions=[
            "modelo quadrático com W = L",
            "V_DS pequeno no ensaio de RDS(on)",
            "VT tomado como VGS(th) do datasheet",
        ],
        reference=MOS_REF,
    )
    return MosfetModel(VTO=vth, KP=kp, LAMBDA=lam), [step]


def saturation_current(
    m: MosfetModel, vgs: pint.Quantity, vds: pint.Quantity
) -> Calculated[pint.Quantity]:
    return record(
        "ID_sat",
        "Corrente de dreno na saturação",
        r"I_D = \frac{K_P}{2}(V_{GS} - V_T)^2 (1 + \lambda V_{DS})",
        output=drain_current(m, vgs, vds),
        inputs={"K_P": m.KP, "V_{GS}": vgs, "V_T": m.VTO, r"\lambda": m.LAMBDA, "V_{DS}": vds},
        assumptions=["V_DS ≥ V_GS − V_T (saturação)"],
        reference=MOS_REF,
    )
