"""SPICE models of catalogue parts placed in the schematic, built from their datasheet values.

The same model builders as the design modules are used (``design/devmodels.py``,
``design/opamp.py``, the thyristor of the BD-TIR bench), so a part behaves the same in a design
and in the free simulator. Each builder also reports the datasheet spread of the parameter that
Monte Carlo and worst case vary (:class:`Spread`).
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from dataclasses import dataclass

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.core.calc import CalcLog
from circuitos.core.units import Q_, parse_unit
from circuitos.design import devmodels
from circuitos.design.opamp import OpAmp, opamp_model
from circuitos.devices import igbt as igbt_dev
from circuitos.devices import thyristor


@dataclass(frozen=True)
class Spread:
    """Range of one model parameter: generic ``tol`` or datasheet minimum/maximum."""

    param: str
    lo: float
    nom: float
    hi: float
    source: str

    def at(self, u: float) -> float:
        """Value for u ∈ [−1, 1]: −1 → lo, 0 → nominal, +1 → hi (piecewise linear)."""
        return self.nom + u * ((self.hi - self.nom) if u >= 0 else (self.nom - self.lo))


@dataclass
class PartModel:
    model_name: str
    model_text: str  # .model / .subckt lines
    warnings: list[str]
    spread: Spread | None = None
    extra: dict[str, float] = dataclasses.field(default_factory=dict)


def digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def _num(p: Parameter | None, prefer: tuple[str, ...] = ("typ", "max", "min")) -> float | None:
    if p is None or not p.has_value:
        return None
    return float(Q_(devmodels.value(p, prefer), parse_unit(p.unit)).to_base_units().magnitude)


def _si(p: Parameter, attr: str) -> float | None:
    v = getattr(p, attr)
    if v is None:
        return None
    return float(Q_(float(v), parse_unit(p.unit)).to_base_units().magnitude)


def review_warning(rec: ComponentRecord, ref: str) -> list[str]:
    if rec.review.status == "liberado":
        return []
    return [
        f"{ref}: {rec.part_number} ainda não foi revisado (status {rec.review.status}); "
        "o modelo usa os valores extraídos do datasheet, sem conferência."
    ]


def constant_drop_diode(name: str, vf: float) -> str:
    """Constant-drop diode (1 mΩ above VF, 1 µS reverse leakage), as in the design modules."""
    return "\n".join(
        [
            f".subckt {name} a k",
            f"BD a k I = (v(a,k) > {vf:.9g}) ? (v(a,k) - {vf:.9g}) / 1m : v(a,k) * 1u",
            ".ends",
        ]
    )


def diode(rec: ComponentRecord, ref: str) -> PartModel:
    vf = _num(rec.parameters.get("VF"), ("typ", "max"))
    if vf is None:
        raise ValueError(f"{ref}: {rec.part_number} sem VF no datasheet")
    p = rec.parameters["VF"]
    warn = review_warning(rec, ref)
    if p.typ is None:
        warn.append(f"{ref}: VF do datasheet é máximo ({vf:.3g} V); o modelo usa esse valor.")
    warn.append(
        f"{ref}: diodo de queda constante (V_F = {vf:.3g} V); ruptura reversa e "
        "recuperação reversa não modeladas."
    )
    name = f"DCD_{digest(rec.part_number + str(vf))}"
    return PartModel(name, constant_drop_diode(name, vf), warn)


def zener_subckt(name: str, vz0: float, rz: float, vf: float) -> str:
    """Zener of the design modules (V_Z0 + r_z·I) plus a constant forward drop."""
    return "\n".join(
        [
            f".subckt {name} a k",
            f"BZ k a I = (v(k,a) > {vz0:.9g}) ? (v(k,a) - {vz0:.9g}) / {rz:.9g} : v(k,a) * 1n",
            f"BF a k I = (v(a,k) > {vf:.9g}) ? (v(a,k) - {vf:.9g}) / 1m : 0",
            ".ends",
        ]
    )


def zener(
    rec: ComponentRecord, ref: str, log: CalcLog, vz_override: float | None = None
) -> PartModel:
    pwl, warn = devmodels.zener_pwl(rec, log, ref)
    warn = review_warning(rec, ref) + warn
    vf = _num(rec.parameters.get("VF"), ("typ", "max"))
    if vf is None:
        vf = 0.7
        warn.append(f"{ref}: datasheet sem VF; condução direta com 0,7 V (premissa).")
    vz_p = rec.parameters["VZ"]
    spread: Spread | None = None
    lo, hi = _si(vz_p, "min"), _si(vz_p, "max")
    if lo is not None and hi is not None:
        spread = Spread("vz", lo, pwl.VZ, hi, f"VZ mín./máx. do datasheet ({rec.part_number})")
    else:
        tol = _num(rec.parameters.get("VZ_tol"), ("max", "typ"))
        if tol is not None:
            t = tol if tol > 1 else tol * 100  # percent unit converts to a fraction
            spread = Spread(
                "vz",
                pwl.VZ * (1 - t / 100),
                pwl.VZ,
                pwl.VZ * (1 + t / 100),
                f"tolerância de VZ ±{t:g} % ({rec.part_number})",
            )
    vz = vz_override if vz_override is not None else pwl.VZ
    vz0 = vz - pwl.IZT * pwl.rz
    text_key = f"{rec.part_number}|{vz0:.9g}|{pwl.rz:.9g}|{vf:.9g}"
    name = f"DZ_{digest(text_key)}"
    return PartModel(name, zener_subckt(name, vz0, pwl.rz, vf), warn, spread)


def bjt(
    rec: ComponentRecord, ref: str, ic_op: float, log: CalcLog, bf_override: float | None
) -> PartModel:
    warn = review_warning(rec, ref)
    if devmodels.is_darlington(rec):
        dm, w = devmodels.darlington_model(rec, ic_op, Q_(0.7, "V"), 100.0, log, ref)
        name = f"DAR_{digest(rec.part_number + str(ic_op))}"
        return PartModel(name, dm.subckt(name), warn + w, extra={"darlington": 1.0})
    m, w = devmodels.bjt_model(rec, ic_op, Q_(0.7, "V"), 100.0, log, ref)
    warn += w
    spread: Spread | None = None
    entries = devmodels.hfe_entries(rec)
    if entries:
        ics = [ic for ic, _ in entries]
        best = min(
            range(len(entries)),
            key=lambda k: abs(math.log((ics[k] or ic_op) / ic_op)),
        )
        p = entries[best][1]
        if p.min is not None and p.max is not None:
            spread = Spread(
                "bf",
                float(p.min),
                m.BF,
                float(p.max),
                f"hFE mín./máx. do datasheet ({rec.part_number})",
            )
    if bf_override is not None:
        m = dataclasses.replace(m, BF=bf_override)
    name = f"QM_{digest(rec.part_number + m.spice('x'))}"
    return PartModel(name, m.spice(name), warn, spread)


def mosfet(rec: ComponentRecord, ref: str, log: CalcLog, vto_override: float | None) -> PartModel:
    m, w = devmodels.mos_model(rec, log, ref)
    warn = review_warning(rec, ref) + w
    vth = rec.parameters["VGS(th)"]
    lo, hi = _si(vth, "min"), _si(vth, "max")
    spread = (
        Spread("vto", lo, m.VT, hi, f"VGS(th) mín./máx. do datasheet ({rec.part_number})")
        if lo is not None and hi is not None
        else None
    )
    p_channel = rec.category.startswith("mosfet.p")
    if p_channel:
        # catalogue values are magnitudes (schema mosfet.p): SPICE wants VTO < 0 for PMOS
        if spread is not None:
            spread = Spread("vto", -spread.hi, -spread.nom, -spread.lo, spread.source)
        if vto_override is not None:
            vto_override = -abs(vto_override)
    if vto_override is not None:
        m = dataclasses.replace(m, VT=abs(vto_override))
    text = m.spice("x")
    if p_channel:
        text = text.replace("NMOS(LEVEL=1 VTO=", "PMOS(LEVEL=1 VTO=-")
    name = f"MM_{digest(rec.part_number + text)}"
    warn.append(f"{ref}: MOSFET de nível 1 sem capacitâncias nem diodo de corpo.")
    return PartModel(name, text.replace(".model x ", f".model {name} "), warn, spread)


def jfet(rec: ComponentRecord, ref: str, log: CalcLog) -> PartModel:
    m, w = devmodels.jfet_model(rec, log, ref)
    text = m.spice("x")
    if rec.category.startswith("jfet.p"):
        # magnitudes in the catalogue (schema jfet.p): PJF takes VTO = +|VP|
        text = text.replace(f"NJF(VTO={-m.VP:.6g}", f"PJF(VTO={m.VP:.6g}")
    name = f"JM_{digest(rec.part_number + text)}"
    return PartModel(
        name, text.replace(".model x ", f".model {name} "), review_warning(rec, ref) + w
    )


def opamp_subckt(name: str, m: OpAmp) -> str:
    """Macromodel of the design modules (slew-rate limit and output clamp) as a subcircuit."""
    lines = [f".subckt {name} inp inn out", *m.nonlinear_lines("o", "inp", "inn", "out"), ".ends"]
    return "\n".join(lines)


def opamp(rec: ComponentRecord, ref: str, vcc: float, vee: float, log: CalcLog) -> PartModel:
    m, w = opamp_model(rec, vcc, vee, log, ref)
    name = f"OA_{digest(rec.part_number + opamp_subckt('x', m))}"
    return PartModel(name, opamp_subckt(name, m), review_warning(rec, ref) + w)


def thyristor_subckt(
    name: str,
    kind: thyristor.Kind,
    vt0: float,
    rt: float,
    igt: tuple[float, float, float, float],
    ih: float,
    il: float,
) -> str:
    m = thyristor.ThyristorModel(
        kind=kind,
        VT0=Q_(vt0, "V"),
        rT=Q_(rt, "ohm"),
        IGT=(Q_(igt[0], "A"), Q_(igt[1], "A"), Q_(igt[2], "A"), Q_(igt[3], "A")),
        IH=Q_(ih, "A"),
        IL=Q_(il, "A"),
    )
    return m.spice(name)


def thyristor_part(
    rec: ComponentRecord, ref: str, kind: thyristor.Kind, vt0: float, il_default: float
) -> PartModel:
    warn = review_warning(rec, ref)
    params = rec.parameters
    if kind == "triac":
        values = [_num(params.get(f"IGT@{q}"), ("max", "typ")) for q in thyristor.QUADRANTS]
    else:
        values = [_num(params.get("IGT"), ("max", "typ"))]
    if any(v is None for v in values):
        raise ValueError(f"{ref}: {rec.part_number} sem IGT no datasheet")
    gt = [float(v) for v in values if v is not None]
    igt = (gt[0], gt[1], gt[2], gt[3]) if kind == "triac" else (gt[0], 1e6, 1e6, 1e6)
    ih = _num(params.get("IH"), ("max", "typ"))
    if ih is None:
        raise ValueError(f"{ref}: {rec.part_number} sem IH no datasheet")
    il = _num(params.get("IL"), ("max", "typ"))
    if il is None:
        il = max(il_default, ih)
        warn.append(
            f"{ref}: o datasheet não dá I_L; usado {il * 1e3:.3g} mA (parâmetro do símbolo, "
            "no mínimo I_H)."
        )
    rt = 10e-3
    p_vtm = params.get("VTM")
    if p_vtm is not None and p_vtm.has_value and "ITM" in p_vtm.conditions:
        vtm = _num(p_vtm, ("typ", "max"))
        itm = p_vtm.conditions["ITM"].to_pint().m_as("A")
        assert vtm is not None
        fit = thyristor.on_state_fit(Q_(vtm, "V"), Q_(itm, "A"), Q_(vt0, "V"))
        rt = float(fit.value.m_as("ohm"))
    else:
        warn.append(f"{ref}: datasheet sem VTM; r_T = 10 mΩ (premissa).")
    warn.append(
        f"{ref}: I_GT e I_H máximos do datasheet (disparo garantido); V_T0 = {vt0:g} V do símbolo."
    )
    key = f"{rec.part_number}|{vt0}|{rt}|{igt}|{ih}|{il}"
    name = f"TH_{digest(key)}"
    return PartModel(name, thyristor_subckt(name, kind, vt0, rt, igt, ih, il), warn)


def igbt_subckt(name: str, vth: float, v0: float, ron: float, diode: bool, vf: float) -> str:
    lines = [
        f".subckt {name} c g e",
        f"BC c e I = (v(g,e) > {vth:.9g}) ? max(v(c,e) - {v0:.9g}, 0) / {ron:.9g} : 0",
        "RL c e 10meg",
        "RG g e 1g",
    ]
    if diode:
        lines.append(f"BD e c I = (v(e,c) > {vf:.9g}) ? (v(e,c) - {vf:.9g}) / 1m : 0")
    lines.append(".ends")
    return "\n".join(lines)


def igbt(rec: ComponentRecord, ref: str, v0: float, with_diode: bool) -> PartModel:
    warn = review_warning(rec, ref)
    params = rec.parameters
    vth = _num(params.get("VGE(th)"), ("typ", "max"))
    p_sat = params.get("VCE(sat)")
    if vth is None or p_sat is None or not p_sat.has_value or "IC" not in p_sat.conditions:
        raise ValueError(f"{ref}: {rec.part_number} sem VGE(th) ou VCE(sat) com IC de ensaio")
    vce = _num(p_sat, ("typ", "max"))
    assert vce is not None
    ic = p_sat.conditions["IC"].to_pint()
    ron = float(igbt_dev.fit_r_on(Q_(vce, "V"), ic, Q_(v0, "V")).value.m_as("ohm"))
    vf = _num(params.get("VF"), ("typ", "max"))
    if with_diode and vf is None:
        warn.append(f"{ref}: sem VF do diodo no datasheet; diodo antiparalelo com 1,5 V.")
        vf = 1.5
    warn.append(
        f"{ref}: IGBT linear por partes: V_GE(th) típico, r_on de VCE(sat) a "
        f"{ic.m_as('A'):g} A com joelho V0 = {v0:g} V; sem perdas de comutação."
    )
    name = f"IG_{digest(f'{rec.part_number}|{v0}|{with_diode}')}"
    return PartModel(name, igbt_subckt(name, vth, v0, ron, with_diode, vf or 1.5), warn)


# ------------------------------------------------------------------ LEDs and lamps (indicators)
_LED_COLOURS = (
    ("infraverm", "ir"),
    ("infrared", "ir"),
    ("vermelh", "vermelho"),
    ("red", "vermelho"),
    ("laranja", "laranja"),
    ("orange", "laranja"),
    ("amarel", "amarelo"),
    ("yellow", "amarelo"),
    ("verde", "verde"),
    ("green", "verde"),
    ("azul", "azul"),
    ("blue", "azul"),
    ("branc", "branco"),
    ("white", "branco"),
)


def led_colour(rec: ComponentRecord) -> str | None:
    """Colour of a catalogue LED from its ``cor`` attribute (None: not stated)."""
    attr = rec.attributes.get("cor")
    text = (attr.value if attr is not None else "").lower()
    for key, colour in _LED_COLOURS:
        if key in text:
            return colour
    return None


@dataclass(frozen=True)
class LedData:
    vf: float  # V, forward drop of the constant-drop model
    i_ref: float  # A, test current of V_F (100 % brightness)
    i_max: float | None  # A, maximum DC forward current
    colour: str | None


def led_data(rec: ComponentRecord, ref: str) -> tuple[LedData, list[str]]:
    """V_F (typical, else maximum) at its test current and I_F max., from the datasheet."""
    p = rec.parameters.get("VF")
    vf = _num(p, ("typ", "max"))
    if p is None or vf is None:
        raise ValueError(f"{ref}: {rec.part_number} sem VF no datasheet")
    warn = review_warning(rec, ref)
    if p.typ is None:
        warn.append(f"{ref}: o datasheet não dá V_F típico; o modelo usa o máximo ({vf:.3g} V).")
    cond = p.conditions.get("IF")
    i_ref = float(cond.to_pint().m_as("A")) if cond is not None else None
    i_max = _num(rec.parameters.get("IF"), ("max",))
    if i_ref is None:
        i_ref = i_max
    if i_ref is None:
        raise ValueError(f"{ref}: {rec.part_number} sem corrente de ensaio de VF nem IF máx.")
    warn.append(
        f"{ref}: LED de queda constante (V_F = {vf:.3g} V a {i_ref * 1e3:.3g} mA); "
        "a resistência dinâmica não está no datasheet e não é modelada."
    )
    return LedData(vf, i_ref, i_max, led_colour(rec)), warn


@dataclass(frozen=True)
class LampData:
    vn: float  # V
    pn: float  # W

    @property
    def r_hot(self) -> float:
        """Hot filament resistance at the rated point, R = V_n²/P_n (Ω)."""
        return self.vn**2 / self.pn


def lamp_data(rec: ComponentRecord, ref: str) -> tuple[LampData, list[str]]:
    vn = _num(rec.parameters.get("V_nom"), ("typ", "max", "min"))
    pn = _num(rec.parameters.get("P_nom"), ("typ", "max", "min"))
    if vn is None or pn is None or pn <= 0:
        raise ValueError(f"{ref}: {rec.part_number} sem tensão e potência nominais")
    return LampData(vn, pn), review_warning(rec, ref)
