import numpy as np
import pytest

from circuitos.core.units import q
from circuitos.devices.bjt import BjtModel, forward_gain, output_characteristic, output_resistance
from circuitos.devices.mosfet import (
    MosfetModel,
    drain_current,
    fit_to_datasheet,
    saturation_current,
)

BJT = BjtModel(IS=q(1e-14, "A"), BF=200, BR=2, VAF=q(80, "V"))
T = q(27, "degC")


def test_bjt_active_region_gain_and_early_effect():
    ic5, vbe5 = output_characteristic(BJT, q(10, "uA"), q(5, "V"), T)
    ic10, _ = output_characteristic(BJT, q(10, "uA"), q(10, "V"), T)
    # forward active: IC ≈ BF·IB·(1 − VBC/VAF), VBC = VBE − VCE
    early = 1 + (5 - vbe5.m_as("V")) / 80
    assert ic5.m_as("mA") == pytest.approx(2.0 * early, rel=1e-3)
    assert ic10.m_as("A") > ic5.m_as("A")
    beta = forward_gain(BJT, ic5, q(10, "uA")).value.m_as("dimensionless")
    assert beta == pytest.approx(200 * early, rel=1e-3)
    ro = output_resistance(BJT, ic5, q(5, "V")).value.m_as("kohm")
    assert ro == pytest.approx(85 / ic5.m_as("A") / 1e3)


def test_bjt_saturation_at_low_vce():
    ic, vbe = output_characteristic(BJT, q(10, "uA"), q(np.array([0.0, 0.05, 1.0]), "V"), T)
    assert ic.m_as("A")[0] <= 0  # VCE = 0: collector current reverses (BR term)
    assert ic.m_as("A")[1] < ic.m_as("A")[2]
    assert np.all(vbe.m_as("V") > 0.5)


def test_bjt_spice_and_validation():
    assert BJT.spice().startswith(".model QMOD NPN(")
    with pytest.raises(ValueError):
        BjtModel(IS=q(1e-14, "A"), BF=-1, BR=1, VAF=q(50, "V"))


FET = MosfetModel(VTO=q(3, "V"), KP=q(2, "A/V**2"), LAMBDA=q(0.01, "1/V"))


def test_mosfet_regions():
    assert drain_current(FET, q(2, "V"), q(5, "V")).m_as("A") == 0
    sat = drain_current(FET, q(5, "V"), q(5, "V")).m_as("A")
    assert sat == pytest.approx(1.0 * 4 * 1.05)
    tri = drain_current(FET, q(5, "V"), q(1, "V")).m_as("A")
    assert tri == pytest.approx(2 * (2 * 1 - 0.5) * 1.01)
    # continuity at the edge of saturation
    edge = drain_current(FET, q(5, "V"), q(2, "V")).m_as("A")
    assert edge == pytest.approx(1.0 * 4 * 1.02)


def test_mosfet_fit_reproduces_rds_on():
    # synthetic test point (not datasheet data): RDS(on) = 0.05 ohm at VGS = 10 V, VT = 3 V
    model, steps = fit_to_datasheet(q(3, "V"), q(0.05, "ohm"), q(10, "V"), q(0, "1/V"))
    small = drain_current(model, q(10, "V"), q(1e-3, "V")).m_as("A")
    assert 1e-3 / small == pytest.approx(0.05, rel=1e-3)
    assert steps[0].step.id == "KP_fit"
    with pytest.raises(ValueError):
        fit_to_datasheet(q(3, "V"), q(0.05, "ohm"), q(2, "V"), q(0, "1/V"))


def test_mosfet_step_and_validation():
    assert saturation_current(FET, q(6, "V"), q(10, "V")).step.id == "ID_sat"
    assert "LEVEL=1" in FET.spice()
    with pytest.raises(ValueError):
        MosfetModel(VTO=q(3, "V"), KP=q(0, "A/V**2"), LAMBDA=q(0, "1/V"))
