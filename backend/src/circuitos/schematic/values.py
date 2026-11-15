"""SPICE number syntax: ``4k7``-free engineering notation as ngspice reads it.

ngspice suffixes are case-insensitive: ``f p n u m k meg g t`` (``m`` is milli, ``meg`` is
mega) and ``mil``. Letters after the number and suffix (a unit such as ``V`` or ``Ohm``) are
ignored, exactly as ngspice does. A value in braces (``{R0*2}``) is a parameter expression and
is passed to ngspice untouched.
"""

from __future__ import annotations

import math
import re

_SUFFIX = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "meg": 1e6,
    "g": 1e9,
    "t": 1e12,
    "mil": 25.4e-6,
}
_NUMBER = re.compile(
    r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(meg|mil|[fpnuµμmkgt])?([a-zA-ZΩ°%/]*)\s*$",
    re.IGNORECASE,
)


def is_expression(text: str) -> bool:
    s = text.strip()
    return s.startswith("{") and s.endswith("}")


def parse_value(text: str) -> float:
    """Number in SPICE notation; raises ``ValueError`` with a message in Portuguese."""
    m = _NUMBER.match(str(text))
    if m is None:
        raise ValueError(f"Valor inválido: {text!r} (use notação SPICE, ex.: 4.7k, 10u, 1meg)")
    number = float(m.group(1))
    suffix = (m.group(2) or "").lower()
    return number * _SUFFIX.get(suffix, 1.0)


def try_parse(text: str) -> float | None:
    try:
        return parse_value(text)
    except ValueError:
        return None


_ENG = (
    (1e12, "t"),
    (1e9, "g"),
    (1e6, "meg"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "u"),
    (1e-9, "n"),
    (1e-12, "p"),
    (1e-15, "f"),
)


def format_value(x: float, digits: int = 6) -> str:
    """Shortest SPICE-readable form with an engineering suffix (``4.7k``, ``1meg``, ``10u``)."""
    if x == 0 or not math.isfinite(x):
        return f"{x:g}"
    ax = abs(x)
    for scale, suffix in _ENG:
        if ax >= scale * 0.9999999999:
            return f"{x / scale:.{digits}g}{suffix}"
    return f"{x:.{digits}g}"
