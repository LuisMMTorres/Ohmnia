"""The 830-point solderless breadboard: holes, the strips that connect them, drawing coordinates.

Layout (top view, rows run left to right, 0.1" = one unit):

* 63 rows of terminal strips. In each row, holes ``a``-``e`` (upper half) are one strip and
  ``f``-``j`` (lower half) another; a 0.3" channel separates ``e`` from ``f``, so a DIP
  package straddles it.
* Two power rails above (``tp`` = +, ``tn`` = -) and two below (``bn`` = -, ``bp`` = +), each with
  50 holes in ten groups of five. Rail holes are named after the row they line up with
  (``tp12``). On some boards each rail is cut in the middle (``rails_split``).

Hole names: ``a12`` (row 12, column a) and ``tn20`` (top negative rail at row 20).
"""

from __future__ import annotations

import re

ROWS = 63
UPPER = "abcde"
LOWER = "fghij"
COLUMNS = UPPER + LOWER
RAILS = ("tp", "tn", "bn", "bp")
RAIL_ROWS: tuple[int, ...] = tuple(r for g in range(10) for r in range(2 + 6 * g, 7 + 6 * g))
SPLIT_AFTER = 30  # split rails: rows <= 30 and >= 32 are separate

# vertical drawing position of each column/rail, in 0.1" units from the top rail
Y: dict[str, int] = {
    "tp": 0, "tn": 1,
    "a": 3, "b": 4, "c": 5, "d": 6, "e": 7,
    "f": 10, "g": 11, "h": 12, "i": 13, "j": 14,
    "bn": 16, "bp": 17,
}  # fmt: skip

_MAIN = re.compile(r"^([a-j])(\d{1,2})$")
_RAIL = re.compile(r"^(tp|tn|bn|bp)(\d{1,2})$")


class HoleError(ValueError):
    pass


def parse(hole: str) -> tuple[str, int]:
    """``"c12"`` → ``("c", 12)``, ``"tn20"`` → ``("tn", 20)``; raises :class:`HoleError`."""
    h = hole.strip().lower()
    m = _MAIN.match(h) or _RAIL.match(h)
    if m is None:
        raise HoleError(f"Furo inexistente: {hole!r}")
    col, row = m.group(1), int(m.group(2))
    if col in RAILS:
        if row not in RAIL_ROWS:
            raise HoleError(f"Furo inexistente: {hole!r} (o barramento não tem furo nessa posição)")
    elif not 1 <= row <= ROWS:
        raise HoleError(f"Furo inexistente: {hole!r} (linhas de 1 a {ROWS})")
    return col, row


def valid(hole: str) -> bool:
    try:
        parse(hole)
    except HoleError:
        return False
    return True


def name(col: str, row: int) -> str:
    return f"{col}{row}"


def strip(hole: str, rails_split: bool = False) -> str:
    """Identifier of the conductor a hole belongs to: ``"12L"``, ``"12R"``, ``"tn"``."""
    col, row = parse(hole)
    if col in RAILS:
        if rails_split:
            return f"{col}-{'esq' if row <= SPLIT_AFTER else 'dir'}"
        return col
    return f"{row}{'L' if col in UPPER else 'R'}"


def strip_holes(strip_id: str) -> list[str]:
    """Holes of a terminal strip (rails are not listed: they are long)."""
    row, side = int(strip_id[:-1]), strip_id[-1]
    return [name(c, row) for c in (UPPER if side == "L" else LOWER)]


def half(hole: str) -> str:
    """``"U"`` (upper rails and a-e) or ``"L"`` (f-j and lower rails)."""
    col, _ = parse(hole)
    return "U" if col in UPPER or col in ("tp", "tn") else "L"


def xy(hole: str) -> tuple[int, int]:
    col, row = parse(hole)
    return row, Y[col]


def nearest_rail_row(row: int) -> int:
    return min(RAIL_ROWS, key=lambda r: (abs(r - row), r))


def spec() -> dict[str, object]:
    """Geometry for the editor (same rules as here, so both sides agree)."""
    return {
        "id": "830",
        "label": "Protoboard de 830 pontos",
        "rows": ROWS,
        "upper": UPPER,
        "lower": LOWER,
        "rails": list(RAILS),
        "rail_rows": list(RAIL_ROWS),
        "split_after": SPLIT_AFTER,
        "y": Y,
        "rail_polarity": {"tp": "+", "tn": "-", "bn": "-", "bp": "+"},
    }
