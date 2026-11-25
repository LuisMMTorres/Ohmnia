"""Breadboard view (Fase 10): board rules, pinouts, automatic assembly and the check."""

from __future__ import annotations

from pathlib import Path

import pytest

from circuitos.breadboard import board
from circuitos.breadboard.autoplace import autoplace
from circuitos.breadboard.check import ERRORS, board_nets, check
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


def test_two_boards_and_vertical_bus_require_explicit_jumpers():
    conductor = board.strip
    assert conductor("2:a12") == conductor("2:e12") != conductor("a12")
    assert conductor("2:tp2") != conductor("tp2")
    assert conductor("vp1") == conductor("vp40") != conductor("vn1")
    assert board.strip_holes("2:12L") == [f"2:{c}12" for c in "abcde"]
    bb = Breadboard(wires=[Jumper(id="w1", a="a12", b="vp1"), Jumper(id="w2", a="vp2", b="2:e12")])
    nets = board_nets(bb)
    assert nets.find(conductor("a12")) == nets.find(conductor("2:a12"))
    assert nets.find(conductor("vn1")) != nets.find(conductor("a12"))
    for invalid in ("vp41", "2:vp1", "3:a12"):
        assert not board.valid(invalid)


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
    rec = _record("thyristor/stmicroelectronics-tyn625.yaml", "TYN625")
    assert rec.pinout is None
    d = resolve(Component(id="1", kind="scr", ref="T1", x=0, y=0), rec)
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
    (c1, r1), (_, r3) = board.parse(q.legs["1"]), board.parse(q.legs["3"])
    free = "b" if c1 in board.UPPER else "i"  # same half as the legs: shorts their strips
    bb.wires.append(Jumper(id="x", a=f"2:{free}{r1}", b=f"2:{free}{r3}"))
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


# ---------------------------------------------------------------------------- boards


def test_boards_sit_over_the_channel_with_both_headers():
    from circuitos.breadboard.packages import package
    from circuitos.cosim import examples as ex

    uno, esp = package("board-uno"), package("board-esp32")
    assert len(uno.pins) == 32 and len(esp.pins) == 38
    assert uno.silk[0] == "NC" and uno.silk[-1] == "SCL"  # leg 1 at the left of the lower row
    assert esp.silk[0] == "3V3" and esp.silk[-1] == "GND"
    assert {dc for _, dc in uno.leg_offsets()} == {0, -1}
    for make in (ex.arduino_pwm_temperature, ex.esp32_energy_meter):
        sch = make()
        ref = build(sch, {})
        board_part = next(
            r for r in ref.parts.values() if r.kind in ("arduino_uno", "esp32_devkitc")
        )
        assert board_part.package in ("board-uno", "board-esp32")
        bb, _ = autoplace(ref)
        placed = bb.part(board_part.ref)
        assert placed is not None
        cols = {board.parse(h)[0] for h in placed.legs.values()}
        assert cols == {"c", "h"}
        assert check(ref, bb).ok


def test_board_gnd_pins_are_one_node():
    from circuitos.cosim import examples as ex

    sch = ex.arduino_pwm_temperature()
    ref = build(sch, {})
    uno = next(r for r in ref.parts.values() if r.kind == "arduino_uno")
    gnd = [pin for pin, role in uno.pinmap.items() if role == "GND"]
    assert len(gnd) == 3
    bb, _ = autoplace(ref)
    part = bb.part(uno.ref)
    assert part is not None
    used = [
        w
        for w in bb.wires
        if any(board.strip(h) == board.strip(part.legs[g]) for g in gnd for h in (w.a, w.b))
    ]
    assert used  # the assembly wires one of them
    # moving the ground wire to another GND pin of the board keeps the assembly right
    w = used[0]
    end = "a" if any(board.strip(w.a) == board.strip(part.legs[g]) for g in gnd) else "b"
    hole = getattr(w, end)
    other = next(g for g in gnd if board.strip(part.legs[g]) != board.strip(hole))
    col, row = board.parse(part.legs[other])
    lower = "2:" if part.legs[other].startswith("2:") else ""
    taken = {h for x in bb.wires for h in (x.a, x.b)}
    setattr(
        w,
        end,
        next(
            f"{lower}{c}{row}"
            for c in ("ab" if col == "c" else "ij")
            if f"{lower}{c}{row}" not in taken
        ),
    )
    assert check(ref, bb).ok, [i.message for i in check(ref, bb).issues]


def test_board_gnd_pins_get_no_jumpers_between_them():
    """The GND pins of a development board are joined on the board itself: placing it alone
    must not lay jumpers between them."""
    from tests.unit.schematic.helpers import Builder

    b = Builder("esp32")
    pins = [
        "3V3", "GND", "IO36", "IO39", "IO34", "IO35", "IO32", "IO33", "IO25", "IO26", "IO27",
        "IO14", "IO12", "IO23", "IO22", "IO21", "IO19", "IO18", "IO5", "IO17", "IO16", "IO4",
        "IO2", "IO15", "IO13",
    ]  # fmt: skip
    b.add("esp32_devkitc", "U1", ["0" if p == "GND" else f"n_{p}" for p in pins])
    b.add("ground", "G1", ["0"])
    ref = build(b.sch, {})
    bb, _ = autoplace(ref)
    legs = bb.part("U1").legs  # type: ignore[union-attr]
    board_strips = {board.strip(h) for h in legs.values()}
    # at most the ground strip goes to its rail; no jumper joins two strips of the board
    assert not [w for w in bb.wires if {board.strip(w.a), board.strip(w.b)} <= board_strips]
    assert len(bb.wires) <= 1
    assert check(ref, bb).ok
