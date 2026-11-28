"""Potentiometers, trimpots and the 555 on the breadboard (pinouts from Bourns and TI).

Bourns 3386 (p. 2), 3362 (p. 1), 3296 (p. 1), PTV09 (p. 1-2) and PDB18 (p. 1): terminal 1 is
the counter-clockwise end, 2 the wiper, 3 the clockwise end. TI NE555 (SLFS022K, table 4-1):
1 GND, 2 TRIG, 3 OUT, 4 RESET, 5 CONT, 6 THRES, 7 DISCH, 8 VCC.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from circuitos.breadboard.packages import PACKAGES
from circuitos.breadboard.pinout import resolve
from circuitos.components.repository import load_record_file
from circuitos.schematic.cosim_symbols import symbol_takes
from circuitos.schematic.library import SYMBOLS
from circuitos.schematic.model import Component

DATA = Path(__file__).resolve().parents[4] / "data" / "components"


def _comp(kind: str) -> Component:
    return Component(id="1", kind=kind, ref="X1", x=0, y=0)


@pytest.mark.parametrize(
    ("kind", "package", "reference"),
    [("potentiometer", "pot-9mm", "PTV09A"), ("trimpot", "trimpot-3386p", "3386P")],
)
def test_generic_pot_is_drawn_as_a_real_reference_part(kind, package, reference):
    r = resolve(_comp(kind), None)
    assert r.package == package and r.origin == "generico"
    assert r.pinmap == {"1": "a", "2": "w", "3": "b"}
    assert any(reference in n for n in r.notes)


def test_potentiometer_sits_with_the_passives():
    assert SYMBOLS["potentiometer"].group == "Passivos"
    assert SYMBOLS["trimpot"].group == "Passivos"
    assert SYMBOLS["trimpot"].catalogue == ("resistor.variable",)


@pytest.mark.parametrize(
    ("rel", "package", "trimpot"),
    [
        ("resistor/bourns-3386p-1-103lf.yaml", "trimpot-3386p", True),
        ("resistor/bourns-3362p-1-103lf.yaml", "trimpot-3362p", True),
        ("resistor/bourns-3296w-1-103lf.yaml", "trimpot-3296w", True),
        ("resistor/bourns-ptv09a-4020f-b103.yaml", "pot-9mm", False),
        ("resistor/bourns-pdb181-k420k-503b.yaml", "pot-17mm", False),
    ],
)
def test_catalogue_pots_bring_their_pinout(rel, package, trimpot):
    rec = load_record_file(DATA / rel)
    assert rec.pinout is not None and rec.pinout.package == package
    assert package in PACKAGES
    kind = "trimpot" if trimpot else "potentiometer"
    assert symbol_takes(kind, rec) and not symbol_takes(
        "potentiometer" if trimpot else "trimpot", rec
    )
    r = resolve(_comp(kind), rec)
    assert r.origin == "datasheet" and r.pinmap == {"1": "a", "2": "w", "3": "b"}


def test_555_pins_follow_the_ti_table():
    rec = load_record_file(DATA / "timer" / "ti-ne555.yaml")
    r = resolve(_comp("timer555"), rec)
    assert r.origin == "datasheet" and r.package == "dip-8"
    assert r.pinmap == {
        "1": "GND",
        "2": "TRIG",
        "3": "OUT",
        "4": "RESET",
        "5": "CONT",
        "6": "THRES",
        "7": "DISCH",
        "8": "VCC",
    }
    generic = resolve(_comp("timer555"), None)
    assert generic.pinmap == r.pinmap and generic.package == "dip-8"
