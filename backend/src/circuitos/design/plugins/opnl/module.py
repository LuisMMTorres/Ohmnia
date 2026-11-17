"""DM-OPNL: non-linear op-amp circuits.

Closed forms (Sedra & Smith, *Microelectronic Circuits*, 7th ed., ch. 18 "Signal generators and
waveform-shaping circuits" for comparators and bistables, ch. 4 "Diodes", sec. on precision
rectifiers (superdiode) for the rectifiers; Pertence, *Amplificadores operacionais e filtros
ativos*, for the logarithmic amplifier and the Zener limiter):

* comparator: output high while v+ > v−; for a sine of peak Vm against Vref the duty cycle is
  D = 1/2 − arcsin(Vref/Vm)/π;
* inverting Schmitt trigger (R1 output → +, R2 + → Vref): V_T± = (1 − β)Vref + β·V_sat±,
  β = R2/(R1 + R2); non-inverting (R1 input → +, R2 output → +, Vref at −):
  V_T± = Vref(1 + R1/R2) − V_sat∓·R1/R2;
* precision half-wave rectifier (inverting, two diodes): vo = (R2/R1)|vin| in one half-cycle,
  0 in the other, independent of VF; full wave with a summing amplifier: vo = G|vin|;
  average G·Vm/π (half) or 2G·Vm/π (full);
* logarithmic amplifier (transdiode: NPN in the feedback, base grounded):
  vo = −V_T ln(vin/(R·I_S) + 1);
* limiter: inverting amplifier with Zener + diode branches in the feedback; while a branch
  conducts vo = (VF + V_Z0 + r_z·Vm/R1)/(1 + r_z/Rf).

The saturation levels are those of the chosen op-amp (datasheet swing, see ``design/opamp.py``).
The simulation uses the macromodel with the slew-rate limit and the output clamp, the
constant-drop diode with VF of the chosen part, the piecewise-linear Zener and the Ebers-Moll
transistor of the analysis.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

import numpy as np
import pint
from pydantic import BaseModel, Field

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
    Trace,
    make_trace,
)
from circuitos.design.devmodels import VT_300K, ZenerPwl, bjt_model, quantity, zener_pwl
from circuitos.design.engine import Analysis, Device
from circuitos.design.opamp import REF as OPA_REF
from circuitos.design.opamp import TRAN_OPTIONS, OpAmp, opamp_model
from circuitos.design.plugins.zen.module import vz_of
from circuitos.reports.common import BomRow, LabItem, passive
from circuitos.reports.schematic import value_sheet

Config = Literal[
    "comparador",
    "schmitt_inversor",
    "schmitt_nao_inversor",
    "retificador_meia",
    "retificador_onda",
    "logaritmico",
    "limitador",
]
REF = OPA_REF.model_copy(update={"chapter": "18 (Signal generators and waveform-shaping)"})
REF_RECT = OPA_REF.model_copy(update={"chapter": "4 (Diodes), precision rectifiers"})
PERT = BibRef(book="Pertence, Amplificadores operacionais e filtros ativos", edition="8ª")
NPTS = 2000  # simulation steps per period
DELAY_FRAC = 1e-4  # SR delay of a threshold crossing, as a fraction of Vm, in the slow test


class OpnlSpec(BaseModel):
    config: Config = "schmitt_inversor"
    device: Literal["ampop", "comparador"] = "ampop"  # comparator only
    Vm: QuantityModel = QuantityModel(value=5, unit="V")  # input peak
    f: QuantityModel = QuantityModel(value=1, unit="kHz")
    Vref: QuantityModel = QuantityModel(value=0, unit="V")  # comparator reference
    Vc: QuantityModel = QuantityModel(value=0, unit="V")  # Schmitt: centre of the window
    VH: QuantityModel = QuantityModel(value=1, unit="V")  # Schmitt: hysteresis V_T+ − V_T−
    G: float = Field(default=1, gt=0, le=100)  # rectifier / limiter gain
    Vlim: QuantityModel = QuantityModel(value=5.6, unit="V")  # limiter output level
    Vin_dc: QuantityModel = QuantityModel(value=1, unit="V")  # log amplifier input
    R_base: QuantityModel = QuantityModel(value=10, unit="kohm")
    Rp: QuantityModel = QuantityModel(value=1, unit="kohm")  # comparator pull-up
    RL: QuantityModel = QuantityModel(value=10, unit="kohm")
    VCC: QuantityModel = QuantityModel(value=15, unit="V")
    VBE: QuantityModel = QuantityModel(value=0.65, unit="V")  # log amp: VBE at the hFE test
    res_series: Literal["E24", "E96"] = "E96"
    TA: QuantityModel = QuantityModel(value=25, unit="degC")


LABELS = {
    "VTp": "Limiar superior V_T+",
    "VTn": "Limiar inferior V_T−",
    "VH_real": "Histerese (valores comerciais)",
    "Vref_set": "Tensão de referência",
    "beta": "β = R2/(R1+R2) (inversor) ou R1/R2 (não inversor)",
    "Vo_hi": "Nível alto da saída",
    "Vo_lo": "Nível baixo da saída",
    "duty": "Ciclo de trabalho da saída",
    "Vo_avg": "Valor médio da saída",
    "Vo_max": "Pico da saída",
    "Vo_min": "Mínimo da saída",
    "Vo": "Tensão de saída",
    "slope": "Inclinação (por década de entrada)",
    "Iin": "Corrente de entrada",
    "Vlim_p": "Nível de limitação positivo",
    "Vlim_n": "Nível de limitação negativo",
    "Iz_pk": "Corrente no Zener na limitação",
    "t_d": "Atraso de comutação por SR",
    "R1": "R1",
    "R2": "R2",
    "R3": "R3",
    "R4": "R4",
    "R5": "R5",
    "Rp": "Pull-up",
}
SPEC_LABELS = {
    "config": "Circuito",
    "device": "Dispositivo (comparador)",
    "Vm": "Amplitude do sinal de entrada",
    "f": "Frequência do sinal",
    "Vref": "Referência do comparador",
    "Vc": "Centro da janela de histerese",
    "VH": "Largura da histerese",
    "G": "Ganho (retificador, limitador)",
    "Vlim": "Nível de limitação desejado",
    "Vin_dc": "Tensão de entrada (logarítmico)",
    "R_base": "Resistor de base",
    "Rp": "Resistor de pull-up (LM311)",
    "RL": "Carga",
    "VCC": "Alimentação (±)",
    "VBE": "VBE no ponto de teste do hFE (logarítmico)",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {
    "comparador": "comparador",
    "schmitt_inversor": "Schmitt inversor",
    "schmitt_nao_inversor": "Schmitt não inversor",
    "retificador_meia": "retificador de precisão de meia onda",
    "retificador_onda": "retificador de precisão de onda completa",
    "logaritmico": "amplificador logarítmico",
    "limitador": "limitador com Zener",
    "ampop": "ampop",
    "E24": "E24",
    "E96": "E96",
}


def _spec(spec: BaseModel) -> OpnlSpec:
    if not isinstance(spec, OpnlSpec):
        raise TypeError("DM-OPNL espera OpnlSpec")
    return spec


def diode_subckt(vf: float, ron: float = 1e-5) -> str:
    """Constant-drop diode: ``ron`` above VF (default 10 µΩ), 1 nS below."""
    return "\n".join(
        [
            ".subckt DIODE a k",
            f"BD a k I = (v(a,k) > {vf:.9g}) ? (v(a,k) - {vf:.9g}) / {ron:.9g} : v(a,k) * 1n",
            ".ends",
        ]
    )


class OpnlModule:
    id = "DM-OPNL"
    family = "ampops"
    title = "Ampops não lineares"
    spec_schema = OpnlSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Limiar superior", "osciloscópio em modo XY", "VTp"),
        LabItem("Limiar inferior", "osciloscópio em modo XY", "VTn"),
        LabItem("Valor médio da saída", "multímetro CC", "Vo_avg"),
        LabItem("Tensão de saída (logarítmico)", "multímetro CC", "Vo"),
    ]
    questions = [
        "Por que a histerese torna o comparador imune a ruído?",
        "Por que o retificador de precisão não sofre com a queda do diodo?",
        "Como a temperatura altera a saída do amplificador logarítmico?",
    ]
    practice = {
        "objective": "Montar o circuito, medir limiares, níveis e valor médio e comparar com o "
        "projeto.",
        "material": "Fonte simétrica, gerador de funções, osciloscópio, multímetro, ampop, "
        "diodos, Zeners e resistores da lista de materiais.",
        "procedure": [
            "Aplique uma triangular lenta e veja a curva de transferência em modo XY.",
            "Meça os níveis de saída e os limiares; compare com o projeto.",
            "Para os retificadores, meça o valor médio e veja a saída perto do zero.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        c = s.config
        if c == "comparador" and s.device == "comparador":
            return [Role(designator="U1", category="comparator", description="Comparador")]
        out = [Role(designator="U1", category="opamp", description="Amplificador operacional")]
        if c == "retificador_onda":
            out.append(Role(designator="U2", category="opamp", description="Ampop somador"))
        if c.startswith("retificador") or c == "limitador":
            out += [
                Role(designator="D1", category="diode.signal", description="Diodo"),
                Role(designator="D2", category="diode.signal", description="Diodo"),
            ]
        if c == "limitador":
            out += [
                Role(designator="DZ1", category="diode.zener", description="Zener"),
                Role(designator="DZ2", category="diode.zener", description="Zener"),
            ]
        if c == "logaritmico":
            out.append(Role(designator="Q1", category="bjt.npn", description="Transistor (log)"))
        return out

    def required_ratings(self, role: Role) -> list[str]:
        if role.category.startswith("diode.zener"):
            return ["Ptot"]
        if role.category.startswith("diode"):
            return ["VRRM", "IF(AV)"]
        if role.category.startswith("bjt"):
            return ["VCEO", "IC"]
        return []  # op-amp and comparator supply limits checked in accepts

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0, "K/W")

    def _vz_target(self, s: OpnlSpec, vf: float = 0.7) -> float:
        return float(s.Vlim.to_pint().m_as("V")) - vf

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        s = _spec(spec)
        vs = s.VCC.to_pint().m_as("V")
        if role.category in ("opamp", "comparator"):
            sym = rec.parameters.get("VS_max")
            tot = rec.parameters.get("VS_total_max")
            return (sym is not None and (sym.max or 0) >= vs) or (
                tot is not None and (tot.max or 0) >= 2 * vs
            )
        if role.category == "diode.zener":
            vz = vz_of(rec)
            t = self._vz_target(s)
            return vz is not None and "ZZT" in rec.parameters and abs(vz - t) <= 0.15 * t
        return True

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        if role.category == "diode.zener":
            return abs((vz_of(rec) or 0.0) - self._vz_target(_spec(spec)))
        if role.category == "opamp":
            sr = quantity(rec, "SR", ("typ", "min"))
            return -float(sr.m_as("V/us")) if sr is not None else 0.0  # fastest edges first
        return 0.0

    # ------------------------------------------------------------------ models
    def _ops(self, s: OpnlSpec, devices: Mapping[str, Device], log: CalcLog) -> list[OpAmp]:
        vcc = s.VCC.to_pint().m_as("V")
        n = 2 if s.config == "retificador_onda" else 1
        out = []
        for k in range(n):
            d = f"U{k + 1}"
            out.append(opamp_model(devices[d].record, vcc, -vcc, log, d, with_errors=False)[0])
        return out

    def _comparator_vol(self, rec: ComponentRecord | None) -> float:
        if rec is None:
            return 0.0
        q = quantity(rec, "VOL", ("typ", "max"))
        if q is None:
            raise ValueError(f"{rec.part_number}: datasheet sem VOL")
        return float(q.m_as("V"))

    def _zener(self, s: OpnlSpec, dev: Device, log: CalcLog, d: str, vf: float) -> ZenerPwl:
        if dev.record is None:
            return ZenerPwl(self._vz_target(s, vf), 5e-3, 1e-3, None)
        return zener_pwl(dev.record, log, d)[0]

    # ------------------------------------------------------------------ design
    def _design(
        self, s: OpnlSpec, devices: Mapping[str, Device], log: CalcLog
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        """Part values, summary magnitudes (SI), warnings, netlist lines and the test period."""
        c = s.config
        ser = s.res_series
        vm = s.Vm.to_pint().m_as("V")
        f = s.f.to_pint().m_as("Hz")
        rb = s.R_base.to_pint().m_as("ohm")
        rl = s.RL.to_pint().m_as("ohm")
        vcc = s.VCC.to_pint().m_as("V")
        v: dict[str, float] = {}
        sm: dict[str, float] = {}
        w: list[DesignWarning] = []
        t_period = 1 / f

        def com(step: str, desc: str, q: float) -> float:
            return float(commercial(log, step, desc, Q_(q, "ohm"), ser, "nearest").m_as("ohm"))

        sine = f"Vin in 0 SIN(0 {vm:.9g} {f:.9g})"
        if c == "comparador" and s.device == "comparador":
            vol = self._comparator_vol(devices["U1"].record)
            rp = s.Rp.to_pint().m_as("ohm")
            vref = s.Vref.to_pint().m_as("V")
            hi = vcc * rl / (rp + rl)
            v["Rp"] = rp
            sm |= {"Vo_hi": hi, "Vo_lo": vol}
            lines = [
                sine,
                f"Vref ref 0 DC {vref:.9g}",
                f"Vcc vcc 0 DC {vcc:.9g}",
                f"Rp o vcc {rp:.9g}",
                f"RL o 0 {rl:.9g}",
                # open-collector output: saturates at VOL while v+ < v− (1 mΩ above VOL)
                f"BU1 o 0 I = (v(in) - v(ref) < 0) ? (v(o) - {vol:.9g}) / 1m : 0",
            ]
            log.add(
                record(
                    "Vo_hi",
                    "Nível alto da saída em coletor aberto (pull-up e carga)",
                    r"V_{OH} = V_{CC}\frac{R_L}{R_p + R_L},\quad V_{OL} = V_{OL,datasheet}",
                    output=Q_(hi, "V"),
                    inputs={"R_p": Q_(rp, "ohm"), "R_L": Q_(rl, "ohm"), "V_{OL}": Q_(vol, "V")},
                    assumptions=["transistor de saída cortado: fuga desprezível"],
                    reference=REF,
                )
            )
            self._duty(s, vm, vref, sm, log)
            return v, sm, w, lines, t_period

        ops = self._ops(s, devices, log)
        u = ops[0]
        if c == "comparador":
            vref = s.Vref.to_pint().m_as("V")
            sm |= {"Vo_hi": u.v_hi, "Vo_lo": u.v_lo}
            lines = [
                sine,
                f"Vref ref 0 DC {vref:.9g}",
                f"RL o 0 {rl:.9g}",
                *u.nonlinear_lines("U1", "in", "ref", "o"),
            ]
            self._duty(s, vm, vref, sm, log)
            return v, sm, w, lines, t_period

        if c in ("schmitt_inversor", "schmitt_nao_inversor"):
            return self._schmitt(s, u, log, com, rl, vm, f)

        if c in ("retificador_meia", "retificador_onda"):
            vf = [devices[d].drop.m_as("V") for d in ("D1", "D2")]
            r1 = rb
            g1 = s.G if c == "retificador_meia" else 1.0
            r2 = com("R2", "R2 (ganho do retificador)", g1 * r1)
            v |= {"R1": r1, "R2": r2}
            lines = [sine, diode_subckt(max(vf)), *u.nonlinear_lines("U1", "0", "n", "a")]
            lines.append(f"R1 in n {r1:.9g}")
            if c == "retificador_meia":
                # positive output in the negative half-cycle: D2 a → o, D1 n → a
                lines += [f"R2 o n {r2:.9g}", "XD2 a o DIODE", "XD1 n a DIODE"]
                lines.append(f"RL o 0 {rl:.9g}")
                gp, gn = 0.0, r2 / r1
                out = "o"
            else:
                # half wave −vin in the positive half-cycle (reversed diodes) + summing amp
                ra = rb
                rbb = com("R4", "R4 = R3/2 (meia onda × 2 no somador)", ra / 2)
                rf = com("R5", "R5 (ganho do somador)", s.G * ra)
                v |= {"R3": ra, "R4": rbb, "R5": rf}
                lines += [f"R2 h n {r2:.9g}", "XD2 h a DIODE", "XD1 a n DIODE"]
                ops2 = ops[1]
                lines += [
                    f"R3 in s {ra:.9g}",
                    f"R4 h s {rbb:.9g}",
                    f"R5 s o {rf:.9g}",
                    f"RL o 0 {rl:.9g}",
                    *ops2.nonlinear_lines("U2", "0", "s", "o"),
                ]
                g_h = r2 / r1
                gp = rf * (g_h / rbb - 1 / ra)
                gn = rf / ra
                out = "o"
            avg = vm * (gp + gn) / math.pi
            sm |= {"Vo_avg": avg, "Vo_max": vm * max(gp, gn), "Vo_min": 0.0}
            log.add(
                record(
                    "Vo_avg",
                    "Valor médio da saída do retificador de precisão",
                    r"V_{o,med} = \frac{V_m (G_+ + G_-)}{\pi}",
                    output=Q_(avg, "V"),
                    inputs={"V_m": Q_(vm, "V"), "G_+": Q_(gp, ""), "G_-": Q_(gn, "")},
                    assumptions=[
                        "ampop com realimentação pelos diodos: a queda VF não aparece na saída",
                        "G_+ e G_- são os ganhos em cada semiciclo com os resistores comerciais",
                    ],
                    reference=REF_RECT,
                )
            )
            td = 2 * max([*vf, 0.6]) / u.SR if math.isfinite(u.SR) else 0.0
            sm["t_d"] = td
            if td * 2 * math.pi * f > 0.05:
                w.append(
                    DesignWarning(
                        code="slew",
                        message=f"O ampop leva {td * 1e6:.3g} µs para atravessar a zona morta "
                        "dos diodos: distorção visível perto do zero nessa frequência.",
                    )
                )
            assert out == "o"
            return v, sm, w, lines, t_period

        if c == "logaritmico":
            return self._log(s, u, devices["Q1"], log, com, rb)

        # limiter
        vf = devices["D1"].drop.m_as("V")
        z = self._zener(s, devices["DZ1"], log, "DZ1", vf)
        r1 = rb
        rf = com("R2", "R2 (ganho do inversor)", s.G * r1)
        v |= {"R1": r1, "R2": rf}
        vlim = (vf + z.VZ0 + z.rz * vm / r1) / (1 + z.rz / rf)
        iz = vm / r1 - vlim / rf
        log.add(
            record(
                "Vlim_p",
                "Nível de limitação (ramo Zener + diodo conduzindo)",
                r"V_{lim} = \frac{V_F + V_{Z0} + r_z V_m/R_1}{1 + r_z/R_2}",
                output=Q_(vlim, "V"),
                inputs={
                    "V_F": Q_(vf, "V"),
                    "V_{Z0}": Q_(z.VZ0, "V"),
                    "r_z": Q_(z.rz, "ohm"),
                    "V_m": Q_(vm, "V"),
                    "R_1": Q_(r1, "ohm"),
                    "R_2": Q_(rf, "ohm"),
                },
                assumptions=["terra virtual na entrada inversora; mesmos Zener e diodo nos dois"],
                reference=PERT,
            )
        )
        # below the Zener level the circuit is a plain inverter: the peak is G·Vm
        vpk = min(vlim, s.G * vm)
        sm |= {"Vlim_p": vlim, "Vlim_n": -vlim, "Iz_pk": iz, "Vo_max": vpk, "Vo_min": -vpk}
        if s.G * vm <= vlim:
            w.append(
                DesignWarning(
                    code="sem_limitacao",
                    message="G·Vm não alcança o nível do Zener: o circuito não chega a limitar.",
                )
            )
        if z.IZK is not None and 0 < iz < z.IZK:
            w.append(
                DesignWarning(
                    code="izk",
                    message=f"Corrente no Zener ({iz * 1e3:.3g} mA) abaixo de IZK: a tensão de "
                    "limitação fica abaixo da nominal (joelho).",
                )
            )
        # The series branch depends on VF + VZ0 and rz + Ron, not on how its on-resistance
        # is split. Balance the two resistances to avoid a 100 kS diode in series with
        # a nearly floating node (ngspice 47/Windows: timestep too small in XD2.BD).
        # Preserve VZ0 and the total slope; these are equivalent model coefficients,
        # not new datasheet parameters. Other circuits keep the original diode model.
        branch_r = (z.rz + 1e-5) / 2
        z_sim = replace(z, rz=branch_r, VZ=z.VZ0 + z.IZT * branch_r)
        lines = [
            sine,
            diode_subckt(vf, ron=branch_r),
            z_sim.spice_subckt(),
            f"R1 in n {r1:.9g}",
            f"R2 o n {rf:.9g}",
            "XDZ1 o m1 ZPWL",
            "XD1 m1 n DIODE",
            "XDZ2 n m2 ZPWL",
            "XD2 m2 o DIODE",
            f"RL o 0 {rl:.9g}",
            *u.nonlinear_lines("U1", "0", "n", "o"),
        ]
        return v, sm, w, lines, t_period

    def _duty(
        self, s: OpnlSpec, vm: float, vref: float, sm: dict[str, float], log: CalcLog
    ) -> None:
        if abs(vref) >= vm:
            raise ValueError("A referência precisa ficar dentro da amplitude do sinal")
        d = 0.5 - math.asin(vref / vm) / math.pi
        sm["duty"] = d
        log.add(
            record(
                "duty",
                "Ciclo de trabalho da saída (senoide contra a referência)",
                r"D = \frac{1}{2} - \frac{1}{\pi}\arcsin\frac{V_{ref}}{V_m}",
                output=Q_(d * 100, "percent"),
                inputs={"V_{ref}": Q_(vref, "V"), "V_m": Q_(vm, "V")},
                assumptions=["saída alta enquanto v_in > V_ref; atrasos iguais nas duas bordas"],
                reference=REF,
            )
        )

    def _schmitt(
        self,
        s: OpnlSpec,
        u: OpAmp,
        log: CalcLog,
        com: object,
        rl: float,
        vm: float,
        f: float,
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        assert callable(com)
        vh = s.VH.to_pint().m_as("V")
        vc = s.Vc.to_pint().m_as("V")
        rb = s.R_base.to_pint().m_as("ohm")
        span = u.v_hi - u.v_lo
        if vh >= span:
            raise ValueError("Histerese maior que a excursão da saída do ampop")
        v: dict[str, float] = {}
        w: list[DesignWarning] = []
        if s.config == "schmitt_inversor":
            beta0 = vh / span
            r2 = rb
            r1 = com("R1", "R1 (saída → entrada +)", r2 * (1 - beta0) / beta0)
            beta = r2 / (r1 + r2)
            vref = (vc - beta * (u.v_hi + u.v_lo) / 2) / (1 - beta)
            vtp = (1 - beta) * vref + beta * u.v_hi
            vtn = (1 - beta) * vref + beta * u.v_lo
            latex = r"V_{T\pm} = (1-\beta)V_{ref} + \beta V_{sat\pm},\ \beta = \frac{R_2}{R_1+R_2}"
            lines = [
                f"Vref ref 0 DC {vref:.9g}",
                f"R1 o p {r1:.9g}",
                f"R2 p ref {r2:.9g}",
                *u.nonlinear_lines("U1", "p", "in", "o"),
            ]
            k = beta
        else:
            k = vh / span
            r2 = rb
            r1 = com("R1", "R1 (entrada → entrada +)", k * r2)
            k = r1 / r2
            vref = (vc + k * (u.v_hi + u.v_lo) / 2) / (1 + k)
            vtp = vref * (1 + k) - u.v_lo * k
            vtn = vref * (1 + k) - u.v_hi * k
            latex = (
                r"V_{T\pm} = V_{ref}\left(1 + \frac{R_1}{R_2}\right) - V_{sat\mp}\frac{R_1}{R_2}"
            )
            lines = [
                f"Vref ref 0 DC {vref:.9g}",
                f"R1 in p {r1:.9g}",
                f"R2 o p {r2:.9g}",
                *u.nonlinear_lines("U1", "p", "ref", "o"),
            ]
        lines.append(f"RL o 0 {rl:.9g}")
        v |= {"R1": r1, "R2": r2}
        log.add(
            record(
                "VTp",
                "Limiares do Schmitt com os resistores comerciais",
                latex,
                output=Q_(vtp, "V"),
                inputs={
                    "V_{T-}": Q_(vtn, "V"),
                    "V_{ref}": Q_(vref, "V"),
                    "V_{sat+}": Q_(u.v_hi, "V"),
                    "V_{sat-}": Q_(u.v_lo, "V"),
                    "R_1": Q_(r1, "ohm"),
                    "R_2": Q_(r2, "ohm"),
                },
                assumptions=[
                    "saturação nos níveis de excursão do ampop",
                    "V_ref de fonte de baixa impedância (ou divisor com Thévenin em R2)",
                    "offset do ampop desprezado (desloca os dois limiares de ±V_OS)",
                ],
                reference=REF,
            )
        )
        if max(abs(vtp), abs(vtn)) >= vm:
            raise ValueError("Os limiares ficam fora da amplitude do sinal de entrada")
        # the threshold test uses a triangle slow enough for the switching delay to be
        # negligible: slewing to the middle of the swing plus the regenerative start, a few
        # time constants 1/(2π·GBW·b), b the positive-feedback fraction
        td = span / (2 * u.SR) if math.isfinite(u.SR) else 0.0
        b = r2 / (r1 + r2) if s.config == "schmitt_inversor" else r1 / (r1 + r2)
        t_sw = td + 5 / (2 * math.pi * u.GBW * b)
        f_test = min(f, DELAY_FRAC / (4 * t_sw))
        if 4 * vm * f * td > 0.01 * vh:
            w.append(
                DesignWarning(
                    code="atraso",
                    message=f"Na frequência do sinal, o atraso de SR ({td * 1e6:.3g} µs) desloca "
                    f"os limiares em {4 * vm * f * td * 1e3:.3g} mV (entrada triangular).",
                )
            )
        tri = (
            f"Vin in 0 PWL(0 {-vm:.9g} {0.5 / f_test:.9g} {vm:.9g} {1 / f_test:.9g} {-vm:.9g}) r=0"
        )
        sm = {
            "VTp": vtp,
            "VTn": vtn,
            "VH_real": vtp - vtn,
            "Vref_set": vref,
            "beta": k,
            "Vo_hi": u.v_hi,
            "Vo_lo": u.v_lo,
            "t_d": td,
        }
        return v, sm, w, [tri, *lines], 1 / f_test

    def _log(
        self, s: OpnlSpec, u: OpAmp, dev: Device, log: CalcLog, com: object, rb: float
    ) -> tuple[dict[str, float], dict[str, float], list[DesignWarning], list[str], float]:
        vin = s.Vin_dc.to_pint().m_as("V")
        if vin <= 0:
            raise ValueError("O amplificador logarítmico precisa de entrada positiva")
        iin = vin / rb
        q, _ = bjt_model(dev.record, iin, s.VBE.to_pint(), 100.0, log, "Q1")
        vo = -VT_300K * math.log(iin / q.IS + 1)
        log.add(
            record(
                "Vo",
                "Saída do amplificador logarítmico (transdiodo)",
                r"v_o = -V_T \ln\left(\frac{v_{in}}{R\,I_S} + 1\right)",
                output=Q_(vo, "V"),
                inputs={
                    "v_{in}": Q_(vin, "V"),
                    "R": Q_(rb, "ohm"),
                    "I_S": Q_(q.IS, "A"),
                    "V_T": Q_(VT_300K, "V"),
                },
                assumptions=[
                    "coletor no terra virtual (V_CB = 0): I_C = v_in/R",
                    "V_T a 27 °C; I_S do modelo do transistor escolhido",
                ],
                reference=PERT,
            )
        )
        slope = -VT_300K * math.log(10)
        lines = [
            f"Vin in 0 DC {vin:.9g}",
            f"R1 in n {rb:.9g}",
            q.spice("QLOG"),
            "Q1 n 0 o QLOG",
            *u.nonlinear_lines("U1", "0", "n", "o"),
        ]
        sm = {"Vo": vo, "slope": slope, "Iin": iin}
        v = {"R1": rb}
        w: list[DesignWarning] = []
        if vo < u.v_lo:
            w.append(DesignWarning(code="excursao", message="A saída passa da excursão."))
        return v, sm, w, lines, 1e-3

    @staticmethod
    def _q(key: str, x: float) -> pint.Quantity:
        if key == "duty":
            return Q_(x * 100, "percent")
        if key == "beta":
            return Q_(x, "")
        if key == "slope":
            return Q_(x, "V").to("mV")
        if key == "Iin":
            return Q_(x, "A").to("uA")
        if key == "Iz_pk":
            return Q_(x, "A").to("mA")
        if key == "t_d":
            return Q_(x, "s").to("us")
        return Q_(x, "V")

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        v, sm, warnings, _, _ = self._design(s, devices, log)
        summary: dict[str, pint.Quantity] = {k: self._q(k, x) for k, x in sm.items()}
        for k, x in v.items():
            summary[k] = Q_(x, "ohm")
        stresses = self._stresses(s, sm, devices)
        traces, period = self._waves(s, sm)
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={},
            warnings=warnings,
            convergence_keys=tuple(k for k in ("VTp", "Vo_avg", "Vo", "Vlim_p") if k in sm),
            traces=traces,
            trace_period=Q_(period, "s") if traces else None,
        )

    def _stresses(
        self, s: OpnlSpec, sm: Mapping[str, float], devices: Mapping[str, Device]
    ) -> list[Stress]:
        out: list[Stress] = []
        vcc = s.VCC.to_pint().m_as("V")
        rb = s.R_base.to_pint().m_as("ohm")
        if s.config.startswith("retificador") or s.config == "limitador":
            i_avg = s.Vm.to_pint().m_as("V") / rb / math.pi
            for d in ("D1", "D2"):
                out += [
                    Stress(
                        designator=d,
                        key="VRRM",
                        label="Tensão reversa (excursão do ampop)",
                        value=QuantityModel(value=2 * vcc, unit="V"),
                        calc_step_id="Vo_avg" if "Vo_avg" in sm else "Vlim_p",
                    ),
                    Stress(
                        designator=d,
                        key="IF(AV)",
                        label="Corrente média",
                        value=QuantityModel(value=i_avg, unit="A"),
                        calc_step_id="Vo_avg" if "Vo_avg" in sm else "Vlim_p",
                    ),
                ]
        if s.config == "limitador":
            pz = sm["Vlim_p"] * max(sm["Iz_pk"], 0.0)
            for d in ("DZ1", "DZ2"):
                out.append(
                    Stress(
                        designator=d,
                        key="Ptot",
                        label="Potência no Zener (pico, por segurança)",
                        value=QuantityModel(value=max(pz, 1e-6), unit="W"),
                        calc_step_id="Vlim_p",
                    )
                )
        if s.config == "logaritmico":
            out += [
                Stress(
                    designator="Q1",
                    key="VCEO",
                    label="Tensão coletor-emissor",
                    value=QuantityModel(value=max(-sm["Vo"], 0.1), unit="V"),
                    calc_step_id="Vo",
                ),
                Stress(
                    designator="Q1",
                    key="IC",
                    label="Corrente de coletor",
                    value=QuantityModel(value=sm["Iin"], unit="A"),
                    calc_step_id="Vo",
                ),
            ]
        return out

    def _waves(self, s: OpnlSpec, sm: Mapping[str, float]) -> tuple[dict[str, Trace], float]:
        c = s.config
        vm = s.Vm.to_pint().m_as("V")
        f = s.f.to_pint().m_as("Hz")
        th = np.linspace(0, 2 * math.pi, 720, endpoint=False)
        if c == "logaritmico":
            return {}, 0.0
        if c.startswith("schmitt"):
            tri = np.interp(th, [0, math.pi, 2 * math.pi], [-vm, vm, -vm])
            hi, lo = sm["Vo_hi"], sm["Vo_lo"]
            inv = c == "schmitt_inversor"
            state = hi if inv else lo
            out = []
            for x in tri:
                if x >= sm["VTp"]:
                    state = lo if inv else hi
                elif x <= sm["VTn"]:
                    state = hi if inv else lo
                out.append(state)
            return {"Entrada": make_trace("V", tri), "Saída": make_trace("V", out)}, 1 / f
        vin = vm * np.sin(th)
        if c == "comparador":
            vref = s.Vref.to_pint().m_as("V")
            vo = np.where(vin > vref, sm["Vo_hi"], sm["Vo_lo"])
        elif c.startswith("retificador"):
            gn = sm["Vo_max"] / vm
            vo = np.where(vin < 0, -vin, 0.0) * gn if c == "retificador_meia" else np.abs(vin) * gn
        else:
            g = s.G
            vo = np.clip(-g * vin, sm["Vlim_n"], sm["Vlim_p"])
        return {"Entrada": make_trace("V", vin), "Saída": make_trace("V", vo)}, 1 / f

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        _, _sm, _, lines, period = self._design(s, devices, CalcLog())
        c = s.config
        tol_sat = "excursão: mesmo grampo do modelo (sobre-passo SR·C/G desprezível)"
        checks: list[SimCheck] = []
        if c == "comparador":
            checks = [
                SimCheck(
                    quantity="Ciclo de trabalho",
                    summary_key="duty",
                    metric="duty",
                    probe="v(o)",
                    tolerance_pct=1.0,
                    justification="atraso de comutação igual nas duas bordas",
                ),
                SimCheck(
                    quantity="Nível alto",
                    summary_key="Vo_hi",
                    metric="max",
                    probe="v(o)",
                    tolerance_pct=0.5,
                    justification=tol_sat,
                ),
            ]
        elif c.startswith("schmitt"):
            rise_is_low = c == "schmitt_inversor"  # inverting: output rises at V_T−
            checks = [
                SimCheck(
                    quantity="Limiar superior",
                    summary_key="VTp",
                    metric="x_fall" if rise_is_low else "x_rise",
                    probe="v(o)",
                    voltage="v(in)",
                    tolerance_pct=1.0,
                    justification="triangular lenta: atraso de comutação ≈ 0,01 % de Vm",
                ),
                SimCheck(
                    quantity="Limiar inferior",
                    summary_key="VTn",
                    metric="x_rise" if rise_is_low else "x_fall",
                    probe="v(o)",
                    voltage="v(in)",
                    tolerance_pct=1.0,
                    justification="triangular lenta: atraso de comutação ≈ 0,01 % de Vm",
                ),
                SimCheck(
                    quantity="Nível alto",
                    summary_key="Vo_hi",
                    metric="max",
                    probe="v(o)",
                    tolerance_pct=0.5,
                    justification=tol_sat,
                ),
            ]
        elif c.startswith("retificador"):
            checks = [
                SimCheck(
                    quantity="Valor médio da saída",
                    summary_key="Vo_avg",
                    metric="avg",
                    probe="v(o)",
                    tolerance_pct=1.0,
                    justification="zona morta (2VF/SR) e GBW finito do ampop",
                ),
                SimCheck(
                    quantity="Pico da saída",
                    summary_key="Vo_max",
                    metric="max",
                    probe="v(o)",
                    tolerance_pct=1.0,
                    justification="GBW finito do ampop",
                ),
            ]
        elif c == "logaritmico":
            checks = [
                SimCheck(
                    quantity="Tensão de saída",
                    summary_key="Vo",
                    metric="avg",
                    probe="v(o)",
                    tolerance_pct=0.5,
                    justification="mesmo modelo de Ebers-Moll; ganho finito do ampop",
                )
            ]
        else:
            checks = [
                SimCheck(
                    quantity="Pico positivo (limitação)",
                    summary_key="Vo_max",
                    metric="max",
                    probe="v(o)",
                    tolerance_pct=1.0,
                    justification="mesmos modelos de Zener e diodo; ganho finito do ampop",
                ),
                SimCheck(
                    quantity="Pico negativo (limitação)",
                    summary_key="Vo_min",
                    metric="min",
                    probe="v(o)",
                    tolerance_pct=1.0,
                    justification="mesmos modelos de Zener e diodo; ganho finito do ampop",
                ),
            ]
        n_per = 3
        if c == "comparador":  # duty cycle between two rising edges: a two-period window
            period *= 2
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[c]}",
            netlist="\n".join([TRAN_OPTIONS, *lines]),
            tran_stop=QuantityModel(value=n_per * period, unit="s"),
            tran_step=QuantityModel(value=period / NPTS, unit="s"),
            period=QuantityModel(value=period, unit="s"),
            probes={"Entrada": "v(in)", "Saída": "v(o)"},
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        vals = {k: format_eng(sm[k].to_pint()) for k in sm if k[0] == "R" and k[1:].isdigit()}
        if "Rp" in sm:
            vals["Rp"] = format_eng(sm["Rp"].to_pint())
        parts = {c.designator: c.part_number for c in result.selection}
        return value_sheet(title, ENUM_LABELS[s.config], vals, parts)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        sm = result.summary
        rows = []
        for k in sm:
            if (k[0] == "R" and k[1:].isdigit()) or k == "Rp":
                rows.append(
                    passive(k, "Resistor 1 % (filme metálico)", format_eng(sm[k].to_pint()))
                )
        return rows
