"""DM-PAD: class D amplifier, half-bridge with two N-MOSFETs, natural-sampling PWM and LC filter.

Principle (Boylestad & Nashelsky, 11th ed., ch. 12, class D amplifier): the input is compared
with a triangular carrier; the comparator drives the output switches, so the switch node is a
two-level PWM wave whose mean follows the input, and a low-pass LC filter recovers the signal.
With ref = m·sin ωt and a triangle of unit amplitude, the duty cycle is d = (1 + m sin ωt)/2 and
the mean of the switch node is (2d − 1)·V = m·V·sin ωt.

The output filter is the 2nd-order Butterworth low-pass loaded by RL. From
H(s) = 1 / (LC s² + (L/RL) s + 1), ω0 = 1/√(LC) and Q = RL·√(C/L); Butterworth (Q = 1/√2) at
ω0 = ωc gives L = √2·RL/ωc and C = 1/(√2·RL·ωc) (derived here, not quoted from a table).

Rule 4: the transistors are modelled as switches with RDS(on) of the datasheet (on) and a large
off resistance, the same element the simulator uses (``SW`` with RON/ROFF), driven by the same
comparator (natural sampling, no dead time). The circuit is then linear between switching
instants, so the analytic solution is exact: switching instants by root finding, the state
[iL, vC] propagated with the matrix exponential, and the periodic steady state from
x0 = (I − Φ(T))⁻¹·g. Switching losses are estimated from tr and tf of the datasheet (Mohan,
Undeland & Robbins, Power Electronics, 3rd ed., ch. 2, switching power loss), not simulated.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pint
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from scipy.linalg import expm
from scipy.optimize import brentq

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.eseries import SeriesName
from circuitos.core.units import Q_, QuantityModel, format_eng, parse_unit
from circuitos.design.analog import commercial
from circuitos.design.base import (
    Circuit,
    DesignResult,
    DesignWarning,
    Role,
    SimCheck,
    Stress,
    make_trace,
)
from circuitos.design.devmodels import BOYLESTAD, quantity
from circuitos.design.engine import Analysis, Device
from circuitos.reports.common import BomRow, LabItem, passive
from circuitos.reports.schematic import Svg

FloatArray = NDArray[np.float64]
REF = BOYLESTAD.model_copy(update={"chapter": "12 (Power amplifiers: class D)"})
MOHAN = BibRef(
    book="Mohan, Undeland & Robbins, Power Electronics",
    edition="3rd",
    chapter="2 (switching losses)",
)
R_OFF = 1e9  # Ω, off resistance of the switch (analysis and simulator)
N_SUB = 6  # sub-steps per switching interval in the exact solution (trapezoidal averages)
RON_IDEAL = 0.05  # Ω, ideal step before a part is chosen


class PadSpec(BaseModel):
    VCC: QuantityModel = QuantityModel(value=24, unit="V")  # each rail (±VCC)
    RL: QuantityModel = QuantityModel(value=8, unit="ohm")
    Po: QuantityModel = QuantityModel(value=10, unit="W")  # desired output power (sine)
    f_sig: QuantityModel = QuantityModel(value=1, unit="kHz")
    fs: QuantityModel = QuantityModel(value=200, unit="kHz")  # carrier (switching) frequency
    fc: QuantityModel = QuantityModel(value=25, unit="kHz")  # filter cut-off (Butterworth)
    filter_series: SeriesName = "E12"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")
    Rth_cs: QuantityModel = QuantityModel(value=0.5, unit="K/W")
    m_max: float = Field(default=0.95, gt=0.1, lt=1.0)  # largest modulation index accepted


LABELS = {
    "fs": "Frequência de chaveamento (múltiplo inteiro do sinal)",
    "L": "Indutor do filtro",
    "C": "Capacitor do filtro",
    "f0": "Frequência de corte do filtro (valores comerciais)",
    "Q_f": "Fator de qualidade do filtro",
    "R_on": "RDS(on) de cada chave",
    "m": "Índice de modulação",
    "Vp": "Amplitude da tensão na carga",
    "Vo_rms": "Tensão eficaz na carga",
    "Po": "Potência na carga",
    "Pi": "Potência das fontes",
    "eff": "Rendimento (só condução)",
    "IL_max": "Corrente de pico no indutor",
    "IL_rms": "Corrente eficaz no indutor",
    "ripple_pp": "Ondulação residual na carga (pico a pico, perto de vo = 0)",
    "I_high_avg": "Corrente média da fonte positiva",
    "P_cond": "Perda de condução por chave",
    "P_sw": "Perda de comutação por chave (estimativa)",
    "THD": "Distorção harmônica total da saída (até a 50ª)",
}
SPEC_LABELS = {
    "VCC": "Alimentação (por trilho, ±)",
    "RL": "Carga (alto-falante)",
    "Po": "Potência de saída desejada",
    "f_sig": "Frequência do sinal",
    "fs": "Frequência de chaveamento (portadora)",
    "fc": "Corte do filtro LC (Butterworth)",
    "filter_series": "Série dos valores de L e C",
    "m_max": "Índice de modulação máximo",
}
ENUM_LABELS = {"E12": "E12", "E6": "E6", "E24": "E24"}


def _spec(spec: BaseModel) -> PadSpec:
    if not isinstance(spec, PadSpec):
        raise TypeError("DM-PAD espera PadSpec")
    return spec


def r_on_of(rec: ComponentRecord | None) -> float:
    if rec is None:
        return RON_IDEAL
    p = rec.parameters.get("RDS(on)")
    if p is None or p.max is None:
        raise ValueError(f"{rec.part_number}: datasheet sem RDS(on) máximo")
    return float(Q_(p.max, parse_unit(p.unit)).m_as("ohm"))


@dataclass(frozen=True)
class Bridge:
    vcc: float
    r_on: float
    rl: float
    L: float
    C: float
    f: float  # signal
    k: int  # carrier periods per signal period
    m: float

    @property
    def rth(self) -> float:
        return self.r_on * R_OFF / (self.r_on + R_OFF)

    @property
    def vth(self) -> float:
        """Thevenin voltage of the switch node with the high side on (low side: −vth)."""
        return self.vcc * (1 / self.r_on - 1 / R_OFF) * self.rth

    def h(self, w: float) -> complex:
        """vo / v_th with the series Rth + jωL and the load RL ∥ C."""
        zp = self.rl / (1 + 1j * w * self.rl * self.C)
        return complex(zp / (self.rth + 1j * w * self.L + zp))

    def matrices(self) -> tuple[FloatArray, FloatArray]:
        a = np.array(
            [[-self.rth / self.L, -1 / self.L], [1 / self.C, -1 / (self.rl * self.C)]],
            dtype=np.float64,
        )
        b = np.array([1 / self.L, 0.0], dtype=np.float64)
        return a, b

    def intervals(self) -> list[tuple[float, float, int]]:
        """(start, end, state) over one signal period; state +1 = high side on."""
        ts = 1 / (self.f * self.k)
        w = 2 * math.pi * self.f
        out: list[tuple[float, float, int]] = []
        for n in range(self.k):
            t0 = n * ts

            def g_up(t: float, t0: float = t0) -> float:
                return self.m * math.sin(w * t) - (-1 + 4 * (t - t0) / ts)

            def g_dn(t: float, t0: float = t0) -> float:
                return self.m * math.sin(w * t) - (1 - 4 * (t - t0 - ts / 2) / ts)

            t1 = brentq(g_up, t0, t0 + ts / 2, xtol=1e-15 * ts + 1e-18)
            t2 = brentq(g_dn, t0 + ts / 2, t0 + ts, xtol=1e-15 * ts + 1e-18)
            out += [(t0, t1, 1), (t1, t2, -1), (t2, t0 + ts, 1)]
        return out


@dataclass
class Solution:
    t: FloatArray  # time points (edges duplicated)
    il: FloatArray
    vo: FloatArray
    state: FloatArray  # +1 / −1 per point
    x0: FloatArray


def _propagator(a: FloatArray, b: FloatArray, u: float, h: float) -> tuple[FloatArray, FloatArray]:
    m = np.zeros((3, 3))
    m[:2, :2] = a
    m[:2, 2] = b * u
    e = expm(m * h)
    return e[:2, :2], e[:2, 2]


def solve(br: Bridge) -> Solution:
    """Exact periodic steady state of the switched linear circuit."""
    a, b = br.matrices()
    iv = br.intervals()
    period = 1 / br.f
    # forced response from x = 0 over one period: x(T) = Φ x0 + g
    x = np.zeros(2)
    for t0, t1, st in iv:
        phi, gam = _propagator(a, b, st * br.vth, t1 - t0)
        x = phi @ x + gam
    phi_t = expm(a * period)
    x0 = np.linalg.solve(np.eye(2) - phi_t, x)
    ts_, il, vo, sts = [], [], [], []
    x = x0.copy()
    for t0, t1, st in iv:
        h = (t1 - t0) / N_SUB
        phi, gam = _propagator(a, b, st * br.vth, h)
        for j in range(N_SUB + 1):
            ts_.append(t0 + j * h)
            il.append(x[0])
            vo.append(x[1])
            sts.append(st)
            if j < N_SUB:
                x = phi @ x + gam
    return Solution(
        t=np.asarray(ts_),
        il=np.asarray(il),
        vo=np.asarray(vo),
        state=np.asarray(sts, dtype=np.float64),
        x0=x0,
    )


def _avg(t: FloatArray, y: FloatArray) -> float:
    return float(np.trapezoid(y, t) / (t[-1] - t[0]))


class PadModule:
    id = "DM-PAD"
    family = "amplificadores"
    title = "Amplificador classe D (meia ponte)"
    spec_schema = PadSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão eficaz na carga", "multímetro true RMS (após o filtro)", "Vo_rms"),
        LabItem("Potência na carga", "a partir da tensão eficaz", "Po"),
        LabItem("Corrente média da fonte positiva", "multímetro em série", "I_high_avg"),
        LabItem("Ondulação residual na carga", "osciloscópio, banda total", "ripple_pp"),
    ]
    questions = [
        "Por que o rendimento da classe D não cai com a amplitude como na classe B?",
        "O que acontece com a ondulação na carga se a frequência de corte do filtro subir?",
        "Por que a fonte negativa chega a receber energia em parte do ciclo (bombeamento)?",
        "Para que serve o tempo morto num driver real de meia ponte?",
    ]
    practice = {
        "objective": "Montar a meia ponte com modulador PWM e filtro LC, medir potência, "
        "rendimento e ondulação residual na carga.",
        "material": "Fonte simétrica com limite de corrente, gerador de sinal e de triangular "
        "(ou modulador integrado), comparador, driver de meia ponte com tempo morto, os dois "
        "MOSFETs, indutor e capacitor do filtro, resistor de carga de potência, osciloscópio.",
        "procedure": [
            "Monte o driver com tempo morto e confira as tensões de porta sem a fonte de potência.",
            "Ligue a fonte de potência com limite de corrente baixo, sem sinal: a carga deve "
            "ter só a ondulação residual.",
            "Aplique o sinal até a amplitude de projeto; meça a tensão eficaz na carga e as "
            "correntes das fontes.",
            "Calcule Po, Pi e η e compare com o projeto; meça a temperatura dos MOSFETs.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        return [
            Role(designator="Q1", category="mosfet.n", description="Chave superior (lado alto)"),
            Role(designator="Q2", category="mosfet.n", description="Chave inferior (lado baixo)"),
        ]

    def required_ratings(self, role: Role) -> list[str]:
        return ["VDS", "ID"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).Rth_cs.to_pint()

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        p = rec.parameters.get("RDS(on)")
        return p is not None and p.max is not None

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        return r_on_of(rec)

    # ------------------------------------------------------------------ analysis
    def _filter(self, s: PadSpec, log: CalcLog) -> tuple[float, float, float]:
        rl = s.RL.to_pint().m_as("ohm")
        f = s.f_sig.to_pint().m_as("Hz")
        k = max(2, round(s.fs.to_pint().m_as("Hz") / f))
        fs = log.add(
            record(
                "fs",
                "Portadora com número inteiro de períodos por período do sinal",
                r"f_s = \mathrm{round}\!\left(\frac{f_{s,desejada}}{f}\right) f",
                output=Q_(k * f, "Hz").to("kHz"),
                inputs={"f_{s,desejada}": s.fs.to_pint(), "f": s.f_sig.to_pint()},
                assumptions=["regime periódico exato no período do sinal"],
                reference=REF,
            )
        ).m_as("Hz")
        wc = 2 * math.pi * s.fc.to_pint().m_as("Hz")
        l_calc = log.add(
            record(
                "L_calc",
                "Indutor do filtro Butterworth de 2ª ordem carregado por RL",
                r"L = \frac{\sqrt{2}\,R_L}{\omega_c}",
                output=Q_(math.sqrt(2) * rl / wc, "H").to("uH"),
                inputs={"R_L": s.RL.to_pint(), r"\omega_c": Q_(wc, "rad/s")},
                assumptions=[
                    "H(s) = 1/(LCs² + (L/R_L)s + 1), ω0 = ω_c e Q = R_L√(C/L) = 1/√2 "
                    "(dedução a partir da função de transferência)"
                ],
                reference=REF,
            )
        )
        c_calc = log.add(
            record(
                "C_calc",
                "Capacitor do filtro Butterworth de 2ª ordem",
                r"C = \frac{1}{\sqrt{2}\,R_L\,\omega_c}",
                output=Q_(1 / (math.sqrt(2) * rl * wc), "F").to("uF"),
                inputs={"R_L": s.RL.to_pint(), r"\omega_c": Q_(wc, "rad/s")},
                reference=REF,
            )
        )
        lv = commercial(log, "L", "Indutor", l_calc, s.filter_series, "nearest").m_as("H")
        cv = commercial(log, "C", "Capacitor", c_calc, s.filter_series, "nearest").m_as("F")
        log.add(
            record(
                "f0",
                "Frequência natural do filtro com os valores comerciais",
                r"f_0 = \frac{1}{2\pi\sqrt{LC}}",
                output=Q_(1 / (2 * math.pi * math.sqrt(lv * cv)), "Hz").to("kHz"),
                inputs={"L": Q_(lv, "H").to("uH"), "C": Q_(cv, "F").to("uF")},
                reference=REF,
            )
        )
        log.add(
            record(
                "Q_f",
                "Fator de qualidade do filtro carregado",
                r"Q = R_L\sqrt{C/L}",
                output=Q_(rl * math.sqrt(cv / lv), ""),
                inputs={"R_L": s.RL.to_pint(), "L": Q_(lv, "H"), "C": Q_(cv, "F")},
                reference=REF,
            )
        )
        return fs, lv, cv

    def bridge(self, s: PadSpec, devices: Mapping[str, Device], log: CalcLog) -> Bridge:
        fs, lv, cv = self._filter(s, log)
        f = s.f_sig.to_pint().m_as("Hz")
        r1 = r_on_of(devices["Q1"].record)
        r2 = r_on_of(devices["Q2"].record)
        r_on = max(r1, r2)
        log.add(
            record(
                "R_on",
                "Resistência de cada chave em condução",
                r"R_{on} = R_{DS(on),max}",
                output=Q_(r_on, "ohm"),
                assumptions=[
                    "RDS(on) máximo a 25 °C, porta excitada com o VGS do ensaio do datasheet "
                    "(driver ideal)",
                    "mesma resistência de chave (RON/ROFF) no simulador",
                    "RDS(on) cresce com Tj: a perda real é maior",
                ],
                reference=REF,
            )
        )
        vcc = s.VCC.to_pint().m_as("V")
        rl = s.RL.to_pint().m_as("ohm")
        po = s.Po.to_pint().m_as("W")
        vp = math.sqrt(2 * po * rl)
        k = round(fs / f)
        probe = Bridge(vcc, r_on, rl, lv, cv, f, k, 0.5)
        hmag = abs(probe.h(2 * math.pi * f))
        m = log.add(
            record(
                "m",
                "Índice de modulação para a amplitude desejada (modelo médio)",
                r"m = \frac{V_p}{V_{th}\,|H(j\omega)|},\quad V_p = \sqrt{2 P_o R_L}",
                output=Q_(vp / (probe.vth * hmag), ""),
                inputs={
                    "P_o": s.Po.to_pint(),
                    "R_L": s.RL.to_pint(),
                    "V_{th}": Q_(probe.vth, "V"),
                    "|H(j\\omega)|": Q_(hmag, ""),
                },
                assumptions=[
                    "média da meia ponte: (2d − 1)·V_th = m·V_th·sen ωt (amostragem natural)",
                    "H inclui R_on em série com L e a carga R_L ∥ C",
                ],
                reference=REF,
            )
        ).m_as("")
        return Bridge(vcc, r_on, rl, lv, cv, f, k, float(m))

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        br = self.bridge(s, devices, log)
        if br.m > s.m_max:
            raise ValueError(
                f"Índice de modulação {br.m:.3g} acima do máximo ({s.m_max:g}): aumente VCC "
                "ou reduza a potência."
            )
        fs = br.f * br.k
        if s.fc.to_pint().m_as("Hz") > fs / 5:
            warnings.append(
                DesignWarning(
                    code="filtro",
                    message="O corte do filtro está acima de fs/5: a ondulação de chaveamento "
                    "na carga fica grande.",
                )
            )
        if s.fc.to_pint().m_as("Hz") < 3 * br.f:
            warnings.append(
                DesignWarning(
                    code="filtro",
                    message="O corte do filtro está perto da frequência do sinal: a resposta "
                    "do filtro atenua e defasa o sinal.",
                )
            )
        sol = solve(br)
        t, il, vo = sol.t, sol.il, sol.vo
        r_hi = np.where(sol.state > 0, br.r_on, R_OFF)
        r_lo = np.where(sol.state > 0, R_OFF, br.r_on)
        v_sw = sol.state * br.vth - br.rth * il
        i_hi = (br.vcc - v_sw) / r_hi  # from +VCC into the switch node
        i_lo = (v_sw + br.vcc) / r_lo  # from the switch node into −VCC
        po = _avg(t, vo**2) / br.rl
        pi = br.vcc * _avg(t, i_hi) + br.vcc * _avg(t, i_lo)
        p1 = _avg(t, i_hi**2 * r_hi)
        p2 = _avg(t, i_lo**2 * r_lo)
        vo_rms = math.sqrt(_avg(t, vo**2))
        exact = (
            "solução exata do circuito chaveado (instantes de comutação e exponencial de matriz)"
        )
        log.add(
            record(
                "Po",
                "Potência na carga",
                r"P_o = \frac{1}{T}\int_0^T \frac{v_o^2}{R_L}\,dt",
                output=Q_(po, "W"),
                assumptions=[exact],
                reference=REF,
            )
        )
        log.add(
            record(
                "Pi",
                "Potência das fontes",
                r"P_i = V_{CC}\,\bar i_{+} + V_{CC}\,\bar i_{-}",
                output=Q_(pi, "W"),
                assumptions=[exact, "a fonte negativa recebe energia em parte do ciclo"],
                reference=REF,
            )
        )
        p_cond = max(p1, p2)
        log.add(
            record(
                "P_cond",
                "Perda de condução na chave mais solicitada",
                r"P_{cond} = \frac{1}{T}\int_0^T i_Q^2 R_{on}\,dt",
                output=Q_(p_cond, "W"),
                inputs={"R_{on}": Q_(br.r_on, "ohm")},
                assumptions=[exact],
                reference=REF,
            )
        )
        p_sw = 0.0
        il_abs = _avg(t, np.abs(il))
        recs = [devices[d].record for d in ("Q1", "Q2")]
        trf = []
        for rec in recs:
            if rec is None:
                continue
            tr_, tf_ = quantity(rec, "tr", ("typ", "max")), quantity(rec, "tf", ("typ", "max"))
            if tr_ is not None and tf_ is not None:
                trf.append(float(tr_.m_as("s") + tf_.m_as("s")))
        if trf:
            tsum = max(trf)
            p_sw = log.add(
                record(
                    "P_sw",
                    "Perda de comutação por chave (estimativa, não simulada)",
                    r"P_{sw} \approx \frac{1}{2}\cdot\frac{1}{2}\,(2V_{CC})\,"
                    r"\overline{|i_L|}\,(t_r + t_f)\,f_s",
                    output=Q_(0.25 * 2 * br.vcc * il_abs * tsum * fs, "W"),
                    inputs={
                        "V_{CC}": s.VCC.to_pint(),
                        r"\overline{|i_L|}": Q_(il_abs, "A"),
                        "t_r + t_f": Q_(tsum, "s").to("ns"),
                        "f_s": Q_(fs, "Hz").to("kHz"),
                    },
                    assumptions=[
                        "comutação dura com variação linear de tensão e corrente",
                        "tr e tf típicos do datasheet, nas condições de ensaio dele (RG, VDD)",
                        "metade das comutações em cada chave",
                    ],
                    reference=MOHAN,
                )
            ).m_as("W")
        else:
            warnings.append(
                DesignWarning(
                    code="estimativa",
                    message="Sem tr/tf no datasheet (ou sem componente): perda de comutação "
                    "não estimada.",
                )
            )
        warnings.append(
            DesignWarning(
                code="modelo",
                message="Chaves ideais com RDS(on), sem tempo morto, sem diodo de corpo e sem "
                "capacitâncias; o driver de porta (com tempo morto e bootstrap) não é "
                "projetado aqui.",
            )
        )
        # residual ripple near the zero crossing of vo (largest duty-cycle ripple)
        n_per = 3 * (N_SUB + 1)
        mid = len(t) // 2
        j0 = mid - (mid % n_per)
        win = vo[j0 : j0 + n_per]
        ripple = float(np.max(win) - np.min(win))
        grid = np.linspace(0, 1 / br.f, 4096, endpoint=False)
        tt, idx = np.unique(t, return_index=True)
        vo_u = np.interp(grid, tt, vo[idx])
        il_u = np.interp(grid, tt, il[idx])
        spec_ = np.fft.rfft(vo_u) / vo_u.size
        amp = np.abs(spec_[:51]) * 2
        thd = float(np.sqrt(np.sum(amp[2:] ** 2)) / amp[1] * 100)
        summary: dict[str, pint.Quantity] = {
            "fs": Q_(fs, "Hz").to("kHz"),
            "L": Q_(br.L, "H").to("uH"),
            "C": Q_(br.C, "F").to("uF"),
            "f0": Q_(1 / (2 * math.pi * math.sqrt(br.L * br.C)), "Hz").to("kHz"),
            "R_on": Q_(br.r_on, "ohm"),
            "m": Q_(br.m, ""),
            "Vp": Q_(float(np.max(vo)), "V"),
            "Vo_rms": Q_(vo_rms, "V"),
            "Po": Q_(po, "W"),
            "Pi": Q_(pi, "W"),
            "eff": Q_(po / pi * 100, "percent"),
            "IL_max": Q_(float(np.max(il)), "A"),
            "IL_rms": Q_(math.sqrt(_avg(t, il**2)), "A"),
            "ripple_pp": Q_(ripple, "V").to("mV"),
            "I_high_avg": Q_(_avg(t, i_hi), "A"),
            "P_cond": Q_(p_cond, "W"),
            "P_sw": Q_(p_sw, "W"),
            "THD": Q_(thd, "percent"),
        }
        i_pk = float(np.max(np.abs(il)))
        stresses = []
        for d in ("Q1", "Q2"):
            stresses += [
                Stress(
                    designator=d,
                    key="VDS",
                    label="Tensão dreno-fonte (chave aberta)",
                    value=QuantityModel(value=2 * br.vcc, unit="V"),
                    calc_step_id="R_on",
                ),
                Stress(
                    designator=d,
                    key="ID",
                    label="Corrente de pico (indutor)",
                    value=QuantityModel(value=i_pk, unit="A"),
                    calc_step_id="Po",
                ),
            ]
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses={"Q1": Q_(p_cond + p_sw, "W"), "Q2": Q_(p_cond + p_sw, "W")},
            warnings=warnings,
            convergence_keys=("Po",),
            traces={
                "Tensão na carga": make_trace("V", vo_u),
                "Corrente no indutor": make_trace("A", il_u),
            },
            trace_period=Q_(1 / br.f, "s"),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        br = self.bridge(s, devices, CalcLog())
        x0 = solve(br).x0
        ts = 1 / (br.f * br.k)
        lines = [
            f".model SWD SW(VT=0 VH=0 RON={br.r_on:.9g} ROFF={R_OFF:.6g})",
            f"VCC vcc 0 DC {br.vcc:.9g}",
            f"VEE vee 0 DC {-br.vcc:.9g}",
            f"VREF r 0 SIN(0 {br.m:.12g} {br.f:.12g})",
            f"VTRI tri 0 PWL(0 -1 {ts / 2:.12g} 1 {ts:.12g} -1) r=0",
            "ECMP ctl 0 r tri 1",
            "VSH vcc dh 0",
            "S1 dh sw ctl 0 SWD",
            "S2 sw vee 0 ctl SWD",
            "VSL sw lx 0",
            f"L1 lx o {br.L:.9g} IC={x0[0]:.9g}",
            f"C1 o 0 {br.C:.9g} IC={x0[1]:.9g}",
            f"RL o 0 {br.rl:.9g}",
        ]
        checks = [
            SimCheck(
                quantity="Tensão eficaz na carga",
                summary_key="Vo_rms",
                metric="rms",
                probe="v(o)",
                tolerance_pct=0.5,
                justification="mesmas chaves (RON/ROFF) e mesmo comparador",
            ),
            SimCheck(
                quantity="Corrente de pico no indutor",
                summary_key="IL_max",
                metric="max",
                probe="i(vsl)",
                tolerance_pct=1.0,
                justification="mesmo circuito; o passo do simulador desloca os instantes de "
                "comutação",
            ),
            SimCheck(
                quantity="Corrente média da fonte positiva",
                summary_key="I_high_avg",
                metric="avg",
                probe="i(vsh)",
                tolerance_pct=2.0,
                justification="corrente pulsada: média sensível ao instante de comutação",
            ),
        ]
        return Circuit(
            title=f"{self.id}: meia ponte classe D",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=2 / br.f, unit="s"),
            tran_step=QuantityModel(value=ts / 400, unit="s"),
            period=QuantityModel(value=1 / br.f, unit="s"),
            probes={"Tensão na carga": "v(o)", "Corrente no indutor": "i(vsl)"},
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        parts = {c.designator: c.part_number for c in result.selection}
        sm = result.summary
        svg = Svg(620, 340)
        svg.title(title)
        svg.terminal(250, 40, f"+{s.VCC.value:g} V")
        svg.terminal(250, 310, f"−{s.VCC.value:g} V")
        g1, d1, s1 = svg.nmos(240, 110, "Q1", parts.get("Q1", ""))
        g2, d2, s2 = svg.nmos(240, 240, "Q2", parts.get("Q2", ""))
        svg.wire(d1, (d1[0], 40))
        svg.wire(s2, (s2[0], 310))
        svg.wire(s1, (s1[0], 175), d2)
        svg.dot(s1[0], 175)
        svg.text(s1[0] + 6, 170, "sw")
        svg.box(60, 150, 100, 50, "PWM", "comparador + driver")
        svg.wire((160, 165), (190, 165), (190, g1[1]), g1)
        svg.wire((160, 185), (200, 185), (200, g2[1]), g2)
        svg.text(205, g2[1] - 6, "inv.")
        svg.inductor_h(s1[0], 400, 175, "L", format_eng(sm["L"].to_pint()))
        svg.cap_v(430, 175, 280, "C", format_eng(sm["C"].to_pint()))
        svg.wire((400, 175), (520, 175))
        svg.resistor_v(520, 175, 280, "RL", format_eng(s.RL.to_pint()))
        svg.wire((430, 280), (520, 280))
        svg.ground(475, 280)
        svg.ac_source(30, 175, 280, "vin")
        svg.wire((30, 175), (60, 175))
        svg.ground(30, 280)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        sm = result.summary
        return [
            passive(
                "L1",
                "Indutor do filtro (núcleo sem saturar, baixa resistência)",
                format_eng(sm["L"].to_pint()),
                f"Ipico ≥ {format_eng(sm['IL_max'].to_pint())}, "
                f"Ief ≥ {format_eng(sm['IL_rms'].to_pint())}",
            ),
            passive(
                "C1",
                "Capacitor do filtro (filme, baixa ESR)",
                format_eng(sm["C"].to_pint()),
                f"V ≥ {format_eng(sm['Vp'].to_pint())} de pico",
            ),
            passive(
                "RL",
                "Carga (alto-falante ou resistor de potência)",
                format_eng(s.RL.to_pint()),
                f"P ≥ {format_eng(sm['Po'].to_pint())}",
            ),
            passive(
                "U1",
                "Modulador PWM (triangular + comparador) e driver de meia ponte",
                "",
                "com tempo morto e bootstrap; não projetado neste módulo",
            ),
        ]
