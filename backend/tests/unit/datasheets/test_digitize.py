"""Curve digitising on a synthetic figure with a known function (no real datasheet data).

Figure: x linear 0–1,2 V over 100–400 pt; y logarithmic 1 mA–10 A over 400–100 pt (y grows
upwards). Curve: I = 1e-9·exp(V/0,05) A, drawn as a red polyline over the range where it is
inside the plot.
"""

from __future__ import annotations

import math

import numpy as np
import pymupdf
import pytest
from hypothesis import given
from hypothesis import strategies as st

from circuitos.datasheets.digitize import (
    AxisCalibration,
    Calibration,
    Rect,
    trace_colour,
    vector_paths,
)

X0, X1, Y_BOTTOM, Y_TOP = 100.0, 400.0, 400.0, 100.0
CAL = Calibration(
    x=AxisCalibration(p1=X0, v1=0.0, p2=X1, v2=1.2, scale="lin"),
    y=AxisCalibration(p1=Y_BOTTOM, v1=1e-3, p2=Y_TOP, v2=10.0, scale="log"),
)
PLOT = Rect(x0=X0, y0=Y_TOP, x1=X1, y1=Y_BOTTOM)


def law(v: float) -> float:
    return 1e-9 * math.exp(v / 0.05)


def _figure() -> pymupdf.Document:
    doc = pymupdf.open()
    page = doc.new_page()
    # axes and a grid line (must be ignored by vector_paths)
    page.draw_line((X0, Y_BOTTOM), (X1, Y_BOTTOM), color=(0, 0, 0))
    page.draw_line((X0, Y_BOTTOM), (X0, Y_TOP), color=(0, 0, 0))
    page.draw_line((X0, 250), (X1, 250), color=(0.7, 0.7, 0.7))
    pts = []
    for v in np.linspace(0.0, 1.2, 200):
        i = law(float(v))
        if 1e-3 <= i <= 10:
            pts.append(pymupdf.Point(CAL.x.position(float(v)), CAL.y.position(i)))
    page.draw_polyline(pts, color=(1, 0, 0), width=1.2)
    return doc


@given(
    p1=st.floats(0, 500),
    span=st.floats(10, 500),
    v1=st.floats(1e-6, 1e3),
    ratio=st.floats(1.5, 1e6),
    t=st.floats(0, 1),
    log=st.booleans(),
)
def test_calibration_round_trip(
    p1: float, span: float, v1: float, ratio: float, t: float, log: bool
) -> None:
    axis = AxisCalibration(p1=p1, v1=v1, p2=p1 + span, v2=v1 * ratio, scale="log" if log else "lin")
    pos = p1 + t * span
    assert axis.position(axis.value(pos)) == pytest.approx(pos, abs=1e-6)


def test_bad_calibration_is_rejected() -> None:
    with pytest.raises(ValueError):
        AxisCalibration(p1=1, v1=0, p2=1, v2=5)
    with pytest.raises(ValueError):
        AxisCalibration(p1=1, v1=0, p2=9, v2=5, scale="log")


def test_vector_path_recovers_the_function() -> None:
    doc = _figure()
    paths = vector_paths(doc[0], PLOT)
    red = [p for p in paths if p.colour == (1.0, 0.0, 0.0)]
    assert len(red) == 1, [p.colour for p in paths]
    values = CAL.to_values(red[0].points)
    errors = [abs(i / law(v) - 1) for v, i in values]
    assert max(errors) < 1e-3  # exact vertices: only float rounding of the PDF coordinates


def test_colour_trace_follows_the_function() -> None:
    doc = _figure()
    positions = trace_colour(doc[0], PLOT, (255, 0, 0), columns=80)
    values = CAL.to_values(positions)
    assert len(values) >= 15  # the curve covers about a quarter of the plot width
    # one pixel at zoom 4 is 0,25 pt; on a 3-decade axis over 300 pt that is ~0,6 % in I
    errors = [abs(i / law(v) - 1) for v, i in values]
    assert np.median(errors) < 0.02
    assert max(errors) < 0.08
