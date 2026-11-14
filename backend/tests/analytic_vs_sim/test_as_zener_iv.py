"""AS-ZENER-01: Zener bench model × ngspice DC sweep of the same subcircuit.

Reverse voltage swept from 0 to VZ0 + 1 V (1 mV step) at 27 °C and 100 °C. Tolerance: 0,1 % in
current where |IZ| > 1 µA. Below that (leakage of the reverse branch) the tolerance is 10 nA,
because ngspice replaces the exponential by a cubic approximation for strongly reverse-biased
junctions (SPICE3 diode model) and adds GMIN across each junction.
"""

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.diode import DiodeModel
from circuitos.devices.zener import ZenerModel, reverse_current
from circuitos.simulation.backend import make_backend

pytestmark = pytest.mark.ngspice

MODEL = ZenerModel(
    VZ0=q(5.0, "V"),
    Rz=q(2.0, "ohm"),
    Is_r=q(1, "uA"),
    n_r=1.5,
    TC=q(0.03, "percent/K"),
    forward=DiodeModel(Is=q(10, "nA"), n=1.8, Rs=q(0.05, "ohm")),
)


@pytest.mark.parametrize("temp_c", [27, 100])
def test_reverse_iv_matches_ngspice(temp_c):
    vmax = MODEL.vz0_at(q(temp_c, "degC")).m_as("V") + 1.0
    netlist = f"""AS-ZENER-01
{MODEL.spice()}
V1 k 0 DC 0
X1 0 k DZENER
.options temp={temp_c}
.dc V1 0 {vmax:.4f} 1m
"""
    plot = make_backend().run(netlist).plot("dc")
    v = np.real(plot.vectors[plot.scale].data)
    i_sim = -np.real(plot["i(v1)"].data)  # current delivered by V1 into the cathode
    i_model = reverse_current(MODEL, q(v, "V"), q(temp_c, "degC")).m_as("A")
    big = np.abs(i_sim) > 1e-6
    np.testing.assert_allclose(i_model[big], i_sim[big], rtol=1e-3)
    np.testing.assert_allclose(i_model[~big], i_sim[~big], atol=1e-8)
