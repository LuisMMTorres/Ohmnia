"""Steady-state junction temperature (SV-TERM, first part).

    sem dissipador:  Tj = TA + P·Rθja
    com dissipador:  Tj = TA + P·(Rθjc + Rθcs + Rθsa)
    dissipador necessário: Rθsa ≤ (Tj,max − margem − TA)/P − Rθjc − Rθcs

Reference: Mohan, Undeland & Robbins, *Power Electronics* (heat sinks and thermal design
chapter). Chapter and equation numbers still to be checked against the printed book.
"""

from __future__ import annotations

import pint

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, require

THERMAL_REF = BibRef(
    book="Mohan, Undeland & Robbins, Power Electronics", chapter="Heat sinks and thermal design"
)


def junction_temperature(
    designator: str, P: pint.Quantity, TA: pint.Quantity, Rth_ja: pint.Quantity
) -> Calculated[pint.Quantity]:
    require(P, "W", "P")
    require(Rth_ja, "K/W", "Rθja")
    tj = Q_(TA.to("degC").magnitude + P.m_as("W") * Rth_ja.m_as("K/W"), "degC")
    return record(
        f"Tj_{designator}",
        f"Temperatura de junção de {designator} sem dissipador",
        r"T_j = T_A + P\,R_{\theta ja}",
        output=tj,
        inputs={"T_A": TA.to("degC"), "P": P, r"R_{\theta ja}": Rth_ja},
        assumptions=["regime permanente", "montagem do ensaio de Rθja do datasheet"],
        reference=THERMAL_REF,
    )


def required_heatsink(
    designator: str,
    P: pint.Quantity,
    TA: pint.Quantity,
    Tj_max: pint.Quantity,
    margin_K: float,
    Rth_jc: pint.Quantity,
    Rth_cs: pint.Quantity,
) -> Calculated[pint.Quantity]:
    require(P, "W", "P")
    budget = Tj_max.to("degC").magnitude - margin_K - TA.to("degC").magnitude
    rsa = Q_(
        budget / P.m_as("W") - Rth_jc.m_as("K/W") - Rth_cs.m_as("K/W") if P.magnitude > 0 else 1e9,
        "K/W",
    )
    return record(
        f"Rsa_{designator}",
        f"Resistência térmica máxima do dissipador de {designator}",
        r"R_{\theta sa} \le \frac{T_{j,max} - \Delta T_{marg} - T_A}{P}"
        r" - R_{\theta jc} - R_{\theta cs}",
        output=rsa,
        inputs={
            r"T_{j,max}": Tj_max.to("degC"),
            r"\Delta T_{marg}": Q_(margin_K, "K"),
            "T_A": TA.to("degC"),
            "P": P,
            r"R_{\theta jc}": Rth_jc,
            r"R_{\theta cs}": Rth_cs,
        },
        assumptions=["regime permanente", "Rθcs da interface informada no projeto"],
        reference=THERMAL_REF,
    )
