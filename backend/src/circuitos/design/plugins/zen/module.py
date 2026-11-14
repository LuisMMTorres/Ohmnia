"""DM-ZEN: Zener shunt regulator, alone or driving an emitter-follower pass transistor.

Design for the worst case of line and load (Boylestad & Nashelsky, *Electronic Devices and
Circuit Theory*, 11th ed., ch. 2, "Zener diodes" — fixed/variable Vi and RL; Malvino,
*Electronic Principles*, Zener chapter: the Zener regulator and the Zener follower):

* the series resistor is the largest that still keeps IZ ≥ IZ,mín at the lowest input and the
  heaviest load (rounded down in the E-series, so the commercial value also keeps it);
* the Zener and resistor dissipations are taken at the highest input and the lightest load.

The Zener is the piecewise-linear model VZ = VZ0 + rz·IZ (``design.devmodels``); the same model
goes to the simulator, so the check compares the arithmetic of the two corners exactly.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import pint
from pydantic import BaseModel, Field
from scipy.optimize import brentq

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.analog import commercial, dc_check, dc_circuit, q
from circuitos.design.base import Circuit, DesignResult, DesignWarning, Role, Stress
from circuitos.design.devmodels import BOYLESTAD, VT_300K, Bjt, ZenerPwl, bjt_model, zener_pwl
from circuitos.design.engine import Analysis, Device
from circuitos.reports.common import BomRow, LabItem, passive, resistor_row
from circuitos.reports.schematic import Svg

Variant = Literal["simples", "transistor"]
OPEN_LOAD = 1e9  # Ω, stands for an open output of the emitter follower


class ZenSpec(BaseModel):
    variant: Variant = "simples"
    Vin: QuantityModel = QuantityModel(value=15, unit="V")  # nominal unregulated input
    vin_tol_pct: float = Field(default=10.0, ge=0, le=40)  # ± around Vin
    Vo: QuantityModel = QuantityModel(value=9.1, unit="V")  # desired output
    IL_min: QuantityModel = QuantityModel(value=0, unit="mA")
    IL_max: QuantityModel = QuantityModel(value=30, unit="mA")
    iz_min_frac: float = Field(default=0.1, gt=0, le=1)  # IZ,min ≥ this × IZT (and ≥ IZK)
    vz_window_pct: float = Field(default=5.0, gt=0, le=20)  # accepted VZ around the target
    VBE: QuantityModel = QuantityModel(value=0.7, unit="V")  # assumption at the hFE test IC
    beta_ideal: float = Field(default=100, gt=1, le=2000)  # ideal pass only
    res_series: Literal["E12", "E24"] = "E24"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")
    Rth_cs: QuantityModel = QuantityModel(value=0.5, unit="K/W")


LABELS = {
    "Vin_min": "Tensão de entrada mínima",
    "Vin_max": "Tensão de entrada máxima",
    "VZ_target": "VZ desejada",
    "VZ": "VZ do Zener escolhido (em IZT)",
    "VZ0": "VZ0 do modelo",
    "rz": "Resistência dinâmica rz",
    "IZ_min": "Corrente Zener mínima admitida",
    "Rs": "Resistor série Rs",
    "P_Rs": "Potência máxima em Rs",
    "IZ_a": "IZ com entrada mínima e carga máxima",
    "IZ_b": "IZ com entrada máxima e carga mínima",
    "Vo_a": "Saída com entrada mínima e carga máxima",
    "Vo_b": "Saída com entrada máxima e carga mínima",
    "PZ_max": "Potência máxima no Zener",
    "PQ_max": "Potência máxima no transistor",
    "VCE_max": "VCE máxima do transistor",
    "IC_max": "Corrente de coletor máxima",
    "IB_max": "Corrente de base máxima",
    "line_reg": "Regulação de linha ΔVo/ΔVin",
    "load_reg": "Regulação de carga ΔVo/ΔIL",
    "RL_min": "Resistência de carga mínima",
    "RL_max": "Resistência de carga máxima",
}
SPEC_LABELS = {
    "variant": "Arranjo",
    "Vin": "Tensão de entrada nominal (não regulada)",
    "vin_tol_pct": "Variação da entrada (± %)",
    "Vo": "Tensão de saída desejada",
    "IL_min": "Corrente de carga mínima",
    "IL_max": "Corrente de carga máxima",
    "iz_min_frac": "IZ mínima (fração de IZT)",
    "vz_window_pct": "Janela de VZ aceita (± %)",
    "VBE": "VBE na corrente de ensaio (premissa)",
    "beta_ideal": "β de projeto (passo ideal)",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {"simples": "Zener e resistor série", "transistor": "Zener com transistor série"}


def _spec(spec: BaseModel) -> ZenSpec:
    if not isinstance(spec, ZenSpec):
        raise TypeError("DM-ZEN espera ZenSpec")
    return spec


def vz_of(rec: ComponentRecord) -> float | None:
    p = rec.parameters.get("VZ")
    if p is None or p.typ is None:
        return None
    return Q_(p.typ, p.unit).m_as("V")


class ZenModule:
    id = "DM-ZEN"
    family = "fontes"
    title = "Regulador Zener"
    spec_schema = ZenSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão de saída, entrada mínima e carga máxima", "multímetro CC", "Vo_a"),
        LabItem("Tensão de saída, entrada máxima e carga mínima", "multímetro CC", "Vo_b"),
        LabItem("Corrente no Zener, pior caso de dissipação", "multímetro em série", "IZ_b"),
        LabItem("Corrente no Zener, pior caso de regulação", "multímetro em série", "IZ_a"),
    ]
    questions = [
        "Por que Rs é calculado com a entrada mínima e a carga máxima, e a potência do Zener "
        "com a entrada máxima e a carga mínima?",
        "O que acontece com a saída se a carga pedir mais corrente que IL,máx? Verifique "
        "medindo com uma carga menor que RL,mín.",
        "Compare a regulação de linha medida com rz/(Rs + rz). Por que o transistor série "
        "melhora a regulação de carga?",
    ]
    practice = {
        "objective": "Montar o regulador, levantar a saída nos dois cantos de pior caso "
        "(entrada mínima com carga máxima; entrada máxima com carga mínima) e comparar com o "
        "cálculo e a simulação.",
        "material": "Fonte CC ajustável, multímetros, resistores de carga RL,mín e RL,máx "
        "(ou carga eletrônica) e os componentes da lista de materiais.",
        "procedure": [
            "Monte o circuito com a fonte desligada e o limite de corrente ajustado.",
            "Ajuste a entrada para Vin,mín, ligue RL,mín e meça Vo e IZ.",
            "Ajuste a entrada para Vin,máx, ligue RL,máx (ou deixe sem carga) e meça Vo e IZ.",
            "Varie a entrada com carga fixa e trace Vo × Vin; calcule a regulação de linha.",
            "Confira a temperatura do Zener (e do transistor) no pior caso de dissipação.",
        ],
    }

    # ------------------------------------------------------------------ roles
    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        roles = [Role(designator="DZ1", category="diode.zener", description="Diodo Zener")]
        if s.variant == "transistor":
            roles.append(
                Role(designator="Q1", category="bjt.npn", description="Transistor série NPN")
            )
        return roles

    def required_ratings(self, role: Role) -> list[str]:
        return ["Ptot"] if role.designator == "DZ1" else ["VCEO", "IC"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).Rth_cs.to_pint()

    def _target(self, s: ZenSpec) -> float:
        vo = float(s.Vo.to_pint().m_as("V"))
        vbe = float(s.VBE.to_pint().m_as("V")) if s.variant == "transistor" else 0.0
        return vo + vbe

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        if role.designator != "DZ1":
            return True
        s = _spec(spec)
        vz = vz_of(rec)
        target = self._target(s)
        return vz is not None and abs(vz - target) <= s.vz_window_pct / 100 * target

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        if role.designator != "DZ1":
            return 0.0
        vz = vz_of(rec)
        return abs((vz or 0.0) - self._target(_spec(spec)))

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        ref = BOYLESTAD.model_copy(update={"chapter": "2 (Zener diodes)"})
        vin = s.Vin.to_pint()
        tol = s.vin_tol_pct / 100
        vo_t = s.Vo.to_pint().m_as("V")
        il_min = s.IL_min.to_pint().m_as("A")
        il_max = s.IL_max.to_pint().m_as("A")
        if il_max <= 0 or il_min < 0 or il_min > il_max:
            raise ValueError("Use 0 ≤ IL,mín ≤ IL,máx e IL,máx > 0")
        vin_min = log.add(
            record(
                "Vin_min",
                "Entrada mínima",
                r"V_{in,min} = V_{in}(1 - \delta)",
                output=(vin * (1 - tol)).to("V"),
                inputs={"V_{in}": vin, r"\delta": Q_(s.vin_tol_pct, "percent")},
            )
        ).m_as("V")
        vin_max = log.add(
            record(
                "Vin_max",
                "Entrada máxima",
                r"V_{in,max} = V_{in}(1 + \delta)",
                output=(vin * (1 + tol)).to("V"),
                inputs={"V_{in}": vin, r"\delta": Q_(s.vin_tol_pct, "percent")},
            )
        ).m_as("V")
        # loads as resistors at the desired output (what the user connects on the bench)
        rl_min = vo_t / il_max
        rl_max = vo_t / il_min if il_min > 0 else math.inf
        if s.variant == "transistor" and not math.isfinite(rl_max):
            rl_max = OPEN_LOAD  # the emitter needs a path: a 1 GΩ leak stands for "no load"
        log.add(
            record(
                "RL_min",
                "Carga mínima (corrente máxima na tensão desejada)",
                r"R_{L,min} = V_o / I_{L,max}",
                output=Q_(rl_min, "ohm"),
                inputs={"V_o": s.Vo.to_pint(), "I_{L,max}": s.IL_max.to_pint()},
                reference=ref,
            )
        )
        if math.isfinite(rl_max) and rl_max < OPEN_LOAD:
            log.add(
                record(
                    "RL_max",
                    "Carga máxima (corrente mínima na tensão desejada)",
                    r"R_{L,max} = V_o / I_{L,min}",
                    output=Q_(rl_max, "ohm"),
                    inputs={"V_o": s.Vo.to_pint(), "I_{L,min}": s.IL_min.to_pint()},
                    reference=ref,
                )
            )

        # ---------------------------------------------------------------- the Zener
        dz = devices["DZ1"].record
        target = self._target(s)
        if dz is None:
            z = ZenerPwl(VZ=target, IZT=0.0, rz=0.0, IZK=None)
            iz_floor = 1e-3
            log.add(
                record(
                    "VZ0_DZ1",
                    "Zener ideal (passo sem componente): VZ igual à desejada",
                    r"V_Z = V_{Z,desejada},\; r_z = 0",
                    output=Q_(target, "V"),
                )
            )
        else:
            z, w = zener_pwl(dz, log, "DZ1")
            warnings += [DesignWarning(code="modelo", message=m) for m in w]
            iz_floor = max(s.iz_min_frac * z.IZT, z.IZK or 0.0)
        vz_rec = z.VZ
        iz_min = log.add(
            record(
                "IZ_min",
                "Corrente Zener mínima admitida (critério de projeto)",
                r"I_{Z,min} = \max(I_{ZK},\; k\,I_{ZT})",
                output=Q_(iz_floor, "A").to("mA"),
                inputs={"k": Q_(s.iz_min_frac, "")}
                | ({"I_{ZT}": Q_(z.IZT, "A").to("mA")} if z.IZT else {})
                | ({"I_{ZK}": Q_(z.IZK, "A").to("mA")} if z.IZK else {}),
                assumptions=["abaixo do joelho a tensão deixa de ser regulada"],
                reference=ref,
            )
        ).m_as("A")

        # ---------------------------------------------------------------- the transistor
        bjt: Bjt | None = None
        if s.variant == "transistor":
            bjt, w = bjt_model(
                devices["Q1"].record, il_max, s.VBE.to_pint(), s.beta_ideal, log, "Q1"
            )
            warnings += [DesignWarning(code="modelo", message=m) for m in w]

        def load_current(vo: float, rl: float) -> float:
            return 0.0 if not math.isfinite(rl) else vo / rl

        def corner(vi: float, rl: float, rs: float) -> tuple[float, float, float, float]:
            """(Vo, IZ, IL, IB) at input vi and load rl with series resistor rs."""
            if bjt is None:
                # Thevenin of vi–rs and VZ0–rz, loaded by rl (Zener on while IZ > 0)
                g = 1 / rs + (1 / z.rz if z.rz > 0 else 0.0) + (1 / rl if math.isfinite(rl) else 0)
                if z.rz > 0:
                    vo = (vi / rs + z.VZ0 / z.rz) / g
                    iz = (vo - z.VZ0) / z.rz
                else:
                    vo = z.VZ0
                    iz = (vi - vo) / rs - load_current(vo, rl)
                if iz < 0:  # Zener off: plain divider
                    vo = vi * (rl / (rl + rs)) if math.isfinite(rl) else vi
                    iz = 0.0
                return vo, iz, load_current(vo, rl), 0.0

            def residual(vo: float) -> float:
                ie = load_current(vo, rl)
                ic = ie * bjt.BF / (bjt.BF + 1)
                vbe = bjt.vbe(ic) if ic > 0 else 0.0
                vz = vo + vbe
                ib = ie / (bjt.BF + 1)
                iz = (vz - z.VZ0) / z.rz if z.rz > 0 else (vi - vz) / rs - ib
                return (vi - vz) / rs - iz - ib

            if z.rz > 0:
                vo = brentq(residual, -1.0, vi)
            else:
                ic0 = load_current(vo_t, rl) * bjt.BF / (bjt.BF + 1)
                vo = z.VZ0 - (bjt.vbe(ic0) if ic0 > 0 else 0.0)
            ie = load_current(vo, rl)
            ib = ie / (bjt.BF + 1)
            ic = ie - ib
            vz = vo + (bjt.vbe(ic) if ic > 0 else 0.0)
            iz = (vz - z.VZ0) / z.rz if z.rz > 0 else (vi - vz) / rs - ib
            return vo, iz, ie, ib

        # ---------------------------------------------------------------- Rs
        if bjt is None:
            ib_max = 0.0
            rs_req = (vin_min - z.VZ0 - z.rz * iz_min) / (il_max + iz_min)
            latex = r"R_s = \frac{V_{in,min} - (V_{Z0} + r_z I_{Z,min})}{I_{L,max} + I_{Z,min}}"
            rs_inputs = {}
        else:
            ic_max = il_max * bjt.BF / (bjt.BF + 1)
            ib_max = log.add(
                record(
                    "IB_max",
                    "Corrente de base com a carga máxima",
                    r"I_{B,max} = \frac{I_{L,max}}{\beta_F + 1}",
                    output=Q_(il_max / (bjt.BF + 1), "A").to("mA"),
                    inputs={"I_{L,max}": s.IL_max.to_pint(), r"\beta_F": Q_(bjt.BF, "")},
                    reference=ref,
                )
            ).m_as("A")
            rs_req = (vin_min - z.VZ0 - z.rz * iz_min) / (ib_max + iz_min)
            latex = r"R_s = \frac{V_{in,min} - (V_{Z0} + r_z I_{Z,min})}{I_{B,max} + I_{Z,min}}"
            rs_inputs = {"I_{B,max}": Q_(ib_max, "A").to("mA")}
            log.add(
                record(
                    "VBE_Q1",
                    "VBE de Q1 com a carga máxima (modelo exponencial)",
                    r"V_{BE} = V_T \ln\!\left(\frac{I_C}{I_S} + 1\right)",
                    output=Q_(bjt.vbe(ic_max), "V"),
                    inputs={"I_C": Q_(ic_max, "A"), "I_S": Q_(bjt.IS, "A")},
                    reference=ref,
                )
            )
        if rs_req <= 0:
            raise ValueError(
                f"A entrada mínima ({vin_min:.3g} V) não basta para VZ = {vz_rec:.3g} V: "
                "aumente a entrada ou escolha uma tensão de saída menor"
            )
        rs_calc = log.add(
            record(
                "Rs_calc",
                "Maior resistor série que mantém IZ ≥ IZ,mín no pior caso",
                latex,
                output=Q_(rs_req, "ohm"),
                inputs={
                    "V_{in,min}": Q_(vin_min, "V"),
                    "V_{Z0}": Q_(z.VZ0, "V"),
                    "r_z": Q_(z.rz, "ohm"),
                    "I_{Z,min}": Q_(iz_min, "A").to("mA"),
                    "I_{L,max}": s.IL_max.to_pint(),
                    **rs_inputs,
                },
                assumptions=["entrada mínima e carga máxima"],
                reference=ref,
            )
        )
        rs = commercial(log, "Rs", "Resistor série comercial", rs_calc, s.res_series, "down").m_as(
            "ohm"
        )

        vo_a, iz_a, il_a, ib_a = corner(vin_min, rl_min, rs)
        vo_b, iz_b, _, _ = corner(vin_max, rl_max, rs)
        model_txt = "mesmas equações do modelo linear por partes" + (
            " e do transistor exponencial" if bjt else ""
        )
        for tag, vi, vo, iz, rl_txt in (
            ("a", vin_min, vo_a, iz_a, "R_{L,min}"),
            ("b", vin_max, vo_b, iz_b, "R_{L,max}"),
        ):
            label = "entrada mínima, carga máxima" if tag == "a" else "entrada máxima, carga mínima"
            log.add(
                record(
                    f"Vo_{tag}",
                    f"Tensão de saída ({label})",
                    r"\frac{V_{in} - V_Z}{R_s} = I_Z + I_B + \ldots;\quad "
                    r"V_Z = V_{Z0} + r_z I_Z;\quad V_o = V_Z" + (r" - V_{BE}(I_C)" if bjt else ""),
                    output=Q_(vo, "V"),
                    inputs={"V_{in}": Q_(vi, "V"), "R_s": Q_(rs, "ohm")},
                    assumptions=[model_txt, f"carga {rl_txt}"],
                    reference=ref,
                )
            )
            log.add(
                record(
                    f"IZ_{tag}",
                    f"Corrente no Zener ({label})",
                    r"I_Z = \frac{V_Z - V_{Z0}}{r_z}",
                    output=Q_(iz, "A").to("mA"),
                    inputs={"V_o": Q_(vo, "V")},
                    reference=ref,
                )
            )
        if iz_a < iz_min * (1 - 1e-6):
            warnings.append(
                DesignWarning(
                    code="joelho",
                    message=f"IZ no pior caso ({format_eng(Q_(iz_a, 'A'))}) ficou abaixo de "
                    f"IZ,mín ({format_eng(Q_(iz_min, 'A'))}).",
                )
            )
        vz_b = z.VZ0 + z.rz * iz_b
        pz = log.add(
            record(
                "PZ_max",
                "Potência máxima no Zener (entrada máxima, carga mínima)",
                r"P_Z = V_Z\,I_Z",
                output=Q_(vz_b * iz_b, "W"),
                inputs={"V_Z": Q_(vz_b, "V"), "I_Z": Q_(iz_b, "A").to("mA")},
                reference=ref,
            )
        )
        i_rs_b = (vin_max - vz_b) / rs
        p_rs = log.add(
            record(
                "P_Rs",
                "Potência máxima no resistor série",
                r"P_{R_s} = \frac{(V_{in,max} - V_Z)^2}{R_s}",
                output=Q_(i_rs_b**2 * rs, "W"),
                inputs={"V_{in,max}": Q_(vin_max, "V"), "V_Z": Q_(vz_b, "V"), "R_s": Q_(rs, "ohm")},
                reference=ref,
            )
        )
        # small-signal regulation: Zener branch rz against Rs (and RL); follower divides by β+1
        rz = z.rz
        line = rz / (rs + rz) if rz > 0 else 0.0
        log.add(
            record(
                "line_reg",
                "Regulação de linha (pequenos sinais, carga leve)",
                r"\frac{\Delta V_o}{\Delta V_{in}} \approx \frac{r_z}{R_s + r_z}",
                output=Q_(line * 1000, "mV/V"),
                inputs={"r_z": Q_(rz, "ohm"), "R_s": Q_(rs, "ohm")},
                assumptions=["R_L ≫ r_z; despreza a variação de V_BE"],
                reference=ref,
            )
        )
        rpar = rs * rz / (rs + rz) if rz > 0 else 0.0
        if bjt is None:
            load = rpar
            latex_l = r"\frac{\Delta V_o}{\Delta I_L} \approx -(R_s \parallel r_z)"
            inputs_l = {"r_z": Q_(rz, "ohm"), "R_s": Q_(rs, "ohm")}
        else:
            ic_a = il_a - ib_a
            re = VT_300K / ic_a if ic_a > 0 else 0.0
            load = re + rpar / (bjt.BF + 1)
            latex_l = (
                r"\frac{\Delta V_o}{\Delta I_L} \approx -\left(r_e + "
                r"\frac{R_s \parallel r_z}{\beta + 1}\right),\; r_e = V_T/I_C"
            )
            inputs_l = {
                "r_z": Q_(rz, "ohm"),
                "R_s": Q_(rs, "ohm"),
                r"\beta": Q_(bjt.BF, ""),
                "I_C": Q_(ic_a, "A"),
            }
        log.add(
            record(
                "load_reg",
                "Regulação de carga (pequenos sinais)",
                latex_l,
                output=Q_(-load * 1000, "mV/A"),
                inputs=inputs_l,
                reference=ref,
            )
        )

        stresses = [
            Stress(
                designator="DZ1",
                key="Ptot",
                label="Potência no Zener",
                value=QuantityModel.from_pint(pz.to("W")),
                calc_step_id="PZ_max",
            ),
            Stress(
                designator="DZ1",
                key="IZM",
                label="Corrente Zener máxima",
                value=QuantityModel(value=iz_b, unit="A"),
                calc_step_id="IZ_b",
            ),
        ]
        losses: dict[str, pint.Quantity] = {"DZ1": pz.to("W")}
        summary: dict[str, pint.Quantity] = {
            "Vin_min": Q_(vin_min, "V"),
            "Vin_max": Q_(vin_max, "V"),
            "VZ_target": Q_(target, "V"),
            "VZ": Q_(vz_rec, "V"),
            "VZ0": Q_(z.VZ0, "V"),
            "rz": Q_(z.rz, "ohm"),
            "IZ_min": Q_(iz_min, "A").to("mA"),
            "Rs": Q_(rs, "ohm"),
            "P_Rs": p_rs.to("W"),
            "RL_min": Q_(rl_min, "ohm"),
            "Vo_a": Q_(vo_a, "V"),
            "Vo_b": Q_(vo_b, "V"),
            "IZ_a": Q_(iz_a, "A").to("mA"),
            "IZ_b": Q_(iz_b, "A").to("mA"),
            "PZ_max": pz.to("W"),
            "line_reg": Q_(line * 1000, "mV/V"),
            "load_reg": Q_(-load * 1000, "mV/A"),
        }
        if math.isfinite(rl_max) and rl_max < OPEN_LOAD:
            summary["RL_max"] = Q_(rl_max, "ohm")
        if bjt is not None:
            # VCE worst case: highest input, heaviest load (largest current with largest drop)
            vo_c, _, il_c, ib_c = corner(vin_max, rl_min, rs)
            vce = vin_max - vo_c
            pq = vce * (il_c - ib_c)
            log.add(
                record(
                    "PQ_max",
                    "Potência máxima no transistor (entrada máxima, carga máxima)",
                    r"P_Q = (V_{in,max} - V_o)\,I_C",
                    output=Q_(pq, "W"),
                    inputs={
                        "V_{in,max}": Q_(vin_max, "V"),
                        "V_o": Q_(vo_c, "V"),
                        "I_C": Q_(il_c - ib_c, "A"),
                    },
                    assumptions=["o coletor vai direto à entrada não regulada"],
                    reference=ref,
                )
            )
            vce_max = vin_max - min(vo_a, vo_b, vo_c)
            stresses += [
                Stress(
                    designator="Q1",
                    key="VCEO",
                    label="Tensão coletor-emissor",
                    value=QuantityModel(value=vce_max, unit="V"),
                    calc_step_id="PQ_max",
                ),
                Stress(
                    designator="Q1",
                    key="IC",
                    label="Corrente de coletor",
                    value=QuantityModel(value=il_c - ib_c, unit="A"),
                    calc_step_id="PQ_max",
                ),
            ]
            losses["Q1"] = Q_(pq, "W")
            summary |= {
                "IB_max": Q_(ib_max, "A").to("mA"),
                "IC_max": Q_(il_c - ib_c, "A"),
                "VCE_max": Q_(vce_max, "V"),
                "PQ_max": Q_(pq, "W"),
                "Vo_c": Q_(vo_c, "V"),
            }
        if abs(vo_a - vo_t) / vo_t > 0.05:
            warnings.append(
                DesignWarning(
                    code="vo_fora",
                    message=f"A saída com o Zener escolhido ({vo_a:.3g} V) difere mais de 5 % "
                    f"da desejada ({vo_t:.3g} V).",
                )
            )
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses=losses,
            warnings=warnings,
            convergence_keys=("Rs", "Vo_a", "Vo_b"),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        """Both corners in one netlist: suffix a (entrada mínima, carga máxima) and b."""
        s = _spec(spec)
        log = CalcLog()
        dz = devices["DZ1"].record
        if dz is not None:
            z, _ = zener_pwl(dz, log, "DZ1")
        else:
            z = ZenerPwl(VZ=q(summary, "VZ", "V"), IZT=0, rz=1e-3, IZK=None)
        rs = q(summary, "Rs", "ohm")
        lines = [z.spice_subckt()]
        bjt = None
        if s.variant == "transistor":
            bjt, _ = bjt_model(
                devices["Q1"].record,
                s.IL_max.to_pint().m_as("A"),
                s.VBE.to_pint(),
                s.beta_ideal,
                log,
                "Q1",
            )
            lines.append(bjt.spice("QSER"))
        rl = {"a": q(summary, "RL_min", "ohm"), "b": summary.get("RL_max")}
        corners = {"a": q(summary, "Vin_min", "V"), "b": q(summary, "Vin_max", "V")}
        for tag, vi in corners.items():
            lines += [f"VIN{tag} in{tag} 0 DC {vi:.9g}", f"RS{tag} in{tag} z{tag} {rs:.9g}"]
            lines.append(f"VSZ{tag} z{tag} zs{tag} 0")
            lines.append(f"XZ{tag} zs{tag} 0 ZPWL")
            out = f"z{tag}"
            if bjt is not None:
                lines.append(f"Q{tag} in{tag} z{tag} o{tag} QSER")
                out = f"o{tag}"
            r = rl[tag]
            r_val = r if isinstance(r, float) else (r.to_pint().m_as("ohm") if r else None)
            if r_val is not None:
                lines.append(f"RL{tag} {out} 0 {r_val:.9g}")
            elif bjt is not None:
                lines.append(f"RLK{tag} {out} 0 {OPEN_LOAD:g}")
        o = "o" if bjt is not None else "z"
        checks = [
            dc_check("Saída, entrada mínima e carga máxima", "Vo_a", f"v({o}a)"),
            dc_check("Saída, entrada máxima e carga mínima", "Vo_b", f"v({o}b)"),
            dc_check("IZ, entrada mínima e carga máxima", "IZ_a", "i(vsza)", 1.0),
            dc_check("IZ, entrada máxima e carga mínima", "IZ_b", "i(vszb)", 1.0),
        ]
        return dc_circuit(
            f"{self.id}: {ENUM_LABELS[s.variant]} (cantos de pior caso)", "\n".join(lines), checks
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        parts = {c.designator: c.part_number for c in result.selection}
        sm = result.summary
        svg = Svg(560, 300)
        svg.title(title)
        y_top, y_bot = 80, 240
        svg.dc_source(60, y_top, y_bot, "Vin", f"{s.Vin.value:g} V ± {s.vin_tol_pct:g} %")
        rs = format_eng(sm["Rs"].to_pint()) if "Rs" in sm else ""
        svg.resistor_h(60, 200, y_top, "Rs", rs)
        if s.variant == "simples":
            svg.wire((200, y_top), (420, y_top))
            svg.dot(260, y_top)
            svg.zener_v(260, y_top, y_bot, "DZ1", parts.get("DZ1", ""))
            svg.resistor_v(420, y_top, y_bot, "RL", f"≥ {format_eng(sm['RL_min'].to_pint())}")
            svg.terminal(470, y_top, "Vo")
            svg.wire((420, y_top), (470, y_top))
        else:
            svg.wire((40, 50), (60, 50))
            svg.wire((60, y_top), (60, 50), (330, 50))
            svg.dot(60, y_top)
            svg.wire((200, y_top), (240, y_top))
            svg.dot(240, y_top)
            svg.zener_v(240, y_top + 20, y_bot, "DZ1", parts.get("DZ1", ""), left=True)
            svg.line(240, y_top, 240, y_top + 20)
            b, c, e = svg.bjt(330, 110, "Q1", parts.get("Q1", ""))
            svg.wire((240, y_top), (240, 110), b)
            svg.wire(c, (c[0], 50), (330, 50))
            svg.wire(e, (e[0], 160), (440, 160))
            svg.resistor_v(440, 160, y_bot, "RL", f"≥ {format_eng(sm['RL_min'].to_pint())}")
            svg.terminal(490, 160, "Vo")
            svg.wire((440, 160), (490, 160))
            svg.wire((440, y_bot), (440, y_bot))
        svg.wire((60, y_bot), (440 if s.variant == "transistor" else 420, y_bot))
        svg.ground(60, y_bot)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        rows = [r for r in (resistor_row(result, "Rs", "Rs", "P_Rs"),) if r]
        rows.append(
            passive(
                "Cin",
                "Capacitor de desacoplamento da entrada (recomendado)",
                "100 nF",
                "cerâmico, junto ao regulador",
            )
        )
        return rows
