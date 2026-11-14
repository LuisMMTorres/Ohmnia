"""BV-AMPOP-OFFSET/-IB/-IOS/-A0/-CMRR/-PSRR/-GBW/-SR/-EXCURSAO: the virtual bench measures the
macromodel on ngspice and recovers the values it was built with.

The model numbers below are generic test values, not datasheet data. Tolerance: each test's own
``tolerance_pct`` (finite A0, Rin and the 20–80 % SR window, justified in the bench).
"""

import math

import pytest

from circuitos.design.opamp import OpAmp
from circuitos.devices.opamp_bench import run_bench

pytestmark = pytest.mark.ngspice

MODELS = {
    "bipolar": OpAmp(
        A0=2e5,
        GBW=1e6,
        Rin=2e6,
        Vos=1e-3,
        Ib=80e-9,
        Ios=20e-9,
        SR=0.5e6,
        v_hi=13.0,
        v_lo=-13.0,
        CMRR=10 ** (90 / 20),
        PSRR=10 ** (96 / 20),
    ),
    "jfet": OpAmp(
        A0=2e5,
        GBW=3e6,
        Rin=1e12,
        Vos=3e-3,
        Ib=30e-12,
        Ios=5e-12,
        SR=13e6,
        v_hi=13.5,
        v_lo=-13.5,
        CMRR=10 ** (86 / 20),
        PSRR=10 ** (86 / 20),
    ),
}
EXPECTED = {
    "BV-AMPOP-OFFSET",
    "BV-AMPOP-IB",
    "BV-AMPOP-IOS",
    "BV-AMPOP-A0",
    "BV-AMPOP-CMRR",
    "BV-AMPOP-PSRR",
    "BV-AMPOP-GBW",
    "BV-AMPOP-SR",
    "BV-AMPOP-EXCURSAO+",
    "BV-AMPOP-EXCURSAO-",
}


@pytest.mark.parametrize("name", list(MODELS))
def test_bench_recovers_model(name):
    res = run_bench(MODELS[name], 15.0)
    ids = {t.id for t in res.tests}
    assert ids >= EXPECTED
    bad = [t for t in res.tests if not t.ok]
    assert not bad, [(t.id, t.measured, t.expected, t.error_pct) for t in bad]
    assert res.steps and res.netlists
    assert len(res.bode_f) == len(res.bode_mag) > 10
    assert res.step_out.max() > 0


def test_bench_without_errors_skips_cmrr_psrr():
    u = OpAmp(A0=1e5, GBW=1e6, SR=1e6, v_hi=13.0, v_lo=-13.0)
    res = run_bench(u, 15.0)
    ids = {t.id for t in res.tests}
    assert "BV-AMPOP-CMRR" not in ids and "BV-AMPOP-PSRR" not in ids
    assert all(t.ok for t in res.tests)
    gbw = next(t for t in res.tests if t.id == "BV-AMPOP-GBW")
    assert math.isclose(gbw.measured.m_as("Hz"), 1e6, rel_tol=0.01)
