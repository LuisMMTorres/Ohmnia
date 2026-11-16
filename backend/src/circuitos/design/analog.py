"""Helpers shared by the analog design modules (phase 4): E-series parts, DC checks."""

from __future__ import annotations

from collections.abc import Mapping

import pint

from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.eseries import SeriesName, snap
from circuitos.core.units import Q_, QuantityModel

from .base import Circuit, SimCheck

DC_RUN = 2e-6  # s: resistive (or settled) circuits, the transient is the DC solution


def commercial(
    log: CalcLog,
    step_id: str,
    description: str,
    required: pint.Quantity,
    series: SeriesName,
    mode: str,
    reference: BibRef | None = None,
    note: str | None = None,
) -> pint.Quantity:
    """Round a computed value to the E-series and log it."""
    sym = {"up": r"\lceil", "down": r"\lfloor", "nearest": r"\langle"}[mode]
    end = {"up": r"\rceil", "down": r"\rfloor", "nearest": r"\rangle"}[mode]
    out = snap(required, series, mode)  # type: ignore[arg-type]
    word = {"up": "para cima", "down": "para baixo", "nearest": "ao mais próximo"}[mode]
    # "C_o" → "C_{o,calc}": appending "_{calc}" to a subscripted name is a double subscript
    base, _, sub = step_id.partition("_")
    sub = sub.strip("{}")
    calc = f"{base}_{{{sub},calc}}" if sub else f"{step_id}_{{calc}}"
    return log.add(
        record(
            step_id,
            f"{description} (série {series}, arredondado {word})",
            f"{step_id} = {sym} {calc} {end}_{{{series}}}",
            output=out,
            inputs={calc: required},
            assumptions=[note] if note else [],
            reference=reference,
        )
    )


def dc_circuit(title: str, netlist: str, checks: list[SimCheck], stop: float = DC_RUN) -> Circuit:
    """Circuit checked at its DC operating point (short transient of a resistive network)."""
    return Circuit(
        title=title,
        netlist=netlist,
        tran_stop=QuantityModel(value=stop, unit="s"),
        tran_step=QuantityModel(value=stop / 100, unit="s"),
        period=QuantityModel(value=stop / 2, unit="s"),
        checks=checks,
    )


def dc_check(quantity: str, key: str, probe: str, tol: float = 0.5, why: str = "") -> SimCheck:
    return SimCheck(
        quantity=quantity,
        summary_key=key,
        metric="avg",
        probe=probe,
        tolerance_pct=tol,
        justification=why or "mesmo modelo no cálculo e no simulador",
    )


def q(summary: Mapping[str, QuantityModel], key: str, unit: str) -> float:
    return float(summary[key].to_pint().m_as(unit))


def W(v: float) -> pint.Quantity:
    return Q_(v, "W")
