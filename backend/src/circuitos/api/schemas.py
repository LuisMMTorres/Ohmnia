"""API request/response models (transport only; domain types live in the core packages)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from circuitos.core.units import QuantityModel, VectorModel


class SimulationIn(BaseModel):
    netlist: str = Field(min_length=1, max_length=2_000_000)
    timeout_s: float = Field(default=120.0, gt=0, le=3600)
    backend: Literal["auto", "shared", "batch"] = "auto"


class VectorInfo(BaseModel):
    name: str
    unit: str
    length: int
    complex: bool


class PlotInfo(BaseModel):
    name: str
    kind: str
    title: str
    scale: str | None
    vectors: list[VectorInfo]
    run: int = 0
    run_label: str = ""
    base: str = ""


class RunOut(BaseModel):
    index: int
    label: str
    values: dict[str, str]


class JobErrorOut(BaseModel):
    kind: str
    message: str
    suggestions: list[str]
    log: str


class JobOut(BaseModel):
    id: str
    state: str
    progress: float
    message: str
    backend: str | None = None
    elapsed_s: float | None = None
    plots: list[PlotInfo] | None = None
    error: JobErrorOut | None = None
    log: str | None = None
    runs: list[RunOut] | None = None
    summary: dict[str, Any] | None = None
    warnings: list[str] | None = None


class PlotData(BaseModel):
    plot: str
    kind: str
    x: VectorModel | None
    x_name: str | None
    traces: dict[str, VectorModel]
    decimated: bool


class Measurements(BaseModel):
    vector: str
    mean: QuantityModel
    rms: QuantityModel
    peak: QuantityModel
    peak_to_peak: QuantityModel
    minimum: QuantityModel
    maximum: QuantityModel
    frequency: QuantityModel | None = None
    period: QuantityModel | None = None
    duty_cycle: QuantityModel | None = None
    base: QuantityModel | None = None
    top: QuantityModel | None = None
    rise_time: QuantityModel | None = None
    fall_time: QuantityModel | None = None
    overshoot: QuantityModel | None = None
    undershoot: QuantityModel | None = None


class SnapIn(BaseModel):
    value: QuantityModel
    series: Literal["E3", "E6", "E12", "E24", "E48", "E96", "E192"] = "E24"
    mode: Literal["nearest", "up", "down"] = "nearest"


class SnapOut(BaseModel):
    value: QuantityModel
    formatted: str
    tolerance: float
