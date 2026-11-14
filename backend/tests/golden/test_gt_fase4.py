"""GT-P8..P15: Phase 4 reference cases proposed for the user's check (decision D6).

Classic textbook-style exercises (Boylestad & Nashelsky, *Electronic Devices and Circuit
Theory*, 11th ed., ch. 2, 4, 5, 6 and 7; Kuffel, Zaengl & Kuffel, *High Voltage Engineering:
Fundamentals*, 2nd ed., ch. 2), solved here by the closed-form result with VBE = 0,7 V and a
constant diode drop. The BJT model is given IS so that VBE = 0,7 V exactly at the closed-form
current, so the exponential solver must reproduce the textbook number. They are NOT copied from
a numbered worked example: the user confirms the numbers (or points to the book example) and
then the docstring gets the example and page. Table in docs/validacao/fontes-amplificadores.md.

Tolerance: 1e-6 relative for the network equations; 1e-3 for the waveform cases (grid of
2 880 points per period); 0,5 % for corner frequencies read off a log grid.
"""

import math

import numpy as np
import pytest

from circuitos.core.units import Q_
from circuitos.design.devmodels import VT_300K, Bjt, Mos
from circuitos.design.engine import Device
from circuitos.design.plugins.forma import FormaModule, FormaSpec
from circuitos.design.qpoint import bjt_q, mos_q, parallel, thevenin
from circuitos.design.smallsignal import Network, corner, log_grid

VBE = 0.7
REL = 1e-6


def bjt_for(ic: float, beta: float) -> Bjt:
    return Bjt(IS=ic / math.expm1(VBE / VT_300K), BF=beta)


def test_p8_fixed_bias():
    """Polarização fixa: VCC = 12 V, RB = 240 kΩ, RC = 2,2 kΩ, β = 50 → IB = 47,08 µA,
    IC = 2,354 mA, VCE = 6,82 V."""
    ib = (12 - VBE) / 240e3
    ic = 50 * ib
    q = bjt_q(bjt_for(ic, 50), 12, 12, 240e3, 2.2e3, 0.0)
    assert pytest.approx(47.083e-6, rel=1e-4) == q.IB
    assert pytest.approx(ic, rel=REL) == q.IC
    assert pytest.approx(12 - ic * 2.2e3, rel=REL) == q.VCE
    assert pytest.approx(6.82, abs=0.01) == q.VCE


def test_p9_divider_bias_exact():
    """Divisor (análise exata): VCC = 22 V, R1 = 39 kΩ, R2 = 3,9 kΩ, RC = 10 kΩ, RE = 1,5 kΩ,
    β = 100 → RTh = 3,55 kΩ, ETh = 2 V, IC = 0,838 mA, VCE = 12,35 V."""
    vth, rth = thevenin(22, 39e3, 3.9e3)
    assert vth == pytest.approx(2.0, rel=REL)
    ib = (vth - VBE) / (rth + 101 * 1.5e3)
    ic = 100 * ib
    q = bjt_q(bjt_for(ic, 100), 22, vth, rth, 10e3, 1.5e3)
    assert pytest.approx(ic, rel=REL) == q.IC
    assert pytest.approx(0.838e-3, rel=1e-3) == q.IC
    assert pytest.approx(22 - ic * 10e3 - 101 * ib * 1.5e3, rel=REL) == q.VCE
    assert pytest.approx(12.35, abs=0.01) == q.VCE


def test_p10_collector_feedback():
    """Realimentação de coletor: VCC = 10 V, RF = 250 kΩ, RC = 4,7 kΩ, RE = 1,2 kΩ, β = 90 →
    IB = 11,82 µA, IC = 1,064 mA, VCE = 3,66 V."""
    ib = (10 - VBE) / (250e3 + 91 * (4.7e3 + 1.2e3))
    ic = 90 * ib
    q = bjt_q(bjt_for(ic, 90), 10, 0.0, 250e3, 4.7e3, 1.2e3, collector_feedback=True)
    assert pytest.approx(ic, rel=REL) == q.IC
    assert pytest.approx(1.064e-3, rel=1e-3) == q.IC
    assert pytest.approx(10 - 91 * ib * (4.7e3 + 1.2e3), rel=REL) == q.VCE
    assert pytest.approx(3.66, abs=0.01) == q.VCE


def test_p11_mosfet_divider():
    """E-MOSFET com divisor: VG = 4 V, RS = 1 kΩ, RD = 2 kΩ, VDD = 16 V, VT = 2 V,
    k = 0,3 mA/V² (ID = k(VGS − VT)²) → ID = 0,594 mA, VGS = 3,41 V, VDS = 14,22 V."""
    k, vt, vg, rs = 0.3e-3, 2.0, 4.0, 1e3
    # ID = k (vg − ID·rs − vt)²  →  k rs² ID² − (2 k rs (vg − vt) + 1) ID + k (vg − vt)² = 0
    a, b, c = k * rs**2, -(2 * k * rs * (vg - vt) + 1), k * (vg - vt) ** 2
    i_d = (-b - math.sqrt(b * b - 4 * a * c)) / (2 * a)  # root with VGS > VT
    q = mos_q(Mos(VT=vt, KP=2 * k), 16, vg, 2e3, rs)
    assert pytest.approx(i_d, rel=REL) == q.ID
    assert vt < q.VGS
    assert pytest.approx(0.594e-3, rel=1e-3) == q.ID
    assert pytest.approx(16 - i_d * 3e3, rel=REL) == q.VDS


def test_p12_common_emitter_midband_and_corner():
    """EC com RE desviado (π-híbrido, sem Cπ/Cμ): gm = 40 mS, rπ = 2,5 kΩ, RB = 10 kΩ,
    RC = 4,7 kΩ, RL = 10 kΩ, Rs = 600 Ω → Avs = −gm(RC∥RL)·Ri/(Rs + Ri), Ri = RB∥rπ = 2 kΩ;
    só Cin = 1 µF finito: fL = 1/(2π(Rs + Ri)Cin) = 61,2 Hz."""
    gm, rpi, rb, rc, rl, rs, cin = 40e-3, 2.5e3, 10e3, 4.7e3, 10e3, 600.0, 1e-6
    n = Network()
    n.R("vs", "s1", rs)
    n.C("s1", "b", cin)
    n.R("b", "0", rb)
    n.R("b", "e", rpi)
    n.R("e", "0", 1e-9)  # bypassed emitter
    n.gm("c", "e", gm, "b", "e")
    n.R("c", "0", rc)
    n.C("c", "out", 1.0)
    n.R("out", "0", rl)
    ri = parallel(rb, rpi)
    expected = gm * parallel(rc, rl) * ri / (rs + ri)
    h = n.solve(np.array([1e5]), "vs", ["out"])["out"][0]
    assert abs(h) == pytest.approx(expected, rel=1e-6)
    assert h.real < 0  # inverting
    f = log_grid(1.0, 1e5, 400)
    mag = np.abs(n.solve(f, "vs", ["out"])["out"])
    fl = corner(f, mag, "fl")
    assert fl == pytest.approx(1 / (2 * math.pi * (rs + ri) * cin), rel=5e-3)


def _forma(**kw: object) -> dict[str, float]:
    mod = FormaModule()
    spec = FormaSpec(**kw)
    role = mod.roles(spec)[0]
    an = mod.analyse(spec, {role.designator: Device(record=None, drop=Q_(0.7, "V"))})
    return {k: float(v.m_as(v.units)) for k, v in an.summary.items()}


def test_p13_clippers():
    """Ceifador paralelo: Vm = 10 V, VB = 3 V, VF = 0,7 V, R = 1 kΩ, RL = 100 kΩ → saída
    máxima 3,7 V, mínima −10·100/101 = −9,90 V. Série: máximo Vm − VB − VF = 6,3 V.
    Duplo: ±3,7 V."""
    p = _forma(kind="ceifador_paralelo")
    assert p["Vo_max"] == pytest.approx(3.7, rel=1e-9)
    assert p["Vo_min"] == pytest.approx(-10 * 100 / 101, rel=1e-6)
    s = _forma(kind="ceifador_serie")
    assert s["Vo_max"] == pytest.approx(6.3, rel=1e-6)
    assert s["Vo_min"] == pytest.approx(0.0, abs=1e-12)
    d = _forma(kind="ceifador_duplo")
    assert (d["Vo_max"], d["Vo_min"]) == pytest.approx((3.7, -3.7), rel=1e-9)


def test_p14_clamper():
    """Grampeador positivo: Vm = 10 V, VB = 3 V, VF = 0,7 V, C = 10 µF, RL = 100 kΩ, 1 kHz
    (RL·C = 1 000 T) → VC = Vm + VB − VF = 12,3 V, mínimo 2,3 V, máximo ≈ 2Vm + VB − VF = 22,3 V
    menos a descarga em meio período, ≈ (Vm + VC)(1 − e^(−T/(2RLC))) ≈ 0,011 V."""
    g = _forma(kind="grampeador")
    assert g["VC"] == pytest.approx(12.3, rel=1e-9)
    assert g["Vo_min"] == pytest.approx(2.3, rel=1e-6)
    droop = 22.3 * (1 - math.exp(-0.5e-3 / 1.0))
    assert g["Vo_max"] == pytest.approx(22.3 - droop, abs=5e-3)


def test_p15_cockcroft_walton():
    """Multiplicador de 3 estágios: Vm = 100 V, VF = 0,7 V, 60 Hz, RL = 1 MΩ → sem carga
    6(Vm − VF) = 595,8 V; com C por estágio, ΔV = Io/(fC)(2n³/3 + n²/2 − n/6) = 22·Io/(fC) e
    δV = 6·Io/(fC), Io = Vo/RL."""
    m = _forma(
        kind="multiplicador",
        stages=3,
        Vm={"value": 100, "unit": "V"},
        f={"value": 60, "unit": "Hz"},
        RL={"value": 1, "unit": "Mohm"},
    )
    assert m["Vo_noload"] == pytest.approx(595.8, rel=1e-9)
    c = m["C_stage"] * 1e-6
    io = m["Vo_avg"] / 1e6
    assert pytest.approx(22.0) == 2 * 27 / 3 + 9 / 2 - 3 / 6
    assert m["dV"] == pytest.approx(22.0 * io / (60 * c), rel=1e-9)
    assert m["ripple"] == pytest.approx(6 * io / (60 * c), rel=1e-9)
    assert m["Vo_avg"] == pytest.approx(595.8 - m["dV"], rel=1e-9)
