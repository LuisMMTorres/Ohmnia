"""DM-RET3 design module: three-phase rectifiers of 3, 6 and 12 pulses with commutation."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pint
from pydantic import BaseModel, Field, model_validator

from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.base import (
    Circuit,
    DesignWarning,
    PowerPort,
    Role,
    SimCheck,
    Stress,
    make_trace,
)
from circuitos.design.engine import Analysis, Device
from circuitos.design.loadspec import LoadBy
from circuitos.design.measure import scale
from circuitos.design.plugins.retc1.module import diode_model, scr_model

from . import model as m
from .model import Pulses

HART_3F = BibRef(
    book="Hart, Power Electronics",
    edition="1st",
    chapter="4 (three-phase rectifiers, controlled three-phase rectifiers, commutation)",
)
MOHAN_3F = BibRef(
    book="Mohan, Undeland, Robbins, Power Electronics",
    edition="3rd",
    chapter="6 (line-frequency phase-controlled rectifiers; effect of Ls)",
)

LABEL = {
    3: "3 pulsos (estrela, ponto médio)",
    6: "6 pulsos (ponte de Graetz)",
    12: "12 pulsos (duas pontes em série, secundários Y e Δ)",
}


class Ret3Spec(BaseModel):
    pulses: Pulses = 6
    controlled: bool = True
    Vin: QuantityModel = QuantityModel(value=380, unit="V")  # primary line-to-line, RMS
    f: QuantityModel = QuantityModel(value=60, unit="Hz")
    # secondary line-to-line, RMS (12 pulses: each bridge)
    Vsec: QuantityModel = QuantityModel(value=220, unit="V")
    load_by: LoadBy = "potencia"  # which load quantity the user gives: P or the current
    P: QuantityModel = QuantityModel(value=2500, unit="W")  # load power (DC current, L ≫)
    Io: QuantityModel = QuantityModel(value=10, unit="A")  # load current (DC, L ≫)
    E: QuantityModel = QuantityModel(value=0, unit="V")  # counter-EMF of the load
    Ls: QuantityModel = QuantityModel(value=0.5, unit="mH")  # per phase, secondary side
    alpha_nom: QuantityModel = QuantityModel(value=30, unit="deg")
    vin_tol_pct: float = Field(default=10.0, ge=0, le=30)
    TA: QuantityModel = QuantityModel(value=40, unit="degC")
    Rth_cs: QuantityModel = QuantityModel(value=0.5, unit="K/W")

    @model_validator(mode="after")
    def _check(self) -> Ret3Spec:
        a = self.alpha_nom.to_pint().m_as("deg")
        if self.controlled and not 0 <= a < 90:
            raise ValueError("α nominal deve estar entre 0° e 90° (modo retificador)")
        if self.Vsec.to_pint().m_as("V") <= 0:
            raise ValueError("A tensão do secundário deve ser positiva")
        if self.load_by == "corrente":
            if self.Io.to_pint().m_as("A") <= 0:
                raise ValueError("A corrente da carga deve ser positiva")
        elif self.P.to_pint().m_as("W") <= 0:
            raise ValueError("A potência da carga deve ser positiva")
        return self

    def alpha(self) -> float:
        return math.radians(self.alpha_nom.to_pint().m_as("deg")) if self.controlled else 0.0


def _spec(spec: BaseModel) -> Ret3Spec:
    if not isinstance(spec, Ret3Spec):
        raise TypeError("DM-RET3 espera Ret3Spec")
    return spec


def _designator(s: Ret3Spec) -> str:
    n = {3: 3, 6: 6, 12: 12}[s.pulses]
    return f"{'T' if s.controlled else 'D'}1–{'T' if s.controlled else 'D'}{n}"


class Ret3Module:
    id = "DM-RET3"
    family = "retificadores"
    title = "Retificador trifásico"
    spec_schema = Ret3Spec
    spec_labels = {"Vin": "Tensão de linha do primário (eficaz)"}

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        return [
            Role(
                designator=_designator(s),
                category="thyristor.scr" if s.controlled else "diode",
                description="Tiristores (SCR)" if s.controlled else "Diodos retificadores",
                count=s.pulses,
            )
        ]

    def required_ratings(self, role: Role) -> list[str]:
        if role.category.startswith("thyristor"):
            return ["VDRM", "VRRM", "IT(RMS)"]
        return ["VRRM", "IF(AV)"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).Rth_cs.to_pint()

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        p = s.pulses
        des = _designator(s)
        VT = devices[des].drop.m_as("V")
        f = s.f.to_pint().m_as("Hz")
        w = 2 * math.pi * f
        Ls = s.Ls.to_pint().m_as("H")
        P = s.P.to_pint().m_as("W")
        E = s.E.to_pint().m_as("V")
        a = s.alpha()
        log = CalcLog()
        warnings: list[DesignWarning] = []
        ref = HART_3F
        n_drop = {3: 1, 6: 2, 12: 4}[p]
        k_v = {3: r"\frac{3}{2\pi}", 6: r"\frac{3}{\pi}", 12: r"\frac{6}{\pi}"}[p]
        k_x = {
            3: r"\frac{3\omega L_s}{2\pi}",
            6: r"\frac{3\omega L_s}{\pi}",
            12: r"\frac{6\omega L_s}{\pi}",
        }[p]
        Vll_m = log.add(
            record(
                "Vll_m",
                "Tensão de linha de pico do secundário" + (" (cada ponte)" if p == 12 else ""),
                r"V_{LL,m} = \sqrt{2}\,V_{LL,sec}",
                output=Q_(math.sqrt(2) * s.Vsec.to_pint().m_as("V"), "V"),
                inputs={"V_{LL,sec}": s.Vsec.to_pint()},
                assumptions=["fonte trifásica equilibrada e senoidal", "transformador ideal"],
                reference=ref,
            )
        ).m_as("V")
        # Vo = V0 − kx·Io (closed form, linear in Io) and P = Vo·Io: the smaller root of
        # kx·Io² − V0·Io + P = 0 is the operating point (the other one is past maximum power)
        v0 = m.mean_output(p, Vll_m, a, 0.0, Ls, f, VT)
        kx = v0 - m.mean_output(p, Vll_m, a, 1.0, Ls, f, VT)
        if v0 <= E or v0 <= 0:
            raise ValueError(
                "Com essa tensão do secundário e esse α, a tensão média não supera E: "
                "aumente V_sec ou reduza α"
            )
        if s.load_by == "corrente":
            io_val = s.Io.to_pint().m_as("A")
            if v0 - kx * io_val <= 0:
                raise ValueError(
                    "Com essa corrente a queda por comutação anula a tensão média: "
                    "aumente V_sec, reduza L_s ou reduza a corrente"
                )
        elif kx > 1e-12:
            disc = v0 * v0 - 4 * kx * P
            if disc < 0:
                raise ValueError(
                    "Potência acima do máximo que esse secundário entrega com L_s "
                    f"({format_eng(Q_(v0 * v0 / (4 * kx), 'W'))}): aumente V_sec ou reduza L_s"
                )
            io_val = (v0 - math.sqrt(disc)) / (2 * kx)
        else:
            io_val = P / v0
        Io = log.add(
            record(
                "Io",
                "Corrente na carga pedida (dada pelo usuário)",
                r"I_o = I_{o,pedida}",
                output=Q_(io_val, "A"),
                inputs={"I_{o,pedida}": s.Io.to_pint()},
                assumptions=["corrente de carga constante (indutância da carga grande)"],
                reference=ref,
            )
            if s.load_by == "corrente"
            else record(
                "Io",
                "Corrente na carga que entrega a potência pedida",
                rf"P = V_o I_o,\quad V_o = {k_v} V_{{LL,m}}\cos\alpha - {k_x} I_o - n V_T"
                rf"\Rightarrow {k_x} I_o^2 - V_{{o0}} I_o + P = 0",
                output=Q_(io_val, "A"),
                inputs={
                    "P": s.P.to_pint(),
                    "V_{o0}": Q_(v0, "V"),
                    "L_s": s.Ls.to_pint(),
                    r"\alpha": Q_(math.degrees(a), "deg"),
                    "n V_T": Q_(n_drop * VT, "V"),
                },
                assumptions=[
                    "corrente de carga constante (indutância da carga grande)",
                    "L_s por fase do lado do secundário",
                    "dispositivos como queda constante",
                    "raiz menor: ponto de operação abaixo da potência máxima",
                ],
                reference=ref,
            )
        ).m_as("A")
        Vo = v0 - kx * Io
        if Vo <= E:
            raise ValueError(
                "A tensão média na carga ficou menor que E: reduza "
                + ("a corrente" if s.load_by == "corrente" else "a potência")
            )
        mu = m.overlap_angle(a, Io, Ls, Vll_m, f)
        log.add(
            record(
                "mu",
                "Ângulo de comutação (sobreposição)",
                r"\cos\alpha - \cos(\alpha + \mu) = \frac{2\omega L_s I_o}{V_{LL,m}}",
                output=Q_(math.degrees(mu), "deg"),
                inputs={
                    r"\omega L_s": Q_(w * Ls, "ohm"),
                    "I_o": Q_(Io, "A"),
                    "V_{LL,m}": Q_(Vll_m, "V"),
                },
                reference=MOHAN_3F,
            )
        )
        dv_mu = {3: 3 / (2 * math.pi), 6: 3 / math.pi, 12: 6 / math.pi}[p] * w * Ls * Io
        log.add(
            record(
                "dV_mu",
                "Queda de tensão média causada pela comutação",
                rf"\Delta V_\mu = {k_x} I_o",
                output=Q_(dv_mu, "V"),
                inputs={"L_s": s.Ls.to_pint(), "I_o": Q_(Io, "A")},
                reference=MOHAN_3F,
            )
        )
        wv = m.waves(p, Vll_m, a, Io, Ls, f, VT)
        vo_avg, vo_rms = m.mean(wv.vo), m.rms(wv.vo)
        ripple = float(np.ptp(wv.vo))
        log.add(
            record(
                "Vo",
                "Tensão média na saída (forma de onda do modelo)",
                r"V_o = \frac{1}{2\pi}\int_0^{2\pi} v_o\,d\theta",
                output=Q_(vo_avg, "V"),
                inputs={"V_{LL,m}": Q_(Vll_m, "V")},
                reference=ref,
            )
        )
        log.add(
            record(
                "Vo_rms",
                "Tensão eficaz na saída",
                r"V_{o,ef} = \sqrt{\overline{v_o^2}}",
                output=Q_(vo_rms, "V"),
                inputs={},
                reference=ref,
            )
        )
        log.add(
            record(
                "dVo",
                "Ondulação de pico a pico da tensão de saída",
                r"\Delta V_o = v_{o,max} - v_{o,min}",
                output=Q_(ripple, "V"),
                inputs={},
                reference=ref,
            )
        )
        R = (Vo - s.E.to_pint().m_as("V")) / Io
        log.add(
            record(
                "R_load",
                "Resistência equivalente da carga",
                r"R = \frac{V_o - E}{I_o}",
                output=Q_(R, "ohm"),
                inputs={"V_o": Q_(Vo, "V"), "E": s.E.to_pint(), "I_o": Q_(Io, "A")},
                reference=ref,
            )
        )
        # α range under mains variation
        tol = s.vin_tol_pct / 100
        summary: dict[str, pint.Quantity] = {}
        if s.controlled:
            amin = _alpha_for(p, Vll_m * (1 - tol), Vo, Io, Ls, f, VT)
            amax = _alpha_for(p, Vll_m * (1 + tol), Vo, Io, Ls, f, VT)
            if amin is None:
                warnings.append(
                    DesignWarning(
                        code="sem_reserva",
                        message=f"Com a rede {s.vin_tol_pct:g} % abaixo do nominal, nem α = 0° "
                        "alcança Vo: aumente α nominal ou a tensão do secundário.",
                    )
                )
            else:
                summary["alpha_min"] = Q_(math.degrees(amin), "deg")
            if amax is not None:
                summary["alpha_max"] = Q_(math.degrees(amax), "deg")
                if amin is not None:
                    log.add(
                        record(
                            "alpha_range",
                            f"Faixa de α para a rede variando ±{s.vin_tol_pct:g} %",
                            r"V_o\left(V_{LL,m}(1 \pm \delta), \alpha\right) = V_o",
                            output=Q_(math.degrees(amax - amin), "deg"),
                            inputs={
                                r"\alpha_{min}": Q_(math.degrees(amin), "deg"),
                                r"\alpha_{max}": Q_(math.degrees(amax), "deg"),
                            },
                            reference=ref,
                        )
                    )
        # devices
        i_dev = wv.bridges[0].i_dev
        id_avg, id_rms = m.mean(i_dev), m.rms(i_dev)
        log.add(
            record(
                "I_dev_avg",
                "Corrente média em cada dispositivo",
                r"I_{med} = \frac{I_o}{3}",
                output=Q_(id_avg, "A"),
                inputs={"I_o": Q_(Io, "A")},
                reference=ref,
            )
        )
        log.add(
            record(
                "I_dev_rms",
                "Corrente eficaz em cada dispositivo",
                r"I_{ef} = \sqrt{\overline{i^2}} \approx \frac{I_o}{\sqrt{3}}",
                output=Q_(id_rms, "A"),
                inputs={"I_o": Q_(Io, "A")},
                assumptions=["calculada na forma de onda trapezoidal (com μ)"],
                reference=ref,
            )
        )
        log.add(
            record(
                "V_block",
                "Tensão de bloqueio máxima em cada dispositivo",
                r"V_{DRM} = V_{RRM} = V_{LL,m}",
                output=Q_(Vll_m, "V"),
                inputs={"V_{LL,m}": Q_(Vll_m, "V")},
                assumptions=["α percorre toda a faixa; picos de comutação (notches) desprezados"],
                reference=ref,
            )
        )
        if s.controlled:
            keys = [
                ("VDRM", "Tensão direta de bloqueio", Vll_m, "V", "V_block"),
                ("VRRM", "Tensão reversa", Vll_m, "V", "V_block"),
                ("IT(AV)", "Corrente média", id_avg, "A", "I_dev_avg"),
                ("IT(RMS)", "Corrente eficaz", id_rms, "A", "I_dev_rms"),
            ]
        else:
            keys = [
                ("VRRM", "Tensão reversa de pico", Vll_m, "V", "V_block"),
                ("IF(AV)", "Corrente média", id_avg, "A", "I_dev_avg"),
            ]
        stresses = [
            Stress(
                designator=des,
                key=k,
                label=lbl,
                value=QuantityModel(value=v, unit=u),
                calc_step_id=sid,
            )
            for k, lbl, v, u, sid in keys
        ]
        losses = {des: Q_(VT * id_avg, "W")}
        if VT > 0:
            log.add(
                record(
                    f"P_{des}",
                    f"Perda em condução em cada dispositivo ({des})",
                    r"P = V_T\,I_{med}",
                    output=Q_(VT * id_avg, "W"),
                    inputs={"V_T": Q_(VT, "V"), "I_{med}": Q_(id_avg, "A")},
                    assumptions=["queda constante do datasheet (conservador)"],
                    reference=ref,
                )
            )
        # input side and transformer
        Vin = s.Vin.to_pint().m_as("V")
        Vll = Vll_m / math.sqrt(2)
        N = Vin / Vll
        i_line_rms = m.rms(wv.bridges[0].i_line[0])
        pf, dpf, thd_i = m.power_factor(wv), m.displacement_factor(wv), m.thd(wv.i_ref[0])
        va_sec = sum(3 * m.rms(b.e[0]) * m.rms(b.i_line[0]) for b in wv.bridges)
        ref_rms = m.rms(wv.i_ref[0])
        va_pri = 3 * m.rms(wv.e[0]) * ref_rms
        rows = [
            (
                "Vll_sec",
                "Tensão de linha eficaz do secundário" + (" (Y e Δ)" if p == 12 else ""),
                r"V_{LL} = V_{LL,m}/\sqrt{2}",
                Vll,
                "V",
            ),
            ("N", "Relação de tensões de linha primário : secundário", r"N = V_{in}/V_{LL}", N, ""),
            (
                "I_line",
                "Corrente de linha eficaz do secundário" + (" (cada ponte)" if p == 12 else ""),
                r"I_{L} = \sqrt{\overline{i_a^2}}",
                i_line_rms,
                "A",
            ),
            (
                "VA_sec",
                "Potência aparente dos secundários",
                r"S_{sec} = \sum 3 V_{f} I_{L}",
                va_sec,
                "V*A",
            ),
            ("VA_pri", "Potência aparente do primário", r"S_{pri} = 3 V_f I_{pri}", va_pri, "V*A"),
            ("PF", "Fator de potência na entrada", r"FP = \frac{P}{S_{pri}}", pf, ""),
            (
                "DPF",
                "Fator de deslocamento",
                r"FD = \cos\varphi_1 \approx \cos(\alpha + \mu/2)",
                dpf,
                "",
            ),
            (
                "THD_i",
                "Distorção harmônica total da corrente de linha do primário",
                r"THD_i = \frac{\sqrt{\sum_{h\ge2} I_h^2}}{I_1}",
                thd_i * 100,
                "percent",
            ),
        ]
        for sid, desc, latex, val, unit in rows:
            log.add(record(sid, desc, latex, output=Q_(val, unit), inputs={}, reference=ref))
        if p == 3:
            warnings.append(
                DesignWarning(
                    code="cc_no_transformador",
                    message=f"3 pulsos: cada fase do secundário conduz corrente média de "
                    f"{format_eng(Q_(Io / 3, 'A'))}; use primário em Δ ou secundário em "
                    "zigue-zague para não "
                    "saturar o núcleo.",
                )
            )
        if mu > math.radians(30):
            warnings.append(
                DesignWarning(
                    code="comutacao_longa",
                    message=f"μ = {f'{math.degrees(mu):.1f}'.replace('.', ',')}°: a comutação "
                    "ocupa boa parte do pulso; "
                    "o modelo continua válido, mas confira a queda e os entalhes na rede.",
                )
            )
        summary.update(
            {
                "Vll_m": Q_(Vll_m, "V"),
                "Vll_sec": Q_(Vll, "V"),
                "N": Q_(N, ""),
                "Vo": Q_(vo_avg, "V"),
                "Vo_rms": Q_(vo_rms, "V"),
                "dVo": Q_(ripple, "V"),
                "Io": Q_(Io, "A"),
                "R_load": Q_(R, "ohm"),
                "mu": Q_(math.degrees(mu), "deg"),
                "dV_mu": Q_(dv_mu, "V"),
                "alpha": Q_(math.degrees(a), "deg"),
                "I_dev_avg": Q_(id_avg, "A"),
                "I_dev_rms": Q_(id_rms, "A"),
                "V_block": Q_(Vll_m, "V"),
                "I_line": Q_(i_line_rms, "A"),
                "I_pri_ref": Q_(ref_rms, "A"),
                "VA_sec": Q_(va_sec, "V*A"),
                "VA_pri": Q_(va_pri, "V*A"),
                "PF": Q_(pf, ""),
                "DPF": Q_(dpf, ""),
                "THD_i": Q_(thd_i * 100, "percent"),
                "P_out": Q_(vo_avg * Io, "W"),
            }
        )
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses=losses,
            warnings=warnings,
            convergence_keys=("Vll_m", "Vo"),
            traces={
                "Tensão na saída": make_trace("V", wv.vo),
                "Corrente na carga": make_trace("A", np.full_like(wv.vo, Io)),
                "Corrente de linha (fase a)": make_trace("A", wv.bridges[0].i_line[0]),
                "Tensão de fase a (fonte)": make_trace("V", wv.e[0]),
            },
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        """Same model as the analysis, except the load: R in series with L = 30·R/ω (and E),
        so the load current is nearly constant (the analysis assumes it constant)."""
        s = _spec(spec)
        p = s.pulses
        des = _designator(s)
        VT = devices[des].drop.m_as("V")
        Vll_m = summary["Vll_m"].to_pint().m_as("V")
        f = s.f.to_pint().m_as("Hz")
        T = 1 / f
        w = 2 * math.pi * f
        Ls = s.Ls.to_pint().m_as("H")
        a = math.degrees(s.alpha())
        R = summary["R_load"].to_pint().m_as("ohm")
        E = s.E.to_pint().m_as("V")
        L = 30 * R / w
        vph = Vll_m / math.sqrt(3)
        lines = [scr_model(VT), diode_model(VT)]
        n_dev = 0
        gates: list[str] = []

        def device(anode: str, cathode: str, natural_deg: float) -> str:
            nonlocal n_dev
            n_dev += 1
            if not s.controlled:
                return f"XD{n_dev} {anode} {cathode} DIODE"
            td = ((natural_deg + a) % 360) / 360 * T
            gates.append(
                f"VG{n_dev} g{n_dev} 0 PULSE(0 1 {td:.9g} 10u 10u {T / 3 * 0.95:.9g} {T:.9g})"
            )
            return f"XT{n_dev} {anode} {cathode} g{n_dev} SCR"

        def sources(tag: str, shift_deg: float, neutral: str) -> list[str]:
            out = []
            for k, ph in enumerate("abc"):
                phase = -(shift_deg + 120 * k)
                node = f"{ph}{tag}"
                src = f"{node}s"
                out.append(f"VS{ph}{tag} {src} {neutral} SIN(0 {vph:.9g} {f:.9g} 0 0 {phase:.9g})")
                if Ls > 0:
                    out.append(f"LS{ph}{tag} {src} {node}l {Ls:.9g}")
                    out.append(f"VI{ph}{tag} {node}l {node} 0")
                else:
                    out.append(f"VI{ph}{tag} {src} {node} 0")
            return out

        def six(tag: str, shift_deg: float, pos: str, neg: str) -> list[str]:
            out = []
            for k, ph in enumerate("abc"):
                out.append(device(f"{ph}{tag}", pos, 30 + shift_deg + 120 * k))
                out.append(device(neg, f"{ph}{tag}", 210 + shift_deg + 120 * k))
            return out

        if p == 3:
            lines += sources("1", 0, "0")
            for k, ph in enumerate("abc"):
                lines.append(device(f"{ph}1", "p", 30 + 120 * k))
            out_pos, out_neg = "p", "0"
        elif p == 6:
            lines += sources("1", 0, "0") + six("1", 0, "p", "n")
            out_pos, out_neg = "p", "n"
        else:
            lines += sources("1", 0, "0") + six("1", 0, "p", "m")
            lines += [*sources("2", 30, "nn2"), "RNN2 nn2 0 1Meg", *six("2", 30, "m", "n")]
            out_pos, out_neg = "p", "n"
        lines += gates
        # 10 MΩ from every node to ground: the series bridges leave nodes floating while the
        # devices are off (15 µA at 150 V, negligible)
        lines.append(".options rshunt=1e7")
        lines += [f"RL {out_pos} x {R:.9g}", f"LL x y {L:.9g}", f"VE y {out_neg} {E:.9g}"]
        if out_neg != "0":
            lines.append(f"RREF {out_neg} 0 1Meg")
        v_out = f"v({out_pos})" if out_neg == "0" else f"v({out_pos})-v({out_neg})"
        i_ref = "i(via1)"
        if p == 12:  # primary phase A referred to the Y secondary (ampere-turns)
            kd = 1 / math.sqrt(3)
            i_ref = f"i(via1)+{kd:.6f}*i(via2)-{kd:.6f}*i(vib2)"
        exact = "modelo com Io constante; no simulador a carga é R + L = 30R/ω"
        checks = [
            SimCheck(
                quantity="Tensão média na saída",
                summary_key="Vo",
                metric="avg",
                probe=v_out,
                tolerance_pct=1.0,
                justification=exact,
            ),
            SimCheck(
                quantity="Corrente média na carga",
                summary_key="Io",
                metric="avg",
                probe="i(ve)",
                tolerance_pct=1.0,
                justification=exact,
            ),
            SimCheck(
                quantity="Corrente de linha eficaz",
                summary_key="I_line",
                metric="rms",
                probe="i(via1)",
                tolerance_pct=2.0,
                justification=exact,
            ),
            SimCheck(
                quantity="Fator de potência",
                summary_key="PF",
                metric="pf",
                probe=i_ref,
                voltage="v(a1s)",
                tolerance_pct=2.0,
                justification=exact,
            ),
            SimCheck(
                quantity="THD da corrente de linha",
                summary_key="THD_i",
                metric="thd",
                probe=i_ref,
                tolerance_pct=10.0,
                justification=exact + "; a ondulação residual de Io altera as harmônicas",
            ),
        ]
        probes = {
            "Tensão na saída": v_out,
            "Corrente na carga": "i(ve)",
            "Corrente de linha (fase a)": "i(via1)",
            "Tensão de fase a (fonte)": "v(a1s)",
        }
        # ideal transformer, Y-Y equivalent: line quantities of the primary referred by N
        n_ratio = s.Vin.to_pint().m_as("V") / (Vll_m / math.sqrt(2))
        dev = "T" if s.controlled else "D"
        probes |= {
            "Tensão de linha ab do secundário": "v(a1s)-v(b1s)",
            "Tensão de linha ab do primário": scale("v(a1s)-v(b1s)", n_ratio),
            "Corrente de linha do primário (fase a)": scale(i_ref, 1 / n_ratio),
            f"Tensão em {dev}1 (anodo − catodo)": "v(a1)-v(p)",
        }
        powers = {
            "Secundário, fase a (× 3 para o total)": PowerPort(voltage="v(a1s)", current="i(via1)"),
            "Carga": PowerPort(voltage=v_out, current="i(ve)"),
        }
        return Circuit(
            title=f"{self.id}: {LABEL[p]}" + (f", α = {a:g}°" if s.controlled else ", a diodos"),
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=35 * T, unit="s"),
            tran_step=QuantityModel(value=T / 8000, unit="s"),
            period=QuantityModel(value=T, unit="s"),
            probes=probes,
            checks=checks,
            powers=powers,
        )


def _alpha_for(
    p: Pulses, Vll_m: float, Vo: float, Io: float, Ls: float, f: float, VT: float
) -> float | None:
    """α giving Vo with the closed form (exact in this model); None if α = 0 is not enough."""
    w = 2 * math.pi * f
    k = {3: 3 / (2 * math.pi), 6: 3 / math.pi, 12: 6 / math.pi}[p]
    n = {3: 1, 6: 2, 12: 4}[p]
    c = (Vo + k * w * Ls * Io + n * VT) / (k * Vll_m)
    if c > 1:
        return None
    return math.acos(max(c, -1.0))
