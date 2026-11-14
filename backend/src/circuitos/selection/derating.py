"""Derating policies (decision D4).

The user follows no standard or company manual: the two presets below are the system defaults,
shown in the interface and in reports as "critério de projeto, não normativo", and every factor
can be edited per project.

A factor f on a rating means: rating ≥ f · stress. The Tj margin is in kelvin:
Tj,max − Tj ≥ margin.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Preset = Literal["didatico", "industrial", "personalizado"]

LABEL = "critério de projeto, não normativo"

# Rating key → factor, per category family (the part of the category before the first dot).
_DIDATICO: dict[str, dict[str, float]] = {
    "diode": {"VRRM": 1.5, "IF(AV)": 1.2, "IFSM": 1.0, "Ptot": 1.5, "IZM": 1.2},
    "bjt": {"VCEO": 1.3, "IC": 1.2},
    "regulator": {"VI_max": 1.1, "VIO_max": 1.1, "IO_max": 1.2},
    "bridge": {"VRRM": 1.5, "IF(AV)": 1.2, "IFSM": 1.0},
    "thyristor": {"VDRM": 1.5, "VRRM": 1.5, "IT(AV)": 1.2, "IT(RMS)": 1.2, "ITSM": 1.0},
    "mosfet": {"VDS": 1.3, "ID": 1.2},
    "jfet": {"VDS": 1.3, "Ptot": 1.5},
    "capacitor": {"V_rated": 1.2, "I_ripple": 1.0},
    "resistor": {"P_rated": 1.5},
    "inductor": {"Isat": 1.2},
}
_INDUSTRIAL: dict[str, dict[str, float]] = {
    "diode": {"VRRM": 2.0, "IF(AV)": 1.5, "IFSM": 1.0, "Ptot": 2.0, "IZM": 1.5},
    "bjt": {"VCEO": 1.5, "IC": 1.5},
    "regulator": {"VI_max": 1.2, "VIO_max": 1.2, "IO_max": 1.5},
    "bridge": {"VRRM": 2.0, "IF(AV)": 1.5, "IFSM": 1.0},
    "thyristor": {"VDRM": 2.0, "VRRM": 2.0, "IT(AV)": 1.5, "IT(RMS)": 1.5, "ITSM": 1.0},
    "mosfet": {"VDS": 1.5, "ID": 1.5},
    "jfet": {"VDS": 1.5, "Ptot": 2.0},
    "capacitor": {"V_rated": 1.5, "I_ripple": 1.3},
    "resistor": {"P_rated": 2.0},
    "inductor": {"Isat": 1.3},
}
_TJ_MARGIN = {"didatico": 15.0, "industrial": 25.0}


class DeratingPolicy(BaseModel):
    preset: Preset = "didatico"
    by_family: dict[str, dict[str, float]] = Field(default_factory=lambda: _copy(_DIDATICO))
    tj_margin_K: float = Field(default=15.0, ge=0)

    @classmethod
    def from_preset(cls, preset: Literal["didatico", "industrial"]) -> DeratingPolicy:
        table = _DIDATICO if preset == "didatico" else _INDUSTRIAL
        return cls(preset=preset, by_family=_copy(table), tj_margin_K=_TJ_MARGIN[preset])

    def factor(self, category: str, key: str) -> float:
        """Required factor for a rating; 1.0 (rating ≥ stress) when the policy has none."""
        family = category.split(".", 1)[0]
        return self.by_family.get(family, {}).get(key, 1.0)


def _copy(table: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {k: dict(v) for k, v in table.items()}
