"""Base types of the schematic symbol library (shared by the library and the Fase 11 symbols)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ParamType = Literal["number", "text", "choice", "code"]


@dataclass(frozen=True)
class ParamDef:
    name: str
    label: str
    unit: str = ""
    default: str = ""
    type: ParamType = "number"
    choices: tuple[str, ...] = ()
    optional: bool = False
    help: str = ""


@dataclass(frozen=True)
class PinDef:
    name: str
    dx: int
    dy: int


@dataclass(frozen=True)
class Symbol:
    kind: str
    label: str
    group: str
    prefix: str  # SPICE element letter
    pins: tuple[PinDef, ...]
    params: tuple[ParamDef, ...] = ()
    catalogue: tuple[str, ...] = ()  # categories whose parts can be placed with this symbol
    tolerance: str | None = None  # parameter varied by "tol" (Monte Carlo, worst case)
    description: str = ""
    ref_prefix: str = ""  # designator prefix for new parts (default: the SPICE letter)
    extra: dict[str, str] = field(default_factory=dict)

    def param(self, name: str) -> ParamDef:
        for p in self.params:
            if p.name == name:
                return p
        raise KeyError(f"{self.kind}: parâmetro {name!r} inexistente")
