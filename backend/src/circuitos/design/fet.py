"""Helpers shared by the JFET designs (DM-BIAS, DM-SSA)."""

from __future__ import annotations

import math

import pint

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
from circuitos.core.units import Q_, QuantityModel, parse_unit

from .base import Stress
from .devmodels import BOYLESTAD, Jfet, value

REF_FET = BOYLESTAD.model_copy(update={"chapter": "7 (FET biasing)"})


def vgs_for(m: Jfet, i_d: float, log: CalcLog) -> float:
    """VGS for a drain current, inverting Shockley's equation (saturation)."""
    if not 0 < i_d < m.IDSS:
        raise ValueError(
            f"A corrente pedida ({i_d * 1e3:.3g} mA) precisa ficar entre 0 e IDSS "
            f"({m.IDSS * 1e3:.3g} mA) do JFET"
        )
    vgs = -m.VP * (1 - math.sqrt(i_d / m.IDSS))
    log.add(
        record(
            "VGS_design",
            "VGS para a corrente de dreno desejada (equação de Shockley)",
            r"V_{GS} = V_{GS(off)}\left(1 - \sqrt{I_D/I_{DSS}}\right)",
            output=Q_(vgs, "V"),
            inputs={
                "I_D": Q_(i_d, "A").to("mA"),
                "I_{DSS}": Q_(m.IDSS, "A").to("mA"),
                "V_{GS(off)}": Q_(-m.VP, "V"),
            },
            reference=REF_FET,
        )
    )
    return vgs


def power_stress(
    rec: ComponentRecord | None,
    p: float,
    TA: pint.Quantity,
    log: CalcLog,
    designator: str,
    step_id: str,
) -> Stress:
    """Dissipation as an equivalent load at 25 °C, using the datasheet linear derating.

    The JFET datasheets give Ptot at TA = 25 °C and a derating factor, not RθJA: the allowed
    dissipation at TA is Ptot − k·(TA − 25 °C), so P is checked against Ptot after scaling by
    Ptot / P_allowed(TA).
    """
    ta = TA.to("degC").magnitude
    scale = 1.0
    inputs: dict[str, pint.Quantity] = {"P": Q_(p, "W").to("mW"), "T_A": TA.to("degC")}
    if rec is not None:
        pt, kd = rec.parameters.get("Ptot"), rec.parameters.get("Ptot_derating")
        if pt is not None and kd is not None and pt.has_value and kd.has_value:
            ptot = Q_(value(pt, ("max",)), parse_unit(pt.unit)).m_as("W")
            k = Q_(value(kd, ("max",)), parse_unit(kd.unit)).m_as("W/K")
            allowed = ptot - k * max(ta - 25.0, 0.0)
            if allowed <= 0:
                raise ValueError(f"{rec.part_number}: sem dissipação permitida a {ta:g} °C")
            scale = ptot / allowed
            inputs |= {"P_{tot,25}": Q_(ptot, "W").to("mW"), "k": Q_(k, "W/K").to("mW/K")}
    pe = log.add(
        record(
            step_id,
            f"Dissipação de {designator} referida a 25 °C (curva de redução do datasheet)",
            r"P_{eq} = P\,\frac{P_{tot,25}}{P_{tot,25} - k\,(T_A - 25\,°C)}",
            output=Q_(p * scale, "W").to("mW"),
            inputs=inputs,
            assumptions=["redução linear da dissipação acima de 25 °C, como no datasheet"],
            reference=REF_FET,
        )
    )
    return Stress(
        designator=designator,
        key="Ptot",
        label="Dissipação (equivalente a 25 °C)",
        value=QuantityModel.from_pint(pe.to("W")),
        calc_step_id=step_id,
    )
