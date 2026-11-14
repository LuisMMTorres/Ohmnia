"""DM-DIFF: BJT differential pair with a resistor tail or a current-mirror tail.

DC: the symmetric pair is solved with the exponential junction (``design.qpoint`` style),
the mirror with finite β: I_out = I_ref/(1 + 2/β). Small signal (Boylestad & Nashelsky,
11th ed., ch. 10 "Operational amplifiers", differential amplifier circuit; Sedra & Smith,
7th ed., ch. 9 "Differential and multistage amplifiers"):

    Ad (single-ended, c2)  = gm·RC/2                    vd = v1 − v2
    Acm (single-ended, c2) = −β·RC / [rπ + 2(β + 1)·REE]
    CMRR = |Ad/Acm|,  Rid = 2·rπ

With the mirror tail the datasheet gives no Early voltage, so its output resistance is taken
as infinite: Acm = 0 and the CMRR is not computed (the simulation uses the same model).
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
    make_trace,
)
from circuitos.design.devmodels import BOYLESTAD, SEDRA, VT_300K, bjt_model, hfe_entries, quantity
from circuitos.design.engine import Analysis, Device
from circuitos.reports.common import BomRow, LabItem, resistor_row
from circuitos.reports.schematic import Svg

Tail = Literal["resistor", "espelho"]
REF = SEDRA.model_copy(update={"chapter": "9 (Differential and multistage amplifiers)"})
REF_B = BOYLESTAD.model_copy(update={"chapter": "10 (Operational amplifiers)"})


class DiffSpec(BaseModel):
    tail: Tail = "resistor"
    VCC: QuantityModel = QuantityModel(value=12, unit="V")
    VEE: QuantityModel = QuantityModel(value=12, unit="V")  # magnitude of the negative rail
    I_tail: QuantityModel = QuantityModel(value=2, unit="mA")
    vc_frac: float = Field(default=0.5, gt=0.05, lt=0.95)  # VC = frac·VCC
    vd_pk: QuantityModel = QuantityModel(value=5, unit="mV")  # differential input (waveforms)
    f_sig: QuantityModel = QuantityModel(value=1, unit="kHz")
    VBE: QuantityModel = QuantityModel(value=0.7, unit="V")
    beta_ideal: float = Field(default=100, gt=1, le=2000)
    res_series: Literal["E12", "E24"] = "E24"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")


LABELS = {
    "IC_q": "Corrente de coletor de Q1 e Q2",
    "I_tail_q": "Corrente da cauda",
    "VC_q": "Tensão de coletor",
    "VE_q": "Tensão nos emissores",
    "VCE_q": "VCE de Q1 e Q2",
    "REE": "Resistor da cauda REE",
    "Rref": "Resistor de referência do espelho",
    "I_ref": "Corrente de referência do espelho",
    "RC": "Resistor de coletor RC",
    "gm": "Transcondutância de cada transistor",
    "r_pi": "rπ de cada transistor",
    "Ad": "Ganho diferencial (saída simples em c2)",
    "Ad_diff": "Ganho diferencial (saída diferencial)",
    "Acm": "Ganho de modo comum (saída simples)",
    "CMRR_dB": "CMRR (dB)",
    "Rid": "Resistência de entrada diferencial",
    "Vcm_max": "Máximo modo comum de entrada (Q1, Q2 ativos)",
}
SPEC_LABELS = {
    "tail": "Cauda",
    "VCC": "Alimentação positiva",
    "VEE": "Alimentação negativa (módulo)",
    "I_tail": "Corrente da cauda",
    "vc_frac": "VC como fração de VCC",
    "vd_pk": "Amplitude do sinal diferencial",
    "f_sig": "Frequência do sinal",
    "VBE": "VBE na corrente de ensaio (premissa)",
    "beta_ideal": "β de projeto (passo ideal)",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {"resistor": "resistor REE", "espelho": "espelho de corrente (Q3, Q4)"}


def _spec(spec: BaseModel) -> DiffSpec:
    if not isinstance(spec, DiffSpec):
        raise TypeError("DM-DIFF espera DiffSpec")
    return spec


class DiffModule:
    id = "DM-DIFF"
    family = "amplificadores"
    title = "Amplificador diferencial"
    spec_schema = DiffSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Corrente de coletor", "multímetro (queda em RC)", "IC_q"),
        LabItem("Ganho diferencial", "osciloscópio, dois canais", "Ad"),
        LabItem("Ganho de modo comum", "osciloscópio, entradas unidas", "Acm"),
        LabItem("CMRR", "a partir dos dois ganhos", "CMRR_dB"),
    ]
    questions = [
        "Por que o ganho de modo comum diminui quando REE aumenta? O que o espelho de corrente "
        "faz com ele?",
        "Aumente o sinal diferencial até a saída distorcer: compare com a tangente hiperbólica "
        "da característica do par.",
        "O que acontece se Q1 e Q2 tiverem β diferentes? Meça a tensão de desvio na saída.",
    ]
    practice = {
        "objective": "Montar o par diferencial, medir a polarização, o ganho diferencial e o "
        "de modo comum, e calcular a CMRR.",
        "material": "Fonte simétrica, gerador de funções, osciloscópio, multímetro, "
        "transistores do mesmo lote (de preferência casados).",
        "procedure": [
            "Monte o circuito e meça VC1, VC2 e VE sem sinal.",
            "Aplique o sinal diferencial (uma base no gerador por divisor, a outra no terra) e "
            "meça a saída em c2.",
            "Una as duas bases ao gerador e meça a saída de modo comum.",
            "Calcule Ad, Acm e a CMRR; compare com o cálculo e a simulação.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        roles = [
            Role(designator="Q1–Q2", category="bjt.npn", description="Par diferencial NPN", count=2)
        ]
        if s.tail == "espelho":
            roles.append(
                Role(
                    designator="Q3–Q4",
                    category="bjt.npn",
                    description="Espelho de corrente NPN",
                    count=2,
                )
            )
        return roles

    def required_ratings(self, role: Role) -> list[str]:
        return ["VCEO", "IC"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        return bool(hfe_entries(rec))

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        q = quantity(rec, "IC", ("max",))
        return float(q.m_as("A")) if q is not None else 0.0

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vcc = s.VCC.to_pint().m_as("V")
        vee = s.VEE.to_pint().m_as("V")
        it = s.I_tail.to_pint().m_as("A")
        ic_t = it / 2
        m, w = bjt_model(devices["Q1–Q2"].record, ic_t, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
        warnings += [DesignWarning(code="modelo", message=x) for x in w]
        vbe = m.vbe(ic_t)
        r: dict[str, float] = {}
        summary: dict[str, pint.Quantity] = {}
        if s.tail == "resistor":
            ree_q = log.add(
                record(
                    "REE_calc",
                    "Resistor da cauda para a corrente desejada (bases em 0 V)",
                    r"R_{EE} = \frac{V_{EE} - V_{BE}}{I_{cauda}}",
                    output=Q_((vee - vbe) / it, "ohm"),
                    inputs={
                        "V_{EE}": s.VEE.to_pint(),
                        "V_{BE}": Q_(vbe, "V"),
                        "I_{cauda}": s.I_tail.to_pint(),
                    },
                    reference=REF_B,
                )
            )
            r["REE"] = commercial(log, "REE", "REE comercial", ree_q, s.res_series, "nearest").m_as(
                "ohm"
            )

            def residual(v: float) -> float:  # v = VBE of Q1 = Q2
                ic = m.ic(v)
                return float(2 * ic * (1 + 1 / m.BF) - (-v + vee) / r["REE"])

            vbe_q = brentq(residual, 0.0, min(vee, 1.5), xtol=1e-15)
            ic_q = m.ic(vbe_q)
            i_tail_q = 2 * ic_q * (1 + 1 / m.BF)
            latex = (
                r"2 I_S e^{V_{BE}/V_T}\frac{\beta+1}{\beta} = "
                r"\frac{V_{EE} - V_{BE}}{R_{EE}}"
            )
        else:
            m3, w3 = bjt_model(
                devices["Q3–Q4"].record, it, s.VBE.to_pint(), s.beta_ideal, log, "Q3"
            )
            warnings += [DesignWarning(code="modelo", message=x) for x in w3]
            vbe3 = m3.vbe(it)
            iref_target = it * (1 + 2 / m3.BF)
            rref_q = log.add(
                record(
                    "Rref_calc",
                    "Resistor de referência do espelho",
                    r"R_{ref} = \frac{V_{CC} + V_{EE} - V_{BE}}{I_{ref}},\;"
                    r"I_{ref} = I_o\left(1 + \frac{2}{\beta}\right)",
                    output=Q_((vcc + vee - vbe3) / iref_target, "ohm"),
                    inputs={
                        "V_{CC}": s.VCC.to_pint(),
                        "V_{EE}": s.VEE.to_pint(),
                        "V_{BE}": Q_(vbe3, "V"),
                        r"\beta": Q_(m3.BF, ""),
                    },
                    reference=REF,
                )
            )
            r["Rref"] = commercial(
                log, "Rref", "Rref comercial", rref_q, s.res_series, "nearest"
            ).m_as("ohm")

            def residual_m(v: float) -> float:  # VBE of Q3 = Q4
                ic = m3.ic(v)
                return float(ic * (1 + 2 / m3.BF) - (vcc + vee - v) / r["Rref"])

            v3 = brentq(residual_m, 0.0, min(vcc + vee, 1.5), xtol=1e-15)
            i_tail_q = m3.ic(v3)  # identical transistors, no Early effect
            summary["I_ref"] = Q_((vcc + vee - v3) / r["Rref"], "A").to("mA")
            ic_q = i_tail_q / 2 / (1 + 1 / m.BF)
            vbe_q = m.vbe(ic_q)
            latex = r"I_o = \frac{I_{ref}}{1 + 2/\beta},\; I_C = \frac{I_o}{2}\frac{\beta}{\beta+1}"
        log.add(
            record(
                "IC_q",
                "Corrente de coletor de cada transistor do par (solução exata)",
                latex,
                output=Q_(ic_q, "A").to("mA"),
                inputs={k: Q_(v, "ohm") for k, v in r.items()} | {r"\beta_F": Q_(m.BF, "")},
                assumptions=["transistores idênticos", "bases em 0 V (CC)", "sem efeito Early"],
                reference=REF,
            )
        )
        rc_q = log.add(
            record(
                "RC_calc",
                "RC para a tensão de coletor desejada",
                r"R_C = \frac{V_{CC} - V_C}{I_C}",
                output=Q_(vcc * (1 - s.vc_frac) / ic_t, "ohm"),
                inputs={
                    "V_{CC}": s.VCC.to_pint(),
                    "V_C": Q_(vcc * s.vc_frac, "V"),
                    "I_C": Q_(ic_t, "A"),
                },
                reference=REF,
            )
        )
        r["RC"] = commercial(log, "RC", "RC comercial", rc_q, s.res_series, "nearest").m_as("ohm")
        rc = r["RC"]
        vc = vcc - ic_q * rc
        ve = -vbe_q
        gm = ic_q / VT_300K
        rpi = m.BF / gm
        ad = gm * rc / 2
        log.add(
            record(
                "Ad",
                "Ganho diferencial, saída simples em c2",
                r"A_d = \frac{g_m R_C}{2},\; g_m = \frac{I_C}{V_T}",
                output=Q_(ad, ""),
                inputs={"g_m": Q_(gm, "S").to("mS"), "R_C": Q_(rc, "ohm")},
                reference=REF,
            )
        )
        summary |= {
            "IC_q": Q_(ic_q, "A").to("mA"),
            "I_tail_q": Q_(i_tail_q, "A").to("mA"),
            "VC_q": Q_(vc, "V"),
            "VE_q": Q_(ve, "V"),
            "VCE_q": Q_(vc - ve, "V"),
            "gm": Q_(gm, "S").to("mS"),
            "r_pi": Q_(rpi, "ohm").to("kohm"),
            "Ad": Q_(ad, ""),
            "Ad_diff": Q_(2 * ad, ""),
            "Rid": Q_(2 * rpi, "ohm").to("kohm"),
            "Vcm_max": Q_(vc, "V"),  # VCB ≥ 0 keeps Q1, Q2 active
        } | {k: Q_(v, "ohm") for k, v in r.items()}
        if s.tail == "resistor":
            ree = r["REE"]
            acm = m.BF * rc / (rpi + 2 * (m.BF + 1) * ree)
            log.add(
                record(
                    "Acm",
                    "Ganho de modo comum, saída simples",
                    r"|A_{cm}| = \frac{\beta R_C}{r_\pi + 2(\beta+1) R_{EE}}",
                    output=Q_(acm, ""),
                    inputs={
                        r"\beta": Q_(m.BF, ""),
                        "R_C": Q_(rc, "ohm"),
                        r"r_\pi": Q_(rpi, "ohm"),
                        "R_{EE}": Q_(ree, "ohm"),
                    },
                    reference=REF,
                )
            )
            cmrr = 20 * math.log10(ad / acm)
            log.add(
                record(
                    "CMRR_dB",
                    "Razão de rejeição de modo comum",
                    r"\mathrm{CMRR} = 20\log_{10}\left|\frac{A_d}{A_{cm}}\right|",
                    output=Q_(cmrr, ""),
                    inputs={"A_d": Q_(ad, ""), "A_{cm}": Q_(acm, "")},
                    reference=REF,
                )
            )
            summary["Acm"] = Q_(acm, "")
            summary["CMRR_dB"] = Q_(cmrr, "")
        else:
            warnings.append(
                DesignWarning(
                    code="early",
                    message="Sem tensão de Early no datasheet, o espelho é tratado "
                    "como fonte de corrente ideal: Acm = 0 e a CMRR não é calculada.",
                )
            )
        # waveforms: small-signal collector voltages for a differential sine
        vd = s.vd_pk.to_pint().m_as("V")
        th = np.linspace(0, 2 * math.pi, 720, endpoint=False)
        vin = vd * np.sin(th)
        traces = {
            "Entrada diferencial v1 − v2": make_trace("V", vin),
            "Coletor de Q2": make_trace("V", vc + ad * vin),
            "Coletor de Q1": make_trace("V", vc - ad * vin),
        }
        if vd / VT_300K > 0.5:
            warnings.append(
                DesignWarning(
                    code="grande_sinal",
                    message="vd de pico passa de 2·VT/4: o par já não é "
                    "linear (característica em tangente hiperbólica); as formas calculadas são de "
                    "pequenos sinais.",
                )
            )
        stresses = [
            Stress(
                designator="Q1–Q2",
                key="VCEO",
                label="VCE máxima",
                value=QuantityModel(value=vcc + vee, unit="V"),
                calc_step_id="IC_q",
            ),
            Stress(
                designator="Q1–Q2",
                key="IC",
                label="Corrente de coletor",
                value=QuantityModel(value=i_tail_q, unit="A"),
                calc_step_id="IC_q",
            ),
        ]
        losses = {"Q1–Q2": Q_((vc - ve) * ic_q, "W")}
        if s.tail == "espelho":
            stresses += [
                Stress(
                    designator="Q3–Q4",
                    key="VCEO",
                    label="VCE máxima",
                    value=QuantityModel(value=vcc + vee, unit="V"),
                    calc_step_id="IC_q",
                ),
                Stress(
                    designator="Q3–Q4",
                    key="IC",
                    label="Corrente de coletor",
                    value=QuantityModel(value=i_tail_q, unit="A"),
                    calc_step_id="IC_q",
                ),
            ]
            losses["Q3–Q4"] = Q_((ve + vee) * i_tail_q, "W")
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses=losses,
            warnings=warnings,
            convergence_keys=("IC_q", "Ad"),
            traces=traces,
            trace_period=Q_(1 / s.f_sig.to_pint().m_as("Hz"), "s"),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        """Two copies: ``a`` driven differentially (transient and .ac), ``b`` in common mode."""
        s = _spec(spec)
        log = CalcLog()
        vcc = s.VCC.to_pint().m_as("V")
        vee = s.VEE.to_pint().m_as("V")
        it = s.I_tail.to_pint().m_as("A")
        m, _ = bjt_model(devices["Q1–Q2"].record, it / 2, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
        lines = [m.spice("QP"), f"VCC vcc 0 DC {vcc:.9g}", f"VEE vee 0 DC {-vee:.9g}"]
        if s.tail == "espelho":
            m3, _ = bjt_model(devices["Q3–Q4"].record, it, s.VBE.to_pint(), s.beta_ideal, log, "Q3")
            lines.append(m3.spice("QM"))
        rc = summary["RC"].to_pint().m_as("ohm")
        fsig = s.f_sig.to_pint().m_as("Hz")
        vd = s.vd_pk.to_pint().m_as("V")
        for tag in ("a", "b"):
            if tag == "a":
                lines += [
                    f"V1a b1a 0 DC 0 AC 0.5 SIN(0 {vd / 2:.9g} {fsig:.9g})",
                    f"V2a b2a 0 DC 0 AC 0.5 180 SIN(0 {-vd / 2:.9g} {fsig:.9g})",
                ]
            else:
                lines += ["V1b b1b 0 DC 0 AC 1", "V2b b2b 0 DC 0 AC 1"]
            lines += [
                f"RC1{tag} vcc c1{tag} {rc:.9g}",
                f"RC2{tag} vcc c2{tag} {rc:.9g}",
                f"VS{tag} c1{tag} q1{tag} 0",
                f"Q1{tag} q1{tag} b1{tag} e{tag} QP",
                f"Q2{tag} c2{tag} b2{tag} e{tag} QP",
            ]
            if s.tail == "resistor":
                lines.append(f"REE{tag} e{tag} vee {summary['REE'].to_pint().m_as('ohm'):.9g}")
            else:
                rref = summary["Rref"].to_pint().m_as("ohm")
                lines += [
                    f"RREF{tag} vcc r{tag} {rref:.9g}",
                    f"Q4{tag} r{tag} r{tag} vee QM",
                    f"Q3{tag} e{tag} r{tag} vee QM",
                ]
        checks = [
            SimCheck(
                quantity="Corrente de coletor de Q1",
                summary_key="IC_q",
                metric="avg",
                probe="i(vsa)",
                tolerance_pct=0.5,
                justification="mesmo modelo; sinal pequeno e simétrico",
            ),
            SimCheck(
                quantity="Ganho diferencial (c2)",
                summary_key="Ad",
                metric="ac_mag",
                probe="v(c2a)",
                freq=fsig,
                tolerance_pct=0.5,
                justification="mesmo modelo linearizado (.ac)",
            ),
        ]
        if "Acm" in summary:
            checks.append(
                SimCheck(
                    quantity="Ganho de modo comum (c2)",
                    summary_key="Acm",
                    metric="ac_mag",
                    probe="v(c2b)",
                    freq=fsig,
                    tolerance_pct=0.5,
                    justification="mesmo modelo linearizado (.ac)",
                )
            )
        return Circuit(
            title=f"{self.id}: par diferencial, cauda com {ENUM_LABELS[s.tail]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=3 / fsig, unit="s"),
            tran_step=QuantityModel(value=1 / fsig / 400, unit="s"),
            period=QuantityModel(value=1 / fsig, unit="s"),
            probes={
                "Entrada diferencial v1 − v2": "v(b1a)-v(b2a)",
                "Coletor de Q2": "v(c2a)",
                "Coletor de Q1": "v(c1a)",
            },
            checks=checks,
            ac_start=QuantityModel(value=10, unit="Hz"),
            ac_stop=QuantityModel(value=1e5, unit="Hz"),
            ac_points_per_decade=10,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        parts = {c.designator: c.part_number for c in result.selection}

        def v(k: str) -> str:
            return format_eng(sm[k].to_pint()) if k in sm else ""

        svg = Svg(560, 360)
        svg.title(title)
        top, bot = 50, 320
        svg.wire((150, top), (420, top))
        svg.terminal(420, top, f"+{s.VCC.value:g} V")
        svg.resistor_v(180, top, 110, "RC1", v("RC"))
        svg.resistor_v(380, top, 110, "RC2", v("RC"))
        b1, c1, e1 = svg.bjt(172, 150, "Q1", parts.get("Q1–Q2", ""))
        b2, c2, e2 = svg.bjt(388, 150, "Q2", "", mirror=True)
        svg.wire((180, 110), c1)
        svg.wire((380, 110), c2)
        svg.terminal(b1[0] - 20, b1[1], "v1", "end")
        svg.wire(b1, (b1[0] - 16, b1[1]))
        svg.terminal(b2[0] + 20, b2[1], "v2")
        svg.wire(b2, (b2[0] + 16, b2[1]))
        svg.terminal(440, 110, "vo (c2)")
        svg.wire((380, 110), (436, 110))
        svg.wire(e1, (e1[0], 200), (e2[0], 200), e2)
        svg.dot(280, 200)
        if s.tail == "resistor":
            svg.resistor_v(280, 200, bot, "REE", v("REE"))
        else:
            b3, c3, e3 = svg.bjt(272, 250, "Q3", parts.get("Q3–Q4", ""))
            svg.wire((280, 200), c3)
            svg.wire(e3, (e3[0], bot))
            svg.wire(b3, (200, 250))
            svg.text(196, 245, f"Q4 (diodo) + Rref {v('Rref')}", "end")
        svg.wire((150, bot), (420, bot))
        svg.terminal(420, bot, f"−{s.VEE.value:g} V")
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        rows = [
            resistor_row(result, "RC1, RC2", "RC"),
            resistor_row(result, "REE", "REE"),
            resistor_row(result, "Rref", "Rref"),
        ]
        out = [r for r in rows if r]
        if out and out[0].designator == "RC1, RC2":
            out[0].quantity = 2
        return out
