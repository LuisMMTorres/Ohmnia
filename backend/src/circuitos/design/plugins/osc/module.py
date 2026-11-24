"""DM-OSC: oscillators, multivibrators and the 555 timer.

Closed forms:

* Wien bridge: f0 = 1/(2πRC), oscillation when 1 + Rf/Rg = 3; the gain is set slightly above 3
  and two antiparallel diodes across R4 (part of Rf) bring it back to 3. The output peak where
  the diodes start to conduct is Vo = 1,5·VF·(R3 + R4)/R4 (Sedra & Smith, *Microelectronic
  Circuits*, 7th ed., ch. 18 "Signal generators and waveform-shaping circuits", Wien-bridge
  oscillator with diode limiter, same reasoning as its example);
* RC phase shift (three CR sections, the last R at the virtual ground of the inverting
  amplifier): f0 = 1/(2π√6·RC), |A| ≥ 29 (Boylestad & Nashelsky, *Electronic Devices and Circuit
  Theory*, 11th ed., ch. 14 "Feedback and oscillator circuits"); the amplitude is limited by the
  op-amp saturation;
* op-amp astable (Schmitt + RC): t_H = RC·ln((V_H − βV_L)/((1 − β)V_H)), t_L likewise, β =
  R2/(R1 + R2), V_H/V_L the saturation levels (Sedra & Smith, ch. 18), plus the slewing time
  of each edge (V_H − V_L)/SR;
* 555 astable: t_H = (RA + RB)C·ln((VCC − V_trig)/(VCC − V_thres)), t_L = RB·C·ln(V_thres/V_trig)
  and monostable t_w = RC·ln(VCC/(VCC − V_thres)), with the comparator thresholds of the
  datasheet (TI NE555, SLFS022K; 1,1RC for the nominal 2/3 VCC);
* BJT astable multivibrator: each half period t = RB·C·ln((2VCC − VBE − VCE(sat))/(VCC − VBE))
  (≈ 0,693 RB·C) (Boylestad & Nashelsky, ch. on multivibrators; Millman & Halkias).

The simulation uses the op-amp macromodel with slew rate and output clamp, the constant-drop
diode of the chosen part, a behavioural 555 (two comparators at the datasheet thresholds, a
latch and the discharge switch) and the Ebers-Moll transistors of the analysis.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pint
from pydantic import BaseModel, Field
from scipy.optimize import brentq

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.analog import commercial
from circuitos.design.base import (
    Circuit,
    DesignResult,
    DesignWarning,
    Role,
    SimCheck,
    Stress,
    Trace,
    make_trace,
)
from circuitos.design.devmodels import VT_300K, bjt_model, quantity
from circuitos.design.engine import Analysis, Device
from circuitos.design.mna import Circuit as Mna
from circuitos.design.opamp import REF as OPA_REF
from circuitos.design.opamp import TRAN_OPTIONS, OpAmp, opamp_model
from circuitos.design.plugins.opnl.module import diode_subckt
from circuitos.reports import drawings_opamp
from circuitos.reports.canvas import pretty, si_values
from circuitos.reports.common import BomRow, LabItem, passive

Config = Literal[
    "wien",
    "deslocamento_fase",
    "astavel_ampop",
    "ne555_astavel",
    "ne555_monoestavel",
    "multivibrador_tbj",
]
REF = OPA_REF.model_copy(update={"chapter": "18 (Signal generators and waveform-shaping)"})
BOY = BibRef(
    book="Boylestad & Nashelsky, Electronic Devices and Circuit Theory",
    edition="11th",
    chapter="14 (Feedback and oscillator circuits)",
)
SLOTINE = BibRef(
    book="Slotine & Li, Applied Nonlinear Control",
    edition="1991",
    chapter="5 (Describing function)",
)
TI555 = BibRef(book="Texas Instruments NE555 (SLFS022K)", edition="Rev. K", chapter="8.3, 9.2")
NPTS = 1000  # simulation steps per period
N_WIN = 4  # periods in the measurement window


class OscSpec(BaseModel):
    config: Config = "wien"
    f: QuantityModel = QuantityModel(value=1, unit="kHz")
    duty: float = Field(default=0.6, gt=0.5, lt=0.95)  # 555 astable duty cycle
    t_w: QuantityModel = QuantityModel(value=1, unit="ms")  # 555 monostable pulse width
    C: QuantityModel = QuantityModel(value=10, unit="nF")
    R_base: QuantityModel = QuantityModel(value=10, unit="kohm")  # gain resistors (Rg)
    gain_margin: float = Field(default=0.05, gt=0, le=0.5)  # loop gain above the minimum
    beta: float = Field(default=0.5, gt=0.05, lt=0.95)  # astable: R2/(R1 + R2)
    VCC: QuantityModel = QuantityModel(value=15, unit="V")  # ± for op-amps, + for 555/BJT
    VCC_tbj: QuantityModel = QuantityModel(value=5, unit="V")
    RC_tbj: QuantityModel = QuantityModel(value=1, unit="kohm")  # BJT collector resistors
    VBE: QuantityModel = QuantityModel(value=0.65, unit="V")
    VCEsat: QuantityModel = QuantityModel(value=0.1, unit="V")
    RL: QuantityModel = QuantityModel(value=10, unit="kohm")
    res_series: Literal["E24", "E96"] = "E96"
    cap_series: Literal["E6", "E12", "E24"] = "E12"
    TA: QuantityModel = QuantityModel(value=25, unit="degC")


LABELS = {
    "f0": "Frequência de oscilação (com o modelo do ampop)",
    "f0_ideal": "Frequência de oscilação (ampop ideal)",
    "f0_regen": "Frequência com limiar de regeneração do modelo",
    "T": "Período",
    "tH": "Tempo em nível alto",
    "tL": "Tempo em nível baixo",
    "duty": "Ciclo de trabalho",
    "t_w": "Largura do pulso (monoestável)",
    "Vo_pk": "Amplitude de saída (estimativa)",
    "Vo_pp": "Excursão pico a pico",
    "A_loop": "Ganho do amplificador",
    "A_min": "Ganho mínimo para oscilar",
    "R": "R (rede de frequência)",
    "C": "C (rede de frequência)",
    "C1": "C1",
    "C2": "C2",
    "R1": "R1",
    "R2": "R2",
    "R3": "R3",
    "R4": "R4",
    "R5": "R5",
    "R6": "R6",
    "Rf": "Rf",
    "Rg": "Rg",
    "RA": "RA",
    "RB": "RB",
    "RB1": "RB1 (base)",
    "RB2": "RB2 (base)",
    "RC1": "RC1 (coletor)",
    "RC2": "RC2 (coletor)",
}
SPEC_LABELS = {
    "config": "Circuito",
    "f": "Frequência desejada",
    "duty": "Ciclo de trabalho (555 astável)",
    "t_w": "Largura do pulso (555 monoestável)",
    "C": "Capacitor de temporização",
    "R_base": "Resistor de base (Rg)",
    "gain_margin": "Margem de ganho acima do mínimo",
    "beta": "β = R2/(R1+R2) (astável com ampop)",
    "VCC": "Alimentação (± nos ampops; + no 555)",
    "VCC_tbj": "Alimentação do multivibrador com TBJ",
    "RC_tbj": "Resistores de coletor (TBJ)",
    "VBE": "VBE de condução (TBJ)",
    "VCEsat": "VCE de saturação (TBJ)",
    "RL": "Carga",
    "res_series": "Série de resistores",
    "cap_series": "Série de capacitores",
}
ENUM_LABELS = {
    "wien": "oscilador em ponte de Wien",
    "deslocamento_fase": "oscilador por deslocamento de fase (RC)",
    "astavel_ampop": "multivibrador astável com ampop",
    "ne555_astavel": "555 astável",
    "ne555_monoestavel": "555 monoestável",
    "multivibrador_tbj": "multivibrador astável com TBJ",
    "E6": "E6",
    "E12": "E12",
    "E24": "E24",
    "E96": "E96",
}


def _spec(spec: BaseModel) -> OscSpec:
    if not isinstance(spec, OscSpec):
        raise TypeError("DM-OSC espera OscSpec")
    return spec


def timer_lines(vcc: float, vthr: float, vtrg: float, voh: float, vol: float) -> list[str]:
    """Behavioural 555: comparators at the thresholds, a latch (1 ns) and the discharge switch.

    Pins: thr (threshold), trig, dis (discharge), out; supply node vcc.
    """
    h = vcc / 2
    return [
        f"BLQ qn 0 V = (v(trig) < {vtrg:.9g}) ? {vcc:.9g} : ((v(thr) > {vthr:.9g}) ? 0 : "
        f"((v(q) > {h:.9g}) ? {vcc:.9g} : 0))",
        "RLQ qn q 1k",
        "CLQ q 0 1p",
        f"BLO out 0 V = (v(q) > {h:.9g}) ? {voh:.9g} : {vol:.9g}",
        f"BLB qb 0 V = {vcc:.9g} - v(q)",
        "SDIS dis 0 qb 0 SWDIS",
        f".model SWDIS SW(VT={h:.9g} VH=0 RON=1 ROFF=1G)",
    ]


def sat_df(x: float) -> float:
    """Describing function of a unit-slope saturation at level 1 for amplitude 1/x."""
    return 1.0 if x >= 1 else 2 / math.pi * (math.asin(x) + x * math.sqrt(1 - x * x))


def clamp_amplitude(vf: float, r_clamped: float, x: float) -> float:
    """Current amplitude I where the resistor with the diode clamp (±VF) behaves as x·R."""
    return float(brentq(lambda i: sat_df(vf / (i * r_clamped)) - x, vf / r_clamped, 1e6 * vf))


def marginal_f0(
    u: OpAmp,
    passives: list[tuple[str, str, str, str, float]],
    inp: str,
    inn: str,
    scaled: str,
    f_guess: float,
) -> tuple[float, float]:
    """Steady-state frequency: the element ``scaled`` (the one the limiter acts on) is scaled
    by x until the dominant pole pair of the closed loop sits on the jω axis.

    Returns (f0, x). The pole pair is the one nearest 2π·f_guess (generalized eigenvalues of
    the nodal matrices with the op-amp macromodel).
    """
    w_g = 2 * math.pi * f_guess

    def pair(x: float) -> complex:
        c = Mna()
        for kind, name, a, b, val in passives:
            getattr(c, kind)(name, a, b, val * x if name == scaled else val)
        u.add(c, "U1", inp, inn, "o")
        p = [z for z in c.poles() if z.imag > 0]
        return complex(min(p, key=lambda z: abs(abs(z) - w_g)))

    x = brentq(lambda y: pair(y).real, 1e-3, 1.0, xtol=1e-12)
    return pair(x).imag / (2 * math.pi), float(x)


class OscModule:
    id = "DM-OSC"
    family = "ampops"
    title = "Osciladores, multivibradores e 555"
    spec_schema = OscSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Frequência de oscilação", "osciloscópio ou frequencímetro", "f0"),
        LabItem("Ciclo de trabalho", "osciloscópio", "duty"),
        LabItem("Amplitude de saída", "osciloscópio", "Vo_pp"),
    ]
    questions = [
        "Por que o oscilador de Wien precisa de ganho exatamente 3 em regime?",
        "O que limita a amplitude no oscilador por deslocamento de fase?",
        "Por que o ciclo de trabalho do 555 astável básico é sempre maior que 50 %?",
    ]
    practice = {
        "objective": "Montar o oscilador, medir frequência, ciclo de trabalho e amplitude e "
        "comparar com o projeto.",
        "material": "Fonte, osciloscópio, ampop ou 555 ou transistores, resistores, capacitores "
        "(filme) e diodos da lista de materiais.",
        "procedure": [
            "Ligue a alimentação e observe a partida da oscilação.",
            "Meça o período e os tempos alto e baixo.",
            "Varie o resistor de ganho (Wien) e observe a distorção e a amplitude.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        c = _spec(spec).config
        if c.startswith("ne555"):
            return [Role(designator="U1", category="timer", description="Temporizador 555")]
        if c == "multivibrador_tbj":
            return [
                Role(designator="Q1", category="bjt.npn", description="Transistor"),
                Role(designator="Q2", category="bjt.npn", description="Transistor"),
            ]
        out = [Role(designator="U1", category="opamp", description="Amplificador operacional")]
        if c in ("wien", "deslocamento_fase"):
            out += [
                Role(designator="D1", category="diode.signal", description="Diodo (amplitude)"),
                Role(designator="D2", category="diode.signal", description="Diodo (amplitude)"),
            ]
        return out

    def required_ratings(self, role: Role) -> list[str]:
        if role.category.startswith("diode"):
            return ["VRRM"]
        if role.category.startswith("bjt"):
            return ["VCEO", "IC"]
        if role.category == "timer":
            return ["VCC_max"]
        return []

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        s = _spec(spec)
        if role.category == "opamp":
            vs = s.VCC.to_pint().m_as("V")
            sym, tot = rec.parameters.get("VS_max"), rec.parameters.get("VS_total_max")
            return (sym is not None and (sym.max or 0) >= vs) or (
                tot is not None and (tot.max or 0) >= 2 * vs
            )
        if role.category == "timer":
            return all(k in rec.parameters for k in ("V_thres", "V_trig", "VOH", "VOL"))
        return True

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        if role.category == "opamp":
            sr = quantity(rec, "SR", ("typ", "min"))
            return -float(sr.m_as("V/us")) if sr is not None else 0.0
        return 0.0

    # ------------------------------------------------------------------ design
    def _cap(self, s: OscSpec, log: CalcLog, step: str, desc: str, c: float) -> float:
        return float(commercial(log, step, desc, Q_(c, "F"), s.cap_series, "nearest").m_as("F"))

    def _res(self, s: OscSpec, log: CalcLog, step: str, desc: str, r: float) -> float:
        return float(commercial(log, step, desc, Q_(r, "ohm"), s.res_series, "nearest").m_as("ohm"))

    def _design(
        self, s: OscSpec, devices: Mapping[str, Device], log: CalcLog
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        """Part values (SI), summary magnitudes (SI), warnings, netlist and the period."""
        c = s.config
        f = s.f.to_pint().m_as("Hz")
        cb = self._cap(s, log, "C", "Capacitor de temporização", s.C.to_pint().m_as("F"))
        rg = s.R_base.to_pint().m_as("ohm")
        rl = s.RL.to_pint().m_as("ohm")
        if c in ("wien", "deslocamento_fase", "astavel_ampop"):
            vcc = s.VCC.to_pint().m_as("V")
            u = opamp_model(devices["U1"].record, vcc, -vcc, log, "U1", with_errors=False)[0]
            if c == "wien":
                return self._wien(s, devices, u, log, f, cb, rg, rl)
            if c == "deslocamento_fase":
                return self._phase(s, devices, u, log, f, cb, rl)
            return self._astable(s, u, log, f, cb, rl)
        if c.startswith("ne555"):
            return self._timer(s, devices["U1"].record, log, f, cb, rl)
        return self._tbj(s, devices, log, f, cb)

    def _wien(
        self,
        s: OscSpec,
        devices: Mapping[str, Device],
        u: OpAmp,
        log: CalcLog,
        f: float,
        cb: float,
        rg: float,
        rl: float,
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        r = self._res(s, log, "R", "R da ponte de Wien", 1 / (2 * math.pi * f * cb))
        f0i = 1 / (2 * math.pi * r * cb)
        log.add(
            record(
                "f0_ideal",
                "Frequência de oscilação da ponte de Wien (ampop ideal)",
                r"f_0 = \frac{1}{2\pi R C}",
                output=Q_(f0i, "Hz"),
                inputs={"R": Q_(r, "ohm"), "C": Q_(cb, "F").to("nF")},
                assumptions=["R e C iguais nos dois braços; ampop ideal na frequência f0"],
                reference=REF,
            )
        )
        # Rf = R3 + R4 = (2 + margin)·Rg; R4 (with the diodes) brings the gain back to 3
        rf_total = (2 + 3 * s.gain_margin) * rg
        r4 = self._res(s, log, "R4", "R4 (em paralelo com os diodos)", 0.5 * rf_total)
        r3 = self._res(s, log, "R3", "R3", rf_total - r4)
        a = 1 + (r3 + r4) / rg
        if a <= 3:
            raise ValueError("Ganho da ponte não passa de 3 com os resistores comerciais")
        net = [
            ("R", "1", "o", "p", r),
            ("C", "1", "p", "x", cb),
            ("R", "2", "x", "0", r),
            ("C", "2", "x", "0", cb),
            ("R", "g", "n", "0", rg),
            ("R", "3", "n", "m", r3),
            ("R", "4", "m", "o", r4),
        ]
        f0, x = marginal_f0(u, net, "x", "n", "4", f0i)
        self._log_loop(log, f0, f0i, "R4 em paralelo com os diodos")
        vf = max(devices["D1"].drop.m_as("V"), devices["D2"].drop.m_as("V")) or 0.7
        # describing function of the diode clamp on R4: its fundamental behaves as x·R4
        i_amp = clamp_amplitude(vf, r4, x)
        vpk = i_amp * (rg + r3) + vf
        log.add(
            record(
                "Vo_pk",
                "Amplitude de saída (função descritiva do grampo de diodos sobre R4)",
                r"N\!\left(\frac{V_F}{I R_4}\right) = x,"
                r"\ N(u) = \frac{2}{\pi}\left(\arcsin u + u\sqrt{1-u^2}\right),"
                r"\ V_{o,pk} = I\,(R_g + R_3) + V_F",
                output=Q_(vpk, "V"),
                inputs={
                    "x": Q_(x, ""),
                    "I": Q_(i_amp, "A").to("mA"),
                    "V_F": Q_(vf, "V"),
                    "R_3": Q_(r3, "ohm"),
                    "R_4": Q_(r4, "ohm"),
                    "R_g": Q_(rg, "ohm"),
                },
                assumptions=[
                    "x: fator de R4 que põe os polos no eixo jω (passo anterior)",
                    "corrente senoidal de amplitude I em Rg, R3 e R4 (a ponte filtra os "
                    "harmônicos)",
                    "diodos de queda constante: a tensão em R4 é ceifada em ±V_F",
                ],
                reference=SLOTINE,
            )
        )
        v = {"R": r, "C": cb, "Rg": rg, "R3": r3, "R4": r4}
        sm = {"f0": f0, "f0_ideal": f0i, "T": 1 / f0, "A_loop": a, "A_min": 3.0, "Vo_pk": vpk}
        w: list[DesignWarning] = []
        if 2 * vpk > u.v_hi - u.v_lo:
            w.append(
                DesignWarning(
                    code="excursao",
                    message="A amplitude estimada passa da excursão: o ampop vai saturar.",
                )
            )
        lines = [
            diode_subckt(vf),
            f"R1 o p {r:.9g}",
            f"C1 p x {cb:.9g} IC=0.05",
            f"R2 x 0 {r:.9g}",
            f"C2 x 0 {cb:.9g}",
            f"Rg n 0 {rg:.9g}",
            f"R3 n m {r3:.9g}",
            f"R4 m o {r4:.9g}",
            "XD1 m o DIODE",
            "XD2 o m DIODE",
            f"RL o 0 {rl:.9g}",
            *u.nonlinear_lines("U1", "x", "n", "o"),
        ]
        return v, sm, w, lines, 1 / f0

    @staticmethod
    def _log_loop(log: CalcLog, f0: float, f0i: float, what: str) -> None:
        log.add(
            record(
                "f0",
                "Frequência de oscilação em regime com o modelo do ampop",
                r"\det\left(G + sC\right) = 0,\ s = \pm j2\pi f_0"
                r"\ (\text{ganho efetivo do limitador no limiar de oscilação})",
                output=Q_(f0, "Hz"),
                inputs={"f_{0,ideal}": Q_(f0i, "Hz")},
                assumptions=[
                    f"o limitador reduz o ganho até o par de polos dominante ficar no eixo jω "
                    f"({what})",
                    "polos do circuito nodal com A0, GBW e Rin do ampop escolhido",
                ],
                reference=REF,
            )
        )

    def _phase(
        self,
        s: OscSpec,
        devices: Mapping[str, Device],
        u: OpAmp,
        log: CalcLog,
        f: float,
        cb: float,
        rl: float,
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        r = self._res(s, log, "R", "R das seções RC", 1 / (2 * math.pi * math.sqrt(6) * f * cb))
        f0i = 1 / (2 * math.pi * math.sqrt(6) * r * cb)
        log.add(
            record(
                "f0_ideal",
                "Frequência do oscilador por deslocamento de fase (3 seções CR, ampop ideal)",
                r"f_0 = \frac{1}{2\pi\sqrt{6}\,RC},\quad |A| \ge 29",
                output=Q_(f0i, "Hz"),
                inputs={"R": Q_(r, "ohm"), "C": Q_(cb, "F").to("nF")},
                assumptions=["o último R é a entrada do inversor (terra virtual)"],
                reference=BOY,
            )
        )
        # at least 20 % above 29 so that the oscillation builds up in a few tens of periods;
        # Rf = R5 + R6, the diodes across R6 bring the gain back to the threshold
        rf_total = 29 * (1 + max(s.gain_margin, 0.2)) * r
        r6 = self._res(s, log, "R6", "R6 (em paralelo com os diodos)", 0.5 * rf_total)
        r5 = self._res(s, log, "R5", "R5", rf_total - r6)
        a = (r5 + r6) / r
        if a < 29 or r5 / r >= 29:
            raise ValueError("Ganho fora da faixa (29 < A, R5/R < 29) com os resistores comerciais")
        net = [
            ("C", "1", "o", "a", cb),
            ("R", "1", "a", "0", r),
            ("C", "2", "a", "b", cb),
            ("R", "2", "b", "0", r),
            ("C", "3", "b", "c", cb),
            ("R", "3", "c", "n", r),
            ("R", "5", "n", "m", r5),
            ("R", "6", "m", "o", r6),
        ]
        f0, x = marginal_f0(u, net, "0", "n", "6", f0i)
        self._log_loop(log, f0, f0i, "R6 em paralelo com os diodos")
        vf = max(devices["D1"].drop.m_as("V"), devices["D2"].drop.m_as("V")) or 0.7
        i_amp = clamp_amplitude(vf, r6, x)
        vpk = i_amp * r5 + vf
        log.add(
            record(
                "Vo_pk",
                "Amplitude de saída (função descritiva do grampo de diodos sobre R6)",
                r"N\!\left(\frac{V_F}{I R_6}\right) = x,\ V_{o,pk} = I R_5 + V_F",
                output=Q_(vpk, "V"),
                inputs={
                    "x": Q_(x, ""),
                    "I": Q_(i_amp, "A").to("mA"),
                    "V_F": Q_(vf, "V"),
                    "R_5": Q_(r5, "ohm"),
                    "R_6": Q_(r6, "ohm"),
                },
                assumptions=[
                    "x: fator de R6 que põe os polos no eixo jω",
                    "corrente senoidal na realimentação (a rede CR filtra os harmônicos)",
                    "terra virtual na entrada inversora",
                ],
                reference=SLOTINE,
            )
        )
        v = {"R": r, "C": cb, "R5": r5, "R6": r6}
        sm = {"f0": f0, "f0_ideal": f0i, "T": 1 / f0, "A_loop": a, "A_min": 29.0, "Vo_pk": vpk}
        lines = [
            diode_subckt(vf),
            f"C1 o a {cb:.9g} IC=0.05",
            f"R1 a 0 {r:.9g}",
            f"C2 a b {cb:.9g}",
            f"R2 b 0 {r:.9g}",
            f"C3 b c {cb:.9g}",
            f"R3 c n {r:.9g}",
            f"R5 n m {r5:.9g}",
            f"R6 m o {r6:.9g}",
            "XD1 m o DIODE",
            "XD2 o m DIODE",
            f"RL o 0 {rl:.9g}",
            *u.nonlinear_lines("U1", "0", "n", "o"),
        ]
        w: list[DesignWarning] = []
        if vpk > min(u.v_hi, -u.v_lo):
            w.append(
                DesignWarning(
                    code="excursao",
                    message="A amplitude estimada passa da excursão: o ampop vai saturar.",
                )
            )
        return v, sm, w, lines, 1 / f0

    def _astable(
        self, s: OscSpec, u: OpAmp, log: CalcLog, f: float, cb: float, rl: float
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        r2 = s.R_base.to_pint().m_as("ohm")
        r1 = self._res(s, log, "R1", "R1 (saída → entrada +)", r2 * (1 - s.beta) / s.beta)
        b = r2 / (r1 + r2)
        vh, vl = u.v_hi, u.v_lo
        k_h = math.log((vh - b * vl) / ((1 - b) * vh))
        k_l = math.log((vl - b * vh) / ((1 - b) * vl))
        t_sl = (vh - vl) / u.SR if math.isfinite(u.SR) else 0.0
        r = self._res(s, log, "R", "R de temporização", (1 / f - 2 * t_sl) / ((k_h + k_l) * cb))
        th = r * cb * k_h + t_sl
        tl = r * cb * k_l + t_sl
        t = th + tl
        log.add(
            record(
                "T",
                "Período do astável com ampop (saturação assimétrica e slew rate)",
                r"t_H = RC\ln\frac{V_H - \beta V_L}{(1-\beta)V_H} + \frac{V_H - V_L}{SR},\ "
                r"t_L = RC\ln\frac{V_L - \beta V_H}{(1-\beta)V_L} + \frac{V_H - V_L}{SR}",
                output=Q_(t, "s").to("ms"),
                inputs={
                    "R": Q_(r, "ohm"),
                    "C": Q_(cb, "F").to("nF"),
                    r"\beta": Q_(b, ""),
                    "V_H": Q_(vh, "V"),
                    "V_L": Q_(vl, "V"),
                    "SR": Q_(u.SR, "V/s").to("V/us"),
                },
                assumptions=[
                    "o capacitor continua carregando durante a transição (aproximação de 1ª "
                    "ordem do tempo de subida)"
                ],
                reference=REF,
            )
        )
        v = {"R": r, "C": cb, "R1": r1, "R2": r2}
        sm = {"f0": 1 / t, "T": t, "tH": th, "tL": tl, "duty": th / t, "Vo_pp": vh - vl}
        w: list[DesignWarning] = []
        if t_sl > 0.02 * t:
            w.append(
                DesignWarning(
                    code="slew",
                    message=f"As transições levam {t_sl * 1e6:.3g} µs ({100 * t_sl / t:.1f} % "
                    "do período): a fórmula fica aproximada; prefira ampop mais rápido.",
                )
            )
        lines = [
            f"Rt o n {r:.9g}",
            f"Ct n 0 {cb:.9g} IC=0.01",
            f"R1 o p {r1:.9g}",
            f"R2 p 0 {r2:.9g}",
            f"RL o 0 {rl:.9g}",
            *u.nonlinear_lines("U1", "p", "n", "o"),
        ]
        return v, sm, w, lines, t

    def _timer(
        self, s: OscSpec, rec: ComponentRecord | None, log: CalcLog, f: float, cb: float, rl: float
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        vcc = s.VCC.to_pint().m_as("V")
        if rec is None:
            kthr, ktrg, voh, vol = 2 / 3, 1 / 3, vcc - 1.7, 0.1
            how = "limiares nominais 2/3 e 1/3 de VCC (sem componente)"
        else:
            p_thr, p_trg = rec.parameters["V_thres"], rec.parameters["V_trig"]
            vt = p_thr.conditions["VCC"].to_pint().m_as("V") if "VCC" in p_thr.conditions else 15
            kthr = float(quantity(rec, "V_thres").m_as("V")) / vt  # type: ignore[union-attr]
            vt2 = p_trg.conditions["VCC"].to_pint().m_as("V") if "VCC" in p_trg.conditions else 15
            ktrg = float(quantity(rec, "V_trig").m_as("V")) / vt2  # type: ignore[union-attr]
            p_oh = rec.parameters["VOH"]
            vt3 = p_oh.conditions["VCC"].to_pint().m_as("V") if "VCC" in p_oh.conditions else 15
            voh = vcc - (vt3 - float(quantity(rec, "VOH", ("typ", "min")).m_as("V")))  # type: ignore[union-attr]
            vol = float(quantity(rec, "VOL", ("typ", "max")).m_as("V"))  # type: ignore[union-attr]
            how = f"limiares típicos do datasheet ({rec.part_number}) proporcionais a VCC"
        vthr, vtrg = kthr * vcc, ktrg * vcc
        k_ch = math.log((vcc - vtrg) / (vcc - vthr))
        k_dis = math.log(vthr / vtrg)
        w: list[DesignWarning] = []
        if s.config == "ne555_monoestavel":
            tw_req = s.t_w.to_pint().m_as("s")
            k_m = math.log(vcc / (vcc - vthr))
            r = self._res(s, log, "RA", "R de temporização", tw_req / (k_m * cb))
            tw = r * cb * k_m
            log.add(
                record(
                    "t_w",
                    "Largura do pulso do 555 monoestável",
                    r"t_w = RC\ln\frac{V_{CC}}{V_{CC} - V_{thres}}\ (= 1{,}1RC\ \text{com } 2/3)",
                    output=Q_(tw, "s").to("ms"),
                    inputs={
                        "R": Q_(r, "ohm"),
                        "C": Q_(cb, "F").to("nF"),
                        "V_{thres}": Q_(vthr, "V"),
                    },
                    assumptions=[how, "descarga com chave ideal; correntes de limiar desprezadas"],
                    reference=TI555,
                )
            )
            t_trig = 2 * tw  # trigger period of the test (one pulse per 2·t_w)
            v = {"RA": r, "C": cb}
            sm = {"t_w": tw, "T": t_trig, "Vo_hi": voh}
            pw = tw / 50
            lines = [
                f"Vcc vcc 0 DC {vcc:.9g}",
                f"Vtr trig 0 PULSE({vcc:.9g} 0 {tw / 4:.9g} {pw / 10:.9g} {pw / 10:.9g} "
                f"{pw:.9g} {t_trig:.9g})",
                f"RA vcc thr {r:.9g}",
                f"Ct thr 0 {cb:.9g} IC=0",
                "Rdis dis thr 1m",
                f"RL out 0 {rl:.9g}",
                *timer_lines(vcc, vthr, vtrg, voh, vol),
            ]
            return v, sm, w, lines, t_trig
        d = s.duty
        # t_H/t_L = (RA + RB)k_ch/(RB k_dis) = d/(1 − d)
        rb_ = self._res(s, log, "RB", "RB", (1 - d) / (f * cb * k_dis))
        ra = self._res(s, log, "RA", "RA", d / (f * cb * k_ch) - rb_)
        if ra <= 0:
            raise ValueError("Ciclo de trabalho inviável no 555 astável básico")
        th = (ra + rb_) * cb * k_ch
        tl = rb_ * cb * k_dis
        t = th + tl
        log.add(
            record(
                "T",
                "Período do 555 astável",
                r"t_H = (R_A + R_B)C\ln\frac{V_{CC} - V_{trig}}{V_{CC} - V_{thres}},\ "
                r"t_L = R_B C\ln\frac{V_{thres}}{V_{trig}}",
                output=Q_(t, "s").to("ms"),
                inputs={
                    "R_A": Q_(ra, "ohm"),
                    "R_B": Q_(rb_, "ohm"),
                    "C": Q_(cb, "F").to("nF"),
                    "V_{thres}": Q_(vthr, "V"),
                    "V_{trig}": Q_(vtrg, "V"),
                },
                assumptions=[how, "descarga com chave ideal; correntes de limiar desprezadas"],
                reference=TI555,
            )
        )
        if ra < 1e3:
            w.append(
                DesignWarning(
                    code="ra",
                    message="RA abaixo de 1 kΩ: corrente alta no transistor de descarga.",
                )
            )
        v = {"RA": ra, "RB": rb_, "C": cb}
        sm = {"f0": 1 / t, "T": t, "tH": th, "tL": tl, "duty": th / t, "Vo_hi": voh}
        lines = [
            f"Vcc vcc 0 DC {vcc:.9g}",
            f"RA vcc dis {ra:.9g}",
            f"RB dis thr {rb_:.9g}",
            f"Ct thr 0 {cb:.9g} IC={vtrg:.9g}",
            "Rtr thr trig 1m",
            f"RL out 0 {rl:.9g}",
            *timer_lines(vcc, vthr, vtrg, voh, vol),
        ]
        return v, sm, w, lines, t

    def _tbj(
        self, s: OscSpec, devices: Mapping[str, Device], log: CalcLog, f: float, cb: float
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        vcc = s.VCC_tbj.to_pint().m_as("V")
        rc = s.RC_tbj.to_pint().m_as("ohm")
        vbe = s.VBE.to_pint().m_as("V")
        vce = s.VCEsat.to_pint().m_as("V")
        k = math.log((2 * vcc - vbe - vce) / (vcc - vbe))
        rb = self._res(s, log, "RB1", "RB (base)", 1 / (2 * f * cb * k))
        half = rb * cb * k
        t = 2 * half
        log.add(
            record(
                "T",
                "Período do multivibrador astável com TBJ (simétrico)",
                r"t = R_B C \ln\frac{2V_{CC} - V_{BE} - V_{CE(sat)}}{V_{CC} - V_{BE}},\ T = 2t",
                output=Q_(t, "s").to("ms"),
                inputs={
                    "R_B": Q_(rb, "ohm"),
                    "C": Q_(cb, "F").to("nF"),
                    "V_{CC}": Q_(vcc, "V"),
                    "V_{BE}": Q_(vbe, "V"),
                    "V_{CE(sat)}": Q_(vce, "V"),
                },
                assumptions=[
                    "o transistor que conduz satura; a base do outro vai a "
                    "V_BE − (V_CC − V_CE(sat))",
                    "recarga do coletor (R_C·C) bem mais rápida que o meio período",
                ],
                reference=BOY,
            )
        )
        ic = (vcc - vce) / rc
        q1, _ = bjt_model(devices["Q1"].record, ic, s.VBE.to_pint(), 100.0, log, "Q1")
        q2, _ = bjt_model(devices["Q2"].record, ic, s.VBE.to_pint(), 100.0, log, "Q2")
        # Regeneration starts when the loop gain (gm·RC)² of the pair reaches 1, i.e. at
        # IC = VT/RC, well below the design VBE (Sedra & Smith, ch. 18, bistable loop gain)
        v_on = VT_300K * math.log(VT_300K / (rc * q1.IS))
        k_on = math.log((2 * vcc - vbe - vce) / (vcc - v_on))
        t_on = 2 * rb * cb * k_on
        log.add(
            record(
                "f0_regen",
                "Frequência com o limiar de regeneração do modelo (conferência com a simulação)",
                r"V_{on} = V_T \ln\frac{V_T}{R_C I_S},\ "
                r"f = \left[2 R_B C \ln\frac{2V_{CC} - V_{BE} - V_{CE(sat)}}{V_{CC} - V_{on}}"
                r"\right]^{-1}",
                output=Q_(1 / t_on, "Hz"),
                inputs={
                    "V_T": Q_(VT_300K, "V"),
                    "R_C": Q_(rc, "ohm"),
                    "I_S": Q_(q1.IS, "A"),
                    "V_{on}": Q_(v_on, "V"),
                },
                assumptions=[
                    "a transição começa quando gm·R_C = 1 no transistor que sai do corte",
                    "mesmo ponto de partida da base que a fórmula de livro",
                ],
                reference=OPA_REF.model_copy(update={"chapter": "18 (bistable feedback loop)"}),
            )
        )
        w: list[DesignWarning] = []
        if rb > 0.7 * q1.BF * rc:
            w.append(
                DesignWarning(
                    code="saturacao",
                    message=f"RB = {format_eng(Q_(rb, 'ohm'))} é grande frente a β·RC: o "
                    "transistor pode não saturar. Aumente C e reduza RB.",
                )
            )
        rec = devices["Q1"].record
        vebo = quantity(rec, "VEBO", ("max",)) if rec is not None else None
        if vebo is not None and vcc - vce > float(vebo.m_as("V")):
            w.append(
                DesignWarning(
                    code="vebo",
                    message=f"A base vai a −{vcc - vce:.3g} V, acima de VEBO "
                    f"({float(vebo.m_as('V')):.3g} V): a junção base-emissor entra em ruptura "
                    "(o modelo não representa isso).",
                )
            )
        v = {"RB1": rb, "RB2": rb, "RC1": rc, "RC2": rc, "C1": cb, "C2": cb}
        sm = {"f0": 1 / t, "f0_regen": 1 / t_on, "T": t, "tH": half, "tL": half, "duty": 0.5}
        lines = [
            f"Vcc vcc 0 DC {vcc:.9g}",
            q1.spice("QM1"),
            q2.spice("QM2"),
            f"RC1 vcc c1 {rc:.9g}",
            f"RC2 vcc c2 {rc:.9g}",
            f"RB1 vcc b1 {rb:.9g}",
            f"RB2 vcc b2 {rb:.9g}",
            f"C1 c1 b2 {cb:.9g} IC=0",
            f"C2 c2 b1 {cb:.9g} IC={-vcc / 2:.9g}",
            "Q1 c1 b1 0 QM1",
            "Q2 c2 b2 0 QM2",
        ]
        return v, sm, w, lines, t

    @staticmethod
    def _q(key: str, x: float) -> pint.Quantity:
        if key in ("f0", "f0_ideal", "f0_regen"):
            return Q_(x, "Hz")
        if key in ("T", "tH", "tL", "t_w"):
            return Q_(x, "s").to("ms")
        if key == "duty":
            return Q_(x * 100, "percent")
        if key in ("A_loop", "A_min"):
            return Q_(x, "")
        return Q_(x, "V")

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        v, sm, warnings, _, period = self._design(s, devices, log)
        summary: dict[str, pint.Quantity] = {k: self._q(k, x) for k, x in sm.items()}
        for k, x in v.items():
            summary[k] = Q_(x, "F").to("nF") if k.startswith("C") else Q_(x, "ohm")
        stresses: list[Stress] = []
        if s.config == "multivibrador_tbj":
            vcc = s.VCC_tbj.to_pint().m_as("V")
            ic = vcc / s.RC_tbj.to_pint().m_as("ohm")
            for d in ("Q1", "Q2"):
                stresses += [
                    Stress(
                        designator=d,
                        key="VCEO",
                        label="Tensão coletor-emissor",
                        value=QuantityModel(value=vcc, unit="V"),
                        calc_step_id="T",
                    ),
                    Stress(
                        designator=d,
                        key="IC",
                        label="Corrente de coletor",
                        value=QuantityModel(value=ic, unit="A"),
                        calc_step_id="T",
                    ),
                ]
        if s.config in ("wien", "deslocamento_fase"):
            for d in ("D1", "D2"):
                stresses.append(
                    Stress(
                        designator=d,
                        key="VRRM",
                        label="Tensão reversa (antiparalelo: V_F; margem pela saída)",
                        value=QuantityModel(value=sm["Vo_pk"], unit="V"),
                        calc_step_id="Vo_pk",
                    )
                )
        if s.config.startswith("ne555"):
            stresses.append(
                Stress(
                    designator="U1",
                    key="VCC_max",
                    label="Alimentação",
                    value=QuantityModel(value=s.VCC.to_pint().m_as("V"), unit="V"),
                    calc_step_id="T" if "tH" in sm else "t_w",
                )
            )
        traces = self._waves(s, sm, period)
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={},
            warnings=warnings,
            convergence_keys=("T",),
            traces=traces,
            trace_period=Q_(2 * period, "s"),
        )

    def _waves(self, s: OscSpec, sm: Mapping[str, float], period: float) -> dict[str, Trace]:
        t = np.linspace(0, 2 * period, 720, endpoint=False)
        if s.config == "wien":
            return {"Saída (ideal)": make_trace("V", sm["Vo_pk"] * np.sin(2 * np.pi * t / period))}
        if s.config == "deslocamento_fase":
            return {}
        if s.config == "ne555_monoestavel":
            on = (t % period) < sm["t_w"]
            return {"Saída": make_trace("V", np.where(on, sm["Vo_hi"], 0.0))}
        hi = (t % period) < sm["tH"]
        return {"Saída": make_trace("", np.where(hi, 1.0, 0.0))}

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        _, sm, _, lines, period = self._design(s, devices, CalcLog())
        c = s.config
        probe = {"ne555_astavel": "v(out)", "ne555_monoestavel": "v(out)"}.get(c, "v(o)")
        if c == "multivibrador_tbj":
            probe = "v(c2)"
        checks: list[SimCheck] = []
        n_settle = 3
        if c == "ne555_monoestavel":
            checks.append(
                SimCheck(
                    quantity="Largura do pulso",
                    summary_key="t_w",
                    metric="t_high",
                    probe=probe,
                    tolerance_pct=1.0,
                    justification="mesmos limiares; chave de descarga de 1 Ω",
                )
            )
        else:
            tol, why = {
                "wien": (2.0, "distorção dos diodos limitadores; função descritiva"),
                "deslocamento_fase": (2.0, "distorção dos diodos limitadores; função descritiva"),
                "astavel_ampop": (2.0, "transição por SR aproximada como tempo somado"),
                "ne555_astavel": (1.0, "mesmos limiares; chave de descarga de 1 Ω"),
                "multivibrador_tbj": (3.0, "V_CE(sat) de projeto × Ebers-Moll; recarga R_C·C"),
            }[c]
            checks.append(
                SimCheck(
                    quantity="Frequência de oscilação",
                    summary_key="f0_regen" if c == "multivibrador_tbj" else "f0",
                    metric="freq",
                    probe=probe,
                    tolerance_pct=tol,
                    justification=why,
                )
            )
            if "duty" in sm and c != "multivibrador_tbj":
                checks.append(
                    SimCheck(
                        quantity="Ciclo de trabalho",
                        summary_key="duty",
                        metric="duty",
                        probe=probe,
                        tolerance_pct=tol,
                        justification=why,
                    )
                )
            if c == "wien":
                n_settle = 80  # the amplitude grows from the initial kick
                checks.append(
                    SimCheck(
                        quantity="Amplitude de saída",
                        summary_key="Vo_pk",
                        metric="max",
                        probe=probe,
                        tolerance_pct=5.0,
                        justification="função descritiva: harmônicos em v+ desprezados",
                    )
                )
            if c == "deslocamento_fase":
                n_settle = 60
                checks.append(
                    SimCheck(
                        quantity="Amplitude de saída",
                        summary_key="Vo_pk",
                        metric="max",
                        probe=probe,
                        tolerance_pct=5.0,
                        justification="função descritiva: harmônicos na rede desprezados",
                    )
                )
        win = N_WIN * period
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[c]}",
            # Gear for the op-amp clamps; the BJT regenerative edge needs the default (trap)
            netlist="\n".join(lines if c == "multivibrador_tbj" else [TRAN_OPTIONS, *lines]),
            tran_stop=QuantityModel(value=(n_settle + 2 * N_WIN) * period, unit="s"),
            tran_step=QuantityModel(value=period / NPTS, unit="s"),
            period=QuantityModel(value=win, unit="s"),
            probes={"Saída": probe},
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        same = {"Rt": "R", "Ct": "C"} if s.config == "astavel_ampop" else {}
        if s.config in ("wien", "deslocamento_fase"):
            ks = (1, 2) if s.config == "wien" else (1, 2, 3)
            same = {f"{x}{k}": x for x in "RC" for k in ks}
        elif s.config.startswith("ne555"):
            same = {"Ct": "C"}
        names = {k: k for k in sm if k[0] in "RC" and k not in ("R", "C")} | same
        v = si_values(sm, names) | {"RL": s.RL.to_pint().m_as("ohm")}
        parts = {c.designator: c.part_number for c in result.selection}
        vcc = s.VCC_tbj if s.config == "multivibrador_tbj" else s.VCC
        extra = {"Vcc": pretty(vcc), "trigger": "pulso de disparo"}
        return drawings_opamp.osc(s.config, title, v, parts, extra)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        sm = result.summary
        rows = []
        for k in sm:
            if k[0] == "R":
                rows.append(
                    passive(k, "Resistor 1 % (filme metálico)", format_eng(sm[k].to_pint()))
                )
            elif k[0] == "C":
                rows.append(passive(k, "Capacitor (filme)", format_eng(sm[k].to_pint())))
        return rows
