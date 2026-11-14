"""DM-RETC1 design module: single-phase controlled and semicontrolled rectifiers."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pint
from pydantic import BaseModel, Field, model_validator
from scipy.optimize import brentq

from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.base import Circuit, DesignWarning, Role, SimCheck, Stress, make_trace
from circuitos.design.engine import Analysis, Device

from . import model as m
from .model import Topology

HART_CTRL = BibRef(
    book="Hart, Power Electronics",
    edition="1st",
    chapter="3 (controlled half-wave rectifier) and 4 (controlled full-wave rectifiers)",
)

TOPOLOGY_LABEL = {
    "meia_onda": "meia onda controlada",
    "ponte": "ponte totalmente controlada",
    "semicontrolada": "ponte semicontrolada",
}


class Retc1Spec(BaseModel):
    topology: Topology = "ponte"
    freewheel: bool = False  # half wave only: freewheeling diode across the load
    Vin: QuantityModel = QuantityModel(value=127, unit="V")  # primary, RMS
    f: QuantityModel = QuantityModel(value=60, unit="Hz")
    R: QuantityModel = QuantityModel(value=10, unit="ohm")
    L: QuantityModel = QuantityModel(value=100, unit="mH")
    E: QuantityModel = QuantityModel(value=0, unit="V")
    Vo: QuantityModel = QuantityModel(value=60, unit="V")  # mean load voltage at α nominal
    alpha_nom: QuantityModel = QuantityModel(value=30, unit="deg")
    vin_tol_pct: float = Field(default=10.0, ge=0, le=30)  # mains variation for the α range
    TA: QuantityModel = QuantityModel(value=40, unit="degC")
    Rth_cs: QuantityModel = QuantityModel(value=0.5, unit="K/W")

    @model_validator(mode="after")
    def _check(self) -> Retc1Spec:
        a = self.alpha_nom.to_pint().m_as("deg")
        if not 0 <= a < 180:
            raise ValueError("α nominal deve estar entre 0° e 180°")
        if self.freewheel and self.topology != "meia_onda":
            raise ValueError("Diodo de roda livre só se aplica à meia onda")
        return self


def _spec(spec: BaseModel) -> Retc1Spec:
    if not isinstance(spec, Retc1Spec):
        raise TypeError("DM-RETC1 espera Retc1Spec")
    return spec


def _scr_designator(topo: Topology) -> str:
    return {"meia_onda": "T1", "ponte": "T1–T4", "semicontrolada": "T1–T2"}[topo]


def _diode_designator(s: Retc1Spec) -> str | None:
    if s.topology == "semicontrolada":
        return "D1–D2"
    if s.topology == "meia_onda" and s.freewheel:
        return "D1"
    return None


class Retc1Module:
    id = "DM-RETC1"
    family = "retificadores"
    title = "Retificador monofásico controlado"
    spec_schema = Retc1Spec

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        n = {"meia_onda": 1, "ponte": 4, "semicontrolada": 2}[s.topology]
        roles = [
            Role(
                designator=_scr_designator(s.topology),
                category="thyristor.scr",
                description="Tiristores (SCR)",
                count=n,
            )
        ]
        d = _diode_designator(s)
        if d:
            roles.append(
                Role(
                    designator=d,
                    category="diode",
                    description="Diodo de roda livre" if s.freewheel else "Diodos da ponte",
                    count=1 if s.freewheel else 2,
                )
            )
        return roles

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
        topo = s.topology
        log = CalcLog()
        warnings: list[DesignWarning] = []
        ref = HART_CTRL
        t_des = _scr_designator(topo)
        d_des = _diode_designator(s)
        VT = devices[t_des].drop.m_as("V")
        VD = devices[d_des].drop.m_as("V") if d_des else 0.0
        f = s.f.to_pint().m_as("Hz")
        w = 2 * math.pi * f
        ld = m.Load(
            R=s.R.to_pint().m_as("ohm"), L=s.L.to_pint().m_as("H"), E=s.E.to_pint().m_as("V")
        )
        Vo = s.Vo.to_pint().m_as("V")
        alpha = math.radians(s.alpha_nom.to_pint().m_as("deg"))
        if Vo <= ld.E:
            raise ValueError("Vo deve ser maior que a força contraeletromotriz E")
        drop = m.forward_drop(topo, VT, VD)

        def vo_at(vm: float, a: float) -> float:
            sol = m.solve(topo, vm, a, ld, f, VT, VD, s.freewheel)
            return m.mean(m.waves(sol).vo) if sol.fired else ld.E

        lo = (drop + ld.E) / max(math.sin(alpha), 1e-3) * 1.0001 + 1e-6
        hi = lo + 20 * Vo + 100
        if vo_at(hi, alpha) < Vo:
            raise ValueError("Não há tensão de pico que produza Vo com esse α")
        Vm = float(brentq(lambda v: vo_at(v, alpha) - Vo, lo, hi, xtol=1e-9))
        sol = m.solve(topo, Vm, alpha, ld, f, VT, VD, s.freewheel)
        wv = m.waves(sol)
        load_inputs = {"R": s.R.to_pint(), "L": s.L.to_pint(), "E": s.E.to_pint()}
        log.add(
            record(
                "Vm",
                "Tensão de pico do secundário para Vo em α nominal (modelo exato)",
                r"\omega L\frac{di}{d\theta} + Ri = V_m\sin\theta - V_{quedas} - E;\quad "
                r"\overline{v_o}(V_m, \alpha_{nom}) = V_o",
                output=Q_(Vm, "V"),
                inputs={
                    "V_o": s.Vo.to_pint(),
                    r"\alpha_{nom}": s.alpha_nom.to_pint(),
                    "V_{quedas}": Q_(drop, "V"),
                    **load_inputs,
                },
                assumptions=[
                    "tiristores e diodos como quedas constantes",
                    "fonte e transformador ideais (sem indutância de comutação)",
                    "solução analítica por trechos; β e o regime periódico por busca de raiz",
                ],
                reference=ref,
            )
        )
        mode = "contínua" if sol.continuous else "descontínua"
        log.add(
            record(
                "modo",
                f"Condução {mode} da corrente de carga",
                r"i_o(\alpha + T_{saída}) = i_o(\alpha) > 0 \Rightarrow \text{contínua}",
                output=Q_(1.0 if sol.continuous else 0.0, ""),
                inputs={r"\omega L/R": Q_(w * ld.L / ld.R, "")},
                assumptions=["1 = contínua, 0 = descontínua"],
                reference=ref,
            )
        )
        if sol.beta is not None:
            log.add(
                record(
                    "beta",
                    "Ângulo de extinção da corrente",
                    r"i_o(\beta) = 0:\ \frac{V_m}{Z}\sin(\beta - \varphi) - \frac{V_{quedas}+E}{R}"
                    r" + A\,e^{-(\beta-\alpha)/\omega\tau} = 0",
                    output=Q_(math.degrees(sol.beta), "deg"),
                    inputs={
                        "Z": Q_(math.hypot(ld.R, w * ld.L), "ohm"),
                        r"\varphi": Q_(math.degrees(math.atan2(w * ld.L, ld.R)), "deg"),
                    },
                    reference=ref,
                )
            )
        # closed form with ideal devices, for comparison in the audit trail
        ideal_sol = m.solve(topo, Vm, alpha, ld, f, 0.0, 0.0, s.freewheel)
        if ideal_sol.continuous and topo != "meia_onda":
            v_ideal = m.ideal_average_continuous(topo, Vm, alpha)
            latex = (
                r"V_o = \frac{2V_m}{\pi}\cos\alpha"
                if topo == "ponte"
                else r"V_o = \frac{V_m}{\pi}(1 + \cos\alpha)"
            )
        elif ideal_sol.beta is not None and not (topo == "meia_onda" and s.freewheel):
            v_ideal = m.ideal_average_discontinuous(topo, Vm, alpha, ideal_sol.beta, ld.E)
            latex = (
                r"V_o = \frac{pV_m}{2\pi}(\cos\alpha - \cos\beta) + E\,"
                r"\frac{2\pi/p - (\beta - \alpha)}{2\pi/p}"
            )
        else:
            v_ideal = m.mean(m.waves(ideal_sol).vo)
            latex = r"V_o = \frac{1}{2\pi}\int_0^{2\pi} v_o\,d\theta"
        log.add(
            record(
                "Vo_ideal",
                "Tensão média com dispositivos ideais (forma fechada, para comparação)",
                latex,
                output=Q_(v_ideal, "V"),
                inputs={"V_m": Q_(Vm, "V"), r"\alpha": s.alpha_nom.to_pint()},
                assumptions=["quedas nulas"],
                reference=ref,
            )
        )
        vo_avg, vo_rms = m.mean(wv.vo), m.rms(wv.vo)
        io_avg, io_rms = m.mean(wv.io), m.rms(wv.io)
        di = float(np.ptp(wv.io))
        log.add(
            record(
                "Vo",
                "Tensão média na carga (modelo)",
                r"V_o = \frac{1}{2\pi}\int_0^{2\pi} v_o\,d\theta",
                output=Q_(vo_avg, "V"),
                inputs={"V_m": Q_(Vm, "V")},
                reference=ref,
            )
        )
        log.add(
            record(
                "Io",
                "Corrente média na carga",
                r"I_o = \frac{V_o - E}{R}",
                output=Q_(io_avg, "A"),
                inputs={"V_o": Q_(vo_avg, "V"), "E": s.E.to_pint(), "R": s.R.to_pint()},
                assumptions=["a tensão média no indutor é nula em regime"],
                reference=ref,
            )
        )
        log.add(
            record(
                "Io_rms",
                "Corrente eficaz na carga",
                r"I_{o,ef} = \sqrt{\frac{1}{2\pi}\int_0^{2\pi} i_o^2\,d\theta}",
                output=Q_(io_rms, "A"),
                inputs={},
                reference=ref,
            )
        )
        log.add(
            record(
                "dIo",
                "Ondulação de pico a pico da corrente de carga",
                r"\Delta I_o = i_{o,max} - i_{o,min}",
                output=Q_(di, "A"),
                inputs={},
                reference=ref,
            )
        )

        # α range for the mains tolerance
        tol = s.vin_tol_pct / 100
        a_high_v = self._alpha_for(topo, Vm * (1 + tol), Vo, ld, f, VT, VD, s.freewheel)
        a_low_v = self._alpha_for(topo, Vm * (1 - tol), Vo, ld, f, VT, VD, s.freewheel)
        if a_low_v is None:
            warnings.append(
                DesignWarning(
                    code="sem_reserva",
                    message=f"Com a rede {s.vin_tol_pct:g} % abaixo do nominal, nem α = 0° "
                    "alcança Vo: aumente α nominal ou a tensão do secundário.",
                )
            )
        if a_high_v is not None and a_low_v is not None:
            log.add(
                record(
                    "alpha_range",
                    f"Faixa de α para a rede variando ±{s.vin_tol_pct:g} %",
                    r"\overline{v_o}\left(V_m(1 \pm \delta), \alpha\right) = V_o",
                    output=Q_(math.degrees(a_high_v) - math.degrees(a_low_v), "deg"),
                    inputs={
                        r"\alpha_{min}": Q_(math.degrees(a_low_v), "deg"),
                        r"\alpha_{max}": Q_(math.degrees(a_high_v), "deg"),
                        r"\delta": Q_(s.vin_tol_pct, "percent"),
                    },
                    reference=ref,
                )
            )

        # devices
        it = wv.devices["T1"]
        it_avg, it_rms, it_pk = m.mean(it), m.rms(it), float(np.max(it))
        # α moves over the whole range at start-up and under control, so the blocking stress is
        # the peak of the secondary (plus E when the load holds the cathode at E)
        vdrm = Vm
        vrrm = Vm + ld.E if topo == "meia_onda" else Vm
        log.add(
            record(
                "IT_avg",
                "Corrente média em cada tiristor",
                r"I_{T,med} = \frac{1}{2\pi}\int_0^{2\pi} i_T\,d\theta",
                output=Q_(it_avg, "A"),
                inputs={},
                reference=ref,
            )
        )
        log.add(
            record(
                "IT_rms",
                "Corrente eficaz em cada tiristor",
                r"I_{T,ef} = \sqrt{\frac{1}{2\pi}\int_0^{2\pi} i_T^2\,d\theta}",
                output=Q_(it_rms, "A"),
                inputs={},
                reference=ref,
            )
        )
        piv_latex = (
            r"V_{DRM} = V_m,\quad V_{RRM} = V_m + E"
            if topo == "meia_onda"
            else r"V_{DRM} = V_{RRM} = V_m"
        )
        log.add(
            record(
                "VDRM",
                "Tensão direta de bloqueio máxima em cada tiristor",
                piv_latex,
                output=Q_(vdrm, "V"),
                inputs={"V_m": Q_(Vm, "V")},
                assumptions=["α percorre toda a faixa na partida e no controle"],
                reference=ref,
            )
        )
        log.add(
            record(
                "VRRM",
                "Tensão reversa máxima em cada tiristor",
                piv_latex,
                output=Q_(vrrm, "V"),
                inputs={"V_m": Q_(Vm, "V"), "E": s.E.to_pint()},
                reference=ref,
            )
        )
        stresses = [
            Stress(
                designator=t_des,
                key="VDRM",
                label="Tensão direta de bloqueio",
                value=QuantityModel(value=vdrm, unit="V"),
                calc_step_id="VDRM",
            ),
            Stress(
                designator=t_des,
                key="VRRM",
                label="Tensão reversa",
                value=QuantityModel(value=vrrm, unit="V"),
                calc_step_id="VRRM",
            ),
            Stress(
                designator=t_des,
                key="IT(AV)",
                label="Corrente média",
                value=QuantityModel(value=it_avg, unit="A"),
                calc_step_id="IT_avg",
            ),
            Stress(
                designator=t_des,
                key="IT(RMS)",
                label="Corrente eficaz",
                value=QuantityModel(value=it_rms, unit="A"),
                calc_step_id="IT_rms",
            ),
        ]
        losses = {t_des: Q_(VT * it_avg, "W")}
        if VT > 0:
            log.add(
                record(
                    f"P_{t_des}",
                    f"Perda em condução em cada tiristor ({t_des})",
                    r"P_T = V_T\,I_{T,med}",
                    output=Q_(VT * it_avg, "W"),
                    inputs={"V_T": Q_(VT, "V"), "I_{T,med}": Q_(it_avg, "A")},
                    assumptions=[
                        "queda constante V_TM do datasheet (conservador)",
                        "perdas de comutação e de porta desprezadas em 60 Hz",
                    ],
                    reference=ref,
                )
            )
        summary: dict[str, pint.Quantity] = {}
        if d_des:
            idd = wv.devices["D1"]
            id_avg, id_rms = m.mean(idd), m.rms(idd)
            vd_rev = Vm if topo == "semicontrolada" else float(max(np.max(wv.vo), 0.0))
            log.add(
                record(
                    "ID_avg",
                    "Corrente média em cada diodo",
                    r"I_{D,med} = \frac{1}{2\pi}\int_0^{2\pi} i_D\,d\theta",
                    output=Q_(id_avg, "A"),
                    inputs={},
                    reference=ref,
                )
            )
            log.add(
                record(
                    "VR_D",
                    "Tensão reversa máxima em cada diodo",
                    r"V_{R,max} = V_m" if topo == "semicontrolada" else r"V_{R,max} = \max v_o",
                    output=Q_(vd_rev, "V"),
                    inputs={"V_m": Q_(Vm, "V")},
                    reference=ref,
                )
            )
            stresses += [
                Stress(
                    designator=d_des,
                    key="VRRM",
                    label="Tensão reversa de pico",
                    value=QuantityModel(value=vd_rev, unit="V"),
                    calc_step_id="VR_D",
                ),
                Stress(
                    designator=d_des,
                    key="IF(AV)",
                    label="Corrente média",
                    value=QuantityModel(value=id_avg, unit="A"),
                    calc_step_id="ID_avg",
                ),
            ]
            losses[d_des] = Q_(VD * id_avg, "W")
            summary["ID_avg"] = Q_(id_avg, "A")
            summary["ID_rms"] = Q_(id_rms, "A")

        # input side
        Vin = s.Vin.to_pint().m_as("V")
        Vsec = Vm / math.sqrt(2)
        N = Vin / Vsec
        isec_rms = m.rms(wv.i_src - np.mean(wv.i_src))
        pf = m.power_factor(wv.vs, wv.i_src)
        dpf = m.displacement_factor(wv.vs, wv.i_src)
        thd_i = m.thd(wv.i_src)
        va = Vsec * m.rms(wv.i_src)
        for sid, desc, latex_s, val, unit, ins in (
            ("Vsec", "Tensão eficaz do secundário", r"V_{sec} = V_m/\sqrt{2}", Vsec, "V", {}),
            (
                "N",
                "Relação de espiras primário : secundário",
                r"N = V_{in}/V_{sec}",
                N,
                "",
                {"V_{in}": s.Vin.to_pint()},
            ),
            (
                "Isec",
                "Corrente eficaz do secundário",
                r"I_{sec} = \sqrt{\overline{i_s^2}}",
                m.rms(wv.i_src),
                "A",
                {},
            ),
            ("VA_sec", "Potência aparente do secundário", r"S = V_{sec} I_{sec}", va, "V*A", {}),
            ("PF", "Fator de potência na entrada", r"FP = \frac{P}{V_{sec} I_{sec}}", pf, "", {}),
            ("DPF", "Fator de deslocamento", r"FD = \cos\varphi_1", dpf, "", {}),
            (
                "THD_i",
                "Distorção harmônica total da corrente de entrada",
                r"THD_i = \frac{\sqrt{\sum_{h\ge2} I_h^2}}{I_1}",
                thd_i * 100,
                "percent",
                {},
            ),
        ):
            log.add(record(sid, desc, latex_s, output=Q_(val, unit), inputs=ins, reference=ref))
        if topo == "meia_onda":
            warnings.append(
                DesignWarning(
                    code="cc_no_transformador",
                    message="Meia onda: o secundário conduz corrente média de "
                    f"{format_eng(Q_(m.mean(wv.i_src), 'A'))}, que magnetiza o núcleo do "
                    "transformador.",
                )
            )
        if not sol.continuous:
            warnings.append(
                DesignWarning(
                    code="descontinuo",
                    message="Corrente de carga descontínua em α nominal: a tensão média passa a "
                    "depender da carga; aumente L se a aplicação pedir corrente contínua.",
                )
            )
        summary.update(
            {
                "Vm": Q_(Vm, "V"),
                "Vo": Q_(vo_avg, "V"),
                "Vo_rms": Q_(vo_rms, "V"),
                "Vo_ideal": Q_(v_ideal, "V"),
                "Io": Q_(io_avg, "A"),
                "Io_rms": Q_(io_rms, "A"),
                "dIo": Q_(di, "A"),
                "alpha": s.alpha_nom.to_pint(),
                "continuous": Q_(1.0 if sol.continuous else 0.0, ""),
                "IT_avg": Q_(it_avg, "A"),
                "IT_rms": Q_(it_rms, "A"),
                "IT_pk": Q_(it_pk, "A"),
                "VDRM": Q_(vdrm, "V"),
                "VRRM": Q_(vrrm, "V"),
                "Vsec": Q_(Vsec, "V"),
                "N": Q_(N, ""),
                "Isec": Q_(m.rms(wv.i_src), "A"),
                "Isec_ac": Q_(isec_rms, "A"),
                "VA_sec": Q_(va, "V*A"),
                "PF": Q_(pf, ""),
                "DPF": Q_(dpf, ""),
                "THD_i": Q_(thd_i * 100, "percent"),
                "P_out": Q_(float(np.mean(wv.vo * wv.io)), "W"),
            }
        )
        if sol.beta is not None:
            summary["beta"] = Q_(math.degrees(sol.beta), "deg")
        if a_high_v is not None:
            summary["alpha_max"] = Q_(math.degrees(a_high_v), "deg")
        if a_low_v is not None:
            summary["alpha_min"] = Q_(math.degrees(a_low_v), "deg")
        traces = {
            "Tensão no secundário": make_trace("V", wv.vs),
            "Tensão na carga": make_trace("V", wv.vo),
            "Corrente na carga": make_trace("A", wv.io),
            "Corrente no secundário": make_trace("A", wv.i_src),
        }
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses=losses,
            warnings=warnings,
            convergence_keys=("Vm", "Vo"),
            traces=traces,
        )

    @staticmethod
    def _alpha_for(
        topo: Topology,
        Vm: float,
        Vo: float,
        ld: m.Load,
        f: float,
        VT: float,
        VD: float,
        freewheel: bool,
    ) -> float | None:
        def g(a: float) -> float:
            sol = m.solve(topo, Vm, a, ld, f, VT, VD, freewheel)
            return (m.mean(m.waves(sol).vo) if sol.fired else ld.E) - Vo

        if g(0.0) < 0:
            return None
        hi = math.pi * 0.999
        if g(hi) > 0:
            return hi
        return float(brentq(g, 0.0, hi, xtol=1e-7))

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        """Same model as the analysis: constant-drop SCRs and diodes, ideal source.

        The SCR is a latch (fires with gate > 0,5 V while forward biased, holds while its
        conduction current exceeds 1 µA). Short gate pulses (5°) at α and α + π.
        """
        s = _spec(spec)
        topo = s.topology
        t_des = _scr_designator(topo)
        d_des = _diode_designator(s)
        VT = devices[t_des].drop.m_as("V")
        VD = devices[d_des].drop.m_as("V") if d_des else 0.0
        Vm = summary["Vm"].to_pint().m_as("V")
        f = s.f.to_pint().m_as("Hz")
        T = 1 / f
        a = s.alpha_nom.to_pint().m_as("deg")
        ta = a / 360 * T
        tw = T / 72
        R = s.R.to_pint().m_as("ohm")
        L = s.L.to_pint().m_as("H")
        E = s.E.to_pint().m_as("V")

        def gate(n: int, t0: float) -> str:
            return f"VG{n} g{n} 0 PULSE(0 1 {t0:.9g} 1n 1n {tw:.9g} {T:.9g})"

        lines = [scr_model(VT), diode_model(VD)]
        src = f"SIN(0 {Vm:.9g} {f:.9g})"
        if topo == "meia_onda":
            lines += [f"VS a 0 {src}", "VSD a a1 0", "XT1 a1 p g1 SCR", gate(1, ta)]
            if s.freewheel:
                lines.append("XD1 0 p DIODE")
            v_sec = "v(a)"
        elif topo == "ponte":
            lines += [
                f"VS a b {src}",
                "VSD a a1 0",
                "XT1 a1 p g1 SCR",
                "XT2 0 b g2 SCR",
                "XT3 b p g3 SCR",
                "XT4 0 a1 g4 SCR",
                gate(1, ta),
                gate(2, ta),
                gate(3, ta + T / 2),
                gate(4, ta + T / 2),
            ]
            v_sec = "v(a)-v(b)"
        else:
            lines += [
                f"VS a b {src}",
                "VSD a a1 0",
                "XT1 a1 p g1 SCR",
                "XT2 b p g2 SCR",
                "XD1 0 a1 DIODE",
                "XD2 0 b DIODE",
                gate(1, ta),
                gate(2, ta + T / 2),
            ]
            v_sec = "v(a)-v(b)"
        lines += [f"RL p x {R:.9g}", f"LL x y {L:.9g}" if L > 0 else "VLL x y 0", f"VE y 0 {E:.9g}"]
        tau_periods = (L / R) * f if L > 0 else 0
        settle = int(min(max(20, 6 * tau_periods + 5), 200))
        probes = {
            "Tensão no secundário": v_sec,
            "Tensão na carga": "v(p)",
            "Corrente na carga": "i(ve)",
            "Corrente no secundário": "i(vsd)",
        }
        checks = [
            SimCheck(
                quantity="Tensão média na carga",
                summary_key="Vo",
                metric="avg",
                probe="v(p)",
                tolerance_pct=1.0,
                justification=_EXACT,
            ),
            SimCheck(
                quantity="Tensão eficaz na carga",
                summary_key="Vo_rms",
                metric="rms",
                probe="v(p)",
                tolerance_pct=1.0,
                justification=_EXACT,
            ),
            SimCheck(
                quantity="Corrente média na carga",
                summary_key="Io",
                metric="avg",
                probe="i(ve)",
                tolerance_pct=1.0,
                justification=_EXACT,
            ),
            SimCheck(
                quantity="Corrente eficaz no secundário",
                summary_key="Isec",
                metric="rms",
                probe="i(vsd)",
                tolerance_pct=1.0,
                justification=_EXACT,
            ),
            SimCheck(
                quantity="Fator de potência",
                summary_key="PF",
                metric="pf",
                probe="i(vsd)",
                voltage=v_sec,
                tolerance_pct=2.0,
                justification=_EXACT,
            ),
            SimCheck(
                quantity="THD da corrente de entrada",
                summary_key="THD_i",
                metric="thd",
                probe="i(vsd)",
                tolerance_pct=5.0,
                justification=_EXACT + "; a THD é sensível ao passo de tempo",
            ),
        ]
        return Circuit(
            title=f"{self.id}: {TOPOLOGY_LABEL[topo]}"
            + (" com roda livre" if s.freewheel else "")
            + f", α = {a:g}°",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=settle * T, unit="s"),
            tran_step=QuantityModel(value=T / 8000, unit="s"),
            period=QuantityModel(value=T, unit="s"),
            probes=probes,
            checks=checks,
        )


_EXACT = "modelo exato (mesmos dispositivos de queda constante no simulador)"


def scr_model(VT: float) -> str:
    """Latching SCR with constant drop VT (1 mΩ above it), 1 MΩ off-state leakage."""
    return "\n".join(
        [
            ".subckt SCR a k g",
            f"BA a ks I = v(st) * ((v(a,k) > {VT:.9g}) ? (v(a,k) - {VT:.9g}) / 1m : 0)",
            "VKS ks k DC 0",
            "RLK a k 1Meg",
            f"BST nst 0 V = ((v(g) > 0.5 && v(a,k) > {VT:.9g}) || "
            "(v(st) > 0.5 && i(VKS) > 1e-6)) ? 1 : 0",
            "RST nst st 1k",
            "CST st 0 1n",
            ".ends",
        ]
    )


def diode_model(VF: float) -> str:
    """Constant-drop diode (1 mΩ above VF, 1 µS reverse leakage)."""
    return "\n".join(
        [
            ".subckt DIODE a k",
            f"BD a k I = (v(a,k) > {VF:.9g}) ? (v(a,k) - {VF:.9g}) / 1m : v(a,k) * 1u",
            ".ends",
        ]
    )
