"""DM-OPA: linear op-amp circuits.

Ideal closed-loop relations (Sedra & Smith, *Microelectronic Circuits*, 7th ed., ch. 2
"Operational amplifiers"; Pertence, *Amplificadores operacionais e filtros ativos*): inverting
−R2/R1, non-inverting 1 + R2/R1, follower 1, summing −Rf/Ri per input, difference
(R2/R1)(v2 − v1) with R4/R3 = R2/R1, integrator −1/(sRC) (with Rf ∥ C to set the DC gain),
differentiator −sRC (with a series R to limit the high-frequency gain), transimpedance −Rf,
transconductance with the load in the feedback path i = vi/R1, three-op-amp instrumentation
amplifier (1 + 2R/RG)·(R4/R3).

The analysis then solves the real circuit, with the macromodel of the chosen op-amp (finite A0,
single pole at GBW/A0, Rin, VOS and bias currents; see ``design/opamp.py``), by modified nodal
analysis: the DC output error with the input at zero, the gain at the signal frequency and the
−3 dB frequency. The netlist holds the same elements, so ``.op``/``.ac`` agree to rounding.
"""

from __future__ import annotations

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
from circuitos.design.engine import Analysis, Device
from circuitos.design.mna import Circuit as Mna
from circuitos.design.opamp import REF, OpAmp, gbw_of, opamp_model
from circuitos.design.smallsignal import corner, log_grid
from circuitos.reports.common import BomRow, LabItem, passive, resistor_row
from circuitos.reports.schematic import Svg

Config = Literal[
    "inversor",
    "nao_inversor",
    "seguidor",
    "somador",
    "subtrator",
    "integrador",
    "diferenciador",
    "transimpedancia",
    "transcondutancia",
    "instrumentacao",
]
F1, F2, PPD = 0.1, 1e8, 20
SIM_RUN = 1e-3  # s, DC check transient (starts at the DC solution)


class OpaSpec(BaseModel):
    config: Config = "inversor"
    Av: float = Field(default=10, gt=0, le=1e4)  # |gain| (at f_sig for integrator/differentiator)
    R_base: QuantityModel = QuantityModel(value=10, unit="kohm")  # R1 (input resistor)
    Rt: QuantityModel = QuantityModel(value=100, unit="kohm")  # transimpedance (V/A)
    Gm: QuantityModel = QuantityModel(value=1, unit="mA/V")  # transconductance
    R_load_fb: QuantityModel = QuantityModel(value=1, unit="kohm")  # load in the feedback (V-I)
    Vin: QuantityModel = QuantityModel(value=0.5, unit="V")  # input amplitude (sine)
    Iin: QuantityModel = QuantityModel(value=20, unit="uA")  # input current amplitude (I-V)
    f_sig: QuantityModel = QuantityModel(value=1, unit="kHz")
    VCC: QuantityModel = QuantityModel(value=15, unit="V")  # ± supplies
    RL: QuantityModel = QuantityModel(value=10, unit="kohm")
    bias_comp: bool = True  # resistor at the non-inverting input = R seen by the inverting one
    res_series: Literal["E24", "E96"] = "E96"
    TA: QuantityModel = QuantityModel(value=25, unit="degC")


LABELS = {
    "Av_ideal": "Ganho ideal",
    "Av": "Ganho na frequência do sinal (modelo do ampop)",
    "gain_err": "Erro de ganho por A0 e GBW finitos",
    "f_H": "Frequência de corte superior (−3 dB)",
    "f_L": "Frequência de corte inferior (−3 dB)",
    "Vo_dc": "Saída com entrada nula (offset e polarização)",
    "Vo_pk": "Amplitude de saída",
    "Vo_max": "Excursão disponível (positiva)",
    "SR_req": "Taxa de inclinação exigida",
    "f_pmax": "Banda de potência plena (SR/2πVo)",
    "R1": "R1",
    "R2": "R2 (realimentação)",
    "Rp": "Resistor de compensação na entrada +",
    "C1": "Capacitor",
    "R3": "R3",
    "R4": "R4",
    "RG": "RG (ganho do amplificador de instrumentação)",
    "Rin": "Resistência de entrada",
    "IL_pk": "Corrente de pico na carga (V-I)",
}
SPEC_LABELS = {
    "config": "Circuito",
    "Av": "|Ganho| desejado",
    "R_base": "Resistor de entrada R1",
    "Rt": "Transimpedância (V/A)",
    "Gm": "Transcondutância",
    "R_load_fb": "Carga na realimentação (V-I)",
    "Vin": "Amplitude do sinal de entrada",
    "Iin": "Amplitude da corrente de entrada",
    "f_sig": "Frequência do sinal",
    "VCC": "Alimentação (±)",
    "RL": "Carga na saída",
    "bias_comp": "Compensar corrente de polarização",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {
    "inversor": "inversor",
    "nao_inversor": "não inversor",
    "seguidor": "seguidor de tensão",
    "somador": "somador inversor (2 entradas)",
    "subtrator": "subtrator (diferencial)",
    "integrador": "integrador (com Rf)",
    "diferenciador": "diferenciador (com R série)",
    "transimpedancia": "conversor I-V (transimpedância)",
    "transcondutancia": "conversor V-I (carga flutuante)",
    "instrumentacao": "amplificador de instrumentação (3 ampops)",
    "E24": "E24",
    "E96": "E96",
}


def _spec(spec: BaseModel) -> OpaSpec:
    if not isinstance(spec, OpaSpec):
        raise TypeError("DM-OPA espera OpaSpec")
    return spec


def par(*r: float) -> float:
    return 1 / sum(1 / x for x in r)


class OpaModule:
    id = "DM-OPA"
    family = "ampops"
    title = "Ampop: circuitos lineares"
    spec_schema = OpaSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Ganho na frequência do sinal", "osciloscópio, dois canais", "Av"),
        LabItem("Frequência de corte superior", "gerador + osciloscópio (−3 dB)", "f_H"),
        LabItem("Saída com entrada aterrada", "multímetro CC", "Vo_dc"),
    ]
    questions = [
        "Por que o ganho medido em alta frequência cai? Relacione f_H com GBW e o ganho.",
        "De onde vem a tensão de saída com a entrada aterrada? Como o resistor na entrada + "
        "reduz a parcela da corrente de polarização?",
        "Aumente a amplitude até a saída distorcer: é saturação ou taxa de inclinação?",
    ]
    practice = {
        "objective": "Montar o circuito com ampop, medir ganho, banda e erro CC e comparar "
        "com o projeto.",
        "material": "Fonte simétrica, gerador, osciloscópio, multímetro, ampop do projeto e "
        "resistores/capacitores da lista de materiais.",
        "procedure": [
            "Monte com a alimentação desligada; confira a pinagem do ampop.",
            "Com a entrada aterrada, meça a tensão de saída (erro CC).",
            "Aplique o sinal de projeto e meça a relação saída/entrada.",
            "Varra a frequência até o ganho cair 3 dB e anote f_H.",
        ],
    }

    def _n_opamps(self, s: OpaSpec) -> int:
        return 3 if s.config == "instrumentacao" else 1

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        return [
            Role(designator=f"U{k + 1}", category="opamp", description="Amplificador operacional")
            for k in range(self._n_opamps(s))
        ]

    def required_ratings(self, role: Role) -> list[str]:
        return []  # the supply limit is checked in accepts (± or total, as the datasheet gives)

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        s = _spec(spec)
        vs = s.VCC.to_pint().m_as("V")
        sym = rec.parameters.get("VS_max")
        tot = rec.parameters.get("VS_total_max")
        ok = (sym is not None and (sym.max or 0) >= vs) or (
            tot is not None and (tot.max or 0) >= 2 * vs
        )
        return ok and "Avol" in rec.parameters

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        # prefer the part whose GBW leaves the most margin, then the smaller offset
        s = _spec(spec)
        gbw = gbw_of(rec)
        need = max(s.Av, 1) * s.f_sig.to_pint().m_as("Hz") * 10
        vos = rec.parameters.get("Vos")
        v = (vos.typ or vos.max or 0.0) if vos is not None and vos.has_value else 0.0
        return (0.0 if gbw >= need else 1.0) + v / 1e3

    # ------------------------------------------------------------------ design
    def _values(self, s: OpaSpec, log: CalcLog) -> dict[str, float]:
        """Passive values from the ideal relations, rounded to the series."""
        ser = s.res_series
        r1 = s.R_base.to_pint().m_as("ohm")
        av = s.Av
        w = 2 * math.pi * s.f_sig.to_pint().m_as("Hz")
        v: dict[str, float] = {}

        def com(step: str, desc: str, q: pint.Quantity, mode: str = "nearest") -> float:
            return float(commercial(log, step, desc, q, ser, mode).m_as("ohm"))

        c = s.config
        if c in ("inversor", "somador", "subtrator"):
            v["R1"] = r1
            r2 = log.add(
                record(
                    "R2_calc",
                    "Realimentação para o ganho pedido",
                    r"R_2 = |A_v|\,R_1",
                    output=Q_(av * r1, "ohm"),
                    inputs={"|A_v|": Q_(av, ""), "R_1": s.R_base.to_pint()},
                    reference=REF,
                )
            )
            v["R2"] = com("R2", "R2", r2)
            if c == "subtrator":
                v["R3"], v["R4"] = v["R1"], v["R2"]
        elif c == "nao_inversor":
            if av <= 1:
                raise ValueError("Não inversor: ganho deve ser maior que 1 (use o seguidor)")
            v["R1"] = r1
            r2 = log.add(
                record(
                    "R2_calc",
                    "Realimentação para o ganho pedido",
                    r"R_2 = (A_v - 1)\,R_1",
                    output=Q_((av - 1) * r1, "ohm"),
                    inputs={"A_v": Q_(av, ""), "R_1": s.R_base.to_pint()},
                    reference=REF,
                )
            )
            v["R2"] = com("R2", "R2", r2)
        elif c == "integrador":
            v["R1"] = r1
            cc = log.add(
                record(
                    "C1_calc",
                    "Capacitor para |Av| na frequência do sinal",
                    r"C = \frac{1}{\omega R_1 |A_v|}",
                    output=Q_(1 / (w * r1 * av), "F").to("nF"),
                    inputs={"R_1": s.R_base.to_pint(), r"\omega": Q_(w, "rad/s")},
                    reference=REF,
                )
            )
            v["C1"] = float(commercial(log, "C1", "Capacitor", cc, "E12", "nearest").m_as("F"))
            rf = log.add(
                record(
                    "R2_calc",
                    "Resistor em paralelo com C (limita o ganho CC; polo em f/10)",
                    r"R_f = \frac{10}{\omega C}",
                    output=Q_(10 / (w * v["C1"]), "ohm"),
                    inputs={"C": Q_(v["C1"], "F").to("nF")},
                    assumptions=["critério de projeto: o polo de R_f·C fica uma década abaixo"],
                    reference=REF,
                )
            )
            v["R2"] = com("R2", "Rf", rf)
        elif c == "diferenciador":
            cc = log.add(
                record(
                    "C1_calc",
                    "Capacitor para |Av| na frequência do sinal",
                    r"C = \frac{|A_v|}{\omega R_f}",
                    output=Q_(av / (w * r1 * av), "F").to("nF"),
                    inputs={"R_f": Q_(r1 * av, "ohm"), r"\omega": Q_(w, "rad/s")},
                    assumptions=["R_f = |A_v|·R_1, com R_1 o resistor série da entrada"],
                    reference=REF,
                )
            )
            v["R2"] = com("R2", "Rf", Q_(r1 * av, "ohm"))
            v["C1"] = float(commercial(log, "C1", "Capacitor", cc, "E12", "nearest").m_as("F"))
            rs = log.add(
                record(
                    "R1_calc",
                    "Resistor em série com C (o ganho para de subir em 10·f)",
                    r"R_s = \frac{1}{10\,\omega C}",
                    output=Q_(1 / (10 * w * v["C1"]), "ohm"),
                    inputs={"C": Q_(v["C1"], "F").to("nF")},
                    assumptions=["critério de projeto: polo uma década acima do sinal"],
                    reference=REF,
                )
            )
            v["R1"] = com("R1", "Rs", rs)
        elif c == "transimpedancia":
            v["R2"] = com("R2", "Rf = Rt", s.Rt.to_pint().to("ohm"))
        elif c == "transcondutancia":
            r = log.add(
                record(
                    "R1_calc",
                    "Resistor de entrada para a transcondutância",
                    r"R_1 = \frac{1}{G_m}",
                    output=Q_(1 / s.Gm.to_pint().m_as("S"), "ohm"),
                    inputs={"G_m": s.Gm.to_pint()},
                    reference=REF,
                )
            )
            v["R1"] = com("R1", "R1", r)
            v["R2"] = s.R_load_fb.to_pint().m_as("ohm")
        elif c == "instrumentacao":
            if av <= 1:
                raise ValueError("Instrumentação: ganho deve ser maior que 1")
            v["R1"] = r1  # R of the first stage (each side); difference stage R3 = R4 = R1
            rg = log.add(
                record(
                    "RG_calc",
                    "RG para o ganho pedido (estágio diferencial com ganho 1)",
                    r"R_G = \frac{2R}{A_v - 1}",
                    output=Q_(2 * r1 / (av - 1), "ohm"),
                    inputs={"R": s.R_base.to_pint(), "A_v": Q_(av, "")},
                    reference=REF,
                )
            )
            v["RG"] = com("RG", "RG", rg)
            v["R3"] = v["R4"] = r1
        # bias compensation resistor at the non-inverting input
        if s.bias_comp and c in ("inversor", "somador", "integrador", "transimpedancia"):
            seen = {
                "inversor": lambda: par(v["R1"], v["R2"]),
                "somador": lambda: par(v["R1"], v["R1"], v["R2"]),
                "integrador": lambda: par(v["R1"], v["R2"]),
                "transimpedancia": lambda: v["R2"],
            }[c]()
            rp = log.add(
                record(
                    "Rp_calc",
                    "Resistor na entrada + igual ao visto pela entrada −",
                    r"R_p = R_{eq,-}",
                    output=Q_(seen, "ohm"),
                    assumptions=["anula a parcela de I_B (sobra a de I_OS)"],
                    reference=REF,
                )
            )
            v["Rp"] = com("Rp", "Rp", rp)
        return v

    def circuit(self, s: OpaSpec, v: Mapping[str, float], ops: list[OpAmp]) -> tuple[Mna, str]:
        """MNA circuit (input source "Vsig" with AC 1) and the output expression."""
        c = Mna()
        rl = s.RL.to_pint().m_as("ohm")
        cfg = s.config
        rp = v.get("Rp", 0.0)
        u = ops[0]

        def plus(node: str) -> str:
            if rp > 0:
                c.R("p", "p", "0", rp)
                return "p"
            return "0" if node == "0" else node

        out = "v(o)"
        if cfg == "inversor":
            c.V("sig", "s", "0", 0.0, 1.0)
            c.R("1", "s", "n", v["R1"])
            c.R("2", "n", "o", v["R2"])
            u.add(c, "U1", plus("0"), "n", "o")
        elif cfg == "somador":
            c.V("sig", "s", "0", 0.0, 1.0)
            c.V("sig2", "s2", "0", 0.0, 0.0)
            c.R("1", "s", "n", v["R1"])
            c.R("1b", "s2", "n", v["R1"])
            c.R("2", "n", "o", v["R2"])
            u.add(c, "U1", plus("0"), "n", "o")
        elif cfg == "subtrator":
            c.V("sig", "s", "0", 0.0, 1.0)  # differential input at v2 (non-inverting side)
            c.R("1", "0", "n", v["R1"])
            c.R("2", "n", "o", v["R2"])
            c.R("3", "s", "p", v["R3"])
            c.R("4", "p", "0", v["R4"])
            u.add(c, "U1", "p", "n", "o")
        elif cfg in ("nao_inversor", "seguidor"):
            c.V("sig", "s", "0", 0.0, 1.0)
            if cfg == "nao_inversor":
                c.R("1", "n", "0", v["R1"])
                c.R("2", "n", "o", v["R2"])
                u.add(c, "U1", "s", "n", "o")
            else:
                u.add(c, "U1", "s", "o", "o")
        elif cfg == "integrador":
            c.V("sig", "s", "0", 0.0, 1.0)
            c.R("1", "s", "n", v["R1"])
            c.C("1", "n", "o", v["C1"])
            c.R("2", "n", "o", v["R2"])
            u.add(c, "U1", plus("0"), "n", "o")
        elif cfg == "diferenciador":
            c.V("sig", "s", "0", 0.0, 1.0)
            c.R("1", "s", "m", v["R1"])
            c.C("1", "m", "n", v["C1"])
            c.R("2", "n", "o", v["R2"])
            u.add(c, "U1", "0", "n", "o")
        elif cfg == "transimpedancia":
            c.I("sig", "0", "n", 0.0, 1.0)  # current into the inverting node
            c.R("s", "n", "0", 1e12)  # source resistance of an ideal current source (DC path)
            c.R("2", "n", "o", v["R2"])
            u.add(c, "U1", plus("0"), "n", "o")
        elif cfg == "transcondutancia":
            c.V("sig", "s", "0", 0.0, 1.0)
            c.R("1", "n", "0", v["R1"])
            c.R("2", "n", "o", v["R2"])  # the load, floating in the feedback path
            u.add(c, "U1", "s", "n", "o")
            out = "v(o)-v(n)"
        else:  # instrumentation: vd = 1 V AC split ±0.5 around ground
            c.V("sig", "s", "0", 0.0, 0.5)
            c.V("sigb", "sb", "0", 0.0, -0.5)
            ra = v["R1"]
            c.R("a", "na", "oa", ra)
            c.R("g", "na", "nb", v["RG"])
            c.R("b", "nb", "ob", ra)
            ops[0].add(c, "U1", "s", "na", "oa")
            ops[1].add(c, "U2", "sb", "nb", "ob")
            c.R("3", "ob", "n", v["R3"])
            c.R("4", "n", "o", v["R4"])
            c.R("5", "oa", "p", v["R3"])
            c.R("6", "p", "0", v["R4"])
            ops[2].add(c, "U3", "p", "n", "o")
        c.R("L", "o", "0", rl)
        return c, out

    def _ideal(self, s: OpaSpec, v: Mapping[str, float]) -> tuple[float, str, str]:
        """|gain| of the ideal circuit at f_sig, its formula and unit."""
        w = 2 * math.pi * s.f_sig.to_pint().m_as("Hz")
        c = s.config
        if c in ("inversor", "somador"):
            return v["R2"] / v["R1"], r"|A_v| = R_2/R_1", ""
        if c == "subtrator":
            return v["R2"] / v["R1"], r"A_d = R_2/R_1\ (R_4/R_3 = R_2/R_1)", ""
        if c == "nao_inversor":
            return 1 + v["R2"] / v["R1"], r"A_v = 1 + R_2/R_1", ""
        if c == "seguidor":
            return 1.0, r"A_v = 1", ""
        if c == "integrador":
            zf = v["R2"] / (1 + 1j * w * v["R2"] * v["C1"])
            return abs(zf / v["R1"]), r"|A_v| = \frac{R_f/R_1}{\sqrt{1 + (\omega R_f C)^2}}", ""
        if c == "diferenciador":
            zin = v["R1"] + 1 / (1j * w * v["C1"])
            return abs(v["R2"] / zin), r"|A_v| = \frac{R_f}{|R_s + 1/(j\omega C)|}", ""
        if c == "transimpedancia":
            return v["R2"], r"|v_o/i_i| = R_f", "ohm"
        if c == "transcondutancia":
            return v["R2"] / v["R1"], r"i_L = v_i/R_1,\ v_{RL} = v_i R_L/R_1", ""
        return (1 + 2 * v["R1"] / v["RG"]) * v["R4"] / v["R3"], r"A_v = (1 + 2R/R_G)\,R_4/R_3", ""

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vcc = s.VCC.to_pint().m_as("V")
        fsig = s.f_sig.to_pint().m_as("Hz")
        v = self._values(s, log)
        ops: list[OpAmp] = []
        for k in range(self._n_opamps(s)):
            d = f"U{k + 1}"
            m, w = opamp_model(devices[d].record, vcc, -vcc, log, d)
            ops.append(m)
            warnings += [DesignWarning(code="modelo", message=x) for x in w]
        av_id, formula, unit = self._ideal(s, v)
        log.add(
            record(
                "Av_ideal",
                "Ganho com ampop ideal (valores comerciais)",
                formula,
                output=Q_(av_id, unit),
                inputs={k: Q_(x, "F" if k == "C1" else "ohm") for k, x in v.items()},
                reference=REF,
            )
        )
        c, out = self.circuit(s, v, ops)
        f = log_grid(F1, F2, PPD)
        nodes = ["o", "n"] if out != "v(o)" else ["o"]
        resp = c.ac(f, nodes)
        h = resp["o"] - (resp["n"] if out != "v(o)" else 0)
        mag = np.abs(h)
        hs = c.ac(np.array([fsig]), nodes)
        av = float(abs(hs["o"][0] - (hs["n"][0] if out != "v(o)" else 0)))
        sol = "análise nodal exata com o modelo do ampop (A0, GBW, Rin)"
        log.add(
            record(
                "Av",
                "Ganho na frequência do sinal com o ampop real",
                r"|A_v| = \left|\frac{v_o}{v_i}\right|_{f}",
                output=Q_(av, unit),
                inputs={"f": s.f_sig.to_pint()},
                assumptions=[sol],
                reference=REF,
            )
        )
        f_h = corner(f, mag, "fh")
        f_l = corner(f, mag, "fl") if s.config in ("diferenciador",) else None
        u = ops[0]
        beta_txt = r"|A_v(f_H)| = |A_v|_{max}/\sqrt{2}"
        if f_h is not None:
            log.add(
                record(
                    "f_H",
                    "Frequência de corte superior (curva de ganho)",
                    beta_txt,
                    output=Q_(f_h, "Hz").to("kHz"),
                    inputs={"GBW": Q_(u.GBW, "Hz").to("MHz")},
                    assumptions=[sol, "lido na curva (−3 dB do máximo)"],
                    reference=REF,
                )
            )
        # DC output error with the input at zero (VOS and bias currents)
        vdc, _ = c.op()
        vo_dc = vdc["o"] - (vdc["n"] if out != "v(o)" else 0.0)
        log.add(
            record(
                "Vo_dc",
                "Saída com a entrada nula",
                r"V_{o,CC} = f(V_{OS}, I_B, I_{OS})",
                output=Q_(vo_dc, "V").to("mV"),
                inputs={
                    "V_{OS}": Q_(u.Vos, "V").to("mV"),
                    "I_B": Q_(u.Ib, "A").to("nA"),
                    "I_{OS}": Q_(u.Ios, "A").to("nA"),
                },
                assumptions=[sol, "valores típicos; o sinal de VOS e IOS da peça é aleatório"],
                reference=REF,
            )
        )
        amp_in = (
            s.Iin.to_pint().m_as("A")
            if s.config == "transimpedancia"
            else s.Vin.to_pint().m_as("V")
        )
        vo_pk = av * amp_in
        if s.config == "transcondutancia":
            vo_pk = abs(hs["o"][0]) * amp_in  # op-amp output, not the load voltage
        vo_pk_total = vo_pk + abs(vo_dc)
        sr_req = 2 * math.pi * fsig * vo_pk
        log.add(
            record(
                "SR_req",
                "Taxa de inclinação exigida pela senoide de saída",
                r"SR_{req} = 2\pi f V_{o,p}",
                output=Q_(sr_req, "V/s").to("V/us"),
                inputs={"f": s.f_sig.to_pint(), "V_{o,p}": Q_(vo_pk, "V")},
                reference=REF,
            )
        )
        if vo_pk_total > min(u.v_hi, -u.v_lo):
            warnings.append(
                DesignWarning(
                    code="excursao",
                    message=f"A saída ({vo_pk_total:.3g} V de pico) passa da excursão do ampop "
                    f"({min(u.v_hi, -u.v_lo):.3g} V): vai ceifar.",
                )
            )
        if sr_req > u.SR:
            warnings.append(
                DesignWarning(
                    code="slew",
                    message=f"A senoide de saída exige {sr_req / 1e6:.3g} V/µs e o ampop dá "
                    f"{u.SR / 1e6:.3g} V/µs: haverá distorção por taxa de inclinação.",
                )
            )
        flat = ("inversor", "nao_inversor", "somador", "subtrator", "instrumentacao")
        if s.config in flat and abs(av / av_id - 1) > 0.05:
            warnings.append(
                DesignWarning(
                    code="banda",
                    message="O ganho na frequência do sinal difere mais de 5 % do ideal: "
                    "GBW do ampop insuficiente para esse ganho.",
                )
            )
        summary: dict[str, pint.Quantity] = {
            "Av_ideal": Q_(av_id, unit),
            "Av": Q_(av, unit),
            "gain_err": Q_((av / av_id - 1) * 100, "percent"),
            "Vo_dc": Q_(vo_dc, "V").to("mV"),
            "Vo_pk": Q_(vo_pk, "V"),
            "Vo_max": Q_(u.v_hi, "V"),
            "SR_req": Q_(sr_req, "V/s").to("V/us"),
        }
        if math.isfinite(u.SR) and vo_pk > 0:
            summary["f_pmax"] = Q_(u.SR / (2 * math.pi * vo_pk), "Hz").to("kHz")
        if f_h is not None:
            summary["f_H"] = Q_(f_h, "Hz").to("kHz")
        if f_l is not None:
            summary["f_L"] = Q_(f_l, "Hz")
        for key, x in v.items():
            summary[key] = Q_(x, "F").to("nF") if key == "C1" else Q_(x, "ohm")
        if s.config == "transcondutancia":
            summary["IL_pk"] = Q_(amp_in / v["R1"], "A").to("mA")
        rin = {
            "inversor": v.get("R1"),
            "somador": v.get("R1"),
            "subtrator": (v.get("R3", 0) + v.get("R4", 0)),
        }.get(s.config)
        if rin:
            summary["Rin"] = Q_(rin, "ohm")
        # waveforms over one period (linear: DC + phasor)
        th = np.linspace(0, 2 * math.pi, 720, endpoint=False)
        hph = hs["o"][0] - (hs["n"][0] if out != "v(o)" else 0)
        vin_w = amp_in * np.sin(th)
        vo_w = vo_dc + amp_in * abs(hph) * np.sin(th + np.angle(hph))
        vo_w = np.clip(vo_w, u.v_lo, u.v_hi)
        traces = {
            ("Corrente de entrada" if s.config == "transimpedancia" else "Entrada"): make_trace(
                "A" if s.config == "transimpedancia" else "V", vin_w
            ),
            "Saída": make_trace("V", vo_w),
        }
        stresses: list[Stress] = []  # supply limit checked in accepts
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={},
            warnings=warnings,
            convergence_keys=("Av",),
            traces=traces,
            trace_period=Q_(1 / fsig, "s"),
            bode_f=Trace(unit="Hz", values=[float(x) for x in f]),
            bode={"Ganho": Trace(unit="", values=[float(x) for x in mag])},
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        log = CalcLog()
        vcc = s.VCC.to_pint().m_as("V")
        v = self._values(s, log)
        ops = [
            opamp_model(devices[f"U{k + 1}"].record, vcc, -vcc, log, f"U{k + 1}")[0]
            for k in range(self._n_opamps(s))
        ]
        c, out = self.circuit(s, v, ops)
        vdc, _ = c.op()
        lines = []
        for line in c.netlist():
            if line.startswith("C"):  # start the DC run at the DC solution
                _, a, b, _val = line.split()
                line += f" IC={vdc.get(a, 0.0) - vdc.get(b, 0.0):.12g}"
            lines.append(line)
        fsig = s.f_sig.to_pint().m_as("Hz")
        checks = [
            SimCheck(
                quantity="Saída com entrada nula",
                summary_key="Vo_dc",
                metric="avg",
                probe=out,
                tolerance_pct=1.0,
                justification="mesmo modelo (.tran a partir da solução CC)",
            ),
            SimCheck(
                quantity="Ganho na frequência do sinal",
                summary_key="Av",
                metric="ac_mag",
                probe=out,
                freq=fsig,
                tolerance_pct=0.5,
                justification="mesmo circuito linear (.ac)",
            ),
        ]
        if "f_H" in summary:
            checks.append(
                SimCheck(
                    quantity="Frequência de corte superior",
                    summary_key="f_H",
                    metric="ac_fh",
                    probe=out,
                    tolerance_pct=1.0,
                    justification="interpolação na grade de 20 pontos/década",
                )
            )
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[s.config]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=SIM_RUN, unit="s"),
            tran_step=QuantityModel(value=SIM_RUN / 100, unit="s"),
            period=QuantityModel(value=SIM_RUN / 2, unit="s"),
            checks=checks,
            ac_start=QuantityModel(value=F1, unit="Hz"),
            ac_stop=QuantityModel(value=F2, unit="Hz"),
            ac_points_per_decade=PPD,
            bode_probes={"Ganho": out},
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        parts = {c.designator: c.part_number for c in result.selection}
        sm = result.summary

        def val(k: str) -> str:
            return format_eng(sm[k].to_pint()) if k in sm else ""

        svg = Svg(600, 300)
        svg.title(title)
        cfg = s.config
        if cfg == "instrumentacao":
            i1, p1, o1 = svg.opamp(160, 80, "U1", parts.get("U1", ""), flip=True)
            i2, p2, o2 = svg.opamp(160, 220, "U2", parts.get("U2", ""), flip=True)
            i3, p3, o3 = svg.opamp(400, 150, "U3", parts.get("U3", ""))
            svg.wire((60, p1[1]), p1)
            svg.terminal(56, p1[1], "v1", "end")
            svg.wire((60, p2[1]), p2)
            svg.terminal(56, p2[1], "v2", "end")
            svg.wire(i1, (140, i1[1]), (140, 125))
            svg.resistor_v(140, 125, 175, "RG", val("RG"))
            svg.wire((140, 175), (140, i2[1]), i2)
            svg.resistor_h(140, o1[0], 125, "R", val("R1"))
            svg.wire(o1, (o1[0], 125))
            svg.resistor_h(140, o2[0], 175, "R", val("R1"))
            svg.wire(o2, (o2[0], 175))
            svg.resistor_h(o1[0], i3[0], 80, "R3", val("R3"))
            svg.wire((i3[0], 80), i3)
            svg.resistor_h(o2[0], p3[0], 220, "R3", val("R3"))
            svg.wire((p3[0], 220), p3)
            svg.terminal(o3[0] + 40, o3[1], "vo")
            svg.wire(o3, (o3[0] + 36, o3[1]))
            return svg.render(title)
        inv, non, o = svg.opamp(260, 150, "U1", parts.get("U1", ""))
        svg.wire(o, (440, o[1]))
        svg.resistor_v(440, o[1], 260, "RL", format_eng(s.RL.to_pint()))
        svg.ground(440, 260)
        svg.terminal(470, o[1], "vo")
        svg.wire((440, o[1]), (466, o[1]))
        # feedback
        fb_y = 80
        if cfg in ("nao_inversor", "seguidor", "transcondutancia"):
            svg.wire((60, non[1]), non)
            svg.ac_source(60, non[1], 260, "vi")
            svg.ground(60, 260)
            if cfg == "seguidor":
                svg.wire(inv, (230, inv[1]), (230, fb_y), (o[0] + 20, fb_y), (o[0] + 20, o[1]))
                return svg.render(title)
            svg.wire(inv, (200, inv[1]))
            svg.resistor_v(200, inv[1], 260, "R1", val("R1"))
            svg.ground(200, 260)
            svg.wire((200, inv[1]), (200, fb_y))
            lbl = "RL (carga)" if cfg == "transcondutancia" else "R2"
            svg.resistor_h(200, o[0] + 20, fb_y, lbl, val("R2"))
            svg.wire((o[0] + 20, fb_y), (o[0] + 20, o[1]))
            return svg.render(title)
        # inverting family: input element(s) to the inverting node
        svg.wire(inv, (200, inv[1]))
        if cfg == "transimpedancia":
            svg.text(110, inv[1] - 8, "ii →")
            svg.wire((90, inv[1]), (200, inv[1]))
        elif cfg == "diferenciador":
            svg.resistor_h(60, 120, inv[1], "Rs", val("R1"))
            svg.cap_h(120, 200, inv[1], "C", val("C1"))
        else:
            svg.resistor_h(60, 200, inv[1], "R1", val("R1"))
        if cfg not in ("transimpedancia",):
            svg.terminal(56, inv[1], "vi", "end")
        if cfg == "somador":
            svg.resistor_h(60, 200, inv[1] - 40, "R1b", val("R1"))
            svg.wire((200, inv[1] - 40), (200, inv[1]))
            svg.terminal(56, inv[1] - 40, "vi2", "end")
        svg.wire((200, inv[1]), (200, fb_y))
        svg.resistor_h(200, o[0] + 20, fb_y, "R2", val("R2"))
        if cfg == "integrador":
            svg.wire((200, fb_y), (200, fb_y - 40))
            svg.cap_h(200, o[0] + 20, fb_y - 40, "C", val("C1"))
            svg.wire((o[0] + 20, fb_y - 40), (o[0] + 20, fb_y))
        svg.wire((o[0] + 20, fb_y), (o[0] + 20, o[1]))
        if cfg == "subtrator":
            svg.resistor_h(60, 200, non[1], "R3", val("R3"))
            svg.terminal(56, non[1], "v2", "end")
            svg.wire((200, non[1]), non)
            svg.resistor_v(220, non[1], 260, "R4", val("R4"))
            svg.ground(220, 260)
        elif "Rp" in sm:
            svg.wire(non, (230, non[1]))
            svg.resistor_v(230, non[1], 260, "Rp", val("Rp"))
            svg.ground(230, 260)
        else:
            svg.wire(non, (230, non[1]), (230, 260))
            svg.ground(230, 260)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        rows: list[BomRow] = []
        for k in ("R1", "R2", "R3", "R4", "RG", "Rp"):
            r = resistor_row(result, k, k)
            if r:
                rows.append(r)
        if "C1" in result.summary:
            rows.append(
                passive(
                    "C1",
                    "Capacitor (filme ou cerâmico C0G)",
                    format_eng(result.summary["C1"].to_pint()),
                )
            )
        return rows
