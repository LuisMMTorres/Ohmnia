"""Unit tests of the Phase 5 core: MNA solver, op-amp macromodel and filter prototypes."""

import math
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.signal as sg

from circuitos.design.filters import (
    ladder_g,
    min_order,
    normalise,
    prototype,
    response,
    sections,
    transform,
)
from circuitos.design.mna import Circuit
from circuitos.design.opamp import C_POLE, OpAmp, db_ratio


# ---------------------------------------------------------------- MNA
def rc_lowpass(r: float = 1e3, c: float = 1e-6) -> Circuit:
    k = Circuit()
    k.V("1", "in", "0", dc=2.0, ac=1.0)
    k.R("1", "in", "o", r)
    k.C("1", "o", "0", c)
    return k


def test_mna_dc_opens_capacitors():
    v, _ = rc_lowpass().op()
    assert v["o"] == pytest.approx(2.0)


def test_mna_ac_rc_corner():
    fc = 1 / (2 * math.pi * 1e3 * 1e-6)
    h = rc_lowpass().ac(np.array([fc]), ["o"])["o"][0]
    assert abs(h) == pytest.approx(1 / math.sqrt(2), rel=1e-12)
    assert math.degrees(np.angle(h)) == pytest.approx(-45, rel=1e-12)


def test_mna_poles_rc_and_rlc():
    p = rc_lowpass().poles()
    assert p == pytest.approx([-1 / (1e3 * 1e-6)], rel=1e-9)
    k = Circuit()  # series RLC: s² + (R/L)s + 1/(LC)
    k.V("s", "in", "0")  # branch currents are keyed by name: keep names unique
    k.R("1", "in", "a", 10.0)
    k.L("1", "a", "b", 1e-3)
    k.C("1", "b", "0", 1e-6)
    got = sorted(k.poles(), key=lambda z: z.imag)
    want = sorted(np.roots([1, 10 / 1e-3, 1 / (1e-3 * 1e-6)]), key=lambda z: z.imag)
    assert np.allclose(got, want, rtol=1e-9)


def test_mna_vcvs_and_vccs():
    k = Circuit()
    k.V("s", "in", "0", dc=1.0)
    k.E("x", "e", "0", "in", "0", 5.0)
    k.G("1", "0", "g", "in", "0", 1e-3)  # 1 mA into node g
    k.R("1", "g", "0", 2e3)
    v, _ = k.op()
    assert v["e"] == pytest.approx(5.0)
    assert v["g"] == pytest.approx(2.0)


# ---------------------------------------------------------------- op-amp model
def follower(u: OpAmp, vin: float = 1.0) -> float:
    k = Circuit()
    k.V("in", "in", "0", dc=vin, ac=1.0)
    u.add(k, "U", "in", "o", "o")
    return k.op()[0]["o"]


def test_macromodel_pole_values():
    u = OpAmp(A0=2e5, GBW=1e6)
    assert u.fb == pytest.approx(5.0)
    assert u.r_pole * C_POLE == pytest.approx(1 / (2 * math.pi * 5.0))
    assert abs(u.a(1e6)) == pytest.approx(2e5 / math.sqrt(1 + (1e6 / 5) ** 2))


def test_follower_finite_gain_and_offset():
    a0 = 1e4
    assert follower(OpAmp(A0=a0, GBW=1e6)) == pytest.approx(a0 / (1 + a0), rel=1e-12)
    vo = follower(OpAmp(A0=a0, GBW=1e6, Vos=1e-3))
    assert vo == pytest.approx((1 + 1e-3) * a0 / (1 + a0), rel=1e-12)


def test_cmrr_chain_input_referred_error():
    """Follower with A0 → ∞: vo = vin(1 + k)/(1 − k), k = 1/(2·CMRR) (v_cm = (v+ + v−)/2)."""
    k = 1 / (2 * 1e3)
    vo = follower(OpAmp(A0=1e12, GBW=1e12, CMRR=1e3))
    assert vo == pytest.approx((1 + k) / (1 - k), rel=1e-9)


def test_closed_loop_bandwidth_is_gbw_over_noise_gain():
    k = Circuit()
    k.V("in", "in", "0", ac=1.0)
    k.R("1", "in", "n", 1e3)
    k.R("2", "o", "n", 99e3)
    OpAmp(A0=1e6, GBW=1e6).add(k, "U", "0", "n", "o")
    f = np.array([1.0, 1e4])
    h = k.ac(f, ["o"])["o"]
    assert abs(h[0]) == pytest.approx(99, rel=1e-3)
    assert abs(h[1]) == pytest.approx(99 / math.sqrt(2), rel=2e-3)  # f_H = GBW/100


def fake_record(**params):
    return SimpleNamespace(
        parameters={
            k: SimpleNamespace(has_value=True, typ=t, min=m) for k, (t, m) in params.items()
        }
    )


def test_db_ratio_reads_raw_db_as_voltage_ratio():
    rec = fake_record(CMRR=(80.0, None), PSRR=(None, 60.0))
    assert db_ratio(rec, "CMRR") == pytest.approx(1e4)
    assert db_ratio(rec, "PSRR") == pytest.approx(1e3)  # minimum when no typical
    assert db_ratio(rec, "Avol") == math.inf


# ---------------------------------------------------------------- filters
def test_butterworth_poles_on_unit_circle():
    _, p = prototype("butterworth", 5, 10 * math.log10(2), 40)
    assert np.allclose(np.abs(p), 1.0)
    assert all(x.real < 0 for x in p)


@pytest.mark.parametrize(
    ("approx", "ratio", "rp", "rs", "n"),
    [
        ("butterworth", 2.0, 3.0103, 40, 7),
        ("chebyshev", 2.0, 0.5, 40, 5),
        ("eliptico", 2.0, 0.5, 40, 4),
    ],
)
def test_min_order_matches_scipy(approx, ratio, rp, rs, n):
    assert min_order(approx, ratio, rp, rs) == n


@pytest.mark.parametrize("kind", ["passa_baixas", "passa_altas", "passa_faixa", "rejeita_faixa"])
def test_sections_reproduce_the_transfer_function(kind):
    z, p = prototype("chebyshev", 4, 1.0, 40)
    w1, w2 = 2 * math.pi * 1e3, 2 * math.pi * 1.2e3
    zt, pt = (
        transform(z, p, kind, w1, w2)
        if kind in ("passa_faixa", "rejeita_faixa")
        else transform(z, p, kind, w1)
    )
    w_c = math.sqrt(w1 * w2) if kind in ("passa_faixa", "rejeita_faixa") else w1
    secs = normalise(sections(zt, pt, kind), kind, w_c)
    f = np.logspace(1, 5, 400)
    h = response(secs, f)
    assert np.all(np.isfinite(h))
    assert len(secs) >= 2


def test_ladder_g_butterworth_closed_form():
    for n in (2, 3, 4, 7):
        want = [2 * math.sin((2 * k - 1) * math.pi / (2 * n)) for k in range(1, n + 1)]
        assert ladder_g("butterworth", n, 10 * math.log10(2)) == pytest.approx(want, rel=1e-12)


def test_scipy_reference_for_chebyshev_ripple():
    """|H| at the band edge of the Chebyshev prototype is −rp dB."""
    z, p, k = sg.cheb1ap(3, 1.0)
    _, h = sg.freqs_zpk(z, p, k, [1.0])
    assert 20 * math.log10(abs(h[0])) == pytest.approx(-1.0, abs=1e-9)
