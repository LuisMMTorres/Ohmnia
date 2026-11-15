"""GT-P33..P49: Phase 5 power-electronics reference cases proposed for the user's check.

GT-CC-01..03, GT-CC-MCD-01, GT-CCI-01..02, GT-INV-01..03, GT-HARM-01, GT-INV-FLT-01,
GT-CACA-01..02, GT-CMD-01 (RC-DIAC trigger), GT-CMD-SNUB-01, GT-CMD-I2T-01 and GT-CMD-BOOT-01
of the scope. Textbook-style exercises solved in closed form: Hart, *Power Electronics*, 1st ed.,
ch. 5 (AC voltage controllers), ch. 6 (DC-DC converters), ch. 7 (DC power supplies), ch. 8
(inverters) and ch. 10 (snubbers); Erickson & Maksimović, 2nd ed., ch. 5 (discontinuous
conduction mode); Infineon/IR AN-978 (bootstrap). Like P8–P32 they are NOT copied from a
numbered worked example: the user confirms the numbers (or points to the book example) and the
docstring then gets the example and page. Table in docs/validacao/casos-referencia-propostos.md.

The converter cases run the analysis with ideal devices (no part chosen, so no drops) and check
the summary against the closed form; the protection cases use the reviewed catalogue, whose
datasheet values enter the formula.

Tolerance: 1e-9 relative for closed forms evaluated on the module's own values; 1e-6 for the
roots found numerically (β); 1e-3 for the fundamental of a PWM wave synthesised on 2¹⁷ samples
(natural sampling, mf = 21); 2e-3 for the Fourier series of the square wave from the FFT.
"""

import math

import numpy as np
import pytest

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.design.inverter import amplitudes, grid, square_harmonic
from circuitos.selection.derating import DeratingPolicy

REL = 1e-9


def q(v: float, u: str) -> dict[str, object]:
    return {"value": v, "unit": u}


def ideal(mid: str, **raw) -> dict[str, float]:
    """Summary of the analysis with ideal devices, in SI (percent kept as percent)."""
    mod = registry.get(mid)
    a = mod.analyse(mod.spec_schema(**raw), {})
    out = {}
    for k, v in a.summary.items():
        out[k] = float(v.to_base_units().magnitude) if str(v.units) != "percent" else v.magnitude
    return out


def design(repo, mid: str, **raw) -> dict[str, float]:
    mod = registry.get(mid)
    res, _ = run(
        mod,
        mod.spec_schema(**raw),
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    return {k: float(v.to_pint().to_base_units().magnitude) for k, v in res.summary.items()}


# ---------------------------------------------------------------- GT-CC
def test_p33_buck_ccm():
    """Buck MCC: Vin = 24 V, Vo = 12 V, Io = 2 A, fs = 50 kHz, ΔiL = 30 %, ΔVo = 1 %.
    D = Vo/Vin = 0,5; L = (Vin − Vo)D/(fs ΔiL) = 12·0,5/(50 k·0,6) = 200 µH;
    C ≥ ΔiL/(8 fs ΔVo) = 12,5 µF → 15 µF (E12) e ΔVo = ΔiL/(8 fs C) = 0,1 V."""
    s = ideal("DM-CC")
    assert s["D"] == pytest.approx(0.5, rel=REL)
    assert s["L1"] == pytest.approx(200e-6, rel=REL)
    assert s["dIL1"] == pytest.approx(0.6, rel=REL)
    assert s["C_o"] == pytest.approx(15e-6, rel=REL)
    assert s["dVo"] == pytest.approx(0.6 / (8 * 50e3 * 15e-6), rel=REL)


def test_p34_boost_ccm():
    """Boost MCC: 12 V → 24 V, 1 A: D = 1 − Vin/Vo = 0,5; IL = Io/(1 − D) = 2 A;
    L = Vin D/(fs ΔiL) = 12·0,5/(50 k·0,6) = 200 µH; ΔVo = Io D/(fs C)."""
    s = ideal("DM-CC", topology="boost", Vin=q(12, "V"), Vo=q(24, "V"), Io=q(1, "A"))
    assert s["D"] == pytest.approx(0.5, rel=REL)
    assert s["IL1"] == pytest.approx(2.0, rel=REL)
    assert s["L1"] == pytest.approx(200e-6, rel=REL)
    assert s["dVo"] == pytest.approx(1 * 0.5 / (50e3 * s["C_o"]), rel=REL)


def test_p35_buckboost_ccm():
    """Buck-boost MCC: 12 V → |Vo| = 24 V, 1 A: D = Vo/(Vin + Vo) = 2/3; IL = Io/(1 − D) = 3 A;
    L = Vin D/(fs ΔiL) = 12·(2/3)/(50 k·0,9) = 177,8 µH; ΔVo = Io D/(fs C)."""
    s = ideal("DM-CC", topology="buckboost", Vin=q(12, "V"), Vo=q(24, "V"), Io=q(1, "A"))
    assert s["D"] == pytest.approx(2 / 3, rel=1e-6)
    assert s["IL1"] == pytest.approx(3.0, rel=1e-6)
    assert s["L1"] == pytest.approx(12 * (2 / 3) / (50e3 * 0.9), rel=1e-6)
    assert s["dVo"] == pytest.approx(1 * (2 / 3) / (50e3 * s["C_o"]), rel=1e-6)


def test_p36_buck_dcm():
    """Buck MCD (Erickson ch. 5): L = 0,5·L_crit, L_crit = (1 − M)R/(2fs) = 30 µH;
    M = 2/(1 + √(1 + 4K/D²)), K = 2L/(R Ts) = 0,25 → D = 1/√8 = 0,3536;
    i_pk = (Vin − Vo)D/(L fs)."""
    s = ideal("DM-CC", mode="MCD")
    assert s["L_crit"] == pytest.approx((1 - 0.5) * 6 / (2 * 50e3), rel=REL)
    assert s["L1"] == pytest.approx(15e-6, rel=REL)
    assert s["D"] == pytest.approx(1 / math.sqrt(8), rel=1e-6)
    assert s["IL1_pk"] == pytest.approx(12 * s["D"] / (15e-6 * 50e3), rel=1e-6)


# ---------------------------------------------------------------- GT-CCI
def test_p37_flyback():
    """Flyback: Vin = 48 V, Vo = 12 V, D = 0,4: Vo = Vin (Ns/Np) D/(1 − D) → Ns/Np = 0,375;
    I_m,pk = I_m + ΔI_m/2 com I_m = Io·n/(1 − D)."""
    s = ideal("DM-CCI")
    assert s["n"] == pytest.approx(12 * 0.6 / (48 * 0.4), rel=REL)
    assert s["D"] == pytest.approx(0.4, rel=1e-6)
    im = 2 * s["n"] / (1 - s["D"])
    assert s["Im_pk"] == pytest.approx(im * (1 + 0.3 / 2), rel=1e-6)


def test_p38_forward():
    """Forward: Vo = Vin (Ns/Np) D → Ns/Np = 12/(48·0,4) = 0,625;
    L_o = (Vin n − Vo) D/(fs ΔiL) = (30 − 12)·0,4/(50 k·0,6) = 240 µH."""
    s = ideal("DM-CCI", topology="forward")
    assert s["n"] == pytest.approx(0.625, rel=REL)
    assert s["L_o"] == pytest.approx(240e-6, rel=1e-6)


# ---------------------------------------------------------------- GT-INV / GT-HARM
def test_p39_square_wave():
    """Onda quadrada monofásica ±Vdc (ponte completa), Vdc = 400 V, sem tempo morto:
    V1 = 4Vdc/(π√2) = 360,1 V; V_rms = Vdc; THD = √(π²/8 − 1) = 48,34 %."""
    s = ideal("DM-INV", modulation="quadrada", dead_time=q(0, "us"))
    assert s["V1"] == pytest.approx(4 * 400 / (math.pi * math.sqrt(2)), rel=2e-3)
    assert s["V_rms"] == pytest.approx(400, rel=1e-6)
    assert s["THD_v"] == pytest.approx(100 * math.sqrt(math.pi**2 / 8 - 1), rel=2e-3)


def test_p40_spwm_bipolar():
    """SPWM bipolar, ma = 0,8, mf = 21: V1 = ma Vdc/√2 = 226,3 V; sem harmônicos de baixa ordem
    (os primeiros ficam em torno de mf)."""
    s = ideal("DM-INV", modulation="spwm_bipolar", dead_time=q(0, "us"))
    assert s["V1"] == pytest.approx(0.8 * 400 / math.sqrt(2), rel=1e-3)


def test_p41_spwm_unipolar_cancels_mf():
    """SPWM unipolar: os harmônicos em mf se cancelam entre as pernas; os primeiros ficam em
    2mf ± 1 (Hart ch. 8). V1 = ma Vdc/√2."""
    s = ideal("DM-INV", modulation="spwm_unipolar", dead_time=q(0, "us"))
    assert s["V1"] == pytest.approx(0.8 * 400 / math.sqrt(2), rel=1e-3)
    from circuitos.design.inverter import leg_voltages, load_voltages, switching

    th = grid(2**15)
    legs = switching("spwm_unipolar", 1, 0.8, 21, 0.0, th)
    v = load_voltages(1, leg_voltages(legs, 400.0))[0]
    a = amplitudes(v)
    assert a[21] < 1e-3 * a[1]
    assert a[41] > 0.05 * a[1]


def test_p42_square_wave_fourier_series():
    """GT-HARM-01: série de Fourier da onda quase quadrada, V_n = 4Vdc/(nπ)·cos(nα), α = 30°:
    o 3º harmônico se anula; FFT da forma sintetizada confere até n = 15."""
    th = grid(2**15)
    alpha = math.radians(30)
    v = np.where((th > alpha) & (th < math.pi - alpha), 1.0, 0.0) - np.where(
        (th > math.pi + alpha) & (th < 2 * math.pi - alpha), 1.0, 0.0
    )
    a = amplitudes(v)
    for n in range(1, 16):
        assert a[n] == pytest.approx(abs(square_harmonic(1.0, n, alpha)), abs=2e-3)
    assert square_harmonic(1.0, 3, alpha) == pytest.approx(0.0, abs=1e-12)


def test_p43_output_filter():
    """GT-INV-FLT-01: filtro LC de saída: fc = 1/(2π√(Lf Cf)), com Cf comercial (E12)
    próximo de 1/((2π·fc_ratio·fs)² Lf)."""
    s = ideal("DM-INV", modulation="spwm_bipolar", filter=True, mf=201)
    assert s["fc_f"] == pytest.approx(1 / (2 * math.pi * math.sqrt(s["Lf"] * s["Cf"])), rel=REL)
    target = 1 / ((2 * math.pi * 0.2 * s["fs"]) ** 2 * s["Lf"])
    assert 0.8 < s["Cf"] / target < 1.25  # one E12 step either side


# ---------------------------------------------------------------- GT-CACA / GT-CMD-01
def test_p44_ac_controller_r_load():
    """GT-CACA-01: gradador com carga R, Vs = 220 V, α = 90°:
    Vo = Vs √(1 − α/π + sin 2α/(2π)) = 220/√2 = 155,6 V; FP = Vo/Vs = 0,707."""
    s = ideal("DM-CACA")
    assert s["Vo_ideal"] == pytest.approx(220 / math.sqrt(2), rel=REL)
    assert s["Vo_rms"] == pytest.approx(220 / math.sqrt(2), rel=1e-4)
    assert s["PF"] == pytest.approx(1 / math.sqrt(2), rel=1e-4)


def test_p45_ac_controller_rl_load():
    """GT-CACA-02: gradador com carga RL, R = 50 Ω, L = 100 mH, 60 Hz, α = 90°:
    θ = atan(ωL/R) = 37,0°; β da equação sin(β − θ) = sin(α − θ) e^{(α − β)/(ωτ)};
    Vo = Vs √{[(β − α) − (sin 2β − sin 2α)/2]/π}."""
    s = ideal("DM-CACA", L=q(100, "mH"))
    w = 2 * math.pi * 60
    th = math.atan(w * 0.1 / 50)
    a, b = math.pi / 2, s["beta"]
    assert s["theta_z"] == pytest.approx(th, rel=REL)
    assert math.sin(b - th) == pytest.approx(
        math.sin(a - th) * math.exp((a - b) / (w * 0.1 / 50)), abs=1e-6
    )
    vo = 220 * math.sqrt(((b - a) - (math.sin(2 * b) - math.sin(2 * a)) / 2) / math.pi)
    assert s["Vo_rms"] == pytest.approx(vo, rel=1e-4)


def test_p46_rc_diac_trigger():
    """GT-CMD-01: disparo por rede RC + DIAC, R = 100 kΩ, C = 100 nF, V_BO = 32 V, 220 V/60 Hz:
    k = 1/√(1 + (ωRC)²) = 0,0663, φ = atan(ωRC) = 86,2°, α = φ + asin(V_BO/(Vm k)) = 98,8°."""
    s = ideal("DM-CACA", trigger="diac")
    x = 2 * math.pi * 60 * 100e3 * 100e-9
    k = 1 / math.sqrt(1 + x * x)
    alpha = math.atan(x) + math.asin(32 / (220 * math.sqrt(2) * k))
    assert s["k_rc"] == pytest.approx(k, rel=REL)
    assert s["alpha"] == pytest.approx(alpha, rel=REL)
    assert math.degrees(alpha) == pytest.approx(98.79, abs=0.01)


# ---------------------------------------------------------------- GT-CMD
def test_p47_rcd_snubber(reviewed_catalogue):
    """GT-CMD-SNUB-01: snubber RCD de desligamento, Vbus = 311 V, Io = 10 A, t_f do IGBT escolhido:
    C_s = Io t_f/(2 Vbus); E = Io² t_f²/(24 C_s) + V_F Io t_f/2; P_R = ½ C_s Vbus² fs."""
    s = design(reviewed_catalogue, "DM-CMD")
    tf = 2 * s["C_s_min"] * 311 / 10
    assert tf > 0
    assert s["E_off0"] == pytest.approx(0.5 * 311 * 10 * tf, rel=REL)
    assert s["P_Rs"] == pytest.approx(0.5 * s["C_s"] * 311**2 * 20e3, rel=REL)
    assert s["E_off"] < s["E_off0"] / 5
    assert s["R_s"] <= 0.05 / 20e3 / (5 * s["C_s"])


def test_p48_fuse_i2t(reviewed_catalogue):
    """GT-CMD-I2T-01: o I²t de interrupção do fusível deve ficar abaixo do I²t da ponte; com
    20 A²s contra a ponte escolhida não há aviso; com 10⁴ A²s o aviso aparece."""
    mod = registry.get("DM-CMD")
    pol = DeratingPolicy.from_preset("didatico")
    ok, _ = run(
        mod,
        mod.spec_schema(),
        lambda c: reviewed_catalogue.search(category=c),
        reviewed_catalogue.get,
        pol,
    )
    assert ok.summary["I2t_bridge"].value > 20
    assert all(w.code != "fusivel_i2t" for w in ok.warnings)
    bad, _ = run(
        mod,
        mod.spec_schema(fuse_I2t=q(1e4, "A**2*s")),
        lambda c: reviewed_catalogue.search(category=c),
        reviewed_catalogue.get,
        pol,
    )
    assert any(w.code == "fusivel_i2t" for w in bad.warnings)


def test_p49_bootstrap_ir2110(reviewed_catalogue):
    """GT-CMD-BOOT-01: capacitor de bootstrap do IR2110 (AN-978):
    C ≥ 2[2Qg + I_QBS/f + Q_ls]/(V_CC − V_F − V_LS − V_Min), com Qg do IGBT, I_QBS e V_BSUV− do
    IR2110, V_F do diodo de bootstrap e V_LS = V_CE(sat)."""
    mod = registry.get("DM-CMD")
    res, _ = run(
        mod,
        mod.spec_schema(),
        lambda c: reviewed_catalogue.search(category=c),
        reviewed_catalogue.get,
        DeratingPolicy.from_preset("didatico"),
    )
    parts = {c.designator: c.part_number for c in res.selection}
    assert parts["U1"] == "IR2110"
    step = next(st for st in res.steps if st.id == "C_boot_min")
    i = {k: v.to_pint().to_base_units().magnitude for k, v in step.inputs.items()}
    c = (
        2
        * (2 * i["Q_g"] + i["I_QBS"] / 20e3 + i["Q_ls"])
        / (15 - i["V_F"] - i["V_LS"] - i["V_Min"])
    )
    assert res.summary["C_boot_min"].to_pint().m_as("F") == pytest.approx(c, rel=REL)
    assert res.summary["C_boot"].to_pint().m_as("F") >= 10 * c
