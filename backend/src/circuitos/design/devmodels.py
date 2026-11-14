"""Device models for the design modules, built from catalogue records.

The catalogue holds datasheet values; the design modules need model parameters. Each helper
logs how a model parameter came from the datasheet (or from a stated design assumption when the
datasheet has no such value), so the calculation record shows it.

* BJT: Ebers-Moll transport model with BF from hFE and IS from a forward base-emitter voltage
  assumption at the hFE test current (datasheets of small-signal parts rarely give VBE(on)).
  The same model goes to SPICE (``BjtModel.spice``), so the analytic Q-point and the
  simulation solve the same equations.
* Zener: piecewise-linear model VZ = VZ0 + rz·IZ with rz = ZZT and VZ0 = VZ − IZT·ZZT, the
  textbook equivalent circuit (Boylestad, *Electronic Devices and Circuit Theory*, ch. 2, Zener
  diodes; Malvino, *Electronic Principles*, Zener chapter: second approximation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pint
from scipy.optimize import brentq

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_, parse_unit

BOYLESTAD = BibRef(
    book="Boylestad & Nashelsky, Electronic Devices and Circuit Theory", edition="11th"
)
SEDRA = BibRef(book="Sedra & Smith, Microelectronic Circuits", edition="7th")
VT_300K = 0.025852  # kT/q at 300 K, V (27 °C, the SPICE nominal temperature)


def value(p: Parameter, prefer: tuple[str, ...] = ("typ", "max", "min")) -> float:
    for attr in prefer:
        v = getattr(p, attr)
        if v is not None:
            return float(v)
    raise ValueError(f"{p.symbol} sem valor")


def quantity(
    rec: ComponentRecord, key: str, prefer: tuple[str, ...] = ("typ", "max", "min")
) -> pint.Quantity | None:
    p = rec.parameters.get(key)
    if p is None or not p.has_value:
        return None
    return Q_(value(p, prefer), parse_unit(p.unit))


# ------------------------------------------------------------------------------------ BJT


@dataclass(frozen=True)
class Bjt:
    """Transport model used by the designs (NPN or PNP, magnitudes)."""

    IS: float  # A
    BF: float
    pnp: bool = False
    VAF: float | None = None  # V; None: no Early effect (the designs neglect it)
    CJC: float = 0.0  # F, constant (MJC = 0): Cμ
    TF: float = 0.0  # s, forward transit time: Cπ = TF·gm

    def vbe(self, ic: float, vt: float = VT_300K) -> float:
        """|VBE| for a collector current |IC| in forward-active operation."""
        return vt * math.log(ic / self.IS + 1.0)

    def ic(self, vbe: float, vt: float = VT_300K) -> float:
        return self.IS * (math.exp(vbe / vt) - 1.0)

    def ie(self, vbe: float, vt: float = VT_300K) -> float:
        """Emitter current in forward-active operation (VBC ≪ 0)."""
        return self.IS * math.expm1(min(vbe / vt, 200.0)) * (1 + 1 / self.BF)

    def em(self, vbe: float, vbc: float, vt: float = VT_300K) -> tuple[float, float]:
        """(IB, IC) of the full Ebers-Moll transport model with BR = 1 (as in SPICE, BR=1)."""
        ebe = math.expm1(min(vbe / vt, 200.0))
        ebc = math.expm1(min(vbc / vt, 200.0))
        ib = self.IS / self.BF * ebe + self.IS * ebc
        ic = self.IS * (ebe - ebc) - self.IS * ebc
        return ib, ic

    def spice(self, name: str) -> str:
        kind = "PNP" if self.pnp else "NPN"
        vaf = f" VAF={self.VAF:.6g}" if self.VAF else ""
        caps = f" CJC={self.CJC:.6g} MJC=0 TF={self.TF:.6g}" if self.CJC > 0 or self.TF > 0 else ""
        return f".model {name} {kind}(IS={self.IS:.6g} BF={self.BF:.6g} BR=1{vaf}{caps})"


def with_capacitances(
    m: Bjt, rec: ComponentRecord | None, ic: float, log: CalcLog, designator: str
) -> tuple[Bjt, list[str]]:
    """Add Cμ = Cobo and Cπ = gm/(2π·fT) − Cμ from the datasheet (hybrid-π at the Q-point)."""
    if rec is None:
        return m, []
    ft = quantity(rec, "fT", ("typ", "min"))
    cobo = quantity(rec, "Cobo", ("typ", "max"))
    if ft is None or cobo is None:
        return m, [
            f"{designator}: o datasheet não dá fT e Cobo; a resposta em alta frequência "
            "não foi calculada."
        ]
    gm = ic / VT_300K
    cmu = float(cobo.m_as("F"))
    fT = float(ft.m_as("Hz"))
    cpi = max(gm / (2 * math.pi * fT) - cmu, 0.0)
    log.add(
        record(
            f"Cpi_{designator}",
            f"Capacitâncias do modelo π-híbrido de {designator}",
            r"C_\mu = C_{obo};\quad C_\pi = \frac{g_m}{2\pi f_T} - C_\mu",
            output=Q_(cpi, "F").to("pF"),
            inputs={"f_T": ft, "C_{obo}": cobo, "g_m": Q_(gm, "S").to("mS")},
            assumptions=[
                "fT e Cobo do datasheet (típicos, ou o limite dado) usados no ponto Q",
                "C_μ constante (sem variação com V_CB)",
            ],
            reference=SEDRA.model_copy(update={"chapter": "10 (Frequency response)"}),
        )
    )
    return Bjt(m.IS, m.BF, m.pnp, m.VAF, CJC=cmu, TF=cpi / gm if gm > 0 else 0.0), []


def hfe_entries(rec: ComponentRecord) -> list[tuple[float | None, Parameter]]:
    """hFE parameters of a record with their test collector current (A)."""
    out = []
    for p in rec.parameters.values():
        if p.symbol != "hFE" or not p.has_value:
            continue
        ic = p.conditions.get("IC")
        out.append((ic.to_pint().m_as("A") if ic is not None else None, p))
    return out


def bjt_model(
    rec: ComponentRecord | None,
    ic_op: float,
    vbe_assumed: pint.Quantity,
    beta_ideal: float,
    log: CalcLog,
    designator: str,
) -> tuple[Bjt, list[str]]:
    """Model of a chosen transistor near the operating current ``ic_op`` (A).

    Without a record (ideal pass) BF is the design value ``beta_ideal``. With a record, BF is
    the hFE entry tested nearest (log scale) to ``ic_op``: typical value, else the geometric
    mean of minimum and maximum, else the only limit given. IS makes |VBE| = ``vbe_assumed`` at
    that test current.
    """
    warnings: list[str] = []
    vbe0 = vbe_assumed.m_as("V")
    pnp = rec is not None and rec.category.startswith("bjt.pnp")
    if rec is None:
        bf, ic_t = beta_ideal, max(ic_op, 1e-6)
        how = "premissa de projeto (sem componente escolhido)"
        inputs: dict[str, pint.Quantity] = {}
        latex = r"\beta_F = \beta_{projeto}"
    else:
        entries = hfe_entries(rec)
        if not entries:
            raise ValueError(f"{rec.part_number}: datasheet sem hFE")
        known = [(ic, p) for ic, p in entries if ic is not None]
        if known and ic_op > 0:
            ic_k, p = min(known, key=lambda e: abs(math.log((e[0] or 1.0) / ic_op)))
            ic_t = float(ic_k or ic_op)
        else:
            ic_0, p = entries[0]
            ic_t = float(ic_0 or max(ic_op, 1e-6))
        if p.typ is not None:
            bf, how, latex = float(p.typ), "hFE típico do datasheet", r"\beta_F = h_{FE,typ}"
        elif p.min is not None and p.max is not None:
            bf = math.sqrt(p.min * p.max)
            how, latex = (
                "média geométrica de hFE mín. e máx.",
                r"\beta_F = \sqrt{h_{FE,min}\,h_{FE,max}}",
            )
        else:
            bf = value(p, ("min", "max"))
            how, latex = "único limite de hFE do datasheet", r"\beta_F = h_{FE,lim}"
            warnings.append(f"{designator}: o datasheet só dá um limite de hFE; BF = {bf:g}.")
        inputs = {
            k: Q_(v, "")
            for k, v in (("h_{FE,min}", p.min), ("h_{FE,typ}", p.typ), ("h_{FE,max}", p.max))
            if v is not None
        }
        inputs["I_{C,ensaio}"] = Q_(ic_t, "A").to("mA")
    log.add(
        record(
            f"BF_{designator}",
            f"Ganho de corrente do modelo de {designator}"
            + (f" ({rec.part_number})" if rec else ""),
            latex,
            output=Q_(bf, ""),
            inputs=inputs,
            assumptions=[how, "β constante na faixa de corrente do projeto"],
            reference=BOYLESTAD,
        )
    )
    is_ = ic_t / (math.exp(vbe0 / VT_300K) - 1.0)
    log.add(
        record(
            f"IS_{designator}",
            f"Corrente de saturação do modelo de {designator}",
            r"I_S = \frac{I_{C,ensaio}}{e^{V_{BE}/V_T} - 1}",
            output=Q_(is_, "A"),
            inputs={
                "I_{C,ensaio}": Q_(ic_t, "A").to("mA"),
                "V_{BE}": vbe_assumed.to("V"),
                "V_T": Q_(VT_300K, "V"),
            },
            assumptions=[
                "V_BE na corrente de ensaio do hFE é premissa do projeto (o datasheet não dá "
                "V_BE(on) nessa corrente)",
                "T = 27 °C, temperatura nominal do SPICE",
            ],
            reference=SEDRA,
        )
    )
    return Bjt(IS=is_, BF=bf, pnp=pnp), warnings


# ------------------------------------------------------------------------------ Darlington


@dataclass(frozen=True)
class Darlington:
    """Monolithic Darlington as two Ebers-Moll transistors: Q1 drives the base of Q2.

    The internal base-emitter shunt resistors of power Darlingtons are not modelled (their
    values are only in the datasheet drawing, without tolerance); they matter at low current.
    """

    q1: Bjt
    q2: Bjt

    @property
    def pnp(self) -> bool:
        return self.q1.pnp

    @property
    def BF(self) -> float:
        """Composite forward gain IC/IB = β1β2 + β1 + β2."""
        b1, b2 = self.q1.BF, self.q2.BF
        return b1 * b2 + b1 + b2

    def split(self, vbe: float) -> float:
        """VBE of Q2 for a composite |VBE| in forward-active operation (IE1 = IB2)."""

        def f(v2: float) -> float:
            ib2 = self.q2.IS * math.expm1(min(v2 / VT_300K, 200)) / self.q2.BF
            return self.q1.ie(vbe - v2) - ib2

        return float(brentq(f, vbe / 2 - 1.0, vbe / 2 + 1.0, xtol=1e-15, rtol=1e-14))

    def ic(self, vbe: float) -> float:
        v2 = self.split(vbe)
        return self.q1.ic(vbe - v2) + self.q2.ic(v2)

    def ie(self, vbe: float) -> float:
        return self.q2.ie(self.split(vbe))

    def vbe(self, ic: float) -> float:
        return float(brentq(lambda v: self.ic(v) - ic, 0.0, 4.0, xtol=1e-15, rtol=1e-14))

    def subckt(self, name: str) -> str:
        """SPICE subcircuit ``name c b e`` with the two transistor models."""
        return "\n".join(
            [
                self.q1.spice(f"{name}_Q1M"),
                self.q2.spice(f"{name}_Q2M"),
                f".subckt {name} c b e",
                f"Q1 c b m {name}_Q1M",
                f"Q2 c m e {name}_Q2M",
                ".ends",
            ]
        )


def is_darlington(rec: ComponentRecord) -> bool:
    """A part whose minimum hFE is in the thousands is a Darlington (two junctions)."""
    return any((p.min or 0) >= 500 for _, p in hfe_entries(rec))


def darlington_model(
    rec: ComponentRecord | None,
    ic_op: float,
    vbe_assumed: pint.Quantity,
    beta_ideal: float,
    log: CalcLog,
    designator: str,
) -> tuple[Darlington, list[str]]:
    """Two equal-β transistors whose composite gain is the datasheet hFE near ``ic_op``.

    β of each transistor from hFE = β² + 2β (β1 = β2 = β). IS of each makes its VBE equal to
    ``vbe_assumed`` (per junction) at the hFE test current, so the composite VBE there is
    2·vbe_assumed; the datasheet VBE(on) (a maximum at high current) is logged for comparison.
    """
    warnings: list[str] = []
    v0 = vbe_assumed.m_as("V")
    pnp = rec is not None and rec.category.startswith("bjt.pnp")
    if rec is None:
        hfe, ic_t, how = beta_ideal, max(ic_op, 1e-6), "premissa de projeto (sem componente)"
        inputs: dict[str, pint.Quantity] = {}
    else:
        entries = [(i, p) for i, p in hfe_entries(rec) if i is not None] or hfe_entries(rec)
        ic_k, p = min(entries, key=lambda e: abs(math.log((e[0] or ic_op) / max(ic_op, 1e-9))))
        ic_t = float(ic_k or ic_op)
        if p.typ is not None:
            hfe, how = float(p.typ), "hFE típico do datasheet"
        elif p.min is not None and p.max is not None:
            hfe, how = math.sqrt(p.min * p.max), "média geométrica de hFE mín. e máx."
        else:
            hfe, how = value(p, ("min", "max")), "único limite de hFE do datasheet (mínimo)"
            warnings.append(
                f"{designator}: o datasheet só dá hFE mínimo ({hfe:g}); o modelo usa esse valor "
                "(ganho real maior: corrente de base sobra)."
            )
        inputs = {"h_{FE}": Q_(hfe, ""), "I_{C,ensaio}": Q_(ic_t, "A")}
    beta = math.sqrt(hfe + 1.0) - 1.0
    log.add(
        record(
            f"BF_{designator}",
            f"Ganho de cada transistor do Darlington {designator}"
            + (f" ({rec.part_number})" if rec else ""),
            r"h_{FE} = \beta_1\beta_2 + \beta_1 + \beta_2,\; \beta_1 = \beta_2 "
            r"\Rightarrow \beta = \sqrt{h_{FE} + 1} - 1",
            output=Q_(beta, ""),
            inputs=inputs,
            assumptions=[how, "os dois transistores com o mesmo β"],
            reference=BOYLESTAD.model_copy(update={"chapter": "5 (Darlington connection)"}),
        )
    )
    ib1 = ic_t / hfe
    ic1 = beta * ib1
    ic2 = beta * (beta + 1) * ib1
    e = math.expm1(v0 / VT_300K)
    q1 = Bjt(IS=ic1 / e, BF=beta, pnp=pnp)
    q2 = Bjt(IS=ic2 / e, BF=beta, pnp=pnp)
    vbe_on = rec.parameters.get("VBE(on)") if rec else None
    log.add(
        record(
            f"IS_{designator}",
            f"Correntes de saturação do Darlington {designator} (Q2, saída)",
            r"I_{S2} = \frac{\beta(\beta+1)\,I_{C,ensaio}/h_{FE}}{e^{V_{BE}/V_T} - 1},\;"
            r"I_{S1} = I_{S2}/(\beta + 1)",
            output=Q_(q2.IS, "A"),
            inputs={"V_{BE}": vbe_assumed.to("V"), "I_{C,ensaio}": Q_(ic_t, "A")}
            | (
                {"V_{BE(on),ds}": Q_(value(vbe_on, ("max", "typ")), parse_unit(vbe_on.unit))}
                if vbe_on is not None and vbe_on.has_value
                else {}
            ),
            assumptions=[
                "V_BE de cada junção na corrente de ensaio é premissa do projeto; V_BE do "
                "conjunto = 2 V_BE",
                "resistores internos de base-emissor não modelados",
            ],
            reference=SEDRA,
        )
    )
    return Darlington(q1, q2), warnings


# ------------------------------------------------------------------------------------ JFET


@dataclass(frozen=True)
class Jfet:
    """N-channel JFET, Shockley's equation (SPICE NJF level 1 with λ = 0)."""

    IDSS: float  # A
    VP: float  # V, magnitude of the pinch-off voltage (VGS(off) = −VP)
    CGS: float = 0.0  # F, constant
    CGD: float = 0.0  # F, constant

    @property
    def BETA(self) -> float:
        return self.IDSS / self.VP**2

    def id_sat(self, vgs: float) -> float:
        """ID = IDSS(1 − VGS/VGS(off))², zero below cut-off."""
        return 0.0 if vgs <= -self.VP else self.IDSS * (1 + vgs / self.VP) ** 2

    def gm(self, vgs: float) -> float:
        return 0.0 if vgs <= -self.VP else 2 * self.IDSS / self.VP * (1 + vgs / self.VP)

    def spice(self, name: str) -> str:
        # PB very large: constant junction capacitances, as in the analysis
        caps = f" CGS={self.CGS:.6g} CGD={self.CGD:.6g} PB=1e6" if self.CGS or self.CGD else ""
        return f".model {name} NJF(VTO={-self.VP:.6g} BETA={self.BETA:.6g} LAMBDA=0{caps})"


def jfet_model(
    rec: ComponentRecord | None,
    log: CalcLog,
    designator: str,
    idss_ideal: float = 4e-3,
    vp_ideal: float = 2.0,
) -> tuple[Jfet, list[str]]:
    """IDSS typical (else geometric mean of the range); VP from the transconductance at VGS = 0.

    gm0 = 2·IDSS/|VP| (Boylestad, 11th ed., ch. 8, FET small-signal analysis), so |VP| =
    2·IDSS/|yfs| with yfs typical (else the geometric mean); the result is checked against the
    VGS(off) range of the datasheet.
    """
    warnings: list[str] = []
    if rec is None:
        log.add(
            record(
                f"VP_{designator}",
                f"JFET {designator}: premissas do passo ideal",
                r"I_{DSS},\ |V_P| \text{ de projeto}",
                output=Q_(vp_ideal, "V"),
                inputs={"I_{DSS}": Q_(idss_ideal, "A").to("mA")},
            )
        )
        return Jfet(idss_ideal, vp_ideal), warnings

    def central(key: str, unit: str) -> tuple[float, str]:
        p = rec.parameters.get(key)
        if p is None or not p.has_value:
            raise ValueError(f"{rec.part_number}: datasheet sem {key}")
        u = parse_unit(p.unit)
        if p.typ is not None:
            return Q_(p.typ, u).m_as(unit), "típico"
        if p.min is not None and p.max is not None:
            return Q_(math.sqrt(p.min * p.max), u).m_as(unit), "média geométrica de mín. e máx."
        return Q_(value(p, ("min", "max")), u).m_as(unit), "único limite"

    idss, how_i = central("IDSS", "A")
    gm0, how_g = central("yfs", "S")
    vp = 2 * idss / gm0
    log.add(
        record(
            f"IDSS_{designator}",
            f"IDSS do modelo de {designator} ({rec.part_number})",
            r"I_{DSS} = I_{DSS,ds}",
            output=Q_(idss, "A").to("mA"),
            assumptions=[how_i],
            reference=BOYLESTAD.model_copy(update={"chapter": "6 (Shockley's equation)"}),
        )
    )
    log.add(
        record(
            f"VP_{designator}",
            f"Tensão de estrangulamento do modelo de {designator}",
            r"|V_P| = \frac{2 I_{DSS}}{g_{m0}},\; g_{m0} = |y_{fs}|",
            output=Q_(vp, "V"),
            inputs={"I_{DSS}": Q_(idss, "A").to("mA"), "g_{m0}": Q_(gm0, "S").to("mS")},
            assumptions=[f"|yfs| {how_g}", "lei quadrática de Shockley (a mesma do SPICE)"],
            reference=BOYLESTAD.model_copy(update={"chapter": "8 (FET amplifiers: gm0)"}),
        )
    )
    off = rec.parameters.get("VGS(off)")
    if off is not None and off.has_value:
        u = parse_unit(off.unit)
        lo = Q_(off.min, u).m_as("V") if off.min is not None else 0.0
        hi = Q_(off.max, u).m_as("V") if off.max is not None else math.inf
        if not lo <= vp <= hi:
            warnings.append(
                f"{designator}: |VP| = {vp:.3g} V do modelo fica fora da faixa de VGS(off) do "
                f"datasheet ({lo:g} a {hi:g} V)."
            )
    cgs = cgd = 0.0
    ciss, crss = rec.parameters.get("Ciss"), rec.parameters.get("Crss")
    if ciss is not None and crss is not None and ciss.has_value and crss.has_value:
        cgd = Q_(value(crss), parse_unit(crss.unit)).m_as("F")
        cgs = Q_(value(ciss), parse_unit(ciss.unit)).m_as("F") - cgd
    return Jfet(idss, vp, cgs, cgd), warnings


# ---------------------------------------------------------------------------------- Zener


@dataclass(frozen=True)
class ZenerPwl:
    VZ: float  # V at IZT
    IZT: float  # A
    rz: float  # ohm
    IZK: float | None  # A

    @property
    def VZ0(self) -> float:
        return self.VZ - self.IZT * self.rz

    def spice_subckt(self, name: str = "ZPWL") -> str:
        """Same piecewise-linear model for the simulator (cathode first: current k → a)."""
        return "\n".join(
            [
                f".subckt {name} k a",
                f"BZ k a I = (v(k,a) > {self.VZ0:.9g}) ? (v(k,a) - {self.VZ0:.9g}) / "
                f"{self.rz:.9g} : v(k,a) * 1n",
                ".ends",
            ]
        )


def zener_pwl(rec: ComponentRecord, log: CalcLog, designator: str) -> tuple[ZenerPwl, list[str]]:
    warnings: list[str] = []
    vz_p = rec.parameters.get("VZ")
    zzt_p = rec.parameters.get("ZZT")
    izt_p = rec.parameters.get("IZT")
    if vz_p is None or not vz_p.has_value or zzt_p is None or not zzt_p.has_value:
        raise ValueError(f"{rec.part_number}: datasheet sem VZ ou ZZT")
    vz = Q_(value(vz_p), parse_unit(vz_p.unit)).m_as("V")
    if izt_p is not None and izt_p.has_value:
        izt = Q_(value(izt_p), parse_unit(izt_p.unit)).m_as("A")
    else:
        izt = vz_p.conditions["IZ"].to_pint().m_as("A")
    rz = Q_(value(zzt_p, ("typ", "max")), parse_unit(zzt_p.unit)).m_as("ohm")
    if zzt_p.typ is None:
        warnings.append(f"{designator}: ZZT do datasheet é máximo; o modelo usa esse valor.")
    izk_q = quantity(rec, "IZK")
    pwl = ZenerPwl(vz, izt, rz, izk_q.m_as("A") if izk_q is not None else None)
    log.add(
        record(
            f"VZ0_{designator}",
            f"Modelo linear por partes de {designator} ({rec.part_number})",
            r"V_Z = V_{Z0} + r_z I_Z;\quad r_z = Z_{ZT},\; V_{Z0} = V_Z - I_{ZT} Z_{ZT}",
            output=Q_(pwl.VZ0, "V"),
            inputs={"V_Z": Q_(vz, "V"), "I_{ZT}": Q_(izt, "A").to("mA"), "Z_{ZT}": Q_(rz, "ohm")},
            assumptions=[
                "segunda aproximação do Zener (fonte V_Z0 em série com r_z)",
                "Z_ZT do datasheet medida em pequenos sinais a 1 kHz, usada como inclinação CC",
            ],
            reference=BOYLESTAD,
        )
    )
    return pwl, warnings


# ---------------------------------------------------------------------------------- MOSFET


@dataclass(frozen=True)
class Mos:
    """Square-law N-MOSFET (SPICE level 1, W = L, λ = 0 in the designs)."""

    VT: float  # V
    KP: float  # A/V²

    def id_sat(self, vgs: float) -> float:
        return 0.0 if vgs <= self.VT else self.KP / 2 * (vgs - self.VT) ** 2

    def spice(self, name: str) -> str:
        return f".model {name} NMOS(LEVEL=1 VTO={self.VT:.6g} KP={self.KP:.6g} LAMBDA=0)"


def mos_model(
    rec: ComponentRecord | None,
    log: CalcLog,
    designator: str,
    vt_ideal: float = 3.0,
    kp_ideal: float = 1.0,
) -> tuple[Mos, list[str]]:
    """VT = middle of the VGS(th) range; KP from RDS(on) in deep triode (as on the FET bench)."""
    warnings: list[str] = []
    if rec is None:
        log.add(
            record(
                f"VT_{designator}",
                f"Limiar de {designator}: premissa do passo ideal",
                r"V_T = V_{T,projeto}",
                output=Q_(vt_ideal, "V"),
            )
        )
        return Mos(vt_ideal, kp_ideal), warnings
    vth = rec.parameters.get("VGS(th)")
    rds = rec.parameters.get("RDS(on)")
    if vth is None or vth.min is None or vth.max is None:
        raise ValueError(f"{rec.part_number}: datasheet sem VGS(th) mín. e máx.")
    if rds is None or rds.max is None or "VGS" not in rds.conditions:
        raise ValueError(f"{rec.part_number}: datasheet sem RDS(on) com VGS de ensaio")
    vt = Q_((vth.min + vth.max) / 2, parse_unit(vth.unit)).m_as("V")
    log.add(
        record(
            f"VT_{designator}",
            f"Tensão de limiar do modelo de {designator} ({rec.part_number})",
            r"V_T = \frac{V_{GS(th),min} + V_{GS(th),max}}{2}",
            output=Q_(vt, "V"),
            inputs={
                "V_{GS(th),min}": Q_(vth.min, parse_unit(vth.unit)),
                "V_{GS(th),max}": Q_(vth.max, parse_unit(vth.unit)),
            },
            assumptions=["ponto médio da faixa do datasheet (não há valor típico)"],
            reference=SEDRA,
        )
    )
    r_on = Q_(rds.max, parse_unit(rds.unit)).m_as("ohm")
    vgs = rds.conditions["VGS"].to_pint().m_as("V")
    kp = 1 / (r_on * (vgs - vt))
    log.add(
        record(
            f"KP_{designator}",
            f"Transcondutância do modelo de {designator} a partir de RDS(on)",
            r"K_P = \frac{1}{R_{DS(on)}\,(V_{GS} - V_T)}",
            output=Q_(kp, "A/V**2"),
            inputs={"R_{DS(on)}": Q_(r_on, "ohm"), "V_{GS}": Q_(vgs, "V"), "V_T": Q_(vt, "V")},
            assumptions=[
                "modelo quadrático (nível 1), triodo profundo no ensaio de RDS(on)",
                "RDS(on) máximo do datasheet: KP conservador",
            ],
            reference=SEDRA,
        )
    )
    warnings.append(
        f"{designator}: o modelo quadrático de um MOSFET de potência é didático; a corrente "
        "real em VGS próximo do limiar pode diferir bastante."
    )
    return Mos(vt, kp), warnings
