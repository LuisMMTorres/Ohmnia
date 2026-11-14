"""DM-SSA: small-signal amplifiers (common emitter, collector, base; common source).

Bias by voltage divider (DM-BIAS rules), then the hybrid-π model at the exact Q-point:
gm = IC/VT, rπ = β/gm, Cμ = Cobo, Cπ = gm/(2π·fT) − Cμ (Sedra & Smith, *Microelectronic
Circuits*, 7th ed., ch. 7 and 10; Boylestad & Nashelsky, 11th ed., ch. 5 "BJT AC analysis"
and ch. 9 "BJT and JFET frequency response").

Mid-band formulas (Boylestad, ch. 5) give the gain, Zin and Zout; the coupling and bypass
capacitors put the emitter (source) bypass pole at f_L and the coupling poles a decade below
(design criterion). The whole equivalent circuit is then solved by nodal analysis at every
frequency (``design.smallsignal``), which gives the Bode plot and the exact f_L and f_H, the
same linear model SPICE uses in ``.ac``.
"""

from __future__ import annotations

import cmath
import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pint
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
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
from circuitos.design.devmodels import (
    BOYLESTAD,
    SEDRA,
    VT_300K,
    Bjt,
    Mos,
    bjt_model,
    hfe_entries,
    mos_model,
    quantity,
    with_capacitances,
)
from circuitos.design.engine import Analysis, Device
from circuitos.design.qpoint import bjt_q, mos_q, parallel, thevenin
from circuitos.design.smallsignal import Network, corner, log_grid
from circuitos.reports.common import BomRow, LabItem, capacitor_row, resistor_row
from circuitos.reports.schematic import Svg

Config = Literal["EC", "CC", "BC", "FC"]
REF = BOYLESTAD.model_copy(update={"chapter": "5 (BJT AC analysis)"})
REF_F = BOYLESTAD.model_copy(update={"chapter": "9 (BJT and JFET frequency response)"})
REF_FET = BOYLESTAD.model_copy(update={"chapter": "8 (FET amplifiers)"})
F1, F2, PPD = 1.0, 1e9, 20  # Bode sweep (Hz) and points per decade


class SsaSpec(BaseModel):
    config: Config = "EC"
    VCC: QuantityModel = QuantityModel(value=12, unit="V")
    IC: QuantityModel = QuantityModel(value=1, unit="mA")
    RL: QuantityModel = QuantityModel(value=10, unit="kohm")
    Rs: QuantityModel = QuantityModel(value=600, unit="ohm")  # signal source resistance
    Av: float = Field(default=10, ge=0, le=1000)  # |gain| target of EC/FC; 0: RE fully bypassed
    f_L: QuantityModel = QuantityModel(value=100, unit="Hz")
    Vs_pk: QuantityModel = QuantityModel(value=10, unit="mV")  # source amplitude (waveforms)
    f_sig: QuantityModel = QuantityModel(value=1, unit="kHz")
    kE: float = Field(default=0.1, ge=0.02, le=0.4)
    divider_k: float = Field(default=10, ge=2, le=100)
    VBE: QuantityModel = QuantityModel(value=0.7, unit="V")
    beta_ideal: float = Field(default=100, gt=1, le=2000)
    res_series: Literal["E12", "E24"] = "E24"
    cap_series: Literal["E3", "E6", "E12"] = "E6"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")


LABELS = {
    "IC_q": "Corrente de coletor/dreno no ponto Q",
    "VCE_q": "VCE/VDS no ponto Q",
    "gm": "Transcondutância gm",
    "r_pi": "Resistência rπ",
    "re": "Resistência re",
    "Av": "Ganho de tensão (base/porta → carga)",
    "Avs": "Ganho de tensão a partir da fonte",
    "Av_dB": "Ganho a partir da fonte (dB)",
    "Zin": "Impedância de entrada",
    "Zout": "Impedância de saída",
    "f_L": "Frequência de corte inferior (−3 dB)",
    "f_H": "Frequência de corte superior (−3 dB)",
    "f_L_est": "f_L estimada (soma dos polos)",
    "Vo_pk": "Amplitude da saída",
    "Vo_max_sym": "Excursão simétrica máxima (estimada)",
    "Cin": "Capacitor de acoplamento de entrada",
    "Cout": "Capacitor de acoplamento de saída",
    "CE": "Capacitor de desvio do emissor/fonte",
    "CB": "Capacitor de desvio da base",
    "RE1": "Parte não desviada de RE",
    "RE2": "Parte desviada de RE",
    "RC": "Resistor de coletor/dreno",
    "RE": "Resistor de emissor/fonte",
    "R1": "Resistor do divisor R1",
    "R2": "Resistor do divisor R2",
    "C_pi": "Capacitância Cπ",
    "C_mu": "Capacitância Cμ",
}
SPEC_LABELS = {
    "config": "Configuração",
    "VCC": "Alimentação",
    "IC": "Corrente de polarização",
    "RL": "Resistência de carga",
    "Rs": "Resistência da fonte de sinal",
    "Av": "Ganho desejado |Av| (EC/FC; 0 = RE todo desviado)",
    "f_L": "Frequência de corte inferior desejada",
    "Vs_pk": "Amplitude do sinal da fonte",
    "f_sig": "Frequência do sinal (formas de onda)",
    "kE": "VE como fração de VCC",
    "divider_k": "Critério do divisor (β·RE ≥ k·R2)",
    "VBE": "VBE na corrente de ensaio (premissa)",
    "beta_ideal": "β de projeto (passo ideal)",
    "res_series": "Série de resistores",
    "cap_series": "Série de capacitores",
}
ENUM_LABELS = {
    "EC": "emissor comum",
    "CC": "coletor comum (seguidor de emissor)",
    "BC": "base comum",
    "FC": "fonte comum (MOSFET)",
}


def _spec(spec: BaseModel) -> SsaSpec:
    if not isinstance(spec, SsaSpec):
        raise TypeError("DM-SSA espera SsaSpec")
    return spec


class SsaModule:
    id = "DM-SSA"
    family = "amplificadores"
    title = "Amplificador de pequenos sinais"
    spec_schema = SsaSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Corrente de polarização", "multímetro em série", "IC_q"),
        LabItem("Ganho na banda média", "osciloscópio, dois canais", "Avs"),
        LabItem("Frequência de corte inferior", "gerador + osciloscópio (−3 dB)", "f_L"),
        LabItem("Frequência de corte superior", "gerador + osciloscópio (−3 dB)", "f_H"),
        LabItem("Impedância de entrada", "resistor série + osciloscópio", "Zin"),
    ]
    questions = [
        "Por que o ganho do emissor comum depende de RE1 e quase não depende de β?",
        "Qual capacitor domina a frequência de corte inferior? Retire-o e meça de novo.",
        "O que limita a resposta em alta frequência? Relacione com o efeito Miller em Cμ.",
    ]
    practice = {
        "objective": "Montar o amplificador, conferir a polarização, medir o ganho na banda "
        "média e as frequências de corte, e comparar com o cálculo e a simulação.",
        "material": "Fonte CC, gerador de funções, osciloscópio de dois canais, multímetro e "
        "os componentes da lista.",
        "procedure": [
            "Monte o circuito e confira a polarização (VB, VE, VC) antes de aplicar sinal.",
            "Aplique a senoide do gerador pela resistência Rs na frequência do sinal.",
            "Meça a amplitude e a fase da saída; calcule o ganho.",
            "Varra a frequência para baixo e para cima até o ganho cair 3 dB.",
            "Aumente a amplitude até a saída ceifar; compare com a excursão estimada.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        if s.config == "FC":
            return [Role(designator="Q1", category="mosfet.n", description="MOSFET canal N")]
        return [Role(designator="Q1", category="bjt.npn", description="Transistor NPN")]

    def required_ratings(self, role: Role) -> list[str]:
        return ["VDS"] if role.category.startswith("mosfet") else ["VCEO", "IC"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        if role.category.startswith("mosfet"):
            vth = rec.parameters.get("VGS(th)")
            rds = rec.parameters.get("RDS(on)")
            return bool(vth and vth.min is not None and rds and rds.max is not None)
        return bool(hfe_entries(rec)) and "fT" in rec.parameters

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        q = quantity(rec, "IC", ("max",)) or quantity(rec, "ID", ("max",))
        return float(q.m_as("A")) if q is not None else 0.0

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vcc = s.VCC.to_pint().m_as("V")
        ic = s.IC.to_pint().m_as("A")
        rl = s.RL.to_pint().m_as("ohm")
        rsig = s.Rs.to_pint().m_as("ohm")
        fl = s.f_L.to_pint().m_as("Hz")
        rec = devices["Q1"].record
        fet = s.config == "FC"
        r: dict[str, float] = {}
        net = Network()
        net.R("sig", "b0", rsig)
        # ---------------------------------------------------------------- bias
        ve = s.kE * vcc
        if fet:
            m_f, w = mos_model(rec, log, "Q1")
            warnings += [DesignWarning(code="modelo", message=x) for x in w]
            vgs = m_f.VT + math.sqrt(2 * ic / m_f.KP)
            gm = math.sqrt(2 * m_f.KP * ic)
            re_tot = ve / ic
            rc_calc = (vcc - ve) / 2 / ic  # VDS ≈ (VDD − VS)/2 for symmetric swing
        else:
            m_b, w = bjt_model(rec, ic, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
            warnings += [DesignWarning(code="modelo", message=x) for x in w]
            ie = ic * (m_b.BF + 1) / m_b.BF
            re_tot = ve / ie
            rc_calc = (vcc - ve) / 2 / ic if s.config != "CC" else 0.0
            gm = ic / VT_300K
        re_q = log.add(
            record(
                "RE_calc",
                "Resistor de emissor/fonte pelo critério VE = kE·VCC",
                r"R_E = \frac{k_E V_{CC}}{I_E}",
                output=Q_(re_tot, "ohm"),
                inputs={"k_E": Q_(s.kE, ""), "V_{CC}": s.VCC.to_pint(), "I_C": s.IC.to_pint()},
                assumptions=["critério de projeto: VE ≈ 10 % de VCC"],
                reference=REF,
            )
        )
        if s.config == "CC":
            # follower: VE near VCC/2 for symmetric swing, no RC
            re_q = log.add(
                record(
                    "RE_cc",
                    "Seguidor de emissor: VE ≈ VCC/2 para excursão simétrica",
                    r"R_E = \frac{V_{CC}/2}{I_E}",
                    output=Q_(vcc / 2 / (ic * (1 + 1 / s.beta_ideal)), "ohm"),
                    inputs={"V_{CC}": s.VCC.to_pint(), "I_C": s.IC.to_pint()},
                    reference=REF,
                )
            )
        re_c = commercial(log, "RE", "RE comercial", re_q, s.res_series, "nearest").m_as("ohm")
        r["RE"] = re_c
        if s.config != "CC":
            rc_q = log.add(
                record(
                    "RC_calc",
                    "RC para VCE ≈ (VCC − VE)/2 (excursão simétrica)",
                    r"R_C = \frac{V_{CC} - V_E}{2 I_C}",
                    output=Q_(rc_calc, "ohm"),
                    inputs={"V_{CC}": s.VCC.to_pint(), "V_E": Q_(ve, "V"), "I_C": s.IC.to_pint()},
                    reference=REF,
                )
            )
            r["RC"] = commercial(log, "RC", "RC comercial", rc_q, s.res_series, "nearest").m_as(
                "ohm"
            )
        # split RE for the gain target (EC/FC)
        if s.config in ("EC", "FC") and s.Av > 0:
            rload = parallel(r["RC"], rl)
            if fet:
                re1_calc = (gm * rload / s.Av - 1) / gm
                latex = r"R_{S1} = \frac{g_m (R_D \parallel R_L)/|A_v| - 1}{g_m}"
            else:
                re1_calc = rload / s.Av - 1 / gm
                latex = r"R_{E1} = \frac{R_C \parallel R_L}{|A_v|} - r_e"
            re1_calc = min(max(re1_calc, 0.0), re_c)
            re1_q = log.add(
                record(
                    "RE1_calc",
                    "Parte não desviada de RE para o ganho desejado",
                    latex,
                    output=Q_(re1_calc, "ohm"),
                    inputs={"|A_v|": Q_(s.Av, ""), "g_m": Q_(gm, "S").to("mS")},
                    assumptions=["r_e = 1/g_m no ponto Q desejado"],
                    reference=REF,
                )
            )
            if re1_calc > 0:
                r["RE1"] = commercial(
                    log, "RE1", "RE1 comercial", re1_q, s.res_series, "nearest"
                ).m_as("ohm")
                r["RE2"] = max(re_c - r["RE1"], 0.0)
                if r["RE2"] > 0:
                    r["RE2"] = commercial(
                        log,
                        "RE2",
                        "RE2 comercial (restante de RE)",
                        Q_(r["RE2"], "ohm"),
                        s.res_series,
                        "nearest",
                    ).m_as("ohm")
                del r["RE"]
            if s.Av > gm * rload:
                warnings.append(
                    DesignWarning(
                        code="ganho",
                        message=f"|Av| = {s.Av:g} passa do máximo com RE todo desviado "
                        f"({gm * rload:.3g}); o projeto usa RE todo desviado.",
                    )
                )
        re1 = r.get("RE1", 0.0 if s.config in ("EC", "FC") else re_c)
        re_dc = r.get("RE", 0.0) + r.get("RE1", 0.0) + r.get("RE2", 0.0)
        # divider
        if fet:
            vg = vgs + ic * re_dc
            r2 = commercial(
                log, "R2", "R2 da porta", Q_(1e6 * vg / vcc, "ohm"), s.res_series, "nearest"
            ).m_as("ohm")
            r1 = commercial(
                log, "R1", "R1 da porta", Q_(r2 * (vcc - vg) / vg, "ohm"), s.res_series, "nearest"
            ).m_as("ohm")
        else:
            beta_min = self._beta_min(rec, ic) or m_b.BF
            vb = ie * re_dc + m_b.vbe(ic)
            r2_calc = log.add(
                record(
                    "R2_calc",
                    "R2 do divisor (β·RE ≥ k·R2)",
                    r"R_2 \le \frac{\beta_{min} R_E}{k}",
                    output=Q_(beta_min * re_dc / s.divider_k, "ohm"),
                    inputs={r"\beta_{min}": Q_(beta_min, ""), "R_E": Q_(re_dc, "ohm")},
                    reference=REF,
                )
            )
            r2 = commercial(log, "R2", "R2 comercial", r2_calc, s.res_series, "down").m_as("ohm")
            ib = ic / m_b.BF
            r1 = commercial(
                log,
                "R1",
                "R1 comercial",
                Q_((vcc - vb) / (vb / r2 + ib), "ohm"),
                s.res_series,
                "nearest",
            ).m_as("ohm")
        r["R1"], r["R2"] = r1, r2
        vth, rth = thevenin(vcc, r1, r2)
        # ---------------------------------------------------------------- Q-point
        summary: dict[str, pint.Quantity] = {}
        if fet:
            qf = mos_q(m_f, vcc, vth, r.get("RC", 0.0), re_dc)
            icq, vceq = qf.ID, qf.VDS
            gm = math.sqrt(2 * m_f.KP * icq)
            log.add(
                record(
                    "gm",
                    "Transcondutância no ponto Q",
                    r"g_m = \sqrt{2 K_P I_D}",
                    output=Q_(gm, "S").to("mS"),
                    inputs={"K_P": Q_(m_f.KP, "A/V**2"), "I_D": Q_(icq, "A")},
                    reference=REF_FET,
                )
            )
            m_ss: Bjt | Mos = m_f
            rpi = math.inf
            cpi = cmu = 0.0
        else:
            q = bjt_q(m_b, vcc, vth, rth, r.get("RC", 0.0), re_dc)
            icq, vceq = q.IC, q.VCE
            m_c, w = with_capacitances(m_b, rec, icq, log, "Q1")
            warnings += [DesignWarning(code="modelo", message=x) for x in w]
            m_ss = m_c
            gm = icq / VT_300K
            rpi = m_b.BF / gm
            cmu = m_c.CJC
            cpi = m_c.TF * gm
            log.add(
                record(
                    "gm",
                    "Transcondutância no ponto Q",
                    r"g_m = \frac{I_C}{V_T}",
                    output=Q_(gm, "S").to("mS"),
                    inputs={"I_C": Q_(icq, "A").to("mA"), "V_T": Q_(VT_300K, "V")},
                    reference=SEDRA,
                )
            )
            log.add(
                record(
                    "r_pi",
                    "Resistência de entrada do modelo π",
                    r"r_\pi = \beta/g_m",
                    output=Q_(rpi, "ohm").to("kohm"),
                    inputs={r"\beta": Q_(m_b.BF, ""), "g_m": Q_(gm, "S").to("mS")},
                    reference=SEDRA,
                )
            )
            summary["r_pi"] = Q_(rpi, "ohm").to("kohm")
            summary["re"] = Q_(1 / gm, "ohm")
            summary["C_pi"] = Q_(cpi, "F").to("pF")
            summary["C_mu"] = Q_(cmu, "F").to("pF")
        if fet:
            vb_q, ve_q, vc_q = qf.VG, qf.VS, qf.VD
        else:
            vb_q, ve_q, vc_q = q.VB, q.VE, q.VC
        summary |= {"VB_q": Q_(vb_q, "V"), "VE_q": Q_(ve_q, "V"), "VC_q": Q_(vc_q, "V")}
        if vceq < 0.3:
            warnings.append(
                DesignWarning(code="saturado", message="O transistor está saturado no ponto Q.")
            )
        summary |= {
            "IC_q": Q_(icq, "A").to("mA"),
            "VCE_q": Q_(vceq, "V"),
            "gm": Q_(gm, "S").to("mS"),
        }
        # ---------------------------------------------------------------- mid-band
        rb = parallel(r1, r2)
        rc = r.get("RC", 0.0)
        beta = getattr(m_ss, "BF", math.inf)
        if s.config == "EC":
            zb = rpi + (beta + 1) * re1
            zin = parallel(rb, zb)
            av = -beta * parallel(rc, rl) / zb
            zout = rc
            lat = (
                r"A_v = -\frac{\beta (R_C \parallel R_L)}{r_\pi + (\beta + 1) R_{E1}},\;"
                r"Z_{in} = R_1 \parallel R_2 \parallel [r_\pi + (\beta+1)R_{E1}],\;"
                r"Z_{out} = R_C"
            )
        elif s.config == "CC":
            rel = parallel(re_c, rl)
            zb = rpi + (beta + 1) * rel
            zin = parallel(rb, zb)
            av = (beta + 1) * rel / zb
            zout = parallel(re_c, (rpi + parallel(rsig, rb)) / (beta + 1))
            lat = (
                r"A_v = \frac{(\beta+1)(R_E \parallel R_L)}{r_\pi + (\beta+1)(R_E \parallel R_L)},"
                r"\; Z_{out} = R_E \parallel \frac{r_\pi + R_s \parallel R_B}{\beta + 1}"
            )
        elif s.config == "BC":
            zin = parallel(re_c, rpi / (beta + 1))
            av = gm * parallel(rc, rl)
            zout = rc
            lat = (
                r"A_v = g_m (R_C \parallel R_L),\; Z_{in} = R_E \parallel \frac{r_\pi}{\beta+1},"
                r"\; Z_{out} = R_C"
            )
        else:
            zin = rb
            av = -gm * parallel(rc, rl) / (1 + gm * re1)
            zout = rc
            lat = (
                r"A_v = -\frac{g_m (R_D \parallel R_L)}{1 + g_m R_{S1}},\;"
                r"Z_{in} = R_1 \parallel R_2,\; Z_{out} = R_D"
            )
        avs = av * zin / (zin + rsig)
        log.add(
            record(
                "Av",
                "Ganho na banda média (base/porta → carga)",
                lat,
                output=Q_(av, ""),
                inputs={k: Q_(v, "ohm") for k, v in r.items()}
                | {"R_L": s.RL.to_pint(), "g_m": Q_(gm, "S").to("mS")},
                assumptions=["capacitores em curto na banda média; r_o desprezado"],
                reference=REF if not fet else REF_FET,
            )
        )
        log.add(
            record(
                "Avs",
                "Ganho a partir da fonte de sinal",
                r"A_{vs} = A_v \frac{Z_{in}}{Z_{in} + R_s}",
                output=Q_(avs, ""),
                inputs={"A_v": Q_(av, ""), "Z_{in}": Q_(zin, "ohm"), "R_s": s.Rs.to_pint()},
                reference=REF,
            )
        )
        # ---------------------------------------------------------------- capacitors
        w_l = 2 * math.pi * fl
        caps: dict[str, float] = {}
        # resistance seen by each capacitor (short-circuit time constants, Boylestad ch. 9)
        r_in_seen = rsig + zin
        r_out_seen = zout + rl
        if s.config == "BC":
            caps["CB"] = 1 / (w_l / 10 * (parallel(r1, r2) + rpi) / 1)
            r_in_seen = rsig + zin
        cin_req = 1 / (w_l / 10 * r_in_seen)
        cout_req = 1 / (w_l / 10 * r_out_seen)
        dom_ce = s.config in ("EC", "FC") and re_dc - re1 > 0
        if dom_ce:
            # resistance seen by CE: RE2 ∥ (RE1 + (r_π + R_s∥R_B)/(β+1))  (BJT) or 1/gm (FET)
            rth_b = parallel(rsig, rb)
            r_e = (rpi + rth_b) / (beta + 1) if not fet else 1 / gm
            r_ce = parallel(re_dc - re1, re1 + r_e)
            ce_req = 1 / (w_l * r_ce)
        else:
            # no bypass capacitor: the input coupling capacitor sets f_L
            cin_req = 1 / (w_l * r_in_seen)
            r_ce = 0.0
            ce_req = 0.0
        for name, cval in (
            ("Cin", cin_req),
            ("Cout", cout_req),
            ("CE", ce_req),
            ("CB", caps.get("CB", 0.0)),
        ):
            if cval <= 0:
                continue
            req = log.add(
                record(
                    f"{name}_calc",
                    f"{name}: polo em "
                    + (
                        "f_L"
                        if (name == "CE" and dom_ce) or (name == "Cin" and not dom_ce)
                        else "f_L/10"
                    ),
                    r"C = \frac{1}{2\pi f\,R_{vista}}",
                    output=Q_(cval, "F").to("uF"),
                    inputs={"f_L": s.f_L.to_pint()},
                    reference=REF_F,
                    assumptions=[
                        "constante de tempo de curto-circuito de cada capacitor",
                        "critério: um polo dominante em f_L, os outros uma década abaixo",
                    ],
                )
            )
            caps[name] = commercial(log, name, f"{name} comercial", req, s.cap_series, "up").m_as(
                "F"
            )
        # ---------------------------------------------------------------- exact response
        net = self._network(s, r, caps, gm, rpi, cpi, cmu, rl, rsig, fet)
        f = log_grid(F1, F2, PPD)
        h = net.solve(f, "sig", ["out"])["out"]
        mag = np.abs(h)
        f_l = corner(f, mag, "fl")
        f_h = corner(f, mag, "fh") if not fet and cpi + cmu > 0 else None
        fsig = s.f_sig.to_pint().m_as("Hz")
        h_sig = complex(net.solve(np.array([fsig]), "sig", ["out"])["out"][0])
        log.add(
            record(
                "Avs_f",
                "Ganho na frequência do sinal (circuito equivalente completo)",
                r"A_{vs}(f) = \frac{V_o}{V_s}\Big|_{f}",
                output=Q_(abs(h_sig), ""),
                inputs={"f": s.f_sig.to_pint()},
                assumptions=["análise nodal exata do modelo π-híbrido com os capacitores"],
                reference=REF_F,
            )
        )
        if f_l is not None:
            log.add(
                record(
                    "f_L",
                    "Frequência de corte inferior (−3 dB, solução exata)",
                    r"|A_{vs}(f_L)| = |A_{vs}|_{max}/\sqrt{2}",
                    output=Q_(f_l, "Hz"),
                    reference=REF_F,
                )
            )
            summary["f_L"] = Q_(f_l, "Hz")
        if f_h is not None:
            log.add(
                record(
                    "f_H",
                    "Frequência de corte superior (−3 dB, solução exata)",
                    r"|A_{vs}(f_H)| = |A_{vs}|_{max}/\sqrt{2}",
                    output=Q_(f_h, "Hz"),
                    inputs={r"C_\pi": Q_(cpi, "F").to("pF"), r"C_\mu": Q_(cmu, "F").to("pF")},
                    assumptions=["efeito Miller incluído na solução nodal"],
                    reference=REF_F,
                )
            )
            summary["f_H"] = Q_(f_h, "Hz").to("kHz")
        vs_pk = s.Vs_pk.to_pint().m_as("V")
        vo_pk = abs(h_sig) * vs_pk
        # symmetric swing: limited by saturation (VCE → 0,3 V) or cut-off (IC → 0) on the
        # AC load line (Boylestad, ch. 5)
        r_ac = parallel(re_c, rl) if s.config == "CC" else parallel(rc, rl)
        swing = min(vceq - 0.3, icq * r_ac)
        summary |= (
            {
                "Av": Q_(av, ""),
                "Avs": Q_(abs(h_sig), ""),
                "Av_dB": Q_(20 * math.log10(abs(h_sig)), ""),
                "Zin": Q_(zin, "ohm").to("kohm"),
                "Zout": Q_(zout, "ohm").to("kohm"),
                "Vo_pk": Q_(vo_pk, "V"),
                "Vo_max_sym": Q_(swing, "V"),
            }
            | {k: Q_(v, "ohm") for k, v in r.items()}
            | {k: Q_(v, "F").to("uF") for k, v in caps.items()}
        )
        if s.config in ("EC", "FC") and s.Av > 0 and abs(abs(av) / s.Av - 1) > 0.2:
            warnings.append(
                DesignWarning(
                    code="ganho",
                    message=f"|Av| obtido ({abs(av):.3g}) difere mais de 20 % do desejado "
                    f"({s.Av:g}): RE da polarização (kE) ou gm do dispositivo real limitam o "
                    "ajuste.",
                )
            )
        if vo_pk > swing:
            warnings.append(
                DesignWarning(
                    code="ceifamento",
                    message=f"A saída pedida ({vo_pk:.3g} V de pico) passa da excursão estimada "
                    f"({swing:.3g} V): haverá ceifamento.",
                )
            )
        # waveforms over one signal period: small-signal output (after Cout)
        th = np.linspace(0, 2 * math.pi, 720, endpoint=False)
        ph = cmath.phase(h_sig)
        traces = {
            "Sinal da fonte": make_trace("V", vs_pk * np.sin(th)),
            "Saída (sobre RL)": make_trace("V", vo_pk * np.sin(th + ph)),
        }
        p_q = vceq * icq
        stresses = [
            Stress(
                designator="Q1",
                key="VDS" if fet else "VCEO",
                label="Tensão no transistor",
                value=QuantityModel(value=vcc, unit="V"),
                calc_step_id="gm",
            ),
            Stress(
                designator="Q1",
                key="ID" if fet else "IC",
                label="Corrente no transistor",
                value=QuantityModel(value=icq, unit="A"),
                calc_step_id="gm",
            ),
        ]
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": Q_(p_q, "W")},
            warnings=warnings,
            convergence_keys=("IC_q", "Avs"),
            traces=traces,
            trace_period=Q_(1 / fsig, "s"),
            bode_f=Trace(unit="Hz", values=[float(x) for x in f]),
            bode={"Ganho Vo/Vs": Trace(unit="", values=[float(x) for x in mag])},
        )

    def _beta_min(self, rec: ComponentRecord | None, ic: float) -> float | None:
        if rec is None:
            return None
        known = [(i, p) for i, p in hfe_entries(rec) if i is not None]
        if not known:
            return None
        _, p = min(known, key=lambda e: abs(math.log((e[0] or 1.0) / ic)))
        return p.min

    def _network(
        self,
        s: SsaSpec,
        r: Mapping[str, float],
        caps: Mapping[str, float],
        gm: float,
        rpi: float,
        cpi: float,
        cmu: float,
        rl: float,
        rsig: float,
        fet: bool,
    ) -> Network:
        """Small-signal equivalent: supply and bypassed nodes at AC ground."""
        n = Network()
        rb = parallel(r["R1"], r["R2"])
        n.R("sig", "s1", rsig)
        cin = caps.get("Cin", 0.0)
        cout = caps.get("Cout", 0.0)
        if s.config == "BC":
            # input into the emitter, base bypassed by CB
            n.C("s1", "e", cin)
            n.R("e", "0", r["RE"])
            n.R("b", "0", rb)
            n.C("b", "0", caps.get("CB", 0.0))
        else:
            n.C("s1", "b", cin)
            n.R("b", "0", rb)
            re1 = r.get("RE1", 0.0)
            re2 = r.get("RE2", r.get("RE", 0.0) if s.config in ("EC", "FC") else 0.0)
            if s.config == "CC":
                n.R("e", "0", r["RE"])
            elif re1 > 0 and re2 <= 0:  # RE fully unbypassed: no CE
                n.R("e", "0", re1)
            elif re1 > 0:
                n.R("e", "e2", re1)
                n.R("e2", "0", re2)
                n.C("e2", "0", caps.get("CE", 0.0))
            else:
                n.R("e", "0", re2)
                n.C("e", "0", caps.get("CE", 0.0))
        if not fet:
            n.R("b", "e", rpi)
            n.C("b", "e", cpi)
            n.C("b", "c", cmu)
        n.gm("c", "e", gm, "b", "e")
        if s.config == "CC":
            n.R("c", "0", 1e-3)  # collector at AC ground
            n.C("e", "out", cout)
        else:
            n.R("c", "0", r["RC"])
            n.C("c", "out", cout)
        n.R("out", "0", rl)
        return n

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        log = CalcLog()
        rec = devices["Q1"].record
        vcc = s.VCC.to_pint().m_as("V")
        ic = s.IC.to_pint().m_as("A")
        fet = s.config == "FC"
        R = {
            k: summary[k].to_pint().m_as("ohm")
            for k in ("R1", "R2", "RC", "RE", "RE1", "RE2")
            if k in summary
        }
        C = {k: summary[k].to_pint().m_as("F") for k in ("Cin", "Cout", "CE", "CB") if k in summary}
        fsig = s.f_sig.to_pint().m_as("Hz")
        vs = s.Vs_pk.to_pint().m_as("V")
        lines = [
            f"VCC vcc 0 DC {vcc:.9g}",
            f"VS sig 0 DC 0 AC 1 SIN(0 {vs:.9g} {fsig:.9g})",
            f"RSIG sig s1 {s.Rs.to_pint().m_as('ohm'):.9g}",
        ]
        if fet:
            m_f, _ = mos_model(rec, log, "Q1")
            lines.append(m_f.spice("MQ"))
            dev = "M1 cq b e e MQ"
        else:
            m_b, _ = bjt_model(rec, ic, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
            icq = summary["IC_q"].to_pint().m_as("A")
            m_c, _ = with_capacitances(m_b, rec, icq, log, "Q1")
            lines.append(m_c.spice("QB"))
            dev = "Q1 cq b e QB"
        vb = summary["VB_q"].to_pint().m_as("V")
        ve = summary["VE_q"].to_pint().m_as("V")
        vc = summary["VC_q"].to_pint().m_as("V")
        # capacitors start charged to the analytic Q-point (uic): the run starts settled
        lines += [f"R1 vcc b {R['R1']:.9g}", f"R2 b 0 {R['R2']:.9g}", dev]
        if s.config == "BC":
            lines += [f"CIN s1 e {C['Cin']:.9g} IC={-ve:.6g}", f"CB b 0 {C['CB']:.9g} IC={vb:.6g}"]
        else:
            lines.append(f"CIN s1 b {C['Cin']:.9g} IC={-vb:.6g}")
        if s.config == "CC":
            lines += [
                "VSC vcc cq 0",
                f"RE e 0 {R['RE']:.9g}",
                f"COUT e out {C['Cout']:.9g} IC={ve:.6g}",
            ]
        else:
            lines += [
                f"RC vcc c {R['RC']:.9g}",
                "VSC c cq 0",
                f"COUT c out {C['Cout']:.9g} IC={vc:.6g}",
            ]
            if "RE1" in R:
                lines.append(f"RE1 e e2 {R['RE1']:.9g}")
                if "RE2" in R:
                    re2v = ve * R["RE2"] / (R["RE1"] + R["RE2"])
                    lines.append(f"RE2 e2 0 {R['RE2']:.9g}")
                    if "CE" in C:
                        lines.append(f"CE e2 0 {C['CE']:.9g} IC={re2v:.6g}")
                else:
                    lines.append("VRE2 e2 0 0")
            else:
                lines.append(f"RE e 0 {R['RE']:.9g}")
                if "CE" in C:
                    lines.append(f"CE e 0 {C['CE']:.9g} IC={ve:.6g}")
        lines.append(f"RL out 0 {s.RL.to_pint().m_as('ohm'):.9g}")
        checks = [
            SimCheck(
                quantity="Corrente de polarização",
                summary_key="IC_q",
                metric="avg",
                probe="i(vsc)",
                tolerance_pct=1.0,
                justification="mesmo modelo; o sinal pequeno desloca pouco a média",
            ),
            SimCheck(
                quantity="Ganho na frequência do sinal",
                summary_key="Avs",
                metric="ac_mag",
                probe="v(out)",
                freq=fsig,
                tolerance_pct=1.0,
                justification="mesmo modelo linearizado no ponto Q (.ac)",
            ),
        ]
        if "f_L" in summary:
            checks.append(
                SimCheck(
                    quantity="Frequência de corte inferior",
                    summary_key="f_L",
                    metric="ac_fl",
                    probe="v(out)",
                    tolerance_pct=2.0,
                    justification="interpolação na grade de 20 pontos/década",
                )
            )
        if "f_H" in summary:
            checks.append(
                SimCheck(
                    quantity="Frequência de corte superior",
                    summary_key="f_H",
                    metric="ac_fh",
                    probe="v(out)",
                    tolerance_pct=2.0,
                    justification="interpolação na grade de 20 pontos/década",
                )
            )
        settle = 10 / fsig
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[s.config]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=settle + 2 / fsig, unit="s"),
            tran_step=QuantityModel(value=1 / fsig / 400, unit="s"),
            period=QuantityModel(value=1 / fsig, unit="s"),
            probes={"Sinal da fonte": "v(sig)", "Saída (sobre RL)": "v(out)"},
            checks=checks,
            ac_start=QuantityModel(value=F1, unit="Hz"),
            ac_stop=QuantityModel(value=F2, unit="Hz"),
            ac_points_per_decade=PPD,
            bode_probes={"Ganho Vo/Vs": "v(out)"},
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        part = next((c.part_number for c in result.selection), "")

        def v(k: str) -> str:
            return format_eng(sm[k].to_pint()) if k in sm else ""

        svg = Svg(620, 340)
        svg.title(title)
        top, bot, x = 50, 300, 330
        svg.wire((150, top), (560, top))
        svg.terminal(560, top, f"VCC = {s.VCC.value:g} V")
        svg.ac_source(40, 150, bot, "vs", f"Rs = {format_eng(s.Rs.to_pint())}")
        svg.wire((40, 150), (40, 130), (70, 130))
        fet = s.config == "FC"
        if s.config == "BC":
            b, c, e = svg.bjt(x, 150, "Q1", part)
            svg.cap_h(70, 160, 130, "Cin", v("Cin"))
            svg.wire((160, 130), (230, 130), (230, 220), (e[0], 220))
            svg.wire(e, (e[0], 220))
            svg.resistor_v(e[0], 220, bot, "RE", v("RE"))
            svg.resistor_v(170, top, 175, "R1", v("R1"))
            svg.resistor_v(170, 175, bot, "R2", v("R2"))
            svg.wire((170, 150), b)
            svg.cap_v(120, 150, bot, "CB", v("CB"))
            svg.wire((120, 150), (170, 150))
        else:
            b, c, e = svg.nmos(x, 150, "Q1", part) if fet else svg.bjt(x, 150, "Q1", part)
            svg.cap_h(70, 170, 130, "Cin", v("Cin"))
            svg.wire((170, 130), (230, 130), (230, 150), b)
            svg.resistor_v(230, top, 130, "R1", v("R1"))
            svg.resistor_v(230, 150, bot, "R2", v("R2"))
            if "RE1" in sm:
                svg.resistor_v(e[0], e[1], 230, "RE1", v("RE1"))
                if "RE2" in sm:
                    svg.resistor_v(e[0], 230, bot, "RE2", v("RE2"))
                    svg.cap_v(e[0] + 70, 230, bot, "CE", v("CE"))
                    svg.wire((e[0], 230), (e[0] + 70, 230))
            else:
                svg.resistor_v(e[0], e[1], bot, "RE", v("RE"))
                if "CE" in sm:
                    svg.cap_v(e[0] + 70, e[1] + 10, bot, "CE", v("CE"))
                    svg.wire((e[0], e[1] + 10), (e[0] + 70, e[1] + 10))
        if s.config == "CC":
            svg.wire(c, (c[0], top))
            svg.cap_h(e[0], e[0] + 110, 230, "Cout", v("Cout"))
            out_x = e[0] + 110
            svg.resistor_v(out_x, 230, bot, "RL", format_eng(s.RL.to_pint()))
        else:
            svg.resistor_v(c[0], top, 100, "RC", v("RC"))
            svg.wire((c[0], 100), c)
            svg.cap_h(c[0], c[0] + 130, 100, "Cout", v("Cout"))
            out_x = c[0] + 130
            svg.resistor_v(out_x, 100, bot, "RL", format_eng(s.RL.to_pint()))
        svg.terminal(out_x + 30, 100 if s.config != "CC" else 230, "vo")
        svg.wire((40, bot), (out_x, bot))
        svg.ground(330, bot)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        rows = [resistor_row(result, k, k) for k in ("R1", "R2", "RC", "RE", "RE1", "RE2")]
        rows += [
            capacitor_row(result, k, k, desc, "tensão ≥ VCC")
            for k, desc in (
                ("Cin", "Capacitor de acoplamento"),
                ("Cout", "Capacitor de acoplamento"),
                ("CE", "Capacitor de desvio"),
                ("CB", "Capacitor de desvio"),
            )
        ]
        return [r for r in rows if r]
