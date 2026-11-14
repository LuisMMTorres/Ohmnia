"""Op-amp device bench (BD-AMPOP) and virtual laboratory tests (BV-AMPOP).

BD-AMPOP shows the macromodel of ``design/opamp.py``: open-loop gain A(f) = A0/(1 + jf/fb),
the slew-limited step response and the output swing.

BV-AMPOP reproduces the classical laboratory measurements on the simulator (ngspice), each
recovering one parameter of the model, which must agree with the value the model was built
from (Pertence, *Amplificadores operacionais e filtros ativos*, chapter on op-amp parameters
and their measurement; test conditions as in the TI LM741/TL071 datasheets):

* OFFSET: inputs grounded, noise gain G = 1 + R2/R1 = 1001 with the bias compensation
  resistor R1∥R2 at the + input: V_OS = V_o/G;
* IB: follower with R_B = 1 MΩ in series with the + input, I_B+ = −(V_o − V_o,ref)/R_B; and
  R_F = 1 MΩ from the output to the − input (+ grounded), I_B− = (V_o − V_o,ref)/R_F, with the
  plain follower as reference; I_B = (I_B+ + I_B−)/2, I_OS = I_B+ − I_B− + 2V_OS/R_in (the
  differential input resistance of the datasheet carries V_OS/R_in through each resistor);
* A0: inverting gain 1000 at two input levels, A0 = ΔV_o/Δ(v+ − v−) at the pins;
* CMRR: the offset circuit with its reference lifted to V_cm = ±5 V,
  CMRR = ΔV_cm/(ΔV_o/G + ΔV_o/A0) (the second term removes the finite-gain error);
* PSRR: the offset circuit at ±15 V and ±12 V supplies, PSRR = ΔV_S/(ΔV_o/G);
* GBW: non-inverting gain 101, GBW = |H(0)|·f_H (exact for a single pole);
* SR: follower, 10 V input step, slope of the output between 20 % and 80 %;
* EXCURSÃO: open loop with a ±1 V sine, maximum and minimum of the output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pint
from numpy.typing import NDArray

from circuitos.core.calc import BibRef, CalcStep, record
from circuitos.core.units import Q_
from circuitos.design.mna import Circuit as Mna
from circuitos.design.opamp import TRAN_OPTIONS, OpAmp
from circuitos.simulation.backend import SimulatorBackend, make_backend
from circuitos.simulation.results import Plot

PERT = BibRef(
    book="Pertence, Amplificadores operacionais e filtros ativos",
    edition="8ª",
    chapter="parâmetros do ampop e sua medição",
)
FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class BenchTest:
    id: str
    name: str
    measured: pint.Quantity
    expected: pint.Quantity
    tolerance_pct: float
    method: str

    @property
    def error_pct(self) -> float:
        e = float(self.expected.magnitude)
        m = float(self.measured.m_as(self.expected.units))
        return abs(m - e) / abs(e) * 100 if e else abs(m) * 100

    @property
    def ok(self) -> bool:
        return self.error_pct <= self.tolerance_pct


@dataclass
class BenchResult:
    tests: list[BenchTest]
    steps: list[CalcStep]
    bode_f: FloatArray
    bode_mag: FloatArray  # V/V
    bode_phase: FloatArray  # deg
    step_t: FloatArray  # s
    step_in: FloatArray
    step_out: FloatArray
    netlists: dict[str, str]


def _dc_circuit(u: OpAmp, vs: float) -> Mna:
    """All DC test fixtures in one netlist (independent op-amp instances)."""
    c = Mna()
    g_r1, g_r2 = 100.0, 100e3
    rp = g_r1 * g_r2 / (g_r1 + g_r2)
    rb = 1e6
    c.V("sp", "sp", "0", vs)
    c.V("sn", "0", "sn", vs)
    c.V("sp2", "sp2", "0", vs - 3)
    c.V("sn2", "0", "sn2", vs - 3)

    def offset(tag: str, ref: str, sup: tuple[str, str]) -> None:
        c.R(f"1{tag}", f"n{tag}", ref, g_r1)
        c.R(f"2{tag}", f"n{tag}", f"o{tag}", g_r2)
        c.R(f"p{tag}", f"p{tag}", ref, rp)
        u.add(c, f"U{tag}", f"p{tag}", f"n{tag}", f"o{tag}", sup)

    offset("os", "0", ("sp", "sn"))
    # bias currents
    u.add(c, "Uref", "0", "oref", "oref", ("sp", "sn"))
    c.R("bp", "pbp", "0", rb)
    u.add(c, "Ubp", "pbp", "obp", "obp", ("sp", "sn"))
    c.R("bn", "obn", "obn_i", rb)
    u.add(c, "Ubn", "0", "obn_i", "obn", ("sp", "sn"))
    # open-loop gain: inverting ×1000 at ±5 mV
    for tag, vin in (("ga", 5e-3), ("gb", -5e-3)):
        c.V(f"i{tag}", f"i{tag}", "0", vin)
        c.R(f"1{tag}", f"i{tag}", f"n{tag}", 1e3)
        c.R(f"2{tag}", f"n{tag}", f"o{tag}", 1e6)
        u.add(c, f"U{tag}", "0", f"n{tag}", f"o{tag}", ("sp", "sn"))
    # common mode: reference lifted to ±5 V
    for tag, vcm in (("ca", 5.0), ("cb", -5.0)):
        c.V(f"m{tag}", f"m{tag}", "0", vcm)
        offset(tag, f"m{tag}", ("sp", "sn"))
    # supply: ±(VS − 3) V
    offset("ps", "0", ("sp2", "sn2"))
    return c


def _ac_circuit(u: OpAmp) -> Mna:
    c = Mna()
    c.V("sig", "in", "0", 0.0, 1.0)
    c.R("1", "n", "0", 1e3)
    c.R("2", "n", "o", 100e3)
    u.add(c, "U1", "in", "n", "o")
    return c


def _tran_netlist(u: OpAmp, kind: str, period: float) -> str:
    if kind == "sr":
        src = f"Vin in 0 PULSE(-5 5 {period / 4:.9g} 1n 1n {period / 2:.9g} {period:.9g})"
        lines = [src, *u.nonlinear_lines("U1", "in", "o", "o"), "RL o 0 10k"]
    else:
        src = f"Vin in 0 SIN(0 1 {1 / period:.9g})"
        lines = [src, *u.nonlinear_lines("U1", "in", "0", "o"), "RL o 0 10k"]
    return "\n".join([f"* BV-AMPOP {kind}", TRAN_OPTIONS, *lines])


def _corner_fh(f: FloatArray, mag: FloatArray) -> float:
    level = mag[0] / math.sqrt(2)
    j = int(np.nonzero(mag < level)[0][0])
    i = j - 1
    d0, d1, dl = (20 * math.log10(x) for x in (mag[i], mag[j], level))
    lf = math.log10(f[i]) + (dl - d0) * (math.log10(f[j]) - math.log10(f[i])) / (d1 - d0)
    return float(10**lf)


def _v(plot: Plot, node: str) -> float:
    return float(np.real(plot[f"v({node})"].data)[0])


def _vec(plot: Plot, name: str) -> FloatArray:
    return np.asarray(np.real(plot[name].data), dtype=np.float64)


def run_bench(u: OpAmp, vs: float, backend: SimulatorBackend | None = None) -> BenchResult:
    """Run every BV-AMPOP test on the simulator for the model ``u`` at ±``vs`` supplies."""
    be = backend or make_backend()
    steps: list[CalcStep] = []
    tests: list[BenchTest] = []
    netlists: dict[str, str] = {}

    def step(sid: str, desc: str, latex: str, out: pint.Quantity, **inputs: pint.Quantity) -> None:
        steps.append(record(sid, desc, latex, output=out, inputs=inputs, reference=PERT).step)

    # ------------------------------------------------------------- DC tests (.op)
    dc = "\n".join(["* BV-AMPOP DC", *_dc_circuit(u, vs).netlist(), ".op"])
    netlists["dc"] = dc
    op = be.run(dc).plot("op")
    g = 1 + 100e3 / 100.0
    # open-loop gain first: it corrects the offset reading (closed-loop gain G/(1 + G/A0))
    a0 = (_v(op, "oga") - _v(op, "ogb")) / -(_v(op, "nga") - _v(op, "ngb"))
    vos = _v(op, "oos") / g * (1 + g / a0)
    step(
        "BV-OFFSET",
        "Tensão de offset (ganho de ruído 1001, corrigido pelo A0 medido)",
        r"V_{OS} = \frac{V_o}{G}\left(1 + \frac{G}{A_0}\right)",
        Q_(vos, "V").to("mV"),
        V_o=Q_(_v(op, "oos"), "V"),
        G=Q_(g, ""),
        A_0=Q_(a0, ""),
    )
    tests.append(
        BenchTest(
            "BV-AMPOP-OFFSET",
            "Tensão de offset",
            Q_(vos, "V").to("mV"),
            Q_(u.Vos, "V").to("mV"),
            1.0,
            "Ios·R2 residual",
        )
    )
    vref = _v(op, "oref")
    ibp = -(_v(op, "obp") - vref) / 1e6
    ibn = (_v(op, "obn") - vref) / 1e6
    ib, ios = (ibp + ibn) / 2, ibp - ibn
    if math.isfinite(u.Rin):
        # the differential input resistance carries VOS/Rin through each test resistor (with
        # opposite signs): it cancels in IB and adds −2·VOS/Rin to IOS
        ios += 2 * vos / u.Rin
    step(
        "BV-IB",
        "Correntes de polarização (R = 1 MΩ em cada entrada)",
        r"I_{B+} = -\frac{V_{o,a} - V_{o,ref}}{R_B},\ I_{B-} = \frac{V_{o,b} - V_{o,ref}}{R_F},"
        r"\ I_B = \frac{I_{B+} + I_{B-}}{2},\ I_{OS} = I_{B+} - I_{B-} + \frac{2V_{OS}}{R_{in}}",
        Q_(ib, "A").to("nA"),
        I_Bp=Q_(ibp, "A").to("nA"),
        I_Bn=Q_(ibn, "A").to("nA"),
    )
    if u.Ib:
        tests.append(
            BenchTest(
                "BV-AMPOP-IB",
                "Corrente de polarização",
                Q_(ib, "A").to("nA"),
                Q_(u.Ib, "A").to("nA"),
                2.0,
                "erro de ganho finito no seguidor",
            )
        )
    if u.Ios:
        tests.append(
            BenchTest(
                "BV-AMPOP-IOS",
                "Corrente de offset",
                Q_(ios, "A").to("nA"),
                Q_(u.Ios, "A").to("nA"),
                5.0,
                "diferença de duas medidas",
            )
        )
    dvo = _v(op, "oga") - _v(op, "ogb")
    dvd = -(_v(op, "nga") - _v(op, "ngb"))
    a0 = dvo / dvd
    step(
        "BV-A0",
        "Ganho em malha aberta (ΔVo/Δvd nos pinos)",
        r"A_0 = \frac{\Delta V_o}{\Delta v_d}",
        Q_(a0, ""),
        dVo=Q_(dvo, "V"),
        dvd=Q_(dvd, "V").to("uV"),
    )
    tests.append(
        BenchTest(
            "BV-AMPOP-A0",
            "Ganho em malha aberta",
            Q_(a0, ""),
            Q_(u.A0, ""),
            1.0,
            "Rin e erro de modo comum nos pinos",
        )
    )
    if math.isfinite(u.CMRR):
        dvoc = (_v(op, "oca") - 5.0) - (_v(op, "ocb") + 5.0)
        d_out = _v(op, "oca") - _v(op, "ocb")
        cmrr = 10.0 / (dvoc / g + d_out / a0)
        step(
            "BV-CMRR",
            "Rejeição de modo comum (referência em ±5 V)",
            r"CMRR = \frac{\Delta V_{cm}}{\Delta(V_o - V_{cm})/G + \Delta V_o/A_0}",
            Q_(20 * math.log10(cmrr), ""),
            A0=Q_(a0, ""),
        )
        tests.append(
            BenchTest(
                "BV-AMPOP-CMRR",
                "CMRR (dB)",
                Q_(20 * math.log10(cmrr), ""),
                Q_(20 * math.log10(u.CMRR), ""),
                0.5,
                "em dB",
            )
        )
    if math.isfinite(u.PSRR):
        dvos = (_v(op, "oos") - _v(op, "ops")) / g
        psrr = 3.0 / dvos
        step(
            "BV-PSRR",
            "Rejeição da fonte (±VS → ±(VS − 3 V))",
            r"PSRR = \frac{\Delta V_S}{\Delta V_{OS}}",
            Q_(20 * math.log10(psrr), ""),
            dVOS=Q_(dvos, "V").to("uV"),
        )
        tests.append(
            BenchTest(
                "BV-AMPOP-PSRR",
                "PSRR (dB)",
                Q_(20 * math.log10(psrr), ""),
                Q_(20 * math.log10(u.PSRR), ""),
                0.5,
                "em dB",
            )
        )
    # ------------------------------------------------------------- GBW (.ac)
    acn = "\n".join(["* BV-AMPOP GBW", *_ac_circuit(u).netlist(), ".ac dec 200 1 1e9"])
    netlists["ac"] = acn
    ac = be.run(acn).plot("ac")
    f = _vec(ac, "frequency")
    mag = np.abs(np.asarray(ac["v(o)"].data, dtype=np.complex128))
    fh = _corner_fh(f, mag)
    gbw = mag[0] * fh
    step(
        "BV-GBW",
        "Produto ganho-banda (não inversor ×101)",
        r"GBW = |H(0)|\,f_H",
        Q_(gbw, "Hz").to("MHz"),
        H0=Q_(float(mag[0]), ""),
        f_H=Q_(fh, "Hz").to("kHz"),
    )
    tests.append(
        BenchTest(
            "BV-AMPOP-GBW",
            "Produto ganho-banda",
            Q_(gbw, "Hz").to("MHz"),
            Q_(u.GBW, "Hz").to("MHz"),
            1.0,
            "interpolação a 200 pontos/década",
        )
    )
    # ------------------------------------------------------------- SR and swing (.tran)
    t_sl = 10 / u.SR if math.isfinite(u.SR) else 1e-6
    period = max(40 * t_sl, 20 / u.GBW)
    srn = (
        _tran_netlist(u, "sr", period)
        + f"\n.tran {period / 4000:.6g} {period:.6g} 0 {period / 4000:.6g} uic"
    )
    netlists["sr"] = srn
    tr = be.run(srn).plot("tran")
    t = _vec(tr, "time")
    vo = _vec(tr, "v(o)")
    vin = _vec(tr, "v(in)")
    sel = t >= period / 4
    tt, yy = t[sel], vo[sel]
    lo, hi = float(yy[0]), float(np.max(yy))
    y20, y80 = lo + 0.2 * (hi - lo), lo + 0.8 * (hi - lo)
    t20 = float(np.interp(y20, yy[: int(np.argmax(yy)) + 1], tt[: int(np.argmax(yy)) + 1]))
    t80 = float(np.interp(y80, yy[: int(np.argmax(yy)) + 1], tt[: int(np.argmax(yy)) + 1]))
    sr = (y80 - y20) / (t80 - t20)
    step(
        "BV-SR",
        "Taxa de inclinação (seguidor, degrau de 10 V)",
        r"SR = \frac{v_{80\%} - v_{20\%}}{t_{80\%} - t_{20\%}}",
        Q_(sr, "V/s").to("V/us"),
        t_20=Q_(t20, "s").to("us"),
        t_80=Q_(t80, "s").to("us"),
    )
    if math.isfinite(u.SR):
        tests.append(
            BenchTest(
                "BV-AMPOP-SR",
                "Taxa de inclinação",
                Q_(sr, "V/s").to("V/us"),
                Q_(u.SR, "V/s").to("V/us"),
                2.0,
                "trecho de 20 % a 80 %",
            )
        )
    sw_period = 1e-3
    swn = _tran_netlist(u, "excursao", sw_period) + (
        f"\n.tran {sw_period / 2000:.6g} {2 * sw_period:.6g} 0 {sw_period / 2000:.6g} uic"
    )
    netlists["excursao"] = swn
    sw = be.run(swn).plot("tran")
    vsw = _vec(sw, "v(o)")
    step(
        "BV-EXC",
        "Excursão da saída (malha aberta, entrada ±1 V)",
        r"V_{o,max},\ V_{o,min}",
        Q_(float(vsw.max()), "V"),
        V_omin=Q_(float(vsw.min()), "V"),
    )
    if math.isfinite(u.v_hi):
        tests.append(
            BenchTest(
                "BV-AMPOP-EXCURSAO+",
                "Excursão positiva",
                Q_(float(vsw.max()), "V"),
                Q_(u.v_hi, "V"),
                0.5,
                "grampo do modelo",
            )
        )
        tests.append(
            BenchTest(
                "BV-AMPOP-EXCURSAO-",
                "Excursão negativa",
                Q_(float(vsw.min()), "V"),
                Q_(u.v_lo, "V"),
                0.5,
                "grampo do modelo",
            )
        )
    # ------------------------------------------------------------- BD: A(f)
    fb = np.logspace(-1, math.log10(max(10 * u.GBW, 1e6)), 300)
    a = np.array([u.a(x) for x in fb])
    k = max(int(sel.argmax()) - 50, 0)
    return BenchResult(
        tests=tests,
        steps=steps,
        bode_f=fb,
        bode_mag=np.abs(a),
        bode_phase=np.degrees(np.angle(a)),
        step_t=t[k:],
        step_in=vin[k:],
        step_out=vo[k:],
        netlists=netlists,
    )
