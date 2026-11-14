"""PT-RET-FP: properties of the rectifier model over random operating points.

- the input power factor is in (0, 1];
- the mean output voltage never exceeds the peak minus the drops;
- energy balance: input power = output power + diode losses (ideal transformer).
"""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from circuitos.design.plugins.ret1 import model as m

topologies = st.sampled_from(["meia_onda", "center_tap", "ponte"])


def _pf(w):
    i = w.i_in - np.mean(w.i_in)
    return float(np.mean(w.vs * i) / (m.rms(w.vs) * m.rms(i)))


@settings(max_examples=40, deadline=None)
@given(
    topo=topologies,
    Vm=st.floats(5, 400),
    VF=st.floats(0, 1.2),
    R=st.floats(1, 1000),
    wrc=st.floats(0.5, 500),
)
def test_pt_ret_fp_cap_filter(topo, Vm, VF, R, wrc):
    f = 60.0
    C = wrc / (2 * np.pi * f * R)
    if m.diodes_in_path(topo) * VF >= 0.5 * Vm:
        return
    w = m.cap_filter(topo, Vm, VF, R, C, f)
    pf = _pf(w)
    assert 0 < pf <= 1 + 1e-9
    assert m.mean(w.vo) <= Vm - m.diodes_in_path(topo) * VF + 1e-9
    # power delivered by the secondary winding(s); center tap: two equal halves
    halves = 2 if topo == "center_tap" else 1
    p_in = halves * float(np.mean(w.vs * w.i_sec))
    p_out = float(np.mean(w.vo * w.i_load))
    p_d = m.diodes_in_path(topo) * VF * m.mean(w.i_load)
    assert abs(p_in - p_out - p_d) <= 5e-3 * p_in


@settings(max_examples=30, deadline=None)
@given(topo=st.sampled_from(["center_tap", "ponte"]), Vm=st.floats(5, 400), k=st.floats(1.2, 10))
def test_pt_ret_fp_lc_filter(topo, Vm, k):
    R, f = 20.0, 60.0
    L = k * m.critical_inductance(R, f)
    w = m.lc_filter(topo, Vm, 0.0, R, L, 50 / ((4 * np.pi * f) ** 2 * L), f)
    assert 0 < _pf(w) <= 1 + 1e-9
    assert _pf(w) <= 0.9 + 1e-3  # 2√2/π is the limit for a perfectly flat inductor current
