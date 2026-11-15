"""Measure the automatic mapping against the catalogue's hand-transcribed values.

The catalogue YAML files were transcribed from the manufacturers' datasheets with page and
location for each value. Running the mapper on the same PDFs and comparing tells how much of the
work the import saves and, more importantly, how often it proposes a *wrong* value. The result
feeds ``docs/validacao/importacao-datasheets.md`` and the DS-EXT test.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel

from circuitos.components.models import ComponentRecord
from circuitos.core.units import Q_, parse_unit

from .mapping import Candidate

Outcome = Literal["igual", "diferente", "ausente"]


class Comparison(BaseModel):
    key: str
    outcome: Outcome
    catalogue: str
    extracted: str | None = None
    page_catalogue: int | None = None
    page_extracted: int | None = None


def _fmt(values: dict[str, float | None], unit: str) -> str:
    parts = [f"{k} {v:g}" for k, v in values.items() if v is not None]
    return f"{', '.join(parts)} {unit}"


def _same(a: float, unit_a: str, b: float, unit_b: str) -> bool:
    try:
        b_in_a = float(Q_(b, parse_unit(unit_b)).m_as(parse_unit(unit_a)))
    except Exception:
        return False
    return abs(a - b_in_a) <= 1e-6 * max(abs(a), 1e-12)


def _matches(c: Candidate, expected: dict[str, float | None], unit: str) -> bool:
    for pos, value in expected.items():
        if value is None:
            continue
        got = getattr(c, pos)
        if got is None or not _same(value, unit, got, c.unit):
            return False
    return True


def compare(record: ComponentRecord, candidates: list[Candidate]) -> list[Comparison]:
    """One line per catalogue parameter that has a value (keys with ``@`` are skipped)."""
    by_key: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_key.setdefault(c.key, []).append(c)
    out: list[Comparison] = []
    for key, param in record.parameters.items():
        if "@" in key or not param.has_value:
            continue
        expected = {"min": param.min, "typ": param.typ, "max": param.max}
        cat_text = _fmt(expected, param.unit)
        page = param.source.page if param.source else None
        options = by_key.get(key, [])
        if not options:
            out.append(
                Comparison(key=key, outcome="ausente", catalogue=cat_text, page_catalogue=page)
            )
            continue
        # the accepted candidate decides
        chosen = next((c for c in options if c.accepted), options[0])
        outcome: Outcome = "igual" if _matches(chosen, expected, param.unit) else "diferente"
        out.append(
            Comparison(
                key=key,
                outcome=outcome,
                catalogue=cat_text,
                extracted=_fmt(
                    {"min": chosen.min, "typ": chosen.typ, "max": chosen.max}, chosen.unit
                ),
                page_catalogue=page,
                page_extracted=chosen.page,
            )
        )
    return out


def summary(rows: list[Comparison]) -> dict[str, int]:
    counts = Counter(r.outcome for r in rows)
    return {k: counts.get(k, 0) for k in ("igual", "diferente", "ausente")}


__all__ = ["Comparison", "compare", "summary"]
