"""Numbers, ranges and units as they are printed in datasheets.

Datasheets write units in many ways ("µA", "uA", "mΩ", "°C", "°C/W", "A2s", "V/ns") and use the
typographic minus. This module turns those strings into units ``pint`` understands, so the mapper
(``mapping.py``) can check that a value found next to a symbol has the dimension the category
schema expects. Nothing here decides *which* value belongs to which parameter.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from circuitos.core.errors import UnitError
from circuitos.core.units import Q_, parse_unit

_MINUS = str.maketrans({"−": "-", "–": "-", "—": "-", "‒": "-", "﹣": "-", "－": "-"})

# Exact replacements (keys lower-cased) for unit spellings pint does not read.
_UNIT_EXACT = {
    "°c": "degC",
    "ºc": "degC",
    "℃": "degC",
    "oc": "degC",
    "°c/w": "K/W",
    "ºc/w": "K/W",
    "c/w": "K/W",
    "k/w": "K/W",
    "a2s": "A**2*s",
    "a²s": "A**2*s",
    "a2sec": "A**2*s",
    "sec": "s",
    "msec": "ms",
    "usec": "us",
    "nsec": "ns",
    "%": "percent",
    "mho": "S",
    "mmho": "mS",
}

_BASE_UNITS = ("V", "A", "W", "ohm", "F", "H", "C", "J", "S", "Hz", "s", "K")
_PREFIX = "pnumkMG"
_SIMPLE = re.compile(rf"^[{_PREFIX}]?(?:{'|'.join(_BASE_UNITS)})$")


def normalise_text(text: str) -> str:
    """NFKC, typographic minus to ASCII, µ/μ unified, thin and non-breaking spaces to spaces."""
    text = unicodedata.normalize("NFKC", text).translate(_MINUS)
    return text.replace("μ", "µ").replace(" ", " ").replace(" ", " ")


def unit_from_text(text: str) -> str | None:
    """Unit string accepted by :func:`circuitos.core.units.parse_unit`, or ``None``.

    ``"mΩ"`` → ``"mohm"``, ``"°C/W"`` → ``"K/W"``, ``"mW/°C"`` → ``"mW/K"``, ``"µA"`` → ``"uA"``.
    Only short unit tokens are accepted, so ordinary words ("max", "at", "Tj") are rejected.
    """
    raw = normalise_text(text).strip().strip("()[],;:")
    if not raw or len(raw) > 12:
        return None
    if raw.lower() in _UNIT_EXACT:
        return _UNIT_EXACT[raw.lower()]
    cleaned = raw.replace("µ", "u").replace("Ω", "ohm").replace("Ohm", "ohm").replace(" ", "")
    # NFKC turns "Ω" (U+2126) into "Ω" (U+03A9); both are covered above.
    # A temperature in a denominator is a temperature *difference*: mW/°C ≡ mW/K.
    cleaned = re.sub(r"/[°º]?C$", "/K", cleaned)
    if cleaned.lower() in _UNIT_EXACT:
        return _UNIT_EXACT[cleaned.lower()]
    parts = cleaned.split("/")
    if len(parts) > 2 or not all(_SIMPLE.match(p) for p in parts):
        return None
    try:
        parse_unit(cleaned)
    except UnitError:
        return None
    return cleaned


def compatible(unit: str, expected: str) -> bool:
    """Same physical dimension (``"mA"`` vs ``"A"``). Celsius only matches Celsius."""
    if (unit == "degC") != (expected == "degC"):
        return False
    try:
        a = Q_(1, parse_unit(unit))
        b = Q_(1, parse_unit(expected))
    except UnitError:
        return False
    return bool(a.dimensionality == b.dimensionality)


@dataclass(frozen=True)
class NumberToken:
    value: float
    text: str
    unit: str | None  # unit written together with the number, when there is one
    symmetric: bool = False  # "±20 V"


_NUMBER = re.compile(r"^(?P<sign>[-+±]?)(?P<num>\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)$")
_NUMBER_UNIT = re.compile(r"^(?P<sign>[-+±]?)(?P<num>\d+(?:[.,]\d+)?)\s?(?P<unit>[^\d\s].*)$")
_RANGE = re.compile(
    r"(?P<a>[-+]?\s?\d+(?:[.,]\d+)?)\s*(?:to|a|até|\.\.\.|…|~|-)\s*(?P<b>[-+]?\s?\d+(?:[.,]\d+)?)"
)


def _to_float(sign: str, num: str) -> float:
    value = float(num.replace(",", "."))
    return -value if sign == "-" else value


def number_with_unit(text: str) -> NumberToken | None:
    """``"1.0 V"`` → 1.0 V; ``"±20V"`` → 20 V symmetric; ``"5.0"`` → 5.0 without unit."""
    t = normalise_text(text).strip()
    m = _NUMBER.match(t)
    if m:
        sign = m["sign"]
        return NumberToken(
            value=_to_float("" if sign == "±" else sign, m["num"]),
            text=t,
            unit=None,
            symmetric=sign == "±",
        )
    m = _NUMBER_UNIT.match(t)
    if m:
        unit = unit_from_text(m["unit"])
        if unit is not None:
            sign = m["sign"]
            return NumberToken(
                value=_to_float("" if sign == "±" else sign, m["num"]),
                text=t,
                unit=unit,
                symmetric=sign == "±",
            )
    return None


def parse_range(text: str) -> tuple[float, float] | None:
    """``"-65 to +175"`` → (-65, 175). Only explicit two-number ranges, lower bound first."""
    m = _RANGE.search(normalise_text(text))
    if not m:
        return None
    a = float(m["a"].replace(" ", "").replace(",", "."))
    b = float(m["b"].replace(" ", "").replace(",", "."))
    if a >= b:
        return None
    return a, b


__all__ = [
    "NumberToken",
    "compatible",
    "normalise_text",
    "number_with_unit",
    "parse_range",
    "unit_from_text",
]
