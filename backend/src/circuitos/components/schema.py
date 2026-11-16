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
    # qualitative specifications (name -> description), e.g. output type or protocol
    attributes: dict[str, str] = Field(default_factory=dict)

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
        data["attributes"] = parent.attributes | (data.get("attributes") or {})
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
    for key in record.attributes:
        if key not in schema.attributes:
            problems.append(f"{key}: atributo não previsto na categoria {record.category}")
    return problems


def release_blockers(record: ComponentRecord) -> list[str]:
    """Reasons why the record cannot be released for automatic selection."""
    blockers = validate_against_schema(record)
    schema = load_schema(record.category)
    for key in schema.required:
        # a symbol given per condition ("IGT@Q1" … "IGT@Q4" of a TRIAC) satisfies the
        # requirement when every entry with a value is reviewed
        params = [
            (k, p)
            for k, p in record.parameters.items()
            if (k == key or p.symbol == key) and p.has_value
        ]
        if not params:
            blockers.append(f"{key}: parâmetro obrigatório ausente")
        for k, param in params:
            if param.status != "revisado":
                blockers.append(f"{k}: parâmetro obrigatório não revisado ({param.status})")
    return blockers


def mark_sourced_reviewed(record: ComponentRecord) -> tuple[ComponentRecord, int, list[str]]:
    """Mark as reviewed every parameter and attribute whose source cites a page.

    Used by the category review, where the user confirms a whole category at once. Entries
    without a page stay as they are (a reviewed value must point to its page, rule 1).
    Returns the new record, how many entries changed and the keys left without a page.
    """
    marked = 0
    unsourced: list[str] = []
    params = dict(record.parameters)
    for key, param in record.parameters.items():
        if param.status == "revisado":
            continue
        if param.source is None or param.source.page is None:
            unsourced.append(key)
            continue
        params[key] = param.model_copy(update={"status": "revisado"})
        marked += 1
    attrs = dict(record.attributes)
    for key, attr in record.attributes.items():
        if attr.status == "revisado":
            continue
        if attr.source is None or attr.source.page is None:
            unsourced.append(key)
            continue
        attrs[key] = attr.model_copy(update={"status": "revisado"})
        marked += 1
    return record.model_copy(update={"parameters": params, "attributes": attrs}), marked, unsourced


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
