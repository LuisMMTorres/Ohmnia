"""Small schematics for the breadboard tests (generic parts, labels as nets)."""

from __future__ import annotations

from circuitos.schematic.model import Schematic
from tests.unit.schematic.helpers import Builder


def bridge() -> Schematic:
    b = Builder("ponte")
    b.add("vsin", "V1", ["a", "b"], amplitude="17", freq="60")
    b.add("diode", "D1", ["a", "p"])
    b.add("diode", "D2", ["b", "p"])
    b.add("diode", "D3", ["0", "a"])
    b.add("diode", "D4", ["0", "b"])
    b.add("capacitor", "C1", ["p", "0"], value="470u")
    b.add("resistor", "RL", ["p", "0"], value="100")
    return b.sch


def common_emitter(part_id: str | None = None) -> Schematic:
    b = Builder("emissor comum")
    b.add("vdc", "VCC", ["vcc", "0"], dc="12")
    b.add("vsin", "VIN", ["in", "0"], amplitude="0.01", freq="1k")
    b.add("capacitor", "C1", ["in", "b"], value="10u")
    b.add("resistor", "R1", ["vcc", "b"], value="47k")
    b.add("resistor", "R2", ["b", "0"], value="10k")
    b.add("resistor", "RC", ["vcc", "c"], value="4.7k")
    b.add("resistor", "RE", ["e", "0"], value="1k")
    b.add("npn", "Q1", ["c", "b", "e"], part_id=part_id)
    b.add("capacitor", "CE", ["e", "0"], value="100u")
    return b.sch


def inverting(part_id: str | None = None, vee: str = "-15") -> Schematic:
    b = Builder("inversor")
    b.add("vsin", "V1", ["in", "0"], amplitude="1", freq="1k")
    b.add("resistor", "R1", ["in", "m"], value="10k")
    b.add("resistor", "R2", ["m", "out"], value="100k")
    b.add("opamp", "U1", ["m", "0", "out"], part_id=part_id, vcc="15", vee=vee)
    b.add("resistor", "RL", ["out", "0"], value="10k")
    return b.sch
