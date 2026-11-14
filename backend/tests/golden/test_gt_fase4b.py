"""GT-P16..P19: reference cases proposed for the JFET, Darlington and class D additions (D6).

Textbook-style exercises (Boylestad & Nashelsky, *Electronic Devices and Circuit Theory*,
11th ed., ch. 7 "FET biasing" and ch. 12 "Power amplifiers"), solved here in closed form. Like
P8–P15 they are NOT copied from a numbered worked example: the user confirms the numbers (or
points to the book example) and then the docstring gets the example and page.

Tolerance: 1e-9 relative for the closed forms; 1e-3 for the class D fundamental (FFT of the
exact switched solution resampled on 4 096 points).
"""

import math

import numpy as np
import pytest

from circuitos.design.devmodels import VT_300K, Bjt, Darlington, Jfet
from circuitos.design.plugins.pad.module import Bridge, solve
from circuitos.design.qpoint import jfet_q

REL = 1e-9


def test_p16_jfet_self_bias():
    """Autopolarização: IDSS = 8 mA, VP = 4 V, RS = 1 kΩ, RD = 3,3 kΩ, VDD = 20 V.

    ID = IDSS(1 − ID·RS/VP)² → ID² − 10 ID + 16 = 0 (mA) → ID = 2 mA (a raiz 8 mA dá
    VGS = −8 V, abaixo do corte), VGS = −2 V, VDS = 20 − 2·(3,3 + 1) = 11,4 V.
    """
    q = jfet_q(Jfet(IDSS=8e-3, VP=4.0), 20, 0.0, 3.3e3, 1e3)
    assert pytest.approx(2e-3, rel=REL) == q.ID
    assert pytest.approx(-2.0, rel=REL) == q.VGS
    assert pytest.approx(11.4, rel=REL) == q.VDS


def test_p17_jfet_divider_bias():
    """Divisor: VDD = 16 V, R1 = 2,1 MΩ, R2 = 270 kΩ, RD = 2,4 kΩ, RS = 1,5 kΩ, IDSS = 8 mA,
    VP = 4 V → VG = 1,823 V; IDSS·RS(1 + VGS/VP)² = VG − VGS, raiz em (−VP, 0):
    VGS ≈ −1,80 V, ID ≈ 2,42 mA."""
    vg = 16 * 270e3 / (2.1e6 + 270e3)
    idss, vp, rs = 8e-3, 4.0, 1.5e3
    a = idss * rs / vp**2
    # a·v² + (2·a·vp + 1)·v + (a·vp² − vg) = 0, from IDSS·RS(1 + v/VP)² = VG − v
    roots = np.roots([a, 2 * a * vp + 1, a * vp**2 - vg])
    vgs = float(next(r.real for r in roots if -vp < r.real < 0))
    q = jfet_q(Jfet(IDSS=idss, VP=vp), 16, vg, 2.4e3, rs)
    assert pytest.approx(vgs, rel=1e-8) == q.VGS
    assert pytest.approx((vg - vgs) / rs, rel=1e-8) == q.ID
    assert pytest.approx(2.42e-3, rel=5e-3) == q.ID
    assert pytest.approx(-1.80, abs=0.01) == q.VGS


def test_p18_darlington_gain():
    """Darlington com β1 = β2 = 30: βD = β1β2 + β1 + β2 = 960; IC/IB do modelo de dois
    transistores reproduz βD em qualquer ponto da região ativa, e VBE(IC) inverte IC(VBE)."""
    beta = 30.0
    is1 = 1e-14
    d = Darlington(Bjt(IS=is1, BF=beta), Bjt(IS=is1 * (beta + 1), BF=beta))
    assert pytest.approx(960.0, rel=REL) == d.BF
    for vbe in (1.2, 1.35, 1.5):
        v2 = d.split(vbe)
        ib = d.q1.IS / beta * math.expm1((vbe - v2) / VT_300K)
        assert pytest.approx(960.0, rel=1e-9) == d.ic(vbe) / ib
        assert pytest.approx(vbe, rel=1e-9) == d.vbe(d.ic(vbe))


def test_p19_class_d_filter_and_fundamental():
    """Classe D, meia ponte ±24 V, RL = 8 Ω, fc = 25 kHz: Butterworth L = √2·RL/ωc =
    72,03 µH e C = 1/(√2·RL·ωc) = 0,5627 µF. Com PWM de amostragem natural a componente
    fundamental do nó chaveado é exatamente m·V; na carga ela vale m·V·|H(jω)|."""
    wc = 2 * math.pi * 25e3
    lv, cv = math.sqrt(2) * 8 / wc, 1 / (math.sqrt(2) * 8 * wc)
    assert pytest.approx(72.03e-6, rel=1e-4) == lv
    assert pytest.approx(0.5627e-6, rel=1e-4) == cv
    br = Bridge(vcc=24, r_on=0.05, rl=8, L=lv, C=cv, f=1e3, k=200, m=0.6)
    sol = solve(br)
    grid = np.linspace(0, 1e-3, 4096, endpoint=False)
    tt, idx = np.unique(sol.t, return_index=True)
    vo = np.interp(grid, tt, sol.vo[idx])
    v1 = 2 * abs(np.fft.rfft(vo)[1]) / vo.size
    expected = br.m * br.vth * abs(br.h(2 * math.pi * 1e3))
    assert pytest.approx(expected, rel=1e-3) == v1
