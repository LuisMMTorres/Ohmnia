"""PT-PN-MONOT: the depletion region widens and the capacitance falls as VR grows."""

from hypothesis import given, settings
from hypothesis import strategies as st

from circuitos.core.units import q
from circuitos.devices.pn import Junction, capacitance, depletion_width

doping = st.floats(min_value=1e14, max_value=1e19)
voltage = st.floats(min_value=0, max_value=200)


@settings(max_examples=60, deadline=None)
@given(doping, doping, voltage, voltage)
def test_depletion_monotonic(na, nd, v1, v2):
    j = Junction(
        NA=q(na, "1/cm**3"),
        ND=q(nd, "1/cm**3"),
        area=q(1e-4, "cm**2"),
        Dn=q(30, "cm**2/s"),
        Dp=q(10, "cm**2/s"),
        Ln=q(10, "um"),
        Lp=q(20, "um"),
    )
    lo, hi = sorted((v1, v2))
    t = q(300, "K")
    assert depletion_width(j, q(hi, "V"), t)[0] >= depletion_width(j, q(lo, "V"), t)[0]
    assert capacitance(j, q(hi, "V"), t) <= capacitance(j, q(lo, "V"), t)
