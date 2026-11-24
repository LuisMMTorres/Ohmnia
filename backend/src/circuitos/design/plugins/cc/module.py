"""DM-CC: non-isolated PWM DC-DC converters.

Continuous conduction (MCC): the duty cycle comes from the averaged state-space model with the
switch as R_on (MOSFET) or an equivalent resistance of VCE(sat) (IGBT) and the diode as a
constant drop V_F (Erickson & Maksimović, 2nd ed., ch. 3 and ch. 7). Ripples use the small
ripple approximation: the slope of each state in the on interval times D·Ts (ch. 2); the output
capacitor of the buck, Ćuk and Zeta is fed by an inductor and uses ΔV = Δi/(8 f C).

Discontinuous conduction (MCD; buck, boost and buck-boost): volt-second balance on the
inductor with the diode drop over the three intervals (ch. 5), L as a fraction of the critical
inductance.

Control loop (MCC): small-signal control-to-output transfer of the averaged model (ch. 7-8),
modulator gain 1/V_m and a voltage divider to V_ref; type II or type III error amplifier by
Venable's K factor; margins of the loop with the commercial component values.

The inductors are designed on catalogue cores (SV-MAG) after the selection of the
semiconductors; their losses enter the efficiency.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Mapping
from typing import Literal

import numpy as np
import pint
from pydantic import BaseModel, Field, model_validator
from scipy import signal

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.analog import commercial, q
from circuitos.design.base import Circuit, DesignResult, DesignWarning, Role, SimCheck, Trace
from circuitos.design.engine import Analysis, Device
from circuitos.design.power import (
    ERICKSON,
    Compensator,
    InductorNeed,
    Margins,
    SwitchData,
    SwitchedModel,
    boost_needed,
    converter_model,
    design_inductors,
    diode_data,
    diode_losses,
    efficiency_step,
    gvd,
    k_factor,
    mag_labels,
    margins,
    merge_magnetics,
    pwm_source,
    ref,
    round_comp,
    solve_duty,
    spice_diode,
    spice_switch,
    steady_state,
    switch_data,
    switch_losses,
)
from circuitos.reports import drawings_power
from circuitos.reports.canvas import pretty
from circuitos.reports.common import BomRow, LabItem, passive

Topology = Literal["buck", "boost", "buckboost", "cuk", "sepic", "zeta"]
Mode = Literal["MCC", "MCD"]
FOURTH = ("cuk", "sepic", "zeta")
OUT_FROM_L = ("buck", "cuk", "zeta")  # output capacitor fed by an inductor (triangular current)
E_SS = ref(ERICKSON, "2-3 (steady state; small ripple approximation)")
E_DCM = ref(ERICKSON, "5 (discontinuous conduction mode)")
E_AVG = ref(ERICKSON, "7-8 (averaged small-signal model, transfer functions)")
E_LOOP = ref(ERICKSON, "9 (controller design)")


class CcSpec(BaseModel):
    topology: Topology = "buck"
    mode: Mode = "MCC"
    switch: Literal["mosfet", "igbt"] = "mosfet"
    Vin: QuantityModel = QuantityModel(value=24, unit="V")
    Vo: QuantityModel = QuantityModel(value=12, unit="V")  # magnitude (inverting topologies too)
    Io: QuantityModel = QuantityModel(value=2, unit="A")
    fs: QuantityModel = QuantityModel(value=50, unit="kHz")
    ripple_iL: float = Field(default=0.3, gt=0.01, le=1.8)  # Δi/I of each inductor (MCC)
    ripple_vo: float = Field(default=0.01, gt=0.0005, le=0.2)  # ΔVo/Vo
    ripple_vc1: float = Field(default=0.05, gt=0.005, le=0.5)  # ΔvC1/VC1 (4th order)
    L_ratio: float = Field(default=0.5, gt=0.05, lt=1.0)  # MCD: L = ratio·L_crit
    compensator: Literal["III", "II", "nenhum"] = "III"
    fc_ratio: float = Field(default=0.1, gt=0.005, le=0.3)  # fc/fs
    phase_margin: float = Field(default=60, ge=30, le=80)  # degrees
    Vm: QuantityModel = QuantityModel(value=1, unit="V")  # PWM ramp amplitude
    Vref: QuantityModel = QuantityModel(value=2.5, unit="V")
    R1: QuantityModel = QuantityModel(value=10, unit="kohm")  # upper resistor of the divider
    V_gate: QuantityModel = QuantityModel(value=15, unit="V")
    TA: QuantityModel = QuantityModel(value=40, unit="degC")

    @model_validator(mode="after")
    def _check(self) -> CcSpec:
        vin = self.Vin.to_pint().m_as("V")
        vo = self.Vo.to_pint().m_as("V")
        if vin <= 0 or vo <= 0 or self.Io.to_pint().m_as("A") <= 0:
            raise ValueError("Vin, Vo e Io devem ser positivos")
        if self.topology == "buck" and vo >= vin:
            raise ValueError("O buck só abaixa a tensão: Vo < Vin")
        if self.topology == "boost" and vo <= vin:
            raise ValueError("O boost só eleva a tensão: Vo > Vin")
        if self.mode == "MCD" and self.topology in FOURTH:
            raise ValueError("MCD está disponível para buck, boost e buck-boost")
        if self.Vref.to_pint().m_as("V") >= vo:
            raise ValueError("V_ref deve ser menor que Vo (divisor resistivo)")
        return self


LABELS = {
    "D": "Razão cíclica D",
    "D2": "Fração de desmagnetização D₂ (MCD)",
    "R_load": "Resistência de carga",
    "IL1": "Corrente média em L1",
    "IL2": "Corrente média em L2",
    "VC1": "Tensão média em C1 (acoplamento)",
    "L1": "Indutância L1",
    "L2": "Indutância L2",
    "L_crit": "Indutância crítica (fronteira MCC/MCD)",
    "dIL1": "Ondulação de corrente em L1 (pico a pico)",
    "dIL2": "Ondulação de corrente em L2 (pico a pico)",
    "IL1_pk": "Corrente de pico em L1",
    "C_o": "Capacitor de saída",
    "C1": "Capacitor de acoplamento C1",
    "dVo": "Ondulação da tensão de saída (pico a pico)",
    "dVC1": "Ondulação em C1 (pico a pico)",
    "Vo_avg": "Tensão média de saída (modelo médio)",
    "V_sw": "Tensão máxima na chave",
    "V_d": "Tensão reversa máxima no diodo",
    "Isw_rms": "Corrente eficaz na chave",
    "Isw_pk": "Corrente de pico na chave",
    "Id_avg": "Corrente média no diodo",
    "P_Q1": "Perdas na chave (condução + comutação)",
    "P_D1": "Perdas no diodo",
    "P_gate": "Potência de comando de porta",
    "eta_semi": "Rendimento só com semicondutores",
    "eta": "Rendimento estimado (com magnéticos)",
    "f_rhpz": "Zero no semiplano direito",
    "f0": "Ressonância do filtro LC (planta)",
    "fc": "Frequência de cruzamento do laço",
    "PM": "Margem de fase",
    "GM": "Margem de ganho",
    "Rc1": "R1 do divisor/compensador",
    "Rb": "R inferior do divisor",
    "Rc2": "R2 do compensador",
    "Rc3": "R3 do compensador (tipo III)",
    "Cc1": "C1 do compensador",
    "Cc2": "C2 do compensador",
    "Cc3": "C3 do compensador (tipo III)",
    **mag_labels(["L1", "L2"]),
}
SPEC_LABELS = {
    "topology": "Topologia",
    "mode": "Modo de condução",
    "switch": "Chave",
    "Vin": "Tensão de entrada",
    "Vo": "Tensão de saída (módulo)",
    "Io": "Corrente de saída",
    "fs": "Frequência de comutação",
    "ripple_iL": "Ondulação de corrente nos indutores (Δi/I)",
    "ripple_vo": "Ondulação de tensão na saída (ΔVo/Vo)",
    "ripple_vc1": "Ondulação em C1 (ΔvC1/VC1)",
    "L_ratio": "L/L_crit (MCD)",
    "compensator": "Compensador",
    "fc_ratio": "Cruzamento do laço (fc/fs)",
    "phase_margin": "Margem de fase desejada (°)",
    "Vm": "Amplitude da rampa do PWM",
    "Vref": "Tensão de referência",
    "R1": "Resistor superior do divisor",
    "V_gate": "Tensão de comando de porta",
}
ENUM_LABELS = {
    "buck": "Buck (abaixador)",
    "boost": "Boost (elevador)",
    "buckboost": "Buck-boost (inversor)",
    "cuk": "Ćuk (inversor)",
    "sepic": "SEPIC",
    "zeta": "Zeta",
    "MCC": "contínua (MCC)",
    "MCD": "descontínua (MCD)",
    "mosfet": "MOSFET",
    "igbt": "IGBT",
    "III": "tipo III",
    "II": "tipo II",
    "nenhum": "sem malha (só o estágio de potência)",
}


def _spec(spec: BaseModel) -> CcSpec:
    if not isinstance(spec, CcSpec):
        raise TypeError("DM-CC espera CcSpec")
    return spec


def _v(x: QuantityModel, unit: str) -> float:
    return float(x.to_pint().m_as(unit))


def _cap(log: CalcLog, key: str, desc: str, c: float) -> float:
    return float(commercial(log, key, desc, Q_(c, "F").to("uF"), "E12", "up").m_as("F"))


class CcModule:
    id = "DM-CC"
    family = "potencia"
    title = "Conversores CC-CC não isolados"
    spec_schema = CcSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão média de saída", "multímetro CC", "Vo_avg"),
        LabItem("Ondulação de corrente no indutor", "osciloscópio + ponteira de corrente", "dIL1"),
        LabItem("Ondulação da tensão de saída", "osciloscópio (acoplamento CA)", "dVo"),
        LabItem("Razão cíclica do comando", "osciloscópio", "D"),
    ]
    questions = [
        "Por que a ondulação de corrente do indutor não depende da carga em MCC?",
        "Reduza a carga até a corrente do indutor tocar o zero: o que acontece com Vo em malha "
        "aberta?",
        "Por que o zero no semiplano direito limita a banda do laço do boost?",
    ]
    safety = [
        "Conversores chaveados geram picos de tensão: use ponteira com atenuação adequada e "
        "referência de terra correta (osciloscópio aterrado).",
        "Capacitores eletrolíticos carregados: descarregue antes de manusear.",
        "Comece com tensão de entrada reduzida e limite de corrente na fonte.",
    ]
    practice = {
        "objective": "Montar o conversor, verificar a razão cíclica, as ondulações e o rendimento.",
        "material": "Fonte CC com limite de corrente, gerador PWM ou controlador, "
        "osciloscópio, ponteira de corrente, multímetros, carga resistiva.",
        "procedure": [
            "Monte o estágio de potência; confira a polaridade do diodo e dos capacitores.",
            "Aplique o PWM com a razão cíclica calculada e tensão de entrada reduzida.",
            "Eleve a tensão até o valor nominal; meça Vo, ΔiL e ΔVo.",
            "Meça potência de entrada e de saída para obter o rendimento.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        return [
            Role(
                designator="Q1",
                category="igbt" if s.switch == "igbt" else "mosfet.n",
                description="Chave controlada",
            ),
            Role(designator="D1", category="diode", description="Diodo de roda livre"),
        ]

    def required_ratings(self, role: Role) -> list[str]:
        if role.designator == "D1":
            return ["VRRM", "IF(AV)"]
        return ["VCES", "IC"] if role.category == "igbt" else ["VDS", "ID"]

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        if role.designator == "D1":
            return rec.category.startswith(("diode.schottky", "diode.fast"))
        return True

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    # ------------------------------------------------------------------ helpers
    def _model(
        self,
        s: CcSpec,
        ron: float,
        L1: float = 1.0,
        L2: float = 1.0,
        C1: float = 1.0,
        Co: float = 1.0,
    ) -> SwitchedModel:
        R = _v(s.Vo, "V") / _v(s.Io, "A")
        if s.topology in FOURTH:
            return converter_model(s.topology, L1, C1, R, ron, L2, Co)
        return converter_model(s.topology, L1, Co, R, ron)

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vin, vo, io = _v(s.Vin, "V"), _v(s.Vo, "V"), _v(s.Io, "A")
        fs = _v(s.fs, "Hz")
        ts = 1 / fs
        R = vo / io
        vd = devices["D1"].drop.m_as("V") if "D1" in devices else 0.0
        sw = switch_data(devices["Q1"].record if "Q1" in devices else None)
        dd = diode_data(devices["D1"].record if "D1" in devices else None, vd)
        summary: dict[str, pint.Quantity] = {"R_load": Q_(R, "ohm")}
        log.add(
            record(
                "R_load",
                "Resistência de carga equivalente",
                r"R = V_o / I_o",
                output=Q_(R, "ohm"),
                inputs={"V_o": s.Vo.to_pint(), "I_o": s.Io.to_pint()},
            )
        )
        if s.mode == "MCC":
            out = self._ccm(s, log, warnings, sw, vd, R, vin, vo, io, fs, ts, summary)
        else:
            out = self._dcm(s, log, warnings, sw, vd, R, vin, vo, io, fs, ts, summary)
        i_on, i_off, i_rms, i_avg, v_sw, v_d, id_avg, hard = out
        sl, w = switch_losses(
            log, "Q1", sw, v_sw, i_on, i_off, i_rms, i_avg, fs, _v(s.V_gate, "V"), hard_on=hard
        )
        warnings += [DesignWarning(code="perdas", message=m) for m in w]
        pd, w = diode_losses(log, "D1", dd, id_avg, v_d, fs, hard=(s.mode == "MCC"))
        warnings += [DesignWarning(code="perdas", message=m) for m in w]
        po = vo * io
        eta = efficiency_step(log, po, {"Q1": sl.total, "D1": pd}, "eta_semi")
        summary |= {
            "V_sw": Q_(v_sw, "V"),
            "V_d": Q_(v_d, "V"),
            "Isw_rms": Q_(i_rms, "A"),
            "Isw_pk": Q_(i_off, "A"),
            "Id_avg": Q_(id_avg, "A"),
            "P_Q1": Q_(sl.total, "W"),
            "P_D1": Q_(pd, "W"),
            "P_gate": Q_(sl.p_gate, "W").to("mW"),
            "eta_semi": Q_(eta, "percent"),
        }
        kv, ki = ("VCES", "IC") if s.switch == "igbt" else ("VDS", "ID")
        stresses = [
            _stress("Q1", kv, "Tensão máxima na chave", v_sw, "V", "V_sw"),
            _stress("Q1", ki, "Corrente eficaz na chave", i_rms, "A", "Isw_rms"),
            _stress("D1", "VRRM", "Tensão reversa no diodo", v_d, "V", "V_d"),
            _stress("D1", "IF(AV)", "Corrente média no diodo", id_avg, "A", "Id_avg"),
        ]
        traces = self._traces(s, summary)
        an = Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": Q_(sl.total, "W"), "D1": Q_(pd, "W")},
            warnings=warnings,
            convergence_keys=("D",),
            traces=traces,
            trace_period=Q_(ts, "s"),
        )
        if s.mode == "MCC" and s.compensator != "nenhum":
            self._loop(s, an, sw, vd)
        return an

    # ------------------------------------------------------------------ MCC
    def _ccm(
        self,
        s: CcSpec,
        log: CalcLog,
        warnings: list[DesignWarning],
        sw: SwitchData,
        vd: float,
        R: float,
        vin: float,
        vo: float,
        io: float,
        fs: float,
        ts: float,
        summary: dict[str, pint.Quantity],
    ) -> tuple[float, float, float, float, float, float, float, bool]:
        u = np.array([vin, vd])
        # IGBT: VCE(sat) as an equivalent resistance at the on-state current (iterated below)
        ron = sw.r_on
        D = 0.5
        for _ in range(30):
            m_r = self._model(s, ron)
            D = solve_duty(_const(m_r), vo, u)
            X = steady_state(self._model(s, ron), D, u)
            i_s = X[0] + (X[2] if s.topology in FOURTH else 0.0)
            if sw.kind != "igbt":
                break
            new = sw.v_on / max(i_s, 1e-9)
            if abs(new - ron) < 1e-9 * max(new, 1e-9):
                break
            ron = new
        m = self._model(s, ron)
        X = steady_state(m, D, u)
        dx = m.A1 @ X + m.B1 @ u  # slopes in the on interval with L = C = 1
        fourth = s.topology in FOURTH
        ideal_d = {
            "buck": vo / vin,
            "boost": 1 - vin / vo,
            "buckboost": vo / (vin + vo),
            "cuk": vo / (vin + vo),
            "sepic": vo / (vin + vo),
            "zeta": vo / (vin + vo),
        }[s.topology]
        log.add(
            record(
                "D",
                "Razão cíclica (modelo médio com R_on e V_F)",
                r"\mathbf{0} = (D\mathbf{A}_1 + D'\mathbf{A}_2)\mathbf{X} + (D\mathbf{B}_1 + "
                r"D'\mathbf{B}_2)\mathbf{U},\; X_{v_o} = V_o",
                output=Q_(D, ""),
                inputs={
                    "V_in": Q_(vin, "V"),
                    "V_o": Q_(vo, "V"),
                    "R_on": Q_(ron, "ohm"),
                    "V_F": Q_(vd, "V"),
                    "D_ideal": Q_(ideal_d, ""),
                },
                assumptions=[
                    "modo de condução contínua, ondulação pequena (modelo médio)",
                    "chave = R_on; diodo = queda constante V_F"
                    + ("; IGBT: R_on = V_CE(sat)/I_chave" if sw.kind == "igbt" else ""),
                ],
                reference=E_AVG,
            )
        )
        il1 = float(X[0])
        log.add(
            record(
                "IL1",
                "Corrente média em L1 (regime do modelo médio)",
                r"\mathbf{X} = -\mathbf{A}^{-1}\mathbf{B}\mathbf{U}",
                output=Q_(il1, "A"),
                inputs={"D": Q_(D, ""), "R": Q_(R, "ohm")},
                reference=E_AVG,
            )
        )
        vl1 = abs(float(dx[0]))  # L1 voltage in the on interval
        r = s.ripple_iL
        L1 = vl1 * D * ts / (r * abs(il1))
        log.add(
            record(
                "L1",
                "Indutância L1 para a ondulação pedida",
                r"L_1 = \frac{v_{L1,on}\,D\,T_s}{\Delta i_{L1}}",
                output=Q_(L1, "H").to("uH"),
                inputs={
                    "v_{L1,on}": Q_(vl1, "V"),
                    "D": Q_(D, ""),
                    "T_s": Q_(ts, "s").to("us"),
                    "Δi_L1": Q_(r * abs(il1), "A"),
                },
                assumptions=["aproximação de pequena ondulação: tensão no indutor constante"],
                reference=E_SS,
            )
        )
        dil1 = vl1 * D * ts / L1
        summary |= {
            "D": Q_(D, ""),
            "IL1": Q_(il1, "A"),
            "L1": Q_(L1, "H").to("uH"),
            "dIL1": Q_(dil1, "A"),
            "IL1_pk": Q_(abs(il1) + dil1 / 2, "A"),
        }
        L2 = 1.0
        dil2 = 0.0
        il2 = 0.0
        if fourth:
            il2 = float(X[2])
            vl2 = abs(float(dx[2]))
            L2 = vl2 * D * ts / (r * abs(il2))
            log.add(
                record(
                    "L2",
                    "Indutância L2 para a ondulação pedida",
                    r"L_2 = \frac{v_{L2,on}\,D\,T_s}{\Delta i_{L2}}",
                    output=Q_(L2, "H").to("uH"),
                    inputs={
                        "v_{L2,on}": Q_(vl2, "V"),
                        "I_L2": Q_(il2, "A"),
                        "Δi_L2": Q_(r * abs(il2), "A"),
                    },
                    reference=E_SS,
                )
            )
            dil2 = vl2 * D * ts / L2
            vc1 = float(X[1])
            ic1 = abs(float(dx[1]))  # C1 current in the on interval
            C1_req = ic1 * D * ts / (s.ripple_vc1 * vc1)
            log.add(
                record(
                    "C1_req",
                    "Capacitor de acoplamento para a ondulação pedida",
                    r"C_1 = \frac{|i_{C1,on}|\,D\,T_s}{\Delta v_{C1}}",
                    output=Q_(C1_req, "F").to("uF"),
                    inputs={"i_{C1,on}": Q_(ic1, "A"), "V_C1": Q_(vc1, "V")},
                    assumptions=["corrente em C1 constante em cada intervalo (pequena ondulação)"],
                    reference=E_SS,
                )
            )
            C1 = _cap(log, "C1", "C1 comercial", C1_req)
            dvc1 = ic1 * D * ts / C1
            summary |= {
                "IL2": Q_(il2, "A"),
                "L2": Q_(L2, "H").to("uH"),
                "dIL2": Q_(dil2, "A"),
                "VC1": Q_(vc1, "V"),
                "C1": Q_(C1, "F").to("uF"),
                "dVC1": Q_(dvc1, "V"),
            }
        # output capacitor
        dvo_spec = s.ripple_vo * vo
        if s.topology in OUT_FROM_L:
            di_o = dil2 if fourth else dil1
            co_req = di_o / (8 * fs * dvo_spec)
            log.add(
                record(
                    "C_o_req",
                    "Capacitor de saída (corrente triangular do indutor)",
                    r"C_o = \frac{\Delta i_L}{8 f_s \Delta V_o}",
                    output=Q_(co_req, "F").to("uF"),
                    inputs={
                        "Δi_L": Q_(di_o, "A"),
                        "f_s": s.fs.to_pint(),
                        "ΔV_o": Q_(dvo_spec, "V"),
                    },
                    assumptions=["capacitor ideal (sem RSE)"],
                    reference=E_SS,
                )
            )
        else:
            co_req = io * D * ts / dvo_spec
            log.add(
                record(
                    "C_o_req",
                    "Capacitor de saída (descarrega com I_o durante D·Ts)",
                    r"C_o = \frac{I_o D T_s}{\Delta V_o}",
                    output=Q_(co_req, "F").to("uF"),
                    inputs={"I_o": s.Io.to_pint(), "D": Q_(D, ""), "ΔV_o": Q_(dvo_spec, "V")},
                    assumptions=["capacitor ideal (sem RSE)"],
                    reference=E_SS,
                )
            )
        Co = _cap(log, "C_o", "Capacitor de saída comercial", co_req)
        dvo = (
            (dil2 if fourth else dil1) / (8 * fs * Co)
            if s.topology in OUT_FROM_L
            else io * D * ts / Co
        )
        log.add(
            record(
                "dVo",
                "Ondulação de saída com o capacitor comercial",
                r"\Delta V_o = \frac{\Delta i_L}{8 f_s C_o}"
                if s.topology in OUT_FROM_L
                else r"\Delta V_o = \frac{I_o D T_s}{C_o}",
                output=Q_(dvo, "V").to("mV"),
                inputs={"C_o": Q_(Co, "F").to("uF")},
                reference=E_SS,
            )
        )
        summary |= {"C_o": Q_(Co, "F").to("uF"), "dVo": Q_(dvo, "V").to("mV")}
        summary["Vo_avg"] = Q_(float(X[m.out]), "V")
        # critical inductance (boundary): ripple/2 equals the average current
        i_sum = abs(il1) + abs(il2)
        if fourth:
            le = L1 * L2 / (L1 + L2)
            vle = vl1  # both inductors see Vin in the on interval (ideal)
            lcrit = vle * D * ts / (2 * i_sum)
            log.add(
                record(
                    "L_crit",
                    "Indutância equivalente crítica (fronteira MCC/MCD)",
                    r"L_{e,crit} = \frac{V_{L,on} D T_s}{2(I_{L1} + I_{L2})},\;"
                    r"L_e = L_1 \parallel L_2",
                    output=Q_(lcrit, "H").to("uH"),
                    inputs={"L_e": Q_(le, "H").to("uH"), "I_L1 + I_L2": Q_(i_sum, "A")},
                    reference=E_DCM,
                )
            )
            if le < lcrit:
                warnings.append(
                    DesignWarning(
                        code="mcd", message="Com esses indutores o conversor entra em MCD."
                    )
                )
        else:
            lcrit = vl1 * D * ts / (2 * abs(il1))
            log.add(
                record(
                    "L_crit",
                    "Indutância crítica (fronteira MCC/MCD)",
                    r"L_{crit} = \frac{v_{L,on} D T_s}{2 I_L}",
                    output=Q_(lcrit, "H").to("uH"),
                    inputs={"I_L": Q_(il1, "A")},
                    assumptions=["MCC exige L > L_crit, isto é, Δi/I < 2"],
                    reference=E_DCM,
                )
            )
        summary["L_crit"] = Q_(lcrit, "H").to("uH")
        # switch and diode currents and voltages
        di_s = dil1 + dil2
        i_avg_on = i_sum
        i_on = i_avg_on - di_s / 2
        i_off = i_avg_on + di_s / 2
        i_rms = math.sqrt(D * (i_avg_on**2 + di_s**2 / 12))
        id_avg = (1 - D) * i_avg_on
        vo_max = vo + dvo / 2
        vc1_max = (
            float(summary["VC1"].m_as("V")) + float(summary["dVC1"].m_as("V")) / 2
            if fourth
            else 0.0
        )
        v_sw, v_d = {
            "buck": (vin, vin),
            "boost": (vo_max + vd, vo_max),
            "buckboost": (vin + vo_max + vd, vin + vo_max),
            "cuk": (vc1_max + vd, vc1_max),
            "sepic": (vc1_max + vo_max + vd, vc1_max + vo_max),
            "zeta": (vin + vc1_max + vd, vin + vc1_max),
        }[s.topology]
        log.add(
            record(
                "Isw_rms",
                "Corrente eficaz na chave (trapezoidal)",
                r"I_{S,rms} = \sqrt{D\left(I^2 + \Delta i^2/12\right)}",
                output=Q_(i_rms, "A"),
                inputs={"I": Q_(i_avg_on, "A"), "Δi": Q_(di_s, "A"), "D": Q_(D, "")},
                assumptions=["corrente da chave = soma das correntes dos indutores na condução"],
                reference=E_SS,
            )
        )
        log.add(
            record(
                "V_sw",
                "Tensões máximas na chave e no diodo",
                r"V_{S,max},\,V_{D,max} \text{ do intervalo em que cada um bloqueia}",
                output=Q_(v_sw, "V"),
                inputs={"V_in": Q_(vin, "V"), "V_o,max": Q_(vo_max, "V"), "V_F": Q_(vd, "V")}
                | ({"V_C1,max": Q_(vc1_max, "V")} if fourth else {}),
                assumptions=["sem sobretensão de indutâncias parasitas (ver snubber em DM-CMD)"],
                reference=E_SS,
            )
        )
        log.add(
            record(
                "Id_avg",
                "Corrente média no diodo",
                r"I_{D,avg} = (1 - D)\,I",
                output=Q_(id_avg, "A"),
                inputs={"I": Q_(i_avg_on, "A"), "D": Q_(D, "")},
                reference=E_SS,
            )
        )
        self._needs = [
            InductorNeed("L1", L1, abs(il1) + dil1 / 2, math.sqrt(il1**2 + dil1**2 / 12), dil1, fs)
        ]
        if fourth:
            self._needs.append(
                InductorNeed(
                    "L2", L2, abs(il2) + dil2 / 2, math.sqrt(il2**2 + dil2**2 / 12), dil2, fs
                )
            )
        return i_on, i_off, i_rms, D * i_avg_on, v_sw, v_d, id_avg, True

    # ------------------------------------------------------------------ MCD
    def _dcm(
        self,
        s: CcSpec,
        log: CalcLog,
        warnings: list[DesignWarning],
        sw: SwitchData,
        vd: float,
        R: float,
        vin: float,
        vo: float,
        io: float,
        fs: float,
        ts: float,
        summary: dict[str, pint.Quantity],
    ) -> tuple[float, float, float, float, float, float, float, bool]:
        t = s.topology
        # critical inductance at the CCM boundary (ideal switch, diode drop kept)
        if t == "buck":
            d_b = (vo + vd) / (vin + vd)
            v_on, v_off = vin - vo, vo + vd
            il_b = io
        elif t == "boost":
            d_b = 1 - vin / (vo + vd)
            v_on, v_off = vin, vo + vd - vin
            il_b = io / (1 - d_b)
        else:
            d_b = (vo + vd) / (vin + vo + vd)
            v_on, v_off = vin, vo + vd
            il_b = io / (1 - d_b)
        lcrit = v_on * d_b * ts / (2 * il_b)
        log.add(
            record(
                "L_crit",
                "Indutância crítica (fronteira MCC/MCD)",
                r"L_{crit} = \frac{v_{L,on} D_{MCC} T_s}{2 I_L}",
                output=Q_(lcrit, "H").to("uH"),
                inputs={"v_{L,on}": Q_(v_on, "V"), "D_MCC": Q_(d_b, ""), "I_L": Q_(il_b, "A")},
                reference=E_DCM,
            )
        )
        L1 = s.L_ratio * lcrit
        log.add(
            record(
                "L1",
                "Indutância em MCD",
                r"L = k\,L_{crit}",
                output=Q_(L1, "H").to("uH"),
                inputs={"k": Q_(s.L_ratio, "")},
                reference=E_DCM,
            )
        )
        K = 2 * L1 / (R * ts)
        # volt-second balance with the diode drop: D2 = D·v_on/v_off; Io from the average
        # of the triangle delivered to the output
        if t == "buck":
            # Io = average inductor current = Ipk (D + D2)/2, Ipk = v_on D Ts / L
            D = math.sqrt(2 * L1 * io / (v_on * ts * (1 + v_on / v_off)))
            latex = r"I_o = \frac{v_{on} D T_s}{2L}\,D\left(1 + \frac{v_{on}}{v_{off}}\right)"
        else:
            # Io = average diode current = Ipk·D2/2
            D = math.sqrt(2 * L1 * io * v_off / (v_on**2 * ts))
            latex = r"I_o = \frac{v_{on} D T_s}{2L}\,\frac{D\,v_{on}}{v_{off}}"
        D2 = D * v_on / v_off
        ipk = v_on * D * ts / L1
        log.add(
            record(
                "D",
                "Razão cíclica em MCD (balanço volt-segundo com V_F)",
                latex,
                output=Q_(D, ""),
                inputs={
                    "v_on": Q_(v_on, "V"),
                    "v_off": Q_(v_off, "V"),
                    "L": Q_(L1, "H").to("uH"),
                    "I_o": Q_(io, "A"),
                    "K = 2L/(RT_s)": Q_(K, ""),
                },
                assumptions=["chave ideal (R_on desprezado); diodo com queda V_F constante"],
                reference=E_DCM,
            )
        )
        if D + D2 >= 1:
            raise ValueError(
                "Com esse L o conversor não fica em MCD (D + D₂ ≥ 1); reduza L/L_crit."
            )
        log.add(
            record(
                "D2",
                "Intervalo de desmagnetização",
                r"D_2 = D\,\frac{v_{on}}{v_{off}}",
                output=Q_(D2, ""),
                inputs={"D": Q_(D, "")},
                reference=E_DCM,
            )
        )
        log.add(
            record(
                "IL1_pk",
                "Corrente de pico no indutor",
                r"I_{pk} = \frac{v_{on} D T_s}{L}",
                output=Q_(ipk, "A"),
                inputs={"L": Q_(L1, "H").to("uH")},
                reference=E_DCM,
            )
        )
        il_avg = ipk * (D + D2) / 2
        il_rms = ipk * math.sqrt((D + D2) / 3)
        i_rms = ipk * math.sqrt(D / 3)
        id_avg = ipk * D2 / 2
        # output ripple: charge above Io of the triangular current feeding the capacitor
        span = D + D2 if t == "buck" else D2
        dq = (ipk - io) ** 2 * span * ts / (2 * ipk) if ipk > io else 0.0
        co_req = dq / (s.ripple_vo * vo)
        log.add(
            record(
                "C_o_req",
                "Capacitor de saída em MCD (carga acima de I_o)",
                r"C_o = \frac{(I_{pk} - I_o)^2\,\delta\,T_s}{2 I_{pk}\,\Delta V_o}",
                output=Q_(co_req, "F").to("uF"),
                inputs={"δ": Q_(span, ""), "I_pk": Q_(ipk, "A"), "ΔV_o": Q_(s.ripple_vo * vo, "V")},
                assumptions=[
                    "corrente triangular entregue ao nó de saída (indutor no buck, diodo "
                    "nos outros)",
                    "carga constante I_o; capacitor sem RSE",
                ],
                reference=E_DCM,
            )
        )
        Co = _cap(log, "C_o", "Capacitor de saída comercial", co_req)
        dvo = dq / Co
        v_sw, v_d = {
            "buck": (vin, vin),
            "boost": (vo + dvo / 2 + vd, vo + dvo / 2),
            "buckboost": (vin + vo + dvo / 2 + vd, vin + vo + dvo / 2),
        }[t]
        log.add(
            record(
                "V_sw",
                "Tensão máxima na chave",
                r"V_{S,max}",
                output=Q_(v_sw, "V"),
                inputs={"V_in": Q_(vin, "V"), "V_o": Q_(vo, "V")},
                reference=E_SS,
            )
        )
        summary |= {
            "D": Q_(D, ""),
            "D2": Q_(D2, ""),
            "L1": Q_(L1, "H").to("uH"),
            "L_crit": Q_(lcrit, "H").to("uH"),
            "IL1": Q_(il_avg, "A"),
            "IL1_pk": Q_(ipk, "A"),
            "dIL1": Q_(ipk, "A"),
            "C_o": Q_(Co, "F").to("uF"),
            "dVo": Q_(dvo, "V").to("mV"),
            "Vo_avg": Q_(vo, "V"),
        }
        self._needs = [InductorNeed("L1", L1, ipk, il_rms, ipk, fs)]
        return 0.0, ipk, i_rms, ipk * D / 2, v_sw, v_d, id_avg, False

    # ------------------------------------------------------------------ loop
    def _loop(self, s: CcSpec, an: Analysis, sw: SwitchData, vd: float) -> None:
        sm = an.summary
        log = an.log
        vin, vo = _v(s.Vin, "V"), _v(s.Vo, "V")
        fs = _v(s.fs, "Hz")
        D = float(sm["D"].m_as(""))
        L1 = float(sm["L1"].m_as("H"))
        Co = float(sm["C_o"].m_as("F"))
        L2 = float(sm["L2"].m_as("H")) if "L2" in sm else 1.0
        C1 = float(sm["C1"].m_as("F")) if "C1" in sm else 1.0
        ron = sw.r_on if sw.kind == "mosfet" else 0.0
        m = self._model(s, ron, L1, L2, C1, Co)
        u = np.array([vin, vd])
        H = _v(s.Vref, "V") / vo
        vm = _v(s.Vm, "V")
        # zeros and poles of v̂o/d̂ (transmission zeros of the averaged model)
        A = D * m.A1 + (1 - D) * m.A2
        X = steady_state(m, D, u)
        Bd = ((m.A1 - m.A2) @ X + (m.B1 - m.B2) @ u).reshape(-1, 1)
        C = np.zeros((1, A.shape[0]))
        C[0, m.out] = 1.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z, p, _k = signal.ss2zpk(A, Bd, C, np.zeros((1, 1)))
        rhp = [abs(zz) / (2 * math.pi) for zz in z if zz.real > 1e-9 * abs(zz)]
        f0 = min(abs(pp) for pp in p) / (2 * math.pi)
        sm["f0"] = Q_(f0, "Hz").to("kHz")
        fc = s.fc_ratio * fs
        notes = [f"f_c = {s.fc_ratio:g}·f_s"]
        if rhp:
            frhp = min(rhp)
            sm["f_rhpz"] = Q_(frhp, "Hz").to("kHz")
            log.add(
                record(
                    "f_rhpz",
                    "Zero no semiplano direito de v̂o/d̂",
                    r"G_{vd}(s) = \mathbf{C}(s\mathbf{I} - \mathbf{A})^{-1}\mathbf{B}_d,\; "
                    r"\text{zero com Re} > 0",
                    output=Q_(frhp, "Hz").to("kHz"),
                    inputs={"D": Q_(D, ""), "L_1": Q_(L1, "H").to("uH")},
                    reference=E_AVG,
                )
            )
            if fc > frhp / 5:
                fc = frhp / 5
                notes.append("limitado a f_RHPZ/5 (o zero no semiplano direito tira fase)")
        if s.compensator == "II" and fc > f0 and not rhp and s.topology in OUT_FROM_L:
            notes.append("tipo II acima da ressonância LC sem RSE: o avanço pode não bastar")
        R1 = _v(s.R1, "ohm")
        f = np.logspace(math.log10(max(f0 / 100, 1.0)), math.log10(fs / 2), 600)
        G = H * gvd(m, D, u, f) / vm
        gph = np.degrees(np.unwrap(np.angle(G)))
        limit = 85.0 if s.compensator == "II" else 170.0
        chosen: tuple[float, Compensator, Margins, int] | None = None
        fc_try = fc
        lgf = np.log10(f)

        def plant_at(fx: float) -> tuple[float, float]:
            """|G| and ∠G (degrees, on the branch unwrapped from DC) exactly at fx."""
            g = complex(H * gvd(m, D, u, np.array([fx]))[0] / vm)
            branch = float(np.interp(math.log10(fx), lgf, gph))
            exact = math.degrees(np.angle(g))
            return abs(g), exact + 360.0 * round((branch - exact) / 360.0)

        while fc_try > f[0] * 3:
            mag, ph = plant_at(fc_try)
            if boost_needed(s.phase_margin, ph) <= limit:
                comp = k_factor(CalcLog(), s.compensator, fc_try, mag, ph, s.phase_margin, R1)
                mg_try, nc = margins(f, G * round_comp(comp).h(f))
                if (
                    math.isfinite(mg_try.pm)
                    and mg_try.pm >= s.phase_margin - 15
                    and nc == 1
                    and abs(mg_try.fc / fc_try - 1) < 0.3
                ):
                    chosen = (fc_try, comp, mg_try, nc)
                    break
            fc_try *= 0.9
        if chosen is None:
            an.warnings.append(
                DesignWarning(
                    code="compensador",
                    message=f"O compensador tipo {s.compensator} não alcançou margem de fase "
                    f"≥ {s.phase_margin - 15:.0f}° com um só cruzamento em nenhuma frequência "
                    "abaixo da pedida; experimente o outro tipo ou reduza a margem pedida.",
                )
            )
            return
        fc, _, _, _ = chosen
        if fc < s.fc_ratio * fs * 0.99 and not (rhp and fc >= min(rhp) / 5 * 0.99):
            notes.append(
                f"f_c reduzida para {fc / 1e3:.3g} kHz: acima dela o avanço de fase necessário "
                "passava do limite do compensador ou a margem ficava baixa"
            )
        mag, ph = plant_at(fc)
        comp = k_factor(log, s.compensator, fc, mag, ph, s.phase_margin, R1)
        rc = round_comp(comp)
        rb = R1 * H / (1 - H)
        T = G * rc.h(f)
        mg, _nc = margins(f, T)
        log.add(
            record(
                "PM",
                "Margens do laço com os componentes comerciais",
                r"T(j\omega) = \frac{H\,G_{vd}(j\omega)}{V_m}\,G_c(j\omega),\; "
                r"MF = 180° + \angle T(j\omega_c)",
                output=Q_(mg.pm, "degree"),
                inputs={
                    "f_c": Q_(mg.fc, "Hz").to("kHz"),
                    "H": Q_(H, ""),
                    "V_m": Q_(vm, "V"),
                    "R_1": Q_(rc.R1, "ohm").to("kohm"),
                    "R_2": Q_(rc.R2, "ohm").to("kohm"),
                    "C_1": Q_(rc.C1, "F").to("nF"),
                    "C_2": Q_(rc.C2, "F").to("nF"),
                }
                | (
                    {"R_3": Q_(rc.R3, "ohm").to("kohm"), "C_3": Q_(rc.C3, "F").to("nF")}
                    if rc.kind == "III"
                    else {}
                ),
                assumptions=[
                    "resistores E24 e capacitores E12 (mais próximos)",
                    "amplificador de erro ideal; modulador sem atraso",
                    *notes,
                ],
                reference=E_LOOP,
            )
        )
        sm |= {
            "fc": Q_(mg.fc, "Hz").to("kHz"),
            "PM": Q_(mg.pm, "degree"),
            "Rc1": Q_(rc.R1, "ohm").to("kohm"),
            "Rb": Q_(rb, "ohm").to("kohm"),
            "Rc2": Q_(rc.R2, "ohm").to("kohm"),
            "Cc1": Q_(rc.C1, "F").to("nF"),
            "Cc2": Q_(rc.C2, "F").to("nF"),
        }
        if rc.kind == "III":
            sm |= {"Rc3": Q_(rc.R3, "ohm").to("kohm"), "Cc3": Q_(rc.C3, "F").to("nF")}
        if mg.gm_db is not None:
            sm["GM"] = Q_(mg.gm_db, "")  # dB (kept dimensionless: pint dB is a power ratio)
        if not math.isfinite(mg.pm) or mg.pm < s.phase_margin - 15:
            an.warnings.append(
                DesignWarning(
                    code="margem_fase",
                    message=f"A margem de fase com os componentes comerciais ficou em "
                    f"{mg.pm:.0f}° (pedido {s.phase_margin:.0f}°).",
                )
            )
        an.bode_f = Trace(unit="Hz", values=[float(x) for x in f])
        an.bode = {
            "|G_vd·H/V_m| (planta)": Trace(unit="", values=[float(x) for x in np.abs(G)]),
            "|T| (laço)": Trace(unit="", values=[float(x) for x in np.abs(T)]),
        }

    # ------------------------------------------------------------------ waveforms
    def _traces(self, s: CcSpec, sm: Mapping[str, pint.Quantity]) -> dict[str, Trace]:
        n = 720
        t = np.arange(n) / n
        D = float(sm["D"].m_as(""))
        il = float(sm["IL1"].m_as("A"))
        di = float(sm["dIL1"].m_as("A"))
        if s.mode == "MCC":
            w = np.where(t < D, -di / 2 + di * t / D, di / 2 - di * (t - D) / (1 - D))
            i = il + w
        else:
            d2 = float(sm["D2"].m_as(""))
            ipk = float(sm["IL1_pk"].m_as("A"))
            i = np.where(t < D, ipk * t / D, np.where(t < D + d2, ipk * (1 - (t - D) / d2), 0.0))
        return {"i_L1": Trace(unit="A", values=[float(x) for x in i])}

    # ------------------------------------------------------------------ magnetics
    def finish(
        self,
        spec: BaseModel,
        analysis: Analysis,
        devices: Mapping[str, Device],
        catalogue: Callable[[str], list[ComponentRecord]],
    ) -> None:
        s = _spec(spec)
        self.analyse(spec, devices)  # refresh the inductor needs for these devices
        mag = design_inductors(self._needs, catalogue, _v(s.TA, "degC"))
        p_mag = merge_magnetics(analysis.log, analysis.summary, analysis.warnings, mag)
        po = _v(s.Vo, "V") * _v(s.Io, "A")
        losses = {k: float(v.m_as("W")) for k, v in analysis.losses.items()} | mag.losses
        eta = efficiency_step(analysis.log, po, losses, "eta")
        analysis.summary["eta"] = Q_(eta, "percent")
        if p_mag == 0 and not mag.losses:
            analysis.warnings.append(
                DesignWarning(
                    code="magnetico",
                    message="Indutores não projetados (sem núcleo liberado que atenda): o "
                    "rendimento não inclui as perdas magnéticas.",
                )
            )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        vin, vo, io = _v(s.Vin, "V"), _v(s.Vo, "V"), _v(s.Io, "A")
        fs = _v(s.fs, "Hz")
        ts = 1 / fs
        R = vo / io
        vd = devices["D1"].drop.m_as("V") if "D1" in devices else 0.0
        sw = switch_data(devices["Q1"].record if "Q1" in devices else None)
        D = q(summary, "D", "")
        L1 = q(summary, "L1", "H")
        Co = q(summary, "C_o", "F")
        # initial state at the start of the on interval (switch turns on at t = 0): inductor
        # currents at their valley, capacitors discharged by the on interval at their peak;
        # starting on the ripple phase avoids exciting the slow L-C resonances
        il1 = q(summary, "IL1", "A") - q(summary, "dIL1", "A") / 2 if s.mode == "MCC" else 0.0
        t = s.topology
        dvo = q(summary, "dVo", "V")
        vo_ic = vo + (dvo / 2 if t not in OUT_FROM_L else 0.0)
        lines = [
            spice_switch("SWQ", sw),
            spice_diode("DFW", vd),
            f"VIN in 0 DC {vin:.9g}",
            pwm_source("VG", "g", D, fs),
            f"RL out 0 {R:.9g}",
        ]
        if t in ("buckboost", "cuk"):
            vo_ic = -vo_ic
        lines.append(f"CO out 0 {Co:.9g} IC={vo_ic:.9g}")
        vprobe = "-v(out)" if t in ("buckboost", "cuk") else "v(out)"
        if t == "buck":
            lines += [
                "XQ in sw g SWQ",
                "XD 0 sw DFW",
                f"L1 sw x {L1:.9g} IC={il1:.9g}",
                "VIL1 x out 0",
            ]
        elif t == "boost":
            lines += [
                f"L1 in x {L1:.9g} IC={il1:.9g}",
                "VIL1 x sw 0",
                "XQ sw 0 g SWQ",
                "XD sw out DFW",
            ]
        elif t == "buckboost":
            lines += [
                "XQ in sw g SWQ",
                f"L1 sw x {L1:.9g} IC={il1:.9g}",
                "VIL1 x 0 0",
                "XD out sw DFW",
            ]
        else:
            L2 = q(summary, "L2", "H")
            C1 = q(summary, "C1", "F")
            il2 = q(summary, "IL2", "A") - q(summary, "dIL2", "A") / 2
            vc1 = q(summary, "VC1", "V") + q(summary, "dVC1", "V") / 2
            if t == "cuk":
                lines += [
                    f"L1 in a1 {L1:.9g} IC={il1:.9g}",
                    "VIL1 a1 a 0",
                    "XQ a 0 g SWQ",
                    f"C1 a b {C1:.9g} IC={vc1:.9g}",
                    "XD b 0 DFW",
                    f"L2 out y {L2:.9g} IC={il2:.9g}",
                    "VIL2 y b 0",
                ]
            elif t == "sepic":
                lines += [
                    f"L1 in a1 {L1:.9g} IC={il1:.9g}",
                    "VIL1 a1 a 0",
                    "XQ a 0 g SWQ",
                    f"C1 a b {C1:.9g} IC={vc1:.9g}",
                    f"L2 0 y {L2:.9g} IC={il2:.9g}",
                    "VIL2 y b 0",
                    "XD b out DFW",
                ]
            else:  # zeta
                lines += [
                    "XQ in a g SWQ",
                    f"L1 a a1 {L1:.9g} IC={il1:.9g}",
                    "VIL1 a1 0 0",
                    f"C1 b a {C1:.9g} IC={vc1:.9g}",
                    "XD 0 b DFW",
                    f"L2 b y {L2:.9g} IC={il2:.9g}",
                    "VIL2 y out 0",
                ]
        # settle: several output time constants (the analytic state is the initial condition)
        tau = 2 * R * Co
        n_per = int(min(max(300, 8 * tau / ts), 3000))
        checks = [
            SimCheck(
                quantity="Tensão média de saída",
                summary_key="Vo_avg",
                metric="avg",
                probe=vprobe,
                tolerance_pct=1.0 if s.mode == "MCC" else 3.0,
                justification="modelo médio de pequena ondulação"
                if s.mode == "MCC"
                else "MCD calculado sem R_on",
            ),
            SimCheck(
                quantity="Corrente média em L1",
                summary_key="IL1",
                metric="avg",
                probe="i(vil1)",
                tolerance_pct=2.0 if s.mode == "MCC" else 4.0,
                justification="modelo médio" if s.mode == "MCC" else "MCD calculado sem R_on",
            ),
            SimCheck(
                quantity="Ondulação de corrente em L1",
                summary_key="dIL1",
                metric="pp",
                probe="i(vil1)",
                tolerance_pct=5.0,
                justification="tensão no indutor tomada constante em cada intervalo",
            ),
        ]
        if s.topology in FOURTH:
            checks.append(
                SimCheck(
                    quantity="Corrente média em L2",
                    summary_key="IL2",
                    metric="avg",
                    probe="i(vil2)",
                    tolerance_pct=2.0,
                    justification="modelo médio",
                )
            )
        checks.append(
            SimCheck(
                quantity="Ondulação da tensão de saída",
                summary_key="dVo",
                metric="pp",
                probe=vprobe,
                tolerance_pct=15.0,
                justification="aproximações de carga (corrente da carga e do indutor "
                "constantes em cada intervalo)",
            )
        )
        probes = {"i_L1": "i(vil1)", "v_o": vprobe}
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[t]}, {ENUM_LABELS[s.mode]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=n_per * ts, unit="s"),
            tran_step=QuantityModel(value=ts / 400, unit="s"),
            period=QuantityModel(value=ts, unit="s"),
            probes=probes,
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        txt = {
            k: pretty(sm[src])
            for k, src in (
                ("L1", "L1"),
                ("L2", "L2"),
                ("C1", "C1"),
                ("Co", "C_o"),
                ("RL", "R_load"),
            )
            if src in sm
        }
        txt["VIN"] = pretty(s.Vin)
        comp: dict[str, str] = {
            k: pretty(sm[k]) for k in ("Rc1", "Rb", "Rc2", "Rc3", "Cc1", "Cc2", "Cc3") if k in sm
        }
        if comp:
            comp["Vref"] = pretty(s.Vref)
        parts = {c.designator: c.part_number for c in result.selection}
        note = f"{ENUM_LABELS[s.topology]}, {ENUM_LABELS[s.mode]}"
        if "D" in sm:
            note += f", D = {sm['D'].value:.3f}".replace(".", ",")
        return drawings_power.dcdc(s.topology, title, s.switch, txt, parts, note, comp)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        sm = result.summary
        rows = []
        for k, desc in (("L1", "Indutor L1"), ("L2", "Indutor L2")):
            if k in sm:
                note = (
                    f"{int(sm[k + '_N'].value)} espiras, entreferro {sm[k + '_gap'].value:.2f} mm"
                    if k + "_N" in sm
                    else "projetar o magnético"
                )
                rows.append(passive(k, desc, format_eng(sm[k].to_pint()), note))
        for k, desc in (("C1", "Capacitor de acoplamento"), ("C_o", "Capacitor de saída")):
            if k in sm:
                rows.append(
                    passive(
                        k,
                        desc,
                        format_eng(sm[k].to_pint()),
                        "baixa RSE; tensão ≥ 1,5× a de trabalho",
                    )
                )
        for k in ("Rc1", "Rb", "Rc2", "Rc3", "Cc1", "Cc2", "Cc3"):
            if k in sm:
                rows.append(passive(k, LABELS[k], format_eng(sm[k].to_pint())))
        return rows


def _const(m: SwitchedModel) -> Callable[[float], SwitchedModel]:
    return lambda _d: m


def _stress(des: str, key: str, label: str, v: float, unit: str, step: str) -> Stress:
    return Stress(
        designator=des,
        key=key,
        label=label,
        value=QuantityModel(value=v, unit=unit),
        calc_step_id=step,
    )


from circuitos.design.base import Stress  # noqa: E402
