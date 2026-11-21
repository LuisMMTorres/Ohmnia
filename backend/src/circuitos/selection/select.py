"""Margin checks and automatic selection of catalogue components (SV-SEL).

Rule 5 (CLAUDE.md): only released components take part in automatic selection. A component the
user locks by hand may be unreleased; the result then carries a warning.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.core.units import Q_, QuantityModel, parse_unit
from circuitos.design.base import MarginCheck, MarginStatus, Stress

from .derating import DeratingPolicy


def rating_of(record: ComponentRecord, key: str) -> Parameter | None:
    p = record.parameters.get(key)
    return p if p is not None and p.has_value else None


def _limit(p: Parameter) -> float:
    for value in (p.max, p.typ, p.min):
        if value is not None:
            return value
    raise ValueError(f"{p.symbol} sem valor")


def check(
    record: ComponentRecord, stresses: Iterable[Stress], policy: DeratingPolicy
) -> list[MarginCheck]:
    """Margin of every stress whose key is a rating of the record's category."""
    out: list[MarginCheck] = []
    for s in stresses:
        p = rating_of(record, s.key)
        if p is None:
            continue
        stress = s.value.to_pint()
        rating = Q_(_limit(p), parse_unit(p.unit)).to(stress.units)
        factor = policy.factor(record.category, s.key)
        sv = abs(float(stress.magnitude))
        rv = float(rating.magnitude)
        margin = math.inf if sv == 0 else (rv / sv - 1) * 100
        status: MarginStatus = "ok" if rv >= factor * sv else "atencao" if rv >= sv else "violado"
        out.append(
            MarginCheck(
                designator=s.designator,
                parameter=s.key,
                stress=QuantityModel(value=sv, unit=s.value.unit),
                rating=QuantityModel.from_pint(rating),
                required_factor=factor,
                margin_pct=margin if math.isfinite(margin) else 1e9,
                status=status,
                note=_condition_note(p),
            )
        )
    return out


def _condition_note(p: Parameter) -> str | None:
    if not p.conditions:
        return None
    parts = [f"{k} = {c.value:g} {c.unit}" for k, c in p.conditions.items()]
    return "datasheet: " + ", ".join(parts)


@dataclass(frozen=True)
class Ranked:
    record: ComponentRecord
    checks: list[MarginCheck]
    score: float


def rank(
    candidates: Sequence[ComponentRecord],
    stresses: Sequence[Stress],
    policy: DeratingPolicy,
    required_keys: Sequence[str],
    *,
    include_unreleased: bool = False,
) -> list[Ranked]:
    """Released candidates that meet every required rating with the policy factor.

    ``include_unreleased`` ranks parts still under review too: never used to choose a part
    (rule 5), only to tell the user which ones would serve once reviewed.

    Ranked by the smallest over-rating (sum of log(rating / (factor·stress))), so the cheapest
    adequate part tends to come first; ties by part number.
    """
    ranked: list[Ranked] = []
    for record in candidates:
        if not record.selectable and not include_unreleased:
            continue
        checks = check(record, stresses, policy)
        keys = {c.parameter for c in checks}
        if any(k not in keys for k in required_keys):
            continue
        if any(c.status != "ok" for c in checks):
            continue
        score = sum(
            math.log(max(c.rating.value / (c.required_factor * c.stress.value), 1.0))
            for c in checks
            if c.stress.value > 0
        )
        ranked.append(Ranked(record=record, checks=checks, score=score))
    ranked.sort(key=lambda r: (r.score, r.record.part_number))
    return ranked
