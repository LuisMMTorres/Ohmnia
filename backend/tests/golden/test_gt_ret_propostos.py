"""GT-RET-P1..P7: reference cases proposed for decision D6, waiting for the user's check.

Each case is a classic textbook-style exercise (120 V / 60 Hz single-phase, 480 V / 60 Hz
three-phase) solved here by the closed-form result of the theory, independently of the module
code: Hart, *Power Electronics*, 1st ed., ch. 3 and 4; Mohan, Undeland and Robbins, *Power
Electronics*, 3rd ed., ch. 5 and 6. They are NOT copied from a numbered worked example: the user
confirms the numbers (or points to the equivalent book example) and then the docstring gets the
book, edition, example and page. Table in docs/validacao/casos-referencia-propostos.md.

Tolerance: 1e-3 relative (grid of 14 400–28 800 points per period).
"""

import math

import pytest
from scipy.optimize import brentq

from circuitos.design.plugins.ret1 import model as r1
from circuitos.design.plugins.ret3 import model as t3
from circuitos.design.plugins.retc1 import model as c1

F = 60.0
W = 2 * math.pi * F
VS = 120.0
VM = VS * math.sqrt(2)
VLL = 480.0 * math.sqrt(2)
REL = 1e-3


def test_p1_half_wave_resistive():
    """120 V, 60 Hz, R = 10 Ω: Vo = 54,0 V, Io = 5,40 A, Ief = 8,49 A, P = 720 W, FP = 0,707."""
    R = 10.0
    w = r1.unfiltered("meia_onda", VM, 0.0, R)
    assert r1.mean(w.vo) == pytest.approx(VM / math.pi, rel=REL)
    irms = VM / (2 * R)
    assert r1.rms(w.i_load) == pytest.approx(irms, rel=REL)
    assert r1.rms(w.i_load) ** 2 * R == pytest.approx(720.0, rel=REL)
    pf = r1.rms(w.i_load) ** 2 * R / (VS * r1.rms(w.i_sec))
    assert pf == pytest.approx(1 / math.sqrt(2), rel=REL)


def test_p2_bridge_capacitor_filter():
    """Ponte, 120 V, R = 500 Ω, C = 100 µF: θoff = 93,0°, θon = 60,6°, ΔVo = 21,9 V.

    A aproximação Vm/(2fRC) = 28,3 V superestima a ondulação em ~30 % neste ponto.
    """
    R, C = 500.0, 100e-6
    wrc = W * R * C
    w = r1.cap_filter("ponte", VM, 0.0, R, C, F)
    toff = math.pi - math.atan(wrc)
    assert w.theta_off == pytest.approx(toff, rel=REL)

    def discharge(t: float) -> float:
        return VM * math.sin(toff) * math.exp(-(t - toff) / wrc) - VM * abs(math.sin(t))

    ton = brentq(discharge, math.pi + 0.01, 1.5 * math.pi)
    ripple = VM - VM * abs(math.sin(ton))
    assert float(w.vo.max() - w.vo.min()) == pytest.approx(ripple, rel=REL)
    assert math.degrees(ton - math.pi) == pytest.approx(60.58, abs=0.01)


def test_p3_half_wave_controlled_rl():
    """120 V, R = 20 Ω, L = 40 mH, α = 45°: β = 216,9°, Vo = 40,7 V."""
    R, L, a = 20.0, 0.04, math.radians(45)
    th = math.atan2(W * L, R)

    def current(x: float) -> float:
        return math.sin(x - th) - math.sin(a - th) * math.exp((a - x) / (W * L / R))

    beta = brentq(current, 0.9 * math.pi, 2 * math.pi)
    sol = c1.solve("meia_onda", VM, a, c1.Load(R, L), F)
    assert sol.beta == pytest.approx(beta, rel=REL)
    vo = VM / (2 * math.pi) * (math.cos(a) - math.cos(beta))
    assert c1.mean(c1.waves(sol).vo) == pytest.approx(vo, rel=REL)


def test_p4_bridge_controlled_continuous():
    """Ponte totalmente controlada, 120 V, α = 30°, R = 10 Ω, L ≫: Vo = 93,6 V, Io = 9,36 A."""
    a = math.radians(30)
    w = c1.waves(c1.solve("ponte", VM, a, c1.Load(10.0, 1.0), F))
    vo = 2 * VM / math.pi * math.cos(a)
    assert c1.mean(w.vo) == pytest.approx(vo, rel=REL)
    assert c1.mean(w.io) == pytest.approx(vo / 10.0, rel=REL)


def test_p5_semicontrolled_bridge():
    """Ponte semicontrolada, 120 V, α = 60°, carga R-L: Vo = 81,0 V."""
    a = math.radians(60)
    w = c1.waves(c1.solve("semicontrolada", VM, a, c1.Load(10.0, 1.0), F))
    assert c1.mean(w.vo) == pytest.approx(VM / math.pi * (1 + math.cos(a)), rel=REL)


def test_p6_six_pulse_diode_bridge():
    """Ponte trifásica a diodos, 480 V, Io = 6,48 A: Vo = 648 V, Iℓ = 5,29 A, FP = 0,955."""
    io = 6.482
    w = t3.waves(6, VLL, 0.0, io, 0.0, F, 0.0)
    assert t3.mean(w.vo) == pytest.approx(3 * VLL / math.pi, rel=REL)
    assert t3.rms(w.bridges[0].i_line[0]) == pytest.approx(math.sqrt(2 / 3) * io, rel=REL)
    assert t3.power_factor(w) == pytest.approx(3 / math.pi, rel=REL)


def test_p7_six_pulse_controlled_with_ls():
    """480 V, α = 30°, Io = 50 A, Ls = 1 mH: μ = 5,86°, ΔVμ = 18,0 V, Vo = 543 V."""
    a, io, ls = math.radians(30), 50.0, 1e-3
    w = t3.waves(6, VLL, a, io, ls, F, 0.0)
    mu = math.acos(math.cos(a) - 2 * W * ls * io / VLL) - a
    assert w.mu == pytest.approx(mu, rel=REL)
    vo = 3 * VLL / math.pi * math.cos(a) - 3 * W * ls * io / math.pi
    assert t3.mean(w.vo) == pytest.approx(vo, rel=REL)
