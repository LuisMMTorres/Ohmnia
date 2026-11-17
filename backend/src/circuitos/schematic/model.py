"""Schematic document: components on a grid, wires, net labels, probes, analyses and sweeps.

Coordinates are integer grid units (the editor draws one unit as a few pixels). A component's
pins are at its position plus the pin offsets of its symbol (:mod:`circuitos.schematic.library`)
after mirroring (x → −x) and then rotating clockwise in screen coordinates (y grows downwards).
The document is plain JSON, so it is also the file format of the editor (``.circ.json``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from circuitos.breadboard import board
from circuitos.breadboard.layout import Breadboard

Point = tuple[int, int]
Rotation = Literal[0, 90, 180, 270]

SCHEMA_VERSION = "1"


class Component(BaseModel):
    id: str
    kind: str
    ref: str = Field(min_length=1, max_length=40)
    x: int
    y: int
    rot: Rotation = 0
    mirror: bool = False
    params: dict[str, str] = Field(default_factory=dict)
    part_id: str | None = None  # catalogue record (UUID) whose model replaces the generic one

    @field_validator("ref")
    @classmethod
    def _ref_is_identifier(cls, v: str) -> str:
        if not all(ch.isalnum() or ch == "_" for ch in v):
            raise ValueError(f"Designador {v!r}: use apenas letras, números e _")
        return v


class Wire(BaseModel):
    id: str
    points: list[Point] = Field(min_length=2)


class NetLabel(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=40)
    x: int
    y: int

    @field_validator("name")
    @classmethod
    def _name_is_node(cls, v: str) -> str:
        if not all(ch.isalnum() or ch in "_+-" for ch in v):
            raise ValueError(f"Rótulo {v!r}: use apenas letras, números, _, + e -")
        return v


ProbeKind = Literal["v", "vdiff", "i", "p"]


class NetRef(BaseModel):
    """A net given by a point on it, a label name or a component pin (``R1.2``)."""

    at: Point | None = None
    net: str | None = None
    pin: str | None = None

    @model_validator(mode="after")
    def _one_given(self) -> NetRef:
        if sum(x is not None for x in (self.at, self.net, self.pin)) != 1:
            raise ValueError("Informe exatamente um de: ponto, rótulo ou pino")
        return self


class Probe(BaseModel):
    id: str
    kind: ProbeKind
    name: str | None = None  # display name; default v(net), v(a,b), i(R1), p(Q1)
    target: NetRef | None = None  # v, vdiff (positive side)
    reference: NetRef | None = None  # vdiff (negative side)
    component: str | None = None  # i, p: designator
    pin: str | None = None  # i: pin whose current (into the component) is measured

    @model_validator(mode="after")
    def _complete(self) -> Probe:
        if self.kind in ("v", "vdiff") and self.target is None:
            raise ValueError("Ponta de tensão sem nó")
        if self.kind == "vdiff" and self.reference is None:
            raise ValueError("Ponta diferencial sem nó de referência")
        if self.kind in ("i", "p") and not self.component:
            raise ValueError("Ponta de corrente/potência sem componente")
        return self


AnalysisKind = Literal["op", "tran", "ac", "dc", "noise"]


class Analysis(BaseModel):
    kind: AnalysisKind
    params: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


SweepKind = Literal["none", "step", "temp", "montecarlo", "worstcase"]
MeasureKind = Literal[
    "final", "mean", "rms", "max", "min", "pp", "at", "mag_db_at", "phase_at", "frequency"
]


class ScalarMeasure(BaseModel):
    """A number taken from each run: Monte Carlo statistics and worst-case target."""

    analysis: AnalysisKind = "op"
    vector: str  # probe name or vector name, e.g. "v(out)"
    kind: MeasureKind = "final"
    at: str | None = None  # x of "at", "mag_db_at", "phase_at" (SPICE number)
    start: str | None = None  # window for mean/rms/max/min/pp (transient)
    stop: str | None = None


class Sweep(BaseModel):
    kind: SweepKind = "none"
    # step: "R1.value", "V1.dc", "param:R0" (a .param) or "temp"
    target: str | None = None
    spacing: Literal["list", "lin", "dec", "oct"] = "lin"
    values: list[str] = Field(default_factory=list)  # spacing = list
    start: str | None = None
    stop: str | None = None
    step: str | None = None  # lin: increment
    points: int | None = Field(default=None, ge=1, le=1000)  # dec/oct: points per decade/octave
    runs: int = Field(default=30, ge=1, le=1000)  # Monte Carlo runs (besides the nominal one)
    seed: int = 1
    distribution: Literal["gauss", "uniform"] = "gauss"
    measure: ScalarMeasure | None = None  # required for worstcase


class ScopeConnection(BaseModel):
    positive: str | None = None
    negative: str | None = None

    @field_validator("positive", "negative")
    @classmethod
    def _valid_hole(cls, value: str | None) -> str | None:
        if value is not None:
            board.parse(value)
            return value.strip().lower()
        return None


class Schematic(BaseModel):
    schema_version: str = SCHEMA_VERSION
    title: str = "Circuito sem título"
    components: list[Component] = Field(default_factory=list)
    wires: list[Wire] = Field(default_factory=list)
    labels: list[NetLabel] = Field(default_factory=list)
    probes: list[Probe] = Field(default_factory=list)
    analyses: list[Analysis] = Field(default_factory=list)
    sweep: Sweep = Field(default_factory=Sweep)
    params: dict[str, str] = Field(default_factory=dict)  # .param name = value
    temperature: str = "27"  # °C, .temp
    directives: str = ""  # raw SPICE: .model, .subckt, .options, .ic, unsupported elements
    breadboard: Breadboard | None = None  # the same circuit assembled on a breadboard (Fase 10)
    bench_scope_channels: Literal[0, 2, 4] = 0
    bench_scope_connections: dict[Literal["1", "2", "3", "4"], ScopeConnection] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def _unique_refs(self) -> Schematic:
        seen: set[str] = set()
        for c in self.components:
            key = c.ref.lower()
            if key in seen:
                raise ValueError(f"Designador repetido: {c.ref}")
            seen.add(key)
        return self

    def component(self, ref: str) -> Component:
        for c in self.components:
            if c.ref.lower() == ref.lower():
                return c
        raise KeyError(f"Componente {ref!r} não existe no esquemático")
