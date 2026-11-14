"""AS-SMOKE-01: analytical × ngspice for elementary RC circuits.

Expected values come from circuit theory (voltage divider, first-order step response and
first-order low-pass), not from a book example. Tolerance: 0,5 %.
"""

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.simulation.backend import make_backend

pytestmark = pytest.mark.ngspice

R, C = 1e3, 1e-6
TAU = R * C
TOL = 5e-3

NETLIST = f"""AS-SMOKE-01
V1 in 0 PULSE(0 1 0 1n 1n 50m 100m) AC 1
R1 in out {R}
C1 out 0 {C}
VD a 0 10
RD1 a b 1k
RD2 b 0 2k
.op
.tran 1u 5m 0 1u
.ac dec 100 1 100k
"""


@pytest.fixture(scope="module")
def result():
    return make_backend().run(NETLIST)


def test_divider_operating_point(result):
    assert result.plot("op")["v(b)"].quantity().m_as("V") == pytest.approx(10 * 2 / 3, rel=TOL)


def test_step_response(result):
    tran = result.plot("tran")
    t = tran["time"].quantity().m_as("s")
    v = tran["v(out)"].data
    for k in (0.5, 1, 2, 3):
        expected = 1 - np.exp(-k)
        assert np.interp(k * TAU, t, v) == pytest.approx(expected, rel=TOL)


def test_lowpass_cutoff(result):
    ac = result.plot("ac")
    f = ac["frequency"].data
    h = ac["v(out)"].data
    fc = 1 / (2 * np.pi * TAU)
    assert np.interp(fc, f, np.abs(h)) == pytest.approx(1 / np.sqrt(2), rel=TOL)
    assert np.interp(fc, f, np.degrees(np.angle(h))) == pytest.approx(-45, rel=TOL)
    # −3 dB frequency located from the simulated curve
    f3 = np.interp(-1 / np.sqrt(2), -np.abs(h), f)
    assert q(f3, "Hz").m_as("Hz") == pytest.approx(fc, rel=TOL)
