"""DM-INV: voltage-source inverters, single phase (full bridge) and three phase.

Modulations: square wave, quasi-square wave (single phase, zero intervals α), sinusoidal PWM
bipolar and unipolar (single phase), sinusoidal PWM and space-vector PWM (three phase, min-max
zero-sequence injection). The output waveform is synthesised over one fundamental period
(``design/inverter.py``) with the dead time; the load current, harmonics, THD and the losses of
each device follow from it, harmonic by harmonic. Optional L-C output filter with the corner
at a fraction of the switching frequency and characteristic impedance equal to the load
resistance.

References: Hart, *Power Electronics*, 1st ed., ch. 8; Mohan, Undeland & Robbins, *Power
Electronics*, 3rd ed., ch. 8; Rashid, *Power Electronics*, 4th ed., ch. 6.
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
    make_trace,
)
from circuitos.design.engine import Analysis, Device
from circuitos.design.inverter import (
    HART8,
    MOHAN8,
    RASHID6,
    amplitudes,
    grid,
    leg_losses,
    leg_voltages,
    load_voltages,
    response,
    rms,
    square_harmonic,
    switching,
    thd,
)
from circuitos.design.power import (
    ERICKSON,
    InductorNeed,
    design_inductors,
    efficiency_step,
    mag_labels,
    merge_magnetics,
    pval,
    switch_data,
)
from circuitos.reports import drawings_power
from circuitos.reports.canvas import pretty
from circuitos.reports.common import BomRow, LabItem, passive

Modulation = Literal["quadrada", "quase_quadrada", "spwm_bipolar", "spwm_unipolar", "spwm", "svpwm"]
ONE_PHASE = ("quase_quadrada", "spwm_bipolar", "spwm_unipolar")
THREE_PHASE = ("spwm", "svpwm")
PWM = ("spwm_bipolar", "spwm_unipolar", "spwm", "svpwm")
N_SAMPLES = 2**17
ERICKSON10 = ERICKSON.model_copy(update={"chapter": "10 (input filter design, damping)"})
N_CHECK = 50  # harmonics in the THD compared with the simulator (same count as verify.py)


class InvSpec(BaseModel):
    phases: Literal[1, 3] = 1
    modulation: Modulation = "spwm_unipolar"
    switch: Literal["igbt", "mosfet"] = "igbt"
    Vdc: QuantityModel = QuantityModel(value=400, unit="V")
    f1: QuantityModel = QuantityModel(value=60, unit="Hz")
    mf: int = Field(default=21, ge=3, le=400)  # carrier / fundamental
    ma: float = Field(default=0.8, gt=0.0, le=1.155)
    alpha_deg: float = Field(default=30, ge=0, lt=90)  # quasi-square zero interval
    R: QuantityModel = QuantityModel(value=10, unit="ohm")  # per phase (star)
    L: QuantityModel = QuantityModel(value=20, unit="mH")
    filter: bool = False
    fc_ratio: float = Field(default=0.2, gt=0.01, lt=0.5)  # filter corner / switching frequency
    ripple_if: float = Field(default=0.2, gt=0.01, le=1.0)  # Lf ripple / peak current
    dead_time: QuantityModel = QuantityModel(value=2, unit="us")
    TA: QuantityModel = QuantityModel(value=40, unit="degC")

    @model_validator(mode="after")
    def _check(self) -> InvSpec:
        if self.phases == 3 and self.modulation in ONE_PHASE:
            raise ValueError("Essa modulação é monofásica")
        if self.phases == 1 and self.modulation in THREE_PHASE:
            raise ValueError("Essa modulação é trifásica")
        lim = 2 / math.sqrt(3) if self.modulation == "svpwm" else 1.0
        if self.modulation in PWM and self.ma > lim + 1e-9:
            raise ValueError(f"ma ≤ {lim:.3f} (sem sobremodulação)")
        if self.filter and self.modulation not in PWM:
            raise ValueError("O filtro LC é dimensionado pela frequência de comutação (PWM)")
        return self


LABELS = {
    "fs": "Frequência de comutação",
    "V1": "Tensão fundamental na carga (eficaz)",
    "V1_ideal": "Tensão fundamental ideal (sem tempo morto)",
    "dV_dead": "Erro médio de tensão por perna (tempo morto)",
    "V_rms": "Tensão eficaz total na carga",
    "I1": "Corrente fundamental (eficaz)",
    "I_rms": "Corrente eficaz na carga",
    "I_pk": "Corrente de pico",
    "THD_v": "THD da tensão na carga",
    "THD_i": "THD da corrente",
    "THD_v50": "THD da tensão até a 50ª",
    "THD_i50": "THD da corrente até a 50ª",
    "Po": "Potência ativa na carga",
    "Lf": "Indutor do filtro",
    "Cf": "Capacitor do filtro",
    "Rd": "Resistor de amortecimento do filtro",
    "Cd": "Capacitor de amortecimento do filtro",
    "fc_f": "Frequência de corte do filtro",
    "P_Q1": "Perdas por chave (transistor + diodo)",
    "P_cond": "Condução por transistor",
    "P_sw": "Comutação por transistor",
    "P_d": "Diodo (condução + recuperação)",
    "eta": "Rendimento estimado",
    "I_dc": "Corrente média na entrada CC",
    **mag_labels(["Lf"]),
}
SPEC_LABELS = {
    "phases": "Fases",
    "modulation": "Modulação",
    "switch": "Chave",
    "Vdc": "Tensão do barramento CC",
    "f1": "Frequência fundamental",
    "mf": "Índice de frequência mf = fs/f1",
    "ma": "Índice de modulação ma",
    "alpha_deg": "Intervalo nulo α da onda quase quadrada (°)",
    "R": "Resistência da carga (por fase)",
    "L": "Indutância da carga (por fase)",
    "filter": "Filtro LC de saída",
    "fc_ratio": "Corte do filtro / fs",
    "ripple_if": "Ondulação no indutor do filtro (ΔI/I_pk)",
    "dead_time": "Tempo morto",
}
ENUM_LABELS = {
    "quadrada": "onda quadrada (seis pulsos no trifásico)",
    "quase_quadrada": "onda quase quadrada",
    "spwm_bipolar": "SPWM bipolar",
    "spwm_unipolar": "SPWM unipolar",
    "spwm": "SPWM senoidal",
    "svpwm": "SVPWM (injeção de sequência zero)",
    "igbt": "IGBT",
    "mosfet": "MOSFET",
}


def _spec(spec: BaseModel) -> InvSpec:
    if not isinstance(spec, InvSpec):
        raise TypeError("DM-INV espera InvSpec")
    return spec


def _v(x: QuantityModel, unit: str) -> float:
    return float(x.to_pint().m_as(unit))


class InvModule:
    id = "DM-INV"
    family = "potencia"
    title = "Inversores de tensão"
    spec_schema = InvSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Corrente eficaz na carga", "alicate de valor eficaz verdadeiro", "I_rms"),
        LabItem("THD da corrente", "analisador de energia / FFT do osciloscópio", "THD_i"),
        LabItem("Tensão fundamental", "analisador de energia", "V1"),
    ]
    questions = [
        "Por que a SPWM unipolar desloca os harmônicos para perto de 2·mf?",
        "Qual o efeito do tempo morto na fundamental quando a corrente é pequena?",
        "Compare a tensão máxima linear da SPWM e da SVPWM no trifásico.",
    ]
    safety = [
        "Barramento CC de alta tensão: descarregue os capacitores e confirme com o multímetro "
        "antes de tocar no circuito.",
        "Use ponteiras diferenciais para medir tensões de perna; o terra do osciloscópio não "
        "pode ser ligado a pontos flutuantes.",
    ]

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        return [
            Role(
                designator="Q1",
                category="igbt" if s.switch == "igbt" else "mosfet.n",
                description="Chave com diodo em antiparalelo",
                count=4 if s.phases == 1 else 6,
            )
        ]

    def required_ratings(self, role: Role) -> list[str]:
        return ["VCES", "IC"] if role.category == "igbt" else ["VDS", "ID"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.25, "K/W")

    # ------------------------------------------------------------------ analysis
    def _waves(
        self,
        s: InvSpec,
        lf: float,
        cf: float,
        drops: tuple[float, float, float] = (0, 0, 0),
        rd: float = 0.0,
        cd: float = 0.0,
    ) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray], list[np.ndarray], float]:
        th = grid(N_SAMPLES)
        vdc = _v(s.Vdc, "V")
        w1 = 2 * math.pi * _v(s.f1, "Hz")
        R, L = _v(s.R, "ohm"), _v(s.L, "H")
        st = switching(s.modulation, s.phases, s.ma, s.mf, math.radians(s.alpha_deg), th)
        dead = round(_v(s.dead_time, "s") * _v(s.f1, "Hz") * N_SAMPLES)
        i_leg: list[np.ndarray] | None = None
        vl: list[np.ndarray] = []
        il: list[np.ndarray] = []
        vo: list[np.ndarray] = []
        need = dead > 0 or any(d > 0 for d in drops)
        for _ in range(60):  # the current sign fixes the drops and the blanking voltage
            legs = leg_voltages(st, vdc, i_leg, dead, *drops, synchronous=s.switch == "mosfet")
            vl = load_voltages(s.phases, legs)
            il, vo = [], []
            for v in vl:
                _, v_load, i_inv = response(v, w1, R, L, lf, cf, rd, cd)
                il.append(i_inv)
                vo.append(v_load)
            if not need:
                break
            new = il if s.phases == 3 else [il[0], -il[0]]
            if i_leg is None:
                i_leg = new
                continue
            delta = max(float(np.max(np.abs(a - b))) for a, b in zip(new, i_leg, strict=True))
            # under-relaxed: the leg voltage depends on the sign of the current, and with a
            # large ripple the plain fixed point oscillates around the zero crossings
            i_leg = [0.5 * (a + b) for a, b in zip(new, i_leg, strict=True)]
            if delta < 1e-6 * max(float(np.max(np.abs(a))) for a in new):
                break
        return st, vl, il, vo, dead / N_SAMPLES / _v(s.f1, "Hz")

    def _filter_L(self, s: InvSpec) -> tuple[float, float]:
        """L_f for the carrier ripple (r·I_pk peak to peak) with the capacitor shorting the
        carrier harmonics: i_ripple = (1/L_f)∫(v_inv − v_1)dt, computed on the ideal wave."""
        th = grid(N_SAMPLES)
        vdc = _v(s.Vdc, "V")
        f1 = _v(s.f1, "Hz")
        st = switching(s.modulation, s.phases, s.ma, s.mf, 0.0, th)
        v = load_voltages(s.phases, leg_voltages(st, vdc))[0]
        c = np.fft.rfft(v)
        c[:2] = 0  # remove DC and the fundamental
        h = np.fft.irfft(c, v.size)
        flux = np.cumsum(h) / (f1 * v.size)  # ∫ v dt
        n = v.size // s.mf
        rip = max(float(np.ptp(flux[k * n : (k + 1) * n])) for k in range(s.mf))
        R, L = _v(s.R, "ohm"), _v(s.L, "H")
        i_pk = (
            math.sqrt(2)
            * (s.ma * vdc / (math.sqrt(2) * (2 if s.phases == 3 else 1)))
            / abs(complex(R, 2 * math.pi * f1 * L))
        )
        return rip / (s.ripple_if * i_pk), i_pk

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vdc = _v(s.Vdc, "V")
        f1 = _v(s.f1, "Hz")
        w1 = 2 * math.pi * f1
        R, L = _v(s.R, "ohm"), _v(s.L, "H")
        pwm = s.modulation in PWM
        fs = s.mf * f1 if pwm else f1
        sm: dict[str, pint.Quantity] = {"fs": Q_(fs, "Hz").to("kHz")}
        if pwm and s.phases == 3 and s.mf % 3:
            warnings.append(
                DesignWarning(
                    code="mf",
                    message="No trifásico use mf múltiplo de 3 "
                    "(cancela os harmônicos triplos da portadora).",
                )
            )
        if pwm and s.mf % 2 == 0:
            warnings.append(
                DesignWarning(
                    code="mf",
                    message="mf par gera harmônicos pares (simetria de meia onda perdida).",
                )
            )
        lf = cf = rd = cd = 0.0
        if s.filter:
            fcf = s.fc_ratio * fs
            if fcf < 3 * f1:
                raise ValueError(
                    f"Corte do filtro ({fcf:.0f} Hz) abaixo de 3·f1: aumente mf ou a fração fc/fs"
                )
            lf, i_pk0 = self._filter_L(s)
            log.add(
                record(
                    "Lf",
                    "Filtro LC: indutor pela ondulação na frequência da portadora",
                    r"L_f = \frac{\max_{T_s}\Delta\!\int (v_{inv} - v_1)\,dt}{r\,I_{pk}}",
                    output=Q_(lf, "H").to("mH"),
                    inputs={
                        "r": Q_(s.ripple_if, ""),
                        "I_pk": Q_(i_pk0, "A"),
                        "f_s": Q_(fs, "Hz").to("kHz"),
                    },
                    assumptions=[
                        "o capacitor curto-circuita os harmônicos da portadora",
                        "ondulação pico a pico máxima num período de portadora",
                    ],
                    reference=HART8,
                )
            )
            cf_req = 1 / ((2 * math.pi * fcf) ** 2 * lf)
            log.add(
                record(
                    "Cf_req",
                    "Filtro LC: capacitor para o corte pedido",
                    r"C_f = \frac{1}{(2\pi f_c)^2 L_f},\; f_c = k f_s",
                    output=Q_(cf_req, "F").to("uF"),
                    inputs={"f_c": Q_(fcf, "Hz").to("kHz"), "k": Q_(s.fc_ratio, "")},
                    reference=HART8,
                )
            )
            cf = commercial(
                log, "Cf", "Capacitor do filtro", Q_(cf_req, "F").to("uF"), "E12", "nearest"
            ).m_as("F")
            z0 = math.sqrt(lf / cf)
            cd = commercial(
                log,
                "Cd",
                "Capacitor de amortecimento C_d = 4 C_f",
                Q_(4 * cf, "F").to("uF"),
                "E12",
                "nearest",
            ).m_as("F")
            rd = log.add(
                record(
                    "Rd",
                    "Amortecimento paralelo R_d–C_d do filtro",
                    r"R_d = R_0\sqrt{\frac{(2+n)(4+3n)}{2n^2(4+n)}},\;R_0 = \sqrt{L_f/C_f},\;"
                    r"n = C_d/C_f",
                    output=Q_(z0 * math.sqrt((2 + 4) * (4 + 12) / (2 * 16 * (4 + 4))), "ohm"),
                    inputs={"R_0": Q_(z0, "ohm"), "n": Q_(4, "")},
                    assumptions=[
                        "a carga RL quase não amortece a ressonância (ωL ≫ R em f_c)",
                        "amortecimento ótimo de Middlebrook para n = 4",
                    ],
                    reference=ERICKSON10,
                )
            ).m_as("ohm")
            sm |= {"Rd": Q_(rd, "ohm"), "Cd": Q_(cd, "F").to("uF")}
            sm |= {
                "Lf": Q_(lf, "H").to("mH"),
                "Cf": Q_(cf, "F").to("uF"),
                "fc_f": Q_(1 / (2 * math.pi * math.sqrt(lf * cf)), "Hz").to("kHz"),
            }
        rec = devices["Q1"].record if "Q1" in devices else None
        sw = switch_data(rec)
        vf = (pval(rec, "VF", "V") if s.switch == "igbt" else pval(rec, "VSD", "V")) or 0.0
        drops = (sw.v_on, sw.r_on, vf) if sw.kind != "ideal" else (0.0, 0.0, 0.0)
        st, vl, il, vo, td_eff = self._waves(s, lf, cf, drops, rd, cd)
        v0 = vo[0]
        i0 = il[0]
        a_v = amplitudes(v0)
        # ideal fundamental (closed form)
        if s.modulation == "quadrada":
            v1_id = (4 * vdc / math.pi if s.phases == 1 else 2 * vdc / math.pi) / math.sqrt(2)
            latex = (
                r"V_1 = \frac{4V_{dc}}{\pi\sqrt2}"
                if s.phases == 1
                else r"V_{1,fase} = \frac{2V_{dc}}{\pi\sqrt2}"
            )
            ref = HART8
        elif s.modulation == "quase_quadrada":
            v1_id = square_harmonic(vdc, 1, math.radians(s.alpha_deg)) / math.sqrt(2)
            latex = r"V_n = \frac{4V_{dc}}{n\pi}\cos(n\alpha)"
            ref = HART8
        elif s.phases == 1:
            v1_id = s.ma * vdc / math.sqrt(2)
            latex = r"V_1 = \frac{m_a V_{dc}}{\sqrt2}"
            ref = HART8
        else:
            v1_id = s.ma * vdc / 2 / math.sqrt(2)
            latex = r"V_{1,fase} = \frac{m_a V_{dc}}{2\sqrt2}"
            ref = RASHID6 if s.modulation == "svpwm" else HART8
        log.add(
            record(
                "V1_ideal",
                "Fundamental na saída do inversor (ideal)",
                latex,
                output=Q_(v1_id, "V"),
                inputs={
                    "V_dc": s.Vdc.to_pint(),
                    "m_a": Q_(s.ma, ""),
                    "α": Q_(s.alpha_deg, "degree"),
                },
                assumptions=["modulação linear; chaves ideais; sem tempo morto"]
                + (
                    ["SVPWM: a injeção de sequência zero não altera a fundamental de fase"]
                    if s.modulation == "svpwm"
                    else []
                ),
                reference=ref,
            )
        )
        dvd = vdc * td_eff * fs
        log.add(
            record(
                "dV_dead",
                "Erro médio de tensão por perna devido ao tempo morto",
                r"\Delta V = V_{dc}\,t_d\,f_s\;\mathrm{sgn}(i)",
                output=Q_(dvd, "V"),
                inputs={"t_d": Q_(td_eff, "s").to("us"), "f_s": Q_(fs, "Hz").to("kHz")},
                assumptions=[
                    "tempo morto centrado na borda ideal; o diodo da perna conduz no intervalo"
                ],
                reference=MOHAN8,
            )
        )
        v1 = float(a_v[1]) / math.sqrt(2)
        log.add(
            record(
                "V1",
                "Fundamental na carga (forma de onda sintetizada, FFT)",
                r"V_1 = \frac{|c_1|}{\sqrt2},\; c_n = \frac{2}{N}\sum_k v_k e^{-j n \theta_k}",
                output=Q_(v1, "V"),
                inputs={"N": Q_(N_SAMPLES, ""), "V_1,ideal": Q_(v1_id, "V")},
                assumptions=[
                    "amostragem natural com N pontos por período fundamental",
                    "com o tempo morto e o sinal da corrente de carga"
                    if td_eff > 0
                    else "sem tempo morto",
                ]
                + (["tensão sobre a carga após o filtro LC"] if s.filter else []),
                reference=MOHAN8,
            )
        )
        thd_v = thd(a_v)
        i_load = response(vl[0], w1, R, L, lf, cf, rd, cd)[0]
        po = s.phases * R * rms(i_load) ** 2
        log.add(
            record(
                "THD_v",
                "Distorção harmônica total da tensão na carga",
                r"THD = \frac{\sqrt{\sum_{n\ge2} V_n^2}}{V_1}",
                output=Q_(100 * thd_v, "percent"),
                inputs={"V_1": Q_(v1, "V")},
                assumptions=["todos os harmônicos até N/2 da FFT"],
                reference=HART8,
            )
        )
        log.add(
            record(
                "I_rms",
                "Corrente na carga, harmônico a harmônico",
                r"I_n = \frac{V_n}{|R + j n \omega_1 L|},\; I_{rms} = \sqrt{\sum I_n^2/2}",
                output=Q_(rms(i_load), "A"),
                inputs={"R": s.R.to_pint(), "L": s.L.to_pint(), "f_1": s.f1.to_pint()},
                assumptions=["carga RL linear; trifásico em estrela isolada"],
                reference=HART8,
            )
        )
        sm |= {
            "V1_ideal": Q_(v1_id, "V"),
            "V1": Q_(v1, "V"),
            "dV_dead": Q_(dvd, "V"),
            "V_rms": Q_(rms(v0), "V"),
            "I1": Q_(float(amplitudes(i_load)[1]) / math.sqrt(2), "A"),
            "I_rms": Q_(rms(i_load), "A"),
            "I_pk": Q_(float(np.max(np.abs(i0))), "A"),
            "THD_v": Q_(100 * thd_v, "percent"),
            "THD_i": Q_(100 * thd(amplitudes(i_load)), "percent"),
            "THD_v50": Q_(100 * thd(a_v, N_CHECK), "percent"),
            "THD_i50": Q_(100 * thd(amplitudes(i_load), N_CHECK), "percent"),
            "Po": Q_(po, "W"),
        }
        # dominant harmonics of the load voltage
        top = np.argsort(a_v[2:])[::-1][:5] + 2
        for n in sorted(int(x) for x in top):
            sm[f"Vh_{n}"] = Q_(float(a_v[n]) / math.sqrt(2), "V")
            self.labels.setdefault(f"Vh_{n}", f"Harmônico {n} da tensão (eficaz)")
        # losses
        qrr = pval(rec, "Qrr", "C", ("typ", "max")) or 0.0
        legs_i = il if s.phases == 3 else [il[0], -il[0]]
        ll = leg_losses(
            st[0],
            legs_i[0],
            f1,
            vdc,
            sw.kind,
            sw.v_on,
            sw.r_on,
            vf,
            sw.e_on,
            sw.e_off,
            sw.v_test,
            sw.i_test,
            sw.tr,
            sw.tf,
            qrr,
        )
        n_dev = 4 if s.phases == 1 else 6
        if sw.kind != "ideal":
            log.add(
                record(
                    "P_Q1",
                    "Perdas por chave ao longo do período fundamental",
                    r"P = \frac{1}{T_1}\left[\int (V_{CE} i\ \text{ou}\ R_{on} i^2)\,dt + "
                    r"\sum_{comut.} E(i) + \sum Q_{rr} V_{dc}\right]",
                    output=Q_(ll.per_device, "W"),
                    inputs={
                        "P_cond": Q_(ll.p_cond_sw, "W"),
                        "P_sw": Q_(ll.p_sw, "W"),
                        "P_diodo": Q_(ll.p_cond_d, "W"),
                        "P_rr": Q_(ll.p_rr, "W"),
                        "V_CE(sat) ou R_on": Q_(
                            sw.v_on if sw.kind == "igbt" else sw.r_on,
                            "V" if sw.kind == "igbt" else "ohm",
                        ),
                        "V_F": Q_(vf, "V"),
                        "Q_rr": Q_(qrr, "C").to("nC"),
                    },
                    assumptions=[
                        "energias de comutação escaladas linearmente com V e I do ensaio"
                        if sw.kind == "igbt"
                        else "transições lineares com t_r e t_f do ensaio",
                        "transistor e diodo em antiparalelo no mesmo encapsulamento "
                        "(uma resistência térmica)",
                        "sem perdas no tempo morto além da condução do diodo",
                    ],
                    reference=MOHAN8,
                )
            )
        p_tot = ll.per_device * n_dev
        eta = efficiency_step(log, po, {"chaves": p_tot}, "eta")
        sm |= {
            "P_Q1": Q_(ll.per_device, "W"),
            "P_cond": Q_(ll.p_cond_sw, "W"),
            "P_sw": Q_(ll.p_sw, "W"),
            "P_d": Q_(ll.p_cond_d + ll.p_rr, "W"),
            "eta": Q_(eta, "percent"),
            "I_dc": Q_((po + p_tot) / vdc, "A"),
        }
        kv, ki = ("VCES", "IC") if s.switch == "igbt" else ("VDS", "ID")
        stresses = [
            Stress(
                designator="Q1",
                key=kv,
                label="Tensão do barramento",
                value=QuantityModel(value=vdc, unit="V"),
                calc_step_id="V1_ideal",
            ),
            Stress(
                designator="Q1",
                key=ki,
                label="Corrente de pico",
                value=QuantityModel(value=ll.i_pk, unit="A"),
                calc_step_id="I_rms",
            ),
        ]
        if s.filter:
            ii = il[0]
            self._needs = [
                InductorNeed(
                    "Lf",
                    lf,
                    float(np.max(np.abs(ii))),
                    rms(ii),
                    _ripple(ii, s.mf),
                    fs,
                )
            ]
        else:
            self._needs = []
        traces = {"v_carga": make_trace("V", v0), "i_carga": make_trace("A", i_load)}
        return Analysis(
            log=log,
            stresses=stresses,
            summary=sm,
            losses={"Q1": Q_(ll.per_device, "W")},
            warnings=warnings,
            convergence_keys=("I_rms",),
            traces=traces,
            trace_period=Q_(1 / f1, "s"),
        )

    def finish(
        self,
        spec: BaseModel,
        analysis: Analysis,
        devices: Mapping[str, Device],
        catalogue: Callable[[str], list[ComponentRecord]],
    ) -> None:
        s = _spec(spec)
        if not s.filter:
            return
        self.analyse(spec, devices)
        mag = design_inductors(self._needs, catalogue, _v(s.TA, "degC"))
        merge_magnetics(analysis.log, analysis.summary, analysis.warnings, mag)
        n_dev = 4 if s.phases == 1 else 6
        losses = {"chaves": float(analysis.summary["P_Q1"].m_as("W")) * n_dev}
        losses |= {k: v * s.phases for k, v in mag.losses.items()}
        eta = efficiency_step(
            analysis.log, float(analysis.summary["Po"].m_as("W")), losses, "eta_total"
        )
        analysis.summary["eta"] = Q_(eta, "percent")

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        vdc = _v(s.Vdc, "V")
        f1 = _v(s.f1, "Hz")
        t1 = 1 / f1
        pwm = s.modulation in PWM
        ts = t1 / s.mf
        td = _v(s.dead_time, "s")
        R, L = _v(s.R, "ohm"), _v(s.L, "H")
        rec = devices["Q1"].record if "Q1" in devices else None
        sw = switch_data(rec)
        vf = (pval(rec, "VF", "V") if s.switch == "igbt" else pval(rec, "VSD", "V")) or 0.0
        ron = sw.r_on if sw.kind == "mosfet" and sw.r_on > 0 else 1e-3
        von = sw.v_on if sw.kind == "igbt" else 0.0
        lines = [
            ".subckt QSW d s g",
            f"BQ d s I = (v(g) > 2.5) ? ((v(d,s) > {von:.6g}) ? (v(d,s) - {von:.6g}) / {ron:.6g} : "
            + ("v(d,s) / " + f"{ron:.6g}" if sw.kind == "mosfet" else "0")
            + ") : v(d,s) * 1e-7",
            ".ends",
            ".subckt DAP a k",
            f"BD a k I = (v(a,k) > {vf:.6g}) ? (v(a,k) - {vf:.6g}) / 1m : v(a,k) * 1e-7",
            ".ends",
            f"VDC p 0 DC {vdc:.9g}",
        ]
        if sw.kind == "mosfet":
            # synchronous channel: conducts both ways while on
            lines[1] = f"BQ d s I = (v(g) > 2.5) ? v(d,s) / {ron:.6g} : v(d,s) * 1e-7"
        legs = ["a", "b"] if s.phases == 1 else ["a", "b", "c"]
        tau = L / R
        n_per = int(min(max(6, 6 + 5 * tau / t1), 40))
        # Gate signals: piecewise-linear sources with the exact edges of the modulation
        # (same switching instants as the analysis, so the simulator places breakpoints on
        # them; comparator sources left the edges on arbitrary time steps, and that jitter
        # excited the L-C filter). Dead time: both gates low in a window centred on each edge.
        th = grid(N_SAMPLES)
        st = switching(s.modulation, s.phases, s.ma, s.mf, math.radians(s.alpha_deg), th)
        dead = round(td * f1 * N_SAMPLES)
        for x, sx in zip(legs, st, strict=True):
            win = np.zeros(sx.size, dtype=bool)
            if dead > 0:
                for e in np.nonzero(sx != np.roll(sx, 1))[0]:
                    win[(e - dead // 2 + np.arange(dead)) % sx.size] = True
            up = (sx > 0.5) & ~win
            lo = (sx < 0.5) & ~win
            for name, g in (("gu", up), ("gl", lo)):
                lines.append(f"V{name.upper()}{x} {name}{x} 0 PWL(" + _pwl(g, t1, n_per) + ")")
        for x in legs:
            lines += [
                f"XQU{x} p {x} gu{x} QSW",
                f"XQL{x} {x} 0 gl{x} QSW",
                f"XDU{x} {x} p DAP",
                f"XDL{x} 0 {x} DAP",
                # 100 pF of output capacitance per leg: lets the solver follow the dead-time
                # commutation (it charges in a few ns, nothing at the fundamental)
                f"CO{x} {x} 0 100p",
            ]
        lf = q(summary, "Lf", "H") if s.filter else 0.0
        cf = q(summary, "Cf", "F") if s.filter else 0.0
        rd = q(summary, "Rd", "ohm") if s.filter else 0.0
        cd = q(summary, "Cd", "F") if s.filter else 0.0

        def phase(x: str, end: str) -> list[str]:
            out = []
            node = x
            if s.filter:
                out += [
                    f"LF{x} {x} f{x} {lf:.9g}",
                    f"CF{x} f{x} {'cn' if s.phases == 3 else end} {cf:.9g}",
                    f"RD{x} f{x} d{x} {rd:.9g}",
                    f"CD{x} d{x} {'cn' if s.phases == 3 else end} {cd:.9g}",
                ]
                node = f"f{x}"
            out += [f"RL{x} {node} m{x} {R:.9g}", f"LL{x} m{x} k{x} {L:.9g}", f"VI{x} k{x} {end} 0"]
            return out

        if s.phases == 1:
            lines += phase("a", "b")
            vprobe = "v(fa)-v(b)" if s.filter else "v(a)-v(b)"
        else:
            for x in legs:
                lines += phase(x, "n")
            # a 1 MΩ leak defines the floating star point for the solver
            lines.append("RNG n 0 1meg")
            if s.filter:
                lines.append("RCN cn n 1e-3")
            vprobe = "v(fa)-v(n)" if s.filter else "v(a)-v(n)"
        # the PWL gates put breakpoints on every edge; the step only has to follow the
        # waveforms between them
        step = (ts if pwm else t1 / 200) / 100
        if td > 0:
            step = min(step, td)
        checks = [
            SimCheck(
                quantity="Corrente eficaz na carga",
                summary_key="I_rms",
                metric="rms",
                probe="i(via)",
                tolerance_pct=2.0,
                justification="amostragem natural e tempo morto discretizados",
            ),
            SimCheck(
                quantity="Tensão eficaz na carga",
                summary_key="V_rms",
                metric="rms",
                probe=vprobe,
                tolerance_pct=2.0,
                justification="mesmas formas de onda; quedas nas chaves desprezadas no cálculo",
            ),
            SimCheck(
                quantity="THD da corrente (até a 50ª)",
                summary_key="THD_i50",
                metric="thd",
                probe="i(via)",
                tolerance_pct=10.0,
                justification="harmônicos pequenos: erro relativo maior",
            ),
        ]
        if s.filter:
            checks.append(
                SimCheck(
                    quantity="THD da tensão filtrada (até a 50ª)",
                    summary_key="THD_v50",
                    metric="thd",
                    probe=vprobe,
                    tolerance_pct=10.0,
                    justification="harmônicos pequenos após o filtro",
                )
            )
        return Circuit(
            title=f"{self.id}: {'mono' if s.phases == 1 else 'tri'}fásico, "
            f"{ENUM_LABELS[s.modulation]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=n_per * t1, unit="s"),
            tran_step=QuantityModel(value=step, unit="s"),
            period=QuantityModel(value=t1, unit="s"),
            probes={"v_carga": vprobe, "i_carga": "i(via)"},
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        txt = {
            k: pretty(sm[src])
            for k, src in (("LF", "Lf"), ("CF", "Cf"), ("RD", "Rd"), ("CD", "Cd"))
            if src in sm
        }
        txt.update(VDC=pretty(s.Vdc), R=pretty(s.R), L=pretty(s.L))
        parts = {c.designator: c.part_number for c in result.selection}
        note = f"{'Monofásico' if s.phases == 1 else 'Trifásico'}, {ENUM_LABELS[s.modulation]}"
        flt = s.filter and "Lf" in sm
        return drawings_power.inverter(s.phases, title, s.switch, txt, parts, note, flt)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        sm = result.summary
        rows = []
        if "Lf" in sm:
            rows.append(
                passive(
                    "Lf", "Indutor do filtro", format_eng(sm["Lf"].to_pint()), quantity=s.phases
                )
            )
            rows.append(
                passive(
                    "Cf",
                    "Capacitor do filtro (CA)",
                    format_eng(sm["Cf"].to_pint()),
                    "filme de polipropileno",
                    s.phases,
                )
            )
        rows.append(
            passive(
                "Cdc",
                "Capacitor do barramento CC",
                "(dimensionar pela ondulação)",
                f"tensão ≥ {1.25 * s.Vdc.value:.0f} V",
            )
        )
        return rows


def _pwl(g: np.ndarray, t1: float, n_per: int, v: float = 5.0, edge: float = 10e-9) -> str:
    """PWL points of a periodic logic signal (samples over one period) repeated n_per times."""
    n = g.size
    gi = g.astype(np.int8)
    idx = np.nonzero(gi != np.roll(gi, 1))[0]
    pts = [f"0 {v * gi[0]:g}"]
    for k in range(n_per):
        for e in idx:
            t = (k + e / n) * t1
            if t <= 0:
                continue
            before = v * gi[e - 1]
            pts.append(f"{t:.10g} {before:g} {t + edge:.10g} {v * gi[e]:g}")
    return " ".join(pts)


def _ripple(i: np.ndarray, mf: int) -> float:
    """Largest peak-to-peak ripple inside one carrier period."""
    n = i.size // mf
    return float(max(np.ptp(i[k * n : (k + 1) * n]) for k in range(mf)))
