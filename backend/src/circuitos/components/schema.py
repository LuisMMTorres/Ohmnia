"""Per-category parameter schemas and the release rule.

A schema lists the parameters a category requires, their units and which test conditions each
must state. Schemas live as YAML files in ``components/schemas/`` and are versioned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from circuitos.core.errors import DataIntegrityError
from circuitos.core.units import Q_, parse_unit

from .models import ComponentRecord

SCHEMA_DIR = Path(__file__).parent / "schemas"


class ParameterSpec(BaseModel):
    unit: str
    kind: Literal["max_rating", "characteristic", "thermal"]
    description: str = ""
    conditions_required: list[str] = Field(default_factory=list)


class CategorySchema(BaseModel):
    category: str
    schema_version: str
    description: str = ""
    required: list[str]
    optional: list[str] = Field(default_factory=list)
    parameters: dict[str, ParameterSpec]

    def model_post_init(self, _context: object) -> None:
        listed = set(self.required) | set(self.optional)
        missing = listed - set(self.parameters)
        if missing:
            raise ValueError(f"{self.category}: parâmetros sem especificação: {sorted(missing)}")
        for spec in self.parameters.values():
            parse_unit(spec.unit)


@cache
def load_schema(category: str) -> CategorySchema:
    path = SCHEMA_DIR / f"{category}.yaml"
    if not path.exists():
        raise DataIntegrityError(f"Categoria sem esquema: {category}")
    return CategorySchema.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def available_categories() -> list[str]:
    return sorted(p.stem for p in SCHEMA_DIR.glob("*.yaml"))


def validate_against_schema(record: ComponentRecord) -> list[str]:
    """Return the list of problems (empty when the record conforms to its category schema)."""
    schema = load_schema(record.category)
    problems: list[str] = []
    if record.schema_version != schema.schema_version:
        problems.append(
            f"versão do esquema {record.schema_version} difere da atual {schema.schema_version}"
        )
    for key, param in record.parameters.items():
        spec = schema.parameters.get(key)
        if spec is None:
            problems.append(f"{key}: parâmetro não previsto na categoria {record.category}")
            continue
        if Q_(1, parse_unit(param.unit)).dimensionality != Q_(1, parse_unit(spec.unit)).dimensionality:
            problems.append(f"{key}: unidade {param.unit} incompatível com {spec.unit}")
        if param.has_value:
            for cond in spec.conditions_required:
                if cond not in param.conditions:
                    problems.append(f"{key}: falta a condição de teste {cond}")
    return problems


def release_blockers(record: ComponentRecord) -> list[str]:
    """Reasons why the record cannot be released for automatic selection."""
    blockers = validate_against_schema(record)
    schema = load_schema(record.category)
    for key in schema.required:
        param = record.parameters.get(key)
        if param is None or not param.has_value:
            blockers.append(f"{key}: parâmetro obrigatório ausente")
        elif param.status != "revisado":
            blockers.append(f"{key}: parâmetro obrigatório não revisado ({param.status})")
    return blockers


def release(record: ComponentRecord, reviewer: str) -> ComponentRecord:
    """Mark a record as released. Raises if any blocker remains."""
    blockers = release_blockers(record)
    if blockers:
        raise DataIntegrityError(
            f"{record.part_number} não pode ser liberado: " + "; ".join(blockers)
        )
    review = record.review.model_copy(
        update={"status": "liberado", "reviewed_by": reviewer, "reviewed_at": datetime.now(UTC)}
    )
    return record.model_copy(update={"review": review})
