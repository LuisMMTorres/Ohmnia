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
    kind: Literal["max_rating", "characteristic", "thermal", "geometry"]
    description: str = ""
    conditions_required: list[str] = Field(default_factory=list)


class CategorySchema(BaseModel):
    category: str
    extends: str | None = None
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
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    parent_name = data.get("extends")
    if parent_name:
        # A child category inherits the parent's parameter definitions; it may redefine
        # ``required`` and add parameters. Parameters not required become optional.
        parent = load_schema(parent_name)
        params = {k: v.model_dump() for k, v in parent.parameters.items()}
        params.update(data.get("parameters") or {})
        data["parameters"] = params
        data.setdefault("required", parent.required)
        listed = set(data["required"])
        data["optional"] = [k for k in params if k not in listed]
    return CategorySchema.model_validate(data)


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
        spec = schema.parameters.get(param.symbol)
        if spec is None:
            problems.append(f"{key}: parâmetro não previsto na categoria {record.category}")
            continue
        if (
            Q_(1, parse_unit(param.unit)).dimensionality
            != Q_(1, parse_unit(spec.unit)).dimensionality
        ):
            problems.append(f"{key}: unidade {param.unit} incompatível com {spec.unit}")
        if param.has_value:
            for cond in spec.conditions_required:
                # "Tj|TA": either condition satisfies the requirement (datasheets often state
                # ambient temperature for pulsed measurements).
                options = cond.split("|")
                if not any(o in param.conditions for o in options):
                    problems.append(f"{key}: falta a condição de teste {' ou '.join(options)}")
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
