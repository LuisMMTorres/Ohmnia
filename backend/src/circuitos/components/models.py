"""Component records with per-parameter traceability (docs/modelo-de-dados.md, section 2).

Rule 1: no parameter without a source. Rule 5: only released components reach automatic
selection. Both are enforced here, at the model level, so no code path can bypass them.
"""

from __future__ import annotations

import datetime as dt
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from circuitos.core.units import QuantityModel, parse_unit

ParameterStatus = Literal["a_verificar", "extraido", "revisado"]
ReviewStatus = Literal["rascunho", "em_revisao", "liberado", "rejeitado"]
Lifecycle = Literal["ativo", "nrnd", "obsoleto", "desconhecido"]


class DatasheetRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    manufacturer: str
    document_number: str | None = None
    revision: str | None = None
    date: dt.date | None = None
    url: HttpUrl | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    retrieved_at: datetime | None = None


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasheet_id: str
    page: int | None = Field(default=None, ge=1)
    location: str | None = None
    excerpt: str | None = None
    bbox: tuple[float, float, float, float] | None = None


class Parameter(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    min: float | None = None
    typ: float | None = None
    max: float | None = None
    unit: str
    conditions: dict[str, QuantityModel] = Field(default_factory=dict)
    source: SourceRef | None = None
    status: ParameterStatus = "a_verificar"
    note: str | None = None

    @field_validator("unit")
    @classmethod
    def _unit_known(cls, unit: str) -> str:
        parse_unit(unit)
        return unit

    @model_validator(mode="after")
    def _consistency(self) -> Parameter:
        values = [v for v in (self.min, self.typ, self.max) if v is not None]
        if self.status != "a_verificar" and not values:
            raise ValueError(f"{self.symbol}: parâmetro {self.status} sem valor")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"{self.symbol}: mínimo maior que máximo")
        if self.typ is not None:
            if self.min is not None and self.typ < self.min:
                raise ValueError(f"{self.symbol}: típico menor que mínimo")
            if self.max is not None and self.typ > self.max:
                raise ValueError(f"{self.symbol}: típico maior que máximo")
        if self.status == "revisado" and (self.source is None or self.source.page is None):
            raise ValueError(f"{self.symbol}: parâmetro revisado exige fonte com página")
        if self.status == "extraido" and self.source is None:
            raise ValueError(f"{self.symbol}: parâmetro extraído exige fonte")
        return self

    @property
    def has_value(self) -> bool:
        return any(v is not None for v in (self.min, self.typ, self.max))


class ReviewState(BaseModel):
    status: ReviewStatus = "rascunho"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_by: str = "sistema"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ComponentRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    category: str
    schema_version: str
    manufacturer: str
    part_number: str
    package: str | None = None
    lifecycle: Lifecycle = "desconhecido"
    parameters: dict[str, Parameter] = Field(default_factory=dict)
    datasheets: list[DatasheetRef] = Field(default_factory=list)
    review: ReviewState = Field(default_factory=ReviewState)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sources_point_to_known_datasheets(self) -> ComponentRecord:
        known = {d.id for d in self.datasheets}
        for key, param in self.parameters.items():
            if param.symbol != key:
                raise ValueError(f"Chave {key!r} difere do símbolo {param.symbol!r}")
            if param.source is not None and param.source.datasheet_id not in known:
                raise ValueError(
                    f"{key}: fonte aponta para datasheet inexistente {param.source.datasheet_id!r}"
                )
        return self

    @property
    def selectable(self) -> bool:
        """Rule 5: only released components take part in automatic selection."""
        return self.review.status == "liberado"
