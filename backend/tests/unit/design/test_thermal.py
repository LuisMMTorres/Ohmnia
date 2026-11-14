"""Steady-state junction temperature and required heatsink."""

import pytest

from circuitos.core.units import Q_
from circuitos.thermal.steady import junction_temperature, required_heatsink


def test_junction_temperature():
    r = junction_temperature("D1", Q_(1, "W"), Q_(40, "degC"), Q_(50, "K/W"))
    assert r.value.to("degC").magnitude == pytest.approx(90)
    assert r.step.reference is not None


def test_required_heatsink_keeps_margin():
    r = required_heatsink(
        "Q1", Q_(10, "W"), Q_(40, "degC"), Q_(150, "degC"), 15, Q_(1.5, "K/W"), Q_(0.5, "K/W")
    )
    # (150 − 15 − 40)/10 − 1.5 − 0.5 = 7.5 K/W
    assert r.value.m_as("K/W") == pytest.approx(7.5)
