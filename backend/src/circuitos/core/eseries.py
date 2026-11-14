"""Preferred number series E3–E192 (IEC 60063).

E3–E24 are tabulated because their historical values deviate from the rounded geometric series
(e.g. 2,7; 3,3; 4,7 in E24). E48–E192 follow ``round(10**(i/n), 2)`` with the single documented
exception 9,20 in E192 (the geometric value rounds to 9,19).
"""

from __future__ import annotations

import bisect
import math
from typing import Literal

import pint

from circuitos.core.errors import UnitError
from circuitos.core.units import Q_

SeriesName = Literal["E3", "E6", "E12", "E24", "E48", "E96", "E192"]

_E24 = (
    1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
    3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
)  # fmt: skip
_E12 = _E24[::2]
_E6 = _E24[::4]
_E3 = (1.0, 2.2, 4.7)

TOLERANCE = {"E3": 0.40, "E6": 0.20, "E12": 0.10, "E24": 0.05, "E48": 0.02, "E96": 0.01,
             "E192": 0.005}  # fmt: skip


def _geometric(n: int) -> tuple[float, ...]:
    values = [round(10 ** (i / n), 2) for i in range(n)]
    if n == 192:
        values[values.index(9.19)] = 9.20
    return tuple(values)


_SERIES: dict[str, tuple[float, ...]] = {
    "E3": _E3,
    "E6": _E6,
    "E12": _E12,
    "E24": _E24,
    "E48": _geometric(48),
    "E96": _geometric(96),
    "E192": _geometric(192),
}


def series(name: SeriesName) -> tuple[float, ...]:
    """Mantissas of one decade, in [1, 10)."""
    try:
        return _SERIES[name]
    except KeyError as exc:
        raise ValueError(f"Série desconhecida: {name}") from exc


def _candidates(value: float, name: SeriesName) -> list[float]:
    decade = math.floor(math.log10(value))
    base = series(name)
    out: list[float] = []
    for d in (decade - 1, decade, decade + 1):
        out.extend(m * 10.0**d for m in base)
    return sorted(out)


def _snap(value: float, name: SeriesName, mode: Literal["nearest", "up", "down"]) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Valores de série E devem ser positivos e finitos")
    cands = _candidates(value, name)
    rel = 1e-9
    if mode == "up":
        return cands[bisect.bisect_left(cands, value * (1 - rel))]
    if mode == "down":
        return cands[bisect.bisect_right(cands, value * (1 + rel)) - 1]
    # Nearest in the logarithmic sense, which is how the series is constructed.
    return min(cands, key=lambda c: abs(math.log(c / value)))


def snap(
    quantity: pint.Quantity,
    name: SeriesName = "E24",
    mode: Literal["nearest", "up", "down"] = "nearest",
) -> pint.Quantity:
    """Round a quantity to the series, keeping its unit (``4.6 kΩ → 4.7 kΩ`` in E24)."""
    if not isinstance(quantity, pint.Quantity):
        raise UnitError("snap exige uma grandeza com unidade")
    magnitude = float(quantity.magnitude)
    snapped = _snap(magnitude, name, mode)
    # Clean floating noise such as 4.7000000000000001e3.
    digits = 3 if name in ("E48", "E96", "E192") else 2
    exponent = math.floor(math.log10(snapped))
    snapped = round(snapped, -exponent + digits - 1)
    return Q_(snapped, quantity.units)
