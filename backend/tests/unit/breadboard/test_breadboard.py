"""Breadboard view (Fase 10): board rules, pinouts, automatic assembly and the check."""

from __future__ import annotations

from pathlib import Path

import pytest

from circuitos.breadboard import board
from circuitos.breadboard.autoplace import autoplace
from circuitos.breadboard.check import ERRORS, check
from circuitos.breadboard.guide import guide
from circuitos.breadboard.layout import Breadboard, Jumper, PlacedPart
from circuitos.breadboard.pinout import colour_code, resolve
from circuitos.breadboard.reference import ALIM, build
from circuitos.components.models import ComponentRecord
from circuitos.components.repository import load_records_file
from circuitos.schematic.model import Component

from .circuits import bridge, common_emitter, inverting

DATA = Path(__file__).resolve().parents[4] / "data" / "components"


def _record(rel: str, part: str) -> ComponentRecord:
    return next(r for r in load_records_file(DATA / rel) if r.part_number == part)


def _errors(report):  # type: ignore[no-untyped-def]
    return [i for i in report.issues if i.kind in ERRORS]


# ---------------------------------------------------------------------------- board


def test_strips_rails_and_split():
    assert board.strip("a12") == board.strip("e12") == "12L"
    assert board.strip("f12") == "12R" != board.strip("e12")  # the channel separates halves
    assert board.strip("tn2") == board.strip("tn60") == "tn"
    assert board.strip("tn2", rails_split=True) != board.strip("tn60", rails_split=True)
    assert len(board.RAIL_ROWS) == 50 and 7 not in board.RAIL_ROWS  # gaps between groups of 5
    for bad in ("k3", "a0", "a64", "tn7", "xx"):
        with pytest.raises(board.HoleError):
            board.parse(bad)


@pytest.mark.parametrize(
    ("ohms", "tol", "bands"),
    [
        (4700, "5", ["amarelo", "violeta", "vermelho", "ouro"]),
        (10, None, ["marrom", "preto", "preto"]),
        (0.47, "5", ["amarelo", "violeta", "prata", "ouro"]),
        (4990, "1", ["amarelo", "branco", "branco", "marrom", "marrom"]),
        (1e6, "10", ["marrom", "preto", "verde", "prata"]),
    ],
)
def test_resistor_colour_code(ohms, tol, bands):
    assert colour_code(ohms, tol) == bands


# ---------------------------------------------------------------------------- pinout


def test_generic_parts_are_labelled_and_marked_generic():
    q = resolve(Component(id="1", kind="npn", ref="Q1", x=0, y=0), None)
    assert q.origin == "generico" and q.checkable and q.package == "to-92"
    assert set(q.pinmap.values()) == {"c", "b", "e"}
    assert any("genérica" in n for n in q.notes)
    e = resolve(Component(id="2", kind="vcvs", ref="E1", x=0, y=0), None)
    assert e.origin == "sem_montagem" and not e.checkable


def test_catalogue_pinout_comes_with_page_and_status():
    rec = _record("bjt/onsemi-bc546-bc548.yaml", "BC547B")
    q = resolve(Component(id="1", kind="npn", ref="Q1", x=0, y=0), rec)
    assert q.origin == "datasheet" and q.pinmap == {"1": "c", "2": "b", "3": "e"}
    assert q.source is not None and q.source.page == 7 and q.status == "extraido"
    assert q.datasheet is not None and q.datasheet.document_number == "BC546/D"


def test_dual_op_amp_uses_unit_a_and_supply_pins():
    rec = _record("opamp/ti-lm358.yaml", "LM358P")
    u = resolve(Component(id="1", kind="opamp", ref="U1", x=0, y=0), rec)
    assert u.pinmap == {"1": "out", "2": "inn", "3": "inp", "4": "vee", "8": "vcc"}
    assert u.supplies == {"vcc": 15.0, "vee": -15.0}
    assert any("unidade A" in n for n in u.notes)


def test_part_without_pinout_is_not_guessed():
    rec = _record("diode/onsemi-mbr20100ct.yaml", "MBR20100CTG")
    assert rec.pinout is None
    d = resolve(Component(id="1", kind="diode", ref="D1", x=0, y=0), rec)
    assert d.origin == "sem_pinagem" and not d.checkable and d.pinmap == {}


# ---------------------------------------------------------------------------- assembly


@pytest.mark.parametrize("make", [bridge, common_emitter, inverting])
def test_automatic_assembly_passes_the_check(make):
    ref = build(make(), {})
    bb, notes = autoplace(ref)
    report = check(ref, bb)
    assert report.ok, [i.message for i in report.issues]
    assert not notes
    steps = guide(ref, bb)
    assert steps[-1].text.endswith("fontes.") and len(steps) > len(bb.parts)


def test_ic_supplies_come_from_an_implicit_bench_supply():
    sch = inverting(vee="0")  # single supply: V- goes to ground
    ref = build(sch, {})
    assert ref.nets["U1:4"] == "0" and ref.nets["U1:7"] == "VCC +15 V"
    assert ALIM in ref.parts and set(ref.parts[ALIM].pinmap) == {"0", "+"}
    bb, _ = autoplace(ref)
    assert check(ref, bb).ok


def test_catalogue_parts_assemble_with_their_real_pinout():
    q = _record("bjt/onsemi-p2n2222a.yaml", "P2N2222A")
    u = _record("opamp/ti-lm358.yaml", "LM358P")
    sch_q, sch_u = common_emitter(str(q.id)), inverting(str(u.id))
    for sch, rec, ref_name in ((sch_q, q, "Q1"), (sch_u, u, "U1")):
        ref = build(sch, {ref_name: rec})
        bb, _ = autoplace(ref)
        assert check(ref, bb).ok
    ref = build(sch_q, {"Q1": q})
    assert ref.nets["Q1:1"] == "c" and ref.nets["Q1:3"] == "e"  # C-B-E, from the datasheet


def _assembled():  # type: ignore[no-untyped-def]
    ref = build(common_emitter(), {})
    bb, _ = autoplace(ref)
    return ref, bb


def test_check_finds_swapped_legs():
    ref, bb = _assembled()
    q = bb.part("Q1")
    assert q is not None
    q.legs["1"], q.legs["3"] = q.legs["3"], q.legs["1"]
    errs = _errors(check(ref, bb))
    assert [e.kind for e in errs] == ["trocada"]
    assert "invertidos" in errs[0].message and errs[0].refs == ["Q1"]


def test_check_finds_missing_wire_short_and_unplaced_part():
    ref, bb = _assembled()
    bb.wires.pop()
    assert [e.kind for e in _errors(check(ref, bb))] == ["faltando"]
    ref, bb = _assembled()
    q = bb.part("Q1")
    assert q is not None
    bb.wires.append(Jumper(id="x", a=f"a{q.legs['1'][1:]}", b=f"a{q.legs['3'][1:]}"))
    errs = _errors(check(ref, bb))
    assert any(e.kind == "sobrando" and "Ligação a mais" in e.message for e in errs)
    ref, bb = _assembled()
    bb.parts = [p for p in bb.parts if p.ref != "RE"]
    assert any(e.kind == "nao_montado" and e.refs == ["RE"] for e in _errors(check(ref, bb)))


def test_check_finds_two_things_in_one_hole_and_parts_not_in_the_schematic():
    ref, bb = _assembled()
    hole = bb.parts[0].legs[next(iter(bb.parts[0].legs))]
    bb.wires.append(Jumper(id="y", a=hole, b="j63"))
    bb.parts.append(PlacedPart(ref="R99", package="axial-r", legs={"1": "a60", "2": "a63"}))
    kinds = {e.kind for e in _errors(check(ref, bb))}
    assert {"furo", "fora_do_esquematico"} <= kinds


def test_resistor_legs_can_go_either_way():
    ref, bb = _assembled()
    r = bb.part("R2")
    assert r is not None
    r.legs["1"], r.legs["2"] = r.legs["2"], r.legs["1"]
    assert check(ref, bb).ok


def test_empty_assembly_is_not_ok():
    ref = build(bridge(), {})
    report = check(ref, Breadboard())
    assert not report.ok and report.checked_parts == 0
