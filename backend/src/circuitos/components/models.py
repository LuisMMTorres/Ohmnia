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


AxisScale = Literal["lin", "log"]


class AxisSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    quantity: str  # "IF", "VF", "RDS(on)/RDS(on)@25°C"
    unit: str  # "A", "V", "dimensionless"
    scale: AxisScale = "lin"

    @field_validator("unit")
    @classmethod
    def _unit_known(cls, unit: str) -> str:
        parse_unit(unit)
        return unit


class Curve(BaseModel):
    """A curve digitised from a datasheet figure (docs/modelo-de-dados.md, section 2.5)."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    x: AxisSpec
    y: AxisSpec
    family: dict[str, QuantityModel] = Field(default_factory=dict)  # e.g. Tj = 125 °C
    points: list[tuple[float, float]] = Field(min_length=2)
    source: SourceRef
    method: Literal["manual", "vetor", "cor"] = "manual"
    digitized_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _points_fit_scales(self) -> Curve:
        if self.source.page is None:
            raise ValueError(f"Curva {self.name}: a fonte precisa da página da figura")
        for axis, idx in ((self.x, 0), (self.y, 1)):
            if axis.scale == "log" and any(p[idx] <= 0 for p in self.points):
                raise ValueError(f"Curva {self.name}: eixo logarítmico com valor não positivo")
        return self


class FitResidual(BaseModel):
    x: float
    measured: float
    model: float
    error_pct: float


class FitReport(BaseModel):
    """How well a fitted SPICE model reproduces the datasheet (rule 4 for models)."""

    curves: list[str] = Field(default_factory=list)  # curve ids used
    quantity: str  # what the error is measured on, e.g. "VF(IF)"
    points: int
    rms_error_pct: float
    max_error_pct: float
    residuals: list[FitResidual] = Field(default_factory=list)
    simulated: bool = False  # residuals computed by ngspice on the final .model
    assumptions: list[str] = Field(default_factory=list)
    params_origin: dict[str, str] = Field(default_factory=dict)


class SpiceModel(BaseModel):
    """A ``.model`` or ``.subckt``: from the manufacturer, or fitted to the datasheet."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    kind: Literal["model", "subckt"]
    device: str  # D, NPN, PNP, NMOS, PMOS, NJF, PJF, ... or "subckt"
    pins: list[str] = Field(default_factory=list)
    params: dict[str, float] = Field(default_factory=dict)
    text: str
    origin: Literal["fabricante", "ajustado"]
    source_note: str | None = None  # file name / URL of a manufacturer model
    checked: bool = False  # loaded and ran in ngspice
    check_log: str | None = None
    fit: FitReport | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewState(BaseModel):
    status: ReviewStatus = "rascunho"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_by: str = "sistema"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PinFunction(BaseModel):
    """One leg of the package, as the datasheet names it, and what it is in the schematic symbol."""

    model_config = ConfigDict(frozen=True)

    pin: str  # package pin number as printed ("1", "2", "3"; DIP: "1".."8")
    name: str  # name in the datasheet ("COLLECTOR", "OUT A", "IN− A", "V+", "NC")
    # Symbol pin it carries ("c", "b", "e", "a", "k", "inn", "inp", "out", "d", "g", "s", "mt1",
    # "mt2"), "vcc"/"vee" for supply pins, or None for a pin the symbol does not use (NC, offset,
    # the second unit of a dual op-amp).
    role: str | None = None
    unit: str | None = None  # multi-unit packages: "A", "B"


class Pinout(BaseModel):
    """Pinout of the main package, transcribed from the datasheet (rule 1: page and location)."""

    model_config = ConfigDict(frozen=True)

    package: str  # breadboard package id: "to-92", "to-220", "dip-8", "do-41"...
    pins: list[PinFunction] = Field(min_length=1)
    source: SourceRef
    status: ParameterStatus = "extraido"
    note: str | None = None

    @model_validator(mode="after")
    def _unique_pins(self) -> Pinout:
        numbers = [p.pin for p in self.pins]
        if len(set(numbers)) != len(numbers):
            raise ValueError(f"Pinagem com pino repetido: {numbers}")
        return self


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
    curves: list[Curve] = Field(default_factory=list)
    spice_models: list[SpiceModel] = Field(default_factory=list)
    review: ReviewState = Field(default_factory=ReviewState)
    tags: list[str] = Field(default_factory=list)
    family: str | None = None  # e.g. "1N4001–1N4007": parts sharing one datasheet
    pinout: Pinout | None = None  # breadboard view (Fase 10)
    notes: list[str] = Field(default_factory=list)
    catalog_revision: int = 1  # bump in the YAML to replace the record on the next import

    @model_validator(mode="after")
    def _sources_point_to_known_datasheets(self) -> ComponentRecord:
        known = {d.id for d in self.datasheets}
        for key, param in self.parameters.items():
            # "IR" or "IR@125C": extra entries of the same symbol at other test conditions.
            if key.split("@", 1)[0] != param.symbol:
                raise ValueError(f"Chave {key!r} difere do símbolo {param.symbol!r}")
            if param.source is not None and param.source.datasheet_id not in known:
                raise ValueError(
                    f"{key}: fonte aponta para datasheet inexistente {param.source.datasheet_id!r}"
                )
        if self.pinout is not None and self.pinout.source.datasheet_id not in known:
            ds = self.pinout.source.datasheet_id
            raise ValueError(f"Pinagem: fonte aponta para datasheet inexistente {ds!r}")
        for curve in self.curves:
            if curve.source.datasheet_id not in known:
                raise ValueError(
                    f"Curva {curve.name}: fonte aponta para datasheet inexistente "
                    f"{curve.source.datasheet_id!r}"
                )
        return self

    @property
    def selectable(self) -> bool:
        """Rule 5: only released components take part in automatic selection."""
        return self.review.status == "liberado"
