"""AS-TBJ-01 and AS-FET-01: bench transistor models × ngspice DC sweeps.

AS-TBJ-01: IC(VCE) at constant IB (10 µA and 30 µA), VCE from 0 to 10 V, 27 °C. Tolerance 0,1 %
of IC where IC > 1 µA (plus 1 nA absolute for GMIN).
AS-FET-01: ID(VDS) for VGS = 4, 5 and 6 V (level 1), VDS from 0 to 10 V. Tolerance 0,1 % (1 nA
absolute).
"""

import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.bjt import BjtModel, output_characteristic
from circuitos.devices.mosfet import MosfetModel, drain_current
from circuitos.simulation.backend import make_backend

pytestmark = pytest.mark.ngspice

BJT = BjtModel(IS=q(1e-14, "A"), BF=200, BR=2, VAF=q(80, "V"))
FET = MosfetModel(VTO=q(3.0, "V"), KP=q(2.0, "A/V**2"), LAMBDA=q(0.01, "1/V"))


@pytest.mark.parametrize("ib_ua", [10, 30])
def test_bjt_output_matches_ngspice(ib_ua):
    netlist = f"""AS-TBJ-01
{BJT.spice()}
IB 0 b DC {ib_ua}u
VCE c 0 DC 0
Q1 c b 0 QMOD
.options temp=27
.dc VCE 0 10 10m
"""
    plot = make_backend().run(netlist).plot("dc")
    v = np.real(plot.vectors[plot.scale].data)
    ic_sim = -np.real(plot["i(vce)"].data)
    ic_model = output_characteristic(BJT, q(ib_ua, "uA"), q(v, "V"), q(27, "degC"))[0].m_as("A")
    np.testing.assert_allclose(ic_model, ic_sim, rtol=1e-3, atol=1e-9)


@pytest.mark.parametrize("vgs", [4, 5, 6])
def test_mosfet_output_matches_ngspice(vgs):
    netlist = f"""AS-FET-01
{FET.spice()}
VGS g 0 DC {vgs}
VDS d 0 DC 0
M1 d g 0 0 MMOD W=100u L=100u
.dc VDS 0 10 10m
"""
    plot = make_backend().run(netlist).plot("dc")
    v = np.real(plot.vectors[plot.scale].data)
    id_sim = -np.real(plot["i(vds)"].data)
    id_model = drain_current(FET, q(vgs, "V"), q(v, "V")).m_as("A")
    np.testing.assert_allclose(id_model, id_sim, rtol=1e-3, atol=1e-9)
