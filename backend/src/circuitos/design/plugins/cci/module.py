"""DM-CCI: isolated PWM DC-DC converters in continuous conduction.

n = Ns/Np. Flyback: volt-second balance of the magnetising inductance,
D·(Vin − R_on·I_m) = (1 − D)(Vo + V_F)/n, with I_m = n·Io/(1 − D). Forward (reset winding
N3 = N1, D < 0,5): D·n·(Vin − R_on·n·I_L) = Vo + V_F. Push-pull, half bridge and full bridge
(centre-tapped secondary, D per switch < 0,5): 2·D·n·(V_p − R_on·n·I_L) = Vo + V_F with
V_p = Vin, Vin/2 and Vin (two switches in series in the full bridge). The forward-derived
outputs are a buck stage; ripples by the small-ripple approximation.

The turns ratio is chosen for the nominal duty cycle of the specification; the transformer
(or the coupled inductor of the flyback) is designed on catalogue cores (SV-MAG).

References: Erickson & Maksimović, *Fundamentals of Power Electronics*, 2nd ed., ch. 6
(converter circuits, transformer-isolated converters); Hart, *Power Electronics*, 1st ed.,
ch. 7 (DC power supplies); Mohan, Undeland & Robbins, *Power Electronics*, 3rd ed., ch. 10
(switching DC power supplies).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Literal

import numpy as np
import pint
from pydantic import BaseModel, Field, model_validator

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.analog import commercial, q
from circuitos.design.base import (
    Circuit,
    DesignResult,
    DesignWarning,
    Role,
    SimCheck,
    Stress,
    Trace,
)
from circuitos.design.engine import Analysis, Device
from circuitos.design.power import (
    ERICKSON,
    HART,
    InductorNeed,
    TransformerNeed,
    design_inductors,
    design_transformer,
    diode_data,
    diode_losses,
    efficiency_step,
    mag_labels,
    merge_magnetics,
    pwm_source,
    ref,
    spice_diode,
    spice_switch,
    switch_data,
    switch_losses,
)
from circuitos.reports import drawings_power
from circuitos.reports.canvas import pretty
from circuitos.reports.common import BomRow, LabItem, passive

Topology = Literal["flyback", "forward", "pushpull", "halfbridge", "fullbridge"]
BRIDGE = ("pushpull", "halfbridge", "fullbridge")
E6 = ref(ERICKSON, "6 (transformer-isolated converters)")
H7 = ref(HART, "7 (DC power supplies)")


class CciSpec(BaseModel):
    topology: Topology = "flyback"
    switch: Literal["mosfet", "igbt"] = "mosfet"
    Vin: QuantityModel = QuantityModel(value=48, unit="V")
    Vo: QuantityModel = QuantityModel(value=12, unit="V")
    Io: QuantityModel = QuantityModel(value=2, unit="A")
    fs: QuantityModel = QuantityModel(value=50, unit="kHz")
    D_nom: float = Field(default=0.4, gt=0.05, lt=0.95)  # per switch
    ripple_iL: float = Field(default=0.3, gt=0.01, le=1.5)  # Δi/I (L_o, or Lm of the flyback)
    ripple_vo: float = Field(default=0.01, gt=0.0005, le=0.2)
    V_gate: QuantityModel = QuantityModel(value=15, unit="V")
    TA: QuantityModel = QuantityModel(value=40, unit="degC")

    @model_validator(mode="after")
    def _check(self) -> CciSpec:
        lim = 0.45 if self.topology != "flyback" else 0.8
        if self.D_nom > lim:
            raise ValueError(
                f"D nominal ≤ {lim:g} nesta topologia (reset do núcleo / tempo morto)"
                if self.topology != "flyback"
                else "D nominal ≤ 0,8 no flyback"
            )
        if min(self.Vin.value, self.Vo.value, self.Io.value) <= 0:
            raise ValueError("Vin, Vo e Io devem ser positivos")
        return self


LABELS = {
    "n": "Relação de espiras Ns/Np",
    "D": "Razão cíclica (por chave)",
    "R_load": "Resistência de carga",
    "Lm": "Indutância magnetizante (flyback: projetada)",
    "Im": "Corrente média magnetizante (flyback, referida ao primário)",
    "dIm": "Ondulação da corrente magnetizante",
    "Im_pk": "Corrente de pico no primário",
    "L_o": "Indutor de saída",
    "IL": "Corrente média no indutor de saída",
    "dIL": "Ondulação no indutor de saída",
    "C_o": "Capacitor de saída",
    "dVo": "Ondulação da tensão de saída",
    "Vo_avg": "Tensão média de saída",
    "lam": "Volt-segundo por semiciclo no primário",
    "V_sw": "Tensão máxima na chave",
    "V_d": "Tensão reversa no retificador de saída",
    "Isw_rms": "Corrente eficaz em cada chave",
    "Isw_pk": "Corrente de pico em cada chave",
    "Id_avg": "Corrente média em cada diodo de saída",
    "P_Q1": "Perdas em cada chave",
    "P_D1": "Perdas em cada diodo de saída",
    "P_D2": "Perdas no diodo de roda livre",
    "eta_semi": "Rendimento só com semicondutores",
    "eta": "Rendimento estimado (com magnéticos)",
    **mag_labels(["L_o"]),
    "T1_N1": "Espiras do primário",
    "T1_N2": "Espiras do secundário",
    "T1_Lm": "Indutância magnetizante do transformador projetado",
    "T1_P": "Perdas no transformador",
    "T1_dT": "Elevação de temperatura do transformador",
    "T1_Bpk": "Indução de pico no transformador",
    "T1_gap": "Entreferro do flyback",
    "T1_ratio": "Relação de espiras realizada",
}
SPEC_LABELS = {
    "topology": "Topologia",
    "switch": "Chave",
    "Vin": "Tensão de entrada",
    "Vo": "Tensão de saída",
    "Io": "Corrente de saída",
    "fs": "Frequência de comutação",
    "D_nom": "Razão cíclica nominal por chave (define n)",
    "ripple_iL": "Ondulação de corrente (Δi/I)",
    "ripple_vo": "Ondulação de tensão na saída (ΔVo/Vo)",
    "V_gate": "Tensão de comando de porta",
}
ENUM_LABELS = {
    "flyback": "Flyback",
    "forward": "Forward (enrolamento de reset)",
    "pushpull": "Push-pull",
    "halfbridge": "Meia ponte",
    "fullbridge": "Ponte completa",
    "mosfet": "MOSFET",
    "igbt": "IGBT",
}
N_SW = {"flyback": 1, "forward": 1, "pushpull": 2, "halfbridge": 2, "fullbridge": 4}


def _spec(spec: BaseModel) -> CciSpec:
    if not isinstance(spec, CciSpec):
        raise TypeError("DM-CCI espera CciSpec")
    return spec


def _v(x: QuantityModel, unit: str) -> float:
    return float(x.to_pint().m_as(unit))


def _stress(des: str, key: str, label: str, v: float, unit: str, step: str) -> Stress:
    return Stress(
        designator=des,
        key=key,
        label=label,
        value=QuantityModel(value=v, unit=unit),
        calc_step_id=step,
    )


class CciModule:
    id = "DM-CCI"
    family = "potencia"
    title = "Conversores CC-CC isolados"
    spec_schema = CciSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão média de saída", "multímetro CC", "Vo_avg"),
        LabItem("Tensão na chave desligada", "osciloscópio (ponteira 100×)", "V_sw"),
        LabItem("Ondulação da tensão de saída", "osciloscópio (acoplamento CA)", "dVo"),
    ]
    questions = [
        "Por que o forward com enrolamento de reset N3 = N1 limita D a 0,5?",
        "De onde vem o pico de tensão no desligamento do flyback real, ausente no modelo ideal?",
        "Compare a tensão sobre as chaves do push-pull e da ponte completa para a mesma Vin.",
    ]
    safety = [
        "O primário pode estar ligado à rede retificada: trate-o como circuito perigoso e use "
        "ponteira diferencial ou transformador de isolação.",
        "A indutância de dispersão gera picos acima do calculado: prever snubber/grampeador "
        "(DM-CMD) antes de ligar em tensão plena.",
    ]

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        cat = "igbt" if s.switch == "igbt" else "mosfet.n"
        roles = [Role(designator="Q1", category=cat, description="Chave", count=N_SW[s.topology])]
        roles.append(
            Role(
                designator="D1",
                category="diode",
                description="Retificador de saída",
                count=2 if s.topology in BRIDGE else 1,
            )
        )
        if s.topology == "forward":
            roles.append(Role(designator="D2", category="diode", description="Roda livre"))
            roles.append(Role(designator="D3", category="diode", description="Diodo de reset"))
        return roles

    def required_ratings(self, role: Role) -> list[str]:
        if role.designator.startswith("D"):
            return ["VRRM", "IF(AV)"]
        return ["VCES", "IC"] if role.category == "igbt" else ["VDS", "ID"]

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        if role.designator.startswith("D"):
            return rec.category.startswith(("diode.schottky", "diode.fast"))
        return True

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        t = s.topology
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vin, vo, io = _v(s.Vin, "V"), _v(s.Vo, "V"), _v(s.Io, "A")
        fs = _v(s.fs, "Hz")
        ts = 1 / fs
        R = vo / io
        vd = devices["D1"].drop.m_as("V") if "D1" in devices else 0.0
        vd2 = devices["D2"].drop.m_as("V") if "D2" in devices else vd
        sw = switch_data(devices["Q1"].record if "Q1" in devices else None)
        sm: dict[str, pint.Quantity] = {"R_load": Q_(R, "ohm")}
        vp = vin / 2 if t == "halfbridge" else vin
        k_sw = 2 if t == "fullbridge" else 1  # switches in series with the primary
        d0 = s.D_nom
        # turns ratio for the nominal duty cycle, ideal switch
        n = {
            "flyback": (vo + vd) * (1 - d0) / (vp * d0),
            "forward": (vo + vd) / (vp * d0),
        }.get(t, (vo + vd) / (2 * vp * d0))
        log.add(
            record(
                "n",
                "Relação de espiras para a razão cíclica nominal",
                {
                    "flyback": r"n = \frac{(V_o + V_F)(1 - D_{nom})}{V_{in} D_{nom}}",
                    "forward": r"n = \frac{V_o + V_F}{V_{in} D_{nom}}",
                }.get(t, r"n = \frac{V_o + V_F}{2 V_p D_{nom}}"),
                output=Q_(n, ""),
                inputs={"V_p": Q_(vp, "V"), "V_F": Q_(vd, "V"), "D_nom": Q_(d0, "")},
                assumptions=["chave ideal na escolha de n; o D real sai do cálculo com R_on"],
                reference=E6,
            )
        )
        # duty cycle with the on-state drop (fixed point; IGBT: R_on = VCE(sat)/I)
        D = d0
        for _ in range(100):
            i_on = n * io / (1 - D) if t == "flyback" else n * io
            ron = sw.r_on if sw.kind != "igbt" else sw.v_on / max(i_on, 1e-9)
            vpe = vp - k_sw * ron * i_on
            if t == "flyback":
                new = (vo + vd) / (n * vpe + vo + vd)
            elif t == "forward":
                new = (vo + vd) / (n * vpe)
            else:
                new = (vo + vd) / (2 * n * vpe)
            if abs(new - D) < 1e-13:
                D = new
                break
            D = new
        lim = 0.5 if t != "flyback" else 0.95
        if lim <= D:
            raise ValueError(f"A razão cíclica com as perdas passou de {lim:g}; reduza D nominal.")
        log.add(
            record(
                "D",
                "Razão cíclica com a queda na chave",
                {
                    "flyback": r"D(V_{in} - R_{on} I_m) = (1 - D)\frac{V_o + V_F}{n}",
                    "forward": r"D\,n\,(V_{in} - R_{on} n I_L) = V_o + V_F",
                }.get(t, r"2D\,n\,(V_p - k R_{on} n I_L) = V_o + V_F"),
                output=Q_(D, ""),
                inputs={
                    "n": Q_(n, ""),
                    "R_on": Q_(ron, "ohm"),
                    "V_F": Q_(vd, "V"),
                    "V_p": Q_(vp, "V"),
                },
                assumptions=[
                    "modo contínuo; transformador ideal (sem dispersão)",
                    "corrente magnetizante desprezada nos conversores derivados do forward",
                ]
                + (["IGBT: R_on = V_CE(sat)/I_chave"] if sw.kind == "igbt" else []),
                reference=E6,
            )
        )
        sm |= {"n": Q_(n, ""), "D": Q_(D, ""), "Vo_avg": Q_(vo, "V")}
        needs: list[InductorNeed] = []
        if t == "flyback":
            im = n * io / (1 - D)
            vpe = vp - ron * im
            dim = s.ripple_iL * im
            lm = vpe * D * ts / dim
            log.add(
                record(
                    "Lm",
                    "Indutância magnetizante para a ondulação pedida",
                    r"L_m = \frac{(V_{in} - R_{on} I_m) D T_s}{\Delta i_m},\;"
                    r"I_m = \frac{n I_o}{1 - D}",
                    output=Q_(lm, "H").to("uH"),
                    inputs={"I_m": Q_(im, "A"), "Δi_m": Q_(dim, "A")},
                    reference=E6,
                )
            )
            co_req = io * D * ts / (s.ripple_vo * vo)
            log.add(
                record(
                    "C_o_req",
                    "Capacitor de saída (descarrega com I_o durante D·Ts)",
                    r"C_o = \frac{I_o D T_s}{\Delta V_o}",
                    output=Q_(co_req, "F").to("uF"),
                    inputs={"ΔV_o": Q_(s.ripple_vo * vo, "V")},
                    reference=E6,
                )
            )
            co = commercial(
                log, "C_o", "Capacitor de saída comercial", Q_(co_req, "F").to("uF"), "E12", "up"
            ).m_as("F")
            dvo = io * D * ts / co
            i_rms = math.sqrt(D * (im**2 + dim**2 / 12))
            i_pk = im + dim / 2
            i_valley = im - dim / 2
            i_s_rms = math.sqrt((1 - D) * (im**2 + dim**2 / 12)) / n
            v_sw = vin + (vo + dvo / 2 + vd) / n
            v_d = vo + dvo / 2 + n * vin
            id_avg = io
            sm |= {
                "Lm": Q_(lm, "H").to("uH"),
                "Im": Q_(im, "A"),
                "dIm": Q_(dim, "A"),
                "Im_pk": Q_(i_pk, "A"),
            }
            self._xfmr = TransformerNeed(
                "T1",
                "flyback",
                fs,
                (("P", 1.0, i_rms), ("S", n, i_s_rms)),
                L=lm,
                I_pk=i_pk,
                dI_pp=dim,
            )
            i_on_sw, i_off_sw = i_valley, i_pk
            i_avg_sw = D * im
        else:
            il = io
            span = (1 - D) * ts if t == "forward" else (0.5 - D) * ts
            dil = s.ripple_iL * il
            lo = (vo + vd2) * span / dil
            log.add(
                record(
                    "L_o",
                    "Indutor de saída (estágio buck do secundário)",
                    r"L_o = \frac{(V_o + V_F)\,t_{off}}{\Delta i_L}",
                    output=Q_(lo, "H").to("uH"),
                    inputs={
                        "t_off": Q_(span, "s").to("us"),
                        "Δi_L": Q_(dil, "A"),
                    },
                    assumptions=[
                        "t_off = (1 − D)Ts no forward; (1/2 − D)Ts nos simétricos (saída em 2f_s)"
                    ],
                    reference=H7,
                )
            )
            fo = fs if t == "forward" else 2 * fs
            co_req = dil / (8 * fo * s.ripple_vo * vo)
            log.add(
                record(
                    "C_o_req",
                    "Capacitor de saída (corrente triangular do indutor)",
                    r"C_o = \frac{\Delta i_L}{8 f_o \Delta V_o}",
                    output=Q_(co_req, "F").to("uF"),
                    inputs={"f_o": Q_(fo, "Hz").to("kHz"), "ΔV_o": Q_(s.ripple_vo * vo, "V")},
                    reference=H7,
                )
            )
            co = commercial(
                log, "C_o", "Capacitor de saída comercial", Q_(co_req, "F").to("uF"), "E12", "up"
            ).m_as("F")
            dvo = dil / (8 * fo * co)
            ip = n * il
            dip = n * dil
            i_rms = math.sqrt(D * (ip**2 + dip**2 / 12))
            i_on_sw, i_off_sw = ip - dip / 2, ip + dip / 2
            i_avg_sw = D * ip
            v_sw = {"forward": 2 * vin, "pushpull": 2 * vin}.get(t, vin)
            v_d = 2 * n * vp if t in BRIDGE else n * vin
            id_avg = io / 2 if t in BRIDGE else D * io
            lam = vp * D * ts
            log.add(
                record(
                    "lam",
                    "Volt-segundo aplicado ao primário em cada semiciclo",
                    r"\lambda = V_p D T_s",
                    output=Q_(lam, "V*s").to("V*us"),
                    inputs={"V_p": Q_(vp, "V"), "D": Q_(D, "")},
                    assumptions=[
                        "excitação " + ("unipolar (reset)" if t == "forward" else "simétrica")
                    ],
                    reference=E6,
                )
            )
            sec_rms = (
                math.sqrt(D * il**2 + (0.5 - D) * (il / 2) ** 2 * 2)
                if t in BRIDGE
                else math.sqrt(D) * il
            )
            wind: tuple[tuple[str, float, float], ...]
            if t == "forward":
                wind = (("P", 1.0, i_rms), ("S", n, sec_rms), ("R", 1.0, 0.05 * i_rms))
            elif t == "pushpull":
                wind = (
                    ("P1", 1.0, i_rms),
                    ("P2", 1.0, i_rms),
                    ("S1", n, sec_rms),
                    ("S2", n, sec_rms),
                )
            else:
                wind = (("P", 1.0, i_rms * math.sqrt(2)), ("S1", n, sec_rms), ("S2", n, sec_rms))
            self._xfmr = TransformerNeed(
                "T1", "transformador", fs, wind, lam=lam, bipolar=t != "forward"
            )
            needs.append(
                InductorNeed("L_o", lo, il + dil / 2, math.sqrt(il**2 + dil**2 / 12), dil, fo)
            )
            sm |= {
                "L_o": Q_(lo, "H").to("uH"),
                "IL": Q_(il, "A"),
                "dIL": Q_(dil, "A"),
                "lam": Q_(lam, "V*s").to("V*us"),
            }
            if t == "forward":
                sm["dIm"] = Q_(0.0, "A")
        self._needs = needs
        log.add(
            record(
                "V_sw",
                "Tensão máxima em cada chave",
                {
                    "flyback": r"V_{S} = V_{in} + \frac{V_o + V_F}{n}",
                    "forward": r"V_S = 2V_{in}\;(N_3 = N_1)",
                    "pushpull": r"V_S = 2V_{in}",
                }.get(t, r"V_S = V_{in}"),
                output=Q_(v_sw, "V"),
                inputs={"V_in": Q_(vin, "V"), "n": Q_(n, "")},
                assumptions=["sem o pico da indutância de dispersão (prever snubber/grampeador)"],
                reference=E6,
            )
        )
        log.add(
            record(
                "V_d",
                "Tensão reversa no retificador de saída",
                {
                    "flyback": r"V_D = V_o + n V_{in}",
                    "forward": r"V_D = n V_{in}",
                }.get(t, r"V_D = 2 n V_p"),
                output=Q_(v_d, "V"),
                inputs={"n": Q_(n, "")},
                reference=E6,
            )
        )
        log.add(
            record(
                "Isw_rms",
                "Corrente eficaz em cada chave",
                r"I_{S,rms} = \sqrt{D\left(I_p^2 + \Delta i_p^2/12\right)}",
                output=Q_(i_rms, "A"),
                inputs={"D": Q_(D, "")},
                reference=E6,
            )
        )
        sl, w = switch_losses(
            log, "Q1", sw, v_sw, i_on_sw, i_off_sw, i_rms, i_avg_sw, fs, _v(s.V_gate, "V")
        )
        warnings += [DesignWarning(code="perdas", message=m) for m in w]
        d1 = diode_data(devices["D1"].record if "D1" in devices else None, vd)
        pd1, w = diode_losses(log, "D1", d1, id_avg, v_d, fs)
        warnings += [DesignWarning(code="perdas", message=m) for m in w]
        losses = {"Q1": sl.total * N_SW[t], "D1": pd1 * (2 if t in BRIDGE else 1)}
        stresses = [
            _stress(
                "Q1", "VCES" if s.switch == "igbt" else "VDS", "Tensão na chave", v_sw, "V", "V_sw"
            ),
            _stress(
                "Q1", "IC" if s.switch == "igbt" else "ID", "Corrente eficaz", i_rms, "A", "Isw_rms"
            ),
            _stress("D1", "VRRM", "Tensão reversa", v_d, "V", "V_d"),
            _stress("D1", "IF(AV)", "Corrente média", id_avg, "A", "V_d"),
        ]
        dev_losses = {"Q1": Q_(sl.total, "W"), "D1": Q_(pd1, "W")}
        if t == "forward":
            d2 = diode_data(devices["D2"].record if "D2" in devices else None, vd2)
            pd2, w = diode_losses(log, "D2", d2, (1 - D) * io, n * vin, fs)
            warnings += [DesignWarning(code="perdas", message=m) for m in w]
            losses["D2"] = pd2
            dev_losses["D2"] = Q_(pd2, "W")
            sm["P_D2"] = Q_(pd2, "W")
            stresses += [
                _stress("D2", "VRRM", "Tensão reversa", n * vin, "V", "V_d"),
                _stress("D2", "IF(AV)", "Corrente média", (1 - D) * io, "A", "V_d"),
                _stress("D3", "VRRM", "Tensão reversa", 2 * vin, "V", "V_sw"),
                _stress("D3", "IF(AV)", "Corrente de reset", 0.05 * i_rms, "A", "V_sw"),
            ]
            warnings.append(
                DesignWarning(
                    code="reset",
                    message="D3 conduz só a corrente magnetizante; a corrente usada na seleção "
                    "(5 % da corrente do primário) é uma premissa, confirmada após o projeto "
                    "do transformador.",
                )
            )
        eta = efficiency_step(log, vo * io, losses, "eta_semi")
        sm |= {
            "C_o": Q_(co, "F").to("uF"),
            "dVo": Q_(dvo, "V").to("mV"),
            "V_sw": Q_(v_sw, "V"),
            "V_d": Q_(v_d, "V"),
            "Isw_rms": Q_(i_rms, "A"),
            "Isw_pk": Q_(i_off_sw, "A"),
            "Id_avg": Q_(id_avg, "A"),
            "P_Q1": Q_(sl.total, "W"),
            "P_D1": Q_(pd1, "W"),
            "eta_semi": Q_(eta, "percent"),
        }
        log.add(
            record(
                "dVo",
                "Ondulação de saída com o capacitor comercial",
                r"\Delta V_o",
                output=Q_(dvo, "V").to("mV"),
                inputs={"C_o": Q_(co, "F").to("uF")},
                reference=E6,
            )
        )
        return Analysis(
            log=log,
            stresses=stresses,
            summary=sm,
            losses=dev_losses,
            warnings=warnings,
            convergence_keys=("D",),
            traces=self._traces(s, sm),
            trace_period=Q_(ts, "s"),
        )

    def _traces(self, s: CciSpec, sm: Mapping[str, pint.Quantity]) -> dict[str, Trace]:
        n = 720
        t = np.arange(n) / n
        D = float(sm["D"].m_as(""))
        if s.topology == "flyback":
            im, di = float(sm["Im"].m_as("A")), float(sm["dIm"].m_as("A"))
            ip = np.where(t < D, im - di / 2 + di * t / D, 0.0)
            return {"i_primário": Trace(unit="A", values=[float(x) for x in ip])}
        il, di = float(sm["IL"].m_as("A")), float(sm["dIL"].m_as("A"))
        per = 1.0 if s.topology == "forward" else 0.5
        tt = (t % per) / per
        dd = D / per
        i = np.where(tt < dd, il - di / 2 + di * tt / dd, il + di / 2 - di * (tt - dd) / (1 - dd))
        return {"i_Lo": Trace(unit="A", values=[float(x) for x in i])}

    def finish(
        self,
        spec: BaseModel,
        analysis: Analysis,
        devices: Mapping[str, Device],
        catalogue: Callable[[str], list[ComponentRecord]],
    ) -> None:
        s = _spec(spec)
        self.analyse(spec, devices)
        ta = _v(s.TA, "degC")
        mags = [design_transformer(self._xfmr, catalogue, ta)]
        if self._needs:
            mags.append(design_inductors(self._needs, catalogue, ta))
        losses = {k: float(v.m_as("W")) for k, v in analysis.losses.items()}
        losses["Q1"] = losses["Q1"] * N_SW[s.topology]
        if s.topology in BRIDGE:
            losses["D1"] = losses["D1"] * 2
        for mag in mags:
            merge_magnetics(analysis.log, analysis.summary, analysis.warnings, mag)
            losses |= mag.losses
        eta = efficiency_step(analysis.log, _v(s.Vo, "V") * _v(s.Io, "A"), losses, "eta")
        analysis.summary["eta"] = Q_(eta, "percent")

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        t = s.topology
        vin, vo, io = _v(s.Vin, "V"), _v(s.Vo, "V"), _v(s.Io, "A")
        fs = _v(s.fs, "Hz")
        ts = 1 / fs
        R = vo / io
        vd = devices["D1"].drop.m_as("V") if "D1" in devices else 0.0
        vd2 = devices["D2"].drop.m_as("V") if "D2" in devices else vd
        sw = switch_data(devices["Q1"].record if "Q1" in devices else None)
        D = q(summary, "D", "")
        n = q(summary, "n", "")
        co = q(summary, "C_o", "F")
        dvo = q(summary, "dVo", "V")
        lines = [
            spice_switch("SWQ", sw),
            spice_diode("DR", vd),
            spice_diode("DF", vd2),
            f"RL out 0 {R:.9g}",
        ]
        notes = ""
        if t == "flyback":
            lm = q(summary, "Lm", "H")
            im0 = q(summary, "Im", "A") - q(summary, "dIm", "A") / 2
            lines += [
                f"VIN in 0 DC {vin:.9g}",
                pwm_source("VG", "g", D, fs),
                f"LP in p {lm:.9g} IC={im0:.9g}",
                "VIP p d 0",
                f"LS 0 s {lm * n * n:.9g}",
                "K1 LP LS 1",
                "XQ d 0 g SWQ",
                "XD s out DR",
                f"CO out 0 {co:.9g} IC={vo + dvo / 2:.9g}",
            ]
            checks = [
                SimCheck(
                    quantity="Tensão média de saída",
                    summary_key="Vo_avg",
                    metric="avg",
                    probe="v(out)",
                    tolerance_pct=1.5,
                    justification="R_on com a corrente média no cálculo de D",
                ),
                SimCheck(
                    quantity="Corrente de pico no primário",
                    summary_key="Im_pk",
                    metric="max",
                    probe="i(vip)",
                    tolerance_pct=3.0,
                    justification="tensão no primário constante na condução",
                ),
                SimCheck(
                    quantity="Ondulação da tensão de saída",
                    summary_key="dVo",
                    metric="pp",
                    probe="v(out)",
                    tolerance_pct=15.0,
                    justification="carga constante I_o",
                ),
            ]
            probes = {"i_primário": "i(vip)", "v_o": "v(out)"}
            tau = R * co
        else:
            lo = q(summary, "L_o", "H")
            il0 = q(summary, "IL", "A") - q(summary, "dIL", "A") / 2
            lmz = q(summary, "T1_Lm", "H") if "T1_Lm" in summary else 0.0
            if lmz <= 0:
                lmz = 100 * vin * D * ts / max(n * io, 1e-9)
                notes = "L_m sem projeto do transformador: premissa de 1 % de corrente magnetizante"
            lines += [
                f"VIN in 0 DC {vin:.9g}",
                f"LO x y {lo:.9g} IC={il0:.9g}",
                "VIL y out 0",
                f"CO out 0 {co:.9g} IC={vo:.9g}",
            ]
            if t == "forward":
                lines += [
                    pwm_source("VG", "g", D, fs),
                    f"LP in p {lmz:.9g}",
                    "VIP p d 0",
                    # reset winding N3: dotted end at ground, so when the switch opens it drives
                    # r1 up and D3 clamps it at Vin (v_DS = 2·Vin for N3 = N1)
                    f"LR 0 r1 {lmz:.9g}",
                    f"LS s 0 {lmz * n * n:.9g}",
                    "K1 LP LS 1",
                    "K2 LP LR 1",
                    "K3 LS LR 1",
                    "XQ d 0 g SWQ",
                    "XDR r1 in DR",
                    "XD1 s x DR",
                    "XD2 0 x DF",
                ]
            else:
                lines += [
                    pwm_source("VG1", "g1", D, fs),
                    pwm_source("VG2", "g2", D, fs, ts / 2),
                    f"LS1 s1 c {lmz * n * n:.9g}",
                    f"LS2 c s2 {lmz * n * n:.9g}",
                    "VCT c 0 0",
                    "XD1 s1 x DR",
                    "XD2 s2 x DR",
                ]
                if t == "pushpull":
                    lines += [
                        f"LP1 d1 in {lmz:.9g}",
                        f"LP2 in d2 {lmz:.9g}",
                        "XQ1 d1 0 g1 SWQ",
                        "XQ2 d2 0 g2 SWQ",
                    ]
                    wn = ["LP1", "LP2", "LS1", "LS2"]
                elif t == "halfbridge":
                    lines += [
                        f"VH1 in m {vin / 2:.9g}",
                        "XQ1 in a g1 SWQ",
                        "XQ2 a 0 g2 SWQ",
                        f"LP a pm {lmz:.9g}",
                        "VIP pm m 0",
                    ]
                    wn = ["LP", "LS1", "LS2"]
                else:
                    lines += [
                        "XQ1 in a g1 SWQ",
                        "XQ4 b 0 g1 SWQ",
                        "XQ3 in b g2 SWQ",
                        "XQ2 a 0 g2 SWQ",
                        f"LP a pm {lmz:.9g}",
                        "VIP pm b 0",
                    ]
                    wn = ["LP", "LS1", "LS2"]
                k = 1
                for i in range(len(wn)):
                    for j in range(i + 1, len(wn)):
                        lines.append(f"K{k} {wn[i]} {wn[j]} 1")
                        k += 1
            checks = [
                SimCheck(
                    quantity="Tensão média de saída",
                    summary_key="Vo_avg",
                    metric="avg",
                    probe="v(out)",
                    tolerance_pct=1.5,
                    justification="corrente magnetizante e R_on aproximados",
                ),
                SimCheck(
                    quantity="Corrente média no indutor de saída",
                    summary_key="IL",
                    metric="avg",
                    probe="i(vil)",
                    tolerance_pct=1.5,
                    justification="modelo médio",
                ),
                SimCheck(
                    quantity="Ondulação no indutor de saída",
                    summary_key="dIL",
                    metric="pp",
                    probe="i(vil)",
                    tolerance_pct=5.0,
                    justification="tensão no indutor constante em cada intervalo",
                ),
                SimCheck(
                    quantity="Ondulação da tensão de saída",
                    summary_key="dVo",
                    metric="pp",
                    probe="v(out)",
                    tolerance_pct=15.0,
                    justification="corrente triangular no capacitor",
                ),
            ]
            probes = {"i_Lo": "i(vil)", "v_o": "v(out)"}
            tau = 2 * R * co
        n_per = int(min(max(300, 8 * tau / ts), 3000))
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[t]}" + (f" ({notes})" if notes else ""),
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
        txt = {k: pretty(sm[src]) for k, src in (("LO", "L_o"), ("Co", "C_o")) if src in sm}
        txt["VIN"] = pretty(s.Vin)
        txt["VH1"] = f"{s.Vin.value / 2:g} {s.Vin.unit}".replace(".", ",")
        txt["RL"] = f"{s.Vo.value / s.Io.value:.4g} Ω".replace(".", ",")
        if "T1_N1" in sm:
            txt["T1"] = f"N1 = {int(sm['T1_N1'].value)}, N2 = {int(sm['T1_N2'].value)}"
        elif "n" in sm:
            txt["T1"] = f"n = {sm['n'].value:.4g}".replace(".", ",")
        parts = {c.designator: c.part_number for c in result.selection}
        note = ENUM_LABELS[s.topology]
        if "D" in sm:
            note += f", D = {sm['D'].value:.3f}".replace(".", ",")
        if "Lm" in sm:
            note += f", Lm = {pretty(sm['Lm'])}"
        return drawings_power.isolated(s.topology, title, s.switch, txt, parts, note)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        sm = result.summary
        rows = []
        if "T1_N1" in sm:
            rows.append(
                passive(
                    "T1",
                    "Transformador (projeto SV-MAG)",
                    f"N1 = {int(sm['T1_N1'].value)}, N2 = {int(sm['T1_N2'].value)}",
                    "ver passos de cálculo do magnético",
                )
            )
        else:
            rows.append(
                passive("T1", "Transformador", f"n = {sm['n'].value:.4g}", "projetar o magnético")
            )
        for k, desc in (("L_o", "Indutor de saída"), ("C_o", "Capacitor de saída")):
            if k in sm:
                rows.append(passive(k, desc, format_eng(sm[k].to_pint())))
        return rows
