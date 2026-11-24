"""DM-FIL: filter synthesis (Butterworth, Chebyshev, Bessel, elliptic), active and passive.

Approximation, order and decomposition in ``design/filters.py``. Each section is then built:

* first order: RC (or CR) and a follower;
* Sallen-Key unity gain, low-pass: H = 1/(s²R1R2C1C2 + sC2(R1 + R2) + 1), so with C2 (to
  ground) and C1 (feedback) fixed, R1 + R2 = 1/(Q ω0 C2) and R1R2 = 1/(ω0² C1 C2), real if
  C1 ≥ 4Q²C2; high-pass with equal capacitors: R_g = 2Q/(ω0C), R_fb = 1/(2Qω0C);
* multiple feedback (MFB) low-pass and band-pass (Mancini (ed.), *Op Amps for Everyone*, Texas
  Instruments, 2002, ch. 16 "Active filter design techniques", T. Kugelstadt);
* state variable (KHN) biquad with a summing amplifier for sections with finite zeros
  (elliptic, notch): v_hp = K s²/D, v_bp = −K ω0 s/D, v_lp = K ω0²/D with ω0 = 1/(RC),
  1/Q = 2R2/(R2 + R3), K = 2 − 1/Q (Sedra & Smith, 7th ed., ch. 17 "Filters and tuned
  amplifiers", KHN biquad, derived here for this connection);
* doubly terminated LC ladder (g_k values of ``filters.ladder_g``).

Component values are rounded to the series and the response is recomputed: the realised
filter, with the op-amp macromodel, is solved by nodal analysis at each frequency (the same
circuit as the ``.ac`` netlist), and compared with the ideal approximation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pint
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.eseries import SeriesName, snap
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.base import Circuit, DesignResult, DesignWarning, Role, SimCheck, Trace
from circuitos.design.engine import Analysis, Device
from circuitos.design.filters import (
    Approx,
    Kind,
    Section,
    ladder_g,
    min_order,
    normalise,
    prototype,
    response,
    sections,
    transform,
)
from circuitos.design.mna import Circuit as Mna
from circuitos.design.opamp import REF as OPA_REF
from circuitos.design.opamp import OpAmp, gbw_of, opamp_model
from circuitos.design.smallsignal import corner, log_grid
from circuitos.reports import drawings_filter
from circuitos.reports.common import BomRow, LabItem, passive

Real = Literal["sallen_key", "mfb", "variaveis_estado", "passivo_lc"]
WT = BibRef(book="Williams & Taylor, Electronic Filter Design Handbook", edition="4th", chapter="2")
KUG = BibRef(
    book="Mancini (ed.), Op Amps for Everyone (Texas Instruments)",
    edition="2002",
    chapter="16 (Active filter design techniques)",
)
MYJ = BibRef(
    book="Matthaei, Young & Jones, Microwave Filters, Impedance-Matching Networks, and Coupling "
    "Structures",
    edition="1964",
    chapter="4",
)
PPD = 40


class FilSpec(BaseModel):
    kind: Kind = "passa_baixas"
    approx: Approx = "butterworth"
    realization: Real = "sallen_key"
    fp: QuantityModel = QuantityModel(value=1, unit="kHz")  # passband edge (LP/HP) or centre
    B: QuantityModel = QuantityModel(value=200, unit="Hz")  # bandwidth (BP/BS)
    f_stop: QuantityModel = QuantityModel(value=3, unit="kHz")  # stopband edge
    A_stop: float = Field(default=30, gt=3, le=120)  # dB at f_stop
    ripple_db: float = Field(default=1.0, gt=0.001, le=3)  # Chebyshev / elliptic passband
    order: int = Field(default=0, ge=0, le=12)  # 0 = smallest that meets f_stop/A_stop
    C_base: QuantityModel = QuantityModel(value=10, unit="nF")
    R_base: QuantityModel = QuantityModel(value=10, unit="kohm")  # KHN and summing resistors
    R0: QuantityModel = QuantityModel(value=600, unit="ohm")  # LC ladder terminations
    cap_series: SeriesName = "E12"
    res_series: SeriesName = "E96"
    VCC: QuantityModel = QuantityModel(value=15, unit="V")
    TA: QuantityModel = QuantityModel(value=25, unit="degC")


LABELS = {
    "n": "Ordem",
    "n_opamps": "Número de ampops",
    "f_ref": "Frequência de referência (borda; centro no passa-faixa; borda superior no "
    "rejeita-faixa)",
    "G_ref": "Ganho na borda/centro (projeto)",
    "G_ref_ideal": "Ganho na borda/centro (aproximação ideal)",
    "G_stop": "Ganho na frequência de rejeição (projeto)",
    "A_stop_real": "Atenuação na frequência de rejeição (projeto)",
    "A_stop_ideal": "Atenuação na frequência de rejeição (ideal)",
    "f_3dB": "Corte −3 dB (projeto)",
    "f_3dB_ideal": "Corte −3 dB (ideal)",
    "f_dev": "Desvio do corte pelo arredondamento e pelo ampop",
    "f_L": "Corte inferior −3 dB (projeto)",
    "f_H": "Corte superior −3 dB (projeto)",
    "G_pass": "Ganho na banda passante (projeto)",
}
SPEC_LABELS = {
    "kind": "Tipo",
    "approx": "Aproximação",
    "realization": "Realização",
    "fp": "Borda da banda passante (ou centro)",
    "B": "Largura de banda (passa/rejeita-faixa)",
    "f_stop": "Frequência de rejeição",
    "A_stop": "Atenuação mínima na rejeição (dB)",
    "ripple_db": "Ondulação na banda passante (dB)",
    "order": "Ordem (0 = automática)",
    "C_base": "Capacitor de base",
    "R_base": "Resistor de base (KHN e somador)",
    "R0": "Terminações da escada LC",
    "cap_series": "Série dos capacitores",
    "res_series": "Série dos resistores",
    "VCC": "Alimentação dos ampops (±)",
}
ENUM_LABELS = {
    "passa_baixas": "passa-baixas",
    "passa_altas": "passa-altas",
    "passa_faixa": "passa-faixa",
    "rejeita_faixa": "rejeita-faixa",
    "butterworth": "Butterworth",
    "chebyshev": "Chebyshev",
    "bessel": "Bessel",
    "eliptico": "elíptico (Cauer)",
    "sallen_key": "Sallen-Key",
    "mfb": "realimentação múltipla (MFB)",
    "variaveis_estado": "variáveis de estado (KHN)",
    "passivo_lc": "passivo LC (escada)",
    "E6": "E6",
    "E12": "E12",
    "E24": "E24",
    "E48": "E48",
    "E96": "E96",
    "E3": "E3",
    "E192": "E192",
}


def _spec(spec: BaseModel) -> FilSpec:
    if not isinstance(spec, FilSpec):
        raise TypeError("DM-FIL espera FilSpec")
    return spec


class Builder:
    """Accumulates the realised circuit, part values and op-amp count."""

    def __init__(self, s: FilSpec, op: OpAmp):
        self.c = Mna()
        self.s = s
        self.op = op
        self.parts: list[tuple[str, str, float]] = []  # (designator, kind R/C/L, value)
        self.nodes: dict[str, tuple[str, str]] = {}  # designator → its two nodes
        # (section kind, its index k, the section) in cascade order, for the drawing
        self.layout: list[tuple[str, int, Section]] = []
        self.n_op = 0
        self.nr = 0
        self.nc = 0
        self.nl = 0

    def r(self, a: str, b: str, val: float, series: bool = True) -> float:
        v = float(snap(Q_(val, "ohm"), self.s.res_series, "nearest").m_as("ohm")) if series else val
        self.nr += 1
        self.c.R(str(self.nr), a, b, v)
        self.parts.append((f"R{self.nr}", "R", v))
        self.nodes[f"R{self.nr}"] = (a, b)
        return v

    def cap(self, a: str, b: str, val: float) -> float:
        self.nc += 1
        self.c.C(str(self.nc), a, b, val)
        self.parts.append((f"C{self.nc}", "C", val))
        self.nodes[f"C{self.nc}"] = (a, b)
        return val

    def ind(self, a: str, b: str, val: float) -> float:
        v = float(snap(Q_(val, "H"), self.s.cap_series, "nearest").m_as("H"))
        self.nl += 1
        self.c.L(str(self.nl), a, b, v)
        self.parts.append((f"L{self.nl}", "L", v))
        self.nodes[f"L{self.nl}"] = (a, b)
        return v

    def snap_c(self, val: float, mode: str = "nearest") -> float:
        return float(snap(Q_(val, "F"), self.s.cap_series, mode).m_as("F"))  # type: ignore[arg-type]

    def opamp(self, inp: str, inn: str, out: str) -> None:
        self.n_op += 1
        self.op.add(self.c, f"U{self.n_op}", inp, inn, out)


def _sk_lp(b: Builder, sec: Section, a: str, o: str, k: int) -> None:
    c2 = b.snap_c(b.s.C_base.to_pint().m_as("F"))
    c1 = b.snap_c(4 * sec.Q**2 * c2 * 1.05, "up")
    ssum = 1 / (sec.Q * sec.w0 * c2)
    prod = 1 / (sec.w0**2 * c1 * c2)
    disc = math.sqrt(max(ssum**2 - 4 * prod, 0.0))
    m, x = f"m{k}", f"x{k}"
    b.r(a, m, (ssum + disc) / 2)
    b.r(m, x, (ssum - disc) / 2)
    b.cap(m, o, c1)
    b.cap(x, "0", c2)
    b.opamp(x, o, o)


def _sk_hp(b: Builder, sec: Section, a: str, o: str, k: int) -> None:
    c = b.snap_c(b.s.C_base.to_pint().m_as("F"))
    m, x = f"m{k}", f"x{k}"
    b.cap(a, m, c)
    b.cap(m, x, c)
    b.r(m, o, 1 / (2 * sec.Q * sec.w0 * c))
    b.r(x, "0", 2 * sec.Q / (sec.w0 * c))
    b.opamp(x, o, o)


def _mfb_lp(b: Builder, sec: Section, a: str, o: str, k: int) -> None:
    gain = sec.n0 / sec.w0**2
    c1 = b.snap_c(b.s.C_base.to_pint().m_as("F"))
    c2 = b.snap_c(4 * (1 + gain) * sec.Q**2 * c1 * 1.05, "up")
    disc = math.sqrt(max(c2**2 / sec.Q**2 - 4 * c1 * c2 * (1 + gain), 0.0))
    r2 = (c2 / sec.Q - disc) / (2 * sec.w0 * c1 * c2)
    r3 = 1 / (sec.w0**2 * c1 * c2 * r2)
    m, n = f"m{k}", f"n{k}"
    b.r(a, m, r2 / gain)  # R1
    b.r(m, o, r2)  # R2
    b.r(m, n, r3)  # R3
    b.cap(n, o, c1)
    b.cap(m, "0", c2)
    b.opamp("0", n, o)


def _mfb_bp(b: Builder, sec: Section, a: str, o: str, k: int) -> None:
    am = sec.n1 * sec.Q / sec.w0  # centre gain magnitude
    if am >= 2 * sec.Q**2:
        _khn(b, sec, a, o, k)
        return
    c = b.snap_c(b.s.C_base.to_pint().m_as("F"))
    r2 = 2 * sec.Q / (sec.w0 * c)
    r1 = r2 / (2 * am)
    r3 = am * r1 / (2 * sec.Q**2 - am)
    m, n = f"m{k}", f"n{k}"
    b.r(a, m, r1)
    b.r(m, "0", r3)
    b.cap(m, n, c)
    b.cap(m, o, c)
    b.r(n, o, r2)
    b.opamp("0", n, o)


def _khn(b: Builder, sec: Section, a: str, o: str, k: int) -> None:
    """State-variable biquad + summing amplifier: vo = −(n2 s² + n1 s + n0)/D."""
    c = b.snap_c(b.s.C_base.to_pint().m_as("F"))
    rb = b.s.R_base.to_pint().m_as("ohm")
    r = 1 / (sec.w0 * c)
    q = max(sec.Q, 0.51)
    hp, bp, lp, p1, n1, n2, n3, n4 = (
        f"{t}{k}" for t in ("hp", "bp", "lp", "p", "na", "nb", "nc", "nd")
    )
    rr = b.r(lp, n1, rb)
    b.r(n1, hp, rr, series=False)
    r2 = b.r(a, p1, rb)
    r3 = b.r(bp, p1, rb * (2 * q - 1))
    b.opamp(p1, n1, hp)
    b.r(hp, n2, r)
    b.cap(n2, bp, c)
    b.opamp("0", n2, bp)
    b.r(bp, n3, r)
    b.cap(n3, lp, c)
    b.opamp("0", n3, lp)
    # summing weights from the design ω0: the rounded integrators move ω0 and the zero
    # together and the gain where the section passes stays as designed
    w0 = sec.w0
    gk = 2 * r3 / (r2 + r3)
    rf = b.r(n4, o, rb)
    if sec.n2:
        b.r(hp, n4, rf * gk / sec.n2)
    if sec.n1:
        b.r(bp, n4, rf * gk * w0 / sec.n1)
    if sec.n0:
        b.r(lp, n4, rf * gk * w0**2 / sec.n0)
    b.opamp("0", n4, o)


def _first(b: Builder, sec: Section, a: str, o: str, k: int) -> None:
    c = b.snap_c(b.s.C_base.to_pint().m_as("F"))
    x = f"x{k}"
    if sec.kind == "lp1":
        b.r(a, x, 1 / (sec.w0 * c))
        b.cap(x, "0", c)
    else:
        b.cap(a, x, c)
        b.r(x, "0", 1 / (sec.w0 * c))
    b.opamp(x, o, o)


def build_active(b: Builder, secs: list[Section]) -> str:
    b.c.V("sig", "in", "0", 0.0, 1.0)
    node = "in"
    for k, sec in enumerate(secs, 1):
        out = f"o{k}"
        real = b.s.realization
        n_op = b.n_op
        if sec.order == 1:
            _first(b, sec, node, out, k)
            kind = sec.kind
        elif sec.kind == "notch" or real == "variaveis_estado":
            _khn(b, sec, node, out, k)
            kind = "khn"
        elif sec.kind == "lp":
            (_mfb_lp if real == "mfb" else _sk_lp)(b, sec, node, out, k)
            kind = "mfb_lp" if real == "mfb" else "sk_lp"
        elif sec.kind == "hp":
            _sk_hp(b, sec, node, out, k)
            kind = "sk_hp"
        else:  # band-pass section (state variable when the MFB cannot give the gain)
            _mfb_bp(b, sec, node, out, k)
            kind = "khn" if b.n_op - n_op > 1 else "mfb_bp"
        b.layout.append((kind, k, sec))
        node = out
    return node


def build_ladder(b: Builder, g: list[float], kind: Kind, wc: float) -> str:
    r0 = b.s.R0.to_pint().m_as("ohm")
    b.c.V("sig", "in", "0", 0.0, 1.0)
    b.r("in", "n1", r0, series=False)
    node = "n1"
    for k, gk in enumerate(g, 1):
        shunt = k % 2 == 1
        if kind == "passa_baixas":
            if shunt:
                b.cap(node, "0", b.snap_c(gk / (r0 * wc)))
            else:
                nxt = f"n{k}"
                b.ind(node, nxt, gk * r0 / wc)
                node = nxt
        else:
            if shunt:
                b.ind(node, "0", r0 / (gk * wc))
            else:
                nxt = f"n{k}"
                b.cap(node, nxt, b.snap_c(1 / (gk * r0 * wc)))
                node = nxt
    b.r(node, "0", r0, series=False)
    return node


class FilModule:
    id = "DM-FIL"
    family = "ampops"
    title = "Filtros ativos e passivos"
    spec_schema = FilSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Ganho na borda da banda passante", "gerador + osciloscópio", "G_ref"),
        LabItem("Atenuação na frequência de rejeição", "gerador + osciloscópio", "A_stop_real"),
        LabItem("Frequência de corte −3 dB", "varredura de frequência", "f_3dB"),
    ]
    questions = [
        "Compare Butterworth, Chebyshev e Bessel de mesma ordem: banda de transição e "
        "ondulação. Qual tem a melhor resposta ao degrau?",
        "Quanto o arredondamento dos capacitores para a série deslocou o corte? Por quê?",
        "Por que o GBW do ampop limita o fator Q das seções Sallen-Key?",
    ]
    practice = {
        "objective": "Montar o filtro, levantar a resposta em frequência e compará-la com a "
        "aproximação ideal e com o projeto.",
        "material": "Fonte simétrica, gerador de funções, osciloscópio, ampops, resistores e "
        "capacitores (de preferência filme) da lista de materiais.",
        "procedure": [
            "Monte uma seção por vez e confira o ganho de cada uma em ω0.",
            "Ligue as seções em cascata, da de menor Q para a de maior Q.",
            "Varra a frequência e registre o ganho em dB; marque o corte e a rejeição.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        if s.realization == "passivo_lc":
            return []
        return [Role(designator="U1", category="opamp", description="Ampops (todos iguais)")]

    def required_ratings(self, role: Role) -> list[str]:
        return []

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        s = _spec(spec)
        vs = s.VCC.to_pint().m_as("V")
        sym, tot = rec.parameters.get("VS_max"), rec.parameters.get("VS_total_max")
        return (sym is not None and (sym.max or 0) >= vs) or (
            tot is not None and (tot.max or 0) >= 2 * vs
        )

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        return -gbw_of(rec)  # the widest GBW keeps the section Q closest to the design

    # ------------------------------------------------------------------ design
    @staticmethod
    def f_ref(s: FilSpec) -> float:
        """Where the gain is checked: the edge (LP/HP), the centre (BP), the upper edge (BS)."""
        fp = s.fp.to_pint().m_as("Hz")
        if s.kind != "rejeita_faixa":
            return float(fp)
        bw = s.B.to_pint().m_as("Hz")
        return float(bw / 2 + math.sqrt(bw**2 / 4 + fp**2))

    def _plan(self, s: FilSpec, log: CalcLog) -> tuple[int, list[Section], float, float]:
        fp = s.fp.to_pint().m_as("Hz")
        fs = s.f_stop.to_pint().m_as("Hz")
        bw = s.B.to_pint().m_as("Hz")
        if s.approx == "eliptico" and s.kind == "passa_faixa":
            raise ValueError(
                "Passa-faixa elíptico não implementado (use passa/rejeita-faixa "
                "com outra aproximação ou elíptico em PB/PA)"
            )
        if s.realization == "passivo_lc" and s.kind not in ("passa_baixas", "passa_altas"):
            raise ValueError("Escada LC só para passa-baixas e passa-altas")
        if s.kind == "passa_baixas":
            ratio = fs / fp
        elif s.kind == "passa_altas":
            ratio = fp / fs
        elif s.kind == "passa_faixa":
            ratio = abs(fs**2 - fp**2) / (fs * bw)
        else:
            ratio = fs * bw / abs(fs**2 - fp**2) if fs != fp else math.inf
        n = s.order or min_order(s.approx, ratio, s.ripple_db, s.A_stop)
        if s.realization == "passivo_lc" and s.approx == "chebyshev" and n % 2 == 0:
            n += 1
        log.add(
            record(
                "n",
                "Ordem do filtro" + (" (pedida)" if s.order else " mínima para a rejeição"),
                r"n = \min\{n : A(\Omega_s) \ge A_s\}",
                output=Q_(n, ""),
                inputs={
                    r"\Omega_s": Q_(ratio, ""),
                    "A_s": Q_(s.A_stop, ""),
                    "A_p": Q_(s.ripple_db, ""),
                },
                assumptions=[
                    "Ω_s: frequência de rejeição normalizada no protótipo passa-baixas",
                    "A_s e A_p em dB",
                ],
                reference=WT,
            )
        )
        z, p = prototype(s.approx, n, s.ripple_db, max(s.A_stop, s.ripple_db + 1))
        w1 = 2 * math.pi * fp
        z2, p2 = transform(z, p, s.kind, w1, 2 * math.pi * bw)
        secs = normalise(sections(z2, p2, s.kind), s.kind, w1)
        for k, sec in enumerate(secs, 1):
            log.add(
                record(
                    f"f0_{k}",
                    f"Seção {k}: frequência natural e Q",
                    r"f_0 = \frac{|p|}{2\pi},\quad Q = \frac{|p|}{2\,|\mathrm{Re}\,p|}",
                    output=Q_(sec.w0 / (2 * math.pi), "Hz"),
                    inputs={"Q": Q_(sec.Q, "")},
                    assumptions=[f"seção de {sec.order}ª ordem, tipo {sec.kind}"],
                    reference=WT,
                )
            )
        return n, secs, fp, fs

    def _build(
        self, s: FilSpec, secs: list[Section], n: int, op: OpAmp
    ) -> tuple[Builder, str, float]:
        b = Builder(s, op)
        if s.realization == "passivo_lc":
            g = ladder_g(s.approx, n, s.ripple_db)
            out = build_ladder(b, g, s.kind, 2 * math.pi * s.fp.to_pint().m_as("Hz"))
            return b, out, 0.5
        out = build_active(b, secs)
        return b, out, 1.0

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        n, secs, fp, fs = self._plan(s, log)
        vcc = s.VCC.to_pint().m_as("V")
        if s.realization == "passivo_lc":
            op = OpAmp(A0=1e5, GBW=1e6)
        else:
            op, w = opamp_model(devices["U1"].record, vcc, -vcc, log, "U1", with_errors=False)
            warnings += [DesignWarning(code="modelo", message=x) for x in w]
        b, out, g_term = self._build(s, secs, n, op)
        f_lo = min(fp, fs) / 100
        f_hi = max(fp, fs) * 100
        f = log_grid(f_lo, f_hi, PPD)
        h_real = np.abs(b.c.ac(f, [out])[out])
        h_ideal = g_term * np.abs(response(secs, f))
        fr = self.f_ref(s)
        pts = np.array([fr, fs])
        hr = np.abs(b.c.ac(pts, [out])[out])
        hi = g_term * np.abs(response(secs, pts))
        sol = "análise nodal do circuito com valores comerciais e o modelo do ampop"
        log.add(
            record(
                "G_ref",
                "Ganho na borda (PB/PA) ou no centro (PF/RF) com o circuito real",
                r"|H(j2\pi f_p)|",
                output=Q_(float(hr[0]), ""),
                inputs={"f_{ref}": Q_(fr, "Hz")},
                assumptions=[sol],
                reference=OPA_REF,
            )
        )
        a_real = float(-20 * np.log10(hr[1] / (g_term if g_term else 1)))
        log.add(
            record(
                "A_stop_real",
                "Atenuação na frequência de rejeição (circuito real)",
                r"A = -20\log_{10}\frac{|H(j2\pi f_s)|}{G_{banda}}",
                output=Q_(a_real, ""),
                inputs={"f_s": s.f_stop.to_pint()},
                assumptions=[sol, "em dB"],
                reference=WT,
            )
        )
        if a_real < s.A_stop - 0.5:
            warnings.append(
                DesignWarning(
                    code="rejeicao",
                    message=f"Atenuação em f_s de {a_real:.1f} dB, abaixo dos {s.A_stop:g} dB "
                    "pedidos (efeito do arredondamento ou do ampop).",
                )
            )
        summary: dict[str, pint.Quantity] = {
            "n": Q_(n, ""),
            "f_ref": Q_(fr, "Hz"),
            "G_ref": Q_(float(hr[0]), ""),
            "G_ref_ideal": Q_(float(hi[0]), ""),
            "G_stop": Q_(float(hr[1]), ""),
            "A_stop_real": Q_(a_real, ""),
            "A_stop_ideal": Q_(float(-20 * np.log10(hi[1] / g_term)), ""),
            "G_pass": Q_(float(np.max(h_real)), ""),
        }
        if s.realization != "passivo_lc":
            summary["n_opamps"] = Q_(b.n_op, "")
        if s.kind in ("passa_baixas", "passa_altas"):
            side = "fh" if s.kind == "passa_baixas" else "fl"
            f3 = corner(f, h_real, side)
            f3i = corner(f, h_ideal, side)
            if f3 is not None and f3i is not None:
                log.add(
                    record(
                        "f_3dB",
                        "Corte −3 dB do circuito real (curva)",
                        r"|H(f_{3dB})| = |H|_{max}/\sqrt{2}",
                        output=Q_(f3, "Hz"),
                        inputs={"f_{3dB,ideal}": Q_(f3i, "Hz")},
                        assumptions=[sol],
                        reference=WT,
                    )
                )
                summary |= {
                    "f_3dB": Q_(f3, "Hz"),
                    "f_3dB_ideal": Q_(f3i, "Hz"),
                    "f_dev": Q_((f3 / f3i - 1) * 100, "percent"),
                }
                if abs(f3 / f3i - 1) > 0.05:
                    warnings.append(
                        DesignWarning(
                            code="desvio",
                            message=f"O corte real desvia {100 * (f3 / f3i - 1):+.1f} % do "
                            "ideal: use série mais fina ou ajuste os resistores.",
                        )
                    )
        elif s.kind == "passa_faixa":
            fl, fh = corner(f, h_real, "fl"), corner(f, h_real, "fh")
            if fl is not None and fh is not None:
                summary |= {"f_L": Q_(fl, "Hz"), "f_H": Q_(fh, "Hz")}
        for d, kind, val in b.parts:
            unit = {"R": "ohm", "C": "F", "L": "H"}[kind]
            summary[d] = Q_(val, unit).to({"R": "ohm", "C": "nF", "L": "mH"}[kind])
        zeros = s.approx == "eliptico" or any(sec.kind == "notch" for sec in secs)
        if zeros and s.realization != "variaveis_estado":
            warnings.append(
                DesignWarning(
                    code="topologia",
                    message="Seções com zeros de transmissão foram feitas em variáveis de "
                    "estado (KHN + somador), qualquer que seja a realização escolhida.",
                )
            )
        if s.realization == "passivo_lc":
            warnings.append(
                DesignWarning(
                    code="terminacao",
                    message="Escada com terminações iguais: ganho de 0,5 (−6 dB) na banda "
                    "passante; a fonte precisa ter a resistência R0.",
                )
            )
        if s.realization == "mfb" and s.kind == "passa_altas":
            warnings.append(
                DesignWarning(
                    code="topologia",
                    message="Passa-altas feito em Sallen-Key (MFB passa-altas não implementado).",
                )
            )
        return Analysis(
            log=log,
            stresses=[],
            summary=summary,
            losses={},
            warnings=warnings,
            convergence_keys=("G_ref",),
            bode_f=Trace(unit="Hz", values=[float(x) for x in f]),
            bode={
                "Projeto (valores comerciais)": Trace(unit="", values=[float(x) for x in h_real]),
                "Aproximação ideal": Trace(unit="", values=[float(x) for x in h_ideal]),
            },
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        log = CalcLog()
        n, secs, fp, fs = self._plan(s, log)
        vcc = s.VCC.to_pint().m_as("V")
        if s.realization == "passivo_lc":
            op = OpAmp(A0=1e5, GBW=1e6)
        else:
            op = opamp_model(devices["U1"].record, vcc, -vcc, log, "U1", with_errors=False)[0]
        b, out, _ = self._build(s, secs, n, op)
        probe = f"v({out})"
        checks = [
            SimCheck(
                quantity="Ganho na borda/centro",
                summary_key="G_ref",
                metric="ac_mag",
                probe=probe,
                freq=self.f_ref(s),
                tolerance_pct=0.5,
                justification="mesmo circuito linear (.ac)",
            ),
            SimCheck(
                quantity="Ganho na frequência de rejeição",
                summary_key="G_stop",
                metric="ac_mag",
                probe=probe,
                freq=fs,
                tolerance_pct=0.5,
                justification="mesmo circuito linear (.ac)",
            ),
        ]
        if "f_3dB" in summary:
            checks.append(
                SimCheck(
                    quantity="Corte −3 dB",
                    summary_key="f_3dB",
                    metric="ac_fh" if s.kind == "passa_baixas" else "ac_fl",
                    probe=probe,
                    tolerance_pct=0.5,
                    justification="interpolação na grade de 40 pontos/década",
                )
            )
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[s.kind]} {ENUM_LABELS[s.approx]} de ordem {n}",
            netlist="\n".join(b.c.netlist()),
            checks=checks,
            ac_start=QuantityModel(value=min(fp, fs) / 100, unit="Hz"),
            ac_stop=QuantityModel(value=max(fp, fs) * 100, unit="Hz"),
            ac_points_per_decade=PPD,
            bode_probes={"Projeto (ngspice)": probe},
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        n, secs, _, _ = self._plan(s, CalcLog())
        # same builder as the simulation (the op-amp model does not change the part values)
        b, _, _ = self._build(s, secs, n, OpAmp(A0=1e5, GBW=1e6))
        desc = (
            f"{ENUM_LABELS[s.kind]} {ENUM_LABELS[s.approx]}, ordem {n}, "
            f"{ENUM_LABELS[s.realization]}"
        )
        if s.realization == "passivo_lc":
            return drawings_filter.ladder(title, desc, b.parts, b.nodes)
        values = {d: v for d, _, v in b.parts}
        info = [
            drawings_filter.SectionInfo(kind, k, sec.w0 / (2 * math.pi), sec.Q)
            for kind, k, sec in b.layout
        ]
        parts = {c.designator: c.part_number for c in result.selection}
        return drawings_filter.active(title, desc, info, values, b.nodes, parts.get("U1", ""))

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        sm = result.summary
        rows = []
        for k in sm:
            if k[0] in "RCL" and k[1:].isdigit():
                desc = {
                    "R": "Resistor 1 % (filme metálico)",
                    "C": "Capacitor (filme ou C0G)",
                    "L": "Indutor",
                }[k[0]]
                rows.append(passive(k, desc, format_eng(sm[k].to_pint())))
        if "n_opamps" in sm:
            rows.append(
                passive(
                    "U1…",
                    "Ampops iguais ao U1 (um por seção ativa)",
                    f"{int(sm['n_opamps'].to_pint().m_as(''))} unidades",
                )
            )
        return rows
