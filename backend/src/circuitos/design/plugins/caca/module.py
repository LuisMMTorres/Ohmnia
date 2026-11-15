"""DM-CACA: single-phase AC voltage controller with a TRIAC (or two antiparallel SCRs).

Phase control, resistive load: V_o,rms = V_s·√(1 − α/π + sin 2α/(2π)) (Hart, *Power
Electronics*, 1st ed., ch. 5, AC voltage controllers). RL load: the current
i(ωt) = (V_m/Z)[sin(ωt − θ) − sin(α − θ)·e^{(α − ωt)/(ωτ)}] flows until the extinction angle β
(i(β) = 0, solved numerically); for α ≤ θ the conduction is continuous and the load sees the
whole source voltage. Integral-cycle control: n of every N cycles,
V_o,rms = V_s·√(n/N). DIAC trigger: the RC network across the controller gives
v_C = V_m·k·sin(ωt − φ), k = 1/√(1 + (ωRC)²), φ = atan(ωRC); the DIAC breaks over at
α = φ + asin(V_BO/(V_m k)).

The waveforms are computed on a fine grid with the on-state drop of the chosen part (constant
V_TM), so the harmonics of the load current come from the FFT.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pint
from numpy.typing import NDArray
from pydantic import BaseModel, Field, model_validator
from scipy.optimize import brentq
from scipy.signal import lfilter

from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.base import (
    Circuit,
    DesignResult,
    DesignWarning,
    Role,
    SimCheck,
    Stress,
    make_trace,
)
from circuitos.design.engine import Analysis, Device
from circuitos.design.inverter import amplitudes, thd
from circuitos.design.plugins.retc1.module import scr_model
from circuitos.reports.common import BomRow, LabItem, passive
from circuitos.reports.schematic import value_sheet

HART5 = BibRef(book="Hart, Power Electronics", edition="1st", chapter="5 (AC voltage controllers)")
N = 2**14  # samples per source cycle
FloatArray = NDArray[np.float64]


class CacaSpec(BaseModel):
    control: Literal["fase", "ciclo_integral"] = "fase"
    trigger: Literal["angulo", "diac"] = "angulo"
    Vs: QuantityModel = QuantityModel(value=220, unit="V")  # rms
    f: QuantityModel = QuantityModel(value=60, unit="Hz")
    R: QuantityModel = QuantityModel(value=50, unit="ohm")
    L: QuantityModel = QuantityModel(value=0, unit="mH")
    alpha_deg: float = Field(default=90, ge=0, lt=180)
    n_on: int = Field(default=3, ge=1, le=100)
    N_cycles: int = Field(default=6, ge=1, le=100)
    R_trig: QuantityModel = QuantityModel(value=100, unit="kohm")  # DIAC network (pot + fixed)
    C_trig: QuantityModel = QuantityModel(value=100, unit="nF")
    V_BO: QuantityModel = QuantityModel(value=32, unit="V")  # DIAC breakover (user data)
    TA: QuantityModel = QuantityModel(value=40, unit="degC")

    @model_validator(mode="after")
    def _check(self) -> CacaSpec:
        if self.n_on > self.N_cycles:
            raise ValueError("n ≤ N no controle por ciclos inteiros")
        if self.control == "ciclo_integral" and self.trigger == "diac":
            raise ValueError("O disparo por DIAC é de controle de fase")
        return self


LABELS = {
    "alpha": "Ângulo de disparo α",
    "beta": "Ângulo de extinção β",
    "theta_z": "Ângulo da impedância θ",
    "Vo_rms": "Tensão eficaz na carga",
    "Io_rms": "Corrente eficaz",
    "Po": "Potência na carga",
    "PF": "Fator de potência na fonte",
    "THD_i": "THD da corrente (harmônicos da rede)",
    "I1": "Corrente fundamental (eficaz)",
    "IT_rms": "Corrente eficaz no TRIAC",
    "VDRM": "Tensão de pico bloqueada",
    "P_T1": "Perda no TRIAC",
    "k_rc": "Atenuação da rede RC (DIAC)",
    "phi_rc": "Atraso da rede RC (DIAC)",
}
SPEC_LABELS = {
    "control": "Controle",
    "trigger": "Disparo",
    "Vs": "Tensão da rede (eficaz)",
    "f": "Frequência da rede",
    "R": "Resistência da carga",
    "L": "Indutância da carga",
    "alpha_deg": "Ângulo de disparo α (°)",
    "n_on": "Ciclos ligados n",
    "N_cycles": "Ciclos do período de controle N",
    "R_trig": "Resistência da rede de disparo",
    "C_trig": "Capacitor da rede de disparo",
    "V_BO": "Tensão de disparo do DIAC (V_BO, dado do usuário)",
}
ENUM_LABELS = {
    "fase": "controle de fase",
    "ciclo_integral": "ciclos inteiros",
    "angulo": "ângulo imposto",
    "diac": "rede RC + DIAC",
}


def _spec(spec: BaseModel) -> CacaSpec:
    if not isinstance(spec, CacaSpec):
        raise TypeError("DM-CACA espera CacaSpec")
    return spec


def _v(x: QuantityModel, unit: str) -> float:
    return float(x.to_pint().m_as(unit))


def extinction(alpha: float, theta: float, wtau: float, kv: float = 0.0) -> float:
    """β with i(β) = 0 after α for the RL load, with the on-state drop as kv = V_T·Z/(V_m·R);
    α + π when α ≤ θ (continuous conduction)."""
    if wtau <= 0:
        return math.pi
    if alpha <= theta:
        return alpha + math.pi

    def i(x: float) -> float:
        e = math.exp((alpha - x) / wtau)
        return math.sin(x - theta) - math.sin(alpha - theta) * e - kv * (1 - e)

    return float(brentq(i, alpha + 1e-9, alpha + math.pi))


def _rl_pulse(
    x: FloatArray,
    alpha: float,
    beta: float,
    vm: float,
    vt: float,
    R: float,
    z: float,
    theta: float,
    wtau: float,
) -> FloatArray:
    """Positive current pulse on [α, β] of the RL load with constant drop V_T (Hart ch. 5,
    plus the particular solution −V_T/R of the drop)."""
    e = np.exp((alpha - x) / wtau)
    val = (vm / z) * (np.sin(x - theta) - math.sin(alpha - theta) * e) - (vt / R) * (1 - e)
    return np.asarray(np.where((x >= alpha) & (x <= beta), val, 0.0), dtype=np.float64)


def _burst_rl(
    th: FloatArray, vs: FloatArray, n_on: int, vt: float, R: float, L: float, w: float
) -> FloatArray:
    """Integral-cycle current with RL load: the switch closes at θ = 0 with zero current, the
    gates are held for n cycles and the conduction ends at the next current zero. Exact
    first-order recurrence (zero-order hold of the input), the drop sign taken from the
    previous iterate."""
    h = float(th[1] - th[0]) / w
    a = math.exp(-R * h / L)
    b = (1 - a) / R
    sign = np.sign(vs)
    i = np.zeros_like(vs)
    for _ in range(4):
        u = vs - sign * vt
        i = np.asarray(lfilter([0.0, b], [1.0, -a], u), dtype=np.float64)
        k_off = int(np.searchsorted(th, 2 * math.pi * n_on))
        after = np.nonzero(np.sign(i[k_off:]) != np.sign(i[k_off]))[0]
        end = k_off + (int(after[0]) if after.size else i.size - k_off)
        i[end:] = 0.0
        sign = np.where(i != 0, np.sign(i), sign)
    return i


def waveforms(
    s: CacaSpec, alpha: float, vt: float
) -> tuple[FloatArray, FloatArray, FloatArray, int]:
    """(θ, v_load, i, number of source cycles in the window) on a fine grid."""
    vm = _v(s.Vs, "V") * math.sqrt(2)
    w = 2 * math.pi * _v(s.f, "Hz")
    R, L = _v(s.R, "ohm"), _v(s.L, "H")
    cycles = s.N_cycles if s.control == "ciclo_integral" else 1
    th = np.asarray(2 * math.pi * np.arange(N * cycles) / N, dtype=np.float64)
    vs = vm * np.sin(th)
    sgn = np.sign(vs)
    if s.control == "ciclo_integral":
        if L > 0:
            i = _burst_rl(th, vs, s.n_on, vt, R, L, w)
            v = np.where(i != 0, vs - np.sign(i) * vt, 0.0)
            return th, np.asarray(v, dtype=np.float64), i, cycles
        on = (th < 2 * math.pi * s.n_on) & (np.abs(vs) > vt)
        v = np.where(on, vs - sgn * vt, 0.0)
        return th, np.asarray(v, dtype=np.float64), np.asarray(v / R, dtype=np.float64), cycles
    if L == 0:
        cond = (th % math.pi >= alpha) & (np.abs(vs) > vt)
        v = np.where(cond, vs - sgn * vt, 0.0)
        return th, np.asarray(v, dtype=np.float64), np.asarray(v / R, dtype=np.float64), cycles
    z = math.hypot(R, w * L)
    th_z = math.atan2(w * L, R)
    wtau = w * L / R
    beta = extinction(alpha, th_z, wtau, vt * z / (vm * R))
    if beta >= alpha + math.pi - 1e-12:
        # continuous conduction: the load sees the whole source (drop neglected)
        return th, vs, np.asarray((vm / z) * np.sin(th - th_z), dtype=np.float64), cycles
    i = _rl_pulse(th, alpha, beta, vm, vt, R, z, th_z, wtau) - _rl_pulse(
        (th - math.pi) % (2 * math.pi), alpha, beta, vm, vt, R, z, th_z, wtau
    )
    v = np.where(i != 0, vs - np.sign(i) * vt, 0.0)
    return th, np.asarray(v, dtype=np.float64), i, cycles


class CacaModule:
    id = "DM-CACA"
    family = "potencia"
    title = "Controladores de tensão CA"
    spec_schema = CacaSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão eficaz na carga", "multímetro de valor eficaz verdadeiro", "Vo_rms"),
        LabItem("Ângulo de disparo", "osciloscópio (ponteira diferencial)", "alpha"),
        LabItem("Corrente eficaz", "alicate de valor eficaz verdadeiro", "Io_rms"),
    ]
    questions = [
        "Por que o fator de potência cai com o aumento de α mesmo numa carga resistiva?",
        "Com carga RL, o que acontece quando α < θ?",
        "Compare os harmônicos do controle de fase e do controle por ciclos inteiros.",
    ]
    safety = [
        "Circuito ligado diretamente à rede: use transformador de isolação ou ponteira "
        "diferencial; nunca aterre o osciloscópio num ponto do circuito.",
    ]

    def roles(self, spec: BaseModel) -> list[Role]:
        return [Role(designator="T1", category="thyristor.triac", description="TRIAC")]

    def required_ratings(self, role: Role) -> list[str]:
        return ["VDRM", "IT(RMS)"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    def _alpha(self, s: CacaSpec, log: CalcLog) -> float:
        if s.control == "ciclo_integral":
            return 0.0
        if s.trigger == "angulo":
            a = math.radians(s.alpha_deg)
            log.add(
                record(
                    "alpha",
                    "Ângulo de disparo imposto",
                    r"\alpha",
                    output=Q_(s.alpha_deg, "degree"),
                )
            )
            return a
        vm = _v(s.Vs, "V") * math.sqrt(2)
        w = 2 * math.pi * _v(s.f, "Hz")
        rc = _v(s.R_trig, "ohm") * _v(s.C_trig, "F")
        k = 1 / math.sqrt(1 + (w * rc) ** 2)
        phi = math.atan(w * rc)
        vbo = _v(s.V_BO, "V")
        if vbo >= vm * k:
            raise ValueError(
                f"A rede RC entrega no máximo {vm * k:.1f} V ao DIAC, abaixo de V_BO: reduza R ou C"
            )
        a = phi + math.asin(vbo / (vm * k))
        if a >= math.pi:
            raise ValueError("O disparo cairia depois do fim do semiciclo: reduza R ou C")
        log.add(
            record(
                "k_rc",
                "Rede RC de disparo: atenuação e atraso",
                r"k = \frac{1}{\sqrt{1 + (\omega RC)^2}},\; \varphi = \arctan(\omega RC)",
                output=Q_(k, ""),
                inputs={"R": s.R_trig.to_pint(), "C": s.C_trig.to_pint(), "f": s.f.to_pint()},
                assumptions=[
                    "o DIAC não carrega o capacitor antes do disparo",
                    "rede alimentada pela tensão sobre o TRIAC bloqueado ≈ v_s",
                ],
                reference=HART5,
            )
        )
        log.add(
            record(
                "alpha",
                "Ângulo de disparo pelo DIAC",
                r"\alpha = \varphi + \arcsin\frac{V_{BO}}{V_m k}",
                output=Q_(math.degrees(a), "degree"),
                inputs={
                    "φ": Q_(math.degrees(phi), "degree"),
                    "V_BO": s.V_BO.to_pint(),
                    "V_m": Q_(vm, "V"),
                },
                assumptions=["V_BO informado pelo usuário (não há DIAC no catálogo)"],
                reference=HART5,
            )
        )
        self._rc = (k, phi)
        return a

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vs = _v(s.Vs, "V")
        vm = vs * math.sqrt(2)
        w = 2 * math.pi * _v(s.f, "Hz")
        R, L = _v(s.R, "ohm"), _v(s.L, "H")
        vt = devices["T1"].drop.m_as("V") if "T1" in devices else 0.0
        a = self._alpha(s, log)
        sm: dict[str, pint.Quantity] = {}
        if s.control == "fase":
            sm["alpha"] = Q_(math.degrees(a), "degree")
            if s.trigger == "diac":
                sm |= {
                    "k_rc": Q_(self._rc[0], ""),
                    "phi_rc": Q_(math.degrees(self._rc[1]), "degree"),
                }
        th, v, i, cycles = waveforms(s, a, vt)
        vo = float(np.sqrt(np.mean(v**2)))
        io = float(np.sqrt(np.mean(i**2)))
        if s.control == "fase" and L == 0:
            vo_cf = vs * math.sqrt(1 - a / math.pi + math.sin(2 * a) / (2 * math.pi))
            log.add(
                record(
                    "Vo_ideal",
                    "Tensão eficaz na carga resistiva (ideal)",
                    r"V_{o,rms} = V_s\sqrt{1 - \frac{\alpha}{\pi} + \frac{\sin 2\alpha}{2\pi}}",
                    output=Q_(vo_cf, "V"),
                    inputs={"V_s": s.Vs.to_pint(), "α": Q_(math.degrees(a), "degree")},
                    reference=HART5,
                )
            )
            sm["Vo_ideal"] = Q_(vo_cf, "V")
        elif s.control == "ciclo_integral":
            vo_cf = vs * math.sqrt(s.n_on / s.N_cycles)
            log.add(
                record(
                    "Vo_ideal",
                    "Tensão eficaz por ciclos inteiros (ideal)",
                    r"V_{o,rms} = V_s\sqrt{n/N}",
                    output=Q_(vo_cf, "V"),
                    inputs={"n": Q_(s.n_on, ""), "N": Q_(s.N_cycles, "")},
                    reference=HART5,
                )
            )
            sm["Vo_ideal"] = Q_(vo_cf, "V")
        if s.control == "fase" and L > 0:
            th_z = math.atan2(w * L, R)
            beta = extinction(a, th_z, w * L / R, vt * math.hypot(R, w * L) / (vm * R))
            log.add(
                record(
                    "beta",
                    "Ângulo de extinção da corrente (carga RL)",
                    r"\sin(\beta - \theta)"
                    r" - \sin(\alpha - \theta)\,e^{(\alpha - \beta)/(\omega\tau)}"
                    r" - \frac{V_T Z}{V_m R}\left(1 - e^{(\alpha - \beta)/(\omega\tau)}\right) = 0",
                    output=Q_(math.degrees(min(beta, a + math.pi)), "degree"),
                    inputs={"θ": Q_(math.degrees(th_z), "degree"), "ωτ": Q_(w * L / R, "")},
                    assumptions=["α ≤ θ: condução contínua (β = α + 180°)"],
                    reference=HART5,
                )
            )
            sm |= {
                "beta": Q_(math.degrees(beta), "degree"),
                "theta_z": Q_(math.degrees(th_z), "degree"),
            }
            if a <= th_z:
                warnings.append(
                    DesignWarning(
                        code="conducao_continua",
                        message="α ≤ θ: o TRIAC conduz continuamente e a carga recebe "
                        "toda a tensão "
                        "(sem controle).",
                    )
                )
        log.add(
            record(
                "Vo_rms",
                "Tensão e corrente eficazes (forma de onda com a queda V_TM)",
                r"V_{o,rms} = \sqrt{\frac{1}{T}\int v_o^2\,dt}",
                output=Q_(vo, "V"),
                inputs={"V_TM": Q_(vt, "V")},
                assumptions=["queda constante V_TM do datasheet durante a condução"],
                reference=HART5,
            )
        )
        po = float(np.mean(i**2)) * R
        vsrc = vm * np.sin(th)
        pf = float(np.mean(vsrc * i)) / (vs * io) if io > 0 else 0.0
        amp = amplitudes(i)
        if cycles == 1:
            i1 = float(amp[1]) / math.sqrt(2)
            thd_i = thd(amp)
        else:
            i1 = float(amp[cycles]) / math.sqrt(2)  # line frequency in an N-cycle window
            h = np.delete(amp[1:], cycles - 1)
            thd_i = float(np.sqrt(np.sum(h**2))) / float(amp[cycles])
        log.add(
            record(
                "PF",
                "Fator de potência na fonte",
                r"FP = \frac{P}{V_s I_{rms}}",
                output=Q_(pf, ""),
                inputs={"P": Q_(po, "W"), "I_rms": Q_(io, "A")},
                reference=HART5,
            )
        )
        it_avg = float(np.mean(np.abs(i))) / 2
        p_t = vt * 2 * it_avg
        sm |= {
            "Vo_rms": Q_(vo, "V"),
            "Io_rms": Q_(io, "A"),
            "Po": Q_(po, "W"),
            "PF": Q_(pf, ""),
            "THD_i": Q_(100 * thd_i, "percent"),
            "I1": Q_(i1, "A"),
            "IT_rms": Q_(io, "A"),
            "VDRM": Q_(vm, "V"),
            "P_T1": Q_(p_t, "W"),
        }
        log.add(
            record(
                "P_T1",
                "Perda no TRIAC",
                r"P = V_{TM}\,\overline{|i|}",
                output=Q_(p_t, "W"),
                inputs={"V_TM": Q_(vt, "V")},
                reference=HART5,
            )
        )
        stresses = [
            Stress(
                designator="T1",
                key="VDRM",
                label="Tensão de pico da rede",
                value=QuantityModel(value=vm, unit="V"),
                calc_step_id="Vo_rms",
            ),
            Stress(
                designator="T1",
                key="IT(RMS)",
                label="Corrente eficaz",
                value=QuantityModel(value=io, unit="A"),
                calc_step_id="Vo_rms",
            ),
        ]
        period = cycles / _v(s.f, "Hz")
        return Analysis(
            log=log,
            stresses=stresses,
            summary=sm,
            losses={"T1": Q_(p_t, "W")},
            warnings=warnings,
            convergence_keys=("Io_rms",),
            traces={"v_carga": make_trace("V", v), "i_carga": make_trace("A", i)},
            trace_period=Q_(period, "s"),
        )

    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        vs = _v(s.Vs, "V")
        f = _v(s.f, "Hz")
        T = 1 / f
        R, L = _v(s.R, "ohm"), _v(s.L, "H")
        vt = devices["T1"].drop.m_as("V") if "T1" in devices else 0.0
        lines = [
            scr_model(vt),
            f"VS a 0 SIN(0 {vs * math.sqrt(2):.9g} {f:.9g})",
            "XTA a k ga SCR",
            "XTB k a gb SCR",
            f"RL k m {R:.9g}",
        ]
        lines += [f"LL m x {L:.9g}", "VIO x 0 0"] if L > 0 else ["VIO m 0 0"]
        if s.control == "fase":
            a = summary["alpha"].to_pint().m_as("rad")
            t0 = a / (2 * math.pi * f)
            width = T / 2 - t0 - T / 200  # gate held to the end of the half cycle
            lines += [
                f"VGA ga 0 PULSE(0 5 {t0:.9g} 1n 1n {width:.9g} {T:.9g})",
                f"VGB gb 0 PULSE(0 5 {t0 + T / 2:.9g} 1n 1n {width:.9g} {T:.9g})",
            ]
            period = T
            n_per = 6 if L == 0 else int(min(40, 6 + 5 * (L / R) / T))
        else:
            period = s.N_cycles * T
            on = s.n_on * T
            lines += [
                f"VGA ga 0 PULSE(0 5 0 1n 1n {on - T / 2:.9g} {period:.9g})",
                f"VGB gb 0 PULSE(0 5 {T / 2:.9g} 1n 1n {on - T / 2:.9g} {period:.9g})",
            ]
            n_per = 3
        checks = [
            SimCheck(
                quantity="Tensão eficaz na carga",
                summary_key="Vo_rms",
                metric="rms",
                probe="v(k)",
                tolerance_pct=1.0,
                justification="mesmo modelo de queda constante",
            ),
            SimCheck(
                quantity="Corrente eficaz",
                summary_key="Io_rms",
                metric="rms",
                probe="i(vio)",
                tolerance_pct=1.0,
                justification="mesmo modelo de queda constante",
            ),
        ]
        if s.control == "fase":
            checks.append(
                SimCheck(
                    quantity="Fator de potência",
                    summary_key="PF",
                    metric="pf",
                    probe="i(vio)",
                    voltage="v(a)",
                    tolerance_pct=2.0,
                    justification="valor médio do produto na janela",
                )
            )
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[s.control]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=n_per * period, unit="s"),
            tran_step=QuantityModel(value=T / 4000, unit="s"),
            period=QuantityModel(value=period, unit="s"),
            probes={"v_carga": "v(k)", "i_carga": "i(vio)"},
            checks=checks,
        )

    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        vals: dict[str, str] = {
            k: format_eng(sm[k].to_pint()) for k in ("alpha", "Vo_rms", "Io_rms") if k in sm
        }
        parts = {c.designator: c.part_number for c in result.selection}
        return value_sheet(
            title, ENUM_LABELS[s.control] + " (" + ENUM_LABELS[s.trigger] + ")", vals, parts
        )

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        rows = []
        if s.trigger == "diac" and s.control == "fase":
            rows += [
                passive(
                    "R_trig",
                    "Resistência da rede de disparo (potenciômetro + fixo)",
                    format_eng(s.R_trig.to_pint()),
                ),
                passive(
                    "C_trig",
                    "Capacitor da rede de disparo",
                    format_eng(s.C_trig.to_pint()),
                    "filme, tensão ≥ 250 V CA",
                ),
                passive(
                    "DIAC",
                    "DIAC",
                    f"V_BO = {s.V_BO.value:g} V",
                    "escolher pelo datasheet (não há DIAC no catálogo)",
                ),
            ]
        return rows
