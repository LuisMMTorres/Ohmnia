"""DM-PA: power amplifiers, class A (series-fed) and class B / AB (complementary push-pull).

Boylestad & Nashelsky, *Electronic Devices and Circuit Theory*, 11th ed., ch. 12 "Power
amplifiers": series-fed class A (Pi = VCC·ICQ, Po = Ic,p²·RC/2, η ≤ 25 %) and the
complementary-symmetry class B (Po = Vp²/2RL, Pi = 2·VCC·Vp/(π·RL), P2Q = Pi − Po, η = π/4 ·
Vp/VCC, PQ,max = 2VCC²/(π²RL) for both transistors).

Those textbook formulas assume ideal switching transistors. The module also solves the
push-pull quasi-statically with the exponential junctions of both transistors (the same
equations SPICE solves at each time step, no capacitances), which gives the crossover
distortion of class B, its reduction in class AB, and the exact powers; the simulation is
compared with this solution. Class AB is biased by an ideal source VBB between the bases (in
practice two diodes or a VBE multiplier, not designed here).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pint
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from scipy.optimize import brentq

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
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
from circuitos.design.devmodels import BOYLESTAD, VT_300K, Bjt, bjt_model, hfe_entries, quantity
from circuitos.design.engine import Analysis, Device
from circuitos.reports.common import BomRow, LabItem, passive
from circuitos.reports.schematic import Svg

Cls = Literal["A", "B", "AB"]
REF = BOYLESTAD.model_copy(update={"chapter": "12 (Power amplifiers)"})
N = 4096  # samples per period of the quasi-static solution (same grid as the THD of verify)


class PaSpec(BaseModel):
    cls: Cls = "AB"
    VCC: QuantityModel = QuantityModel(value=15, unit="V")  # each rail (B/AB), the supply (A)
    RL: QuantityModel = QuantityModel(value=8, unit="ohm")
    Po: QuantityModel = QuantityModel(value=5, unit="W")  # desired output power (sine)
    IQ: QuantityModel = QuantityModel(value=20, unit="mA")  # class AB quiescent current
    f_sig: QuantityModel = QuantityModel(value=1, unit="kHz")
    VBE: QuantityModel = QuantityModel(value=0.7, unit="V")
    beta_ideal: float = Field(default=50, gt=1, le=2000)
    TA: QuantityModel = QuantityModel(value=40, unit="degC")
    Rth_cs: QuantityModel = QuantityModel(value=0.5, unit="K/W")


LABELS = {
    "Vp": "Amplitude da tensão na carga",
    "Ip": "Amplitude da corrente na carga",
    "Po": "Potência na carga",
    "Pi": "Potência da fonte",
    "P_Q": "Potência por transistor",
    "P_Q_max": "Potência máxima por transistor (pior amplitude)",
    "eff": "Rendimento",
    "THD": "Distorção harmônica total da saída",
    "ICQ": "Corrente de polarização",
    "VCEQ": "VCE de polarização",
    "Vin_pk": "Amplitude da excitação de base",
    "VBB": "Tensão de polarização entre as bases (AB)",
    "Po_ideal": "Po pela fórmula do livro",
    "Pi_ideal": "Pi pela fórmula do livro",
    "eff_ideal": "η pela fórmula do livro",
    "Vo_rms": "Tensão eficaz na carga",
    "IC_avg": "Corrente média de coletor de Q1",
}
SPEC_LABELS = {
    "cls": "Classe",
    "VCC": "Alimentação (por trilho em B/AB)",
    "RL": "Carga (alto-falante)",
    "Po": "Potência de saída desejada",
    "IQ": "Corrente quiescente (AB)",
    "f_sig": "Frequência do sinal",
    "VBE": "VBE na corrente de ensaio (premissa)",
    "beta_ideal": "β de projeto (passo ideal)",
}
ENUM_LABELS = {
    "A": "classe A (alimentação série)",
    "B": "classe B (push-pull complementar)",
    "AB": "classe AB (push-pull complementar)",
}


def _spec(spec: BaseModel) -> PaSpec:
    if not isinstance(spec, PaSpec):
        raise TypeError("DM-PA espera PaSpec")
    return spec


def _harm(x: NDArray[np.float64]) -> NDArray[np.float64]:
    spec = np.fft.rfft(x) / x.size
    amp = np.abs(spec[:51])
    amp[1:] *= 2
    return np.asarray(amp)


def push_pull(
    qn: Bjt, qp: Bjt, vb_n: NDArray[np.float64], vb_p: NDArray[np.float64], rl: float
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Output voltage and collector currents of the complementary follower (quasi-static)."""
    vo = np.empty_like(vb_n)
    icn = np.empty_like(vb_n)
    icp = np.empty_like(vb_n)

    def ie_n(v: float) -> float:
        return qn.IS * math.expm1(min(v / VT_300K, 200.0)) * (1 + 1 / qn.BF)

    def ie_p(v: float) -> float:
        return qp.IS * math.expm1(min(v / VT_300K, 200.0)) * (1 + 1 / qp.BF)

    for k, (bn, bp) in enumerate(zip(vb_n, vb_p, strict=True)):

        def residual(v: float, bn: float = bn, bp: float = bp) -> float:
            return ie_n(bn - v) - ie_p(v - bp) - v / rl

        lo, hi = min(bn, bp) - 2.0, max(bn, bp) + 2.0
        v = brentq(residual, lo, hi, xtol=1e-13)
        vo[k] = v
        icn[k] = qn.IS * math.expm1(min((bn - v) / VT_300K, 200.0))
        icp[k] = qp.IS * math.expm1(min((v - bp) / VT_300K, 200.0))
    return vo, icn, icp


class PaModule:
    id = "DM-PA"
    family = "amplificadores"
    title = "Amplificador de potência"
    spec_schema = PaSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão eficaz na carga", "multímetro true RMS", "Vo_rms"),
        LabItem("Potência na carga", "a partir da tensão eficaz", "Po"),
        LabItem("Corrente da fonte", "multímetro em série", "IC_avg"),
        LabItem("Distorção harmônica", "analisador de espectro / FFT do osciloscópio", "THD"),
    ]
    questions = [
        "Por que o rendimento da classe A não passa de 25 % com carga resistiva?",
        "Observe a distorção de cruzamento na classe B. Por que ela fica pior com sinal pequeno?",
        "Qual amplitude maximiza a dissipação nos transistores do push-pull? Confirme com a "
        "temperatura do dissipador.",
    ]
    practice = {
        "objective": "Medir potência, rendimento e distorção do estágio de saída e comparar "
        "classes de operação.",
        "material": "Fonte simétrica com limite de corrente, gerador, osciloscópio com FFT, "
        "resistor de carga de potência (no lugar do alto-falante), dissipadores.",
        "procedure": [
            "Fixe os transistores nos dissipadores antes de energizar.",
            "Sem sinal, meça a corrente quiescente (classe AB: ajuste a polarização).",
            "Aplique a senoide e aumente até a amplitude de projeto, sem ceifar.",
            "Meça a tensão na carga e a corrente média das fontes; calcule Po, Pi e η.",
            "Registre o espectro da saída e calcule a THD; compare B com AB.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        roles = [Role(designator="Q1", category="bjt.npn", description="Transistor de saída NPN")]
        if s.cls != "A":
            roles.append(
                Role(designator="Q2", category="bjt.pnp", description="Transistor de saída PNP")
            )
        return roles

    def required_ratings(self, role: Role) -> list[str]:
        return ["VCEO", "IC"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).Rth_cs.to_pint()

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        # a Darlington (hFE in the thousands) is not one junction: the model would not fit it
        return bool(hfe_entries(rec)) and all((p.min or 0) < 500 for _, p in hfe_entries(rec))

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        q = quantity(rec, "IC", ("max",))
        return float(q.m_as("A")) if q is not None else 0.0

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        if s.cls == "A":
            return self._class_a(s, devices)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vcc = s.VCC.to_pint().m_as("V")
        rl = s.RL.to_pint().m_as("ohm")
        po = s.Po.to_pint().m_as("W")
        vp = log.add(
            record(
                "Vp",
                "Amplitude na carga para a potência desejada",
                r"V_p = \sqrt{2 P_o R_L}",
                output=Q_(math.sqrt(2 * po * rl), "V"),
                inputs={"P_o": s.Po.to_pint(), "R_L": s.RL.to_pint()},
                reference=REF,
            )
        ).m_as("V")
        ip = vp / rl
        if vp > vcc - 1.0:
            warnings.append(
                DesignWarning(
                    code="excursao",
                    message=f"Vp = {vp:.3g} V deixa menos de 1 V de VCE nos picos; "
                    "o transistor satura. Aumente VCC.",
                )
            )
        qn, w1 = bjt_model(devices["Q1"].record, ip, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
        qp, w2 = bjt_model(devices["Q2"].record, ip, s.VBE.to_pint(), s.beta_ideal, log, "Q2")
        warnings += [DesignWarning(code="modelo", message=x) for x in w1 + w2]
        # textbook (ideal) formulas
        pi_id = 2 * vcc * vp / (math.pi * rl)
        log.add(
            record(
                "Po_ideal",
                "Potência na carga (fórmula)",
                r"P_o = \frac{V_p^2}{2 R_L}",
                output=Q_(vp**2 / (2 * rl), "W"),
                inputs={"V_p": Q_(vp, "V"), "R_L": s.RL.to_pint()},
                reference=REF,
            )
        )
        log.add(
            record(
                "Pi_ideal",
                "Potência das fontes (fórmula, classe B ideal)",
                r"P_i = \frac{2 V_{CC} V_p}{\pi R_L}",
                output=Q_(pi_id, "W"),
                inputs={"V_{CC}": s.VCC.to_pint(), "V_p": Q_(vp, "V")},
                reference=REF,
            )
        )
        log.add(
            record(
                "eff_ideal",
                "Rendimento (fórmula)",
                r"\eta = \frac{\pi}{4}\frac{V_p}{V_{CC}}",
                output=Q_(math.pi / 4 * vp / vcc * 100, "percent"),
                inputs={"V_p": Q_(vp, "V"), "V_{CC}": s.VCC.to_pint()},
                reference=REF,
            )
        )
        pq_max = log.add(
            record(
                "P_Q_max",
                "Dissipação máxima por transistor (amplitude 2VCC/π)",
                r"P_{Q,max} = \frac{V_{CC}^2}{\pi^2 R_L}",
                output=Q_(vcc**2 / (math.pi**2 * rl), "W"),
                inputs={"V_{CC}": s.VCC.to_pint(), "R_L": s.RL.to_pint()},
                assumptions=["metade de 2V_CC²/(π²R_L) dos dois transistores"],
                reference=REF,
            )
        )
        # drive: base voltages; AB bias VBB/2 per transistor sets IQ
        vbn0 = vbp0 = 0.0
        if s.cls == "AB":
            iq = s.IQ.to_pint().m_as("A")
            vbn0 = qn.vbe(iq)
            vbp0 = -qp.vbe(iq)
            log.add(
                record(
                    "VBB",
                    "Polarização entre as bases para a corrente quiescente",
                    r"V_{BB} = V_{BE,n}(I_Q) + |V_{BE,p}(I_Q)|",
                    output=Q_(vbn0 - vbp0, "V"),
                    inputs={
                        "I_Q": s.IQ.to_pint(),
                        "I_{S,n}": Q_(qn.IS, "A"),
                        "I_{S,p}": Q_(qp.IS, "A"),
                    },
                    assumptions=[
                        "fonte ideal de polarização (diodos ou multiplicador de V_BE na montagem)"
                    ],
                    reference=REF,
                )
            )
        vin_pk = vp + qn.vbe(ip) - vbn0
        log.add(
            record(
                "Vin_pk",
                "Amplitude da excitação para Vp no pico positivo",
                r"v_{in,p} = V_p + V_{BE,n}(I_p) - V_{BB}/2",
                output=Q_(vin_pk, "V"),
                inputs={"V_p": Q_(vp, "V"), "I_p": Q_(ip, "A")},
                reference=REF,
            )
        )
        th = np.linspace(0, 2 * math.pi, N, endpoint=False)
        vin = vin_pk * np.sin(th)
        vo, icn, icp = push_pull(qn, qp, vin + vbn0, vin + vbp0, rl)
        po_x = float(np.mean(vo**2) / rl)
        pi_x = float(vcc * np.mean(icn) + vcc * np.mean(icp))
        pq1 = float(np.mean((vcc - vo) * icn))
        pq2 = float(np.mean((vo + vcc) * icp))
        h = _harm(vo)
        thd = float(np.sqrt(np.sum(h[2:] ** 2)) / h[1] * 100)
        sol = (
            "solução quase estática do push-pull com as junções exponenciais dos dois transistores"
        )
        log.add(
            record(
                "Po",
                "Potência na carga (solução exata)",
                r"P_o = \frac{1}{T}\int_0^T \frac{v_o^2}{R_L}\,dt",
                output=Q_(po_x, "W"),
                assumptions=[sol],
                reference=REF,
            )
        )
        log.add(
            record(
                "Pi",
                "Potência das fontes (solução exata)",
                r"P_i = V_{CC}\,(\bar i_{C1} + \bar i_{C2})",
                output=Q_(pi_x, "W"),
                assumptions=[sol],
                reference=REF,
            )
        )
        log.add(
            record(
                "THD",
                "Distorção harmônica total da tensão na carga",
                r"THD = \frac{\sqrt{\sum_{n\ge 2} V_n^2}}{V_1}",
                output=Q_(thd, "percent"),
                assumptions=[sol, "harmônicas até a 50ª"],
                reference=REF,
            )
        )
        summary: dict[str, pint.Quantity] = {
            "Vp": Q_(float(np.max(vo)), "V"),
            "Ip": Q_(float(np.max(vo)) / rl, "A"),
            "Po": Q_(po_x, "W"),
            "Pi": Q_(pi_x, "W"),
            "P_Q": Q_(max(pq1, pq2), "W"),
            "P_Q_max": pq_max,
            "eff": Q_(po_x / pi_x * 100, "percent"),
            "THD": Q_(thd, "percent"),
            "Vin_pk": Q_(vin_pk, "V"),
            "Po_ideal": Q_(vp**2 / (2 * rl), "W"),
            "Pi_ideal": Q_(pi_id, "W"),
            "eff_ideal": Q_(math.pi / 4 * vp / vcc * 100, "percent"),
            "Vo_rms": Q_(float(np.sqrt(np.mean(vo**2))), "V"),
            "IC_avg": Q_(float(np.mean(icn)), "A"),
        }
        if s.cls == "AB":
            summary["VBB"] = Q_(vbn0 - vbp0, "V")
            summary["ICQ"] = s.IQ.to_pint().to("mA")
        p_dim = max(pq_max.m_as("W"), pq1, pq2)
        stresses = []
        for d in ("Q1", "Q2"):
            stresses += [
                Stress(
                    designator=d,
                    key="VCEO",
                    label="VCE máxima",
                    value=QuantityModel(value=vcc + vp, unit="V"),
                    calc_step_id="Vp",
                ),
                Stress(
                    designator=d,
                    key="IC",
                    label="Corrente de pico",
                    value=QuantityModel(value=ip, unit="A"),
                    calc_step_id="Vp",
                ),
            ]
        step = max(1, N // 720)
        traces = {
            "Tensão na carga": make_trace("V", vo[::step]),
            "Corrente de coletor de Q1": make_trace("A", icn[::step]),
            "Corrente de coletor de Q2": make_trace("A", icp[::step]),
        }
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": Q_(p_dim, "W"), "Q2": Q_(p_dim, "W")},
            warnings=warnings,
            convergence_keys=("Po", "THD"),
            traces=traces,
            trace_period=Q_(1 / s.f_sig.to_pint().m_as("Hz"), "s"),
        )

    def _class_a(self, s: PaSpec, devices: Mapping[str, Device]) -> Analysis:
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vcc = s.VCC.to_pint().m_as("V")
        rl = s.RL.to_pint().m_as("ohm")
        po = s.Po.to_pint().m_as("W")
        icq = log.add(
            record(
                "ICQ",
                "Polarização no meio da reta de carga",
                r"I_{CQ} = \frac{V_{CC}}{2 R_C}",
                output=Q_(vcc / (2 * rl), "A"),
                inputs={"V_{CC}": s.VCC.to_pint(), "R_C": s.RL.to_pint()},
                assumptions=["a carga é o próprio R_C (alimentação série)"],
                reference=REF,
            )
        ).m_as("A")
        ic_pk = math.sqrt(2 * po / rl)
        if ic_pk > icq:
            ic_pk = icq * 0.95
            warnings.append(
                DesignWarning(
                    code="excursao",
                    message=f"A potência pedida passa do máximo da classe A com "
                    f"esta alimentação ({icq**2 * rl / 2:.3g} W); o projeto usa 95 % de ICQ.",
                )
            )
        log.add(
            record(
                "Ip",
                "Amplitude da corrente de coletor",
                r"I_{c,p} = \sqrt{2 P_o / R_C}",
                output=Q_(ic_pk, "A"),
                inputs={"P_o": s.Po.to_pint(), "R_C": s.RL.to_pint()},
                reference=REF,
            )
        )
        q, w = bjt_model(devices["Q1"].record, icq, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
        warnings += [DesignWarning(code="modelo", message=x) for x in w]
        ibq = icq / q.BF
        log.add(
            record(
                "IBQ",
                "Corrente de base de polarização (excitação por corrente)",
                r"I_{BQ} = I_{CQ}/\beta",
                output=Q_(ibq, "A").to("mA"),
                inputs={r"\beta": Q_(q.BF, "")},
                reference=REF,
            )
        )
        pi = vcc * icq
        po_x = ic_pk**2 * rl / 2
        pq = pi - po_x - icq**2 * rl
        log.add(
            record(
                "Po",
                "Potência CA na carga",
                r"P_o = \frac{I_{c,p}^2 R_C}{2}",
                output=Q_(po_x, "W"),
                inputs={"I_{c,p}": Q_(ic_pk, "A")},
                reference=REF,
            )
        )
        log.add(
            record(
                "Pi",
                "Potência da fonte",
                r"P_i = V_{CC} I_{CQ}",
                output=Q_(pi, "W"),
                inputs={"V_{CC}": s.VCC.to_pint(), "I_{CQ}": Q_(icq, "A")},
                reference=REF,
            )
        )
        log.add(
            record(
                "P_Q",
                "Potência no transistor",
                r"P_Q = P_i - P_o - I_{CQ}^2 R_C",
                output=Q_(pq, "W"),
                assumptions=["R_C dissipa também a parcela CC"],
                reference=REF,
            )
        )
        th = np.linspace(0, 2 * math.pi, 720, endpoint=False)
        ic = icq + ic_pk * np.sin(th)
        vce = vcc - ic * rl
        summary: dict[str, pint.Quantity] = {
            "ICQ": Q_(icq, "A"),
            "VCEQ": Q_(vcc - icq * rl, "V"),
            "Ip": Q_(ic_pk, "A"),
            "Vp": Q_(ic_pk * rl, "V"),
            "Po": Q_(po_x, "W"),
            "Pi": Q_(pi, "W"),
            "P_Q": Q_(pq, "W"),
            "eff": Q_(po_x / pi * 100, "percent"),
            "IC_avg": Q_(icq, "A"),
            "Vo_rms": Q_(ic_pk * rl / math.sqrt(2), "V"),
        }
        stresses = [
            Stress(
                designator="Q1",
                key="VCEO",
                label="VCE máxima",
                value=QuantityModel(value=vcc, unit="V"),
                calc_step_id="ICQ",
            ),
            Stress(
                designator="Q1",
                key="IC",
                label="Corrente de pico",
                value=QuantityModel(value=icq + ic_pk, unit="A"),
                calc_step_id="Ip",
            ),
        ]
        traces = {
            "VCE de Q1": make_trace("V", vce),
            "Corrente de coletor de Q1": make_trace("A", ic),
        }
        # the transistor dissipates most with no signal: P = VCEQ·ICQ
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": Q_(pi - icq**2 * rl, "W")},
            warnings=warnings,
            convergence_keys=("ICQ", "Po"),
            traces=traces,
            trace_period=Q_(1 / s.f_sig.to_pint().m_as("Hz"), "s"),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        log = CalcLog()
        vcc = s.VCC.to_pint().m_as("V")
        rl = s.RL.to_pint().m_as("ohm")
        f = s.f_sig.to_pint().m_as("Hz")
        if s.cls == "A":
            icq = summary["ICQ"].to_pint().m_as("A")
            q, _ = bjt_model(devices["Q1"].record, icq, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
            ip = summary["Ip"].to_pint().m_as("A")
            lines = [
                q.spice("QA"),
                f"VCC vcc 0 DC {vcc:.9g}",
                f"RL vcc c {rl:.9g}",
                "VSC c cq 0",
                "Q1 cq b 0 QA",
                f"IB 0 b DC 0 SIN({icq / q.BF:.9g} {ip / q.BF:.9g} {f:.9g})",
            ]
            checks = [
                SimCheck(
                    quantity="Corrente média de coletor",
                    summary_key="IC_avg",
                    metric="avg",
                    probe="i(vsc)",
                    tolerance_pct=0.5,
                    justification="mesmo modelo; excitação por corrente de base",
                ),
                SimCheck(
                    quantity="Tensão eficaz na carga (CA)",
                    summary_key="Vo_rms",
                    metric="rms",
                    probe=f"v(c)-{vcc - icq * rl:.9g}*v(one)",
                    tolerance_pct=1.0,
                    justification="mesmo modelo",
                ),
            ]
            lines.append("VONE one 0 DC 1")
            probes = {"VCE de Q1": "v(c)", "Corrente de coletor de Q1": "i(vsc)"}
        else:
            ip = summary["Ip"].to_pint().m_as("A")
            qn, _ = bjt_model(devices["Q1"].record, ip, s.VBE.to_pint(), s.beta_ideal, log, "Q1")
            qp, _ = bjt_model(devices["Q2"].record, ip, s.VBE.to_pint(), s.beta_ideal, log, "Q2")
            vin = summary["Vin_pk"].to_pint().m_as("V")
            vbb = summary["VBB"].to_pint().m_as("V") if "VBB" in summary else 0.0
            vbn = qn.vbe(s.IQ.to_pint().m_as("A")) if s.cls == "AB" else 0.0
            lines = [
                qn.spice("QN"),
                qp.spice("QP"),
                f"VCC vcc 0 DC {vcc:.9g}",
                f"VEE vee 0 DC {-vcc:.9g}",
                f"VIN in 0 SIN(0 {vin:.9g} {f:.9g})",
                f"VBN bn in DC {vbn:.9g}",
                f"VBP in bp DC {vbb - vbn:.9g}",
                "VSN vcc cn 0",
                "VSP cp vee 0",
                "Q1 cn bn o QN",
                "Q2 cp bp o QP",
                f"RL o 0 {rl:.9g}",
            ]
            checks = [
                SimCheck(
                    quantity="Tensão eficaz na carga",
                    summary_key="Vo_rms",
                    metric="rms",
                    probe="v(o)",
                    tolerance_pct=0.5,
                    justification="mesmo modelo",
                ),
                SimCheck(
                    quantity="Corrente média de Q1",
                    summary_key="IC_avg",
                    metric="avg",
                    probe="i(vsn)",
                    tolerance_pct=1.0,
                    justification="mesmo modelo",
                ),
                SimCheck(
                    quantity="THD da tensão na carga",
                    summary_key="THD",
                    metric="thd",
                    probe="v(o)",
                    tolerance_pct=5.0,
                    justification="mesmo modelo; a THD pequena é sensível ao passo",
                ),
            ]
            probes = {
                "Tensão na carga": "v(o)",
                "Corrente de coletor de Q1": "i(vsn)",
                "Corrente de coletor de Q2": "i(vsp)",
            }
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[s.cls]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=3 / f, unit="s"),
            tran_step=QuantityModel(value=1 / f / 4000, unit="s"),
            period=QuantityModel(value=1 / f, unit="s"),
            probes=probes,
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        parts = {c.designator: c.part_number for c in result.selection}
        svg = Svg(520, 330)
        svg.title(title)
        rl = format_eng(s.RL.to_pint())
        if s.cls == "A":
            svg.wire((200, 50), (360, 50))
            svg.terminal(360, 50, f"VCC = {s.VCC.value:g} V")
            svg.resistor_v(268, 50, 120, "RL", rl)
            b, c, e = svg.bjt(260, 160, "Q1", parts.get("Q1", ""))
            svg.wire((268, 120), c)
            svg.wire(e, (e[0], 280))
            svg.wire(b, (150, 160))
            svg.terminal(146, 160, "iB = IBQ + ib", "end")
            svg.ground(268, 280)
            return svg.render(title)
        svg.terminal(300, 40, f"+{s.VCC.value:g} V")
        svg.terminal(300, 300, f"−{s.VCC.value:g} V")
        bn, cn, en = svg.bjt(292, 110, "Q1", parts.get("Q1", ""))
        bp, cp, ep = svg.bjt(292, 230, "Q2", parts.get("Q2", ""), pnp=True)
        svg.wire(cn, (cn[0], 40), (296, 40))
        svg.wire(cp, (cp[0], 300), (296, 300))
        svg.wire(en, (en[0], 170), ep)
        svg.dot(en[0], 170)
        svg.wire((en[0], 170), (420, 170))
        svg.resistor_v(420, 170, 280, "RL", rl)
        svg.ground(420, 280)
        if s.cls == "AB":
            svg.battery_v(200, bn[1], 170, "VBB/2")
            svg.battery_v(200, 170, bp[1], "VBB/2")
        else:
            svg.wire((200, bn[1]), (200, bp[1]))
        svg.wire(bn, (200, bn[1]))
        svg.wire(bp, (200, bp[1]))
        svg.ac_source(120, 170, 280, "vin")
        svg.wire((120, 170), (200, 170))
        svg.ground(120, 280)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        rows = [
            passive(
                "RL",
                "Carga (alto-falante ou resistor de potência)",
                format_eng(s.RL.to_pint()),
                f"P ≥ {format_eng(result.summary['Po'].to_pint())}",
            )
        ]
        if s.cls == "AB":
            rows.append(
                passive(
                    "VBB",
                    "Polarização entre as bases",
                    format_eng(result.summary["VBB"].to_pint()),
                    "dois diodos em série ou multiplicador de VBE, ajustar IQ",
                )
            )
        return rows
