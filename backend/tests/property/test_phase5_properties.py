"""PT-OPA-GBW and PT-FIL-E24: properties of the op-amp macromodel and of the filter rounding."""

import math

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.design.mna import Circuit
from circuitos.design.opamp import OpAmp
from circuitos.selection.derating import DeratingPolicy


@settings(max_examples=60, deadline=None)
@given(
    a0=st.floats(1e3, 1e7),
    gbw=st.floats(1e4, 1e8),
    gain=st.floats(1.0, 1e3),
)
def test_pt_opa_gbw_closed_loop_bandwidth(a0, gbw, gain):
    """Non-inverting amplifier with one-pole op-amp: f_H = fb(1 + A0β), β = 1/G (exact)."""
    k = Circuit()
    k.V("in", "in", "0", ac=1.0)
    k.R("1", "n", "0", 1e3)
    k.R("2", "o", "n", 1e3 * (gain - 1) + 1e-9)
    u = OpAmp(A0=a0, GBW=gbw)
    u.add(k, "U", "in", "n", "o")
    beta = 1 / (1 + (1e3 * (gain - 1) + 1e-9) / 1e3)
    fh = u.fb * (1 + a0 * beta)
    h = k.ac(np.array([1e-6 * u.fb, fh]), ["o"])["o"]
    assert math.isclose(abs(h[1]) / abs(h[0]), 1 / math.sqrt(2), rel_tol=1e-6)
    assert math.isclose(abs(h[0]), a0 / (1 + a0 * beta), rel_tol=1e-6)


def fil(repo, **raw):
    mod = registry.get("DM-FIL")
    res, _ = run(
        mod,
        mod.spec_schema(**raw),
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    return {k: v.value for k, v in res.summary.items()}, {w.code for w in res.warnings}


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    fp=st.floats(50, 20e3),
    approx=st.sampled_from(["butterworth", "chebyshev", "bessel"]),
    realization=st.sampled_from(["sallen_key", "mfb"]),
)
def test_pt_fil_e24_rounding_bound(reviewed_catalogue, fp, approx, realization):
    """With E24 resistors and E12 capacitors the −3 dB corner stays near the corner of the
    unrounded design (f_dev, from the exact response of the rounded parts), and a deviation above
    5 % is never hidden: the result carries the "desvio" warning (rule 4). Half an E24 step is
    about 5 % per part, so a sixth-order design can pass 5 %; 15 % is the sanity bound."""
    s, warnings = fil(
        reviewed_catalogue,
        approx=approx,
        realization=realization,
        fp={"value": fp, "unit": "Hz"},
        f_stop={"value": 3 * fp, "unit": "Hz"},
        res_series="E24",
    )
    assert abs(s["f_dev"]) <= 15.0
    assert (abs(s["f_dev"]) > 5.0) == ("desvio" in warnings)
    assert s["n"] >= 2
