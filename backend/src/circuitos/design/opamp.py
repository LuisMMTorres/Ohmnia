"""Op-amp macromodel shared by the analysis and the simulator.

Single-pole model (Sedra & Smith, *Microelectronic Circuits*, 7th ed., ch. 2 "Operational
amplifiers", sec. on finite open-loop gain and bandwidth, and ch. 13/appendix on op-amp
macromodels): A(s) = A0/(1 + s/ωb), with ωt = A0·ωb the unity-gain frequency (GBW). Input
resistance Rin, bias currents IB ± IOS/2 into the inputs and the offset VOS as a source in
series with the non-inverting input. The output is an ideal buffer of the internal node (the
catalogue has no output resistance for most parts).

Linear analyses (DC errors, gain, bandwidth) use the model as written, the same element lines
go to the netlist. For time-domain circuits the netlist adds the two non-linearities of a real
op-amp as behavioural sources: the current into the pole capacitor is limited to SR·C (slew
rate) and the internal node is clamped to the output swing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pint

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_
from circuitos.design.devmodels import SEDRA, quantity
from circuitos.design.mna import Circuit

REF = SEDRA.model_copy(update={"chapter": "2 (Operational amplifiers)"})
TI_BW = BibRef(book="Texas Instruments LM741 (SNOSC25D)", edition="Rev. D", chapter="6.6, nota 2")
C_POLE = 1e-9  # F, pole capacitor of the macromodel; R = 1/(2π fb C), gm = A0/R
CLAMP_G = 1e3  # S, conductance of the output-swing clamp beyond the limits
# the stiff clamp locks the trapezoidal rule at the saturation corners (the output stays
# saturated after the input reverses); Gear integration has no such ringing
TRAN_OPTIONS = ".options method=gear"


@dataclass(frozen=True)
class OpAmp:
    A0: float  # V/V
    GBW: float  # Hz
    Rin: float = math.inf  # Ω
    Vos: float = 0.0  # V, in series with the non-inverting input
    Ib: float = 0.0  # A, mean bias current (into each input)
    Ios: float = 0.0  # A, offset current: Ib+ − Ib−
    SR: float = math.inf  # V/s
    v_hi: float = math.inf  # V, output swing limits
    v_lo: float = -math.inf
    name: str = "ideal"
    CMRR: float = math.inf  # V/V; input-referred error v_cm/CMRR, v_cm = (v+ + v−)/2
    PSRR: float = math.inf  # V/V; input-referred error ΔV_S/PSRR (ΔV_S per rail, symmetric)
    VS_nom: float = 15.0  # V per rail where the datasheet VOS holds (PSRR reference)

    @property
    def fb(self) -> float:
        """Open-loop −3 dB frequency, GBW/A0."""
        return self.GBW / self.A0

    @property
    def r_pole(self) -> float:
        """Pole resistor: with C_POLE, R·C = 1/(2π fb); v(n1) = A0·vd at DC."""
        return 1 / (2 * math.pi * self.fb * C_POLE)

    def a(self, f: float) -> complex:
        return self.A0 / (1 + 1j * f / self.fb)

    def _input_chain(
        self, c: Circuit, p: str, inp: str, inn: str, sup: tuple[str, str] | None
    ) -> str:
        """VOS, common-mode and supply errors in series with the + input; returns the node."""
        with_cm = math.isfinite(self.CMRR)
        with_ps = sup is not None and math.isfinite(self.PSRR)
        node = f"{p}x"
        a = f"{p}x1" if (with_cm or with_ps) else node
        c.V(f"{p}os", a, inp, self.Vos)
        if with_cm:
            b = f"{p}x3" if with_ps else node
            c.E(f"{p}ca", f"{p}x2", a, inp, "0", 1 / (2 * self.CMRR))
            c.E(f"{p}cb", b, f"{p}x2", inn, "0", 1 / (2 * self.CMRR))
            a = b
        if with_ps:
            assert sup is not None
            c.E(f"{p}ps", f"{p}x4", a, sup[0], sup[1], 1 / (2 * self.PSRR))
            c.V(f"{p}pn", node, f"{p}x4", -self.VS_nom / self.PSRR)
        return node

    def add(
        self,
        c: Circuit,
        p: str,
        inp: str,
        inn: str,
        out: str,
        sup: tuple[str, str] | None = None,
    ) -> None:
        """Linear macromodel into the MNA circuit (element names prefixed with ``p``).

        ``sup`` = (V+ node, V− node) adds the supply error (PSRR) for the bench tests.
        """
        if math.isfinite(self.Rin):
            c.R(f"{p}in", inp, inn, self.Rin)
        if self.Ib or self.Ios:
            c.I(f"{p}bp", inp, "0", self.Ib + self.Ios / 2)
            c.I(f"{p}bn", inn, "0", self.Ib - self.Ios / 2)
        x = self._input_chain(c, p, inp, inn, sup)
        n1 = f"{p}n1"
        c.G(f"{p}1", "0", n1, x, inn, self.A0 / self.r_pole)
        c.R(f"{p}1", n1, "0", self.r_pole)
        c.C(f"{p}1", n1, "0", C_POLE)
        c.E(f"{p}o", out, "0", n1, "0", 1.0)

    def nonlinear_lines(self, p: str, inp: str, inn: str, out: str) -> list[str]:
        """Netlist of the macromodel with slew-rate limit and output clamp (transient)."""
        gm = self.A0 / self.r_pole
        # the current into the pole capacitor limited to SR·C: dv/dt ≤ SR
        il = self.SR * C_POLE if math.isfinite(self.SR) else 1e30
        hi = self.v_hi if math.isfinite(self.v_hi) else 1e6
        lo = self.v_lo if math.isfinite(self.v_lo) else -1e6
        lines = []
        if math.isfinite(self.Rin):
            lines.append(f"R{p}in {inp} {inn} {self.Rin:.9g}")
        if self.Ib or self.Ios:
            lines += [
                f"I{p}bp {inp} 0 DC {self.Ib + self.Ios / 2:.9g}",
                f"I{p}bn {inn} 0 DC {self.Ib - self.Ios / 2:.9g}",
            ]
        x, n1 = f"{p}x", f"{p}n1"
        if math.isfinite(self.CMRR):
            k = 1 / (2 * self.CMRR)
            lines += [
                f"V{p}os {p}x1 {inp} DC {self.Vos:.9g}",
                f"E{p}ca {p}x2 {p}x1 {inp} 0 {k:.9g}",
                f"E{p}cb {x} {p}x2 {inn} 0 {k:.9g}",
            ]
        else:
            lines.append(f"V{p}os {x} {inp} DC {self.Vos:.9g}")
        lines += [
            f"B{p}1 0 {n1} I=max(min({gm:.9g}*(v({x})-v({inn})),{il:.9g}),{-il:.9g})",
            f"R{p}1 {n1} 0 {self.r_pole:.9g}",
            f"C{p}1 {n1} 0 {C_POLE:.9g}",
            # stiff clamp of the internal node at the output swing (overshoot il/CLAMP_G)
            f"B{p}c {n1} 0 I={CLAMP_G:.9g}*(max(v({n1})-({hi:.9g}),0)+min(v({n1})-({lo:.9g}),0))",
            f"E{p}o {out} 0 {n1} 0 1",
        ]
        return lines


def _typ(rec: ComponentRecord, key: str, unit: str) -> float | None:
    q = quantity(rec, key, ("typ", "max", "min"))
    return None if q is None else float(q.m_as(unit))


def db_ratio(rec: ComponentRecord, key: str) -> float:
    """A ratio stored in dB (CMRR, PSRR) as V/V, typical value; inf when absent.

    The catalogue keeps the dB number as written in the datasheet (pint's dB is a power ratio,
    so it is read as a plain number here): ratio = 10^(dB/20).
    """
    p = rec.parameters.get(key)
    if p is None or not p.has_value:
        return math.inf
    db = p.typ if p.typ is not None else p.min
    return math.inf if db is None else 10 ** (db / 20)


def gbw_of(rec: ComponentRecord) -> float:
    """GBW of a catalogue op-amp in Hz (0,35/tr when only the rise time is given), else 0."""
    gbw = _typ(rec, "GBW", "Hz")
    if gbw is None:
        tr = _typ(rec, "tr", "s")
        gbw = 0.35 / tr if tr else 0.0
    return gbw


def opamp_model(
    rec: ComponentRecord | None,
    v_pos: float,
    v_neg: float,
    log: CalcLog,
    designator: str,
    with_errors: bool = True,
) -> tuple[OpAmp, list[str]]:
    """Macromodel of a catalogue op-amp with typical values, for supplies v_pos/v_neg."""
    warnings: list[str] = []
    if rec is None:
        m = OpAmp(A0=2e5, GBW=1e6, v_hi=v_pos - 1.5, v_lo=v_neg + 1.5)
        log.add(
            record(
                f"A0_{designator}",
                f"Modelo de {designator}: ampop ideal de projeto (sem componente)",
                r"A_0 = 2\cdot10^5,\ GBW = 1\ \mathrm{MHz}",
                output=Q_(m.A0, ""),
                assumptions=["premissa do passo ideal; saturação a 1,5 V dos trilhos"],
                reference=REF,
            )
        )
        return m, warnings
    a0 = _typ(rec, "Avol", "")
    if a0 is None:
        raise ValueError(f"{rec.part_number}: datasheet sem ganho em malha aberta")
    gbw = _typ(rec, "GBW", "Hz")
    how = "GBW típico do datasheet"
    if gbw is None:
        tr = _typ(rec, "tr", "s")
        if tr is None:
            raise ValueError(f"{rec.part_number}: datasheet sem GBW nem tempo de subida")
        gbw = 0.35 / tr
        how = "BW = 0,35/tr do datasheet (resposta de 1ª ordem)"
        log.add(
            record(
                f"GBW_{designator}",
                f"Produto ganho-banda de {designator} a partir do tempo de subida",
                r"GBW = \frac{0{,}35}{t_r}",
                output=Q_(gbw, "Hz").to("MHz"),
                inputs={"t_r": Q_(tr, "s").to("us")},
                assumptions=["polo único: t_r(10–90 %) = 2,2·τ = 0,35/f_t"],
                reference=TI_BW,
            )
        )
    rin = _typ(rec, "Rin", "ohm") or math.inf
    sr = _typ(rec, "SR", "V/s") or math.inf
    vos = (_typ(rec, "Vos", "V") or 0.0) if with_errors else 0.0
    ib = (_typ(rec, "Ib", "A") or 0.0) if with_errors else 0.0
    ios = (_typ(rec, "Ios", "A") or 0.0) if with_errors else 0.0
    cmrr = db_ratio(rec, "CMRR") if with_errors else math.inf
    psrr = db_ratio(rec, "PSRR") if with_errors else math.inf
    # output swing: from-rail drops when given; else the ±15 V test swing as headroom
    vom = quantity(rec, "Vom", ("typ", "min"))
    drop_hi = _typ(rec, "VOH_drop", "V")
    drop_lo = _typ(rec, "VOL_drop", "V")
    if drop_hi is None and vom is not None:
        p = rec.parameters["Vom"]
        vs_test = p.conditions["VS"].to_pint().m_as("V") if "VS" in p.conditions else 15.0
        drop_hi = drop_lo = vs_test - float(vom.m_as("V"))
    if drop_hi is None:
        drop_hi = 1.5
        warnings.append(
            f"{designator}: datasheet sem excursão de saída; premissa de 1,5 V dos trilhos."
        )
    if drop_lo is None:
        drop_lo = drop_hi
    m = OpAmp(
        A0=a0,
        GBW=gbw,
        Rin=rin,
        Vos=vos,
        Ib=ib,
        Ios=ios,
        SR=sr,
        v_hi=v_pos - drop_hi,
        v_lo=v_neg + drop_lo,
        name=rec.part_number,
        CMRR=cmrr,
        PSRR=psrr,
        VS_nom=(v_pos - v_neg) / 2,
    )
    inputs: dict[str, pint.Quantity] = {
        "A_0": Q_(a0, ""),
        "GBW": Q_(gbw, "Hz").to("MHz"),
        "SR": Q_(sr, "V/s").to("V/us"),
        "V_{OS}": Q_(vos, "V").to("mV"),
        "I_B": Q_(ib, "A").to("nA"),
    }
    if math.isfinite(cmrr):
        inputs["CMRR"] = Q_(cmrr, "")
    log.add(
        record(
            f"fb_{designator}",
            f"Polo de malha aberta do modelo de {designator} ({rec.part_number})",
            r"f_b = \frac{GBW}{A_0}",
            output=Q_(m.fb, "Hz"),
            inputs=inputs,
            assumptions=[
                f"valores típicos do datasheet; {how}",
                "modelo de polo único; sem resistência de saída",
                f"saturação em {m.v_lo:.3g} V e {m.v_hi:.3g} V (excursão do datasheet)",
            ],
            reference=REF,
        )
    )
    return m, warnings
