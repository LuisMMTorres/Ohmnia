"""Firing circuit of DM-RETC1: synchronised RC ramp, comparator and phototriac couplers.

The circuit (a classic "ramp and pedestal-free comparator" firing scheme, built only from
catalogue parts):

1. **Synchronism.** A small transformer TS1 (V_sync) feeds a diode bridge DS1–DS4 and the divider
   R1/R2: v_z = k(|v_sync| − 2V_F). Comparator U1A (LM393, open collector) compares v_z with the
   threshold V_th (R3/R4): near every zero crossing v_z < V_th and U1A sinks, discharging the
   ramp capacitor C1 through R_d. The reset window is |θ − nπ| < θ_r.
2. **Ramp.** Between windows C1 charges from V_CC through R5 (exponential ramp):
   v_C(θ) = V_CC − (V_CC − V_0)·exp(−(θ − θ_r)/(ωR5C1)).
3. **Angle.** Comparator U1B releases its output when the ramp exceeds the control voltage V_c
   (cursor of RV1): Q1 (BC337) saturates through the pull-up R7 and lights the LEDs of the
   phototriac couplers (MOC3021, one per SCR, in series with R_LED) from α to the next window:
   α = θ_r + ωR5C1·ln[(V_CC − V_0)/(V_CC − V_c)].
4. **Gate.** Each MOC3021 output fires its SCR from the SCR's own anode (anode-gate firing):
   anode → phototriac → DG (blocks reverse gate current) → R_G → gate; R_GK from gate to cathode.
   Only the SCR that is forward biased draws gate current, so the same pulse in every half cycle
   steers itself to the right pair (T1/T2 in the positive half, T3/T4 in the negative). Once the
   SCR latches, its anode voltage collapses to V_T and the phototriac current stops.

Sizing rules: R_LED and R_G as in the basic driver circuit of the MOC3021M data sheet (onsemi
MOC3023M/D, rev. 3, fig. 7: R_LED = (V_CC − V_F − V_sat)/I_FT, R = V_peak/I_TSM); the gate current
must reach I_GT (max) plus the current taken by R_GK at the smallest firing angle; the LM393 output
sink current is kept within the V_OL test condition (I_OL = 4 mA). RC charge laws as in Hart,
*Power Electronics*, 1st ed., ch. 10 (drive circuits); gate drive requirements of thyristors as in
Mohan, Undeland & Robbins, 3rd ed., ch. 23.

The same equations drive the ngspice model of :func:`netlist` (ideal comparators with the
datasheet V_OL as an on resistance, constant-drop LEDs, diodes and junctions), so the simulated
firing angle, ramp peak and LED current agree with the calculation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import pint

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.eseries import snap
from circuitos.core.units import Q_, QuantityModel, format_eng, parse_unit
from circuitos.design.base import DesignWarning, Role, SimCheck, Stress

MOC_REF = BibRef(
    book="onsemi, MOC3010M…MOC3023M data sheet (MOC3023M/D)",
    edition="rev. 3, June 2023",
    chapter="fig. 7 (basic driver circuit) and characteristics, p. 3–4",
)
LM393_REF = BibRef(
    book="Texas Instruments, LMx93/LM2903 data sheet",
    edition="conforme o registro do catálogo",
    chapter="electrical characteristics (V_OL at I_OL = 4 mA)",
)
HART_DRIVE = BibRef(
    book="Hart, Power Electronics",
    edition="1st",
    chapter="10 (drive circuits, snubber circuits and heat sinks)",
)
MOHAN_GATE = BibRef(
    book="Mohan, Undeland & Robbins, Power Electronics",
    edition="3rd",
    chapter="23 (gate and base drive circuits)",
)

N_SCR = {"meia_onda": 1, "ponte": 4, "semicontrolada": 2}
# SCR → (anode node, cathode node) in the netlist of build_circuit
SCR_NODES = {
    "meia_onda": {"T1": ("a1", "p")},
    "ponte": {"T1": ("a1", "p"), "T2": ("0", "b"), "T3": ("b", "p"), "T4": ("0", "a1")},
    "semicontrolada": {"T1": ("a1", "p"), "T2": ("b", "p")},
}
DUAL_OPEN_COLLECTOR = ("LM393", "LM2903", "LM293")

# fixed choices of the circuit (premises shown in the calculation memory)
R2_SYNC = 10e3  # lower resistor of the synchronism divider
R3_TH = 100e3  # upper resistor of the threshold divider
V_TH_TARGET = 0.2  # zero-crossing threshold (V)
VZ_PEAK_FRACTION = 0.4  # peak of v_z as a fraction of V_CC
RAMP_PEAK_FRACTION = 0.75  # ramp peak as a fraction of V_CC (inside the input range)
RGK = 1e3  # gate-cathode resistor
RV1 = 10e3  # control potentiometer
IF_MARGIN = 1.2  # worst-case LED current ≥ 1,2·I_FT(max)
BASE_OVERDRIVE = 5.0  # I_B ≥ 5·I_C/h_FE(min): deep saturation
DISCHARGE_TAUS = 5.0  # C1 discharged within the window: 5·τ_d ≤ window


def _range(n: int, first: int, prefix: str) -> str:
    return f"{prefix}{first}" if n == 1 else f"{prefix}{first}–{prefix}{first + n - 1}"


def designators(topology: str) -> dict[str, str]:
    n = N_SCR[topology]
    return {
        "U1": "U1",
        "Q1": "Q1",
        "MOC": _range(n, 2, "U"),
        "DS": "DS1–DS4",
        "DG": _range(n, 1, "DG"),
    }


def roles(topology: str) -> list[Role]:
    n = N_SCR[topology]
    d = designators(topology)
    return [
        Role(
            designator=d["U1"],
            category="comparator",
            description="Comparador duplo de coletor aberto (detector de zero e comparador)",
        ),
        Role(
            designator=d["Q1"], category="bjt.npn", description="Transistor de acionamento dos LEDs"
        ),
        Role(
            designator=d["MOC"],
            category="optocoupler",
            description="Optoacoplador com saída TRIAC de fase aleatória (disparo isolado)",
            count=n,
        ),
        Role(
            designator=d["DS"],
            category="diode",
            description="Ponte retificadora do sincronismo",
            count=4,
        ),
        Role(
            designator=d["DG"],
            category="diode",
            description="Diodo em série com a porta (bloqueia corrente reversa)",
            count=n,
        ),
    ]


def is_firing_role(role: Role) -> bool:
    return role.designator.startswith(("U", "Q", "DS", "DG"))


def required_ratings(role: Role) -> list[str]:
    if role.category == "comparator":
        return ["VS_max"]
    if role.category.startswith("bjt"):
        return ["VCEO", "IC"]
    if role.category == "optocoupler":
        return ["VCEO", "ITSM"]
    return ["VRRM"]


def accepts(role: Role, rec: ComponentRecord) -> bool:
    if role.category == "optocoupler":
        out = rec.attributes.get("saida")
        return out is not None and "fase aleatória" in out.value
    if role.category == "comparator":
        ch = rec.attributes.get("canais")
        dual = ch is not None and ch.value.strip() == "2"
        return dual or rec.part_number.upper().startswith(DUAL_OPEN_COLLECTOR)
    return True


# ----------------------------------------------------------------------------- parameters
def _param(rec: ComponentRecord | None, key: str, unit: str, which: str = "max") -> float | None:
    if rec is None:
        return None
    p = rec.parameters.get(key)
    if p is None or not p.has_value:
        return None
    order = {"max": (p.max, p.typ, p.min), "typ": (p.typ, p.max, p.min), "min": (p.min, p.typ)}
    for v in order[which]:
        if v is not None:
            return float(Q_(v, parse_unit(p.unit)).m_as(unit))
    return None


def _cond(rec: ComponentRecord | None, key: str, cond: str, unit: str) -> float | None:
    if rec is None or key not in rec.parameters:
        return None
    c = rec.parameters[key].conditions.get(cond)
    return None if c is None else float(c.to_pint().m_as(unit))


@dataclass
class FiringParts:
    scr: ComponentRecord | None
    comparator: ComponentRecord | None
    bjt: ComponentRecord | None
    moc: ComponentRecord | None
    d_sync: ComponentRecord | None
    d_gate: ComponentRecord | None


def _e(value: float, unit: str, series: str = "E12", mode: str = "nearest") -> float:
    return float(snap(Q_(value, unit), series, mode).m_as(unit))  # type: ignore[arg-type]


def _largest_e6_below(value: float) -> float:
    """Largest E6 capacitance (F) not above ``value``."""
    return _e(value, "F", "E6", "down")


# ----------------------------------------------------------------------------- design
def size(
    *,
    topology: str,
    Vm: float,
    tol: float,
    f: float,
    alpha_deg: float,
    alpha_min_deg: float | None,
    alpha_max_deg: float | None,
    E: float,
    Vcc: float,
    Vsync: float,
    parts: FiringParts,
    designator_scr: str,
    log: CalcLog,
    warnings: list[DesignWarning],
) -> tuple[dict[str, pint.Quantity], list[Stress]]:
    """Size the firing circuit; empty results (and a warning) when a part or value is missing."""
    d = designators(topology)
    n = N_SCR[topology]
    Vm_max, Vm_min = Vm * (1 + tol), Vm * (1 - tol)
    Vsy_pk = math.sqrt(2) * Vsync
    log.add(
        record(
            "fd_Vm_max",
            "Tensão de pico do secundário com a rede no máximo (bloqueio no circuito de porta)",
            r"V_{m,max} = V_m(1 + \delta)",
            output=Q_(Vm_max, "V"),
            inputs={"V_m": Q_(Vm, "V"), r"\delta": Q_(tol * 100, "percent")},
            reference=MOHAN_GATE,
        )
    )

    def basic(ig_pk: float, ic: float, step_ig: str, step_ic: str) -> list[Stress]:
        def st(des: str, key: str, label: str, v: float, unit: str, step: str) -> Stress:
            return Stress(
                designator=des,
                key=key,
                label=label,
                value=QuantityModel(value=v, unit=unit),
                calc_step_id=step,
            )

        return [
            st(d["U1"], "VS_max", "Tensão de alimentação", Vcc, "V", "fd_Vm_max"),
            st(d["Q1"], "VCEO", "Tensão coletor-emissor", Vcc, "V", "fd_Vm_max"),
            st(d["Q1"], "IC", "Corrente de coletor", ic, "A", step_ic),
            st(d["MOC"], "VCEO", "Tensão de bloqueio da saída (VDRM)", Vm_max, "V", "fd_Vm_max"),
            st(d["MOC"], "ITSM", "Corrente de pico da saída", ig_pk, "A", step_ig),
            st(d["DS"], "VRRM", "Tensão reversa", Vsy_pk * (1 + tol), "V", "fd_Vm_max"),
            st(d["DG"], "VRRM", "Tensão reversa", Vm_max, "V", "fd_Vm_max"),
        ]

    need = {
        "IGT do tiristor": _param(parts.scr, "IGT", "A"),
        "VGT do tiristor": _param(parts.scr, "VGT", "V"),
        "IFT do optoacoplador": _param(parts.moc, "IFT", "A"),
        "IF máx. do optoacoplador": _param(parts.moc, "IF", "A"),
        "VF do LED do optoacoplador": _param(parts.moc, "VF", "V"),
        "ITSM do optoacoplador": _param(parts.moc, "ITSM", "A"),
        "VTM do optoacoplador": _param(parts.moc, "VTM", "V"),
        "hFE mín. do transistor": _param(parts.bjt, "hFE", "", "min"),
        "VCE(sat) do transistor": _param(parts.bjt, "VCE(sat)", "V"),
        "VBE(on) do transistor": _param(parts.bjt, "VBE(on)", "V"),
        "VOL do comparador": _param(parts.comparator, "VOL", "V"),
        "IOL do ensaio de VOL": _cond(parts.comparator, "VOL", "IOL", "A"),
        "VF do diodo do sincronismo": _param(parts.d_sync, "VF", "V"),
        "VF do diodo de porta": _param(parts.d_gate, "VF", "V"),
    }
    missing = [k for k, v in need.items() if v is None]
    if missing:
        warnings.append(
            DesignWarning(
                code="disparo_sem_dados",
                message="Circuito de disparo não dimensionado: faltam "
                + ", ".join(missing)
                + ". Libere (ou trave) as peças do circuito de disparo na tela Componentes; a "
                "simulação segue com pulsos ideais na porta.",
            )
        )
        return {}, basic(0.0, 0.0, "fd_Vm_max", "fd_Vm_max")
    IGT, VGT = need["IGT do tiristor"], need["VGT do tiristor"]
    IFT, IF_max = need["IFT do optoacoplador"], need["IF máx. do optoacoplador"]
    VF_led_max = need["VF do LED do optoacoplador"]
    VF_led = _param(parts.moc, "VF", "V", "typ")
    ITSM, VTM = need["ITSM do optoacoplador"], need["VTM do optoacoplador"]
    hfe, vce_sat, vbe = (
        need["hFE mín. do transistor"],
        need["VCE(sat) do transistor"],
        need["VBE(on) do transistor"],
    )
    VOL, IOL = need["VOL do comparador"], need["IOL do ensaio de VOL"]
    VFs, VFg = need["VF do diodo do sincronismo"], need["VF do diodo de porta"]
    assert None not in (IGT, VGT, IFT, IF_max, VF_led_max, VF_led, ITSM, VTM)
    assert None not in (hfe, vce_sat, vbe, VOL, IOL, VFs, VFg)
    IGT_, VGT_, IFT_, IFmax_ = float(IGT), float(VGT), float(IFT), float(IF_max)  # type: ignore[arg-type]
    VFl_max, VFl = float(VF_led_max), float(VF_led)  # type: ignore[arg-type]
    ITSM_, VTM_ = float(ITSM), float(VTM)  # type: ignore[arg-type]
    hfe_, vsat, vbe_ = float(hfe), float(vce_sat), float(vbe)  # type: ignore[arg-type]
    VOL_, IOL_, VFs_, VFg_ = float(VOL), float(IOL), float(VFs), float(VFg)  # type: ignore[arg-type]

    w = 2 * math.pi * f
    T = 1 / f
    out: dict[str, pint.Quantity] = {}
    ref_moc, ref_cmp = MOC_REF, LM393_REF

    def add(key: str, desc: str, latex: str, value: float, unit: str, inputs, ref, assume=()):  # type: ignore[no-untyped-def]
        q = log.add(
            record(
                key,
                desc,
                latex,
                output=Q_(value, unit),
                inputs=inputs,
                assumptions=list(assume),
                reference=ref,
            )
        )
        out[key] = q
        return value

    # 1. synchronism divider
    if Vsy_pk <= 2 * VFs_ + 0.5:
        warnings.append(
            DesignWarning(
                code="disparo_sincronismo",
                message="Tensão de sincronismo baixa demais para a ponte de diodos: "
                "aumente V_sync.",
            )
        )
        return {}, basic(0.0, 0.0, "fd_Vm_max", "fd_Vm_max")
    R1 = _e(R2_SYNC * ((Vsy_pk - 2 * VFs_) / (VZ_PEAK_FRACTION * Vcc) - 1), "ohm")
    k = R2_SYNC / (R1 + R2_SYNC)
    add(
        "fd_R1",
        "Resistor superior do divisor do sincronismo (E12)",
        r"R_1 = R_2\left(\frac{\sqrt{2}V_{sync} - 2V_F}{0{,}4\,V_{CC}} - 1\right)",
        R1,
        "ohm",
        {"V_{sync}": Q_(Vsync, "V"), "V_F": Q_(VFs_, "V"), "R_2": Q_(R2_SYNC, "ohm")},
        HART_DRIVE,
        [
            "pico de v_z em 40 % de V_CC, dentro da faixa de entrada do comparador",
            "R2 = 10 kΩ (escolha)",
        ],
    )
    # 2. zero-crossing threshold
    R4 = _e(R3_TH * V_TH_TARGET / (Vcc - V_TH_TARGET), "ohm")
    Vth = Vcc * R4 / (R3_TH + R4)
    add(
        "fd_R4",
        "Resistor inferior do divisor do limiar de zero (E12)",
        r"R_4 = R_3\,\frac{V_{th}}{V_{CC} - V_{th}}",
        R4,
        "ohm",
        {"R_3": Q_(R3_TH, "ohm"), "V_{CC}": Q_(Vcc, "V")},
        HART_DRIVE,
        ["limiar desejado 0,2 V; R3 = 100 kΩ (escolha)"],
    )
    add(
        "fd_Vth",
        "Limiar do detector de zero",
        r"V_{th} = V_{CC}\frac{R_4}{R_3+R_4}",
        Vth,
        "V",
        {"R_4": Q_(R4, "ohm")},
        HART_DRIVE,
    )
    s_r = (Vth / k + 2 * VFs_) / Vsy_pk
    theta_r = math.asin(min(s_r, 1.0))
    add(
        "fd_theta_r",
        "Meia largura da janela de reinício da rampa (em torno de cada cruzamento por zero)",
        r"\theta_r = \arcsin\frac{V_{th}/k + 2V_F}{\sqrt{2}V_{sync}},\quad k = \frac{R_2}{R_1+R_2}",
        math.degrees(theta_r),
        "deg",
        {"V_{th}": Q_(Vth, "V"), "k": Q_(k, ""), "V_F": Q_(VFs_, "V")},
        HART_DRIVE,
        [
            "diodos da ponte como queda constante V_F (máx. do datasheet)",
            "trafo de sincronismo em fase com o secundário de potência",
        ],
    )
    t_w = 2 * theta_r / w
    # 3. discharge resistor and ramp capacitor
    Rd = _e(Vcc / IOL_, "ohm", "E12", "up")
    Ron = VOL_ / IOL_
    add(
        "fd_Rd",
        "Resistor de descarga de C1 (limita a corrente drenada pelo LM393, E12)",
        r"R_d \geq \frac{V_{CC}}{I_{OL}},\quad R_{on} = \frac{V_{OL}}{I_{OL}}",
        Rd,
        "ohm",
        {"V_{CC}": Q_(Vcc, "V"), "I_{OL}": Q_(IOL_, "A"), "V_{OL}": Q_(VOL_, "V")},
        ref_cmp,
        ["saída do comparador modelada como resistência V_OL/I_OL (ponto de ensaio do datasheet)"],
    )
    C1 = _largest_e6_below(t_w / (DISCHARGE_TAUS * (Rd + Ron)))
    add(
        "fd_C1",
        "Capacitor da rampa (maior valor E6 que descarrega dentro da janela)",
        r"5\,(R_d + R_{on})\,C_1 \leq \frac{2\theta_r}{\omega}",
        C1,
        "F",
        {r"\theta_r": Q_(math.degrees(theta_r), "deg"), "R_d": Q_(Rd, "ohm")},
        HART_DRIVE,
        ["capacitor de filme (sem polaridade)"],
    )
    t_ramp = T / 2 - t_w
    R5 = _e(t_ramp / (C1 * math.log(1 / (1 - RAMP_PEAK_FRACTION))), "ohm", "E24")
    add(
        "fd_R5",
        "Resistor de carga da rampa (E24)",
        r"R_5 = \frac{T/2 - 2\theta_r/\omega}{C_1 \ln\frac{1}{1 - 0{,}75}}",
        R5,
        "ohm",
        {"C_1": Q_(C1, "F"), "f": Q_(f, "Hz")},
        HART_DRIVE,
        [
            "rampa chega a cerca de 75 % de V_CC no fim do semiciclo (faixa de entrada do LM393)",
            "corrente de polarização da entrada do comparador desprezada",
        ],
    )
    # 4. exact periodic ramp (two RC states)
    tau1 = R5 * C1
    Rdr = Rd + Ron
    tau2 = C1 * R5 * Rdr / (R5 + Rdr)
    Vf2 = Vcc * Rdr / (R5 + Rdr)
    a = math.exp(-t_ramp / tau1)
    b = math.exp(-t_w / tau2)
    V0 = (Vf2 * (1 - b) + b * Vcc * (1 - a)) / (1 - a * b)
    Vpk = Vcc + (V0 - Vcc) * a
    add(
        "fd_V0",
        "Tensão de C1 no início da rampa (regime periódico)",
        r"V_0 = \frac{V_{f2}(1-b) + bV_{CC}(1-a)}{1-ab},\ a = e^{-t_r/R_5C_1},\ "
        r"b = e^{-t_w/\tau_2},\ V_{f2} = V_{CC}\frac{R_d+R_{on}}{R_5+R_d+R_{on}}",
        V0,
        "V",
        {"R_5": Q_(R5, "ohm"), "C_1": Q_(C1, "F"), "R_d": Q_(Rd, "ohm")},
        HART_DRIVE,
    )
    add(
        "fd_Vpk",
        "Pico da rampa (fim do semiciclo)",
        r"V_{pk} = V_{CC} - (V_{CC} - V_0)\,e^{-t_r/R_5C_1}",
        Vpk,
        "V",
        {"V_0": Q_(V0, "V")},
        HART_DRIVE,
    )
    lo, hi = math.degrees(theta_r), 180 - math.degrees(theta_r)
    add(
        "fd_alpha_lo",
        "Menor ângulo que o circuito produz",
        r"\alpha_{min} = \theta_r",
        lo,
        "deg",
        {},
        HART_DRIVE,
    )
    add(
        "fd_alpha_hi",
        "Maior ângulo que o circuito produz",
        r"\alpha_{max} = 180° - \theta_r",
        hi,
        "deg",
        {},
        HART_DRIVE,
    )
    a_set = min(max(alpha_deg, lo + 1e-6), hi - 1e-6)
    if not lo < alpha_deg < hi:
        warnings.append(
            DesignWarning(
                code="disparo_fora_da_faixa",
                message=f"α = {alpha_deg:g}° está fora da faixa do circuito de disparo "
                f"({lo:.1f}° a {hi:.1f}°, limitada pela janela do detector de zero): aumente a "
                "tensão de sincronismo ou mude α.",
            )
        )
    Vc = Vcc - (Vcc - V0) * math.exp(-math.radians(a_set - lo) / (w * tau1))
    add(
        "fd_Vctrl",
        "Tensão de controle para o ângulo nominal (cursor de RV1)",
        r"V_c = V_{CC} - (V_{CC} - V_0)\,e^{-(\alpha - \theta_r)/\omega R_5 C_1}",
        Vc,
        "V",
        {r"\alpha": Q_(alpha_deg, "deg"), r"\theta_r": Q_(lo, "deg"), "V_0": Q_(V0, "V")},
        HART_DRIVE,
        ["U1B solta a saída quando a rampa passa de V_c (comparador ideal, offset desprezado)"],
    )
    add(
        "fd_x",
        "Posição do cursor de RV1 (fração de V_CC)",
        r"x = V_c / V_{CC}",
        Vc / Vcc * 100,
        "percent",
        {"V_c": Q_(Vc, "V")},
        HART_DRIVE,
        ["RV1 = 10 kΩ linear entre V_CC e o terra"],
    )
    sens = math.degrees(w * tau1 / (Vcc - Vc))  # dα/dV_c: ωR5C1/(V_CC − V_c) rad/V, in deg/V
    add(
        "fd_sens",
        "Sensibilidade do ângulo à tensão de controle",
        r"\frac{d\alpha}{dV_c} = \frac{\omega R_5 C_1}{V_{CC} - V_c}",
        sens,
        "deg/V",
        {"V_c": Q_(Vc, "V")},
        HART_DRIVE,
    )
    add(
        "alpha_fire",
        "Ângulo de disparo produzido pelo circuito (início do pulso dos LEDs)",
        r"\alpha = \theta_r + \omega R_5 C_1 \ln\frac{V_{CC} - V_0}{V_{CC} - V_c}",
        a_set,
        "deg",
        {"V_c": Q_(Vc, "V")},
        HART_DRIVE,
    )

    # 5. LED string and driver transistor
    v_av = Vcc - n * VFl_max - vsat
    if v_av <= 0:
        warnings.append(
            DesignWarning(
                code="disparo_vcc",
                message=f"V_CC = {Vcc:g} V não alimenta {n} LED(s) em série: aumente V_CC.",
            )
        )
        return {}, basic(0.0, 0.0, "fd_Vm_max", "fd_Vm_max")
    RLED = _e(v_av / (IF_MARGIN * IFT_), "ohm", "E24", "down")
    add(
        "fd_RLED",
        f"Resistor dos {n} LED(s) em série dos optoacopladores (E24)",
        r"R_{LED} \leq \frac{V_{CC} - nV_{F,max} - V_{CE,sat}}{1{,}2\,I_{FT}}",
        RLED,
        "ohm",
        {
            "n": Q_(n, ""),
            "V_{F,max}": Q_(VFl_max, "V"),
            "V_{CE,sat}": Q_(vsat, "V"),
            "I_{FT}": Q_(IFT_, "A"),
        },
        ref_moc,
        ["fórmula de R_LED da fig. 7 do datasheet, com 20 % de folga sobre I_FT máx."],
    )
    IF_min = v_av / RLED
    IF_typ = (Vcc - n * VFl - vsat) / RLED
    add(
        "fd_IF_min",
        "Corrente no LED no pior caso (V_F máx.)",
        r"I_{F,min} = \frac{V_{CC} - nV_{F,max} - V_{CE,sat}}{R_{LED}}",
        IF_min,
        "A",
        {"R_{LED}": Q_(RLED, "ohm")},
        ref_moc,
    )
    add(
        "fd_IF",
        "Corrente no LED (V_F típico)",
        r"I_F = \frac{V_{CC} - nV_{F,typ} - V_{CE,sat}}{R_{LED}}",
        IF_typ,
        "A",
        {"V_{F,typ}": Q_(VFl, "V"), "R_{LED}": Q_(RLED, "ohm")},
        ref_moc,
        ["LED e transistor saturado como quedas constantes"],
    )
    if IF_typ > IFmax_:
        warnings.append(
            DesignWarning(
                code="disparo_if",
                message=f"Corrente nos LEDs ({format_eng(Q_(IF_typ, 'A'))}) acima do máximo do "
                "optoacoplador: aumente R_LED.",
            )
        )
    IB_req = BASE_OVERDRIVE * IF_typ / hfe_
    R7 = _e(Vcc / IOL_, "ohm", "E12", "up")
    IB = (Vcc - vbe_) / R7
    add(
        "fd_R7",
        "Resistor de pull-up de U1B / base de Q1 (E12)",
        r"R_7 \geq \frac{V_{CC}}{I_{OL}},\quad I_B = \frac{V_{CC} - V_{BE}}{R_7} \geq "
        r"5\frac{I_F}{h_{FE,min}}",
        R7,
        "ohm",
        {"I_{OL}": Q_(IOL_, "A"), "h_{FE,min}": Q_(hfe_, ""), "V_{BE}": Q_(vbe_, "V")},
        MOHAN_GATE,
        ["corrente drenada pelo LM393 dentro do ensaio de V_OL", "sobreacionamento de base 5×"],
    )
    add(
        "fd_IB",
        "Corrente de base de Q1",
        r"I_B = \frac{V_{CC} - V_{BE}}{R_7}",
        IB,
        "A",
        {"R_7": Q_(R7, "ohm")},
        MOHAN_GATE,
    )
    if IB_req > IB:
        warnings.append(
            DesignWarning(
                code="disparo_base",
                message=f"Q1 pode não saturar: I_B = {format_eng(Q_(IB, 'A'))} < "
                f"{format_eng(Q_(IB_req, 'A'))} (5·I_F/h_FE). Use um transistor de h_FE maior.",
            )
        )

    # 6. gate circuit
    IGM = _param(parts.scr, "IGM", "A")
    PGM = _param(parts.scr, "PGM", "W")
    i_lim = min(ITSM_, IGM) if IGM is not None else ITSM_
    if PGM is not None:
        i_lim = min(i_lim, PGM / VGT_)
    RG = _e(Vm_max / i_lim, "ohm", "E12", "up")
    add(
        "fd_RG",
        "Resistor de porta (limita a corrente do fototriac, E12)",
        r"R_G \geq \frac{V_{m,max}}{\min(I_{TSM},\ I_{GM},\ P_{GM}/V_{GT})}",
        RG,
        "ohm",
        {"V_{m,max}": Q_(Vm_max, "V"), "I_{TSM}": Q_(ITSM_, "A")}
        | ({"I_{GM}": Q_(IGM, "A")} if IGM is not None else {})
        | ({"P_{GM}": Q_(PGM, "W")} if PGM is not None else {}),
        ref_moc,
        [
            "R = V_pico/I_TSM da fig. 7 do datasheet do MOC3021M",
            "o fototriac conduz só até o tiristor travar",
        ],
    )
    IG_pk = Vm_max / RG
    add(
        "fd_IG_pk",
        "Pico de corrente de porta (pior caso, disparo no pico)",
        r"I_{G,pk} \approx \frac{V_{m,max}}{R_G}",
        IG_pk,
        "A",
        {"R_G": Q_(RG, "ohm")},
        MOHAN_GATE,
    )
    out["fd_RGK"] = Q_(RGK, "ohm")
    V_need = VTM_ + VFg_ + VGT_ + RG * (IGT_ + VGT_ / RGK)
    s_g = (V_need + max(E, 0.0)) / Vm_min
    alpha_g = math.degrees(math.asin(min(s_g, 1.0)))
    add(
        "fd_alpha_gate",
        "Menor ângulo com corrente de porta suficiente (rede no mínimo)",
        r"V_m(1-\delta)\sin\alpha_g - E = V_{TM} + V_{F,DG} + V_{GT} + R_G\left(I_{GT} + "
        r"\frac{V_{GT}}{R_{GK}}\right)",
        alpha_g,
        "deg",
        {
            "V_{TM}": Q_(VTM_, "V"),
            "V_{GT}": Q_(VGT_, "V"),
            "I_{GT}": Q_(IGT_, "A"),
            "R_{GK}": Q_(RGK, "ohm"),
            "E": Q_(E, "V"),
        },
        MOHAN_GATE,
        [
            "I_GT e V_GT máximos do datasheet do tiristor (pior caso)",
            "R_GK = 1 kΩ (escolha: imunidade a ruído e dv/dt)",
            "E somado como pior caso (corrente descontínua)",
        ],
    )
    worst_low = min(alpha_deg, alpha_min_deg if alpha_min_deg is not None else alpha_deg)
    if worst_low < alpha_g:
        warnings.append(
            DesignWarning(
                code="disparo_porta",
                message=f"Abaixo de α = {alpha_g:.1f}° a tensão no anodo não garante a corrente de "
                f"porta (I_GT máx.) pelo fototriac; α nominal/mínimo = {worst_low:.1f}°.",
            )
        )
    if alpha_max_deg is not None and alpha_max_deg >= hi:
        warnings.append(
            DesignWarning(
                code="disparo_faixa_rede",
                message=f"Com a rede no máximo, α precisa chegar a {alpha_max_deg:.1f}°, acima do "
                f"limite do circuito ({hi:.1f}°).",
            )
        )
    out |= {
        "fd_R2": Q_(R2_SYNC, "ohm"),
        "fd_R3": Q_(R3_TH, "ohm"),
        "fd_RV1": Q_(RV1, "ohm"),
        "fd_Vcc": Q_(Vcc, "V"),
        "fd_Vsync": Q_(Vsync, "V"),
    }

    stresses = [
        *basic(IG_pk, IF_typ, "fd_IG_pk", "fd_IF"),
        Stress(
            designator=designator_scr,
            key="IGM",
            label="Corrente de porta de pico",
            value=QuantityModel(value=IG_pk, unit="A"),
            calc_step_id="fd_IG_pk",
        ),
    ]
    return out, stresses


# ----------------------------------------------------------------------------- netlist
def models(VT: float, parts: FiringParts) -> list[str]:
    """Subcircuits: SCR with a real gate, comparator, transistor switch, coupler, diodes."""
    IGT = _param(parts.scr, "IGT", "A") or 0.0
    VGT = _param(parts.scr, "VGT", "V") or 0.0
    VOL = _param(parts.comparator, "VOL", "V") or 0.0
    IOL = _cond(parts.comparator, "VOL", "IOL", "A") or 1.0
    vsat = _param(parts.bjt, "VCE(sat)", "V") or 0.0
    vbe = _param(parts.bjt, "VBE(on)", "V") or 0.0
    VFl = _param(parts.moc, "VF", "V", "typ") or 0.0
    IFT = _param(parts.moc, "IFT", "A") or 0.0
    VTM = _param(parts.moc, "VTM", "V") or 0.0
    VFs = _param(parts.d_sync, "VF", "V") or 0.0
    VFg = _param(parts.d_gate, "VF", "V") or 0.0
    g = "{:.9g}".format
    return [
        ".subckt SCRG a k g",
        # the anode conducts only once the latch is set (st > 0,5): the gate current through
        # the phototriac lasts until then, as in the real regenerative turn-on
        f"BA a ks I = (v(st) > 0.5 && v(a,k) > {g(VT)}) ? (v(a,k) - {g(VT)}) / 1m : 0",
        "VKS ks k DC 0",
        "RLK a k 1Meg",
        "VGS g gj DC 0",
        f"BGK gj k I = (v(gj,k) > {g(VGT)}) ? (v(gj,k) - {g(VGT)}) / 1m : 0",
        f"BST nst 0 V = ((i(VGS) > {g(IGT)} && v(a,k) > {g(VT)}) || "
        "(v(st) > 0.5 && i(VKS) > 1e-6)) ? 1 : 0",
        "RST nst st 1k",
        "CST st 0 1n",
        ".ends",
        ".subckt CMPOC inp inn out",
        f"BO out 0 I = (v(inp) < v(inn)) ? v(out) / {g(VOL / IOL)} : 0",
        "RLO out 0 1G",
        ".ends",
        ".subckt QSW b c e",
        f"BBE b e I = (v(b,e) > {g(vbe)}) ? (v(b,e) - {g(vbe)}) / 1m : 0",
        f"BCE c e I = (v(b,e) > {g(vbe - 0.05)} && v(c,e) > {g(vsat)}) ? "
        f"(v(c,e) - {g(vsat)}) / 1m : 0",
        "RCE c e 1G",
        ".ends",
        ".subckt MOCTR la lk m1 m2",
        "VSL la lx DC 0",
        f"BL lx lk I = (v(lx,lk) > {g(VFl)}) ? (v(lx,lk) - {g(VFl)}) / 1m : v(lx,lk) * 1n",
        f"BT m1 m2 I = (i(VSL) > {g(IFT * 0.999)}) ? ((v(m1,m2) > {g(VTM)}) ? "
        f"(v(m1,m2) - {g(VTM)}) / 1m : ((v(m1,m2) < -{g(VTM)}) ? "
        f"(v(m1,m2) + {g(VTM)}) / 1m : 0)) : 0",
        "RLT m1 m2 1G",
        ".ends",
        ".subckt DSYN a k",
        f"BD a k I = (v(a,k) > {g(VFs)}) ? (v(a,k) - {g(VFs)}) / 1m : v(a,k) * 1n",
        ".ends",
        ".subckt DGT a k",
        f"BD a k I = (v(a,k) > {g(VFg)}) ? (v(a,k) - {g(VFg)}) / 1m : v(a,k) * 1n",
        ".ends",
    ]


def netlist(topology: str, s: Mapping[str, float], f: float, Vm_sync_pk: float) -> list[str]:
    """Elements of the firing circuit (gate nodes g1…gn, SCR subckt SCRG)."""
    g = "{:.9g}".format
    n = N_SCR[topology]
    vcc = s["fd_Vcc"]
    x = s["fd_Vctrl"] / vcc
    lines = [
        f"VCCF vcc 0 DC {g(vcc)}",
        f"VSY sy1 sy2 SIN(0 {g(Vm_sync_pk)} {g(f)})",
        "RSY sy2 0 10Meg",
        "XDS1 sy1 rp DSYN",
        "XDS2 sy2 rp DSYN",
        "XDS3 0 sy1 DSYN",
        "XDS4 0 sy2 DSYN",
        f"R1 rp zs {g(s['fd_R1'])}",
        f"R2 zs 0 {g(s['fd_R2'])}",
        f"R3 vcc vth {g(s['fd_R3'])}",
        f"R4 vth 0 {g(s['fd_R4'])}",
        "XU1A zs vth zr CMPOC",
        f"RD c1 zr {g(s['fd_Rd'])}",
        f"R5 vcc c1 {g(s['fd_R5'])}",
        f"C1 c1 0 {g(s['fd_C1'])}",
        f"RV1A vcc vc {g(s['fd_RV1'] * (1 - x))}",
        f"RV1B vc 0 {g(s['fd_RV1'] * x)}",
        "XU1B c1 vc qb CMPOC",
        f"R7 vcc qb {g(s['fd_R7'])}",
        "XQ1 qb lk 0 QSW",
        f"RLED vcc la0 {g(s['fd_RLED'])}",
        "VLED la0 l0 DC 0",
        f"BTH th 0 V = 360 * ({g(f)} * time - floor({g(f)} * time))",
    ]
    nodes = SCR_NODES[topology]
    for i, (scr, (an, ka)) in enumerate(nodes.items()):
        k = i + 1
        led_out = "lk" if k == n else f"l{k}"
        lines += [
            f"XU{k + 1} l{k - 1} {led_out} {an} m{k} MOCTR",
            f"XDG{k} m{k} n{k} DGT",
            f"RG{k} n{k} gs{k} {g(s['fd_RG'])}",
            f"VIG{k} gs{k} g{k} DC 0",
            f"RGK{k} g{k} {ka} {g(s['fd_RGK'])}",
            f"X{scr} {an} {ka} g{k} SCRG",
        ]
    return lines


PROBES = {
    "Disparo: tensão do sincronismo retificada (v_z)": "v(zs)",
    "Disparo: rampa em C1": "v(c1)",
    "Disparo: tensão de controle (V_c)": "v(vc)",
    "Disparo: corrente nos LEDs dos optoacopladores": "i(vled)",
    "Disparo: corrente de gate de T1": "i(vig1)",
}
_SAME = "mesmo modelo no simulador (comparador ideal com V_OL, quedas constantes)"


def checks() -> list[SimCheck]:
    return [
        SimCheck(
            quantity="Ângulo de disparo produzido pelo circuito",
            summary_key="alpha_fire",
            metric="x_rise",
            probe="i(vled)",
            voltage="v(th)",
            tolerance_pct=2.0,
            justification=_SAME + "; resolução do passo de tempo (T/8000 = 0,045°)",
        ),
        SimCheck(
            quantity="Pico da rampa em C1",
            summary_key="fd_Vpk",
            metric="max",
            probe="v(c1)",
            tolerance_pct=1.0,
            justification=_SAME,
        ),
        SimCheck(
            quantity="Corrente nos LEDs dos optoacopladores",
            summary_key="fd_IF",
            metric="max",
            probe="i(vled)",
            tolerance_pct=1.0,
            justification=_SAME,
        ),
    ]


def practice(topology: str, s: Mapping[str, float]) -> dict[str, object]:
    """Objective, material and procedure of the lab guide with the firing circuit."""
    n = N_SCR[topology]
    scrs = ", ".join(SCR_NODES[topology])

    def v(key: str, unit: str) -> str:
        return format_eng(Q_(s[key], unit))

    return {
        "objective": "Montar o circuito de disparo por rampa sincronizada, ajustar o ângulo α "
        "pela tensão de controle e verificar o efeito de α na tensão média da carga.",
        "material": f"Transformador de potência e de sincronismo, {n} tiristor(es) ({scrs}), "
        f"LM393, transistor NPN, {n} optoacoplador(es) MOC3021, diodos, resistores, C1, "
        f"potenciômetro RV1, fonte CC de {v('fd_Vcc', 'V')}, osciloscópio com ponteira "
        "diferencial, multímetro true RMS.",
        "procedure": [
            "Monte só o circuito de disparo (sem ligar a potência). Alimente com V_CC e o "
            "trafo de sincronismo.",
            f"Meça o limiar em R4 (esperado {v('fd_Vth', 'V')}) e observe v_z no nó R1/R2: "
            "a saída de U1A deve ficar em nível baixo só perto de cada cruzamento por zero.",
            f"Observe a rampa em C1: começa em cerca de {v('fd_V0', 'V')} e chega a "
            f"{v('fd_Vpk', 'V')} no fim de cada semiciclo.",
            f"Ajuste RV1 até o cursor marcar {v('fd_Vctrl', 'V')} e meça no osciloscópio o "
            "atraso entre o zero do sincronismo e o início da tensão em RLED: "
            f"α = {s['alpha_fire']:.1f}° (sensibilidade de {s['fd_sens']:.1f}°/V).",
            f"Confirme a corrente nos LEDs pela tensão em RLED (I_F ≈ {v('fd_IF', 'A')}).",
            "Desligue tudo, ligue a saída de cada MOC3021 ao seu tiristor (anodo → saída → DG → "
            "RG → porta; RGK entre porta e catodo) e confira a polaridade do trafo de "
            "sincronismo (em fase com o secundário de potência).",
            "Ligue a potência e meça a tensão média na carga; varie RV1 e levante a curva "
            "V_o × α comparando com o cálculo.",
        ],
    }


# ----------------------------------------------------------------------------- labels
LABELS = {
    "fd_R1": "Disparo: R1 (divisor do sincronismo)",
    "fd_R2": "Disparo: R2 (divisor do sincronismo)",
    "fd_R3": "Disparo: R3 (limiar de zero)",
    "fd_R4": "Disparo: R4 (limiar de zero)",
    "fd_Vth": "Disparo: limiar do detector de zero",
    "fd_theta_r": "Disparo: meia janela de reinício da rampa",
    "fd_Rd": "Disparo: Rd (descarga de C1)",
    "fd_C1": "Disparo: C1 (rampa)",
    "fd_R5": "Disparo: R5 (carga da rampa)",
    "fd_V0": "Disparo: tensão inicial da rampa",
    "fd_Vpk": "Disparo: pico da rampa",
    "fd_alpha_lo": "Disparo: menor α do circuito",
    "fd_alpha_hi": "Disparo: maior α do circuito",
    "fd_Vctrl": "Disparo: tensão de controle (cursor de RV1)",
    "fd_x": "Disparo: posição do cursor de RV1",
    "fd_sens": "Disparo: sensibilidade dα/dVc",
    "alpha_fire": "Ângulo de disparo produzido pelo circuito",
    "fd_RLED": "Disparo: R_LED",
    "fd_IF_min": "Disparo: corrente nos LEDs (pior caso)",
    "fd_IF": "Disparo: corrente nos LEDs",
    "fd_R7": "Disparo: R7 (pull-up e base de Q1)",
    "fd_IB": "Disparo: corrente de base de Q1",
    "fd_RG": "Disparo: R_G (porta)",
    "fd_IG_pk": "Disparo: pico de corrente de porta",
    "fd_RGK": "Disparo: R_GK (porta-catodo)",
    "fd_alpha_gate": "Disparo: menor α com corrente de porta garantida",
    "fd_RV1": "Disparo: RV1 (potenciômetro de controle)",
    "fd_Vcc": "Disparo: alimentação V_CC",
    "fd_Vsync": "Disparo: tensão do trafo de sincronismo",
}
SPEC_LABELS = {
    "firing": "Incluir circuito de disparo (para o guia de laboratório)",
    "Vcc_firing": "Alimentação do circuito de disparo (V_CC)",
    "Vsync": "Tensão do trafo de sincronismo (eficaz)",
}
