"""Thyristor model for the device bench (BD-TIR): SCR and TRIAC with a resistive load.

Switching model (didactic, the one used to explain IGT, IL and IH in Rashid's thyristor chapter):

    on-state:   v_T = VT0 + rT·i          (SCR: anode → cathode only; TRIAC: both directions)
    off-state:  i = 0
    turn-on:    gate current ≥ IGT of the trigger quadrant while the device is forward biased
    latching:   once on, the device latches when i ≥ IL; before that, removing the gate turns it off
    turn-off:   a latched device turns off when |i| falls below IH (natural commutation)

Quadrants of a TRIAC (MT2 and G measured from MT1): Q1 = MT2(+), G(+); Q2 = MT2(+), G(−);
Q3 = MT2(−), G(−); Q4 = MT2(−), G(+). An SCR only fires in Q1.

The same rules are written as an ngspice behavioural subcircuit (:meth:`ThyristorModel.spice`),
and tests/analytic_vs_sim checks that both give the same waveform.

Circuit: v_s = Vm·sin(ωt) → R → thyristor → return. Gate pulses of amplitude IG and width tw at
ωt = α (and α + π for a TRIAC).

References: Rashid, *Power Electronics: Circuits, Devices and Applications* (thyristor chapter:
latching and holding current, gate characteristics; controlled rectifiers: half-wave with R
load; AC voltage controllers: full-wave with R load). Chapter and equation numbers still to be
checked against the printed book (BibRef.verified = False).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pint
from numpy.typing import NDArray

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, require

TIR_REF = BibRef(
    book="Rashid, Power Electronics: Circuits, Devices and Applications", chapter="Thyristors"
)
RECT_REF = BibRef(
    book="Rashid, Power Electronics: Circuits, Devices and Applications",
    chapter="Controlled rectifiers",
)
ACVC_REF = BibRef(
    book="Rashid, Power Electronics: Circuits, Devices and Applications",
    chapter="AC voltage controllers",
)

Kind = Literal["scr", "triac"]
GateMode = Literal["positivo", "negativo", "acompanha"]
QUADRANTS = ("Q1", "Q2", "Q3", "Q4")


@dataclass(frozen=True)
class ThyristorModel:
    kind: Kind
    VT0: pint.Quantity  # threshold voltage of the on-state line
    rT: pint.Quantity  # slope resistance of the on-state line
    IGT: tuple[pint.Quantity, pint.Quantity, pint.Quantity, pint.Quantity]  # Q1..Q4
    IH: pint.Quantity
    IL: pint.Quantity

    def __post_init__(self) -> None:
        require(self.VT0, "V", "VT0")
        require(self.rT, "ohm", "rT")
        require(self.IH, "A", "IH")
        require(self.IL, "A", "IL")
        if len(self.IGT) != 4:
            raise ValueError("IGT deve ter um valor por quadrante (Q1 a Q4)")
        for q in self.IGT:
            require(q, "A", "IGT")
            if not q.magnitude > 0:
                raise ValueError("IGT deve ser positivo")
        if self.VT0.magnitude < 0 or not self.rT.magnitude > 0:
            raise ValueError("VT0 não pode ser negativo e rT deve ser positivo")
        if not (self.IH.magnitude > 0 and self.IL.magnitude > 0):
            raise ValueError("IH e IL devem ser positivos")

    def igt(self) -> NDArray[np.float64]:
        return np.array([q.m_as("A") for q in self.IGT])

    def spice(self, name: str = "XTIR") -> str:
        """Behavioural subcircuit with pins (anode/MT2, cathode/MT1, gate sense in, gate sense out).

        The gate current enters at pin ``g`` and leaves at ``gk`` (an ideal sense, 0 V); the
        latch states are RC-filtered (τ = 1 µs) so the logic has no algebraic loop.
        """
        vt0 = self.VT0.m_as("V")
        rt = self.rT.m_as("ohm")
        ih = self.IH.m_as("A")
        il = self.IL.m_as("A")
        g1, g2, g3, g4 = self.igt()
        if self.kind == "scr":
            cond = f"(v(a,k) > {vt0:.9g}) ? (v(a,k) - {vt0:.9g}) / {rt:.9g} : 0"
            fire = f"(i(VGS) >= {g1:.9g} && v(a,k) > {vt0:.9g})"
            hold = f"(v(lt) > 0.5 && i(VKS) > {ih:.9g})"
            latch = f"(i(VKS) >= {il:.9g} || v(lt) > 0.5)"
        else:
            cond = (
                f"(v(a,k) > {vt0:.9g}) ? (v(a,k) - {vt0:.9g}) / {rt:.9g} : "
                f"((v(a,k) < -{vt0:.9g}) ? (v(a,k) + {vt0:.9g}) / {rt:.9g} : 0)"
            )
            fire = (
                f"((v(a,k) > {vt0:.9g} && (i(VGS) >= {g1:.9g} || i(VGS) <= -{g2:.9g})) || "
                f"(v(a,k) < -{vt0:.9g} && (i(VGS) <= -{g3:.9g} || i(VGS) >= {g4:.9g})))"
            )
            hold = f"(v(lt) > 0.5 && abs(i(VKS)) > {ih:.9g})"
            latch = f"(abs(i(VKS)) >= {il:.9g} || v(lt) > 0.5)"
        return "\n".join(
            [
                f".subckt {name} a k g gk",
                "VGS g gk DC 0",
                f"BA a ks I = v(st) * ({cond}) + v(a,k) * 1e-9",
                "VKS ks k DC 0",
                f"BST nst 0 V = ({fire} || {hold}) ? 1 : 0",
                "RST nst st 1k",
                "CST st 0 1n",
                f"BLT nlt 0 V = (v(st) > 0.5 && {latch}) ? 1 : 0",
                "RLT nlt lt 1k",
                "CLT lt 0 1n",
                ".ends",
            ]
        )


@dataclass(frozen=True)
class Drive:
    """Source, load and gate drive of the bench circuit."""

    Vm: pint.Quantity  # source peak voltage
    f: pint.Quantity  # source frequency
    R: pint.Quantity  # load resistance
    alpha: pint.Quantity  # firing angle
    IG: pint.Quantity  # gate pulse amplitude (magnitude)
    tw: pint.Quantity  # gate pulse width
    gate_mode: GateMode = "positivo"

    def __post_init__(self) -> None:
        require(self.Vm, "V", "Vm")
        require(self.f, "Hz", "f")
        require(self.R, "ohm", "R")
        require(self.alpha, "deg", "α")
        require(self.IG, "A", "IG")
        require(self.tw, "s", "tw")
        a = self.alpha.m_as("deg")
        if not (0 <= a < 180):
            raise ValueError("α deve estar entre 0° e 180°")
        if not (self.Vm.magnitude > 0 and self.f.magnitude > 0 and self.R.magnitude > 0):
            raise ValueError("Vm, f e R devem ser positivos")
        if self.IG.magnitude < 0 or not self.tw.magnitude > 0:
            raise ValueError("IG não pode ser negativo e tw deve ser positivo")
        if self.tw.m_as("s") * self.f.m_as("Hz") >= 0.5:
            raise ValueError("O pulso de porta deve durar menos de meio ciclo")

    def pulse_signs(self, kind: Kind) -> tuple[int, int]:
        """Gate polarity of the pulse at α and at α + π (0 = no pulse)."""
        if kind == "scr":
            return 1, 0
        return {"positivo": (1, 1), "negativo": (-1, -1), "acompanha": (1, -1)}[self.gate_mode]


@dataclass
class Waveform:
    t: NDArray[np.float64]
    vs: NDArray[np.float64]
    v_load: NDArray[np.float64]
    v_t: NDArray[np.float64]
    i: NDArray[np.float64]
    ig: NDArray[np.float64]
    on: NDArray[np.bool_]
    events: list[tuple[str, float]] = field(default_factory=list)  # ("on"|"off", t)


def gate_current(drive: Drive, kind: Kind, t: NDArray[np.float64]) -> NDArray[np.float64]:
    period = 1 / drive.f.m_as("Hz")
    t_alpha = drive.alpha.m_as("deg") / 360 * period
    tw = drive.tw.m_as("s")
    ig = drive.IG.m_as("A")
    s1, s2 = drive.pulse_signs(kind)
    phase = np.mod(t, period)
    out = np.zeros_like(t)
    out += np.where((phase >= t_alpha) & (phase < t_alpha + tw), s1 * ig, 0.0)
    t2 = t_alpha + period / 2
    out += np.where((phase >= t2) & (phase < t2 + tw), s2 * ig, 0.0)
    return out


def _on_current(m: ThyristorModel, drive: Drive, vs: NDArray[np.float64]) -> NDArray[np.float64]:
    vt0 = m.VT0.m_as("V")
    r = drive.R.m_as("ohm") + m.rT.m_as("ohm")
    fwd = np.where(vs > vt0, (vs - vt0) / r, 0.0)
    if m.kind == "scr":
        return fwd
    return fwd + np.where(vs < -vt0, (vs + vt0) / r, 0.0)


def _fires(m: ThyristorModel, vs: float, ig: float) -> bool:
    vt0 = m.VT0.m_as("V")
    g1, g2, g3, g4 = m.igt()
    if vs > vt0:
        return bool(ig >= g1 or (m.kind == "triac" and ig <= -g2))
    if m.kind == "triac" and vs < -vt0:
        return bool(ig <= -g3 or ig >= g4)
    return False


def simulate(
    m: ThyristorModel, drive: Drive, periods: int = 2, points_per_period: int = 6000
) -> Waveform:
    """Time-step the switching rules (exact on the grid; no circuit solver needed)."""
    period = 1 / drive.f.m_as("Hz")
    t = np.linspace(0, periods * period, periods * points_per_period + 1)
    vs = drive.Vm.m_as("V") * np.sin(2 * np.pi * drive.f.m_as("Hz") * t)
    ig = gate_current(drive, m.kind, t)
    i_on = _on_current(m, drive, vs)
    ih = m.IH.m_as("A")
    il = m.IL.m_as("A")
    on = np.zeros(t.shape, dtype=bool)
    latched = False
    was_on = False
    events: list[tuple[str, float]] = []
    for k in range(t.size):
        now = _fires(m, float(vs[k]), float(ig[k])) or (latched and abs(i_on[k]) > ih)
        latched = now and (abs(i_on[k]) >= il or latched)
        on[k] = now
        if now != was_on:
            events.append(("on" if now else "off", float(t[k])))
        was_on = now
    i = np.where(on, i_on, 0.0)
    v_load = i * drive.R.m_as("ohm")
    return Waveform(t=t, vs=vs, v_load=v_load, v_t=vs - v_load, i=i, ig=ig, on=on, events=events)


def last_period_metrics(w: Waveform, drive: Drive) -> tuple[float, float]:
    """Average and RMS load voltage over the last full period (V)."""
    period = 1 / drive.f.m_as("Hz")
    sel = w.t >= w.t[-1] - period
    t = w.t[sel]
    v = w.v_load[sel]
    span = t[-1] - t[0]
    avg = float(np.trapezoid(v, t) / span)
    rms = float(np.sqrt(np.trapezoid(v**2, t) / span))
    return avg, rms


# ---------------------------------------------------------------- calculation steps


def ideal_load_voltage(kind: Kind, drive: Drive) -> list[Calculated[pint.Quantity]]:
    """Closed-form average/RMS load voltage with an ideal device (VT0 = rT = IH = 0)."""
    vm = drive.Vm.m_as("V")
    a = drive.alpha.m_as("rad")
    inputs = {"V_m": drive.Vm, r"\alpha": drive.alpha}
    if kind == "scr":
        avg = Q_(vm / (2 * math.pi) * (1 + math.cos(a)), "V")
        rms = Q_(vm / 2 * math.sqrt(1 - a / math.pi + math.sin(2 * a) / (2 * math.pi)), "V")
        return [
            record(
                "Vavg_ideal",
                "Tensão média na carga, tiristor ideal (meia onda, carga resistiva)",
                r"V_{med} = \frac{V_m}{2\pi}(1 + \cos\alpha)",
                output=avg,
                inputs=inputs,
                assumptions=["tiristor ideal: VT0 = 0, rT = 0, IH = 0", "disparo garantido em α"],
                reference=RECT_REF,
            ),
            record(
                "Vrms_ideal",
                "Tensão eficaz na carga, tiristor ideal (meia onda, carga resistiva)",
                r"V_{ef} = \frac{V_m}{2}\sqrt{1 - \frac{\alpha}{\pi} + \frac{\sin 2\alpha}{2\pi}}",
                output=rms,
                inputs=inputs,
                assumptions=["tiristor ideal: VT0 = 0, rT = 0, IH = 0", "disparo garantido em α"],
                reference=RECT_REF,
            ),
        ]
    rms = Q_(vm / math.sqrt(2) * math.sqrt(1 - a / math.pi + math.sin(2 * a) / (2 * math.pi)), "V")
    return [
        record(
            "Vrms_ideal",
            "Tensão eficaz na carga, TRIAC ideal (controlador CA monofásico, carga resistiva)",
            r"V_{ef} = \frac{V_m}{\sqrt{2}}"
            r"\sqrt{1 - \frac{\alpha}{\pi} + \frac{\sin 2\alpha}{2\pi}}",
            output=rms,
            inputs=inputs,
            assumptions=[
                "TRIAC ideal: VT0 = 0, rT = 0, IH = 0",
                "disparo garantido em α e α + π (simetria de meia onda; tensão média nula)",
            ],
            reference=ACVC_REF,
        )
    ]


def turn_off_angle(m: ThyristorModel, drive: Drive) -> Calculated[pint.Quantity]:
    vm = drive.Vm.m_as("V")
    r = drive.R.m_as("ohm") + m.rT.m_as("ohm")
    x = (m.VT0.m_as("V") + m.IH.m_as("A") * r) / vm
    if x >= 1:
        raise ValueError("A corrente de pico na carga não alcança IH: o tiristor não se mantém")
    theta = Q_(180 - math.degrees(math.asin(x)), "deg")
    return record(
        "theta_off",
        "Ângulo de bloqueio (a corrente cai abaixo de IH)",
        r"\theta_{off} = \pi - \arcsin\frac{V_{T0} + I_H (R + r_T)}{V_m}",
        output=theta,
        inputs={"V_m": drive.Vm, "V_{T0}": m.VT0, "I_H": m.IH, "R": drive.R, "r_T": m.rT},
        assumptions=["carga resistiva", "comutação natural pela fonte"],
        reference=TIR_REF,
    )


def latch_current(m: ThyristorModel, drive: Drive) -> Calculated[pint.Quantity]:
    """Load current at the end of the gate pulse; the device latches only if it reaches IL."""
    vm = drive.Vm.m_as("V")
    w = 2 * math.pi * drive.f.m_as("Hz")
    a = drive.alpha.m_as("rad")
    tw = drive.tw.m_as("s")
    r = drive.R.m_as("ohm") + m.rT.m_as("ohm")
    # the current peaks at ωt = π/2 if the pulse spans it
    end = a + w * tw
    peak = math.pi / 2 if a <= math.pi / 2 <= end else max(a, end, key=lambda x: math.sin(x))
    i_max = max(0.0, (vm * math.sin(peak) - m.VT0.m_as("V")) / r)
    return record(
        "i_latch",
        "Maior corrente na carga durante o pulso de porta",
        r"i_{max} = \max_{\alpha \le \omega t \le \alpha + \omega t_w}"
        r"\frac{V_m \sin\omega t - V_{T0}}{R + r_T}",
        output=Q_(i_max, "A").to("mA"),
        inputs={
            "V_m": drive.Vm,
            r"\alpha": drive.alpha,
            "t_w": drive.tw,
            "R": drive.R,
            "r_T": m.rT,
            "V_{T0}": m.VT0,
        },
        assumptions=[f"trava se i_max ≥ IL = {m.IL.to('mA'):~.3g}", "carga resistiva"],
        reference=TIR_REF,
    )


def on_state_fit(
    vtm: pint.Quantity, itm: pint.Quantity, vt0: pint.Quantity
) -> Calculated[pint.Quantity]:
    require(vtm, "V", "VTM")
    require(itm, "A", "ITM")
    rt = Q_((vtm.m_as("V") - vt0.m_as("V")) / itm.m_as("A"), "ohm")
    if rt.magnitude <= 0:
        raise ValueError("VT0 deve ser menor que VTM do datasheet")
    return record(
        "rT_fit",
        "Resistência de inclinação a partir de VTM do datasheet",
        r"r_T = \frac{V_{TM} - V_{T0}}{I_{TM}}",
        output=rt.to("mohm"),
        inputs={"V_{TM}": vtm, "I_{TM}": itm, "V_{T0}": vt0},
        assumptions=[
            "reta de condução v = VT0 + rT·i passando pelo ponto de VTM",
            "VT0 da bancada",
        ],
        reference=TIR_REF,
    )
