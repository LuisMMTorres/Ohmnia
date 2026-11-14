"""DM-FORMA: diode wave-shaping circuits — clippers, clamper and voltage multipliers.

Boylestad & Nashelsky, *Electronic Devices and Circuit Theory*, 11th ed., ch. 2 "Diode
applications" (clippers, clampers, voltage-multiplier circuits). The diode is the
constant-drop model with VF of the chosen part (the same behavioural diode as DM-RET1 in the
simulator):

* clippers: piecewise output, exact for the model;
* clamper: C charges to Vm − VF + VB at the input minimum and discharges through RL until the
  diode conducts again (solved exactly for the model, periodic steady state);
* Cockcroft-Walton multiplier with n stages (2n diodes, 2n capacitors): no-load output 2n·(Vm −
  VF); with load current Io, droop ΔV = Io/(f·C)·(2n³/3 + n²/2 − n/6) and ripple
  δV = Io/(f·C)·n(n + 1)/2 (Kuffel, Zaengl & Kuffel, *High Voltage Engineering: Fundamentals*,
  2nd ed., ch. 2, Cockcroft-Walton cascade). These are approximations (linear discharge):
  the simulation tolerance says so.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pint
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from scipy.integrate import solve_ivp

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
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
from circuitos.design.devmodels import BOYLESTAD
from circuitos.design.engine import Analysis, Device
from circuitos.reports.common import BomRow, LabItem, passive
from circuitos.reports.schematic import Svg

Kind = Literal[
    "ceifador_paralelo", "ceifador_serie", "ceifador_duplo", "grampeador", "multiplicador"
]
REF = BOYLESTAD.model_copy(update={"chapter": "2 (Diode applications)"})
KUFFEL = BibRef(
    book="Kuffel, Zaengl & Kuffel, High Voltage Engineering: Fundamentals",
    edition="2nd",
    chapter="2 (Generation of high voltages; cascade circuits)",
)
NPTS = 2880


def diode_model(VF: float) -> str:
    """Constant-drop diode, the same model as the analysis (as in DM-RET1, with 1 nS off-state
    leakage instead of 1 µS so that high-resistance loads are not loaded by the model)."""
    return "\n".join(
        [
            ".subckt DIODE a k",
            f"BD a k I = (v(a,k) > {VF:.9g}) ? (v(a,k) - {VF:.9g}) / 10u : v(a,k) * 1n",
            ".ends",
        ]
    )


class FormaSpec(BaseModel):
    kind: Kind = "ceifador_paralelo"
    Vm: QuantityModel = QuantityModel(value=10, unit="V")  # input peak
    f: QuantityModel = QuantityModel(value=1, unit="kHz")
    VB: QuantityModel = QuantityModel(value=3, unit="V")  # bias source (clippers, clamper)
    R: QuantityModel = QuantityModel(value=1, unit="kohm")  # series resistor (shunt clippers)
    RL: QuantityModel = QuantityModel(value=100, unit="kohm")
    C: QuantityModel = QuantityModel(value=10, unit="uF")  # clamper capacitor
    stages: int = Field(default=1, ge=1, le=6)  # multiplier stages (1 = doubler)
    ripple_pct: float = Field(default=2.0, gt=0, le=20)  # multiplier ripple target, % of Vo
    cap_series: Literal["E3", "E6", "E12"] = "E6"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")


LABELS = {
    "Vo_max": "Máximo da saída",
    "Vo_min": "Mínimo da saída",
    "Vo_avg": "Média da saída",
    "V_clip_hi": "Nível de ceifamento superior",
    "V_clip_lo": "Nível de ceifamento inferior",
    "VC": "Tensão no capacitor de grampeamento",
    "dV": "Queda da tensão de saída com carga",
    "ripple": "Ondulação de pico a pico",
    "Vo_noload": "Saída sem carga",
    "Io": "Corrente na carga",
    "C_stage": "Capacitor por estágio",
    "PIV": "Tensão reversa de pico por diodo",
    "ID_avg": "Corrente média por diodo",
}
SPEC_LABELS = {
    "kind": "Circuito",
    "Vm": "Amplitude da entrada",
    "f": "Frequência",
    "VB": "Fonte de polarização VB",
    "R": "Resistor série",
    "RL": "Carga",
    "C": "Capacitor do grampeador",
    "stages": "Estágios do multiplicador",
    "ripple_pct": "Ondulação desejada (%)",
    "cap_series": "Série de capacitores",
}
ENUM_LABELS = {
    "ceifador_paralelo": "ceifador em paralelo (positivo, com VB)",
    "ceifador_serie": "ceifador em série (com VB)",
    "ceifador_duplo": "ceifador duplo (±VB)",
    "grampeador": "grampeador positivo (com VB)",
    "multiplicador": "multiplicador de tensão (Cockcroft-Walton)",
}


def _spec(spec: BaseModel) -> FormaSpec:
    if not isinstance(spec, FormaSpec):
        raise TypeError("DM-FORMA espera FormaSpec")
    return spec


def _divider(vin: NDArray[np.float64], r: float, rl: float) -> NDArray[np.float64]:
    return np.asarray(vin * rl / (r + rl))


class FormaModule:
    id = "DM-FORMA"
    family = "diodos"
    title = "Ceifadores, grampeadores e multiplicadores"
    spec_schema = FormaSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Máximo da saída", "osciloscópio, acoplamento CC", "Vo_max"),
        LabItem("Mínimo da saída", "osciloscópio, acoplamento CC", "Vo_min"),
        LabItem("Média da saída", "multímetro CC", "Vo_avg"),
    ]
    questions = [
        "Como a queda VF do diodo desloca o nível de ceifamento? Meça com dois diodos "
        "diferentes (silício e Schottky).",
        "No grampeador, o que acontece com o patamar se RL·C não for muito maior que o período?",
        "Por que a saída do multiplicador cai tanto com a carga quando o número de estágios "
        "aumenta?",
    ]
    practice = {
        "objective": "Montar o circuito, observar a forma de onda de saída em CC no "
        "osciloscópio e comparar os níveis com o cálculo e a simulação.",
        "material": "Gerador de funções, fonte CC (polarização), osciloscópio de dois canais, "
        "componentes da lista.",
        "procedure": [
            "Monte o circuito; confira a polaridade dos diodos e dos capacitores.",
            "Aplique a senoide de entrada e observe entrada e saída com acoplamento CC.",
            "Meça os níveis máximo e mínimo da saída.",
            "Varie VB (ou a carga) e observe o efeito.",
        ],
    }

    def _n_diodes(self, s: FormaSpec) -> int:
        return {"ceifador_duplo": 2, "multiplicador": 2 * s.stages}.get(s.kind, 1)

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        n = self._n_diodes(s)
        return [
            Role(
                designator="D1" if n == 1 else f"D1–D{n}",
                category="diode",
                description="Diodos",
                count=n,
            )
        ]

    def required_ratings(self, role: Role) -> list[str]:
        return ["VRRM", "IF(AV)"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        return not rec.category.startswith("diode.zener") and "VF" in rec.parameters

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        # signal diodes first for low currents
        return 0.0 if rec.category == "diode.signal" else 1.0

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        role = self.roles(s)[0]
        vf = devices[role.designator].drop.m_as("V")
        vm = s.Vm.to_pint().m_as("V")
        f = s.f.to_pint().m_as("Hz")
        vb = s.VB.to_pint().m_as("V")
        r = s.R.to_pint().m_as("ohm")
        rl = s.RL.to_pint().m_as("ohm")
        th = np.linspace(0, 2 * math.pi, NPTS, endpoint=False)
        vin = vm * np.sin(th)
        summary: dict[str, pint.Quantity] = {}
        piv = vm + vb
        i_avg = 0.0
        extra: dict[str, float] = {}
        if s.kind in ("ceifador_paralelo", "ceifador_duplo"):
            hi = vb + vf
            lo = -(vb + vf) if s.kind == "ceifador_duplo" else -math.inf
            vo = np.clip(_divider(vin, r, rl), lo, hi)
            log.add(
                record(
                    "V_clip_hi",
                    "Nível de ceifamento superior",
                    r"V_{o,max} = V_B + V_F",
                    output=Q_(hi, "V"),
                    inputs={"V_B": s.VB.to_pint(), "V_F": Q_(vf, "V")},
                    assumptions=["diodo de queda constante", "R_L ≫ R"],
                    reference=REF,
                )
            )
            summary["V_clip_hi"] = Q_(hi, "V")
            if s.kind == "ceifador_duplo":
                log.add(
                    record(
                        "V_clip_lo",
                        "Nível de ceifamento inferior",
                        r"V_{o,min} = -(V_B + V_F)",
                        output=Q_(lo, "V"),
                        inputs={"V_B": s.VB.to_pint(), "V_F": Q_(vf, "V")},
                        reference=REF,
                    )
                )
                summary["V_clip_lo"] = Q_(lo, "V")
            i_d = np.maximum((vin - hi) / r - hi / rl, 0.0)
            i_avg = float(np.mean(i_d))
            piv = vm + vb
        elif s.kind == "ceifador_serie":
            # diode in series with VB opposing it: conducts when vin > VB + VF
            vo = np.where(vin > vb + vf, vin - vb - vf, 0.0)
            log.add(
                record(
                    "Vo_max",
                    "Máximo da saída do ceifador série",
                    r"V_{o,max} = V_m - V_B - V_F",
                    output=Q_(max(vm - vb - vf, 0.0), "V"),
                    inputs={"V_m": s.Vm.to_pint(), "V_B": s.VB.to_pint(), "V_F": Q_(vf, "V")},
                    reference=REF,
                )
            )
            i_avg = float(np.mean(vo / rl))
            piv = vm + vb
        elif s.kind == "grampeador":
            c = s.C.to_pint().m_as("F")
            vo, vc = self._clamper(vm, vf, vb, rl, c, f, th)
            log.add(
                record(
                    "VC",
                    "Tensão no capacitor no instante do mínimo da entrada",
                    r"V_C = V_m - V_F + V_B",
                    output=Q_(vc, "V"),
                    inputs={"V_m": s.Vm.to_pint(), "V_F": Q_(vf, "V"), "V_B": s.VB.to_pint()},
                    assumptions=[
                        "diodo de queda constante; a descarga por R_L no resto "
                        "do período é resolvida exatamente"
                    ],
                    reference=REF,
                )
            )
            summary["VC"] = Q_(vc, "V")
            if 5 * 1 / f > rl * c:
                warnings.append(
                    DesignWarning(
                        code="rc",
                        message="RL·C não é muito maior que o período: o patamar inclina bastante.",
                    )
                )
            i_avg = float(np.mean(np.abs(vo) / rl))
            piv = 2 * vm + vb
        else:
            n = s.stages
            v0 = 2 * n * (vm - vf)
            log.add(
                record(
                    "Vo_noload",
                    f"Saída sem carga do multiplicador de {n} estágio(s)",
                    r"V_{o,0} = 2n(V_m - V_F)",
                    output=Q_(v0, "V"),
                    inputs={"n": Q_(n, ""), "V_m": s.Vm.to_pint(), "V_F": Q_(vf, "V")},
                    reference=REF,
                )
            )
            io = v0 / rl  # first estimate
            ripple_t = s.ripple_pct / 100 * v0
            c_req = log.add(
                record(
                    "C_calc",
                    "Capacitor por estágio para a ondulação desejada",
                    r"C = \frac{I_o\,n(n+1)}{2 f\,\delta V}",
                    output=Q_(io * n * (n + 1) / (2 * f * ripple_t), "F").to("uF"),
                    inputs={
                        "I_o": Q_(io, "A").to("mA"),
                        "n": Q_(n, ""),
                        "f": s.f.to_pint(),
                        r"\delta V": Q_(ripple_t, "V"),
                    },
                    assumptions=["corrente de carga estimada com a saída sem carga"],
                    reference=KUFFEL,
                )
            )
            c = commercial(
                log, "C_stage", "Capacitor comercial por estágio", c_req, s.cap_series, "up"
            ).m_as("F")
            k = 2 * n**3 / 3 + n**2 / 2 - n / 6
            # Vo = V0 − Io·k/(fC) with Io = Vo/RL  →  Vo = V0 / (1 + k/(f·C·RL))
            vo_avg = v0 / (1 + k / (f * c * rl))
            io = vo_avg / rl
            dv = v0 - vo_avg
            rip = io / (f * c) * n * (n + 1) / 2
            log.add(
                record(
                    "dV",
                    "Queda da saída com carga",
                    r"\Delta V = \frac{I_o}{f C}\left(\frac{2n^3}{3} + \frac{n^2}{2} - "
                    r"\frac{n}{6}\right),\; I_o = V_o/R_L",
                    output=Q_(dv, "V"),
                    inputs={"I_o": Q_(io, "A").to("mA"), "C": Q_(c, "F").to("uF")},
                    assumptions=["descarga linear (fC R_L ≫ 1)"],
                    reference=KUFFEL,
                )
            )
            log.add(
                record(
                    "ripple",
                    "Ondulação de pico a pico",
                    r"\delta V = \frac{I_o}{f C}\frac{n(n+1)}{2}",
                    output=Q_(rip, "V"),
                    inputs={"I_o": Q_(io, "A").to("mA"), "C": Q_(c, "F").to("uF")},
                    reference=KUFFEL,
                )
            )
            log.add(
                record(
                    "Vo_avg",
                    "Saída média com carga",
                    r"V_o = V_{o,0} - \Delta V",
                    output=Q_(vo_avg, "V"),
                    reference=KUFFEL,
                )
            )
            vo = vo_avg + rip / 2 * np.sin(th)  # illustrative ripple shape
            summary |= {
                "Vo_noload": Q_(v0, "V"),
                "dV": Q_(dv, "V"),
                "ripple": Q_(rip, "V"),
                "Io": Q_(io, "A").to("mA"),
                "C_stage": Q_(c, "F").to("uF"),
            }
            extra["C"] = c
            i_avg = io
            piv = 2 * vm
        if s.kind != "multiplicador":
            summary |= {"Vo_max": Q_(float(vo.max()), "V"), "Vo_min": Q_(float(vo.min()), "V")}
        summary["Vo_avg"] = Q_(float(np.mean(vo)), "V")
        summary["PIV"] = Q_(piv, "V")
        summary["ID_avg"] = Q_(i_avg, "A").to("mA")
        d = role.designator
        stresses = [
            Stress(
                designator=d,
                key="VRRM",
                label="Tensão reversa de pico",
                value=QuantityModel(value=piv, unit="V"),
                calc_step_id="PIV",
            ),
            Stress(
                designator=d,
                key="IF(AV)",
                label="Corrente média",
                value=QuantityModel(value=max(i_avg, 1e-6), unit="A"),
                calc_step_id="PIV",
            ),
        ]
        log.add(
            record(
                "PIV",
                "Tensão reversa de pico por diodo",
                r"PIV = "
                + {"grampeador": r"2V_m + V_B", "multiplicador": r"2V_m"}.get(s.kind, r"V_m + V_B"),
                output=Q_(piv, "V"),
                inputs={"V_m": s.Vm.to_pint()},
                reference=REF,
            )
        )
        traces = {"Entrada": make_trace("V", vin), "Saída": make_trace("V", vo)}
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={d: Q_(vf * i_avg, "W")},
            warnings=warnings,
            convergence_keys=("Vo_avg",),
            traces=traces,
            trace_period=Q_(1 / f, "s"),
        )

    def _clamper(
        self,
        vm: float,
        vf: float,
        vb: float,
        rl: float,
        c: float,
        f: float,
        th: NDArray[np.float64],
    ) -> tuple[NDArray[np.float64], float]:
        """Periodic steady state of the positive clamper (C in series, diode from VB to output).

        While the diode conducts vo = VB − VF; its current is iD = (VB − VF)/RL − C·dvin/dt, so it
        turns off when C·ω·Vm·cos ωt = (VB − VF)/RL, just after the input minimum. Off, C
        discharges through RL: dvC/dt = −(vin + vC)/(RL·C) with vo = vin + vC, until vo falls to
        the clamp level again. Returns vo on the θ grid and vC at the input minimum.
        """
        w = 2 * math.pi * f
        clamp = vb - vf
        k = clamp / (rl * c * w * vm)
        x_off = math.asin(max(min(k, 1.0), -1.0))
        t_off = (1.5 * math.pi + x_off) / w
        vc_off = clamp - vm * math.sin(w * t_off)

        def ode(t: float, y: NDArray[np.float64]) -> list[float]:
            return [-(vm * math.sin(w * t) + y[0]) / (rl * c)]

        guard = t_off + 0.01 / f

        def hit(t: float, y: NDArray[np.float64]) -> float:
            return float(vm * math.sin(w * t) + y[0] - clamp) if t > guard else 1.0

        hit.terminal = True  # type: ignore[attr-defined]
        hit.direction = -1  # type: ignore[attr-defined]
        sol = solve_ivp(
            ode,
            (t_off, t_off + 1 / f),
            [vc_off],
            events=hit,
            dense_output=True,
            rtol=1e-10,
            atol=1e-12,
            max_step=1 / f / 500,
        )
        t_on = float(sol.t_events[0][0]) if sol.t_events[0].size else t_off + 1 / f
        tt = th / w
        tt = np.where(tt < t_off, tt + 1 / f, tt)  # unwrap the grid to [t_off, t_off + T)
        vin_t = vm * np.sin(w * tt)
        vc_dis = sol.sol(np.minimum(tt, t_on))[0]
        vo = np.where(tt < t_on, vin_t + vc_dis, clamp)
        return np.asarray(vo), vm + clamp

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        role = self.roles(s)[0]
        vf = devices[role.designator].drop.m_as("V")
        vm = s.Vm.to_pint().m_as("V")
        f = s.f.to_pint().m_as("Hz")
        vb = s.VB.to_pint().m_as("V")
        r = s.R.to_pint().m_as("ohm")
        rl = s.RL.to_pint().m_as("ohm")
        lines = [diode_model(vf), f"VIN in 0 SIN(0 {vm:.9g} {f:.9g})"]
        tol, why, periods = 1.0, "mesmo diodo de queda constante no simulador", 3
        if s.kind in ("ceifador_paralelo", "ceifador_duplo"):
            lines += [
                f"R1 in o {r:.9g}",
                f"RL o 0 {rl:.9g}",
                "XD1 o b1 DIODE",
                f"VB1 b1 0 DC {vb:.9g}",
            ]
            if s.kind == "ceifador_duplo":
                lines += ["XD2 b2 o DIODE", f"VB2 0 b2 DC {vb:.9g}"]
        elif s.kind == "ceifador_serie":
            lines += [f"VB1 in a DC {vb:.9g}", "XD1 a o DIODE", f"RL o 0 {rl:.9g}"]
        elif s.kind == "grampeador":
            c = s.C.to_pint().m_as("F")
            vc = summary["VC"].to_pint().m_as("V")
            # v(in, o) = −VC at the input minimum; diode anode at the VB source, cathode at vo
            lines += [
                f"C1 in o {c:.9g} IC={-vc:.6g}",
                f"VB1 k 0 DC {vb:.9g}",
                "XD1 k o DIODE",
                f"RL o 0 {rl:.9g}",
            ]
        else:
            n = s.stages
            c = summary["C_stage"].to_pint().m_as("F")
            v1 = vm - vf
            prev_p, prev_q = "in", "0"
            for k in range(1, n + 1):
                p, q = f"p{k}", ("o" if k == n else f"q{k}")
                lines += [
                    f"CP{k} {prev_p} {p} {c:.9g} IC={(-v1 if k == 1 else -2 * v1):.6g}",
                    f"XDA{k} {prev_q} {p} DIODE",
                    f"XDB{k} {p} {q} DIODE",
                    f"CQ{k} {q} {prev_q} {c:.9g} IC={2 * v1:.6g}",
                ]
                prev_p, prev_q = p, q
            lines.append(f"RL o 0 {rl:.9g}")
            tol, why = 3.0, "fórmula de descarga linear (aproximação) contra a simulação exata"
            periods = 60
        checks: list[SimCheck] = []
        if s.kind == "ceifador_duplo":  # symmetric: the mean is zero, compare the lower level
            checks.append(
                SimCheck(
                    quantity="Mínimo da saída",
                    summary_key="Vo_min",
                    metric="min",
                    probe="v(o)",
                    tolerance_pct=1.0,
                    justification=why,
                )
            )
        else:
            checks.append(
                SimCheck(
                    quantity="Média da saída",
                    summary_key="Vo_avg",
                    metric="avg",
                    probe="v(o)",
                    tolerance_pct=tol,
                    justification=why,
                )
            )
        if s.kind != "multiplicador":
            checks += [
                SimCheck(
                    quantity="Máximo da saída",
                    summary_key="Vo_max",
                    metric="max",
                    probe="v(o)",
                    tolerance_pct=1.0,
                    justification=why,
                ),
            ]
        else:
            checks.append(
                SimCheck(
                    quantity="Ondulação de pico a pico",
                    summary_key="ripple",
                    metric="pp",
                    probe="v(o)",
                    tolerance_pct=25.0,
                    justification="aproximação de descarga linear da ondulação",
                )
            )
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[s.kind]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=periods / f, unit="s"),
            tran_step=QuantityModel(value=1 / f / 4000, unit="s"),
            period=QuantityModel(value=1 / f, unit="s"),
            probes={"Entrada": "v(in)", "Saída": "v(o)"},
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        part = next((c.part_number for c in result.selection), "")
        if s.kind == "multiplicador":
            return self._schematic_cw(s, result, title, part)
        svg = Svg(560, 300)
        svg.title(title)
        top, bot, xs, xl = 80, 240, 90, 440
        svg.ac_source(xs, top, bot, "vin", f"{s.Vm.value:g} V pico")
        vb = f"{s.VB.value:g} V"
        if s.kind in ("ceifador_paralelo", "ceifador_duplo"):
            svg.resistor_h(xs, 220, top, "R", format_eng(s.R.to_pint()))
            svg.wire((220, top), (xl, top))
            svg.diode_v(270, top, 165, "D1", part, up=False)
            svg.battery_v(270, 165, bot, "VB", vb)
            svg.dot(270, top)
            if s.kind == "ceifador_duplo":
                svg.diode_v(360, top, 165, "D2", "", up=True)
                svg.battery_v(360, 165, bot, "VB", vb, flip=True)
                svg.dot(360, top)
        elif s.kind == "ceifador_serie":
            svg.wire((xs, top), (xs, top - 30), (150, top - 30))
            svg.battery_v(150, top - 30, top, "VB", vb)
            svg.device_right(150, 320, top, "diode", "D1", part)
            svg.wire((320, top), (xl, top))
        else:  # grampeador
            svg.cap_h(xs, 220, top, "C", format_eng(s.C.to_pint()))
            svg.wire((220, top), (xl, top))
            svg.diode_v(280, top, 165, "D1", part, up=True)
            svg.battery_v(280, 165, bot, "VB", vb)
            svg.dot(280, top)
        svg.resistor_v(xl, top, bot, "RL", format_eng(s.RL.to_pint()))
        svg.dot(xl, top)
        svg.wire((xl, top), (500, top))
        svg.terminal(500, top, "vo")
        svg.wire((xs, bot), (xl, bot))
        svg.ground(xs, bot)
        return svg.render(title)

    def _schematic_cw(self, s: FormaSpec, result: DesignResult, title: str, part: str) -> str:
        """Cockcroft-Walton ladder: top rail p (push capacitors), lower rail q (smoothing)."""
        n = s.stages
        c = format_eng(result.summary["C_stage"].to_pint()) if "C_stage" in result.summary else ""
        step, xs = 180, 90
        width = xs + 60 + n * step + 120
        svg = Svg(width, 330)
        svg.title(title)
        top, low, gnd = 90, 210, 280
        svg.ac_source(xs, top, low, "vin", f"{s.Vm.value:g} V pico")
        svg.ground(xs, low)
        x = xs + 60
        svg.wire((xs, top), (x - 50, top))
        svg.wire((xs, low), (x, low))
        prev_top: float = x - 50
        for k in range(1, n + 1):
            xp, xq = x + (k - 1) * step, x + (k - 1) * step + step / 2
            svg.cap_h(prev_top, xp, top, f"C{2 * k - 1}", c)
            svg.wire((xp, top), (xq, top))
            svg.diode_v(xp, top, low, f"D{2 * k - 1}", part if k == 1 else "", up=True)
            svg.cap_h(xp, xq, low, f"C{2 * k}", c)
            svg.diode_v(xq, top, low, f"D{2 * k}", "", up=False)
            svg.dot(xp, top)
            svg.dot(xq, top)
            svg.dot(xp, low)
            svg.dot(xq, low)
            nxt = xq + step / 2
            if k < n:
                svg.wire((xq, low), (nxt, low))
                prev_top = xq
            else:
                svg.wire((xq, low), (xq + 80, low))
        xr = x + (n - 1) * step + step / 2 + 80
        svg.resistor_v(xr, low, gnd, "RL", format_eng(s.RL.to_pint()))
        svg.ground(xr, gnd)
        svg.dot(xr, low)
        svg.wire((xr, low), (xr + 30, low))
        svg.terminal(xr + 30, low, "vo")
        svg.text(
            xs - 40,
            318,
            f"Multiplicador de Cockcroft-Walton, {n} estágio(s): saída ≈ "
            f"{2 * n}·(Vm − VF) sem carga.",
        )
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        rows: list[BomRow] = []
        if s.kind in ("ceifador_paralelo", "ceifador_duplo"):
            rows.append(passive("R", "Resistor série", format_eng(s.R.to_pint())))
        if s.kind == "grampeador":
            rows.append(
                passive(
                    "C",
                    "Capacitor de grampeamento",
                    format_eng(s.C.to_pint()),
                    f"tensão ≥ {format_eng(result.summary['VC'].to_pint() * 1.25)}",
                )
            )
        if s.kind == "multiplicador":
            rows.append(
                passive(
                    "C1–C" + str(2 * s.stages),
                    "Capacitores dos estágios",
                    format_eng(result.summary["C_stage"].to_pint()),
                    f"tensão ≥ {2.5 * s.Vm.value:g} V",
                    quantity=2 * s.stages,
                )
            )
        if s.kind != "multiplicador" and s.VB.value != 0:
            rows.append(
                passive(
                    "VB",
                    "Fonte de polarização",
                    f"{s.VB.value:g} V",
                    "fonte CC ou Zener polarizado",
                )
            )
        rows.append(passive("RL", "Carga", format_eng(s.RL.to_pint())))
        return rows
