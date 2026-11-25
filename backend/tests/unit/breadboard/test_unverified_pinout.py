"""Pending pinouts must never become verified automatic connections."""

from pathlib import Path

from circuitos.breadboard.autoplace import autoplace
from circuitos.breadboard.check import check
from circuitos.breadboard.guide import guide
from circuitos.breadboard.pinout import resolve
from circuitos.breadboard.reference import build
from circuitos.components.repository import load_records_file
from circuitos.schematic.model import Component
from tests.unit.schematic.helpers import Builder


def test_unverified_zener_pinout_is_not_used_or_certified():
    path = Path(__file__).parents[4] / "data/components/zener/onsemi-1n5221b-1n5252b.yaml"
    record = next(r for r in load_records_file(path) if r.part_number == "1N5221B")
    assert record.pinout is not None and record.pinout.status == "a_verificar"
    part = resolve(Component(id="z", ref="Z1", kind="zener", x=0, y=0), record)
    assert part.origin == "sem_pinagem"
    assert not part.checkable and not part.pinmap
    b = Builder("Pinagem pendente")
    b.add("vdc", "V1", ["supply", "0"], dc="5")
    b.add("resistor", "R1", ["supply", "out"], value="1k")
    b.add("zener", "Z1", ["0", "out"], part_id=str(record.id))
    ref = build(b.sch, {"Z1": record})
    assembly, _ = autoplace(ref)
    report = check(ref, assembly)
    assert not report.ok
    assert any(i.kind == "sem_pinagem" and "Z1" in i.refs for i in report.issues)
    steps = [s for s in guide(ref, assembly) if "Z1" in s.refs]
    assert steps and all("a verificar" in s.text for s in steps)
    assert all("catodo" not in s.text and "anodo" not in s.text for s in steps)
    assert all(not s.holes for s in steps)
    # Omitting the unresolved part must not turn an incomplete assembly into a success.
    omitted = assembly.model_copy(update={"parts": [p for p in assembly.parts if p.ref != "Z1"]})
    report = check(ref, omitted)
    assert not report.ok
    assert any(i.kind == "sem_pinagem" and "Z1" in i.refs for i in report.issues)
