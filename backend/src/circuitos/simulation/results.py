"""Simulation request/result types shared by every backend."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import numpy as np
import pint

from circuitos.core.units import Q_, parse_unit

PlotKind = Literal["op", "tran", "ac", "dc", "noise", "other"]

# ngspice vector type names (rawfile) -> SI unit.
TYPE_UNITS = {
    "time": "s",
    "frequency": "Hz",
    "voltage": "V",
    "current": "A",
    "temperature": "degC",
    "power": "W",
    "impedance": "ohm",
    "admittance": "S",
    "capacitance": "F",
    "charge": "C",
}


def unit_for(type_name: str, vector_name: str) -> str:
    """Unit of a vector from its ngspice type, falling back on naming conventions."""
    unit = TYPE_UNITS.get(type_name.lower())
    if unit:
        return unit
    lname = vector_name.lower()
    if lname in ("onoise_spectrum", "inoise_spectrum"):
        # noise spectral density; input-referred assumes a voltage input source (usual case)
        return "V/Hz^0.5"
    if lname.startswith("i(") or lname.endswith("#branch"):
        return "A"
    if lname.startswith("v("):
        return "V"
    return ""


def canonical_name(vector_name: str, type_name: str) -> str:
    """Same vector names for every backend: ``v(node)`` and ``i(device)``."""
    name = vector_name.lower()
    sweep = re.fullmatch(r"[iv]\((.+-sweep)\)", name)
    if sweep:  # DC sweep scale: rawfile writes "i(i-sweep)", the shared library "i-sweep"
        return sweep.group(1)
    if name.endswith("-sweep"):
        return name
    if name.endswith("#branch"):
        return f"i({name[: -len('#branch')]})"
    if type_name.lower() == "voltage" and not name.startswith(("v(", "vd(")):
        return f"v({name})"
    return name


def kind_for(plot_name: str) -> PlotKind:
    p = plot_name.lower()
    for key, kind in (
        ("tran", "tran"),
        ("ac", "ac"),
        ("op", "op"),
        ("dc", "dc"),
        ("noise", "noise"),
        ("transient", "tran"),
        ("operating", "op"),
    ):
        if p.startswith(key):
            return kind  # type: ignore[return-value]
    return "other"


@dataclass
class Vector:
    name: str
    unit: str
    data: np.ndarray[Any, np.dtype[Any]]  # float64 or complex128

    @property
    def is_complex(self) -> bool:
        return bool(np.iscomplexobj(self.data))

    def quantity(self) -> pint.Quantity:
        return Q_(self.data, parse_unit(self.unit))


@dataclass
class Plot:
    name: str  # "tran1", "ac1", "op1" (shared) or "Transient Analysis" (rawfile)
    kind: PlotKind
    scale: str | None  # name of the independent vector ("time", "frequency"); None for .op
    vectors: dict[str, Vector] = field(default_factory=dict)
    title: str = ""
    run: int = 0  # index of the run in a sweep, Monte Carlo or worst case (0: single run)
    run_label: str = ""
    base: str = ""  # plot name inside its run ("tran1"), equal to ``name`` for a single run

    def __getitem__(self, name: str) -> Vector:
        try:
            return self.vectors[name.lower()]
        except KeyError as exc:
            raise KeyError(
                f"Vetor {name!r} não existe em {self.name}: {sorted(self.vectors)}"
            ) from exc


_KIND_ORDER = {"op": 0, "dc": 1, "tran": 2, "ac": 3, "noise": 4, "other": 5}


@dataclass
class RunInfo:
    index: int
    label: str
    values: dict[str, str] = field(default_factory=dict)  # varied parameter -> value used


@dataclass
class SimulationResult:
    backend: str
    plots: list[Plot]
    log: str = ""
    warnings: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    runs: list[RunInfo] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)  # worst case, Monte Carlo set-up

    def __post_init__(self) -> None:
        # Same order for every backend: .op, .dc, .tran, .ac, ... then by run and name.
        self.plots.sort(key=lambda p: (_KIND_ORDER[p.kind], p.run, p.name))
        for p in self.plots:
            if not p.base:
                p.base = p.name

    def plot(self, kind: PlotKind, index: int = 0) -> Plot:
        matches = [p for p in self.plots if p.kind == kind]
        if len(matches) <= index:
            raise KeyError(f"Sem análise {kind!r} no resultado ({[p.name for p in self.plots]})")
        return matches[index]


class RunPlan(Protocol):
    """Several netlists run in one job (sweeps, Monte Carlo, worst case)."""

    def execute(self, backend: Any, progress: Any) -> SimulationResult: ...


@dataclass(frozen=True)
class SimulationRequest:
    netlist: str
    timeout_s: float = 120.0
    backend: Literal["auto", "shared", "batch"] = "auto"
    plan: RunPlan | None = None  # when given, the worker runs the plan instead of ``netlist``
