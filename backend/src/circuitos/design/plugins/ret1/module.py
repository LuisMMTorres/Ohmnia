"""DM-RET1 design module: specification → transformer, filter, diodes, margins, Tj."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pint
from pydantic import BaseModel, Field
from scipy.optimize import brentq

from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.eseries import snap
from circuitos.core.units import Q_, QuantityModel
from circuitos.design.base import Circuit, DesignWarning, Role, SimCheck, Stress
from circuitos.design.engine import Analysis, Device

from . import model as m
from .model import Filter, Topology

HART_HW = BibRef(book="Hart, Power Electronics", edition="1st", chapter="3 (Half-wave rectifiers)")
HART_FW = BibRef(book="Hart, Power Electronics", edition="1st", chapter="4 (Full-wave rectifiers)")

TOPOLOGY_LABEL = {
    "meia_onda": "meia onda",
    "center_tap": "onda completa com derivação central",
    "ponte": "onda completa em ponte",
}
FILTER_LABEL = {
    "nenhum": "sem filtro",
    "C": "filtro capacitivo",
    "LC": "filtro LC",
    "pi": "filtro π",
}


class Ret1Spec(BaseModel):
    topology: Topology = "ponte"
    filter: Filter = "C"
    Vin: QuantityModel = QuantityModel(value=127, unit="V")  # primary, RMS
    f: QuantityModel = QuantityModel(value=60, unit="Hz")
    Vo: QuantityModel = QuantityModel(value=12, unit="V")  # mean output
    Io: QuantityModel = QuantityModel(value=1, unit="A")  # mean load current
    ripple_pct: float = Field(default=5.0, gt=0, le=50)  # peak-to-peak, % of Vo
    L_factor: float = Field(default=2.0, ge=1.0, le=20)  # L = factor · Lcrit (LC filter)
    cap_series: Literal["E3", "E6", "E12"] = "E6"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")
    Rth_cs: QuantityModel = QuantityModel(value=0.5, unit="K/W")


def _ref(topology: Topology) -> BibRef:
    return HART_HW if topology == "meia_onda" else HART_FW


class Ret1Module:
    id = "DM-RET1"
    family = "retificadores"
    title = "Retificador monofásico não controlado"
    spec_schema = Ret1Spec

    # ------------------------------------------------------------------ roles
    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        n = m.diode_count(s.topology)
        designator = "D1" if n == 1 else f"D1–D{n}"
        return [
            Role(
                designator=designator, category="diode", description="Diodos retificadores", count=n
            )
        ]

    def required_ratings(self, role: Role) -> list[str]:
        return ["VRRM", "IF(AV)"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).Rth_cs.to_pint()

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        topo, flt = s.topology, s.filter
        if flt in ("LC", "pi") and topo == "meia_onda":
            raise ValueError("Filtros LC e π só estão disponíveis para onda completa")
        role = self.roles(s)[0]
        VF = devices[role.designator].drop.m_as("V")
        n_vf = m.diodes_in_path(topo) * VF
        f = s.f.to_pint().m_as("Hz")
        w = 2 * math.pi * f
        Vo = s.Vo.to_pint().m_as("V")
        Io = s.Io.to_pint().m_as("A")
        p = m.pulses(topo)
        ref = _ref(topo)
        if Vo <= 0 or Io <= 0:
            raise ValueError("Vo e Io devem ser positivos")

        R = log.add(
            record(
                "R",
                "Resistência equivalente da carga",
                r"R = \frac{V_o}{I_o}",
                output=Q_(Vo / Io, "ohm"),
                inputs={"V_o": s.Vo.to_pint(), "I_o": s.Io.to_pint()},
                assumptions=["carga resistiva"],
                reference=ref,
            )
        ).m_as("ohm")
        inputs_vf = {"n V_F": Q_(n_vf, "V")}
        summary: dict[str, pint.Quantity] = {}
        C = L = None
        dV_target = s.ripple_pct / 100 * Vo

        if flt == "nenhum":
            Vm = brentq(
                lambda v: m.unfiltered_average(topo, v, VF) - Vo,
                n_vf + 1e-9,
                100 * Vo + 10 * n_vf + 10,
            )
            log.add(
                record(
                    "Vm",
                    "Tensão de pico do secundário",
                    r"V_o = \frac{p}{2\pi}\left[2V_m\cos\theta_1 - nV_F(\pi - 2\theta_1)\right],"
                    r"\quad \theta_1 = \arcsin\frac{nV_F}{V_m}",
                    output=Q_(Vm, "V"),
                    inputs={"V_o": s.Vo.to_pint(), "p": Q_(p, ""), **inputs_vf},
                    assumptions=["diodo como queda constante", "resolvido numericamente para V_m"],
                    reference=ref,
                )
            )
            waves = m.unfiltered(topo, Vm, VF, R)
        elif flt in ("C", "pi"):
            dV1 = dV_target if flt == "C" else 4 * dV_target
            C_req = log.add(
                record(
                    "C_req",
                    "Capacitância pela ondulação desejada (aproximação de descarga linear)"
                    + ("" if flt == "C" else ", primeiro capacitor do π"),
                    r"C \ge \frac{I_o}{p\,f\,\Delta V_o}",
                    output=Q_(Io / (p * f * dV1), "F").to("uF"),
                    inputs={
                        "I_o": s.Io.to_pint(),
                        "p": Q_(p, ""),
                        "f": s.f.to_pint(),
                        r"\Delta V_o": Q_(dV1, "V"),
                    },
                    assumptions=["descarga linear do capacitor durante todo o período de ondulação"]
                    + (
                        []
                        if flt == "C"
                        else [
                            "critério de projeto: o primeiro capacitor fica com 4 vezes a "
                            "ondulação final"
                        ]
                    ),
                    reference=ref,
                )
            )
            Cq = snap(C_req, s.cap_series, "up")
            C = log.add(
                record(
                    "C",
                    f"Capacitor comercial (série {s.cap_series}, arredondado para cima)",
                    r"C = \lceil C_{req} \rceil_{" + s.cap_series + "}",
                    output=Cq,
                    inputs={"C_{req}": C_req},
                    reference=ref,
                )
            ).m_as("F")
            cap = float(C)
            if flt == "pi":
                C2 = cap
                L = log.add(
                    record(
                        "L",
                        "Indutor do filtro π (C2 = C1)",
                        r"\Delta V_o \approx \frac{\Delta V_{C1}}{(2\omega)^2 L C_2 - 1}"
                        r"\Rightarrow L = \frac{1 + \Delta V_{C1}/\Delta V_o}{(2\omega)^2\,C_2}",
                        output=Q_((1 + dV1 / dV_target) / ((p * w) ** 2 * C2), "H").to("mH"),
                        inputs={
                            r"\Delta V_{C1}": Q_(dV1, "V"),
                            r"\Delta V_o": Q_(dV_target, "V"),
                            "C_2": Q_(C2, "F").to("uF"),
                        },
                        assumptions=[
                            "atenuação do LC pela harmônica de 2f",
                            "critério de projeto: C2 igual a C1",
                        ],
                        reference=ref,
                    )
                ).m_as("H")
                inductance = float(L)

            def c1_waves(v: float) -> m.Waves:
                if flt == "C":
                    return m.cap_filter(topo, v, VF, R, cap, f)
                return m.pi_filter(topo, v, VF, R, inductance, cap, cap, f)

            Vm = brentq(
                lambda v: m.mean(c1_waves(v).vo) - Vo,
                n_vf + Vo * 0.5,
                n_vf + Vo * 3 + 1,
                xtol=1e-9,
            )
            waves = c1_waves(Vm)
            if flt == "C":
                vm_latex = (
                    r"\omega RC\,V_m\cos\theta_{off} + V_m\sin\theta_{off} = nV_F;\quad "
                    r"v_o(\theta_{off})\,e^{-(\theta_{on} + 2\pi/p - \theta_{off})/\omega RC} = "
                    r"V_m\sin\theta_{on} - nV_F;\quad \overline{v_o} = V_o"
                )
                off_latex = r"\omega RC\,V_m\cos\theta_{off} + V_m\sin\theta_{off} = nV_F"
                discharge = "C descarrega pela carga R (exponencial)"
            else:
                vm_latex = (
                    r"i_D = \omega C_1 V_m\cos\theta + i_L;\ "
                    r"v_{C1} = v_{C1}(\theta_{off}) - \frac{1}{\omega C_1}"
                    r"\int_{\theta_{off}}^{\theta} i_L\,d\theta;\ "
                    r"V_{o,h} = \frac{V_{C1,h}Z_h}{jh\omega L + Z_h};\quad "
                    r"\overline{v_o} = V_o"
                )
                off_latex = r"\omega C_1 V_m\cos\theta_{off} + i_L(\theta_{off}) = 0"
                discharge = (
                    "C1 descarrega pela corrente do indutor; regime periódico por ponto fixo "
                    "entre v_C1 e o estágio L-C2-R"
                )
            log.add(
                record(
                    "Vm",
                    "Tensão de pico do secundário (solução periódica exata do modelo)",
                    vm_latex,
                    output=Q_(Vm, "V"),
                    inputs={
                        "V_o": s.Vo.to_pint(),
                        "R": Q_(R, "ohm"),
                        "C": Q_(cap, "F").to("uF"),
                        r"\omega": Q_(w, "rad/s"),
                        **inputs_vf,
                    },
                    assumptions=[
                        "diodo como queda constante",
                        "fonte e transformador ideais",
                        discharge,
                        "resolvido numericamente",
                    ],
                    reference=ref,
                )
            )
            assert waves.theta_on is not None and waves.theta_off is not None
            log.add(
                record(
                    "theta_on",
                    "Ângulo de início de condução dos diodos",
                    r"v_{C}(\theta_{on}) = V_m\sin\theta_{on} - nV_F",
                    output=Q_(math.degrees(waves.theta_on), "deg"),
                    inputs={},
                    reference=ref,
                )
            )
            log.add(
                record(
                    "theta_off",
                    "Ângulo de fim de condução dos diodos",
                    off_latex,
                    output=Q_(math.degrees(waves.theta_off), "deg"),
                    inputs={r"\omega R C": Q_(w * R * cap, "")},
                    reference=ref,
                )
            )
            if flt == "pi":
                assert waves.v_c1 is not None and waves.i_ind is not None
                ripple1 = float(np.ptp(waves.v_c1))
                log.add(
                    record(
                        "dV_C1",
                        "Ondulação de pico a pico em C1",
                        r"\Delta V_{C1} = v_{C1,max} - v_{C1,min}",
                        output=Q_(ripple1, "V"),
                        inputs={},
                        reference=ref,
                    )
                )
                if float(np.min(waves.i_ind)) <= 0:
                    warnings.append(
                        DesignWarning(
                            code="descontinuo",
                            message="A corrente no indutor do π se anula; o modelo supõe "
                            "condução contínua. Aumente L ou C2.",
                        )
                    )
                summary["dV_C1"] = Q_(ripple1, "V")
                summary["VC1_max"] = Q_(float(np.max(waves.v_c1)), "V")
                summary["C2"] = Q_(C2, "F").to("uF")
                summary["L"] = Q_(inductance, "H").to("mH")
        else:  # LC
            Lcrit = log.add(
                record(
                    "Lcrit",
                    "Indutância crítica (corrente contínua no indutor)",
                    r"L_{crit} = \frac{R}{3\omega}",
                    output=Q_(m.critical_inductance(R, f), "H").to("mH"),
                    inputs={"R": Q_(R, "ohm"), r"\omega": Q_(w, "rad/s")},
                    assumptions=["C grande: a impedância do capacitor em 2f é muito menor que R"],
                    reference=HART_FW,
                )
            )
            L = log.add(
                record(
                    "L",
                    "Indutor do filtro",
                    r"L = k_L\,L_{crit}",
                    output=(Lcrit * s.L_factor).to("mH"),
                    inputs={"k_L": Q_(s.L_factor, ""), "L_{crit}": Lcrit},
                    assumptions=["critério de projeto ajustável (k_L)"],
                    reference=HART_FW,
                )
            ).m_as("H")
            Vm = log.add(
                record(
                    "Vm",
                    "Tensão de pico do secundário",
                    r"V_o = \frac{2V_m}{\pi} - nV_F \Rightarrow V_m = \frac{\pi}{2}(V_o + nV_F)",
                    output=Q_(math.pi / 2 * (Vo + n_vf), "V"),
                    inputs={"V_o": s.Vo.to_pint(), **inputs_vf},
                    assumptions=[
                        "corrente contínua no indutor",
                        "resistência do indutor desprezada",
                    ],
                    reference=HART_FW,
                )
            ).m_as("V")
            V2 = 4 * Vm / (3 * math.pi)
            C_req = log.add(
                record(
                    "C_req",
                    "Capacitância pela ondulação desejada",
                    r"\Delta V_o \approx \frac{2V_2}{(2\omega)^2LC - 1},\ V_2 = \frac{4V_m}{3\pi}"
                    r"\Rightarrow C = \frac{2V_2/\Delta V_o + 1}{(2\omega)^2 L}",
                    output=Q_((2 * V2 / dV_target + 1) / ((2 * w) ** 2 * L), "F").to("uF"),
                    inputs={
                        "V_2": Q_(V2, "V"),
                        r"\Delta V_o": Q_(dV_target, "V"),
                        "L": Q_(L, "H").to("mH"),
                    },
                    assumptions=["só a harmônica de 2f", "X_C ≪ R em 2f"],
                    reference=HART_FW,
                )
            )
            C = log.add(
                record(
                    "C",
                    f"Capacitor comercial (série {s.cap_series}, arredondado para cima)",
                    r"C = \lceil C_{req} \rceil_{" + s.cap_series + "}",
                    output=snap(C_req, s.cap_series, "up"),
                    inputs={"C_{req}": C_req},
                    reference=HART_FW,
                )
            ).m_as("F")
            waves = m.lc_filter(topo, Vm, VF, R, L, C, f)
            if float(np.min(waves.i_ind)) <= 0:  # type: ignore[arg-type]
                warnings.append(
                    DesignWarning(
                        code="descontinuo", message="A corrente no indutor se anula: aumente L."
                    )
                )
            summary["L"] = Q_(L, "H").to("mH")

        # ------------------------------------------------------------ output quantities
        vo_avg = m.mean(waves.vo)
        vo_rms = m.rms(waves.vo)
        ripple = float(np.max(waves.vo) - np.min(waves.vo))
        log.add(
            record(
                "Vo_avg",
                "Tensão média na carga (modelo)",
                r"V_o = \frac{1}{2\pi}\int_0^{2\pi} v_o\,d\theta",
                output=Q_(vo_avg, "V"),
                inputs={"V_m": Q_(Vm, "V")},
                assumptions=["integração da forma de onda do modelo em um período"],
                reference=ref,
            )
        )
        log.add(
            record(
                "Vo_rms",
                "Tensão eficaz na carga (modelo)",
                r"V_{o,ef} = \sqrt{\frac{1}{2\pi}\int_0^{2\pi} v_o^2\,d\theta}",
                output=Q_(vo_rms, "V"),
                inputs={},
                reference=ref,
            )
        )
        log.add(
            record(
                "dVo",
                "Ondulação de pico a pico na saída do retificador",
                r"\Delta V_o = v_{o,max} - v_{o,min}",
                output=Q_(ripple, "V"),
                inputs={},
                reference=ref,
            )
        )
        id_avg, id_rms, id_pk = (
            m.mean(waves.i_diode),
            m.rms(waves.i_diode),
            float(np.max(waves.i_diode)),
        )
        log.add(
            record(
                "ID_avg",
                "Corrente média em cada diodo",
                r"I_{D,med} = \frac{I_o}{p}",
                output=Q_(id_avg, "A"),
                inputs={"I_o": Q_(vo_avg / R, "A"), "p": Q_(p, "")},
                reference=ref,
            )
        )
        log.add(
            record(
                "ID_rms",
                "Corrente eficaz em cada diodo (modelo)",
                r"I_{D,ef} = \sqrt{\frac{1}{2\pi}\int_0^{2\pi} i_D^2\,d\theta}",
                output=Q_(id_rms, "A"),
                inputs={},
                reference=ref,
            )
        )
        log.add(
            record(
                "ID_pk",
                "Corrente de pico repetitiva em cada diodo",
                r"I_{D,pico} = \max i_D"
                + (
                    r" = \omega C V_m\cos\theta_{on} + \frac{V_m\sin\theta_{on} - nV_F}{R}"
                    if flt in ("C", "pi")
                    else ""
                ),
                output=Q_(id_pk, "A"),
                inputs={},
                reference=ref,
            )
        )
        log.add(
            record(
                "PIV",
                "Tensão reversa de pico em cada diodo",
                {
                    "meia_onda": r"V_{R,max} = \max(v_o - v_s)",
                    "center_tap": r"V_{R,max} = \max(v_o - v_s) \approx 2V_m",
                    "ponte": r"V_{R,max} = V_m",
                }[topo],
                output=Q_(waves.vr_diode_max, "V"),
                inputs={"V_m": Q_(Vm, "V")},
                reference=ref,
            )
        )
        if waves.i_cap is not None and C is not None:
            ic_rms = m.rms(waves.i_cap)
            log.add(
                record(
                    "IC_rms",
                    "Corrente eficaz no capacitor" + (" C1" if flt == "pi" else ""),
                    r"I_{C,ef} = \sqrt{I_{ret,ef}^2 - I_o^2}",
                    output=Q_(ic_rms, "A"),
                    inputs={},
                    assumptions=[
                        "a componente contínua da corrente retificada vai toda para a carga"
                    ],
                    reference=ref,
                )
            )
            summary["IC_rms"] = Q_(ic_rms, "A")
            summary["C"] = Q_(C, "F").to("uF")
            summary["VC_max"] = summary.pop("VC1_max", Q_(float(np.max(waves.vo)), "V"))

        # ------------------------------------------------------------ transformer
        Vin = s.Vin.to_pint().m_as("V")
        Vsec = Vm / math.sqrt(2)
        N = Vin / Vsec
        isec_rms = m.rms(waves.i_sec)
        iin_rms = m.rms(waves.i_in) / N
        windings = 2 if topo == "center_tap" else 1
        va_sec = windings * Vsec * isec_rms
        va_pri = Vin * iin_rms
        p_in = float(np.mean(waves.vs * waves.i_in))
        p_out = float(np.mean(waves.vo * waves.i_load))
        pf = p_in / (Vsec * m.rms(waves.i_in)) if m.rms(waves.i_in) > 0 else 0.0
        thd_i = m.thd(waves.i_in)
        log.add(
            record(
                "Vsec",
                "Tensão eficaz do secundário" + (" (cada metade)" if topo == "center_tap" else ""),
                r"V_{sec} = \frac{V_m}{\sqrt{2}}",
                output=Q_(Vsec, "V"),
                inputs={"V_m": Q_(Vm, "V")},
                reference=ref,
            )
        )
        log.add(
            record(
                "N",
                "Relação de espiras primário : secundário",
                r"N = \frac{V_{in}}{V_{sec}}",
                output=Q_(N, ""),
                inputs={"V_{in}": s.Vin.to_pint(), "V_{sec}": Q_(Vsec, "V")},
                assumptions=["transformador ideal (sem queda a plena carga)"],
                reference=ref,
            )
        )
        log.add(
            record(
                "Isec",
                "Corrente eficaz do secundário"
                + (" (cada metade)" if topo == "center_tap" else ""),
                r"I_{sec} = \sqrt{\frac{1}{2\pi}\int_0^{2\pi} i_{sec}^2\,d\theta}",
                output=Q_(isec_rms, "A"),
                inputs={},
                reference=ref,
            )
        )
        log.add(
            record(
                "VA_sec",
                "Potência aparente do secundário",
                r"S_{sec} = " + ("2\\," if windings == 2 else "") + r"V_{sec} I_{sec}",
                output=Q_(va_sec, "V*A"),
                inputs={"V_{sec}": Q_(Vsec, "V"), "I_{sec}": Q_(isec_rms, "A")},
                reference=ref,
            )
        )
        log.add(
            record(
                "VA_pri",
                "Potência aparente do primário",
                r"S_{pri} = V_{in} I_{in}",
                output=Q_(va_pri, "V*A"),
                inputs={"V_{in}": s.Vin.to_pint(), "I_{in}": Q_(iin_rms, "A")},
                assumptions=["a componente contínua do secundário não se reflete no primário"],
                reference=ref,
            )
        )
        log.add(
            record(
                "TUF",
                "Fator de utilização do transformador (secundário)",
                r"TUF = \frac{P_{cc}}{S_{sec}}",
                output=Q_(vo_avg * vo_avg / R / va_sec, ""),
                inputs={"P_{cc}": Q_(vo_avg**2 / R, "W"), "S_{sec}": Q_(va_sec, "V*A")},
                reference=ref,
            )
        )
        log.add(
            record(
                "PF",
                "Fator de potência na entrada",
                r"FP = \frac{P_{in}}{V_{in} I_{in}}",
                output=Q_(pf, ""),
                inputs={"P_{in}": Q_(p_in, "W"), "S_{in}": Q_(Vsec * m.rms(waves.i_in), "V*A")},
                assumptions=["transformador ideal: as perdas são só as dos diodos"],
                reference=ref,
            )
        )
        log.add(
            record(
                "THD_i",
                "Distorção harmônica total da corrente de entrada",
                r"THD_i = \frac{\sqrt{\sum_{h\ge2} I_h^2}}{I_1}",
                output=Q_(thd_i * 100, "percent"),
                inputs={},
                assumptions=["até a 50ª harmônica"],
                reference=ref,
            )
        )
        if topo == "meia_onda":
            warnings.append(
                DesignWarning(
                    code="cc_no_transformador",
                    message="Meia onda: o secundário conduz corrente média de "
                    f"{m.mean(waves.i_sec):.3g} A, que magnetiza o núcleo do transformador. "
                    "Prefira onda completa acima de poucos watts.",
                )
            )
        if flt in ("C", "pi"):
            warnings.append(
                DesignWarning(
                    code="surto",
                    message="Corrente de surto na energização (carga do capacitor) depende da "
                    "resistência do enrolamento e da fonte, que não fazem parte desta "
                    "especificação; confira IFSM do diodo quando o transformador for escolhido.",
                )
            )

        # ------------------------------------------------------------ stresses and losses
        d = role.designator
        stresses = [
            Stress(
                designator=d,
                key="VRRM",
                label="Tensão reversa de pico",
                value=QuantityModel(value=waves.vr_diode_max, unit="V"),
                calc_step_id="PIV",
            ),
            Stress(
                designator=d,
                key="IF(AV)",
                label="Corrente média",
                value=QuantityModel(value=id_avg, unit="A"),
                calc_step_id="ID_avg",
            ),
        ]
        losses = {d: Q_(VF * id_avg, "W")}
        if VF > 0:
            log.add(
                record(
                    f"P_{d}",
                    f"Perda em condução em cada diodo ({d})",
                    r"P_D = V_F\,I_{D,med}",
                    output=Q_(VF * id_avg, "W"),
                    inputs={"V_F": Q_(VF, "V"), "I_{D,med}": Q_(id_avg, "A")},
                    assumptions=[
                        "queda constante; despreza a parcela r_d·I_ef²",
                        "perdas de comutação desprezadas em 60 Hz",
                    ],
                    reference=ref,
                )
            )
        summary.update(
            {
                "Vo": Q_(vo_avg, "V"),
                "dVo": Q_(ripple, "V"),
                "Vo_rms": Q_(vo_rms, "V"),
                "Io": Q_(vo_avg / R, "A"),
                "Vm": Q_(Vm, "V"),
                "Vsec": Q_(Vsec, "V"),
                "N": Q_(N, ""),
                "VA_sec": Q_(va_sec, "V*A"),
                "VA_pri": Q_(va_pri, "V*A"),
                "PF": Q_(pf, ""),
                "THD_i": Q_(thd_i * 100, "percent"),
                "ID_avg": Q_(id_avg, "A"),
                "ID_rms": Q_(id_rms, "A"),
                "ID_pk": Q_(id_pk, "A"),
                "PIV": Q_(waves.vr_diode_max, "V"),
                "P_out": Q_(p_out, "W"),
                "eff": Q_(p_out / p_in * 100 if p_in > 0 else 0.0, "percent"),
            }
        )
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses=losses,
            warnings=warnings,
            convergence_keys=("Vm", "Vo"),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        """Same model as the analysis: ideal source, constant-drop diodes, ideal L and C.

        Zero-volt sources ``VSDk`` sense the diode currents. Capacitors and inductor start at the
        analytic mean values (``uic``) so the run settles in a few periods.
        """
        s = _spec(spec)
        role = self.roles(s)[0]
        VF = devices[role.designator].drop.m_as("V")
        Vm = summary["Vm"].to_pint().m_as("V")
        Vo = summary["Vo"].to_pint().m_as("V")
        Io = summary["Io"].to_pint().m_as("A")
        f = s.f.to_pint().m_as("Hz")
        R = s.Vo.to_pint().m_as("V") / s.Io.to_pint().m_as("A")
        src = f"SIN(0 {Vm:.9g} {f:.9g})"
        lines: list[str] = [behavioural_diode_model(VF)]
        if s.topology == "ponte":
            lines += [
                f"VS a b {src}",
                "VSD1 a d1 0",
                "XD1 d1 p DIODE",
                "XD2 b p DIODE",
                "XD3 0 a DIODE",
                "XD4 0 b DIODE",
            ]
            # the output is grounded; the secondary floats (it is a winding)
            neg, v_sec, i_in = "0", "v(a)-v(b)", "-i(vs)"
        elif s.topology == "center_tap":
            lines += [
                f"VS1 a 0 {src}",
                f"VS2 0 b {src}",
                "VSD1 a d1 0",
                "VSD2 b d2 0",
                "XD1 d1 p DIODE",
                "XD2 d2 p DIODE",
            ]
            neg, v_sec, i_in = "0", "v(a)", "i(vsd1)-i(vsd2)"
        else:
            lines += [f"VS a 0 {src}", "VSD1 a d1 0", "XD1 d1 p DIODE"]
            neg, v_sec, i_in = "0", "v(a)", "i(vsd1)"
        out = "p"
        if s.filter in ("C", "pi"):
            C = summary["C"].to_pint().m_as("F")
            lines.append(f"C1 p {neg} {C:.9g} IC={Vo:.6g}")
        if s.filter in ("LC", "pi"):
            L = summary["L"].to_pint().m_as("H")
            C_out = summary["C2" if s.filter == "pi" else "C"].to_pint().m_as("F")
            lines += [f"L1 p o {L:.9g} IC={Io:.6g}", f"C2 o {neg} {C_out:.9g} IC={Vo:.6g}"]
            out = "o"
        lines.append(f"RL {out} {neg} {R:.9g}")
        v_out = f"v({out})"
        probes = {
            "Tensão no secundário": v_sec,
            "Tensão na carga": v_out,
            "Corrente em D1": "i(vsd1)",
            "Corrente de entrada (referida ao secundário)": i_in,
        }
        checks = _checks(s.filter, v_out, v_sec, i_in)
        settle = {"nenhum": 3, "C": 20, "LC": 40, "pi": 40}[s.filter]
        return Circuit(
            title=f"{self.id}: {TOPOLOGY_LABEL[s.topology]}, {FILTER_LABEL[s.filter]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=settle / f, unit="s"),
            # a capacitor-input filter starts conducting with a current step: a coarse time step
            # overshoots it and inflates the RMS input current
            tran_step=QuantityModel(
                value=1 / f / (2000 if s.filter in ("nenhum", "LC") else 10000), unit="s"
            ),
            period=QuantityModel(value=1 / f, unit="s"),
            probes=probes,
            checks=checks,
        )


def _checks(flt: Filter, v_out: str, v_sec: str, i_in: str) -> list[SimCheck]:
    exact = "modelo exato (mesmo diodo de queda constante no simulador)"
    ripple_tol, ripple_why = {
        "nenhum": (1.0, exact),
        "C": (2.0, exact),
        "LC": (2.0, exact + " em condução contínua"),
        "pi": (2.0, exact + " em condução contínua do indutor"),
    }[flt]
    return [
        SimCheck(
            quantity="Tensão média na carga",
            summary_key="Vo",
            metric="avg",
            probe=v_out,
            tolerance_pct=1.0,
            justification=exact,
        ),
        SimCheck(
            quantity="Tensão eficaz na carga",
            summary_key="Vo_rms",
            metric="rms",
            probe=v_out,
            tolerance_pct=1.0,
            justification=exact,
        ),
        SimCheck(
            quantity="Ondulação de pico a pico",
            summary_key="dVo",
            metric="pp",
            probe=v_out,
            tolerance_pct=ripple_tol,
            justification=ripple_why,
        ),
        SimCheck(
            quantity="Corrente média em D1",
            summary_key="ID_avg",
            metric="avg",
            probe="i(vsd1)",
            tolerance_pct=1.0,
            justification=exact,
        ),
        SimCheck(
            quantity="Fator de potência",
            summary_key="PF",
            metric="pf",
            probe=i_in,
            voltage=v_sec,
            tolerance_pct=2.0,
            justification=exact,
        ),
        SimCheck(
            quantity="THD da corrente de entrada",
            summary_key="THD_i",
            metric="thd",
            probe=i_in,
            tolerance_pct=5.0,
            justification=exact + "; a THD é sensível ao passo de tempo da simulação",
        ),
    ]


def behavioural_diode_model(VF: float) -> str:
    """Constant-drop diode, the same model as the analytic calculation.

    On: 10 µΩ above VF (the analysis uses an ideal constant drop). Off: 1 µS, a 1 µA/V leakage
    that keeps a floating secondary (bridge) solvable and is negligible against the load.
    """
    return "\n".join(
        [
            ".subckt DIODE a k",
            f"BD a k I = (v(a,k) > {VF:.9g}) ? (v(a,k) - {VF:.9g}) / 10u : v(a,k) * 1u",
            ".ends",
        ]
    )


def _spec(spec: BaseModel) -> Ret1Spec:
    if not isinstance(spec, Ret1Spec):
        raise TypeError("DM-RET1 espera Ret1Spec")
    return spec
