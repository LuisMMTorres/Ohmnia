"""Assembly on the breadboard: where each leg of each part goes, and the jumper wires.

Stored inside the schematic document (``Schematic.breadboard``), so both views are one circuit.
Legs are explicit holes: the editor may bend axial legs to any span, so the shape is not
derived from the package alone.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from circuitos.breadboard import board

WireColor = Literal["vermelho", "preto", "azul", "verde", "amarelo", "laranja", "branco", "cinza"]


def _hole(v: str) -> str:
    board.parse(v)  # raises HoleError (a ValueError) with a message in Portuguese
    return v.strip().lower()


class PlacedPart(BaseModel):
    ref: str  # schematic designator; "ALIM" for the implicit bench supply of the ICs
    package: str
    legs: dict[str, str] = Field(default_factory=dict)  # package pin (or terminal) -> hole

    @field_validator("legs")
    @classmethod
    def _holes(cls, v: dict[str, str]) -> dict[str, str]:
        return {pin: _hole(h) for pin, h in v.items()}


class Jumper(BaseModel):
    id: str
    a: str
    b: str
    color: WireColor = "verde"

    @field_validator("a", "b")
    @classmethod
    def _holes(cls, v: str) -> str:
        return _hole(v)


class Breadboard(BaseModel):
    board: Literal["830"] = "830"
    rails_split: bool = False
    parts: list[PlacedPart] = Field(default_factory=list)
    wires: list[Jumper] = Field(default_factory=list)

    def part(self, ref: str) -> PlacedPart | None:
        for p in self.parts:
            if p.ref.lower() == ref.lower():
                return p
        return None
