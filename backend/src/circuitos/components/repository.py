"""Component catalogue storage (SQLite through SQLAlchemy) and faceted search.

The repository's YAML files (``data/components``) are the reviewed, versioned source of the
catalogue; the SQLite database is the user's working copy, where review decisions are recorded.
Importing never discards a review unless the YAML record's ``catalog_revision`` was increased.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pint
import yaml
from pydantic import BaseModel, ValidationError
from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from circuitos.core.errors import DataIntegrityError
from circuitos.core.units import Q_, QuantityModel, parse_quantity, parse_unit

from .models import ComponentRecord, Parameter, ParameterStatus
from .schema import load_schema, release, release_blockers, validate_against_schema

_NAMESPACE = uuid.UUID("6f1c3c2e-6d5b-4b8e-9a0e-3c1f2b7d9a10")


def component_id(manufacturer: str, part_number: str) -> uuid.UUID:
    """Stable id, so the same part keeps its id across imports and machines."""
    return uuid.uuid5(_NAMESPACE, f"{manufacturer.strip().lower()}|{part_number.strip().upper()}")


class _Base(DeclarativeBase):
    pass


class _ComponentRow(_Base):
    __tablename__ = "components"
    __table_args__ = (UniqueConstraint("manufacturer", "part_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    manufacturer: Mapped[str] = mapped_column(String(128))
    part_number: Mapped[str] = mapped_column(String(128), index=True)
    family: Mapped[str | None] = mapped_column(String(128))
    review_status: Mapped[str] = mapped_column(String(16), index=True)
    catalog_revision: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ParamFilter(BaseModel):
    """``VRRM >= 600 V``. Compared against the guaranteed worst-case datasheet value."""

    symbol: str
    op: Literal[">=", "<="]
    value: QuantityModel


def guaranteed_value(param: Parameter, op: Literal[">=", "<="], is_rating: bool) -> float | None:
    """Value a filter must be compared with.

    ``>=`` asks for a guaranteed lower bound: ``min``; for an absolute maximum rating, the rating
    itself (``max``); otherwise ``typ`` as a last resort. ``<=`` asks for a guaranteed upper bound:
    ``max``, else ``typ``.
    """
    if op == ">=":
        if param.min is not None:
            return param.min
        if is_rating and param.max is not None:
            return param.max
        return param.typ
    return param.max if param.max is not None else param.typ


@dataclass
class ImportReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


class ComponentRepository:
    def __init__(self, url: str = "sqlite:///:memory:"):
        self.engine = create_engine(url)
        _Base.metadata.create_all(self.engine)
        self._session = sessionmaker(self.engine, expire_on_commit=False)

    # ------------------------------------------------------------------------------ writes --
    def _to_row(self, record: ComponentRecord, row: _ComponentRow | None) -> _ComponentRow:
        row = row or _ComponentRow(id=str(record.id))
        row.category = record.category
        row.manufacturer = record.manufacturer
        row.part_number = record.part_number
        row.family = record.family
        row.review_status = record.review.status
        row.catalog_revision = record.catalog_revision
        row.document = record.model_dump(mode="json")
        row.updated_at = datetime.now(UTC)
        return row

    def save(self, record: ComponentRecord) -> ComponentRecord:
        with self._session.begin() as session:
            row = session.get(_ComponentRow, str(record.id))
            session.add(self._to_row(record, row))
        return record

    def import_records(self, records: Iterable[ComponentRecord]) -> ImportReport:
        report = ImportReport()
        for record in records:
            existing = self.get_or_none(record.id)
            label = f"{record.manufacturer} {record.part_number}"
            if existing is None:
                self.save(record)
                report.added.append(label)
            elif record.catalog_revision > existing.catalog_revision:
                self.save(record)  # new catalogue revision: reviews start over
                report.updated.append(label)
            else:
                report.unchanged.append(label)
        return report

    def import_directory(self, directory: Path) -> ImportReport:
        records: list[ComponentRecord] = []
        report = ImportReport()
        for path in sorted(directory.rglob("*.yaml")):
            try:
                records.extend(load_records_file(path))
            except (ValidationError, DataIntegrityError, yaml.YAMLError) as exc:
                report.errors[str(path.relative_to(directory))] = str(exc)
        result = self.import_records(records)
        result.errors.update(report.errors)
        return result

    def set_parameter_status(
        self, record_id: uuid.UUID, key: str, status: ParameterStatus, note: str | None = None
    ) -> ComponentRecord:
        record = self.get(record_id)
        if key not in record.parameters:
            raise DataIntegrityError(f"{record.part_number} não tem o parâmetro {key}")
        update: dict[str, object] = {"status": status}
        if note is not None:
            update["note"] = note
        # Re-validate: "revisado" requires a source with page.
        param = Parameter.model_validate(record.parameters[key].model_dump() | update)
        params = dict(record.parameters) | {key: param}
        review = record.review
        if (review.status == "liberado" and status != "revisado") or review.status == "rascunho":
            review = review.model_copy(update={"status": "em_revisao"})
        return self.save(record.model_copy(update={"parameters": params, "review": review}))

    def release(self, record_id: uuid.UUID, reviewer: str) -> ComponentRecord:
        return self.save(release(self.get(record_id), reviewer))

    # ------------------------------------------------------------------------------- reads --
    def get_or_none(self, record_id: uuid.UUID) -> ComponentRecord | None:
        with self._session() as session:
            row = session.get(_ComponentRow, str(record_id))
            return ComponentRecord.model_validate(row.document) if row else None

    def get(self, record_id: uuid.UUID) -> ComponentRecord:
        record = self.get_or_none(record_id)
        if record is None:
            raise DataIntegrityError(f"Componente {record_id} não encontrado")
        return record

    def search(
        self,
        *,
        category: str | None = None,
        text: str | None = None,
        review_status: str | None = None,
        filters: Iterable[ParamFilter] = (),
    ) -> list[ComponentRecord]:
        stmt = select(_ComponentRow).order_by(_ComponentRow.part_number)
        if category:
            # "diode" matches "diode.rectifier", "diode.zener"...
            stmt = stmt.where(
                (_ComponentRow.category == category)
                | _ComponentRow.category.startswith(f"{category}.")
            )
        if review_status:
            stmt = stmt.where(_ComponentRow.review_status == review_status)
        if text:
            like = f"%{text.strip()}%"
            stmt = stmt.where(
                _ComponentRow.part_number.ilike(like)
                | _ComponentRow.manufacturer.ilike(like)
                | _ComponentRow.family.ilike(like)
            )
        with self._session() as session:
            records = [ComponentRecord.model_validate(r.document) for r in session.scalars(stmt)]
        filters = list(filters)
        return [r for r in records if all(_matches(r, f) for f in filters)]

    def categories(self) -> dict[str, int]:
        with self._session() as session:
            counts: dict[str, int] = {}
            for (category,) in session.execute(select(_ComponentRow.category)):
                counts[category] = counts.get(category, 0) + 1
            return counts

    def session(self) -> Session:
        return self._session()


def _matches(record: ComponentRecord, flt: ParamFilter) -> bool:
    param = record.parameters.get(flt.symbol)
    if param is None or not param.has_value:
        return False
    schema = load_schema(record.category)
    spec = schema.parameters.get(flt.symbol)
    is_rating = spec is not None and spec.kind == "max_rating"
    value = guaranteed_value(param, flt.op, is_rating)
    if value is None:
        return False
    try:
        mine = Q_(value, parse_unit(param.unit))
        target = flt.value.to_pint()
        mine_in_target = float(mine.m_as(target.units))
    except Exception:
        return False
    limit = float(target.magnitude)
    return mine_in_target >= limit if flt.op == ">=" else mine_in_target <= limit


def _normalise_parameter(
    key: str, raw: dict[str, object], default_ds: str | None, params: dict[str, object]
) -> None:
    raw.setdefault("symbol", key.split("@", 1)[0])
    conditions = raw.get("conditions")
    if isinstance(conditions, dict):
        for name, value in list(conditions.items()):
            if isinstance(value, str) and value.startswith("="):
                # "=VDC": the condition is another parameter of the same part, e.g. IR measured
                # "at rated DC blocking voltage".
                ref = params.get(value[1:])
                if not isinstance(ref, dict) or ref.get("max") is None:
                    raise DataIntegrityError(
                        f"{key}: condição {name} refere-se a {value[1:]}, que não tem valor máximo"
                    )
                conditions[name] = {"value": float(str(ref["max"])), "unit": str(ref["unit"])}
            elif isinstance(value, str | int | float):
                quantity = parse_quantity(str(value))
                conditions[name] = {
                    "value": float(quantity.magnitude),
                    "unit": _unit_symbol(quantity),
                }
    source = raw.get("source")
    if isinstance(source, dict) and default_ds is not None:
        source.setdefault("datasheet_id", default_ds)


def _unit_symbol(quantity: pint.Quantity) -> str:
    """Short ASCII unit symbol ("ms", "uA", "A/us", "°C") for display and storage."""
    return format(quantity.units, "~").replace("μ", "u").replace("µ", "u").replace(" ", "")


def _record_from_dict(data: dict[str, object], origin: str) -> ComponentRecord:
    datasheets = data.get("datasheets") or []
    default_ds = (
        str(datasheets[0]["id"])
        if isinstance(datasheets, list) and len(datasheets) == 1 and isinstance(datasheets[0], dict)
        else None
    )
    data.setdefault("id", str(component_id(str(data["manufacturer"]), str(data["part_number"]))))
    params = data.get("parameters") or {}
    if not isinstance(params, dict):
        raise DataIntegrityError(f"{origin}: 'parameters' deve ser um mapa")
    for key, raw in params.items():
        if isinstance(raw, dict):
            _normalise_parameter(str(key), raw, default_ds, params)
    record = ComponentRecord.model_validate(data)
    problems = validate_against_schema(record)
    if problems:
        raise DataIntegrityError(f"{origin} ({record.part_number}): " + "; ".join(problems))
    return record


def load_records_file(path: Path) -> list[ComponentRecord]:
    """Load one part, or a family file (``parts:``) sharing one datasheet table.

    In a family file, ``parameters`` holds values common to every part, ``per_part`` holds the
    definition (unit, source, conditions, status) of parameters whose value changes per part,
    and ``parts`` maps each part number to those values (and optional overrides).
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DataIntegrityError(f"{path.name}: conteúdo YAML inválido")
    parts = data.pop("parts", None)
    if parts is None:
        return [_record_from_dict(data, path.name)]
    per_part = data.pop("per_part", {}) or {}
    shared = data.pop("parameters", {}) or {}
    data.pop("format", None)
    records = []
    for part_number, overrides in parts.items():
        params = copy.deepcopy(shared)
        overrides = dict(overrides or {})
        # Record-level fields a single part may override (e.g. one part discontinued).
        meta = {k: overrides.pop(k) for k in ("lifecycle", "notes") if k in overrides}
        for key, values in overrides.items():
            base = copy.deepcopy(per_part.get(key, params.get(key, {})))
            if not isinstance(values, dict):
                values = {"max": values}
            params[key] = base | values
        record_data = (
            copy.deepcopy(data) | meta | {"part_number": str(part_number), "parameters": params}
        )
        records.append(_record_from_dict(record_data, path.name))
    return records


def load_record_file(path: Path) -> ComponentRecord:
    records = load_records_file(path)
    if len(records) != 1:
        raise DataIntegrityError(f"{path.name}: arquivo de família; use load_records_file")
    return records[0]


def dump_record(record: ComponentRecord) -> str:
    """YAML for a record, in the same layout as the catalogue files."""
    data = record.model_dump(mode="json", exclude_none=True, exclude={"id"})
    for param in data.get("parameters", {}).values():
        param.pop("symbol", None)
        if not param.get("conditions"):
            param.pop("conditions", None)
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


__all__ = [
    "ComponentRepository",
    "ImportReport",
    "ParamFilter",
    "component_id",
    "dump_record",
    "guaranteed_value",
    "load_record_file",
    "load_records_file",
    "release_blockers",
]
