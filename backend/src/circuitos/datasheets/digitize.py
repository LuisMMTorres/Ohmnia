"""Curve digitising: from positions on a datasheet figure to (x, y) values.

All positions are in PDF points of the page (origin top-left, y downwards), the same frame
PyMuPDF and the page images use, so the result does not depend on the zoom the user worked at.

Three ways to obtain the positions, from best to worst:

* ``vector_paths``: most datasheets draw their graphs as vector paths. The path's own vertices are
  exact; nothing is estimated from pixels.
* ``trace_colour``: for scanned pages, columns of the rendered image are scanned for pixels of
  the curve's colour; the vertical centre of those pixels is the curve.
* manual clicks (the front end sends them as positions).

The axis calibration (two reference ticks per axis, linear or logarithmic) maps positions to
values. Errors of the calibration move every point, so the result keeps the calibration with the
curve's source for review.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pymupdf
from pydantic import BaseModel, Field, model_validator

from circuitos.components.models import AxisScale
from circuitos.core.errors import DataIntegrityError

Point = tuple[float, float]


class AxisCalibration(BaseModel):
    """Two reference positions on one axis (PDF points) with their values."""

    p1: float
    v1: float
    p2: float
    v2: float
    scale: AxisScale = "lin"

    @model_validator(mode="after")
    def _check(self) -> AxisCalibration:
        if math.isclose(self.p1, self.p2, abs_tol=1e-6):
            raise ValueError("As duas marcas de calibração do eixo estão na mesma posição")
        if math.isclose(self.v1, self.v2):
            raise ValueError("As duas marcas de calibração do eixo têm o mesmo valor")
        if self.scale == "log" and (self.v1 <= 0 or self.v2 <= 0):
            raise ValueError("Eixo logarítmico exige valores de calibração positivos")
        return self

    def value(self, position: float) -> float:
        t = (position - self.p1) / (self.p2 - self.p1)
        if self.scale == "log":
            a, b = math.log10(self.v1), math.log10(self.v2)
            return float(10 ** (a + t * (b - a)))
        return self.v1 + t * (self.v2 - self.v1)

    def position(self, value: float) -> float:
        if self.scale == "log":
            a, b = math.log10(self.v1), math.log10(self.v2)
            t = (math.log10(value) - a) / (b - a)
        else:
            t = (value - self.v1) / (self.v2 - self.v1)
        return self.p1 + t * (self.p2 - self.p1)


class Calibration(BaseModel):
    """``x`` calibrated on horizontal positions, ``y`` on vertical ones."""

    x: AxisCalibration
    y: AxisCalibration

    def to_values(self, positions: list[Point]) -> list[Point]:
        out = [(self.x.value(px), self.y.value(py)) for px, py in positions]
        return sorted(out, key=lambda p: p[0])


class Rect(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _ordered(self) -> Rect:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("Retângulo vazio")
        return self

    def contains(self, x: float, y: float, margin: float = 0.5) -> bool:
        return (
            self.x0 - margin <= x <= self.x1 + margin and self.y0 - margin <= y <= self.y1 + margin
        )


class VectorPath(BaseModel):
    """A stroked path inside the plot area, as drawn in the PDF."""

    index: int
    colour: tuple[float, float, float] | None
    width: float | None
    points: list[Point] = Field(min_length=2)
    bbox: tuple[float, float, float, float]


def _is_axis_or_grid(points: list[Point], rect: Rect) -> bool:
    """Straight horizontal/vertical segments spanning the plot are axes or grid lines."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    flat = max(ys) - min(ys) < 0.5 or max(xs) - min(xs) < 0.5
    return flat and len(points) <= 4


def vector_paths(page: pymupdf.Page, rect: Rect, min_points: int = 4) -> list[VectorPath]:
    """Stroked paths whose vertices lie in ``rect``: the candidate curves of a vector figure."""
    out: list[VectorPath] = []
    for i, drawing in enumerate(page.get_drawings()):
        if drawing.get("color") is None:  # filled shapes only (legend boxes, markers)
            continue
        pts: list[Point] = []
        for item in drawing["items"]:
            kind = item[0]
            if kind == "l":
                a, b = item[1], item[2]
                pts.extend([(a.x, a.y), (b.x, b.y)])
            elif kind == "c":  # Bézier: keep the end points and the curve's midpoint
                p0, c1, c2, p3 = item[1], item[2], item[3], item[4]
                mx = 0.125 * p0.x + 0.375 * c1.x + 0.375 * c2.x + 0.125 * p3.x
                my = 0.125 * p0.y + 0.375 * c1.y + 0.375 * c2.y + 0.125 * p3.y
                pts.extend([(p0.x, p0.y), (mx, my), (p3.x, p3.y)])
        inside = [p for p in pts if rect.contains(*p)]
        # drop consecutive duplicates (end of one segment = start of the next)
        clean: list[Point] = []
        for p in inside:
            if not clean or abs(p[0] - clean[-1][0]) > 1e-3 or abs(p[1] - clean[-1][1]) > 1e-3:
                clean.append(p)
        if len(clean) < min_points or _is_axis_or_grid(clean, rect):
            continue
        xs = [p[0] for p in clean]
        ys = [p[1] for p in clean]
        colour = drawing.get("color")
        out.append(
            VectorPath(
                index=i,
                colour=(colour[0], colour[1], colour[2]) if colour else None,
                width=drawing.get("width"),
                points=clean,
                bbox=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    return out


def trace_colour(
    page: pymupdf.Page,
    rect: Rect,
    colour: tuple[int, int, int],
    tolerance: int = 60,
    zoom: float = 4.0,
    columns: int = 60,
) -> list[Point]:
    """Positions (PDF points) of a curve of ``colour`` (0–255 RGB), one per sampled column."""
    clip = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]
    distance = np.abs(img.astype(int) - np.asarray(colour, dtype=int)).sum(axis=2)
    mask = distance <= tolerance
    out: list[Point] = []
    step = max(1, pix.width // columns)
    for col in range(0, pix.width, step):
        rows = np.flatnonzero(mask[:, col])
        if rows.size == 0:
            continue
        # several separate runs in one column (another curve of the same colour, a label):
        # keep the largest run
        runs = np.split(rows, np.flatnonzero(np.diff(rows) > 2) + 1)
        best = max(runs, key=len)
        y = float(np.mean(best))
        out.append((rect.x0 + (col + 0.5) / zoom, rect.y0 + (y + 0.5) / zoom))
    return out


def open_page(path: Path, page: int) -> tuple[pymupdf.Document, pymupdf.Page]:
    doc = pymupdf.open(path)
    if not 1 <= page <= doc.page_count:
        doc.close()
        raise DataIntegrityError(f"Página {page} fora do documento (1–{doc.page_count})")
    return doc, doc[page - 1]


__all__ = [
    "AxisCalibration",
    "Calibration",
    "Point",
    "Rect",
    "VectorPath",
    "open_page",
    "trace_colour",
    "vector_paths",
]
