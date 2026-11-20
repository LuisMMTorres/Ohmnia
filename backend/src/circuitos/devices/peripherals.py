"""Device bench for the sensors, actuators and controllers of the simulator library (BD-PER).

Each bench places the library symbol (the same behavioural SPICE model the schematic uses,
:mod:`circuitos.schematic.cosim_symbols` and :mod:`circuitos.schematic.drive_symbols`) on a
test fixture, runs it in ngspice (with the co-simulation for Arduino, ESP32 and the PLC) and
compares every measurement with the closed form the model implements (rule 4). A catalogue
part placed on the bench gives its datasheet values to the model, as in the schematic.

The fixtures (supply, load, lead resistance, stimulus range) are test conditions chosen by the
user; they are not component parameters.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pint
from numpy.typing import NDArray
from scipy.linalg import expm

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcStep, record
from circuitos.core.units import Q_
from circuitos.cosim.arduino import BOARDS
from circuitos.cosim.controllers import PLC_AI_SHUNT, PLC_AQ_ROUT, PLC_DI_OFF, PLC_DI_ON
from circuitos.devices.opamp_bench import BenchTest
from circuitos.machines import thermocouple as tc
from circuitos.machines.induction import InductionParams, operating_point, steady_state
from circuitos.machines.stepper import load_angle_deg
from circuitos.schematic.cosim_symbols import CATALOGUE_PARAMS, catalogue_value
from circuitos.schematic.library import pin_defs, pin_positions, symbol
from circuitos.schematic.model import Analysis, AnalysisKind, Component, NetLabel, Schematic
from circuitos.schematic.runs import SchematicPlan
from circuitos.schematic.symbols_base import ParamDef
from circuitos.schematic.values import parse_value
from circuitos.simulation.results import Plot

FloatArray = NDArray[np.float64]


class BenchError(ValueError):
    """Bench that cannot run with the given values (message in Portuguese)."""


# ------------------------------------------------------------------------------ references

LM35 = BibRef(book="Texas Instruments, LM35 Precision Centigrade Temperature Sensors", page="1")
IEC60751 = BibRef(
    book="IEC 60751, Industrial platinum resistance thermometers and platinum temperature sensors",
    chapter="equação de Callendar-Van Dusen (T ≥ 0 °C)",
)
NIST_TC = BibRef(
    book="NIST Monograph 175, Temperature-Electromotive Force Reference Functions and Tables "
    "for the Letter-Designated Thermocouple Types Based on the ITS-90",
    edition="1993",
)
LOOP_420 = BibRef(
    book="IEC 60381-1, Analogue signals for process control systems: direct current signals",
    chapter="sinal de 4 a 20 mA",
)
ACS712 = BibRef(book="Allegro MicroSystems, ACS712 datasheet", page="1, 5 e 6")
DIVIDER = BibRef(
    book="Boylestad, Introdução à análise de circuitos",
    chapter="circuitos série e série-paralelo: divisor de tensão",
)
NGSPICE_SW = BibRef(
    book="ngspice User's Manual", chapter="chave controlada por tensão (S): limiar e histerese"
)
DC_MOTOR = BibRef(
    book="Ogata, Engenharia de controle moderno",
    chapter="modelagem do motor CC controlado pela armadura",
)
LUMPED = BibRef(
    book="Incropera, Fundamentos de transferência de calor e de massa",
    chapter="condução transiente: método da capacitância global",
)
CHAPMAN = BibRef(
    book="Chapman, Electric Machinery Fundamentals",
    edition="5th",
    chapter="6 (circuito equivalente do motor de indução)",
)
WEG_CFW500 = BibRef(book="WEG, CFW500 manual de programação", chapter="P0100, P0101, P0136")
WEG_SSW07 = BibRef(book="WEG, SSW-07 manual do usuário", page="31 a 33")
KENJO = BibRef(
    book="Kenjo, Stepping Motors and Their Microprocessor Controls", edition="2nd", chapter="4"
)
ARDUINO = BibRef(
    book="Arduino UNO R3 User Manual (SKU A000066) e referência da linguagem Arduino",
    chapter="analogRead, analogWrite, digitalRead",
)
ESP32 = BibRef(
    book="Espressif, ESP32-WROOM-32 datasheet e referência do núcleo Arduino-ESP32",
    chapter="ADC, DAC, LEDC (PWM)",
)
IEC61131 = BibRef(
    book="IEC 61131-2, Programmable controllers: equipment requirements and tests",
    chapter="entradas digitais tipo 1 (24 V CC)",
)
MODEL = "Modelo comportamental do simulador (o mesmo do esquemático)."


# ------------------------------------------------------------------------------ results


@dataclass
class Trace:
    name: str
    unit: str
    values: list[float | None]


@dataclass
class Curve:
    id: str
    title: str
    x_label: str
    x_unit: str
    x: list[float]
    traces: list[Trace]
    x_log: bool = False


@dataclass
class PeripheralResult:
    kind: str
    tests: list[BenchTest]
    curves: list[Curve]
    steps: list[CalcStep]
    netlists: dict[str, str]
    warnings: list[str]
    used: dict[str, str]  # effective device parameters (catalogue values applied)


def _comma(text: str) -> str:
    """Decimal comma (pt-BR) in the numbers of a label."""
    return re.sub(r"(\d)\.(\d)", r"\1,\2", text)


def _clean(values: FloatArray | Sequence[float]) -> list[float | None]:
    return [float(v) if math.isfinite(float(v)) else None for v in values]


def _decimate(x: FloatArray, n: int = 800) -> NDArray[np.intp]:
    if len(x) <= n:
        return np.arange(len(x))
    return np.unique(np.linspace(0, len(x) - 1, n).round().astype(np.intp))


def crossing(x: FloatArray, y: FloatArray, level: float, rising: bool = True) -> float:
    """First x where y crosses ``level`` upwards (or downwards), linear interpolation."""
    s = (y >= level) if rising else (y <= level)
    idx = np.nonzero(s[1:] & ~s[:-1])[0]
    if len(idx) == 0:
        raise BenchError("o sinal não cruzou o nível esperado durante o ensaio")
    i = int(idx[0])
    x0, x1, y0, y1 = x[i], x[i + 1], y[i], y[i + 1]
    return float(x0 + (level - y0) * (x1 - x0) / (y1 - y0)) if y1 != y0 else float(x1)


# --------------------------------------------------------------------------------- bench


class _Ctx:
    """One bench run: the device under test, its parameters, the fixtures and the results."""

    def __init__(
        self,
        kind: str,
        params: dict[str, str],
        fixture: dict[str, str],
        record_: ComponentRecord | None,
        backend: Any,
        spec: PeripheralBench,
    ):
        self.kind = kind
        self.sym = symbol(kind)
        self.params = {k: v for k, v in params.items() if v.strip() != ""}
        self.fixture_text = {
            p.name: fixture.get(p.name, "").strip() or p.default for p in spec.fixture
        }
        self.record = record_
        self.backend = backend
        self.tests: list[BenchTest] = []
        self.curves: list[Curve] = []
        self.steps: list[CalcStep] = []
        self.netlists: dict[str, str] = {}
        self.warnings: list[str] = []
        self._n = 0

        def fallback(name: str) -> str:
            text = self.params.get(name)
            return text if text is not None else self.sym.param(name).default

        self.text: Callable[[str], str] = (
            catalogue_value(kind, record_, fallback) if record_ is not None else fallback
        )

    # values ---------------------------------------------------------------------------
    def p(self, name: str) -> float:
        """Numeric device parameter (catalogue value, user value or symbol default)."""
        text = self.text(name)
        try:
            return parse_value(text)
        except ValueError as exc:
            label = self.sym.param(name).label
            raise BenchError(f"{label}: {exc}") from exc

    def f(self, name: str) -> float:
        text = self.fixture_text[name]
        try:
            return parse_value(text)
        except ValueError as exc:
            raise BenchError(f"Condição de ensaio {name}: {exc}") from exc

    # schematic ---------------------------------------------------------------------------
    def new(self, title: str) -> Schematic:
        return Schematic(title=title)

    def add(
        self,
        sch: Schematic,
        kind: str,
        ref: str,
        nodes: dict[str, str],
        dut: bool = False,
        **params: str,
    ) -> Component:
        """Place a part (the device under test with ``dut``) and tie its pins by labels."""
        self._n += 1
        values = dict(self.params) if dut else {}
        values.update(params)
        comp = Component(
            id=f"b{self._n}",
            kind=kind,
            ref=ref,
            x=(self._n % 6) * 40,
            y=(self._n // 6) * 40,
            params=values,
            part_id=str(self.record.id) if dut and self.record is not None else None,
        )
        pos = pin_positions(comp)
        names = {p.name for p in pin_defs(comp)}
        if kind in ("resistor", "capacitor"):
            nodes = {{"p": "1", "n": "2"}.get(k, k): v for k, v in nodes.items()}
        unknown = set(nodes) - names
        assert not unknown, f"{kind}: pinos {sorted(unknown)} não existem"
        sch.components.append(comp)
        for p in pin_defs(comp):
            node = nodes.get(
                p.name, f"nc_{ref}_{p.name}".lower().replace("+", "p").replace("-", "n")
            )
            x, y = pos[p.name]
            sch.labels.append(NetLabel(id=f"l{len(sch.labels)}", name=node, x=x, y=y))
        return comp

    def run(
        self, sch: Schematic, label: str, analysis: AnalysisKind = "tran", **params: str
    ) -> Plot:
        sch.analyses = [Analysis(kind=analysis, params=params)]
        records = {str(self.record.id): self.record} if self.record is not None else {}
        plan = SchematicPlan(sch, records)
        self.netlists[label] = plan.nominal().text
        res = plan.execute(self.backend)
        self.warnings += res.warnings
        return next(p for p in res.plots if p.kind == analysis)

    # results -----------------------------------------------------------------------------
    def check(
        self,
        id_: str,
        name: str,
        measured: float,
        expected: float,
        unit: str,
        tolerance_pct: float,
        method: str,
        latex: str,
        inputs: dict[str, pint.Quantity] | None = None,
        reference: BibRef | None = None,
        assumptions: Sequence[str] = (MODEL,),
    ) -> None:
        exp_q = Q_(expected, unit)
        name = _comma(name)
        self.tests.append(BenchTest(id_, name, Q_(measured, unit), exp_q, tolerance_pct, method))
        self.steps.append(
            record(
                id_,
                name,
                latex,
                output=exp_q,
                inputs=inputs or {},
                assumptions=assumptions,
                reference=reference,
            ).step
        )

    def curve(
        self,
        id_: str,
        title: str,
        x_label: str,
        x_unit: str,
        x: FloatArray,
        traces: list[tuple[str, str, FloatArray]],
        x_log: bool = False,
    ) -> None:
        idx = _decimate(np.asarray(x, dtype=float))
        xs = np.asarray(x, dtype=float)[idx]
        self.curves.append(
            Curve(
                id_,
                title,
                x_label,
                x_unit,
                [float(v) for v in xs],
                [Trace(n, u, _clean(np.asarray(v, dtype=float)[idx])) for n, u, v in traces],
                x_log,
            )
        )


def _vec(plot: Plot, name: str) -> FloatArray:
    return np.asarray(plot[name].data, dtype=float)


def _time(plot: Plot) -> FloatArray:
    assert plot.scale is not None
    return np.asarray(plot.vectors[plot.scale].data, dtype=float).real


def _at(plot: Plot, name: str, when: float) -> float:
    return float(np.interp(when, _time(plot), _vec(plot, name)))


def _mean(plot: Plot, name: str, t0: float, t1: float) -> float:
    t = _time(plot)
    sel = (t >= t0) & (t <= t1)
    return float(np.mean(_vec(plot, name)[sel]))


def _slope(x: FloatArray, y: FloatArray, x0: float, x1: float) -> float:
    sel = (x >= x0) & (x <= x1)
    if sel.sum() < 2:
        raise BenchError("pontos insuficientes para a inclinação")
    return float(np.polyfit(x[sel], y[sel], 1)[0])


def _ramp(t0: float, v0: float, t1: float, v1: float) -> str:
    head = f"0 {v0:.9g} " if t0 > 0 else ""
    return f"{head}{t0:.9g} {v0:.9g} {t1:.9g} {v1:.9g}"


def _q(value: float, unit: str) -> pint.Quantity:
    return Q_(value, unit)


# ------------------------------------------------------------------------------ sensors


def _lm35(c: _Ctx) -> None:
    vs, t0, t1 = c.f("vs"), c.f("tmin"), c.f("tmax")
    sens = c.p("sens")
    s = c.new("LM35")
    c.add(s, "vdc", "VS", {"p": "vs", "n": "0"}, dc=f"{vs:g}")
    c.add(
        s, "lm35", "S1", {"VS": "vs", "GND": "0", "OUT": "out"}, dut=True, temp=f"0 {t0:g} 1 {t1:g}"
    )
    tr = c.run(s, "transferência", tstop="1", tmax="2m")
    t = _time(tr)
    temp = t0 + (t1 - t0) * t
    vout = _vec(tr, "v(out)")
    vmax = max(vs - 1.5, 0.0)
    c.curve(
        "lm35",
        "Tensão de saída × temperatura",
        "Temperatura",
        "°C",
        temp,
        [("V(OUT)", "V", vout), ("Modelo: sens·T", "V", np.minimum(sens * temp, vmax))],
    )
    lin_hi = min(t1, vmax / sens if sens > 0 else t1)
    a, b = t0 + 0.1 * (lin_hi - t0), t0 + 0.9 * (lin_hi - t0)
    inputs = {"sens": _q(sens, "V/K"), "V_S": _q(vs, "V")}
    c.check(
        "LM-SENS",
        "Sensibilidade (inclinação da curva)",
        _slope(temp, vout, a, b),
        sens,
        "V/K",
        0.5,
        "Regressão linear de V(OUT) × T na faixa linear (10 % a 90 %).",
        r"S = \frac{\Delta V_{OUT}}{\Delta T}",
        inputs,
        LM35,
    )
    tm = min(max(25.0, t0), t1)
    c.check(
        "LM-25",
        f"Saída a {tm:g} °C",
        float(np.interp(tm, temp, vout)),
        min(sens * tm, vmax),
        "V",
        0.5,
        f"V(OUT) no instante em que a temperatura vale {tm:g} °C.",
        r"V_{OUT} = S \cdot T",
        inputs | {"T": _q(tm, "degC")},
        LM35,
    )
    if sens * t1 > vmax:
        c.check(
            "LM-SAT",
            "Saturação da saída (VS − 1,5 V)",
            float(np.max(vout)),
            vmax,
            "V",
            0.5,
            "Máximo de V(OUT) com a temperatura acima do limite.",
            r"V_{OUT,max} = V_S - 1{,}5\ \mathrm{V}",
            inputs,
        )


def _cvd[T: (float, FloatArray)](r0: float, a: float, b: float, t: T) -> T:
    return r0 * (1 + a * t + b * t * t)


def _pt100(c: _Ctx) -> None:
    i, tmax = c.f("iexc"), c.f("tmax")
    r0, a, b = c.p("r0"), c.p("a"), c.p("b")
    s = c.new("Pt100")
    c.add(s, "idc", "I1", {"p": "0", "n": "x"}, dc=f"{i:g}")
    c.add(s, "pt100", "RT1", {"1": "x", "2": "0"}, dut=True, temp=f"0 0 1 {tmax:g}")
    tr = c.run(s, "R(T)", tstop="1", tmax="2m")
    temp = tmax * _time(tr)
    r = _vec(tr, "v(x)") / i
    c.curve(
        "pt100",
        "Resistência × temperatura",
        "Temperatura",
        "°C",
        temp,
        [("R medida (V/I)", "Ω", r), ("IEC 60751", "Ω", _cvd(r0, a, b, temp))],
    )
    inp = {"R_0": _q(r0, "ohm"), "A": _q(a, "1/K"), "B": _q(b, "1/K^2")}
    tex = r"R(T) = R_0\,(1 + A\,T + B\,T^2)"
    method = "R = V/I com corrente de excitação constante, no instante da temperatura."
    c.check("PT-R0", "Resistência a 0 °C", float(r[0]), r0, "ohm", 0.1, method, tex, inp, IEC60751)
    if tmax >= 100:
        r100 = float(np.interp(100.0, temp, r))
        c.check(
            "PT-R100",
            "Resistência a 100 °C",
            r100,
            _cvd(r0, a, b, 100),
            "ohm",
            0.1,
            method,
            tex,
            inp,
            IEC60751,
        )
        c.check(
            "PT-ALFA",
            "Coeficiente α entre 0 e 100 °C",
            (r100 - r[0]) / (100 * r[0]),
            a + 100 * b,
            "1/K",
            0.2,
            "α = (R100 − R0)/(100 R0) com as resistências medidas.",
            r"\alpha = \frac{R_{100} - R_0}{100\,R_0} = A + 100\,B",
            inp,
            IEC60751,
        )
    c.check(
        "PT-RMAX",
        f"Resistência a {tmax:g} °C",
        float(r[-1]),
        _cvd(r0, a, b, tmax),
        "ohm",
        0.1,
        method,
        tex,
        inp,
        IEC60751,
    )
    c.check(
        "PT-AUTO",
        "Tensão no sensor a 0 °C (corrente de excitação)",
        float(r[0] * i),
        r0 * i,
        "V",
        0.1,
        "V(x) com a corrente de excitação; o modelo não tem autoaquecimento.",
        r"V = R_0\,I",
        inp | {"I": _q(i, "A")},
        IEC60751,
    )


def _thermocouple(c: _Ctx) -> None:
    kind = c.text("type").upper()
    if kind not in tc.TYPES:
        raise BenchError(f"Tipo de termopar desconhecido: {kind}")
    lo, hi = tc.range_c(kind)
    t0 = max(c.f("tmin"), lo)
    t1 = min(c.f("tmax"), hi)
    rl = c.f("rl")
    tref = c.p("tref")
    rloop = c.p("r")
    s = c.new("Termopar")
    prof = f"0 {t0:g} 1 {t1:g}"
    c.add(s, "thermocouple", "TC1", {"+": "p", "-": "0"}, dut=True, temp=prof)
    c.add(s, "resistor", "R1", {"p": "p", "n": "0"}, value="1g")
    c.add(s, "thermocouple", "TC2", {"+": "q", "-": "0"}, dut=True, temp=prof)
    c.add(s, "resistor", "RL", {"p": "q", "n": "0"}, value=f"{rl:g}")
    tr = c.run(s, "FEM", tstop="1", tmax="1m")
    temp = t0 + (t1 - t0) * _time(tr)
    v = _vec(tr, "v(p)")
    nist = np.array([tc.emf_mv(kind, x) - tc.emf_mv(kind, tref) for x in temp]) * 1e-3
    c.curve(
        "tc",
        f"Força eletromotriz do tipo {kind} (junta fria a {tref:g} °C)",
        "Temperatura",
        "°C",
        temp,
        [
            ("V em aberto", "V", v),
            ("NIST ITS-90", "V", nist),
            ("V com carga", "V", _vec(tr, "v(q)")),
        ],
    )
    inp = {"T_ref": _q(tref, "degC")}
    tex = r"V = E(T) - E(T_{ref})"
    for tm in sorted({min(max(100.0, t0), t1), t1}):
        exp = (tc.emf_mv(kind, tm) - tc.emf_mv(kind, tref)) * 1e-3
        c.check(
            f"TC-E{tm:g}",
            f"Tensão em aberto a {tm:g} °C",
            float(np.interp(tm, temp, v)),
            exp,
            "V",
            0.1 if abs(exp) > 1e-4 else 5.0,
            "V(+,−) em aberto (1 GΩ) no instante da temperatura.",
            tex,
            inp | {"T": _q(tm, "degC")},
            NIST_TC,
        )
    if t0 <= tref <= t1:
        sl = _slope(temp, v, max(t0, tref - 10), min(t1, tref + 10))
        seebeck = (tc.emf_mv(kind, tref + 0.5) - tc.emf_mv(kind, tref - 0.5)) * 1e-3
        c.check(
            "TC-SEEBECK",
            f"Coeficiente de Seebeck perto de {tref:g} °C",
            sl,
            seebeck,
            "V/K",
            1.0,
            "Inclinação de V × T em ±10 °C da junta fria.",
            r"S = \frac{dE}{dT}",
            inp,
            NIST_TC,
        )
    vq = float(_vec(tr, "v(q)")[-1])
    e_end = (tc.emf_mv(kind, t1) - tc.emf_mv(kind, tref)) * 1e-3
    c.check(
        "TC-CARGA",
        f"Tensão na carga de {rl:g} Ω a {t1:g} °C",
        vq,
        e_end * rl / (rl + rloop),
        "V",
        0.1,
        "Divisor entre a resistência do laço e a carga.",
        r"V_L = [E(T) - E(T_{ref})]\,\frac{R_L}{R_L + R_{laço}}",
        inp | {"R_L": _q(rl, "ohm"), "R_laço": _q(rloop, "ohm")},
        NIST_TC,
    )


def _loop_current(lo: float, hi: float, x: float) -> float:
    return 4e-3 + 16e-3 * min(max((x - lo) / (hi - lo), 0.0), 1.0)


def _tx420(c: _Ctx) -> None:
    vloop, rl = c.f("vloop"), c.f("rl")
    lo, hi, vmin = c.p("lo"), c.p("hi"), c.p("vmin")
    if hi == lo:
        raise BenchError("Início e fim da faixa iguais")
    s = c.new("4-20 mA")
    c.add(s, "vdc", "V1", {"p": "l", "n": "0"}, dc=f"{vloop:g}")
    c.add(s, "tx420", "TT1", {"+": "l", "-": "ai"}, dut=True, x=_ramp(0, lo, 1, hi))
    c.add(s, "resistor", "RL", {"p": "ai", "n": "0"}, value=f"{rl:g}")
    tr = c.run(s, "faixa", tstop="1", tmax="2m")
    x = lo + (hi - lo) * _time(tr)
    i = _vec(tr, "v(ai)") / rl
    c.curve("tx", "Corrente do laço × grandeza medida", "Grandeza", "", x, [("I do laço", "A", i)])
    inp = {"x_ini": _q(lo, ""), "x_fim": _q(hi, ""), "V_laço": _q(vloop, "V"), "R_L": _q(rl, "ohm")}
    tex = r"I = 4\ \mathrm{mA} + 16\ \mathrm{mA}\,\frac{x - x_{ini}}{x_{fim} - x_{ini}}"
    vfull = vmin + 20e-3 * rl
    if vloop < vfull:
        c.warnings.append(
            f"A fonte de {vloop:g} V não chega a {vfull:.3g} V (mínima para 20 mA "
            "nesta carga): a corrente fica abaixo do esperado no fim da faixa."
        )
    for frac, label in ((0.0, "início"), (0.5, "meio"), (1.0, "fim")):
        xv = lo + frac * (hi - lo)
        exp = _loop_current(lo, hi, xv) * min(
            1.0, (vloop / (vmin + _loop_current(lo, hi, xv) * rl))
        )
        c.check(
            f"TX-{int(4 + 16 * frac)}",
            f"Corrente no {label} da faixa (x = {xv:g})",
            float(np.interp(xv, x, i)),
            exp,
            "A",
            0.2,
            "V(RL)/RL no instante em que a grandeza vale x.",
            tex,
            inp,
            LOOP_420,
        )
    # second run: loop supply too low
    s2 = c.new("4-20 mA, fonte")
    c.add(s2, "vpwl", "V1", {"p": "l", "n": "0"}, points=f"0 0 1 {1.25 * vfull:.6g}")
    c.add(s2, "tx420", "TT1", {"+": "l", "-": "ai"}, dut=True, x=f"{hi:g}")
    c.add(s2, "resistor", "RL", {"p": "ai", "n": "0"}, value=f"{rl:g}")
    tr2 = c.run(s2, "tensão do laço", tstop="1", tmax="2m")
    vs = 1.25 * vfull * _time(tr2)
    i2 = _vec(tr2, "v(ai)") / rl
    c.curve(
        "tx-v",
        "Corrente no fim da faixa × tensão da fonte do laço",
        "Fonte do laço",
        "V",
        vs,
        [("I do laço", "A", i2)],
    )
    half = vfull / 2
    c.check(
        "TX-VMIN",
        f"Corrente com a fonte em {half:.3g} V (metade da mínima)",
        float(np.interp(half, vs, i2)),
        20e-3 * half / vfull,
        "A",
        0.5,
        "Abaixo da tensão mínima o transmissor não sustenta a corrente: "
        "I = I_fim·V_S/(V_min + I_fim·R_L).",
        r"I = \frac{I_{fim}\,V_S}{V_{min} + I_{fim}\,R_L},\quad "
        r"V_{S,min} = V_{min} + 20\ \mathrm{mA}\cdot R_L",
        {"V_min": _q(vmin, "V"), "R_L": _q(rl, "ohm"), "V_S": _q(half, "V")},
        LOOP_420,
        (MODEL, "Tensão mínima do transmissor: valor didático do símbolo."),
    )


def _rtd_temp(r0: float, a: float, b: float, r: float) -> float:
    return (-a + math.sqrt(max(a * a - 4 * b * (1 - r / r0), 0.0))) / (2 * b)


def _tx420_rtd(c: _Ctx) -> None:
    vloop, rl, rw, dw = c.f("vloop"), c.f("rl"), c.f("rlead"), c.f("dlead")
    lo, hi = c.p("lo"), c.p("hi")
    r0, a, b = c.p("r0"), c.p("a"), c.p("b")
    if hi <= lo:
        raise BenchError("O fim da faixa deve ser maior que o início")
    s = c.new("RTD 3 fios")
    c.add(s, "vdc", "V1", {"p": "l", "n": "0"}, dc=f"{vloop:g}")
    c.add(s, "tx420_rtd", "TT1", {"+": "l", "-": "ai", "1": "t1", "2": "t2", "3": "t3"}, dut=True)
    c.add(s, "resistor", "RL", {"p": "ai", "n": "0"}, value=f"{rl:g}")
    c.add(s, "resistor", "RW1", {"p": "t1", "n": "x"}, value=f"{rw + dw:g}")
    c.add(s, "resistor", "RW2", {"p": "y", "n": "t2"}, value=f"{rw:g}")
    c.add(s, "resistor", "RW3", {"p": "y", "n": "t3"}, value=f"{rw:g}")
    c.add(
        s,
        "pt100",
        "RT1",
        {"1": "x", "2": "y"},
        r0=f"{r0:.9g}",
        a=f"{a:.9g}",
        b=f"{b:.9g}",
        temp=_ramp(0, lo, 1, hi),
    )
    tr = c.run(s, "laço", tstop="1", tmax="2m")
    temp = lo + (hi - lo) * _time(tr)
    i = _vec(tr, "v(ai)") / rl
    read = _vec(tr, "v(tt1_t)")
    c.curve(
        "rtd-i",
        "Corrente do laço × temperatura do sensor",
        "Temperatura",
        "°C",
        temp,
        [("I do laço", "A", i)],
    )
    c.curve(
        "rtd-t",
        "Temperatura lida pelo transmissor",
        "Temperatura",
        "°C",
        temp,
        [("Lida", "°C", read), ("Real", "°C", temp)],
    )
    inp = {"R_0": _q(r0, "ohm"), "R_fio": _q(rw, "ohm"), "ΔR_fio": _q(dw, "ohm")}
    tm = (lo + hi) / 2
    t_read = _rtd_temp(r0, a, b, _cvd(r0, a, b, tm) + dw)
    c.check(
        "RTD-T",
        f"Temperatura lida com o sensor a {tm:g} °C",
        float(np.interp(tm, temp, read)),
        t_read,
        "degC",
        0.1 if abs(t_read) > 1 else 5,
        "Nó <ref>_t do transmissor. Fios iguais se cancelam; a diferença ΔR do fio 1 "
        "aparece como erro.",
        r"R_{med} = \frac{V_{13} - V_{32}}{I} = R(T) + \Delta R_{fio},\quad "
        r"T_{lida} = R^{-1}(R_{med})",
        inp,
        IEC60751,
    )
    for frac in (0.0, 0.5, 1.0):
        tv = lo + frac * (hi - lo)
        tl = _rtd_temp(r0, a, b, _cvd(r0, a, b, tv) + dw)
        c.check(
            f"RTD-I{int(4 + 16 * frac)}",
            f"Corrente do laço a {tv:g} °C",
            float(np.interp(tv, temp, i)),
            _loop_current(lo, hi, tl),
            "A",
            0.2,
            "V(RL)/RL no instante da temperatura.",
            r"I = 4\ \mathrm{mA} + 16\ \mathrm{mA}\,\frac{T_{lida} - T_{ini}}{T_{fim} - T_{ini}}",
            inp,
            LOOP_420,
        )


def _acs712(c: _Ctx) -> None:
    vcc, imax = c.f("vcc"), c.f("imax")
    sens, rip, bw = c.p("sens"), c.p("rip"), c.p("bw")
    s = c.new("ACS712")
    c.add(s, "vdc", "VCC", {"p": "vcc", "n": "0"}, dc=f"{vcc:g}")
    c.add(s, "ipwl", "I1", {"p": "m", "n": "ip"}, points=f"0 {-imax:g} 1 {imax:g}")
    c.add(
        s,
        "acs712",
        "S1",
        {"IP+": "ip", "IP-": "m", "VCC": "vcc", "OUT": "out", "GND": "0"},
        dut=True,
    )
    c.add(s, "resistor", "RM", {"p": "m", "n": "0"}, value="1")
    tr = c.run(s, "transferência", tstop="1", tmax="2m")
    i = -imax + 2 * imax * _time(tr)
    vout = _vec(tr, "v(out)")
    c.curve(
        "acs",
        "Tensão de saída × corrente medida",
        "Corrente IP+ → IP−",
        "A",
        i,
        [("V(OUT)", "V", vout), ("Modelo", "V", vcc / 2 + sens * i)],
    )
    inp = {"S": _q(sens, "V/A"), "V_CC": _q(vcc, "V")}
    c.check(
        "ACS-ZERO",
        "Saída sem corrente",
        float(np.interp(0.0, i, vout)),
        vcc / 2,
        "V",
        0.2,
        "V(OUT) quando a corrente passa por zero.",
        r"V_{OUT}(0) = V_{CC}/2",
        inp,
        ACS712,
    )
    c.check(
        "ACS-SENS",
        "Sensibilidade",
        _slope(i, vout, -0.8 * imax, 0.8 * imax),
        sens,
        "V/A",
        0.5,
        "Regressão linear de V(OUT) × I em ±80 % da faixa.",
        r"S = \frac{\Delta V_{OUT}}{\Delta I_P}",
        inp,
        ACS712,
    )
    vip = _vec(tr, "v(ip)") - _vec(tr, "v(m)")
    c.check(
        "ACS-RIP",
        "Resistência do condutor primário",
        float(vip[-1] / i[-1]),
        rip,
        "ohm",
        0.5,
        "V(IP+, IP−)/I no fim da rampa.",
        r"R_{IP} = V_{IP}/I_P",
        {"R_IP": _q(rip, "ohm")},
        ACS712,
    )
    s2 = c.new("ACS712 AC")
    c.add(s2, "vdc", "VCC", {"p": "vcc", "n": "0"}, dc=f"{vcc:g}")
    c.add(s2, "idc", "I1", {"p": "m", "n": "ip"}, dc="0", ac="1")
    c.add(
        s2,
        "acs712",
        "S1",
        {"IP+": "ip", "IP-": "m", "VCC": "vcc", "OUT": "out", "GND": "0"},
        dut=True,
    )
    c.add(s2, "resistor", "RM", {"p": "m", "n": "0"}, value="1")
    ac = c.run(
        s2,
        "banda",
        "ac",
        variation="dec",
        points="50",
        fstart=f"{bw / 1000:g}",
        fstop=f"{bw * 100:g}",
    )
    assert ac.scale is not None
    f = np.asarray(ac.vectors[ac.scale].data).real
    mag = np.abs(np.asarray(ac["v(out)"].data)) / sens
    db = 20 * np.log10(np.maximum(mag, 1e-30))
    c.curve(
        "acs-ac",
        "Resposta em frequência (relativa à sensibilidade)",
        "Frequência",
        "Hz",
        f,
        [("|V(OUT)|/(S·I)", "dB", db)],
        x_log=True,
    )
    c.check(
        "ACS-BW",
        "Banda passante (−3 dB)",
        crossing(f, -db, 10 * math.log10(2)),
        bw,
        "Hz",
        1.0,
        "Frequência em que |V(OUT)| cai 3 dB (análise AC).",
        r"f_{-3dB} = \frac{1}{2\pi RC}",
        {"f_c": _q(bw, "Hz")},
        ACS712,
        (MODEL, "Filtro de 1ª ordem na saída."),
    )


def _potentiometer(c: _Ctx) -> None:
    v, rl = c.f("vin"), c.f("rl")
    r = c.p("r")
    s = c.new("Potenciômetro")
    pos = "0 0 1 1"
    c.add(s, "vdc", "V1", {"p": "a1", "n": "0"}, dc=f"{v:g}")
    c.add(s, "potentiometer", "P1", {"a": "a1", "b": "0", "w": "w1"}, dut=True, pos=pos)
    c.add(s, "resistor", "R1", {"p": "w1", "n": "0"}, value="1g")
    c.add(s, "vdc", "V2", {"p": "a2", "n": "0"}, dc=f"{v:g}")
    c.add(s, "potentiometer", "P2", {"a": "a2", "b": "0", "w": "w2"}, dut=True, pos=pos)
    c.add(s, "resistor", "RL", {"p": "w2", "n": "0"}, value=f"{rl:g}")
    tr = c.run(s, "posição", tstop="1", tmax="2m")
    x = _time(tr)
    w1, w2 = _vec(tr, "v(w1)"), _vec(tr, "v(w2)")
    c.curve(
        "pot",
        "Tensão no cursor × posição",
        "Posição (0 = a, 1 = b)",
        "",
        x,
        [("Sem carga", "V", w1), (f"Com carga de {rl:g} Ω", "V", w2)],
    )
    inp = {"R": _q(r, "ohm"), "V": _q(v, "V")}
    c.check(
        "POT-R",
        "Resistência total a-b",
        v / abs(_at(tr, "i(v1)", 0.5)),
        r,
        "ohm",
        0.2,
        "V/I da fonte com o cursor sem carga.",
        r"R_{ab} = R",
        inp,
        DIVIDER,
    )
    c.check(
        "POT-25",
        "Cursor a 25 % (sem carga)",
        float(np.interp(0.25, x, w1)),
        0.75 * v,
        "V",
        0.2,
        "V(w) com o cursor a 25 % do caminho de a para b.",
        r"V_w = V\,(1 - x)",
        inp | {"x": _q(0.25, "")},
        DIVIDER,
    )
    r1 = r2 = r / 2
    rp = r2 * rl / (r2 + rl)
    c.check(
        "POT-CARGA",
        f"Cursor no meio com carga de {rl:g} Ω",
        float(np.interp(0.5, x, w2)),
        v * rp / (r1 + rp),
        "V",
        0.2,
        "V(w) com a carga ligada entre o cursor e b.",
        r"V_w = V\,\frac{R_2 \parallel R_L}{R_1 + R_2 \parallel R_L}",
        inp | {"R_L": _q(rl, "ohm")},
        DIVIDER,
    )


SENSORS: dict[str, Callable[[_Ctx], None]] = {
    "lm35": _lm35,
    "pt100": _pt100,
    "thermocouple": _thermocouple,
    "tx420": _tx420,
    "tx420_rtd": _tx420_rtd,
    "acs712": _acs712,
    "potentiometer": _potentiometer,
}


# ------------------------------------------------------------------------------ actuators


def _relay(c: _Ctx) -> None:
    vnom, rcoil, pull, ron = c.p("vnom"), c.p("rcoil"), c.p("pull"), c.p("ron")
    vload, rload = c.f("vload"), c.f("rload")
    vmax = 1.2 * vnom
    s = c.new("Relé")
    c.add(s, "vpwl", "VC", {"p": "a1", "n": "0"}, points=f"0 0 1 {vmax:g} 2 0")
    c.add(s, "vdc", "VL", {"p": "com", "n": "0"}, dc=f"{vload:g}")
    c.add(s, "relay", "K1", {"A1": "a1", "A2": "0", "COM": "com", "NA": "na", "NF": "nf"}, dut=True)
    c.add(s, "resistor", "RNA", {"p": "na", "n": "0"}, value=f"{rload:g}")
    c.add(s, "resistor", "RNF", {"p": "nf", "n": "0"}, value=f"{rload:g}")
    tr = c.run(s, "bobina", tstop="2", tmax="1m")
    t = _time(tr)
    vc = _vec(tr, "v(a1)")
    na, nf = _vec(tr, "v(na)"), _vec(tr, "v(nf)")
    c.curve(
        "rele",
        "Bobina e contatos (rampa de subida e descida)",
        "Tempo",
        "s",
        t,
        [("Bobina", "V", vc), ("NA", "V", na), ("NF", "V", nf)],
    )
    up = t <= 1
    t_on = crossing(t[up], na[up], vload / 2)
    t_off = crossing(t[~up], na[~up], vload / 2, rising=False)
    inp = {"V_nom": _q(vnom, "V"), "k_op": _q(pull, "")}
    hyst = (MODEL, "Histerese fixa de ±0,1 V do modelo (vh da chave do ngspice).")
    c.check(
        "RL-OP",
        "Tensão de operação (NA fecha)",
        float(np.interp(t_on, t, vc)),
        pull * vnom + 0.1,
        "V",
        0.5,
        "Tensão da bobina quando NA atinge metade da tensão de carga, na rampa de subida.",
        r"V_{op} = k_{op}\,V_{nom} + V_h",
        inp,
        NGSPICE_SW,
        hyst,
    )
    c.check(
        "RL-DESOP",
        "Tensão de desoperação (NA abre)",
        float(np.interp(t_off, t, vc)),
        pull * vnom - 0.1,
        "V",
        0.5,
        "Tensão da bobina quando NA cai a metade, na descida.",
        r"V_{des} = k_{op}\,V_{nom} - V_h",
        inp,
        NGSPICE_SW,
        hyst,
    )
    i_coil = abs(_at(tr, "i(vc)", vnom / vmax))
    c.check(
        "RL-BOB",
        "Resistência da bobina",
        vnom / i_coil,
        rcoil,
        "ohm",
        0.2,
        "V/I da fonte da bobina na tensão nominal.",
        r"R_{bob} = V_{nom}/I_{bob}",
        {"R_bob": _q(rcoil, "ohm")},
        NGSPICE_SW,
    )
    v_na = _at(tr, "v(na)", 1.0)
    c.check(
        "RL-CONT",
        "Resistência do contato COM-NA",
        (vload - v_na) / (v_na / rload),
        ron,
        "ohm",
        1.0,
        "Queda COM-NA dividida pela corrente da carga, bobina energizada.",
        r"R_{cont} = \frac{V_{COM} - V_{NA}}{V_{NA}/R_{carga}}",
        {"R_on": _q(ron, "ohm")},
        NGSPICE_SW,
    )


def _dc_motor_response(
    r: float, l_: float, ke: float, kt: float, j: float, b: float, v: float, t: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Exact step response of the linear armature + shaft model (state i, ω)."""
    a = np.array([[-r / l_, -ke / l_], [kt / j, -b / j]])
    bv = np.array([v / l_, 0.0])
    x_inf = -np.linalg.solve(a, bv)
    out = np.empty((len(t), 2))
    for k, tk in enumerate(t):
        out[k] = x_inf - expm(a * tk) @ x_inf
    return out[:, 0], out[:, 1]


def _dc_motor(c: _Ctx) -> None:
    v = c.f("v")
    r, l_, ke, kt, j, b = (c.p(n) for n in ("r", "l", "ke", "kt", "j", "b"))
    if min(r, l_, kt, j, b) <= 0 or ke < 0:
        raise BenchError("Use valores positivos para R, L, kt, J e b")
    den = r * b + kt * ke
    w_inf = kt * v / den
    tau_m = j * r / den
    t_on = 1e-3
    tstop = t_on + 12 * tau_m + 10 * l_ / r
    s = c.new("Motor CC")
    c.add(s, "vpwl", "VA", {"p": "a", "n": "0"}, points=f"0 0 {t_on:g} 0 {t_on + 1e-6:g} {v:g}")
    c.add(s, "dc_motor", "M1", {"+": "a", "-": "0"}, dut=True, tl="0")
    tr = c.run(s, "partida", tstop=f"{tstop:.6g}", tmax=f"{min(tstop / 4000, l_ / r / 5):.6g}")
    t = _time(tr)
    w = _vec(tr, "v(m1_w)")
    ia = -_vec(tr, "i(va)")
    i_an, w_an = _dc_motor_response(r, l_, ke, kt, j, b, v, np.maximum(t - t_on - 1e-6, 0))
    rpm = 60 / (2 * math.pi)
    c.curve(
        "mcc-w",
        "Partida em vazio: velocidade",
        "Tempo",
        "s",
        t,
        [("ω simulada", "rpm", w * rpm), ("ω analítica", "rpm", w_an * rpm)],
    )
    c.curve(
        "mcc-i",
        "Partida em vazio: corrente de armadura",
        "Tempo",
        "s",
        t,
        [("i simulada", "A", ia), ("i analítica", "A", i_an)],
    )
    inp = {
        "V": _q(v, "V"),
        "R_a": _q(r, "ohm"),
        "k_e": _q(ke, "V*s/rad"),
        "k_t": _q(kt, "N*m/A"),
        "J": _q(j, "kg*m^2"),
        "b": _q(b, "N*m*s/rad"),
    }
    c.check(
        "MCC-W0",
        "Velocidade em vazio (regime)",
        float(w[-1]),
        w_inf,
        "rad/s",
        0.5,
        "ω no fim do ensaio (12 constantes de tempo).",
        r"\omega_0 = \frac{k_t\,V}{R_a\,b + k_t\,k_e}",
        inp,
        DC_MOTOR,
    )
    c.check(
        "MCC-I0",
        "Corrente em vazio (regime)",
        float(ia[-1]),
        b * w_inf / kt,
        "A",
        0.5,
        "Corrente no fim do ensaio: só vence o atrito viscoso.",
        r"I_0 = \frac{b\,\omega_0}{k_t}",
        inp,
        DC_MOTOR,
    )
    t63_an = crossing(t - t_on, w_an, 0.632 * w_inf)
    c.check(
        "MCC-T63",
        "Tempo até 63 % da velocidade",
        crossing(t - t_on, w, 0.632 * w_inf),
        t63_an,
        "s",
        1.0,
        "Instante em que ω atinge 63,2 % do regime; esperado pela solução "
        "exata do modelo linear (2ª ordem).",
        r"\tau_m \approx \frac{J\,R_a}{R_a\,b + k_t\,k_e}",
        inp | {"τ_m": _q(tau_m, "s")},
        DC_MOTOR,
    )
    ipk = float(np.max(ia))
    ipk_an = float(np.max(i_an))
    c.check(
        "MCC-IPK",
        "Pico da corrente de partida",
        ipk,
        ipk_an,
        "A",
        1.0,
        "Máximo de i(t); esperado pela solução exata (limite V/R se L → 0).",
        r"I_{pk} \le V/R_a",
        inp,
        DC_MOTOR,
    )
    # load: half the stall torque, in steady state
    t_stall = kt * v / r
    tl = c.f("load") * t_stall
    s2 = c.new("Motor CC com carga")
    c.add(s2, "vpwl", "VA", {"p": "a", "n": "0"}, points=f"0 0 {t_on:g} 0 {t_on + 1e-6:g} {v:g}")
    c.add(s2, "dc_motor", "M1", {"+": "a", "-": "0"}, dut=True, tl=f"{tl:.9g}")
    tr2 = c.run(s2, "carga", tstop=f"{tstop:.6g}", tmax=f"{min(tstop / 4000, l_ / r / 5):.6g}")
    w_load = (kt * v - r * tl) / den
    c.check(
        "MCC-WL",
        f"Velocidade com carga de {tl:.3g} N·m",
        float(_vec(tr2, "v(m1_w)")[-1]),
        w_load,
        "rad/s",
        0.5,
        "ω no fim do ensaio com torque de carga constante.",
        r"\omega = \frac{k_t\,V - R_a\,T_L}{R_a\,b + k_t\,k_e}",
        inp | {"T_L": _q(tl, "N*m")},
        DC_MOTOR,
    )
    torques = np.unique(np.append(np.linspace(0, t_stall, 51), tl))
    measured = np.full(len(torques), np.nan)
    measured[0] = w[-1] * rpm
    measured[int(np.argmin(np.abs(torques - tl)))] = _vec(tr2, "v(m1_w)")[-1] * rpm
    c.curve(
        "mcc-tw",
        "Característica torque × velocidade (regime)",
        "Torque de carga",
        "N·m",
        torques,
        [("ω analítica", "rpm", (kt * v - r * torques) / den * rpm), ("Ensaios", "rpm", measured)],
    )


def _heater(c: _Ctx) -> None:
    v = c.f("v")
    r, rth, cth = c.p("r"), c.p("rth"), c.p("cth")
    tamb = c.p("tamb")
    tau = rth * cth
    p = v * v / r
    tstop = 6 * tau
    s = c.new("Aquecedor")
    c.add(s, "vpwl", "V1", {"p": "a", "n": "0"}, points=f"0 0 {tau / 1000:.6g} {v:g}")
    c.add(s, "heater", "H1", {"1": "a", "2": "0"}, dut=True)
    tr = c.run(s, "degrau", tstop=f"{tstop:.6g}", tmax=f"{tau / 200:.6g}")
    t = _time(tr)
    temp = _vec(tr, "v(h1_temp)")
    t_an = tamb + p * rth * (1 - np.exp(-np.maximum(t - tau / 2000, 0) / tau))
    c.curve(
        "aq",
        "Temperatura do corpo após o degrau de tensão",
        "Tempo",
        "s",
        t,
        [("Simulada", "°C", temp), ("Analítica", "°C", t_an)],
    )
    inp = {
        "V": _q(v, "V"),
        "R": _q(r, "ohm"),
        "R_th": _q(rth, "K/W"),
        "C_th": _q(cth, "J/K"),
        "T_amb": _q(tamb, "degC"),
    }
    rise = p * rth * (1 - math.exp(-6))
    c.check(
        "AQ-TF",
        "Elevação de temperatura após 6 τ",
        float(temp[-1] - tamb),
        rise,
        "K",
        0.5,
        "T(6τ) − T_amb.",
        r"\Delta T = P\,R_{th}\,(1 - e^{-t/\tau}),\ P = V^2/R",
        inp,
        LUMPED,
    )
    c.check(
        "AQ-TAU",
        "Constante de tempo térmica",
        crossing(t, temp - tamb, 0.632 * p * rth),
        tau,
        "s",
        1.0,
        "Instante em que a elevação atinge 63,2 % do valor final.",
        r"\tau = R_{th}\,C_{th}",
        inp,
        LUMPED,
    )
    c.check(
        "AQ-P",
        "Potência dissipada",
        v * abs(_at(tr, "i(v1)", tstop)),
        p,
        "W",
        0.2,
        "V × I da fonte.",
        r"P = V^2/R",
        inp,
        LUMPED,
    )


def _switch_manual(c: _Ctx) -> None:
    v, rs, t_close = c.f("v"), c.f("rs"), c.f("tclose")
    ron = c.p("ron")
    s = c.new("Botão")
    c.add(s, "vdc", "V1", {"p": "a", "n": "0"}, dc=f"{v:g}")
    c.add(s, "resistor", "RS", {"p": "a", "n": "x"}, value=f"{rs:g}")
    c.add(
        s,
        "switch_manual",
        "B1",
        {"1": "x", "2": "0"},
        dut=True,
        state=f"0 0 {t_close:g} 0 {t_close * 1.001:g} 1",
    )
    tr = c.run(s, "acionamento", tstop=f"{2 * t_close:g}", tmax=f"{t_close / 500:g}")
    t = _time(tr)
    vx = _vec(tr, "v(x)")
    c.curve("bt", "Tensão na chave (abre → fecha)", "Tempo", "s", t, [("V(chave)", "V", vx)])
    i_on = (v - vx[-1]) / rs
    c.check(
        "BT-RON",
        "Resistência fechada",
        float(vx[-1] / i_on),
        ron,
        "ohm",
        1.0,
        "V(chave)/I com a chave fechada.",
        r"R_{on} = V/I",
        {"R_on": _q(ron, "ohm")},
        NGSPICE_SW,
    )
    c.check(
        "BT-T",
        "Instante do fechamento",
        crossing(t, -vx, -v / 2),
        t_close * 1.0005,
        "s",
        0.5,
        "Instante em que V(chave) cai a metade.",
        r"t = t_{aperto}",
        {"t": _q(t_close, "s")},
        NGSPICE_SW,
    )


def _pump_plant(c: _Ctx) -> None:
    ai, vloop, rl = c.f("ai"), c.f("vloop"), c.f("rl")
    fnom, accel, pmax, prange = c.p("fnom"), c.p("accel"), c.p("pmax"), c.p("prange")
    demand = c.p("demand")
    tau = accel / 3
    t0 = 0.1
    tstop = t0 + 12 * tau
    s = c.new("Planta de bombeamento")
    c.add(s, "vdc", "VAI", {"p": "ai", "n": "0"}, dc=f"{ai:g}")
    c.add(s, "vpwl", "VRUN", {"p": "run", "n": "0"}, points=f"0 0 {t0:g} 0 {t0 + 1e-4:g} 24")
    c.add(s, "vdc", "VL", {"p": "l", "n": "0"}, dc=f"{vloop:g}")
    c.add(
        s,
        "pump_plant",
        "PL1",
        {"AI": "ai", "GND": "0", "RUN": "run", "COM": "0", "PT+": "l", "PT-": "pt"},
        dut=True,
    )
    c.add(s, "resistor", "RL", {"p": "pt", "n": "0"}, value=f"{rl:g}")
    tr = c.run(s, "partida", tstop=f"{tstop:.6g}", tmax=f"{tau / 100:.6g}")
    t = _time(tr)
    f, p = _vec(tr, "v(pl1_f)"), _vec(tr, "v(pl1_p)")
    c.curve(
        "pl",
        "Frequência e pressão na partida",
        "Tempo",
        "s",
        t,
        [
            ("f", "Hz", f),
            ("p", "bar", p),
            ("I do transmissor × 1000", "mA", _vec(tr, "v(pt)") / rl * 1e3),
        ],
    )
    f_ref = fnom * min(max(ai / 10, 0), 1)
    inp = {
        "f_nom": _q(fnom, "Hz"),
        "V_AI": _q(ai, "V"),
        "t_acel": _q(accel, "s"),
        "p_max": _q(pmax, "bar"),
        "consumo": _q(demand, ""),
    }
    c.check(
        "PL-F",
        "Frequência em regime",
        float(f[-1]),
        f_ref,
        "Hz",
        0.5,
        "Nó <ref>_f no fim do ensaio.",
        r"f = f_{nom}\,\frac{V_{AI}}{10\ \mathrm{V}}",
        inp,
        WEG_CFW500,
        (MODEL, "Rampa modelada como atraso de 1ª ordem, τ = t_acel/3 (didático)."),
    )
    c.check(
        "PL-TAU",
        "Tempo até 63 % da frequência",
        crossing(t, f, 0.632 * f_ref) - t0,
        tau,
        "s",
        1.0,
        "Do comando RUN até f = 63,2 % da referência.",
        r"\tau = t_{acel}/3",
        inp,
        WEG_CFW500,
        (MODEL, "Rampa modelada como atraso de 1ª ordem (didático)."),
    )
    p_exp = pmax * (f_ref / fnom) ** 2 * (1 - 0.5 * min(max(demand, 0), 1))
    c.check(
        "PL-P",
        "Pressão em regime",
        float(p[-1]),
        p_exp,
        "bar",
        0.5,
        "Nó <ref>_p no fim do ensaio (lei de afinidade).",
        r"p = p_{max}\,(f/f_{nom})^2\,(1 - \text{consumo}/2)",
        inp,
        assumptions=(MODEL, "Curva da bomba didática (leis de afinidade)."),
    )
    i_exp = 4e-3 + 16e-3 * min(max(p_exp / prange, 0), 1)
    c.check(
        "PL-I",
        "Corrente do transmissor de pressão",
        float(_vec(tr, "v(pt)")[-1] / rl),
        i_exp,
        "A",
        0.5,
        "V(RL)/RL no fim do ensaio.",
        r"I = 4\ \mathrm{mA} + 16\ \mathrm{mA}\,p/p_{FE}",
        {"p_FE": _q(prange, "bar")},
        LOOP_420,
    )


def _motor_params(c: _Ctx, src: Callable[[str], float] | None = None) -> InductionParams:
    g = src or c.p
    return InductionParams(
        rs=g("rs"),
        rr=g("rr"),
        xls=g("xls"),
        xlr=g("xlr"),
        xm=g("xm"),
        poles=int(g("poles")),
        fnom=g("fnom"),
        j=g("j"),
        b=g("b"),
    )


def _motor_defaults(name: str) -> float:
    return parse_value(symbol("induction_motor").param(name).default)


def _induction_motor(c: _Ctx) -> None:
    vline, f, tl = c.f("vline"), c.f("freq"), c.f("tl")
    m = _motor_params(c)
    quad = c.text("load") == "quadrática"
    tstop = c.f("tstop")
    s = c.new("Motor de indução")
    c.add(
        s,
        "v3ph",
        "V1",
        {"a": "a", "b": "b", "c": "c", "n": "0"},
        vrms=f"{vline / math.sqrt(3):.6f}",
        freq=f"{f:g}",
    )
    c.add(s, "induction_motor", "M1", {"A": "a", "B": "b", "C": "c"}, dut=True, tl=f"{tl:g}")
    tr = c.run(s, "partida direta", tstop=f"{tstop:g}")
    t = _time(tr)
    c.curve(
        "mit-t",
        "Partida direta",
        "Tempo",
        "s",
        t,
        [
            ("Velocidade", "rpm", _vec(tr, "v(m1_rpm)")),
            ("Torque", "N·m", _vec(tr, "v(m1_te)")),
            ("Corrente de linha", "A", _vec(tr, "v(m1_i)")),
        ],
    )
    try:
        ref = steady_state(m, vline, f, tl, quadratic=quad)
    except ValueError as exc:
        raise BenchError(f"Sem ponto de operação estável com {tl:g} N·m: {exc}") from exc
    t_end = (0.9 * tstop, tstop)
    inp = {
        "V_linha": _q(vline, "V"),
        "f": _q(f, "Hz"),
        "T_L": _q(tl, "N*m"),
        "R_1": _q(m.rs, "ohm"),
        "R_2": _q(m.rr, "ohm"),
        "X_m": _q(m.xm, "ohm"),
    }
    tex = r"T = \frac{3\,I_2^2\,R_2/s}{\omega_s},\ T = T_L + b\,\omega"
    tail = "Média nos últimos 10 % do ensaio; esperado pelo circuito equivalente por fase."
    c.check(
        "MIT-N",
        "Velocidade em regime",
        _mean(tr, "v(m1_rpm)", *t_end),
        ref.speed_rpm,
        "rpm",
        0.3,
        tail,
        tex,
        inp,
        CHAPMAN,
    )
    c.check(
        "MIT-I",
        "Corrente de linha em regime",
        _mean(tr, "v(m1_i)", *t_end),
        ref.i1,
        "A",
        1.5,
        tail,
        r"I_1 = \frac{V_1}{Z_1 + Z_m \parallel Z_2}",
        inp,
        CHAPMAN,
    )
    c.check(
        "MIT-T",
        "Torque em regime",
        _mean(tr, "v(m1_te)", *t_end),
        ref.torque,
        "N*m",
        1.5,
        tail,
        tex,
        inp,
        CHAPMAN,
    )
    slips = np.linspace(1, 1e-3, 120)
    pts = [operating_point(m, vline, f, float(sl)) for sl in slips]
    c.curve(
        "mit-tw",
        "Torque × velocidade (circuito equivalente)",
        "Velocidade",
        "rpm",
        np.array([p.speed_rpm for p in pts]),
        [
            ("Torque", "N·m", np.array([p.torque for p in pts])),
            ("Corrente", "A", np.array([p.i1 for p in pts])),
        ],
    )


def _vfd(c: _Ctx) -> None:
    ai, tl = c.f("ai"), c.f("tl")
    vnom, fnom, accel, boost = c.p("vnom"), c.p("fnom"), c.p("accel"), c.p("boost")
    fmin = c.p("fmin")
    f_ref = max(fnom * min(max(ai / 10, 0), 1), fmin)
    t_ramp = accel * f_ref / fnom
    tstop = t_ramp + 1.5
    s = c.new("Inversor V/f")
    c.add(s, "vdc", "V1", {"p": "ai", "n": "0"}, dc=f"{ai:g}")
    c.add(s, "vdc", "V2", {"p": "run", "n": "0"}, dc="24")
    c.add(
        s,
        "vfd",
        "INV1",
        {"AI": "ai", "GND": "0", "RUN": "run", "COM": "0", "U": "u", "V": "v", "W": "w"},
        dut=True,
    )
    c.add(
        s, "induction_motor", "M1", {"A": "u", "B": "v", "C": "w"}, tl=f"{tl:g}", load="quadrática"
    )
    tr = c.run(s, "rampa", tstop=f"{tstop:g}")
    t = _time(tr)
    c.curve(
        "inv",
        "Rampa de aceleração",
        "Tempo",
        "s",
        t,
        [
            ("Frequência", "Hz", _vec(tr, "v(inv1_f)")),
            ("Tensão de linha comandada", "V", _vec(tr, "v(inv1_v)")),
            ("Velocidade do motor / 10", "rpm", _vec(tr, "v(m1_rpm)") / 10),
        ],
    )
    inp = {
        "V_AI": _q(ai, "V"),
        "f_nom": _q(fnom, "Hz"),
        "t_acel": _q(accel, "s"),
        "boost": _q(boost, ""),
        "V_nom": _q(vnom, "V"),
    }
    if t_ramp > 0:
        c.check(
            "INV-RAMPA",
            "Frequência na metade da rampa",
            _at(tr, "v(inv1_f)", t_ramp / 2),
            f_ref / 2,
            "Hz",
            1.0,
            "f no instante t_acel·(f_ref/f_nom)/2.",
            r"f(t) = f_{nom}\,\frac{t}{t_{acel}}",
            inp,
            WEG_CFW500,
        )
    c.check(
        "INV-F",
        "Frequência final",
        _at(tr, "v(inv1_f)", tstop),
        f_ref,
        "Hz",
        0.2,
        "Nó <ref>_f no fim do ensaio.",
        r"f = f_{nom}\,V_{AI}/10\ \mathrm{V}",
        inp,
        WEG_CFW500,
    )
    v_cmd = min(vnom * (boost + (1 - boost) * f_ref / fnom), vnom)
    c.check(
        "INV-VF",
        "Tensão de linha comandada (lei V/f)",
        _at(tr, "v(inv1_v)", tstop),
        v_cmd,
        "V",
        0.2,
        "Nó <ref>_v no fim do ensaio.",
        r"V = V_{nom}\,[\,\text{boost} + (1 - \text{boost})\,f/f_{nom}]",
        inp,
        WEG_CFW500,
    )
    mot = _motor_params(c, _motor_defaults)
    if f_ref > 0:
        ref = steady_state(mot, v_cmd, f_ref, tl, quadratic=True)
        c.check(
            "INV-N",
            "Velocidade do motor (padrão da biblioteca) em regime",
            _mean(tr, "v(m1_rpm)", tstop - 0.3, tstop),
            ref.speed_rpm,
            "rpm",
            0.5,
            "Média nos últimos 0,3 s; circuito equivalente na frequência e tensão comandadas.",
            r"T(s) = T_L\,(\omega/\omega_{nom})^2",
            inp | {"T_L": _q(tl, "N*m")},
            CHAPMAN,
        )


def _soft_starter(c: _Ctx) -> None:
    vline, tl = c.f("vline"), c.f("tl")
    vinit, tacc, ilim = c.p("vinit"), c.p("tacc"), c.p("ilim")
    ramp = c.text("control") == "rampa de tensão"
    t0 = 0.1
    tstop = t0 + tacc + 1.5
    s = c.new("Soft-starter")
    c.add(
        s,
        "v3ph",
        "V1",
        {"a": "a", "b": "b", "c": "c", "n": "0"},
        vrms=f"{vline / math.sqrt(3):.6f}",
    )
    c.add(s, "vpwl", "V2", {"p": "run", "n": "0"}, points=f"0 0 {t0:g} 0 {t0 + 1e-3:g} 24")
    c.add(
        s,
        "soft_starter",
        "SS1",
        {
            "L1": "a",
            "L2": "b",
            "L3": "c",
            "RUN": "run",
            "COM": "0",
            "T1": "t1",
            "T2": "t2",
            "T3": "t3",
        },
        dut=True,
    )
    c.add(
        s,
        "induction_motor",
        "M1",
        {"A": "t1", "B": "t2", "C": "t3"},
        tl=f"{tl:g}",
        load="quadrática",
    )
    tr = c.run(s, "partida", tstop=f"{tstop:g}")
    t = _time(tr)
    c.curve(
        "ss",
        "Partida com soft-starter",
        "Tempo",
        "s",
        t,
        [
            ("Fração da tensão k", "", _vec(tr, "v(ss1_k)")),
            ("Corrente de linha", "A", _vec(tr, "v(ss1_i)")),
            ("Velocidade / 100", "rpm", _vec(tr, "v(m1_rpm)") / 100),
        ],
    )
    inp = {"k_0": _q(vinit, ""), "t_acel": _q(tacc, "s"), "I_lim": _q(ilim, "A")}
    if ramp:
        c.check(
            "SS-K",
            "Fração da tensão no meio da rampa",
            _at(tr, "v(ss1_k)", t0 + tacc / 2),
            vinit + (1 - vinit) / 2,
            "",
            1.0,
            "Nó <ref>_k em t_acel/2 após o RUN.",
            r"k(t) = k_0 + (1 - k_0)\,t/t_{acel}",
            inp,
            WEG_SSW07,
        )
    else:
        imax = float(np.max(_vec(tr, "v(ss1_i)")))
        c.check(
            "SS-ILIM",
            "Corrente máxima na partida",
            imax,
            ilim,
            "A",
            3.0,
            "Máximo da corrente de linha eficaz durante a partida.",
            r"I \le I_{lim}",
            inp,
            WEG_SSW07,
        )
    c.check(
        "SS-BYPASS",
        "Fração da tensão após a rampa (bypass)",
        _at(tr, "v(ss1_k)", tstop),
        1.0,
        "",
        0.1,
        "Nó <ref>_k no fim do ensaio.",
        r"k = 1",
        inp,
        WEG_SSW07,
    )
    ref = steady_state(_motor_params(c, _motor_defaults), vline, 60, tl, quadratic=True)
    c.check(
        "SS-N",
        "Velocidade final do motor (padrão da biblioteca)",
        _mean(tr, "v(m1_rpm)", tstop - 0.3, tstop),
        ref.speed_rpm,
        "rpm",
        0.3,
        "Média nos últimos 0,3 s: ponto de operação da partida direta.",
        r"T(s) = T_L\,(\omega/\omega_{nom})^2",
        inp,
        CHAPMAN,
    )


def _contactor(c: _Ctx) -> None:
    vnom, pcoil, ron = c.p("vnom"), c.p("pcoil"), c.p("ron")
    ac = c.text("coil") == "CA"
    vload, rload = c.f("vload"), c.f("rload")
    vmax = 1.2 * vnom
    s = c.new("Contator")
    if ac:
        c.add(
            s,
            "bsource",
            "VC",
            {"p": "a1", "n": "0"},
            type="V",
            expr=f"{vmax * math.sqrt(2):.6g}*(time < 1 ? time : 2 - time)*sin(2*pi*60*time)",
        )
    else:
        c.add(s, "vpwl", "VC", {"p": "a1", "n": "0"}, points=f"0 0 1 {vmax:g} 2 0")
    nodes = {"A1": "a1", "A2": "0"}
    for j in (1, 2, 3):
        nodes |= {f"L{j}": "l", f"T{j}": f"t{j}"}
    c.add(s, "vdc", "VL", {"p": "l", "n": "0"}, dc=f"{vload:g}")
    c.add(s, "contactor", "K1", nodes, dut=True)
    for j in (1, 2, 3):
        c.add(s, "resistor", f"R{j}", {"p": f"t{j}", "n": "0"}, value=f"{rload:g}")
    tr = c.run(s, "bobina", tstop="2", tmax="0.5m" if ac else "1m")
    t = _time(tr)
    env = vmax * np.where(t < 1, t, 2 - t)
    t1 = _vec(tr, "v(t1)")
    c.curve(
        "k",
        "Bobina (valor nominal da rampa) e contato L1-T1",
        "Tempo",
        "s",
        t,
        [("Bobina (eficaz se CA)" if ac else "Bobina", "V", env), ("T1", "V", t1)],
    )
    up = t <= 1
    inp = {"V_nom": _q(vnom, "V"), "P_bob": _q(pcoil, "W")}
    # AC coil: the mean of |v| goes through a 10 ms filter, whose 120 Hz ripple advances the
    # closing and delays the opening by a few percent
    tol = 7.0 if ac else 0.5
    if ac:
        c.warnings.append(
            "Bobina CA: o valor médio retificado passa por um filtro de 10 ms; a "
            "ondulação de 120 Hz antecipa o fechamento e atrasa a abertura em "
            "alguns por cento (tolerância de 7 %)."
        )
    c.check(
        "K-FECHA",
        "Fecha com (tensão da bobina)",
        float(np.interp(crossing(t[up], t1[up], vload / 2), t, env)),
        0.75 * vnom,
        "V",
        tol,
        "Tensão da bobina quando T1 atinge metade da tensão de carga, na subida.",
        r"V_{fecha} = 0{,}75\,V_{nom}",
        inp,
        assumptions=(
            MODEL,
            "Limiares de 75 % e 40 % "
            "da nominal (didáticos; confira a norma IEC 60947-4-1 e o catálogo).",
        ),
    )
    c.check(
        "K-ABRE",
        "Abre com (tensão da bobina)",
        float(np.interp(crossing(t[~up], t1[~up], vload / 2, rising=False), t, env)),
        0.40 * vnom,
        "V",
        tol,
        "Tensão da bobina quando T1 cai a metade, na descida.",
        r"V_{abre} = 0{,}40\,V_{nom}",
        inp,
        assumptions=(MODEL, "Limiares didáticos."),
    )
    if not ac:
        c.check(
            "K-IBOB",
            "Corrente da bobina na tensão nominal",
            abs(_at(tr, "i(vc)", vnom / vmax)),
            pcoil / vnom,
            "A",
            0.5,
            "Corrente da fonte da bobina em V_nom.",
            r"I_{bob} = P_{bob}/V_{nom}",
            inp,
        )
    v1 = _at(tr, "v(t1)", 1.0)
    c.check(
        "K-RON",
        "Resistência de cada contato",
        (vload - v1) / (v1 / rload),
        ron,
        "ohm",
        1.0,
        "Queda L1-T1 dividida pela corrente da carga, contator fechado.",
        r"R_{cont} = \frac{V_L - V_T}{V_T/R}",
        {"R_on": _q(ron, "ohm")},
    )


def _pulses(n: int, t0: float, period: float) -> str:
    pts = ["0 0"]
    for i in range(n):
        a = t0 + i * period
        pts += [
            f"{a:.6g} 0",
            f"{a + 1e-6:.6g} 5",
            f"{a + period / 2:.6g} 5",
            f"{a + period / 2 + 1e-6:.6g} 0",
        ]
    return " ".join(pts)


def _stepper(c: _Ctx, motor_is_dut: bool) -> None:
    nfwd, nback = int(c.f("nfwd")), int(c.f("nback"))
    rate, tl, vm = c.f("rate"), c.f("tl"), c.f("vm")
    if nfwd < 1 or nback < 0 or nback > nfwd or rate <= 0:
        raise BenchError(
            "Use passos à frente ≥ 1, passos de volta entre 0 e os à frente, e taxa positiva"
        )
    m_sym, d_sym = symbol("stepper_motor"), symbol("stepper_driver")

    def g(sym_kind: str, name: str) -> float:
        if (sym_kind == "stepper_motor") == motor_is_dut:
            return c.p(name)
        sym = m_sym if sym_kind == "stepper_motor" else d_sym
        return parse_value(sym.param(name).default)

    step, km = g("stepper_motor", "step"), g("stepper_motor", "km")
    ifull = g("stepper_driver", "ifull")
    micro = int(g("stepper_driver", "micro"))
    period = 1 / rate
    n = nfwd + nback
    t0 = 10e-3
    t_dir = t0 + (nfwd - 0.5) * period
    tstop = t0 + n * period + 0.3
    s = c.new("Motor de passo")
    c.add(s, "vdc", "V1", {"p": "vm", "n": "0"}, dc=f"{vm:g}")
    c.add(s, "vpwl", "V2", {"p": "step", "n": "0"}, points=_pulses(n, t0, period))
    c.add(s, "vpwl", "V3", {"p": "dir", "n": "0"}, points=f"0 5 {t_dir:.6g} 5 {t_dir + 1e-4:.6g} 0")
    drv = {
        "STEP": "step",
        "DIR": "dir",
        "EN": "en",
        "GND": "0",
        "VM": "vm",
        "A+": "a1",
        "A-": "a2",
        "B+": "b1",
        "B-": "b2",
    }
    mot = {"A+": "a1", "A-": "a2", "B+": "b1", "B-": "b2"}
    c.add(s, "stepper_driver", "DRV1", drv, dut=not motor_is_dut)
    c.add(s, "stepper_motor", "M1", mot, dut=motor_is_dut, tl=f"{tl:g}")
    tr = c.run(s, "passos", tstop=f"{tstop:.6g}")
    t = _time(tr)
    c.curve(
        "pp-pos",
        "Posição do rotor e contagem de passos",
        "Tempo",
        "s",
        t,
        [
            ("Posição", "°", _vec(tr, "v(m1_deg)")),
            ("Passos × ângulo/micropasso", "°", _vec(tr, "drv1.steps") * step / micro),
        ],
    )
    c.curve(
        "pp-i",
        "Correntes das fases",
        "Tempo",
        "s",
        t,
        [("i_A", "A", _vec(tr, "i(vdrv1_sa)")), ("i_B", "A", _vec(tr, "i(vdrv1_sb)"))],
    )
    net = nfwd - nback
    inp = {
        "passo": _q(step, "deg"),
        "micropasso": _q(micro, ""),
        "K": _q(km, "N*m/A"),
        "I": _q(ifull, "A"),
        "T_L": _q(tl, "N*m"),
    }
    c.check(
        "PP-PASSOS",
        "Contagem de passos do driver",
        _at(tr, "drv1.steps", tstop),
        net,
        "",
        0.01,
        "Variável <ref>.steps do driver no fim (DIR baixo inverte o sentido).",
        r"n = n_{frente} - n_{volta}",
        inp,
        KENJO,
    )
    home = step / 2  # the driver starts with the current vector at 45° electrical
    try:
        lag = load_angle_deg(tl, km, ifull, step)
    except ValueError as exc:
        raise BenchError(f"Torque de carga acima do torque de retenção: {exc}") from exc
    expected = home + net * step / micro - lag
    tol = 100 * 0.028 * step / micro / max(abs(expected), 1e-9)
    c.check(
        "PP-POS",
        "Posição final do rotor",
        _mean(tr, "v(m1_deg)", tstop - 0.05, tstop),
        expected,
        "deg",
        tol,
        "Média dos últimos 50 ms; tolerância de 2,8 % de um (micro)passo.",
        r"\theta = \theta_0 + n\,\frac{\theta_p}{m} - \frac{1}{N}\arcsin\frac{T_L}{K\,I}",
        inp,
        KENJO,
    )
    final = _mean(tr, "v(m1_deg)", tstop - 0.05, tstop)
    if abs(final - expected) > step / micro:
        c.warnings.append(
            f"O rotor parou a {final:.1f}° em vez de {expected:.1f}°: perdeu passos (perda de "
            "sincronismo). Com esta inércia, reduza a taxa de passos, aumente a corrente do "
            "driver ou use micropasso."
        )
    ia = abs(_mean(tr, "i(vdrv1_sa)", tstop - 0.05, tstop))
    ib = abs(_mean(tr, "i(vdrv1_sb)", tstop - 0.05, tstop))
    c.check(
        "PP-I",
        "Módulo do vetor de corrente parado",
        math.hypot(ia, ib),
        ifull,
        "A",
        1.5,
        "√(i_A² + i_B²) nos últimos 50 ms.",
        r"|\vec{i}| = I_{fase}",
        inp,
        KENJO,
    )


# ------------------------------------------------------------------------------ boards


def _mcu(c: _Ctx) -> None:
    b = BOARDS[c.kind]
    esp = c.kind == "esp32_devkitc"
    rl_d, rl_p = c.f("rl_dig"), c.f("rl_pwm")
    duty = int(c.f("duty"))
    if not 0 <= duty <= 255:
        raise BenchError("Ciclo de trabalho entre 0 e 255")
    names = {
        "adc": "IO34" if esp else "A0",
        "din": "IO4" if esp else "D2",
        "dout": "IO2" if esp else "D8",
        "pwm": "IO18" if esp else "D9",
    }
    num = {k: b.pins[v] for k, v in names.items()}
    dac = "\n  dacWrite(25, 200);" if esp else ""
    program = f"""// Bancada: ADC, entrada digital, saída digital e PWM
int codigo; int entrada;
void setup() {{
  pinMode({num["din"]}, INPUT);
  pinMode({num["dout"]}, OUTPUT);
  pinMode({num["pwm"]}, OUTPUT);
  digitalWrite({num["dout"]}, HIGH);
  analogWrite({num["pwm"]}, {duty});{dac}
}}
void loop() {{
  codigo = analogRead({num["adc"]});
  entrada = digitalRead({num["din"]});
  delay(1);
}}
"""
    ref = "U1"
    vdd = b.vdd
    s = c.new(b.label)
    gnd = "GND"
    nodes = {
        gnd: "0",
        names["adc"]: "x",
        names["din"]: "x",
        names["dout"]: "dout",
        names["pwm"]: "pwm",
    }
    if esp:
        nodes["IO25"] = "dac"
    c.add(s, c.kind, ref, nodes, dut=True, program=program)
    c.add(s, "vpwl", "VX", {"p": "x", "n": "0"}, points=f"0 0 0.5 {vdd:g} 1 0")
    c.add(s, "resistor", "RD", {"p": "dout", "n": "0"}, value=f"{rl_d:g}")
    c.add(s, "resistor", "RP", {"p": "pwm", "n": "0"}, value=f"{rl_p:g}")
    if esp:
        c.add(s, "resistor", "RDAC", {"p": "dac", "n": "0"}, value="1g")
    tr = c.run(s, "E/S", tstop="1")
    adc_warn = [w for w in c.warnings if "fora da faixa efetiva" in w]
    if adc_warn:
        c.warnings = [w for w in c.warnings if w not in adc_warn]
        c.warnings.append(
            "Há leituras do ADC fora da faixa efetiva do "
            f"{b.label}: a rampa vai de 0 V ao fundo de escala de propósito, mas "
            "na placa real a leitura perde precisão fora dessa faixa."
        )
    t = _time(tr)
    vx = _vec(tr, "v(x)")
    code = _vec(tr, f"{ref.lower()}.codigo")
    inp_ = _vec(tr, f"{ref.lower()}.entrada")
    up = t <= 0.5
    full = (1 << b.adc_bits) - 1
    c.curve(
        "adc",
        f"Conversor A/D ({b.adc_bits} bits) na rampa de subida",
        "Tensão na entrada",
        "V",
        vx[up],
        [
            ("analogRead", "", code[up]),
            ("Ideal", "", np.round(np.clip(vx[up], 0, b.adc_fs) / b.adc_fs * full)),
        ],
    )
    c.curve(
        "din",
        "Entrada digital (subida e descida)",
        "Tempo",
        "s",
        t,
        [("Tensão", "V", vx), (f"digitalRead × {vdd:g} V", "V", inp_ * vdd)],
    )
    bib = ESP32 if esp else ARDUINO
    didactic = (MODEL, b.sources.get("didatico", "Limiares e resistência de saída didáticos."))
    inp = {"V_DD": _q(vdd, "V"), "bits": _q(b.adc_bits, ""), "FE": _q(b.adc_fs, "V")}
    # the ADC: slope over the middle of the ramp, and the code at half scale
    sel = up & (vx > 0.2 * b.adc_fs) & (vx < 0.8 * b.adc_fs)
    lsb = 1 / float(np.polyfit(vx[sel], code[sel], 1)[0])
    c.check(
        "MCU-LSB",
        "Resolução do ADC (1 LSB)",
        lsb,
        b.adc_fs / full,
        "V",
        1.0,
        "Inverso da inclinação de analogRead × tensão (20 % a 80 % da escala).",
        r"\mathrm{LSB} = \frac{FE}{2^n - 1}",
        inp,
        bib,
    )
    half_t = 0.25
    v_half = float(np.interp(half_t, t, vx))
    c.check(
        "MCU-ADC",
        f"Código lido com {v_half:.3g} V",
        float(np.interp(half_t, t, code)),
        v_half / b.adc_fs * full,
        "",
        0.5,
        "analogRead no meio da rampa (amostra e retém a "
        "cada 1 ms; erro de até 1 LSB de quantização).",
        r"N = \frac{V}{FE}\,(2^n - 1)",
        inp,
        bib,
    )
    c.check(
        "MCU-VIH",
        "Limiar de subida da entrada digital",
        float(np.interp(crossing(t[up], inp_[up], 0.5), t, vx)),
        b.vih * vdd,
        "V",
        1.0,
        "Tensão quando digitalRead passa a 1 na subida.",
        r"V_{IH} = k_{IH}\,V_{DD}",
        inp | {"k_IH": _q(b.vih, "")},
        bib,
        didactic,
    )
    c.check(
        "MCU-VIL",
        "Limiar de descida da entrada digital",
        float(np.interp(crossing(t[~up], inp_[~up], 0.5, rising=False), t, vx)),
        b.vil * vdd,
        "V",
        1.0,
        "Tensão quando digitalRead volta a 0 na descida.",
        r"V_{IL} = k_{IL}\,V_{DD}",
        inp | {"k_IL": _q(b.vil, "")},
        bib,
        didactic,
    )
    c.check(
        "MCU-VOH",
        f"Saída digital em nível alto com {rl_d:g} Ω",
        float(_vec(tr, "v(dout)")[-1]),
        vdd * rl_d / (rl_d + b.rout),
        "V",
        0.2,
        "V(pino) com digitalWrite(HIGH) e carga.",
        r"V_{OH} = V_{DD}\,\frac{R_L}{R_L + R_{saída}}",
        inp | {"R_saída": _q(b.rout, "ohm"), "R_L": _q(rl_d, "ohm")},
        bib,
        didactic,
    )
    c.check(
        "MCU-PWM",
        f"Tensão média do PWM (analogWrite {duty})",
        float(_vec(tr, "v(pwm)")[-1]),
        vdd * duty / 255 * rl_p / (rl_p + b.rout),
        "V",
        0.2,
        "Modo PWM 'média': o pino entrega a média do ciclo.",
        r"\bar V = V_{DD}\,\frac{D}{255}\,\frac{R_L}{R_L + R_{saída}}",
        inp | {"D": _q(duty, ""), "R_L": _q(rl_p, "ohm")},
        bib,
        didactic,
    )
    if esp:
        c.check(
            "MCU-DAC",
            "Saída do DAC (dacWrite 200)",
            float(_vec(tr, "v(dac)")[-1]),
            200 / 255 * vdd,
            "V",
            0.2,
            "V(IO25) em aberto.",
            r"V = \frac{N}{255}\,V_{DD}",
            inp,
            bib,
        )
    # PWM frequency: switched output
    s2 = c.new(b.label + " PWM")
    prog2 = (
        f"void setup() {{ pinMode({num['pwm']}, OUTPUT); analogWrite({num['pwm']}, 128); }}\n"
        "void loop() { delay(1); }\n"
    )
    c.add(s2, c.kind, ref, {gnd: "0", names["pwm"]: "pwm"}, dut=True, program=prog2, pwm="chaveado")
    c.add(s2, "resistor", "RP", {"p": "pwm", "n": "0"}, value=f"{rl_p:g}")
    f_pwm = b.pwm[num["pwm"]]
    tr2 = c.run(s2, "PWM chaveado", tstop=f"{12 / f_pwm:.6g}")
    t2 = _time(tr2)
    vp = _vec(tr2, "v(pwm)")
    c.curve("pwm", "PWM chaveado (analogWrite 128)", "Tempo", "s", t2, [("V(pino)", "V", vp)])
    sel2 = t2 > 2 / f_pwm
    level = vdd / 2 * rl_p / (rl_p + b.rout)
    rising = np.nonzero((vp[sel2][1:] >= level) & (vp[sel2][:-1] < level))[0]
    tt = t2[sel2]
    if len(rising) >= 3:
        period = float(np.mean(np.diff(tt[rising])))
        c.check(
            "MCU-FPWM",
            f"Frequência do PWM no pino {names['pwm']}",
            1 / period,
            f_pwm,
            "Hz",
            1.0,
            "Inverso do período médio entre bordas de subida.",
            r"f_{PWM}",
            {"f": _q(f_pwm, "Hz")},
            bib,
            (MODEL, b.sources.get("pwm", "")),
        )


PLC_ST = """(* Bancada: I0 -> Q0, AI1 -> AQ0, AI0 em mA *)
Q0 := I0;
AQ0 := AI1;
"""


def _plc(c: _Ctx) -> None:
    rl = c.f("rl")
    s = c.new("CLP")
    nodes = {
        "L+": "lp",
        "M": "0",
        "I0": "i0",
        "AI0": "ai0",
        "AI1": "ai1",
        "Q0a": "lp",
        "Q0b": "q0",
        "AQ0": "aq0",
    }
    c.add(s, "plc", "CLP1", nodes, dut=True, language="st", st=PLC_ST)
    c.add(s, "vdc", "VL", {"p": "lp", "n": "0"}, dc="24")
    c.add(s, "vpwl", "VI", {"p": "i0", "n": "0"}, points="0 0 1 24 2 0")
    c.add(s, "ipwl", "IA", {"p": "0", "n": "ai0"}, points="0 4m 0.8 12m 1.2 12m 2 20m")
    c.add(s, "vpwl", "VA", {"p": "ai1", "n": "0"}, points="0 0 0.8 5 1.2 5 2 10")
    c.add(s, "resistor", "RQ", {"p": "q0", "n": "0"}, value=f"{rl:g}")
    c.add(s, "resistor", "RAQ", {"p": "aq0", "n": "0"}, value="10k")
    tr = c.run(s, "E/S", tstop="2", tmax="2m")
    t = _time(tr)
    vi = _vec(tr, "v(i0)")
    q0 = _vec(tr, "v(q0)")
    c.curve(
        "clp-di",
        "Entrada I0 e saída a relé Q0",
        "Tempo",
        "s",
        t,
        [("I0", "V", vi), ("Q0 (carga)", "V", q0)],
    )
    ai0 = _vec(tr, "clp1.ai0")
    c.curve(
        "clp-ai",
        "Entradas analógicas e saída AQ0",
        "Tempo",
        "s",
        t,
        [
            ("AI0 lida (mA)", "mA", ai0),
            ("AI1 (V)", "V", _vec(tr, "v(ai1)")),
            ("AQ0 (V)", "V", _vec(tr, "v(aq0)")),
        ],
    )
    up = t <= 1
    inp = {"V_ON": _q(PLC_DI_ON, "V"), "V_OFF": _q(PLC_DI_OFF, "V")}
    scan = parse_value(c.text("scan_ms")) * 1e-3
    tol_v = 100 * 24 * scan / PLC_DI_OFF + 1.0  # one scan of the 24 V/s ramp
    c.check(
        "CLP-ON",
        "Entrada digital liga com",
        float(np.interp(crossing(t[up], q0[up], 12), t, vi)),
        PLC_DI_ON,
        "V",
        tol_v,
        "Tensão em I0 quando Q0 fecha (rampa de 24 V/s; atraso de até um ciclo de varredura).",
        r"V_{ON} \ge 15\ \mathrm{V}",
        inp,
        IEC61131,
    )
    c.check(
        "CLP-OFF",
        "Entrada digital desliga com",
        float(np.interp(crossing(t[~up], q0[~up], 12, rising=False), t, vi)),
        PLC_DI_OFF,
        "V",
        tol_v,
        "Tensão em I0 quando Q0 abre, na descida.",
        r"V_{OFF} \le 5\ \mathrm{V}",
        inp,
        IEC61131,
    )
    c.check(
        "CLP-AI0",
        "Leitura de AI0 com 12 mA",
        float(np.interp(1.0, t, ai0)),
        12.0,
        "",
        1.0,
        f"Variável AI0 (mA) com a fonte parada em 12 mA; derivação de {PLC_AI_SHUNT:g} Ω.",
        r"AI0 = \frac{V_{AI0}}{250\ \Omega}",
        {"I": _q(12e-3, "A")},
        IEC61131,
    )
    c.check(
        "CLP-AQ0",
        "Saída AQ0 com AI1 = 5 V (AQ0 := AI1)",
        float(np.interp(1.0, t, _vec(tr, "v(aq0)"))),
        5.0 * 10e3 / (10e3 + PLC_AQ_ROUT),
        "V",
        1.0,
        "V(AQ0) com carga de 10 kΩ, com AI1 parada em 5 V.",
        r"V_{AQ0} = AI1\,\frac{R_L}{R_L + R_{saída}}",
        {"R_saída": _q(PLC_AQ_ROUT, "ohm")},
        IEC61131,
        (MODEL, "Saída analógica didática (10 Ω)."),
    )


# ------------------------------------------------------------------------------ registry


def _fx(name: str, label: str, unit: str, default: str, help_: str = "") -> ParamDef:
    return ParamDef(name, label, unit, default, help=help_)


@dataclass(frozen=True)
class PeripheralBench:
    kind: str
    group: str  # "Sensores", "Atuadores", "Placas e controladores"
    summary: str
    run: Callable[[_Ctx], None]
    driven: tuple[str, ...] = ()  # device parameters set by the bench (stimulus)
    fixture: tuple[ParamDef, ...] = ()
    tests: tuple[str, ...] = ()
    seconds: float = 2.0  # rough run time, for the user interface
    hidden: tuple[str, ...] = field(default=("program", "ladder", "st", "language"))


_T = "Temperatura"
BENCHES: dict[str, PeripheralBench] = {
    b.kind: b
    for b in [
        PeripheralBench(
            "lm35",
            "Sensores",
            "Rampa de temperatura com a alimentação fixa.",
            _lm35,
            ("temp",),
            (
                _fx("vs", "Alimentação VS", "V", "5"),
                _fx("tmin", f"{_T} inicial", "°C", "0"),
                _fx("tmax", f"{_T} final", "°C", "150"),
            ),
            ("Sensibilidade", "Saída a 25 °C", "Saturação (VS − 1,5 V)"),
        ),
        PeripheralBench(
            "pt100",
            "Sensores",
            "Corrente de excitação constante e rampa de temperatura.",
            _pt100,
            ("temp",),
            (
                _fx("iexc", "Corrente de excitação", "A", "1m"),
                _fx("tmax", f"{_T} final", "°C", "850"),
            ),
            ("R a 0 °C", "R a 100 °C", "Coeficiente α", "R no fim da faixa"),
        ),
        PeripheralBench(
            "thermocouple",
            "Sensores",
            "Rampa da junta quente, junta fria fixa; em aberto e com carga.",
            _thermocouple,
            ("temp",),
            (
                _fx("tmin", f"{_T} inicial", "°C", "0"),
                _fx("tmax", f"{_T} final", "°C", "1000"),
                _fx("rl", "Carga do instrumento", "Ω", "1k"),
            ),
            ("FEM a 100 °C e no fim", "Coeficiente de Seebeck", "Tensão com carga"),
        ),
        PeripheralBench(
            "tx420",
            "Sensores",
            "Laço de 24 V com a entrada do CLP (250 Ω); depois, fonte insuficiente.",
            _tx420,
            ("x",),
            (
                _fx("vloop", "Fonte do laço", "V", "24"),
                _fx("rl", "Resistência de entrada", "Ω", "250"),
            ),
            ("4, 12 e 20 mA", "Fonte abaixo da mínima"),
        ),
        PeripheralBench(
            "tx420_rtd",
            "Sensores",
            "Pt100 a três fios com resistência de fio; rampa de temperatura.",
            _tx420_rtd,
            (),
            (
                _fx("vloop", "Fonte do laço", "V", "24"),
                _fx("rl", "Resistência de entrada", "Ω", "250"),
                _fx("rlead", "Resistência de cada fio", "Ω", "5"),
                _fx("dlead", "Diferença no fio 1", "Ω", "0", "Fios desiguais: o erro aparece."),
            ),
            ("Temperatura lida", "4, 12 e 20 mA"),
        ),
        PeripheralBench(
            "acs712",
            "Sensores",
            "Rampa de corrente no primário e resposta em frequência.",
            _acs712,
            (),
            (_fx("vcc", "Alimentação VCC", "V", "5"), _fx("imax", "Corrente máxima (±)", "A", "5")),
            ("Saída em zero", "Sensibilidade", "Resistência do primário", "Banda"),
        ),
        PeripheralBench(
            "potentiometer",
            "Sensores",
            "Cursor de 0 a 1, sem carga e com carga.",
            _potentiometer,
            ("pos",),
            (_fx("vin", "Tensão entre a e b", "V", "10"), _fx("rl", "Carga no cursor", "Ω", "10k")),
            ("Resistência total", "Divisor sem carga", "Efeito de carga"),
        ),
        PeripheralBench(
            "relay",
            "Atuadores",
            "Rampa na bobina até 120 % da nominal e volta; carga nos contatos.",
            _relay,
            (),
            (
                _fx("vload", "Tensão no comum", "V", "12"),
                _fx("rload", "Carga em NA e NF", "Ω", "10"),
            ),
            ("Operação e desoperação", "Resistência da bobina", "Resistência do contato"),
        ),
        PeripheralBench(
            "dc_motor",
            "Atuadores",
            "Degrau de tensão em vazio e com carga.",
            _dc_motor,
            ("tl",),
            (
                _fx("v", "Tensão de armadura", "V", "12"),
                _fx("load", "Carga (fração do torque de rotor bloqueado)", "", "0.5"),
            ),
            (
                "Velocidade e corrente em vazio",
                "Tempo até 63 %",
                "Pico de corrente",
                "Velocidade com carga",
            ),
        ),
        PeripheralBench(
            "heater",
            "Atuadores",
            "Degrau de tensão; planta térmica de 1ª ordem.",
            _heater,
            (),
            (_fx("v", "Tensão aplicada", "V", "10"),),
            ("Elevação de temperatura", "Constante de tempo", "Potência"),
        ),
        PeripheralBench(
            "switch_manual",
            "Atuadores",
            "Fonte com resistor em série; a chave fecha no instante dado.",
            _switch_manual,
            ("state",),
            (
                _fx("v", "Fonte", "V", "5"),
                _fx("rs", "Resistor em série", "Ω", "100"),
                _fx("tclose", "Instante do aperto", "s", "1"),
            ),
            ("Resistência fechada", "Instante do fechamento"),
            seconds=1,
        ),
        PeripheralBench(
            "pump_plant",
            "Atuadores",
            "Referência fixa em AI, RUN em 0,1 s; transmissor no laço de 24 V.",
            _pump_plant,
            (),
            (
                _fx("ai", "Referência em AI", "V", "10"),
                _fx("vloop", "Fonte do laço", "V", "24"),
                _fx("rl", "Entrada do CLP", "Ω", "250"),
            ),
            ("Frequência e rampa", "Pressão", "Corrente do transmissor"),
        ),
        PeripheralBench(
            "induction_motor",
            "Atuadores",
            "Partida direta na rede trifásica com torque de carga.",
            _induction_motor,
            ("tl",),
            (
                _fx("vline", "Tensão de linha (eficaz)", "V", "380"),
                _fx("freq", "Frequência", "Hz", "60"),
                _fx("tl", "Torque de carga", "N·m", "20"),
                _fx("tstop", "Duração do ensaio", "s", "2"),
            ),
            ("Velocidade, corrente e torque em regime", "Curva torque × velocidade"),
            seconds=15,
        ),
        PeripheralBench(
            "vfd",
            "Atuadores",
            "Referência em AI e RUN ligado; motor de indução padrão com carga quadrática.",
            _vfd,
            (),
            (
                _fx("ai", "Referência em AI", "V", "5"),
                _fx("tl", "Torque de carga a 1800 rpm", "N·m", "20"),
            ),
            ("Rampa", "Frequência final", "Lei V/f", "Velocidade do motor"),
            seconds=25,
        ),
        PeripheralBench(
            "soft_starter",
            "Atuadores",
            "RUN em 0,1 s; motor de indução padrão com carga quadrática.",
            _soft_starter,
            (),
            (
                _fx("vline", "Tensão de linha (eficaz)", "V", "380"),
                _fx("tl", "Torque de carga a 1800 rpm", "N·m", "20"),
            ),
            ("Rampa de tensão ou limite de corrente", "Bypass", "Velocidade final"),
            seconds=30,
        ),
        PeripheralBench(
            "contactor",
            "Atuadores",
            "Rampa na bobina até 120 % da nominal e volta.",
            _contactor,
            (),
            (
                _fx("vload", "Tensão nos contatos", "V", "24"),
                _fx("rload", "Carga por fase", "Ω", "10"),
            ),
            ("Fecha e abre", "Corrente da bobina", "Resistência do contato"),
        ),
        PeripheralBench(
            "stepper_motor",
            "Atuadores",
            "Driver STEP/DIR padrão (passo inteiro, 1,5 A): passos à frente e de volta.",
            lambda c: _stepper(c, True),
            ("tl",),
            (
                _fx("nfwd", "Passos à frente", "", "20"),
                _fx("nback", "Passos de volta", "", "5"),
                _fx("rate", "Taxa", "passos/s", "50"),
                _fx("tl", "Torque de carga", "N·m", "0.1"),
                _fx("vm", "Alimentação do driver", "V", "24"),
            ),
            ("Contagem de passos", "Posição e ângulo de carga", "Corrente"),
            seconds=20,
        ),
        PeripheralBench(
            "stepper_driver",
            "Placas e controladores",
            "Motor de passo padrão da biblioteca (17HS19-2004S1): passos à frente e de volta.",
            lambda c: _stepper(c, False),
            (),
            (
                _fx("nfwd", "Passos à frente", "", "20"),
                _fx("nback", "Passos de volta", "", "5"),
                _fx("rate", "Taxa", "passos/s", "50"),
                _fx("tl", "Torque de carga", "N·m", "0.1"),
                _fx("vm", "Alimentação do driver", "V", "24"),
            ),
            ("Contagem de passos", "Posição com micropasso", "Corrente regulada"),
            seconds=20,
        ),
        PeripheralBench(
            "arduino_uno",
            "Placas e controladores",
            "Programa de ensaio: ADC e entrada digital numa rampa, saída digital e PWM com carga.",
            _mcu,
            (),
            (
                _fx("rl_dig", "Carga na saída digital", "Ω", "220"),
                _fx("rl_pwm", "Carga na saída PWM", "Ω", "1k"),
                _fx("duty", "analogWrite (0 a 255)", "", "128"),
            ),
            (
                "Resolução e leitura do ADC",
                "Limiares da entrada",
                "Saída alta com carga",
                "PWM: média e frequência",
            ),
            seconds=10,
        ),
        PeripheralBench(
            "esp32_devkitc",
            "Placas e controladores",
            "Programa de ensaio: ADC e entrada digital numa rampa, saída digital, PWM e DAC.",
            _mcu,
            (),
            (
                _fx("rl_dig", "Carga na saída digital", "Ω", "220"),
                _fx("rl_pwm", "Carga na saída PWM", "Ω", "1k"),
                _fx("duty", "analogWrite (0 a 255)", "", "128"),
            ),
            (
                "Resolução e leitura do ADC",
                "Limiares da entrada",
                "Saída alta com carga",
                "PWM: média e frequência",
                "DAC",
            ),
            seconds=10,
        ),
        PeripheralBench(
            "plc",
            "Placas e controladores",
            "Programa ST de ensaio: Q0 := I0, AQ0 := AI1; rampas "
            "em I0, AI0 (4-20 mA) e AI1 (0-10 V).",
            _plc,
            (),
            (_fx("rl", "Carga na saída Q0", "Ω", "1k"),),
            ("Limiares da entrada digital", "Leitura 4-20 mA", "Saída 0-10 V"),
            seconds=10,
        ),
    ]
}


def bench_params(b: PeripheralBench) -> list[ParamDef]:
    """Device parameters the user may change on the bench."""
    return [
        p
        for p in symbol(b.kind).params
        if p.name not in b.driven and p.name not in b.hidden and p.type != "code"
    ]


def part_applies(kind: str, record_: ComponentRecord) -> bool:
    """A catalogue part is offered on a bench only if it gives a value to the model."""
    cats, mapping = CATALOGUE_PARAMS.get(kind, ((), {}))
    if not any(record_.category.startswith(c) for c in cats):
        return False
    names = {target for target, _unit in mapping.values()}
    if kind == "stepper_motor":
        names |= {"T_hold"}
    return any(record_.parameters.get(n) is not None for n in names)


def run_peripheral(
    kind: str,
    params: dict[str, str],
    fixture: dict[str, str],
    record_: ComponentRecord | None,
    backend: Any,
) -> PeripheralResult:
    spec = BENCHES.get(kind)
    if spec is None:
        raise BenchError(f"Sem bancada para {kind!r}")
    allowed = {p.name for p in bench_params(spec)}
    ctx = _Ctx(
        kind, {k: v for k, v in params.items() if k in allowed}, fixture, record_, backend, spec
    )
    spec.run(ctx)
    used = {p.name: ctx.text(p.name) for p in bench_params(spec)}
    return PeripheralResult(
        kind=kind,
        tests=ctx.tests,
        curves=ctx.curves,
        steps=ctx.steps,
        netlists=ctx.netlists,
        warnings=list(dict.fromkeys(_comma(w) for w in ctx.warnings)),
        used=used,
    )
