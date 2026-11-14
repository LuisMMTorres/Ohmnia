"""Calculation record (memória de cálculo).

Rule 3: every design result is auditable. Calculation functions return :class:`Calculated`, which
pairs the value with a :class:`CalcStep` describing the equation, inputs, assumptions and the
bibliographic reference. Reports and the didactic mode are generated from these steps.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

import pint
from pydantic import BaseModel, ConfigDict, Field

from circuitos.core.errors import UnitError
from circuitos.core.units import QuantityModel


class BibRef(BaseModel):
    """Bibliographic reference of an equation.

    ``verified`` stays ``False`` until someone checks chapter/equation against the printed book.
    """

    model_config = ConfigDict(frozen=True)

    book: str
    edition: str | None = None
    chapter: str | None = None
    equation: str | None = None
    page: str | None = None
    verified: bool = False


class CalcStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    latex: str
    inputs: dict[str, QuantityModel] = Field(default_factory=dict)
    output: QuantityModel
    assumptions: list[str] = Field(default_factory=list)
    reference: BibRef | None = None


@dataclass(frozen=True)
class Calculated[T]:
    value: T
    step: CalcStep


def record(
    id: str,
    description: str,
    latex: str,
    output: pint.Quantity,
    inputs: Mapping[str, pint.Quantity] | None = None,
    assumptions: Iterable[str] = (),
    reference: BibRef | None = None,
) -> Calculated[pint.Quantity]:
    """Build a :class:`Calculated` from pint quantities, enforcing units on every value."""
    if not isinstance(output, pint.Quantity):
        raise UnitError(f"{id}: o resultado deve ter unidade")
    serialised: dict[str, QuantityModel] = {}
    for name, value in (inputs or {}).items():
        if not isinstance(value, pint.Quantity):
            raise UnitError(f"{id}: a entrada {name!r} deve ter unidade")
        serialised[name] = QuantityModel.from_pint(value)
    step = CalcStep(
        id=id,
        description=description,
        latex=latex,
        inputs=serialised,
        output=QuantityModel.from_pint(output),
        assumptions=list(assumptions),
        reference=reference,
    )
    return Calculated(value=output, step=step)


class CalcLog:
    """Ordered collection of steps of one design computation."""

    def __init__(self) -> None:
        self._steps: dict[str, CalcStep] = {}

    def add[T](self, calculated: Calculated[T]) -> T:
        if calculated.step.id in self._steps:
            raise ValueError(f"Passo de cálculo duplicado: {calculated.step.id}")
        self._steps[calculated.step.id] = calculated.step
        return calculated.value

    def __iter__(self) -> Iterator[CalcStep]:
        return iter(self._steps.values())

    def __len__(self) -> int:
        return len(self._steps)

    def __getitem__(self, step_id: str) -> CalcStep:
        return self._steps[step_id]
