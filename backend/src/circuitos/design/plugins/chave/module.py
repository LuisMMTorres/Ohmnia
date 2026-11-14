"""DM-CHAVE: transistor switch (BJT or N-MOSFET, low side) driving a resistive or inductive load.

BJT (Boylestad & Nashelsky, 11th ed., ch. 4, "Transistor switching networks"; Malvino,
*Electronic Principles*, the transistor switch): the load current with the datasheet
VCE(sat), a forced β = hFE,min/k (overdrive factor k) and RB from the datasheet VBE(sat).
The on-state is then solved with the full Ebers-Moll model (both junctions forward biased in
saturation), the same equations as the simulator; the dissipation is estimated with the
datasheet VCE(sat) maximum (conservative), not with the ideal model.

MOSFET: on-state in the triode region of the square-law model; RDS(on) of the datasheet for the
conservative loss. A drive voltage below the VGS of the RDS(on) test is flagged (not a
logic-level part). An inductive load gets a free-wheeling diode across it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import pint
from pydantic import BaseModel, Field
from scipy.optimize import fsolve, root

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng, parse_unit
from circuitos.design.analog import commercial, dc_check, dc_circuit
from circuitos.design.base import Circuit, DesignResult, DesignWarning, Role, Stress
from circuitos.design.devmodels import (
    BOYLESTAD,
    VT_300K,
    Bjt,
    Darlington,
    bjt_model,
    darlington_model,
    hfe_entries,
    is_darlington,
    mos_model,
    quantity,
)
from circuitos.design.engine import Analysis, Device
from circuitos.reports.common import BomRow, LabItem, passive, resistor_row
from circuitos.reports.schematic import Svg

Kind = Literal["tbj", "darlington", "mosfet"]
Load = Literal["resistiva", "indutiva"]
REF = BOYLESTAD.model_copy(update={"chapter": "4 (Transistor switching networks)"})


class ChaveSpec(BaseModel):
    device: Kind = "tbj"
    load: Load = "indutiva"
    VCC: QuantityModel = QuantityModel(value=12, unit="V")
    R_load: QuantityModel = QuantityModel(value=120, unit="ohm")  # e.g. relay coil
    V_drive: QuantityModel = QuantityModel(value=5, unit="V")  # logic high
    overdrive: float = Field(default=2.0, ge=1.0, le=10)  # forced β = hFE,min/k
    R_pulldown: QuantityModel = QuantityModel(value=10, unit="kohm")
    VBE: QuantityModel = QuantityModel(value=0.7, unit="V")
    beta_ideal: float = Field(default=100, gt=1, le=2000)
    res_series: Literal["E12", "E24"] = "E24"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")


LABELS = {
    "I_load": "Corrente na carga (chave fechada)",
    "IB_req": "Corrente de base exigida",
    "beta_forced": "β forçado",
    "RB": "Resistor de base RB",
    "IB_on": "Corrente de base com RB comercial",
    "IC_on": "Corrente de coletor (modelo)",
    "VCE_on": "VCE de saturação (modelo)",
    "VCE_sat_ds": "VCE(sat) máximo do datasheet",
    "P_on_ds": "Dissipação na chave (VCE(sat)/RDS(on) do datasheet)",
    "ID_on": "Corrente de dreno (modelo)",
    "VDS_on": "VDS em condução (modelo)",
    "RDS_on_ds": "RDS(on) máximo do datasheet",
    "V_off": "Tensão na chave aberta",
    "V_clamp": "Tensão máxima no desligamento",
}
SPEC_LABELS = {
    "device": "Chave",
    "load": "Carga",
    "VCC": "Alimentação da carga",
    "R_load": "Resistência da carga",
    "V_drive": "Tensão de comando (nível alto)",
    "overdrive": "Fator de sobreexcitação k",
    "R_pulldown": "Resistor de desligamento (base/porta à terra)",
    "VBE": "VBE na corrente de ensaio (premissa)",
    "beta_ideal": "β de projeto (passo ideal)",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {
    "tbj": "TBJ NPN",
    "darlington": "Darlington NPN",
    "mosfet": "MOSFET canal N",
    "resistiva": "resistiva",
    "indutiva": "indutiva (relé, solenoide)",
}


def _spec(spec: BaseModel) -> ChaveSpec:
    if not isinstance(spec, ChaveSpec):
        raise TypeError("DM-CHAVE espera ChaveSpec")
    return spec


def _nearest(rec: ComponentRecord, symbol: str, ic: float) -> tuple[float, float | None] | None:
    """(value, test IC) of the entry of ``symbol`` tested nearest to ``ic``."""
    best: tuple[float, float | None] | None = None
    dist = math.inf
    for p in rec.parameters.values():
        if p.symbol != symbol or p.max is None:
            continue
        c = p.conditions.get("IC")
        i = c.to_pint().m_as("A") if c is not None else None
        d = abs(math.log(i / ic)) if i else 1e9
        if d < dist:
            dist = d
            best = (float(Q_(p.max, parse_unit(p.unit)).m_as("V")), i)
    return best


def darlington_on(
    d: Darlington, vcc: float, rl: float, vd: float, rb: float, rpd: float
) -> tuple[float, float, float, float]:
    """(IB, IC, VBE, VCE) of a Darlington switch, both transistors with full Ebers-Moll."""

    def eqs(x: list[float]) -> list[float]:
        vb, vm, vc = x
        ib1, ic1 = d.q1.em(vb - vm, vb - vc)
        ib2, ic2 = d.q2.em(vm, vm - vc)
        return [
            (vd - vb) / rb - vb / rpd - ib1,
            ib1 + ic1 - ib2,
            (vcc - vc) / rl - ic1 - ic2,
        ]

    # Levenberg-Marquardt on the raw KCL residuals: the scaled hybrid solver
    # stopped on a spurious point when the base drive is weak.
    sol = root(eqs, [1.45, 0.72, 0.9], method="lm", options={"xtol": 1e-14, "ftol": 1e-18})
    vb, vm, vc = (float(v) for v in sol.x)
    ib1, ic1 = d.q1.em(vb - vm, vb - vc)
    _, ic2 = d.q2.em(vm, vm - vc)
    return float(ib1), float(ic1 + ic2), float(vb), float(vc)


def ebers_moll_on(
    m: Bjt, vcc: float, rl: float, vd: float, rb: float, rpd: float
) -> tuple[float, float, float, float]:
    """(IB, IC, VBE, VCE) of the switch with the full Ebers-Moll model (BR = 1)."""
    br = 1.0

    def eqs(x: list[float]) -> list[float]:
        vbe, vbc = x
        ebe = math.exp(min(vbe / VT_300K, 200))
        ebc = math.exp(min(vbc / VT_300K, 200))
        ib = m.IS / m.BF * (ebe - 1) + m.IS / br * (ebc - 1)
        ic = m.IS * (ebe - ebc) - m.IS / br * (ebc - 1)
        vce = vbe - vbc
        return [(vd - vbe) / rb - vbe / rpd - ib, (vcc - vce) / rl - ic]

    vbe, vbc = fsolve(eqs, [0.75, 0.6], xtol=1e-14)
    ebe = math.exp(vbe / VT_300K)
    ebc = math.exp(vbc / VT_300K)
    ib = m.IS / m.BF * (ebe - 1) + m.IS * (ebc - 1)
    ic = m.IS * (ebe - ebc) - m.IS * (ebc - 1)
    return float(ib), float(ic), float(vbe), float(vbe - vbc)


class ChaveModule:
    id = "DM-CHAVE"
    family = "amplificadores"
    title = "Chave transistorizada"
    spec_schema = ChaveSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Corrente na carga", "multímetro em série", "I_load"),
        LabItem("VCE/VDS com a chave fechada", "multímetro CC", "VCE_on"),
        LabItem("Corrente de base", "multímetro em série", "IB_on"),
    ]
    questions = [
        "Por que se usa um β forçado bem menor que o hFE para garantir a saturação?",
        "Retire o diodo de roda livre (com cuidado, ponteira atenuada) e observe o pico de "
        "tensão no desligamento da carga indutiva.",
        "Compare a dissipação da chave saturada com a de um transistor na região ativa com "
        "a mesma corrente.",
    ]
    practice = {
        "objective": "Montar a chave, verificar a saturação (ou a condução do MOSFET) e a "
        "proteção da carga indutiva.",
        "material": "Fonte CC, gerador de onda quadrada (ou saída digital), osciloscópio, "
        "multímetro, carga (relé, lâmpada ou resistor).",
        "procedure": [
            "Monte o circuito; confira a polaridade do diodo de roda livre.",
            "Aplique o nível alto de comando e meça VCE/VDS e a corrente na carga.",
            "Aplique uma onda quadrada e observe a tensão no coletor/dreno no desligamento.",
            "Meça a temperatura do transistor após alguns minutos ligado.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        roles = [
            Role(
                designator="Q1",
                category="mosfet.n" if s.device == "mosfet" else "bjt.npn",
                description="Chave " + ENUM_LABELS[s.device],
            )
        ]
        if s.load == "indutiva":
            roles.append(Role(designator="D1", category="diode", description="Diodo de roda livre"))
        return roles

    def required_ratings(self, role: Role) -> list[str]:
        if role.designator == "D1":
            return ["VRRM", "IF(AV)"]
        return ["VDS"] if role.category.startswith("mosfet") else ["VCEO", "IC"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        if role.designator == "D1":
            return not rec.category.startswith("diode.zener")
        if role.category.startswith("mosfet"):
            vth = rec.parameters.get("VGS(th)")
            rds = rec.parameters.get("RDS(on)")
            return bool(vth and vth.min is not None and rds and rds.max is not None)
        want = _spec(spec).device == "darlington"
        return (
            bool(hfe_entries(rec))
            and is_darlington(rec) == want
            and any(p.symbol == "VCE(sat)" for p in rec.parameters.values())
        )

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        key = "IF(AV)" if role.designator == "D1" else "IC"
        q = quantity(rec, key, ("max",)) or quantity(rec, "ID", ("max",))
        return float(q.m_as("A")) if q is not None else 0.0

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vcc = s.VCC.to_pint().m_as("V")
        rl = s.R_load.to_pint().m_as("ohm")
        vd = s.V_drive.to_pint().m_as("V")
        rpd = s.R_pulldown.to_pint().m_as("ohm")
        rec = devices["Q1"].record
        summary: dict[str, pint.Quantity] = {}
        r: dict[str, float] = {}
        if s.device in ("tbj", "darlington"):
            dar = s.device == "darlington"
            i0 = vcc / rl
            sat = _nearest(rec, "VCE(sat)", i0) if rec else None
            vce_ds = sat[0] if sat else 0.2
            beta_min = None
            if rec is not None:
                known = [(i, p) for i, p in hfe_entries(rec) if i is not None]
                if known:
                    _, p = min(known, key=lambda e: abs(math.log((e[0] or 1.0) / i0)))
                    beta_min = p.min or p.typ
            beta_min = beta_min or s.beta_ideal
            il = log.add(
                record(
                    "I_load",
                    "Corrente na carga com a chave saturada",
                    r"I_C = \frac{V_{CC} - V_{CE(sat)}}{R_L}",
                    output=Q_((vcc - vce_ds) / rl, "A").to("mA"),
                    inputs={
                        "V_{CC}": s.VCC.to_pint(),
                        "V_{CE(sat)}": Q_(vce_ds, "V"),
                        "R_L": s.R_load.to_pint(),
                    },
                    assumptions=["V_CE(sat) máximo do datasheet no I_C de ensaio mais próximo"],
                    reference=REF,
                )
            ).m_as("A")
            bf = log.add(
                record(
                    "beta_forced",
                    "β forçado (sobreexcitação)",
                    r"\beta_{forçado} = h_{FE,min}/k",
                    output=Q_(beta_min / s.overdrive, ""),
                    inputs={"h_{FE,min}": Q_(beta_min, ""), "k": Q_(s.overdrive, "")},
                    reference=REF,
                )
            ).m_as("")
            ib = log.add(
                record(
                    "IB_req",
                    "Corrente de base exigida",
                    r"I_B = \frac{I_C}{\beta_{forçado}} + \frac{V_{BE}}{R_{pd}}",
                    output=Q_(il / bf + (1.6 if dar else 0.8) / rpd, "A").to("mA"),
                    inputs={"I_C": Q_(il, "A"), r"\beta_{forçado}": Q_(bf, "")},
                    assumptions=["R_pd desvia ~V_BE(sat)/R_pd"],
                    reference=REF,
                )
            ).m_as("A")
            vbe_sat = _nearest(rec, "VBE(on)" if dar else "VBE(sat)", il) if rec else None
            vbs = vbe_sat[0] if vbe_sat else (1.6 if dar else 0.8)
            rb_c = log.add(
                record(
                    "RB_calc",
                    "Resistor de base",
                    r"R_B = \frac{V_{drive} - V_{BE(sat)}}{I_B}",
                    output=Q_((vd - vbs) / ib, "ohm"),
                    inputs={
                        "V_{drive}": s.V_drive.to_pint(),
                        "V_{BE(sat)}": Q_(vbs, "V"),
                        "I_B": Q_(ib, "A"),
                    },
                    assumptions=["V_BE(sat) máximo do datasheet"],
                    reference=REF,
                )
            )
            if rb_c.magnitude <= 0:
                raise ValueError("A tensão de comando não passa de VBE(sat)")
            r["RB"] = commercial(
                log, "RB", "RB comercial (para baixo: mais corrente)", rb_c, s.res_series, "down"
            ).m_as("ohm")
            m: Bjt | Darlington
            if dar:
                m, w = darlington_model(rec, il, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
                ib_on, ic_on, _vbe_on, vce_on = darlington_on(m, vcc, rl, vd, r["RB"], rpd)
            else:
                m, w = bjt_model(rec, il, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
                ib_on, ic_on, _vbe_on, vce_on = ebers_moll_on(m, vcc, rl, vd, r["RB"], rpd)
            warnings += [DesignWarning(code="modelo", message=x) for x in w]
            log.add(
                record(
                    "VCE_on",
                    "Ponto de operação saturado (Ebers-Moll completo)",
                    r"I_C = I_S(e^{V_{BE}/V_T} - e^{V_{BC}/V_T}) - \frac{I_S}{\beta_R}"
                    r"(e^{V_{BC}/V_T} - 1)",
                    output=Q_(vce_on, "V"),
                    inputs={
                        "R_B": Q_(r["RB"], "ohm"),
                        r"\beta_F": Q_(m.BF, ""),
                        r"\beta_R": Q_(1.0, ""),
                    },
                    assumptions=[
                        "β_R = 1 (o datasheet não dá o ganho reverso)",
                        "mesmas equações do simulador; sem resistências de "
                        "corpo, por isso V_CE fica abaixo do V_CE(sat) do "
                        "datasheet",
                    ],
                    reference=REF,
                )
            )
            p_ds = vce_ds * il + vbs * ib_on
            summary |= {
                "I_load": Q_(il, "A").to("mA"),
                "beta_forced": Q_(bf, ""),
                "IB_req": Q_(ib, "A").to("mA"),
                "IB_on": Q_(ib_on, "A").to("mA"),
                "IC_on": Q_(ic_on, "A").to("mA"),
                "VCE_on": Q_(vce_on, "V"),
                "VCE_sat_ds": Q_(vce_ds, "V"),
                "P_on_ds": Q_(p_ds, "W").to("mW"),
                "RB": Q_(r["RB"], "ohm"),
            }
            if ic_on / ib_on > m.BF * 0.9:
                warnings.append(
                    DesignWarning(code="nao_satura", message="O transistor não satura com este RB.")
                )
            key_v, key_i = "VCEO", "IC"
        else:
            m_f, w = mos_model(rec, log, "Q1")
            warnings += [DesignWarning(code="modelo", message=x) for x in w]
            rds = rec.parameters.get("RDS(on)") if rec else None
            rds_ds = Q_(rds.max, parse_unit(rds.unit)).m_as("ohm") if rds and rds.max else 0.0
            vgs_test = (
                rds.conditions["VGS"].to_pint().m_as("V")
                if rds and "VGS" in rds.conditions
                else None
            )
            if vgs_test is not None and vd < vgs_test:
                warnings.append(
                    DesignWarning(
                        code="nivel_logico",
                        message=f"O comando ({vd:g} V) é menor que o VGS de "
                        f"ensaio de RDS(on) ({vgs_test:g} V): o MOSFET não é de nível lógico e o "
                        "RDS(on) real será maior que o do datasheet.",
                    )
                )
            vgs = vd * rpd / (rpd + 100.0)
            r["RG"] = 100.0
            vov = vgs - m_f.VT
            if vov <= 0:
                raise ValueError("O comando não passa do limiar do MOSFET")
            # triode: ID = KP[(vov)·VDS − VDS²/2], VDS = VCC − ID·RL  (quadratic in VDS)
            a = m_f.KP * rl / 2
            b = -(1 + m_f.KP * rl * vov)
            c = vcc
            vds = (-b - math.sqrt(b * b - 4 * a * c)) / (2 * a)
            if vds > vov:
                vds = vcc - m_f.KP / 2 * vov**2 * rl  # saturated: not a good switch
                warnings.append(
                    DesignWarning(
                        code="saturacao_mos",
                        message="O MOSFET não entrou no triodo: comando insuficiente.",
                    )
                )
            idn = (vcc - vds) / rl
            log.add(
                record(
                    "VDS_on",
                    "MOSFET em condução (triodo, modelo quadrático)",
                    r"I_D = K_P\left[(V_{GS} - V_T)V_{DS} - \frac{V_{DS}^2}{2}\right],\;"
                    r"V_{DS} = V_{CC} - I_D R_L",
                    output=Q_(vds, "V"),
                    inputs={
                        "V_{GS}": Q_(vgs, "V"),
                        "V_T": Q_(m_f.VT, "V"),
                        "K_P": Q_(m_f.KP, "A/V**2"),
                        "R_L": s.R_load.to_pint(),
                    },
                    reference=REF,
                )
            )
            il = idn
            p_ds = (vcc / (rl + rds_ds)) ** 2 * rds_ds
            log.add(
                record(
                    "P_on_ds",
                    "Perda em condução com RDS(on) máximo",
                    r"P = I_D^2 R_{DS(on)}",
                    output=Q_(p_ds, "W").to("mW"),
                    inputs={"R_{DS(on)}": Q_(rds_ds, "ohm")},
                    reference=REF,
                )
            )
            summary |= {
                "I_load": Q_(idn, "A").to("mA"),
                "ID_on": Q_(idn, "A").to("mA"),
                "VDS_on": Q_(vds, "V"),
                "RDS_on_ds": Q_(rds_ds, "ohm"),
                "P_on_ds": Q_(p_ds, "W").to("mW"),
                "IC_on": Q_(idn, "A").to("mA"),
                "VCE_on": Q_(vds, "V"),
            }
            key_v, key_i = "VDS", "ID"
        stresses = [
            Stress(
                designator="Q1",
                key=key_v,
                label="Tensão com a chave aberta",
                value=QuantityModel(value=vcc + (1.0 if s.load == "indutiva" else 0.0), unit="V"),
                calc_step_id="P_on_ds" if s.device == "mosfet" else "I_load",
            ),
            Stress(
                designator="Q1",
                key=key_i,
                label="Corrente na carga",
                value=QuantityModel(value=il, unit="A"),
                calc_step_id="P_on_ds" if s.device == "mosfet" else "I_load",
            ),
        ]
        summary["V_off"] = Q_(vcc, "V")
        if s.load == "indutiva":
            vf = devices["D1"].drop.m_as("V") if "D1" in devices else 0.0
            log.add(
                record(
                    "V_clamp",
                    "Tensão na chave no desligamento (diodo de roda livre)",
                    r"V_{max} = V_{CC} + V_F",
                    output=Q_(vcc + vf, "V"),
                    inputs={"V_F": Q_(vf, "V")},
                    assumptions=["o diodo conduz a corrente da bobina no desligamento"],
                    reference=REF,
                )
            )
            summary["V_clamp"] = Q_(vcc + vf, "V")
            stresses += [
                Stress(
                    designator="D1",
                    key="VRRM",
                    label="Tensão reversa",
                    value=QuantityModel(value=vcc, unit="V"),
                    calc_step_id="V_clamp",
                ),
                Stress(
                    designator="D1",
                    key="IF(AV)",
                    label="Corrente da bobina",
                    value=QuantityModel(value=il, unit="A"),
                    calc_step_id="V_clamp",
                ),
            ]
        summary |= {k: Q_(v, "ohm") for k, v in r.items()}
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": summary["P_on_ds"].to("W")},
            warnings=warnings,
            convergence_keys=("I_load",),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        """On-state at DC (the inductance does not matter at DC; the diode is reverse biased)."""
        s = _spec(spec)
        log = CalcLog()
        vcc = s.VCC.to_pint().m_as("V")
        rl = s.R_load.to_pint().m_as("ohm")
        vd = s.V_drive.to_pint().m_as("V")
        rpd = s.R_pulldown.to_pint().m_as("ohm")
        lines = [
            f"VCC vcc 0 DC {vcc:.9g}",
            f"VDR dr 0 DC {vd:.9g}",
            f"RL vcc c {rl:.9g}",
            "VSC c cq 0",
        ]
        if s.device in ("tbj", "darlington"):
            il = summary["I_load"].to_pint().m_as("A")
            rb = summary["RB"].to_pint().m_as("ohm")
            lines += [f"RB dr b {rb:.9g}", f"RPD b 0 {rpd:.9g}"]
            if s.device == "darlington":
                dm, _ = darlington_model(
                    devices["Q1"].record, il, s.VBE.to_pint(), s.beta_ideal, log, "Q1"
                )
                lines += [dm.subckt("DS"), "X1 cq b 0 DS"]
            else:
                m, _ = bjt_model(devices["Q1"].record, il, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
                lines += [m.spice("QS"), "Q1 cq b 0 QS"]
            checks = [
                dc_check("Corrente de coletor", "IC_on", "i(vsc)"),
                dc_check("VCE de saturação", "VCE_on", "v(c)", 1.0),
            ]
        else:
            m_f, _ = mos_model(devices["Q1"].record, log, "Q1")
            lines += [
                m_f.spice("MS"),
                f"RG dr g {summary['RG'].to_pint().m_as('ohm'):.9g}",
                f"RPD g 0 {rpd:.9g}",
                "M1 cq g 0 0 MS",
            ]
            checks = [
                dc_check("Corrente de dreno", "ID_on", "i(vsc)"),
                dc_check("VDS em condução", "VDS_on", "v(c)", 1.0),
            ]
        return dc_circuit(
            f"{self.id}: {ENUM_LABELS[s.device]}, carga {ENUM_LABELS[s.load]}",
            "\n".join(lines),
            checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        parts = {c.designator: c.part_number for c in result.selection}
        svg = Svg(480, 320)
        svg.title(title)
        x = 300
        svg.wire((x + 8, 40), (420, 40))
        svg.terminal(420, 40, f"VCC = {s.VCC.value:g} V")
        svg.resistor_v(
            x + 8,
            40,
            130,
            "RL" if s.load == "resistiva" else "Bobina",
            format_eng(s.R_load.to_pint()),
        )
        if s.load == "indutiva":
            svg.diode_v(x + 80, 40, 130, "D1", parts.get("D1", ""), up=True)
            svg.wire((x + 8, 40), (x + 80, 40))
            svg.wire((x + 8, 130), (x + 80, 130))
        if s.device in ("tbj", "darlington"):
            b, c, e = svg.bjt(x, 170, "Q1", parts.get("Q1", ""))
            rname, rval = "RB", format_eng(sm["RB"].to_pint())
        else:
            b, c, e = svg.nmos(x, 170, "Q1", parts.get("Q1", ""))
            rname, rval = "RG", format_eng(sm["RG"].to_pint())
        svg.wire((x + 8, 130), c)
        svg.wire(e, (e[0], 280))
        svg.resistor_h(120, b[0], b[1], rname, rval)
        svg.terminal(116, b[1], f"comando {s.V_drive.value:g} V", "end")
        svg.dot(220, b[1])
        svg.resistor_v(220, b[1], 280, "Rpd", format_eng(s.R_pulldown.to_pint()))
        svg.wire((220, 280), (x + 8, 280))
        svg.ground(x + 8, 280)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        rows = [r for r in (resistor_row(result, "RB", "RB"),) if r]
        if "RG" in result.summary:
            rows.append(
                passive(
                    "RG",
                    "Resistor de porta",
                    "100 Ω",
                    "limita a corrente de carga da capacitância de porta",
                )
            )
        rows.append(
            passive(
                "Rpd",
                "Resistor de desligamento",
                format_eng(s.R_pulldown.to_pint()),
                "mantém a chave aberta com a entrada flutuando",
            )
        )
        return rows
