"""Synthetic datasheets for the extraction tests.

The parts here (TESTE-D1, TESTE-D2…) are fictitious and so are their values: they exist only to
exercise the parser. They are never loaded into the catalogue (rule 1 is about real parts).
"""

from __future__ import annotations

import pymupdf

# x positions of the columns (PDF points)
COLS = {"param": 40, "symbol": 230, "cond": 290, "min": 420, "typ": 460, "max": 500, "unit": 545}


def _row(page: pymupdf.Page, y: float, cells: dict[str, str], size: float = 9) -> None:
    for col, text in cells.items():
        page.insert_text((COLS[col], y), text, fontsize=size)


def rectifier_pdf() -> bytes:
    """One page: ratings table (Value column) and characteristics table (Min/Typ/Max)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 50), "TESTE-D1  General Purpose Rectifier (ficticio)", fontsize=14)
    page.insert_text((40, 80), "Maximum Ratings", fontsize=11)
    _row(page, 100, {"param": "Parameter", "symbol": "Symbol", "max": "Value", "unit": "Unit"})
    _row(
        page,
        115,
        {"param": "Peak repetitive reverse voltage", "symbol": "V RRM", "max": "800", "unit": "V"},
    )
    _row(
        page,
        130,
        {
            "param": "Average rectified forward current",
            "symbol": "IF(AV)",
            "cond": "TA = 75 °C",
            "max": "2.0",
            "unit": "A",
        },
    )
    _row(
        page,
        145,
        {
            "param": "Peak forward surge current",
            "symbol": "IFSM",
            "cond": "tp = 8.3 ms",
            "max": "60",
            "unit": "A",
        },
    )
    _row(
        page,
        160,
        {
            "param": "Operating junction temperature",
            "symbol": "TJ",
            "max": "-55 to +150",
            "unit": "°C",
        },
    )
    page.insert_text((40, 190), "Electrical Characteristics", fontsize=11)
    _row(
        page,
        210,
        {
            "param": "Parameter",
            "symbol": "Symbol",
            "cond": "Test conditions",
            "min": "Min",
            "typ": "Typ",
            "max": "Max",
            "unit": "Unit",
        },
    )
    _row(
        page,
        225,
        {
            "param": "Forward voltage",
            "symbol": "VF",
            "cond": "IF = 2.0 A, T J = 25 °C",
            "typ": "0.95",
            "max": "1.1",
            "unit": "V",
        },
    )
    _row(
        page,
        240,
        {
            "param": "Reverse current",
            "symbol": "IR",
            "cond": "VR = 800 V, TA = 25 °C",
            "max": "5.0",
            "unit": "µA",
        },
    )
    _row(
        page,
        255,
        {
            "param": "Thermal resistance, junction to ambient",
            "symbol": "RθJA",
            "typ": "50",
            "unit": "°C/W",
        },
    )
    data = doc.tobytes()
    doc.close()
    return bytes(data)


def family_pdf() -> bytes:
    """Family table: one column per part number."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 50), "TESTE-D1 thru TESTE-D3 Rectifiers (ficticio)", fontsize=14)
    y = 100
    xs = {"TESTE-D1": 300, "TESTE-D2": 370, "TESTE-D3": 440}
    page.insert_text((40, y), "Parameter", fontsize=9)
    page.insert_text((230, y), "Symbol", fontsize=9)
    for name, x in xs.items():
        page.insert_text((x, y), name, fontsize=9)
    page.insert_text((520, y), "Unit", fontsize=9)
    y += 15
    page.insert_text((40, y), "Peak repetitive reverse voltage", fontsize=9)
    page.insert_text((230, y), "VRRM", fontsize=9)
    for value, x in zip(("100", "200", "400"), xs.values(), strict=True):
        page.insert_text((x, y), value, fontsize=9)
    page.insert_text((520, y), "V", fontsize=9)
    data = doc.tobytes()
    doc.close()
    return bytes(data)


def scanned_pdf() -> bytes:
    """The rectifier page rasterised: no text layer, needs OCR."""
    src = pymupdf.open(stream=rectifier_pdf(), filetype="pdf")
    pix = src[0].get_pixmap(dpi=200)
    doc = pymupdf.open()
    page = doc.new_page(width=src[0].rect.width, height=src[0].rect.height)
    page.insert_image(page.rect, pixmap=pix)
    data = doc.tobytes()
    doc.close()
    src.close()
    return bytes(data)
