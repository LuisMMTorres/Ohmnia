"""AS-PN-01: depletion capacitance of the BD-PN junction × ngspice small-signal AC.

The bench junction is written as a SPICE diode (CJO = Cj0, VJ = V0, M = 0.5); ngspice computes
the capacitance at each reverse bias from an AC analysis at 1 MHz, C = Im(I)/(2πf·V).
Temperature 27 °C (SPICE TNOM, so no temperature scaling). Tolerance 0,1 %.
"""

import math

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.pn import Junction, capacitance, spice
from circuitos.simulation.backend import make_backend

pytestmark = pytest.mark.ngspice

J = Junction(
    NA=q(1e17, "1/cm**3"),
    ND=q(1e16, "1/cm**3"),
    area=q(1e-4, "cm**2"),
    Dn=q(30, "cm**2/s"),
    Dp=q(10, "cm**2/s"),
    Ln=q(10, "um"),
    Lp=q(20, "um"),
)
T = q(27, "degC")


@pytest.mark.parametrize("vr", [0.0, 1.0, 5.0, 20.0])
def test_depletion_capacitance_matches_ngspice(vr):
    netlist = f"""AS-PN-01
{spice(J, T)}
V1 k 0 DC {vr} AC 1
D1 0 k DPN
.options temp=27 tnom=27
.ac lin 1 1meg 1meg
"""
    plot = make_backend().run(netlist).plot("ac")
    i = plot["i(v1)"].data[0]
    c_sim = abs(np.imag(i)) / (2 * math.pi * 1e6)
    c_model = capacitance(J, q(vr, "V"), T).m_as("F")
    assert c_sim == pytest.approx(c_model, rel=1e-3)
