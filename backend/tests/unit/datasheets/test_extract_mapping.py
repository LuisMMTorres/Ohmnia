"""Extraction (text rows, OCR) and rule-based mapping on synthetic datasheets."""

from __future__ import annotations

import pymupdf
import pytest

from circuitos.datasheets.extract import extract_document, ocr_available
from circuitos.datasheets.mapping import Candidate, map_document, normalise_symbol, rank_categories
from circuitos.datasheets.textvalues import (
    compatible,
    number_with_unit,
    parse_range,
    unit_from_text,
)

from .synthetic import family_pdf, rectifier_pdf, scanned_pdf


def _doc(data: bytes, **kw: object):
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        return extract_document(pdf, **kw)  # type: ignore[arg-type]


def _best(cands: list[Candidate], key: str) -> Candidate:
    accepted = [c for c in cands if c.key == key and c.accepted]
    assert accepted, f"{key} não encontrado: {[c.key for c in cands]}"
    return accepted[0]


# ------------------------------------------------------------------------------ text values --


@pytest.mark.parametrize(
    ("text", "unit"),
    [
        ("V", "V"),
        ("µA", "uA"),
        ("uA", "uA"),
        ("mΩ", "mohm"),
        ("Ω", "ohm"),
        ("°C", "degC"),
        ("°C/W", "K/W"),
        ("mW/°C", "mW/K"),
        ("A2s", "A**2*s"),
        ("nC", "nC"),
        ("V/ns", "V/ns"),
        ("MHz", "MHz"),
    ],
)
def test_unit_from_text(text: str, unit: str) -> None:
    assert unit_from_text(text) == unit


@pytest.mark.parametrize("text", ["max", "Tj", "at", "Symbol", "IF", "Test", "=", ""])
def test_unit_from_text_rejects_words(text: str) -> None:
    assert unit_from_text(text) is None


def test_numbers_and_ranges() -> None:
    tok = number_with_unit("±20V")
    assert tok is not None and tok.value == 20 and tok.unit == "V" and tok.symmetric
    tok = number_with_unit("−0,5")
    assert tok is not None and tok.value == -0.5 and tok.unit is None
    assert parse_range("-55 to +150") == (-55, 150)
    assert parse_range("−65 … +175 °C") == (-65, 175)
    assert parse_range("150") is None


def test_compatible_units() -> None:
    assert compatible("mA", "A")
    assert compatible("K/W", "K/W")
    assert not compatible("V", "A")
    assert not compatible("degC", "K")


def test_symbol_normalisation() -> None:
    assert normalise_symbol("V RRM") == normalise_symbol("VRRM")
    assert normalise_symbol("RθJA") == normalise_symbol("RthJA")


# ------------------------------------------------------------------------------- extraction --


def test_rows_keep_table_lines_together() -> None:
    doc = _doc(rectifier_pdf())
    texts = [r.text for r in doc.page(1).rows]
    assert any("Forward voltage" in t and "1.1" in t for t in texts)
    assert doc.ocr_pages == []


def test_scanned_page_is_reported_without_ocr() -> None:
    doc = _doc(scanned_pdf(), ocr="never")
    assert doc.page(1).rows == []


@pytest.mark.skipif(not ocr_available(), reason="Tesseract (tessdata) não instalado")
def test_scanned_page_goes_through_ocr() -> None:
    doc = _doc(scanned_pdf())
    assert doc.ocr_pages == [1]
    cands = map_document(doc, "diode.rectifier")
    vrrm = _best(cands, "VRRM")
    assert vrrm.max == 800 and vrrm.unit == "V"
    assert any("OCR" in n for n in vrrm.notes)


# ---------------------------------------------------------------------------------- mapping --


@pytest.fixture(scope="module")
def rectifier() -> list[Candidate]:
    return map_document(_doc(rectifier_pdf()), "diode.rectifier")


def test_ratings_from_value_column(rectifier: list[Candidate]) -> None:
    vrrm = _best(rectifier, "VRRM")
    assert (vrrm.min, vrrm.typ, vrrm.max, vrrm.unit) == (None, None, 800, "V")
    assert vrrm.page == 1 and vrrm.bbox is not None
    assert "Peak repetitive reverse voltage" in vrrm.excerpt
    ifav = _best(rectifier, "IF(AV)")
    assert ifav.max == 2.0 and ifav.conditions["TA"].value == 75
    assert ifav.conditions["TA"].unit == "degC"
    ifsm = _best(rectifier, "IFSM")
    assert ifsm.max == 60 and ifsm.conditions["t_pulse"].value == pytest.approx(8.3)


def test_range_gives_both_temperature_limits(rectifier: list[Candidate]) -> None:
    assert _best(rectifier, "Tj_max").max == 150
    assert _best(rectifier, "Tj_min").min == -55


def test_characteristics_use_min_typ_max_columns(rectifier: list[Candidate]) -> None:
    vf = _best(rectifier, "VF")
    assert (vf.min, vf.typ, vf.max) == (None, 0.95, 1.1)
    assert vf.conditions["IF"].value == 2.0 and vf.conditions["Tj"].value == 25
    ir = _best(rectifier, "IR")
    assert ir.max == 5.0 and ir.unit == "uA"
    assert ir.conditions["VR"].value == 800
    rth = _best(rectifier, "Rth_ja")
    assert rth.typ == 50 and rth.unit == "K/W"


def test_conditions_are_not_taken_as_parameters(rectifier: list[Candidate]) -> None:
    # "IF = 2.0 A" on the VF row must not produce an IF candidate
    assert not any(c.key == "IF" for c in rectifier)


def test_one_accepted_candidate_per_key(rectifier: list[Candidate]) -> None:
    keys = [c.key for c in rectifier if c.accepted]
    assert len(keys) == len(set(keys))


def test_family_table_uses_the_part_column() -> None:
    doc = _doc(family_pdf())
    cands = map_document(doc, "diode.rectifier", part_number="TESTE-D2")
    vrrm = _best(cands, "VRRM")
    assert vrrm.max == 200
    assert any("coluna do part number" in n for n in vrrm.notes)


def test_category_ranking() -> None:
    ranking = rank_categories(_doc(rectifier_pdf()))
    assert ranking[0].category == "diode.rectifier"
    assert "VRRM" in ranking[0].found


def test_part_number_in_title_is_not_a_family_column() -> None:
    cands = map_document(_doc(rectifier_pdf()), "diode.rectifier", part_number="TESTE-D1")
    vrrm = _best(cands, "VRRM")
    assert vrrm.max == 800
    assert not any("coluna do part number" in n for c in cands for n in c.notes)
    vf = _best(cands, "VF")
    assert vf.conditions_text is not None and not vf.conditions_text.split(";")[0].endswith(",")
