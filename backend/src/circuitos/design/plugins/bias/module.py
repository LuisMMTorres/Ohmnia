"""DM-BIAS: DC bias of a BJT (fixed, emitter, divider, collector feedback) or an N-MOSFET.

Design rules (Boylestad & Nashelsky, *Electronic Devices and Circuit Theory*, 11th ed.,
ch. 4 "DC biasing — BJTs", design operations; ch. 7 "FET biasing"):

* VE = kE·VCC (default 10 %), so RE fixes IE against changes of β and VBE;
* divider: R2 ≤ β_min·RE/10 (approximate analysis valid; the divider current dominates);
* RC from the desired VCE; every resistor rounded to the E-series;
* the Q-point is then recomputed with the commercial values and the exponential junction
  (``design.qpoint``), the same equations as the simulator.

β sensitivity: the collector current is also given at the hFE limits of the datasheet.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

import pint
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.analog import commercial, dc_check, dc_circuit
from circuitos.design.base import Circuit, DesignResult, DesignWarning, Role, Stress
from circuitos.design.devmodels import (
    BOYLESTAD,
    Bjt,
    bjt_model,
    hfe_entries,
    jfet_model,
    mos_model,
    quantity,
)
from circuitos.design.engine import Analysis, Device
from circuitos.design.fet import power_stress, vgs_for
from circuitos.design.qpoint import bjt_q, jfet_q, mos_q, thevenin
from circuitos.reports.common import BomRow, LabItem, resistor_row
from circuitos.reports.schematic import Svg

Config = Literal[
    "fixa", "emissor", "divisor", "coletor", "mos_divisor", "jfet_auto", "jfet_divisor"
]
REF_BJT = BOYLESTAD.model_copy(update={"chapter": "4 (DC biasing — BJTs)"})
REF_FET = BOYLESTAD.model_copy(update={"chapter": "7 (FET biasing)"})


class BiasSpec(BaseModel):
    config: Config = "divisor"
    VCC: QuantityModel = QuantityModel(value=12, unit="V")
    IC: QuantityModel = QuantityModel(value=2, unit="mA")  # IC (or ID) desired
    VCE: QuantityModel = QuantityModel(value=6, unit="V")  # VCE (or VDS) desired
    kE: float = Field(default=0.1, ge=0, le=0.4)  # VE (or VS) as a fraction of VCC
    divider_k: float = Field(default=10, ge=2, le=100)  # β_min·RE ≥ k·R2
    R_gate: QuantityModel = QuantityModel(value=1, unit="Mohm")  # R1 + R2 of a MOSFET divider
    VBE: QuantityModel = QuantityModel(value=0.7, unit="V")
    beta_ideal: float = Field(default=100, gt=1, le=2000)
    res_series: Literal["E12", "E24"] = "E24"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")


LABELS = {
    "IC_q": "Corrente de coletor no ponto Q",
    "IB_q": "Corrente de base no ponto Q",
    "VCE_q": "VCE no ponto Q",
    "VBE_q": "VBE no ponto Q",
    "VB_q": "Tensão de base",
    "VE_q": "Tensão de emissor",
    "VC_q": "Tensão de coletor",
    "ID_q": "Corrente de dreno no ponto Q",
    "VGS_q": "VGS no ponto Q",
    "VDS_q": "VDS no ponto Q",
    "VG_q": "Tensão de porta",
    "VS_q": "Tensão de fonte",
    "VD_q": "Tensão de dreno",
    "RC": "Resistor de coletor RC",
    "RE": "Resistor de emissor RE",
    "RB": "Resistor de base RB",
    "R1": "Resistor do divisor R1",
    "R2": "Resistor do divisor R2",
    "RD": "Resistor de dreno RD",
    "RS": "Resistor de fonte RS",
    "IC_beta_min": "IC com hFE mínimo do datasheet",
    "IC_beta_max": "IC com hFE máximo do datasheet",
    "P_Q": "Potência no transistor",
    "IC_sat": "Corrente de saturação (reta de carga)",
    "VCE_cut": "VCE de corte (reta de carga)",
}
SPEC_LABELS = {
    "config": "Configuração",
    "VCC": "Alimentação",
    "IC": "Corrente de coletor/dreno desejada",
    "VCE": "VCE/VDS desejada",
    "kE": "VE/VS como fração de VCC",
    "divider_k": "Critério do divisor (β·RE ≥ k·R2)",
    "R_gate": "Resistência da porta (R1 + R2 do divisor, ou RG)",
    "VBE": "VBE na corrente de ensaio (premissa)",
    "beta_ideal": "β de projeto (passo ideal)",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {
    "fixa": "TBJ, polarização fixa",
    "emissor": "TBJ, polarização do emissor",
    "divisor": "TBJ, divisor de tensão",
    "coletor": "TBJ, realimentação do coletor",
    "mos_divisor": "MOSFET de enriquecimento, divisor de tensão",
    "jfet_auto": "JFET canal N, autopolarização (RS)",
    "jfet_divisor": "JFET canal N, divisor de tensão",
}


def _spec(spec: BaseModel) -> BiasSpec:
    if not isinstance(spec, BiasSpec):
        raise TypeError("DM-BIAS espera BiasSpec")
    return spec


class BiasModule:
    id = "DM-BIAS"
    family = "amplificadores"
    title = "Polarização de transistores"
    spec_schema = BiasSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Corrente de coletor/dreno", "multímetro em série", "IC_q"),
        LabItem("VCE / VDS", "multímetro CC", "VCE_q"),
        LabItem("Tensão de base/porta", "multímetro CC (alta impedância)", "VB_q"),
        LabItem("Tensão de emissor/fonte", "multímetro CC", "VE_q"),
    ]
    questions = [
        "Troque o transistor por outro do mesmo código e meça IC de novo: quanto mudou? "
        "Compare com a faixa calculada entre hFE mínimo e máximo.",
        "Por que RE estabiliza o ponto de operação? O que se perde em ganho com ele?",
        "Desenhe a reta de carga CC e marque o ponto Q medido.",
    ]
    practice = {
        "objective": "Montar a polarização, medir o ponto de operação e comparar com o cálculo "
        "e a simulação, avaliando a sensibilidade a β.",
        "material": "Fonte CC, dois multímetros, protoboard e os componentes da lista.",
        "procedure": [
            "Monte o circuito com a fonte desligada e confira a pinagem do transistor.",
            "Energize e meça as tensões de base/porta, emissor/fonte e coletor/dreno.",
            "Meça a corrente de coletor/dreno com o multímetro em série.",
            "Calcule VCE e compare o ponto Q com o calculado.",
            "Aqueça o transistor com os dedos (ou soprador) e observe a deriva de IC.",
        ],
    }

    def _mos(self, s: BiasSpec) -> bool:
        return s.config == "mos_divisor"

    def _jfet(self, s: BiasSpec) -> bool:
        return s.config.startswith("jfet")

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        if self._mos(s):
            return [Role(designator="Q1", category="mosfet.n", description="MOSFET canal N")]
        if self._jfet(s):
            return [Role(designator="Q1", category="jfet.n", description="JFET canal N")]
        return [Role(designator="Q1", category="bjt.npn", description="Transistor NPN")]

    def required_ratings(self, role: Role) -> list[str]:
        if role.category.startswith("jfet"):
            return ["VDS", "Ptot"]
        return ["VDS"] if role.category.startswith("mosfet") else ["VCEO", "IC"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        if role.category.startswith("jfet"):
            idss = quantity(rec, "IDSS", ("typ", "max"))
            need = _spec(spec).IC.to_pint().m_as("A")
            return idss is not None and float(idss.m_as("A")) > need and "yfs" in rec.parameters
        if role.category.startswith("mosfet"):
            vth = rec.parameters.get("VGS(th)")
            rds = rec.parameters.get("RDS(on)")
            return bool(vth and vth.min is not None and rds and rds.max is not None)
        return bool(hfe_entries(rec))

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        """Small-signal parts first: the lowest current rating that passes the margins."""
        q = quantity(rec, "IC", ("max",)) or quantity(rec, "ID", ("max",))
        return float(q.m_as("A")) if q is not None else 0.0

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        if self._mos(s):
            return self._analyse_mos(s, devices)
        if self._jfet(s):
            return self._analyse_jfet(s, devices)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vcc = s.VCC.to_pint().m_as("V")
        ic = s.IC.to_pint().m_as("A")
        vce = s.VCE.to_pint().m_as("V")
        if not 0 < vce < vcc or ic <= 0:
            raise ValueError("Use 0 < VCE < VCC e IC > 0")
        rec = devices["Q1"].record
        m, w = bjt_model(rec, ic, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
        warnings += [DesignWarning(code="modelo", message=x) for x in w]
        beta = m.BF
        ib = ic / beta
        ie = ic + ib
        vbe = m.vbe(ic)
        log.add(
            record(
                "VBE_design",
                "VBE na corrente desejada (modelo exponencial)",
                r"V_{BE} = V_T \ln\!\left(\frac{I_C}{I_S} + 1\right)",
                output=Q_(vbe, "V"),
                inputs={"I_C": s.IC.to_pint(), "I_S": Q_(m.IS, "A")},
                reference=REF_BJT,
            )
        )
        cfg = s.config
        use_re = cfg in ("emissor", "divisor") or (cfg == "coletor" and s.kE > 0)
        ve = s.kE * vcc if use_re else 0.0
        r: dict[str, float] = {}
        if use_re and ve > 0:
            re_calc = log.add(
                record(
                    "RE_calc",
                    "Resistor de emissor pelo critério VE = kE·VCC",
                    r"R_E = \frac{k_E V_{CC}}{I_E},\quad I_E = I_C\,\frac{\beta + 1}{\beta}",
                    output=Q_(ve / ie, "ohm"),
                    inputs={"k_E": Q_(s.kE, ""), "V_{CC}": s.VCC.to_pint(), "I_E": Q_(ie, "A")},
                    assumptions=["critério de projeto: VE ≈ 10 % de VCC estabiliza IE"],
                    reference=REF_BJT,
                )
            )
            r["RE"] = commercial(log, "RE", "RE comercial", re_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
        re = r.get("RE", 0.0)
        ve_c = ie * re
        rc_den = ie if cfg == "coletor" else ic
        rc_calc = log.add(
            record(
                "RC_calc",
                "Resistor de coletor pela VCE desejada",
                r"R_C = \frac{V_{CC} - V_{CE} - V_E}{I_C}"
                if cfg != "coletor"
                else r"R_C = \frac{V_{CC} - V_{CE} - V_E}{I_C + I_B}",
                output=Q_((vcc - vce - ve_c) / rc_den, "ohm"),
                inputs={
                    "V_{CC}": s.VCC.to_pint(),
                    "V_{CE}": s.VCE.to_pint(),
                    "V_E": Q_(ve_c, "V"),
                    "I_C": s.IC.to_pint(),
                },
                reference=REF_BJT,
            )
        )
        if rc_calc.magnitude <= 0:
            raise ValueError("VCE + VE não cabe em VCC: reduza VCE ou kE")
        r["RC"] = commercial(log, "RC", "RC comercial", rc_calc, s.res_series, "nearest").m_as(
            "ohm"
        )
        rc = r["RC"]
        if cfg in ("fixa", "emissor"):
            rb_calc = log.add(
                record(
                    "RB_calc",
                    "Resistor de base para a corrente de base desejada",
                    r"R_B = \frac{V_{CC} - V_{BE} - V_E}{I_B}",
                    output=Q_((vcc - vbe - ve_c) / ib, "ohm"),
                    inputs={
                        "V_{CC}": s.VCC.to_pint(),
                        "V_{BE}": Q_(vbe, "V"),
                        "V_E": Q_(ve_c, "V"),
                        "I_B": Q_(ib, "A").to("uA"),
                    },
                    reference=REF_BJT,
                )
            )
            r["RB"] = commercial(log, "RB", "RB comercial", rb_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
            vth, rth = vcc, r["RB"]
        elif cfg == "coletor":
            vc_target = vcc - (ic + ib) * rc
            rb_calc = log.add(
                record(
                    "RB_calc",
                    "Resistor de realimentação coletor-base",
                    r"R_B = \frac{V_C - V_{BE} - V_E}{I_B}",
                    output=Q_((vc_target - vbe - ve_c) / ib, "ohm"),
                    inputs={
                        "V_C": Q_(vc_target, "V"),
                        "V_{BE}": Q_(vbe, "V"),
                        "V_E": Q_(ve_c, "V"),
                        "I_B": Q_(ib, "A").to("uA"),
                    },
                    reference=REF_BJT,
                )
            )
            r["RB"] = commercial(log, "RB", "RB comercial", rb_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
            vth, rth = 0.0, r["RB"]
        else:
            beta_min = self._beta_limits(rec, ic)[0] or beta
            vb = ve_c + vbe
            r2_calc = log.add(
                record(
                    "R2_calc",
                    "R2 do divisor: corrente do divisor bem maior que IB",
                    r"R_2 \le \frac{\beta_{min} R_E}{k}",
                    output=Q_(beta_min * re / s.divider_k, "ohm"),
                    inputs={
                        r"\beta_{min}": Q_(beta_min, ""),
                        "R_E": Q_(re, "ohm"),
                        "k": Q_(s.divider_k, ""),
                    },
                    assumptions=["critério da análise aproximada (βRE ≥ 10R2)"],
                    reference=REF_BJT,
                )
            )
            r["R2"] = commercial(log, "R2", "R2 comercial", r2_calc, s.res_series, "down").m_as(
                "ohm"
            )
            r2 = r["R2"]
            # exact R1 for VB given the base current through the Thevenin resistance
            r1_calc = log.add(
                record(
                    "R1_calc",
                    "R1 do divisor para a tensão de base",
                    r"R_1 = \frac{V_{CC} - V_B}{V_B/R_2 + I_B}",
                    output=Q_((vcc - vb) / (vb / r2 + ib), "ohm"),
                    inputs={
                        "V_{CC}": s.VCC.to_pint(),
                        "V_B": Q_(vb, "V"),
                        "R_2": Q_(r2, "ohm"),
                        "I_B": Q_(ib, "A").to("uA"),
                    },
                    reference=REF_BJT,
                )
            )
            r["R1"] = commercial(log, "R1", "R1 comercial", r1_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
            vth, rth = thevenin(vcc, r["R1"], r2)
        qp = bjt_q(m, vcc, vth, rth, rc, re, collector_feedback=cfg == "coletor")
        net = {
            "fixa": r"V_{CC} = I_B R_B + V_{BE}",
            "emissor": r"V_{CC} = I_B R_B + V_{BE} + I_E R_E",
            "divisor": r"V_{Th} = I_B R_{Th} + V_{BE} + I_E R_E,\; "
            r"V_{Th} = V_{CC}\frac{R_2}{R_1 + R_2},\; R_{Th} = R_1 \parallel R_2",
            "coletor": r"V_{CC} = (I_C + I_B) R_C + I_B R_B + V_{BE} + I_E R_E",
        }[cfg]
        log.add(
            record(
                "IC_q",
                "Corrente de coletor com os resistores comerciais (solução exata)",
                net + r";\quad I_C = I_S(e^{V_{BE}/V_T} - 1),\; I_B = I_C/\beta_F",
                output=Q_(qp.IC, "A").to("mA"),
                inputs={k: Q_(v, "ohm") for k, v in r.items()} | {r"\beta_F": Q_(beta, "")},
                assumptions=["região ativa direta", "mesmas equações do simulador"],
                reference=REF_BJT,
            )
        )
        log.add(
            record(
                "VCE_q",
                "VCE no ponto de operação",
                r"V_{CE} = V_C - V_E",
                output=Q_(qp.VCE, "V"),
                inputs={"V_C": Q_(qp.VC, "V"), "V_E": Q_(qp.VE, "V")},
                reference=REF_BJT,
            )
        )
        if qp.VCE < 0.3:
            warnings.append(
                DesignWarning(
                    code="saturado",
                    message=f"VCE = {qp.VCE:.2g} V: o transistor está saturado; o modelo da "
                    "região ativa não vale. Revise RC ou IC.",
                )
            )
        summary: dict[str, pint.Quantity] = {
            "IC_q": Q_(qp.IC, "A").to("mA"),
            "IB_q": Q_(qp.IB, "A").to("uA"),
            "VCE_q": Q_(qp.VCE, "V"),
            "VBE_q": Q_(qp.VBE, "V"),
            "VB_q": Q_(qp.VB, "V"),
            "VE_q": Q_(qp.VE, "V"),
            "VC_q": Q_(qp.VC, "V"),
        } | {k: Q_(v, "ohm") for k, v in r.items()}
        # load line (Boylestad, ch. 4): IC,sat with VCE = 0, VCE,cut with IC = 0
        summary["IC_sat"] = Q_(vcc / (rc + re), "A").to("mA")
        summary["VCE_cut"] = Q_(vcc, "V")
        lo, hi = self._beta_limits(rec, ic)
        for tag, b in (("min", lo), ("max", hi)):
            if b is None:
                continue
            qb = bjt_q(Bjt(m.IS, b), vcc, vth, rth, rc, re, collector_feedback=cfg == "coletor")
            summary[f"IC_beta_{tag}"] = Q_(qb.IC, "A").to("mA")
            log.add(
                record(
                    f"IC_beta_{tag}",
                    f"IC com hFE {'mínimo' if tag == 'min' else 'máximo'} do datasheet",
                    r"I_C(\beta = h_{FE," + tag + "})",
                    output=Q_(qb.IC, "A").to("mA"),
                    inputs={r"\beta": Q_(b, "")},
                    assumptions=["mesmo I_S; mostra a sensibilidade do ponto Q a β"],
                    reference=REF_BJT,
                )
            )
        p_q = qp.VCE * qp.IC + qp.VBE * qp.IB
        summary["P_Q"] = Q_(p_q, "W").to("mW")
        stresses = [
            Stress(
                designator="Q1",
                key="VCEO",
                label="Tensão coletor-emissor (corte)",
                value=QuantityModel(value=vcc, unit="V"),
                calc_step_id="VCE_q",
            ),
            Stress(
                designator="Q1",
                key="IC",
                label="Corrente de coletor",
                value=QuantityModel(value=qp.IC, unit="A"),
                calc_step_id="IC_q",
            ),
        ]
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": Q_(p_q, "W")},
            warnings=warnings,
            convergence_keys=("IC_q", "VCE_q"),
        )

    def _beta_limits(
        self, rec: ComponentRecord | None, ic: float
    ) -> tuple[float | None, float | None]:
        if rec is None:
            return None, None
        known = [(i, p) for i, p in hfe_entries(rec) if i is not None]
        if not known:
            return None, None
        _, p = min(known, key=lambda e: abs(math.log((e[0] or 1.0) / ic)))
        return p.min, p.max

    def _analyse_mos(self, s: BiasSpec, devices: Mapping[str, Device]) -> Analysis:
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vdd = s.VCC.to_pint().m_as("V")
        idq = s.IC.to_pint().m_as("A")
        vds = s.VCE.to_pint().m_as("V")
        m, w = mos_model(devices["Q1"].record, log, "Q1")
        warnings += [DesignWarning(code="modelo", message=x) for x in w]
        vgs = m.VT + math.sqrt(2 * idq / m.KP)
        log.add(
            record(
                "VGS_design",
                "VGS para a corrente de dreno desejada (saturação)",
                r"V_{GS} = V_T + \sqrt{\frac{2 I_D}{K_P}}",
                output=Q_(vgs, "V"),
                inputs={"V_T": Q_(m.VT, "V"), "I_D": s.IC.to_pint(), "K_P": Q_(m.KP, "A/V**2")},
                reference=REF_FET,
            )
        )
        vs = s.kE * vdd
        r: dict[str, float] = {}
        rs_calc = log.add(
            record(
                "RS_calc",
                "Resistor de fonte pelo critério VS = kE·VDD",
                r"R_S = \frac{k_E V_{DD}}{I_D}",
                output=Q_(vs / idq, "ohm"),
                inputs={"k_E": Q_(s.kE, ""), "V_{DD}": s.VCC.to_pint(), "I_D": s.IC.to_pint()},
                reference=REF_FET,
            )
        )
        if vs > 0:
            r["RS"] = commercial(log, "RS", "RS comercial", rs_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
        rs = r.get("RS", 0.0)
        rd_calc = log.add(
            record(
                "RD_calc",
                "Resistor de dreno pela VDS desejada",
                r"R_D = \frac{V_{DD} - V_{DS} - V_S}{I_D}",
                output=Q_((vdd - vds - idq * rs) / idq, "ohm"),
                inputs={
                    "V_{DD}": s.VCC.to_pint(),
                    "V_{DS}": s.VCE.to_pint(),
                    "V_S": Q_(idq * rs, "V"),
                    "I_D": s.IC.to_pint(),
                },
                reference=REF_FET,
            )
        )
        if rd_calc.magnitude <= 0:
            raise ValueError("VDS + VS não cabe em VDD")
        r["RD"] = commercial(log, "RD", "RD comercial", rd_calc, s.res_series, "nearest").m_as(
            "ohm"
        )
        vg = vgs + idq * rs
        rg = s.R_gate.to_pint().m_as("ohm")
        r2_calc = log.add(
            record(
                "R2_calc",
                "R2 do divisor da porta (corrente de porta nula)",
                r"R_2 = (R_1 + R_2)\,\frac{V_G}{V_{DD}}",
                output=Q_(rg * vg / vdd, "ohm"),
                inputs={"R_1 + R_2": Q_(rg, "ohm"), "V_G": Q_(vg, "V"), "V_{DD}": s.VCC.to_pint()},
                reference=REF_FET,
            )
        )
        r["R2"] = commercial(log, "R2", "R2 comercial", r2_calc, s.res_series, "nearest").m_as(
            "ohm"
        )
        r1_calc = log.add(
            record(
                "R1_calc",
                "R1 do divisor da porta",
                r"R_1 = R_2\,\frac{V_{DD} - V_G}{V_G}",
                output=Q_(r["R2"] * (vdd - vg) / vg, "ohm"),
                inputs={"R_2": Q_(r["R2"], "ohm"), "V_G": Q_(vg, "V")},
                reference=REF_FET,
            )
        )
        r["R1"] = commercial(log, "R1", "R1 comercial", r1_calc, s.res_series, "nearest").m_as(
            "ohm"
        )
        vg_c = vdd * r["R2"] / (r["R1"] + r["R2"])
        qp = mos_q(m, vdd, vg_c, r["RD"], rs)
        log.add(
            record(
                "ID_q",
                "Corrente de dreno com os resistores comerciais",
                r"V_G = V_{GS} + I_D R_S,\quad I_D = \frac{K_P}{2}(V_{GS} - V_T)^2",
                output=Q_(qp.ID, "A").to("mA"),
                inputs={"V_G": Q_(vg_c, "V"), "R_S": Q_(rs, "ohm")},
                assumptions=["saturação; λ = 0", "mesmas equações do simulador"],
                reference=REF_FET,
            )
        )
        if qp.VDS < qp.VGS - m.VT:
            warnings.append(
                DesignWarning(
                    code="triodo",
                    message="O MOSFET saiu da saturação (VDS < VGS − VT); revise RD.",
                )
            )
        summary: dict[str, pint.Quantity] = {
            "ID_q": Q_(qp.ID, "A").to("mA"),
            "VGS_q": Q_(qp.VGS, "V"),
            "VDS_q": Q_(qp.VDS, "V"),
            "VG_q": Q_(qp.VG, "V"),
            "VS_q": Q_(qp.VS, "V"),
            "VD_q": Q_(qp.VD, "V"),
            "IC_q": Q_(qp.ID, "A").to("mA"),
            "VCE_q": Q_(qp.VDS, "V"),
            "VB_q": Q_(qp.VG, "V"),
            "VE_q": Q_(qp.VS, "V"),
        } | {k: Q_(v, "ohm") for k, v in r.items()}
        p_q = qp.VDS * qp.ID
        summary["P_Q"] = Q_(p_q, "W").to("mW")
        stresses = [
            Stress(
                designator="Q1",
                key="VDS",
                label="Tensão dreno-fonte (corte)",
                value=QuantityModel(value=vdd, unit="V"),
                calc_step_id="ID_q",
            ),
            Stress(
                designator="Q1",
                key="ID",
                label="Corrente de dreno",
                value=QuantityModel(value=qp.ID, unit="A"),
                calc_step_id="ID_q",
            ),
        ]
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": Q_(p_q, "W")},
            warnings=warnings,
            convergence_keys=("ID_q", "VDS_q"),
        )

    def _analyse_jfet(self, s: BiasSpec, devices: Mapping[str, Device]) -> Analysis:
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vdd = s.VCC.to_pint().m_as("V")
        idq = s.IC.to_pint().m_as("A")
        vds = s.VCE.to_pint().m_as("V")
        rec = devices["Q1"].record
        m, w = jfet_model(rec, log, "Q1")
        warnings += [DesignWarning(code="modelo", message=x) for x in w]
        vgs = vgs_for(m, idq, log)
        idss_min = quantity(rec, "IDSS", ("min",)) if rec is not None else None
        if idss_min is not None and float(idss_min.m_as("A")) <= idq:
            warnings.append(
                DesignWarning(
                    code="dispersao",
                    message=f"A corrente pedida passa do IDSS mínimo do datasheet "
                    f"({float(idss_min.m_as('mA')):.3g} mA): com uma peça do limite inferior o "
                    "ponto Q não é alcançado. Meça o IDSS da peça antes de montar.",
                )
            )
        r: dict[str, float] = {}
        if s.config == "jfet_auto":
            rs_calc = log.add(
                record(
                    "RS_calc",
                    "Resistor de fonte da autopolarização",
                    r"R_S = -\frac{V_{GS}}{I_D}",
                    output=Q_(-vgs / idq, "ohm"),
                    inputs={"V_{GS}": Q_(vgs, "V"), "I_D": s.IC.to_pint()},
                    reference=REF_FET,
                )
            )
            r["RS"] = commercial(log, "RS", "RS comercial", rs_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
            r["RG"] = s.R_gate.to_pint().m_as("ohm")
            vg = 0.0
        else:
            vs = s.kE * vdd
            rs_calc = log.add(
                record(
                    "RS_calc",
                    "Resistor de fonte pelo critério VS = kE·VDD",
                    r"R_S = \frac{k_E V_{DD}}{I_D}",
                    output=Q_(vs / idq, "ohm"),
                    inputs={"k_E": Q_(s.kE, ""), "V_{DD}": s.VCC.to_pint(), "I_D": s.IC.to_pint()},
                    reference=REF_FET,
                )
            )
            r["RS"] = commercial(log, "RS", "RS comercial", rs_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
            vg_t = vgs + idq * r["RS"]
            if vg_t <= 0:
                raise ValueError("Com este kE a porta ficaria negativa: aumente kE")
            rg = s.R_gate.to_pint().m_as("ohm")
            r2_calc = log.add(
                record(
                    "R2_calc",
                    "R2 do divisor da porta (corrente de porta nula)",
                    r"R_2 = (R_1 + R_2)\,\frac{V_G}{V_{DD}},\; V_G = V_{GS} + I_D R_S",
                    output=Q_(rg * vg_t / vdd, "ohm"),
                    inputs={"R_1 + R_2": Q_(rg, "ohm"), "V_G": Q_(vg_t, "V")},
                    reference=REF_FET,
                )
            )
            r["R2"] = commercial(log, "R2", "R2 comercial", r2_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
            r1_calc = log.add(
                record(
                    "R1_calc",
                    "R1 do divisor da porta",
                    r"R_1 = R_2\,\frac{V_{DD} - V_G}{V_G}",
                    output=Q_(r["R2"] * (vdd - vg_t) / vg_t, "ohm"),
                    inputs={"R_2": Q_(r["R2"], "ohm"), "V_G": Q_(vg_t, "V")},
                    reference=REF_FET,
                )
            )
            r["R1"] = commercial(log, "R1", "R1 comercial", r1_calc, s.res_series, "nearest").m_as(
                "ohm"
            )
            vg = vdd * r["R2"] / (r["R1"] + r["R2"])
        rd_calc = log.add(
            record(
                "RD_calc",
                "Resistor de dreno pela VDS desejada",
                r"R_D = \frac{V_{DD} - V_{DS} - I_D R_S}{I_D}",
                output=Q_((vdd - vds - idq * r["RS"]) / idq, "ohm"),
                inputs={
                    "V_{DD}": s.VCC.to_pint(),
                    "V_{DS}": s.VCE.to_pint(),
                    "I_D": s.IC.to_pint(),
                },
                reference=REF_FET,
            )
        )
        if rd_calc.magnitude <= 0:
            raise ValueError("VDS + VS não cabe em VDD")
        r["RD"] = commercial(log, "RD", "RD comercial", rd_calc, s.res_series, "nearest").m_as(
            "ohm"
        )
        qp = jfet_q(m, vdd, vg, r["RD"], r["RS"])
        log.add(
            record(
                "ID_q",
                "Corrente de dreno com os resistores comerciais",
                r"V_G = V_{GS} + I_D R_S,\quad I_D = I_{DSS}\left(1 - \frac{V_{GS}}{V_{GS(off)}}"
                r"\right)^2",
                output=Q_(qp.ID, "A").to("mA"),
                inputs={"V_G": Q_(vg, "V"), "R_S": Q_(r["RS"], "ohm")},
                assumptions=[
                    "saturação; λ = 0; corrente de porta nula",
                    "mesmas equações do simulador",
                ],
                reference=REF_FET,
            )
        )
        if qp.VDS < qp.VGS + m.VP:
            warnings.append(
                DesignWarning(
                    code="ohmica",
                    message="O JFET saiu da saturação (VDS < VGS − VGS(off)); revise RD.",
                )
            )
        # the spread of IDSS and VGS(off) moves the Q-point: show the bounds of the datasheet
        summary: dict[str, pint.Quantity] = {
            "ID_q": Q_(qp.ID, "A").to("mA"),
            "VGS_q": Q_(qp.VGS, "V"),
            "VDS_q": Q_(qp.VDS, "V"),
            "VG_q": Q_(qp.VG, "V"),
            "VS_q": Q_(qp.VS, "V"),
            "VD_q": Q_(qp.VD, "V"),
            "IC_q": Q_(qp.ID, "A").to("mA"),
            "VCE_q": Q_(qp.VDS, "V"),
            "VB_q": Q_(qp.VG, "V"),
            "VE_q": Q_(qp.VS, "V"),
            "IDSS_model": Q_(m.IDSS, "A").to("mA"),
            "VP_model": Q_(m.VP, "V"),
        } | {k: Q_(v, "ohm") for k, v in r.items()}
        p_q = qp.VDS * qp.ID
        summary["P_Q"] = Q_(p_q, "W").to("mW")
        stresses = [
            Stress(
                designator="Q1",
                key="VDS",
                label="Tensão dreno-fonte (corte)",
                value=QuantityModel(value=vdd, unit="V"),
                calc_step_id="ID_q",
            ),
            power_stress(rec, p_q, s.TA.to_pint(), log, "Q1", "P_eq"),
        ]
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={},
            warnings=warnings,
            convergence_keys=("ID_q", "VDS_q"),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        log = CalcLog()
        vcc = s.VCC.to_pint().m_as("V")
        R = {
            k: summary[k].to_pint().m_as("ohm")
            for k in ("RC", "RE", "RB", "R1", "R2", "RD", "RS")
            if k in summary
        }
        lines = [f"VCC vcc 0 DC {vcc:.9g}"]
        if self._jfet(s):
            mj, _ = jfet_model(devices["Q1"].record, log, "Q1")
            mj = replace(mj, CGS=0.0, CGD=0.0)  # DC check: no charging transient
            lines += [
                mj.spice("JQ"),
                f"RD vcc dd {R['RD']:.9g}",
                "VSC dd d 0",
                "J1 d g s JQ",
                f"RS s 0 {R['RS']:.9g}",
            ]
            if "RG" in summary:
                lines.append(f"RG g 0 {summary['RG'].to_pint().m_as('ohm'):.9g}")
            else:
                lines += [f"R1 vcc g {R['R1']:.9g}", f"R2 g 0 {R['R2']:.9g}"]
            checks = [
                dc_check("Corrente de dreno", "ID_q", "i(vsc)"),
                dc_check("VDS", "VDS_q", "v(d)-v(s)"),
                dc_check("Tensão de fonte", "VS_q", "v(s)"),
            ]
        elif self._mos(s):
            m, _ = mos_model(devices["Q1"].record, log, "Q1")
            lines += [
                m.spice("MQ"),
                f"R1 vcc g {R['R1']:.9g}",
                f"R2 g 0 {R['R2']:.9g}",
                f"RD vcc dd {R['RD']:.9g}",
                "VSC dd d 0",
                "M1 d g s s MQ",
                f"RS s 0 {R['RS']:.9g}" if "RS" in R else "VRS s 0 0",
            ]
            checks = [
                dc_check("Corrente de dreno", "ID_q", "i(vsc)"),
                dc_check("VDS", "VDS_q", "v(d)-v(s)"),
                dc_check("Tensão de porta", "VG_q", "v(g)"),
            ]
        else:
            m_b, _ = bjt_model(
                devices["Q1"].record,
                s.IC.to_pint().m_as("A"),
                s.VBE.to_pint(),
                s.beta_ideal,
                log,
                "Q1",
            )
            # current sensor at the device collector (RB of collector feedback joins at c)
            lines += [m_b.spice("QB"), f"RC vcc c {R['RC']:.9g}", "VSC c cq 0", "Q1 cq b e QB"]
            lines.append(f"RE e 0 {R['RE']:.9g}" if "RE" in R else "VRE e 0 0")
            if s.config == "divisor":
                lines += [f"R1 vcc b {R['R1']:.9g}", f"R2 b 0 {R['R2']:.9g}"]
            elif s.config == "coletor":
                lines.append(f"RB c b {R['RB']:.9g}")
            else:
                lines.append(f"RB vcc b {R['RB']:.9g}")
            checks = [
                dc_check("Corrente de coletor", "IC_q", "i(vsc)"),
                dc_check("VCE", "VCE_q", "v(c)-v(e)"),
                dc_check("Tensão de base", "VB_q", "v(b)"),
            ]
        return dc_circuit(f"{self.id}: {ENUM_LABELS[s.config]}", "\n".join(lines), checks)

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        part = next((c.part_number for c in result.selection), "")

        def val(k: str) -> str:
            return format_eng(sm[k].to_pint()) if k in sm else ""

        svg = Svg(460, 330)
        svg.title(title)
        top, bot = 50, 290
        x = 260
        svg.wire((60, top), (400, top))
        svg.terminal(400, top, f"VCC = {s.VCC.value:g} V")
        mos = self._mos(s) or self._jfet(s)
        rtop = "RD" if mos else "RC"
        svg.resistor_v(x + 8, top, 120, rtop, val(rtop))
        if self._jfet(s):
            b, c, e = svg.njfet(x, 160, "Q1", part)
        elif mos:
            b, c, e = svg.nmos(x, 160, "Q1", part)
        else:
            b, c, e = svg.bjt(x, 160, "Q1", part)
        svg.wire((x + 8, 120), c)
        rbot = "RS" if mos else "RE"
        if rbot in sm:
            svg.resistor_v(e[0], e[1], bot, rbot, val(rbot))
        else:
            svg.wire(e, (e[0], bot))
        if s.config == "jfet_auto":
            svg.resistor_v(120, 160, bot, "RG", val("RG"))
            svg.wire((120, 160), b)
        elif s.config in ("divisor", "mos_divisor", "jfet_divisor"):
            svg.resistor_v(120, top, 160, "R1", val("R1"))
            svg.resistor_v(120, 160, bot, "R2", val("R2"))
            svg.wire((120, 160), b)
            svg.dot(120, 160)
        elif s.config == "coletor":
            svg.resistor_h(b[0] - 100, b[0], b[1], "RB", val("RB"))
            svg.wire((b[0] - 100, b[1]), (b[0] - 100, 128), (x + 8, 128))
            svg.dot(x + 8, 128)
        else:
            svg.resistor_v(120, top, 160, "RB", val("RB"))
            svg.wire((120, 160), b)
        svg.wire((60, bot), (400, bot))
        svg.ground(260, bot)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        rows = [
            resistor_row(result, k, k) for k in ("R1", "R2", "RB", "RC", "RD", "RE", "RS", "RG")
        ]
        return [r for r in rows if r]
