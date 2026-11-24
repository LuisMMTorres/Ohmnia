"""DM-CMD: gate drive (bootstrap half-bridge driver), turn-off snubber and input protection.

- Gate resistor and drive power: the resistor keeps the peak gate current within the driver
  capability I_O+; the gate charge Q_g is delivered at every turn-on, P = Q_g·V_CC·f_s
  (Mohan, Undeland & Robbins, 3rd ed., ch. 23, gate and base drive circuits).
- Bootstrap capacitor (Infineon/IR application note AN-978, HV floating MOS-gate driver ICs):
  C ≥ 2[2Q_g + I_QBS/f + Q_ls + I_Cbs(leak)/f] / (V_CC − V_F − V_LS − V_Min).
- RCD turn-off snubber (Hart, *Power Electronics*, 1st ed., ch. 10, snubber circuits): with a
  linear current fall in t_f, C = I_o·t_f/(2V_s) brings the switch voltage to V_s at the end of
  the fall; the turn-off energy becomes I_o²t_f²/(24C); the resistor discharges C during the
  shortest on-time (≈ 5RC) and dissipates ½CV_s²f_s.
- Input protection: the fuse clearing I²t must stay below the I²t of the rectifier bridge; the
  varistor's maximum continuous AC voltage must exceed the highest line voltage; the cold
  resistance of the NTC limits the inrush peak (Mohan ch. 29, practical converter design
  considerations).

The snubber turn-off and the inrush peak are simulated in ngspice (current-source switch with
linear fall; bridge closed at the crest of the line voltage).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import pint
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.eseries import snap
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.base import Circuit, DesignResult, DesignWarning, Role, SimCheck, Stress
from circuitos.design.engine import Analysis, Device
from circuitos.design.power import HART, MOHAN, pval, ref, spice_diode, switch_data
from circuitos.reports import drawings_power
from circuitos.reports.canvas import pretty
from circuitos.reports.common import BomRow, LabItem, passive

AN978 = BibRef(
    book="Infineon (International Rectifier), AN-978: HV floating MOS-gate driver ICs",
    edition="rev. D",
    chapter="bootstrap capacitor",
)
HART10 = ref(HART, "10 (drive circuits, snubber circuits and heat sinks)")
MOHAN23 = ref(MOHAN, "23 (gate and base drive circuits)")
MOHAN29 = ref(MOHAN, "29 (practical converter design considerations)")


def _q(v: float, unit: str) -> QuantityModel:
    return QuantityModel(value=v, unit=unit)


class CmdSpec(BaseModel):
    switch: Literal["igbt", "mosfet"] = "igbt"
    Vbus: QuantityModel = _q(311, "V")
    Io: QuantityModel = _q(10, "A")
    fs: QuantityModel = _q(20, "kHz")
    D_min: float = Field(default=0.05, gt=0, lt=1)
    Vcc: QuantityModel = _q(15, "V")
    Qls: QuantityModel = _q(5, "nC")  # level-shift charge (AN-978; confirm for the chosen IC)
    I_cbs: QuantityModel = _q(0, "uA")  # bootstrap capacitor leakage (0: ceramic/film)
    snubber: bool = True
    Vac: QuantityModel = _q(220, "V")
    line_tol: float = Field(default=0.1, ge=0, le=0.3)
    f_line: QuantityModel = _q(60, "Hz")
    I_dc: QuantityModel = _q(3, "A")  # average DC current from the bridge
    I_in_rms: QuantityModel = _q(5, "A")  # line current (rms) of the capacitor-input rectifier
    C_bus: QuantityModel = _q(470, "uF")
    I_inrush: QuantityModel = _q(40, "A")  # target peak inrush current
    fuse_I2t: QuantityModel = _q(20, "A**2*s")  # clearing I²t of the chosen fuse (user data)
    TA: QuantityModel = _q(40, "degC")


LABELS = {
    "Rg": "Resistor de gate",
    "Ig_pk": "Corrente de pico de gate",
    "t_g": "Tempo de carga do gate (estimativa)",
    "P_gate": "Potência de comando por chave",
    "P_drv": "Dissipação do driver",
    "Q_bs": "Carga do bootstrap por ciclo",
    "C_boot_min": "Capacitor de bootstrap mínimo",
    "C_boot": "Capacitor de bootstrap (E12)",
    "dV_boot": "Queda no bootstrap por ciclo",
    "t_hs_max": "Tempo máximo da chave alta ligada",
    "C_s_min": "Capacitor do snubber mínimo",
    "C_s": "Capacitor do snubber (E12)",
    "R_s_max": "Resistor do snubber máximo",
    "R_s": "Resistor do snubber (E24)",
    "P_Rs": "Potência no resistor do snubber",
    "E_off0": "Energia de desligamento sem snubber",
    "E_off": "Energia de desligamento com snubber",
    "I2t_bridge": "I²t da ponte",
    "fuse_In_min": "Corrente nominal mínima do fusível",
    "MCOV_min": "Tensão CA contínua mínima do varistor",
    "R_ntc_min": "Resistência a frio mínima do NTC",
    "R_ntc": "Resistência a frio do NTC (E12)",
    "I_inrush_pk": "Pico de corrente de partida",
    "E_ntc": "Energia no NTC na partida",
}
SPEC_LABELS = {
    "switch": "Chave",
    "Vbus": "Tensão do barramento",
    "Io": "Corrente comutada",
    "fs": "Frequência de chaveamento",
    "D_min": "Razão cíclica mínima da chave baixa",
    "Vcc": "Tensão de alimentação do driver",
    "Qls": "Carga do deslocador de nível (AN-978; confirmar)",
    "I_cbs": "Fuga do capacitor de bootstrap",
    "snubber": "Snubber RCD de desligamento",
    "Vac": "Tensão da rede (eficaz)",
    "line_tol": "Tolerância da rede",
    "f_line": "Frequência da rede",
    "I_dc": "Corrente média no barramento",
    "I_in_rms": "Corrente eficaz de entrada",
    "C_bus": "Capacitor do barramento",
    "I_inrush": "Pico de partida desejado",
    "fuse_I2t": "I²t de interrupção do fusível (dado do fusível)",
}
ENUM_LABELS = {"igbt": "IGBT", "mosfet": "MOSFET"}


def _spec(spec: BaseModel) -> CmdSpec:
    if not isinstance(spec, CmdSpec):
        raise TypeError("DM-CMD espera CmdSpec")
    return spec


def _v(x: QuantityModel, unit: str) -> float:
    return float(x.to_pint().m_as(unit))


def _snap(v: float, unit: str, series: Literal["E12", "E24"], mode: Literal["up", "down"]) -> float:
    return float(snap(Q_(v, unit), series, mode).m_as(unit))


class CmdModule:
    id = "DM-CMD"
    family = "potencia"
    title = "Comando e proteção de chaves"
    spec_schema = CmdSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão no bootstrap", "osciloscópio (ponteira diferencial)", "dV_boot"),
        LabItem("Sobretensão no desligamento", "osciloscópio (ponteira diferencial)", "C_s"),
        LabItem("Corrente de partida", "ponteira de corrente", "I_inrush_pk"),
    ]
    questions = [
        "Por que a chave alta não pode ficar ligada indefinidamente com bootstrap?",
        "O snubber RCD reduz a perda total ou só a transfere para o resistor?",
        "Por que o I²t do fusível deve ser menor que o da ponte?",
    ]
    safety = [
        "Barramento CC carregado mantém tensão perigosa: descarregue o capacitor antes de "
        "mexer no circuito.",
        "Meça o gate da chave alta só com ponteira diferencial ou osciloscópio isolado.",
    ]

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        roles = [
            Role(
                designator="Q1",
                category="igbt" if s.switch == "igbt" else "mosfet.n",
                description="Chave (meia ponte)",
            ),
            Role(designator="U1", category="gate_driver", description="Driver de meia ponte"),
            Role(designator="D1", category="diode", description="Diodo de bootstrap"),
        ]
        if s.snubber:
            roles.append(Role(designator="D2", category="diode", description="Diodo do snubber"))
        roles.append(
            Role(designator="B1", category="bridge", description="Ponte retificadora de entrada")
        )
        return roles

    def required_ratings(self, role: Role) -> list[str]:
        if role.designator == "U1":
            return ["VOFFSET", "VCC_max"]
        if role.designator in ("D1", "D2"):
            return ["VRRM", "IF(AV)"]
        if role.designator == "B1":
            return ["VRRM", "IF(AV)", "IFSM"]
        return ["VCES", "IC"] if role.category == "igbt" else ["VDS", "ID"]

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        if role.designator in ("D1", "D2"):
            return rec.category.startswith("diode.fast")
        return True

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0.5, "K/W")

    # ---------------------------------------------------------------------- analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        sm: dict[str, pint.Quantity] = {}
        vbus, io, fs = _v(s.Vbus, "V"), _v(s.Io, "A"), _v(s.fs, "Hz")
        vcc = _v(s.Vcc, "V")
        q_rec = devices["Q1"].record if "Q1" in devices else None
        u_rec = devices["U1"].record if "U1" in devices else None
        sw = switch_data(q_rec)
        if sw.kind == "ideal":
            warnings.append(
                DesignWarning(
                    code="sem_chave",
                    message="Sem chave escolhida: Q_g, t_f e V_CE(sat) ficam nulos.",
                )
            )
        qg, tf = sw.qg, sw.tf
        v_ls = sw.v_on if sw.kind == "igbt" else sw.r_on * io

        # gate resistor and drive power
        io_plus = pval(u_rec, "IO+", "A", ("min", "typ")) or 0.0
        rg_min = vcc / io_plus if io_plus > 0 else 10.0
        rg = _snap(rg_min, "ohm", "E24", "up")
        ig = vcc / rg
        t_g = 2 * qg * rg / vcc  # charge at the mean current V_CC/(2R_g)
        p_gate = qg * vcc * fs
        iqcc = pval(u_rec, "IQCC", "A") or 0.0
        p_drv = 2 * p_gate + vcc * iqcc
        log.add(
            record(
                "Rg",
                "Resistor de gate pela corrente do driver",
                r"R_g \ge \frac{V_{CC}}{I_{O+}}",
                output=Q_(rg, "ohm"),
                inputs={"V_CC": s.Vcc.to_pint(), "I_O+": Q_(io_plus, "A")},
                assumptions=[
                    "sem resistência interna de gate no datasheet: R_g externo só",
                    "valor E24 acima",
                ],
                reference=MOHAN23,
            )
        )
        log.add(
            record(
                "t_g",
                "Tempo de carga do gate (estimativa de primeira ordem)",
                r"t_g \approx \frac{Q_g}{V_{CC}/(2R_g)}",
                output=Q_(t_g, "s"),
                inputs={"Q_g": Q_(qg, "C"), "R_g": Q_(rg, "ohm")},
                assumptions=["corrente média de gate igual à metade do pico"],
                reference=MOHAN23,
            )
        )
        log.add(
            record(
                "P_drv",
                "Potência de comando e dissipação do driver",
                r"P_{gate} = Q_g V_{CC} f_s,\; P_{drv} = 2P_{gate} + V_{CC} I_{QCC}",
                output=Q_(p_drv, "W"),
                inputs={"Q_g": Q_(qg, "C"), "f_s": s.fs.to_pint(), "I_QCC": Q_(iqcc, "A")},
                assumptions=[
                    "pior caso: toda a energia de gate dissipada no driver "
                    "(R_g externo a absorve em parte)"
                ],
                reference=MOHAN23,
            )
        )
        sm |= {
            "Rg": Q_(rg, "ohm"),
            "Ig_pk": Q_(ig, "A"),
            "t_g": Q_(t_g, "s"),
            "P_gate": Q_(p_gate, "W"),
            "P_drv": Q_(p_drv, "W"),
        }

        # bootstrap (AN-978)
        iqbs = pval(u_rec, "IQBS", "A") or 0.0
        vbsuv = pval(u_rec, "VBSUV-", "V") or 0.0
        vf_b = devices["D1"].drop.m_as("V") if "D1" in devices else 0.0
        qls = _v(s.Qls, "C")
        icbs = _v(s.I_cbs, "A")
        q_bs = 2 * qg + iqbs / fs + qls + icbs / fs
        headroom = vcc - vf_b - v_ls - vbsuv
        if headroom <= 0:
            raise ValueError(
                "V_CC − V_F − V_LS não supera o subtensão V_BSUV do driver: aumente V_CC"
            )
        c_min = 2 * q_bs / headroom
        c_boot = _snap(c_min * 10, "F", "E12", "up")  # AN-978 suggests ≫ the minimum
        dv = q_bs / c_boot
        t_hs = c_boot * headroom / (iqbs + icbs) if iqbs + icbs > 0 else math.inf
        log.add(
            record(
                "C_boot_min",
                "Capacitor de bootstrap mínimo",
                r"C \ge \frac{2\left[2Q_g + \frac{I_{QBS}}{f} + Q_{ls} + \frac{I_{Cbs}}{f}\right]}"
                r"{V_{CC} - V_F - V_{LS} - V_{Min}}",
                output=Q_(c_min, "F"),
                inputs={
                    "Q_g": Q_(qg, "C"),
                    "I_QBS": Q_(iqbs, "A"),
                    "Q_ls": s.Qls.to_pint(),
                    "V_F": Q_(vf_b, "V"),
                    "V_LS": Q_(v_ls, "V"),
                    "V_Min": Q_(vbsuv, "V"),
                },
                assumptions=[
                    "V_Min = limiar de subtensão V_BSUV− do driver",
                    "Q_ls informado pelo usuário (AN-978 cita 5 nC para CIs de 500/600 V)",
                    "valor adotado ≈ 10× o mínimo, E12 acima",
                ],
                reference=AN978,
            )
        )
        log.add(
            record(
                "t_hs_max",
                "Tempo máximo da chave alta ligada sem recarga",
                r"t_{max} = \frac{C (V_{CC} - V_F - V_{LS} - V_{Min})}{I_{QBS} + I_{Cbs}}",
                output=Q_(t_hs if math.isfinite(t_hs) else 1e9, "s"),
                inputs={"C": Q_(c_boot, "F")},
                reference=AN978,
            )
        )
        sm |= {
            "Q_bs": Q_(q_bs, "C"),
            "C_boot_min": Q_(c_min, "F"),
            "C_boot": Q_(c_boot, "F"),
            "dV_boot": Q_(dv, "V"),
            "t_hs_max": Q_(t_hs if math.isfinite(t_hs) else 1e9, "s"),
        }
        t_on_min = s.D_min / fs
        i_d1 = q_bs * fs
        stresses = [
            Stress(
                designator="Q1",
                key="VCES" if s.switch == "igbt" else "VDS",
                label="Tensão do barramento",
                value=_q(vbus, "V"),
                calc_step_id="P_drv",
            ),
            Stress(
                designator="Q1",
                key="IC" if s.switch == "igbt" else "ID",
                label="Corrente comutada",
                value=_q(io, "A"),
                calc_step_id="P_drv",
            ),
            Stress(
                designator="U1",
                key="VOFFSET",
                label="Tensão de deslocamento",
                value=_q(vbus, "V"),
                calc_step_id="C_boot_min",
            ),
            Stress(
                designator="U1",
                key="VCC_max",
                label="Alimentação do driver",
                value=_q(vcc, "V"),
                calc_step_id="P_drv",
            ),
            Stress(
                designator="U1",
                key="Ptot",
                label="Dissipação do driver",
                value=_q(p_drv, "W"),
                calc_step_id="P_drv",
            ),
            Stress(
                designator="D1",
                key="VRRM",
                label="Tensão reversa (barramento + V_CC)",
                value=_q(vbus + vcc, "V"),
                calc_step_id="C_boot_min",
            ),
            Stress(
                designator="D1",
                key="IF(AV)",
                label="Corrente média de recarga",
                value=_q(i_d1, "A"),
                calc_step_id="C_boot_min",
            ),
        ]

        # RCD turn-off snubber (Hart ch. 10)
        if s.snubber:
            vf_s = devices["D2"].drop.m_as("V") if "D2" in devices else 0.0
            cs_min = io * tf / (2 * vbus) if tf > 0 else 0.0
            cs = _snap(cs_min, "F", "E12", "up") if cs_min > 0 else 0.0
            rs_max = t_on_min / (5 * cs) if cs > 0 else math.inf
            rs = _snap(rs_max, "ohm", "E24", "down") if math.isfinite(rs_max) else 0.0
            p_rs = 0.5 * cs * vbus**2 * fs
            e0 = 0.5 * vbus * io * tf
            e_s = io**2 * tf**2 / (24 * cs) + vf_s * io * tf / 2 if cs > 0 else e0
            log.add(
                record(
                    "C_s_min",
                    "Capacitor do snubber: tensão chega a V_s no fim da queda da corrente",
                    r"C_s = \frac{I_o t_f}{2 V_s}",
                    output=Q_(cs_min, "F"),
                    inputs={"I_o": s.Io.to_pint(), "t_f": Q_(tf, "s"), "V_s": s.Vbus.to_pint()},
                    assumptions=[
                        "queda linear da corrente em t_f (t_f do datasheet)",
                        "valor E12 acima",
                    ],
                    reference=HART10,
                )
            )
            log.add(
                record(
                    "R_s_max",
                    "Resistor do snubber: descarga em 5RC no menor tempo ligado",
                    r"R_s \le \frac{D_{min} T_s}{5 C_s}",
                    output=Q_(rs_max if math.isfinite(rs_max) else 0.0, "ohm"),
                    inputs={"D_min": Q_(s.D_min, ""), "C_s": Q_(cs, "F")},
                    assumptions=["valor E24 abaixo"],
                    reference=HART10,
                )
            )
            log.add(
                record(
                    "E_off",
                    "Energia de desligamento com e sem snubber",
                    r"E_0 = \tfrac{1}{2} V_s I_o t_f,\;"
                    r" E = \frac{I_o^2 t_f^2}{24 C_s} + V_F \frac{I_o t_f}{2}",
                    output=Q_(e_s, "J"),
                    inputs={"E_0": Q_(e0, "J"), "V_F": Q_(vf_s, "V"), "C_s": Q_(cs, "F")},
                    assumptions=[
                        "sem snubber: tensão sobe antes da queda da corrente "
                        "(carga indutiva grampeada)"
                    ],
                    reference=HART10,
                )
            )
            log.add(
                record(
                    "P_Rs",
                    "Potência no resistor do snubber",
                    r"P_R = \tfrac{1}{2} C_s V_s^2 f_s",
                    output=Q_(p_rs, "W"),
                    inputs={"C_s": Q_(cs, "F"), "f_s": s.fs.to_pint()},
                    reference=HART10,
                )
            )
            sm |= {
                "C_s_min": Q_(cs_min, "F"),
                "C_s": Q_(cs, "F"),
                "R_s_max": Q_(rs_max if math.isfinite(rs_max) else 0.0, "ohm"),
                "R_s": Q_(rs, "ohm"),
                "P_Rs": Q_(p_rs, "W"),
                "E_off0": Q_(e0, "J"),
                "E_off": Q_(e_s, "J"),
            }
            stresses += [
                Stress(
                    designator="D2",
                    key="VRRM",
                    label="Tensão reversa",
                    value=_q(vbus, "V"),
                    calc_step_id="C_s_min",
                ),
                Stress(
                    designator="D2",
                    key="IF(AV)",
                    label="Corrente média de carga do snubber",
                    value=_q(cs * vbus * fs, "A"),
                    calc_step_id="P_Rs",
                ),
            ]

        # input protection
        vac = _v(s.Vac, "V")
        vpk_max = vac * (1 + s.line_tol) * math.sqrt(2)
        f_line = _v(s.f_line, "Hz")
        b_rec = devices["B1"].record if "B1" in devices else None
        vf_br = devices["B1"].drop.m_as("V") if "B1" in devices else 0.0
        ifsm = pval(b_rec, "IFSM", "A")
        i2t_b = pval(b_rec, "I2t", "A**2*s")
        if i2t_b is None and ifsm is not None:
            i2t_b = ifsm**2 * (1 / (2 * f_line)) / 2  # half sine of one half cycle
        fuse = _v(s.fuse_I2t, "A**2*s")
        if i2t_b is not None:
            log.add(
                record(
                    "I2t_bridge",
                    "I²t da ponte (datasheet, ou meia senoide de I_FSM em meio ciclo)",
                    r"I^2t = \frac{I_{FSM}^2}{2}\cdot\frac{1}{2f}",
                    output=Q_(i2t_b, "A**2*s"),
                    inputs={"I_FSM": Q_(ifsm or 0.0, "A"), "fusível": s.fuse_I2t.to_pint()},
                    assumptions=["valor de I²t do datasheet quando existe"],
                    reference=MOHAN29,
                )
            )
            sm["I2t_bridge"] = Q_(i2t_b, "A**2*s")
            if fuse >= i2t_b:
                warnings.append(
                    DesignWarning(
                        code="fusivel_i2t",
                        message=f"I²t do fusível ({fuse:g} A²s) não é menor que o da ponte "
                        f"({i2t_b:.3g} A²s): a ponte pode falhar antes do fusível.",
                    )
                )
        i_in = _v(s.I_in_rms, "A")
        fuse_in = i_in / 0.75
        mcov = vac * (1 + s.line_tol)
        log.add(
            record(
                "fuse_In_min",
                "Fusível e varistor",
                r"I_n \ge \frac{I_{rms}}{0{,}75},\; V_{MCOV} \ge V_{ca}(1 + tol)",
                output=Q_(fuse_in, "A"),
                inputs={
                    "I_rms": s.I_in_rms.to_pint(),
                    "V_ca": s.Vac.to_pint(),
                    "tol": Q_(s.line_tol, ""),
                },
                assumptions=[
                    "fusível operando a no máximo 75 % da corrente nominal (prática usual)"
                ],
                reference=MOHAN29,
            )
        )
        r_min = (vpk_max - 2 * vf_br) / _v(s.I_inrush, "A")
        r_ntc = _snap(r_min, "ohm", "E12", "up")
        vpk = vac * math.sqrt(2)
        i_pk = (vpk - 2 * vf_br) / r_ntc
        i_pk_max = (vpk_max - 2 * vf_br) / r_ntc
        cbus = _v(s.C_bus, "F")
        e_ntc = 0.5 * cbus * vpk_max**2
        log.add(
            record(
                "R_ntc_min",
                "NTC: resistência a frio pelo pico de partida (liga na crista)",
                r"R_{frio} \ge \frac{\sqrt{2} V_{ca,max} - 2V_F}{I_{pico}},\;"
                r" E \approx \tfrac{1}{2} C V_{pk}^2",
                output=Q_(r_min, "ohm"),
                inputs={
                    "V_pk,max": Q_(vpk_max, "V"),
                    "I_pico": s.I_inrush.to_pint(),
                    "C": s.C_bus.to_pint(),
                },
                assumptions=[
                    "capacitor descarregado",
                    "pior caso: liga na crista da tensão",
                    "valor E12 acima",
                ],
                reference=MOHAN29,
            )
        )
        sm |= {
            "fuse_In_min": Q_(fuse_in, "A"),
            "MCOV_min": Q_(mcov, "V"),
            "R_ntc_min": Q_(r_min, "ohm"),
            "R_ntc": Q_(r_ntc, "ohm"),
            "I_inrush_pk": Q_(i_pk, "A"),
            "E_ntc": Q_(e_ntc, "J"),
        }
        stresses += [
            Stress(
                designator="B1",
                key="VRRM",
                label="Tensão reversa de pico",
                value=_q(vpk_max, "V"),
                calc_step_id="R_ntc_min",
            ),
            Stress(
                designator="B1",
                key="IF(AV)",
                label="Corrente média",
                value=s.I_dc,
                calc_step_id="fuse_In_min",
            ),
            Stress(
                designator="B1",
                key="IFSM",
                label="Pico de partida",
                value=_q(i_pk_max, "A"),
                calc_step_id="R_ntc_min",
            ),
        ]
        return Analysis(log=log, stresses=stresses, summary=sm, losses={}, warnings=warnings)

    # -------------------------------------------------------------------- simulation
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        vbus, io = _v(s.Vbus, "V"), _v(s.Io, "A")
        sw = switch_data(devices["Q1"].record if "Q1" in devices else None)
        tf = sw.tf if sw.tf > 0 else 100e-9
        vf_br = devices["B1"].drop.m_as("V") if "B1" in devices else 0.0
        vpk = _v(s.Vac, "V") * math.sqrt(2)
        f_line = _v(s.f_line, "Hz")
        t1 = 1e-6  # the line closes on the bridge
        t0 = 2e-6  # the switch starts turning off
        lines = [
            spice_diode("DBR", vf_br),
            ".model SWI SW(VT=2.5 VH=0.1 RON=1m ROFF=1e9)",
            f"VAC l 0 SIN(0 {vpk:.9g} {f_line:.9g} 0 0 90)",
            "SL l la gl 0 SWI",
            f"VGL gl 0 PWL(0 0 {t1:.9g} 0 {t1 + 1e-9:.9g} 5)",
            "XB1 la p DBR",
            "XB2 0 p DBR",
            "XB3 n la DBR",
            "XB4 n 0 DBR",
            f"RNTC p q {summary['R_ntc'].to_pint().m_as('ohm'):.9g}",
            "VIN q c 0",
            f"CBUS c n {_v(s.C_bus, 'F'):.9g}",
            "RBL c n 10meg",
            "RREF n 0 1meg",
        ]
        checks = [
            SimCheck(
                quantity="Pico de corrente de partida",
                summary_key="I_inrush_pk",
                metric="max",
                probe="i(vin)",
                tolerance_pct=1.0,
                justification="liga na crista com o capacitor descarregado",
            )
        ]
        probes = {"i_partida": "i(vin)"}
        if s.snubber and "C_s" in summary and summary["C_s"].value > 0:
            vf_s = devices["D2"].drop.m_as("V") if "D2" in devices else 0.0
            cs = summary["C_s"].to_pint().m_as("F")
            rs = summary["R_s"].to_pint().m_as("ohm")
            isw = f"(time < {t0:.9g} ? 0 : max(0, {io:.9g} * (1 - (time - {t0:.9g}) / {tf:.9g})))"
            lines += [
                spice_diode("DSN", vf_s),
                f"VB vb 0 DC {vbus:.9g}",
                f"IO vb sw DC {io:.9g}",
                "SQ sw 0 gq 0 SWI",
                f"VGQ gq 0 PWL(0 5 {t0:.9g} 5 {t0 + 1e-12:.9g} 0)",
                f"BIS is 0 V = {isw}",
                "RIS is 0 1",
                "BSW sw 0 I = v(is)",
                "XDC sw vb DSN",
                "XDS sw cs DSN",
                f"RS sw cs {rs:.9g}",
                f"CS cs 0 {cs:.9g}",
                "BE 0 e I = v(sw) * v(is)",
                "CE e 0 1",
                "RE e 0 1e15",
            ]
            checks.append(
                SimCheck(
                    quantity="Energia de desligamento com snubber",
                    summary_key="E_off",
                    metric="max",
                    probe="v(e)",
                    tolerance_pct=2.0,
                    justification="queda linear da corrente; corrente no R_s desprezada",
                )
            )
            probes["v_chave"] = "v(sw)"
            stop = t0 + 4 * tf
            step = tf / 400
        else:
            stop = t0 + 1e-6
            step = 1e-9
        return Circuit(
            title=f"{self.id}: snubber e partida",
            netlist="\n".join(lines),
            tran_stop=_q(stop, "s"),
            tran_step=_q(step, "s"),
            period=_q(stop, "s"),
            probes=probes,
            checks=checks,
        )

    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        txt = {
            k: pretty(sm[src])
            for k, src in (
                ("Rg", "Rg"),
                ("C_boot", "C_boot"),
                ("CS", "C_s"),
                ("RS", "R_s"),
                ("RNTC", "R_ntc"),
            )
            if src in sm
        }
        txt.update(
            VAC=f"{pretty(s.Vac)} eficaz",
            CBUS=pretty(s.C_bus),
            Vcc=pretty(s.Vcc),
            VB=pretty(s.Vbus),
            IO=pretty(s.Io),
            RBL="10 MΩ",
        )
        if "fuse_In_min" in sm:
            txt["F1"] = f"In ≥ {pretty(sm['fuse_In_min'])}"
        if "MCOV_min" in sm:
            txt["MOV"] = f"MCOV ≥ {pretty(sm['MCOV_min'])}"
        parts = {c.designator: c.part_number for c in result.selection}
        return drawings_power.drive(title, s.switch, txt, parts, "Comando e proteção", s.snubber)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        sm = result.summary
        rows = [
            passive("RG1, RG2", "Resistor de gate", format_eng(sm["Rg"].to_pint()), quantity=2),
            passive(
                "CB",
                "Capacitor de bootstrap",
                format_eng(sm["C_boot"].to_pint()),
                "cerâmico X7R, baixa fuga",
            ),
            passive(
                "RT1",
                "NTC de partida (resistência a frio)",
                format_eng(sm["R_ntc"].to_pint()),
                f"energia ≥ {sm['E_ntc'].value:.3g} J",
            ),
            passive("RV1", "Varistor", f"MCOV ≥ {sm['MCOV_min'].value:.0f} V CA"),
            passive(
                "F1",
                "Fusível",
                f"I_n ≥ {sm['fuse_In_min'].value:.3g} A",
                f"I²t ≤ {s.fuse_I2t.value:g} A²s",
            ),
        ]
        if s.snubber and "C_s" in sm:
            rows += [
                passive(
                    "CS",
                    "Capacitor do snubber",
                    format_eng(sm["C_s"].to_pint()),
                    f"filme, ≥ {s.Vbus.value:g} V",
                ),
                passive(
                    "RS",
                    "Resistor do snubber",
                    format_eng(sm["R_s"].to_pint()),
                    f"≥ {sm['P_Rs'].value:.2g} W",
                ),
            ]
        return rows
