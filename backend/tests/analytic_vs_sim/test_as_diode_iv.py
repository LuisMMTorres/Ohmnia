"""AS-DIODO-01: bench model (Shockley + Rs + SPICE temperature law) × ngspice DC sweep.

Tolerance 0,1 % in forward voltage, 1 µA to 1 A (linear sweep, 1 mA step) at 27 °C and 100 °C.
"""

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.diode import DiodeModel, forward_voltage
from circuitos.simulation.backend import make_backend

pytestmark = pytest.mark.ngspice

MODEL = DiodeModel(Is=q(10, "nA"), n=1.8, Rs=q(0.05, "ohm"))


@pytest.mark.parametrize("temp_c", [27, 100])
def test_iv_matches_ngspice(temp_c):
    netlist = f"""AS-DIODO-01
{MODEL.spice()}
I1 0 a DC 1m
D1 a 0 DMOD
.options temp={temp_c}
.dc I1 1u 1 1m
"""
    plot = make_backend().run(netlist).plot("dc")
    currents = np.real(plot.vectors[plot.scale].data)
    v_sim = np.real(plot["v(a)"].data)
    v_model = forward_voltage(MODEL, q(currents, "A"), q(temp_c, "degC")).m_as("V")
    np.testing.assert_allclose(v_model, v_sim, rtol=1e-3)
