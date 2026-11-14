"""GT-P20..P31: Phase 5 reference cases proposed for the user's check (decision D6).

GT-OPA-01..03, GT-FIL-01..03, GT-OSC-01..03, GT-OSC-MV-01 and GT-OPNL-01..03 of the scope.
Textbook-style exercises solved in closed form: Boylestad & Nashelsky, *Electronic Devices and
Circuit Theory*, 11th ed., ch. 10 (op-amp applications) and ch. 14 (oscillators); Sedra & Smith,
*Microelectronic Circuits*, 7th ed., ch. 2 and ch. 18; Williams & Taylor, *Electronic Filter Design
Handbook*, 4th ed., ch. 2; Matthaei, Young & Jones (1964), ch. 4 for the ladder elements. Like
P8–P19 they are NOT copied from a numbered worked example: the user confirms the numbers (or
points to the book example) and then the docstring gets the example and page. Table in
docs/validacao/casos-referencia-propostos.md.

The module cases run the design (no simulation) with the reviewed catalogue and check that the
summary obeys the closed form with the commercial values it chose.

Tolerance: 1e-9 relative for the closed forms; 1e-4 for the tabulated ladder elements (four
decimals in the tables); 1e-3 for the 555 times, whose thresholds come from the datasheet.
"""

import math

import numpy as np
import pytest

from circuitos.design import registry
from circuitos.design.devmodels import VT_300K
from circuitos.design.engine import run
from circuitos.design.filters import attenuation_db, ladder_g, min_order, prototype
from circuitos.selection.derating import DeratingPolicy

REL = 1e-9
BUTTER_3DB = 10 * math.log10(2)  # passband edge at −3,0103 dB


def design(repo, mid: str, **raw) -> dict[str, float]:
    """Summary of a design, every value in SI (or the dimensionless magnitude)."""
    mod = registry.get(mid)
    res, _ = run(
        mod,
        mod.spec_schema(**raw),
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    out = {}
    for k, v in res.summary.items():
        x = v.to_pint()
        out[k] = float(x.to_base_units().magnitude) if v.unit not in ("percent", "%") else v.value
    return out


# ---------------------------------------------------------------- GT-OPA
def test_p20_inverting_gain(reviewed_catalogue):
    """Inversor: |Av| = 10, R1 = 10 kΩ → R2 = 100 kΩ, Av = −R2/R1 = −10 (ideal);
    Rp = R1 ∥ R2 = 9,09 kΩ para compensar a corrente de polarização."""
    s = design(reviewed_catalogue, "DM-OPA")
    assert s["R1"] == pytest.approx(10e3, rel=REL)
    assert s["R2"] == pytest.approx(100e3, rel=REL)
    assert s["Av_ideal"] == pytest.approx(s["R2"] / s["R1"], rel=REL)
    assert s["Rp"] == pytest.approx(9.09e3, rel=1e-3)  # E96 de 9,0909 kΩ


def test_p21_non_inverting_gain(reviewed_catalogue):
    """Não inversor: Av = 1 + R2/R1 = 10 → R2 = 90 kΩ; o E96 dá 90,9 kΩ e Av = 10,09."""
    s = design(reviewed_catalogue, "DM-OPA", config="nao_inversor")
    assert s["R2"] == pytest.approx(90.9e3, rel=REL)
    assert s["Av_ideal"] == pytest.approx(1 + s["R2"] / s["R1"], rel=REL)
    assert s["Av_ideal"] == pytest.approx(10.09, rel=REL)


def test_p22_finite_gain_inverting(reviewed_catalogue):
    """Inversor com ganho de malha aberta finito: Av = −(R2/R1)/(1 + (1 + R2/R1)/A0); com o
    A0 do datasheet do ampop escolhido o erro de ganho fica em −(1 + R2/R1)/A0 ≈ −11/A0."""
    s = design(reviewed_catalogue, "DM-OPA")
    a_id = s["Av_ideal"]
    a0 = (1 + a_id) / (a_id / s["Av"] - 1)  # A0 implied by the summary
    assert a0 > 1e4  # every catalogue op-amp has A0 above 80 dB
    assert s["Av"] == pytest.approx(a_id / (1 + (1 + a_id) / a0), rel=REL)


# ---------------------------------------------------------------- GT-FIL
def test_p23_butterworth_order_and_q():
    """Butterworth passa-baixas, fp = 1 kHz (−3 dB), fs = 3 kHz com 30 dB:
    n = ⌈log(10^3 − 1)/(2 log 3)⌉ = 4; seções com Q = 1/(2 cos θk), θk = π/8 e 3π/8 →
    Q = 0,5412 e 1,3066; atenuação em fs = 10 log(1 + 3^8) = 38,17 dB."""
    n = min_order("butterworth", 3.0, BUTTER_3DB, 30)
    assert n == 4
    assert n == math.ceil(math.log10(10**3 - 1) / (2 * math.log10(3)))
    _, p = prototype("butterworth", 4, BUTTER_3DB, 30)
    qs = sorted(abs(x) / (-2 * x.real) for x in p if x.imag > 0)
    assert qs == pytest.approx(
        [1 / (2 * math.cos(t)) for t in (math.pi / 8, 3 * math.pi / 8)], rel=REL
    )
    assert qs == pytest.approx([0.5412, 1.3066], rel=1e-4)
    assert attenuation_db(np.array([]), p, 3.0) == pytest.approx(
        10 * math.log10(1 + 3**8), rel=1e-9
    )


def test_p24_chebyshev_order_and_attenuation():
    """Chebyshev 1 dB, ws/wp = 3, As = 30 dB: n = ⌈acosh(√((10^3 − 1)/(10^0,1 − 1)))/acosh 3⌉ = 3;
    atenuação em ws = 10 log(1 + ε² T3(3)²), T3(3) = 4·27 − 3·3 = 99 → 34,05 dB."""
    eps2 = 10**0.1 - 1
    n = min_order("chebyshev", 3.0, 1.0, 30)
    assert n == math.ceil(math.acosh(math.sqrt((10**3 - 1) / eps2)) / math.acosh(3))
    assert n == 3
    _, p = prototype("chebyshev", 3, 1.0, 30)
    att = attenuation_db(np.array([]), p, 3.0)
    assert att == pytest.approx(10 * math.log10(1 + eps2 * 99**2), rel=1e-9)
    assert att == pytest.approx(34.05, abs=0.005)


def test_p25_ladder_elements():
    """Escada LC duplamente terminada: Butterworth n = 3 → g = 1, 2, 1 (gk = 2 sen((2k−1)π/2n));
    Chebyshev 0,5 dB n = 3 → g = 1,5963; 1,0967; 1,5963 (tabela de Chebyshev 0,5 dB)."""
    assert ladder_g("butterworth", 3, BUTTER_3DB) == pytest.approx([1.0, 2.0, 1.0], rel=REL)
    g5 = [2 * math.sin((2 * k - 1) * math.pi / 10) for k in range(1, 6)]
    assert ladder_g("butterworth", 5, BUTTER_3DB) == pytest.approx(g5, rel=REL)
    assert ladder_g("chebyshev", 3, 0.5) == pytest.approx([1.5963, 1.0967, 1.5963], rel=1e-4)


# ---------------------------------------------------------------- GT-OSC
def test_p26_wien_frequency(reviewed_catalogue):
    """Ponte de Wien: f0 = 1/(2πRC), ganho mínimo 3; f = 1 kHz, C = 10 nF → R = 15,9 kΩ
    (E96 15,8 kΩ) e f0 = 1 007 Hz."""
    s = design(reviewed_catalogue, "DM-OSC")
    assert s["f0_ideal"] == pytest.approx(1 / (2 * math.pi * s["R"] * s["C"]), rel=REL)
    assert s["A_min"] == pytest.approx(3.0, rel=REL)
    assert s["R"] == pytest.approx(15.8e3, rel=REL)


def test_p27_phase_shift_frequency(reviewed_catalogue):
    """Deslocamento de fase (três RC, ampop inversor): f0 = 1/(2π√6·RC), |A| ≥ 29; f = 1 kHz,
    C = 10 nF → R = 6,50 kΩ (E96 6,49 kΩ)."""
    s = design(reviewed_catalogue, "DM-OSC", config="deslocamento_fase")
    assert s["f0_ideal"] == pytest.approx(
        1 / (2 * math.pi * math.sqrt(6) * s["R"] * s["C"]), rel=REL
    )
    assert s["A_min"] == pytest.approx(29.0, rel=REL)
    assert s["A_loop"] >= 29


def test_p28_555_astable(reviewed_catalogue):
    """555 astável: tH = ln2·(RA + RB)C, tL = ln2·RB·C com os limiares 2/3 e 1/3 de VCC;
    f = 1 kHz, D = 60 %, C = 10 nF."""
    s = design(reviewed_catalogue, "DM-OSC", config="ne555_astavel")
    ln2 = math.log(2)
    assert s["tH"] == pytest.approx(ln2 * (s["RA"] + s["RB"]) * s["C"], rel=1e-3)
    assert s["tL"] == pytest.approx(ln2 * s["RB"] * s["C"], rel=1e-3)
    assert s["f0"] == pytest.approx(1 / (s["tH"] + s["tL"]), rel=REL)


def test_p29_bjt_multivibrator(reviewed_catalogue):
    """GT-OSC-MV-01, multivibrador astável simétrico: t = RB·C·ln((2VCC − VBE − VCE(sat))/
    (VCC − VBE)), T = 2t; VCC = 5 V, VBE = 0,65 V, VCE(sat) = 0,1 V → ln(9,25/4,35) = 0,7544."""
    s = design(reviewed_catalogue, "DM-OSC", config="multivibrador_tbj")
    k = math.log((2 * 5 - 0.65 - 0.1) / (5 - 0.65))
    assert k == pytest.approx(0.7544, rel=1e-4)
    assert s["T"] == pytest.approx(2 * s["RB1"] * s["C1"] * k, rel=REL)


# ---------------------------------------------------------------- GT-OPNL
def test_p30_schmitt_thresholds(reviewed_catalogue):
    """Schmitt inversor centrado em 0: VT± = ±β·Vsat, β = R2/(R1 + R2); histerese de 1 V com
    Vsat = 13,5 V → β = 0,037 → R1/R2 = 26 (E96 261 kΩ/10 kΩ)."""
    s = design(reviewed_catalogue, "DM-OPNL")
    beta = s["R2"] / (s["R1"] + s["R2"])
    assert s["VTp"] == pytest.approx(beta * s["Vo_hi"], rel=REL)
    assert s["VTn"] == pytest.approx(beta * s["Vo_lo"], rel=REL)
    assert s["VH_real"] == pytest.approx(s["VTp"] - s["VTn"], rel=REL)


def test_p31_precision_full_wave(reviewed_catalogue):
    """Retificador de precisão de onda completa (meia onda + somador): Vo,med = 2·Vm·G/π com
    resistores exatos; com os comerciais, G+ = R5(R2/(R1·R4) − 1/R3) e G− = R5/R3."""
    s = design(reviewed_catalogue, "DM-OPNL", config="retificador_onda")
    gp = s["R5"] * (s["R2"] / (s["R1"] * s["R4"]) - 1 / s["R3"])
    gn = s["R5"] / s["R3"]
    assert s["Vo_avg"] == pytest.approx(5 * (gp + gn) / math.pi, rel=REL)
    assert 2 * 5 * 1 / math.pi == pytest.approx(s["Vo_avg"], rel=5e-3)


def test_p32_log_amplifier(reviewed_catalogue):
    """Amplificador logarítmico com transdiodo: Vo = −VT ln(Iin/IS), Iin = Vin/R;
    inclinação −VT ln 10 = −59,5 mV por década a 300 K."""
    s = design(reviewed_catalogue, "DM-OPNL", config="logaritmico")
    assert s["Iin"] == pytest.approx(1.0 / s["R1"], rel=REL)
    assert s["slope"] == pytest.approx(-VT_300K * math.log(10), rel=REL)
    assert s["slope"] == pytest.approx(-59.53e-3, rel=1e-3)
