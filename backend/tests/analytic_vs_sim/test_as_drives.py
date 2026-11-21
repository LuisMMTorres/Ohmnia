"""AS-DRV: drives, machines and the thermocouple (Fase 11 leftovers) against their analytic models.

Rule 4: each SPICE model must agree with the closed form it implements.

* Induction motor in steady state: per-phase equivalent circuit (Chapman, *Electric Machinery
  Fundamentals*, 5th ed., ch. 6), :mod:`circuitos.machines.induction`.
* Inverter: V/f law and ramps as specified in the symbol; the SPWM fundamental with third
  harmonic injection (Holmes and Lipo, *Pulse Width Modulation for Power Converters*, ch. 6).
* Soft-starter: voltage ramp and current limit (WEG SSW-07 manual, p. 31 to 33).
* Stepper: position = steps × step angle, static load angle asin(T_L/(K I))/N (Kenjo, *Stepping
  Motors and Their Microprocessor Controls*, 2nd ed., ch. 4), :mod:`circuitos.machines.stepper`.
* Thermocouple: NIST ITS-90 reference function, :mod:`circuitos.machines.thermocouple`.
* 12-terminal motor: each of the four dual-voltage connections (WEG, *Guia de especificação de
  motores elétricos*, ligações de 12 cabos) gives the 380 V wye motor's steady state.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from circuitos.machines import thermocouple as tc
from circuitos.machines.induction import InductionParams, steady_state
from circuitos.machines.stepper import load_angle_deg
from circuitos.schematic.model import Analysis
from circuitos.schematic.runs import SchematicPlan
from tests.unit.schematic.helpers import Builder

pytestmark = pytest.mark.ngspice

# defaults of the induction_motor symbol (didactic 4-pole, 380 V Y motor)
MOTOR = InductionParams(rs=1.5, rr=1.2, xls=2.5, xlr=2.5, xm=60, poles=4, fnom=60, j=0.02, b=0.005)
V_PHASE = 380 / math.sqrt(3)


@pytest.fixture(scope="module")
def backend():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    return SharedNgspiceBackend()


def _tran(b: Builder, backend, tstop: str, **params: str):  # type: ignore[no-untyped-def]
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": tstop, **params})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    return tran, np.asarray(tran.vectors[tran.scale].data)


def _at(tran, t, name: str, when: float) -> float:  # type: ignore[no-untyped-def]
    return float(np.interp(when, t, tran.vectors[name].data))


def _mean(tran, t, name: str, t0: float, t1: float) -> float:  # type: ignore[no-untyped-def]
    sel = (t >= t0) & (t <= t1)
    return float(np.mean(np.asarray(tran.vectors[name].data)[sel]))


def test_as_drv_01_direct_on_line_steady_state(backend):
    """AS-DRV-01: DOL start with 20 N·m; the steady state is the equivalent circuit's.

    Tolerances: speed 0,2 %, line current and torque 1 %. Starts with 5 to 8 times the rated
    current (the locked-rotor current of the circuit is 39,4 A).
    """
    b = Builder("dol")
    b.add("v3ph", "V1", ["a", "b", "c", "0"], vrms=f"{V_PHASE:.6f}")
    b.add("induction_motor", "M1", ["a", "b", "c"], tl="20")
    tran, t = _tran(b, backend, "2")
    ref = steady_state(MOTOR, 380, 60, 20)
    assert _mean(tran, t, "v(m1_rpm)", 1.8, 2) == pytest.approx(ref.speed_rpm, rel=2e-3)
    assert _mean(tran, t, "v(m1_i)", 1.8, 2) == pytest.approx(ref.i1, rel=0.01)
    assert _mean(tran, t, "v(m1_te)", 1.8, 2) == pytest.approx(ref.torque, rel=0.01)
    i_start = float(np.max(tran.vectors["v(m1_i)"].data))
    assert 5 * ref.i1 < i_start < 8 * ref.i1


def test_as_drv_02_vf_inverter_at_half_speed(backend):
    """AS-DRV-02: V/f inverter, AI = 5 V → 30 Hz, V = vnom (boost + (1 − boost) f/fnom).

    Ramp: 60 Hz in 5 s → 30 Hz at 2,5 s. Quadratic load (20 N·m at 1800 rpm). Steady state as
    the equivalent circuit at 30 Hz and that voltage (reactances scale with f). Tolerance 0,5 %.
    """
    b = Builder("vfd")
    b.add("vdc", "V1", ["ai", "0"], dc="5")
    b.add("vdc", "V2", ["run", "0"], dc="24")
    b.add("vfd", "INV1", ["ai", "0", "run", "0", "u", "v", "w"])
    b.add("induction_motor", "M1", ["u", "v", "w"], tl="20", load="quadrática")
    tran, t = _tran(b, backend, "6")
    assert _at(tran, t, "v(inv1_f)", 1.25) == pytest.approx(15, rel=0.01)
    assert _at(tran, t, "v(inv1_f)", 5.9) == pytest.approx(30, rel=1e-3)
    v_cmd = 380 * (0.03 + 0.97 * 0.5)
    assert _at(tran, t, "v(inv1_v)", 5.9) == pytest.approx(v_cmd, rel=1e-3)
    ref = steady_state(MOTOR, v_cmd, 30, 20, quadratic=True)
    assert _mean(tran, t, "v(m1_rpm)", 5.5, 6) == pytest.approx(ref.speed_rpm, rel=5e-3)
    assert _mean(tran, t, "v(m1_i)", 5.5, 6) == pytest.approx(ref.i1, rel=0.01)


def test_as_drv_03_spwm_fundamental(backend):
    """AS-DRV-03: SPWM with third harmonic injection, 5 kHz: the line voltage fundamental is
    the commanded one, and the motor runs as with the sinusoidal output.

    Fundamental by Fourier over the last 10 cycles. Tolerances: voltage 1,5 %, speed 0,5 %.
    """
    b = Builder("spwm")
    b.add("vdc", "V1", ["ai", "0"], dc="10")
    b.add("vdc", "V2", ["run", "0"], dc="24")
    b.add("vfd", "INV1", ["ai", "0", "run", "0", "u", "v", "w"], mode="SPWM", accel="0.2")
    b.add("induction_motor", "M1", ["u", "v", "w"], tl="10", load="quadrática")
    tran, t = _tran(b, backend, "1.2")
    sel = t >= 1.2 - 10 / 60
    tt = t[sel]
    vuv = np.asarray(tran.vectors["v(u)"].data)[sel] - np.asarray(tran.vectors["v(v)"].data)[sel]
    w = 2 * math.pi * 60
    span = tt[-1] - tt[0]
    a = 2 / span * np.trapezoid(vuv * np.cos(w * tt), tt)
    bb = 2 / span * np.trapezoid(vuv * np.sin(w * tt), tt)
    assert math.hypot(a, bb) / math.sqrt(2) == pytest.approx(380, rel=0.015)
    ref = steady_state(MOTOR, 380, 60, 10, quadratic=True)
    assert _mean(tran, t, "v(m1_rpm)", 1.0, 1.2) == pytest.approx(ref.speed_rpm, rel=5e-3)


@pytest.mark.parametrize("control", ["rampa de tensão", "limitação de corrente"])
def test_as_drv_04_soft_starter(backend, control):
    """AS-DRV-04: soft-starter on the same motor and load as AS-DRV-01 (quadratic load).

    Voltage ramp: k = vinit + (1 − vinit) t/tacc (0,35 → 1 in 5 s), tolerance 1 %.
    Current limit (20 A): the line current never exceeds the limit by more than 3 %.
    Both end in bypass at the DOL operating point (speed 0,2 %).
    """
    b = Builder("ss")
    b.add("v3ph", "V1", ["a", "b", "c", "0"], vrms=f"{V_PHASE:.6f}")
    b.add("vpwl", "V2", ["run", "0"], points="0 0 0.1 0 0.101 24")
    b.add("soft_starter", "SS1", ["a", "b", "c", "run", "0", "t1", "t2", "t3"],
          control=control, ilim="20")  # fmt: skip
    b.add("induction_motor", "M1", ["t1", "t2", "t3"], tl="20", load="quadrática")
    tran, t = _tran(b, backend, "7")
    if control == "rampa de tensão":
        assert _at(tran, t, "v(ss1_k)", 2.6) == pytest.approx(0.35 + 0.65 * 2.5 / 5, rel=0.01)
    else:
        assert float(np.max(tran.vectors["v(ss1_i)"].data)) < 20 * 1.03
    assert _at(tran, t, "v(ss1_kv)", 6.9) == pytest.approx(1.0, abs=1e-6)  # bypass
    ref = steady_state(MOTOR, 380, 60, 20, quadratic=True)
    assert _mean(tran, t, "v(m1_rpm)", 6.5, 7) == pytest.approx(ref.speed_rpm, rel=2e-3)


def _pulses(n: int, t0: float, period: float) -> str:
    pts = ["0 0"]
    for i in range(n):
        a = t0 + i * period
        pts += [f"{a:.6g} 0", f"{a + 1e-6:.6g} 5", f"{a + period / 2:.6g} 5",
                f"{a + period / 2 + 1e-6:.6g} 0"]  # fmt: skip
    return " ".join(pts)


def test_as_drv_05_stepper_position_and_load_angle(backend):
    """AS-DRV-05: 17HS19-2004S1 on the STEP/DIR driver, full step, 1,5 A per phase.

    Home: current vector at 45° → rotor at 0,9°. 40 steps forward (DIR high) at 50 steps/s,
    then 10 back: 0,9 + 30 × 1,8 = 54,9°. With a constant load of 0,15 N·m the rotor lags by
    asin(T_L/(K I))/N, K = 0,59/(√2 × 2,0) and I = 1,5 A. Tolerance 0,05° (2,8 % of a step).
    Winding current = reference (1,5 × cos 45°), tolerance 1 %.
    """
    k = 0.59 / (math.sqrt(2) * 2.0)
    b = Builder("passo")
    b.add("vdc", "V1", ["vm", "0"], dc="24")
    # 50 pulses at 50 steps/s from 10 ms (each step settles); DIR low after the 40th
    b.add("vpwl", "V2", ["step", "0"], points=_pulses(50, 10e-3, 20e-3))
    b.add("vpwl", "V3", ["dir", "0"], points="0 5 0.8 5 0.8001 0")
    b.add("stepper_driver", "DRV1", ["step", "dir", "en", "0", "vm", "a1", "a2", "b1", "b2"],
          ifull="1.5")  # fmt: skip
    b.add("stepper_motor", "M1", ["a1", "a2", "b1", "b2"], km=f"{k:.6g}", tl="0.15", b="2e-3")
    tran, t = _tran(b, backend, "1.1")
    steps = tran.vectors["drv1.steps"].data
    assert _at(tran, t, "drv1.steps", 1.09) == 30
    assert float(np.max(steps)) == 40
    lag = load_angle_deg(0.15, k, 1.5, 1.8)
    assert _mean(tran, t, "v(m1_deg)", 1.05, 1.1) == pytest.approx(0.9 + 30 * 1.8 - lag, abs=0.05)
    ia = _mean(tran, t, "i(vdrv1_sa)", 1.05, 1.1)
    assert abs(ia) == pytest.approx(1.5 * math.cos(math.pi / 4), rel=0.01)


@pytest.mark.parametrize("kind", ["J", "K", "T", "E", "N"])
def test_as_drv_06_thermocouple(backend, kind):
    """AS-DRV-06: the SPICE source gives E(T) − E(T_ref) of the NIST function; 1 µV."""
    lo, hi = tc.range_c(kind)
    top = min(hi, 1000.0)
    b = Builder("tc")
    b.add("thermocouple", "TC1", ["p", "0"], type=kind, temp=f"0 {lo + 10:g} 1 {top:g}",
          tref="25")  # fmt: skip
    b.add("resistor", "R1", ["p", "0"], value="1g")
    tran, t = _tran(b, backend, "1", tmax="1m")
    for when in (0.0, 0.3, 0.7, 1.0):
        temp = lo + 10 + (top - lo - 10) * when
        expected = (tc.emf_mv(kind, temp) - tc.emf_mv(kind, 25)) * 1e-3
        assert _at(tran, t, "v(p)", when) == pytest.approx(expected, abs=1e-6)


# 12-terminal connections: line -> terminals tied to it, and the extra links between terminals
_TWELVE = {
    "delta_parallel": (220, {"a": "1 6 7 12", "b": "2 4 8 10", "c": "3 5 9 11"}, []),
    "wye_parallel": (380, {"a": "1 7", "b": "2 8", "c": "3 9"}, ["4 5 6 10 11 12"]),
    "delta_series": (440, {"a": "1 12", "b": "2 10", "c": "3 11"}, ["4 7", "5 8", "6 9"]),
    "wye_series": (760, {"a": "1", "b": "2", "c": "3"}, ["4 7", "5 8", "6 9", "10 11 12"]),
}
_TWELVE_PINS = ("1", "2", "3", "7", "8", "9", "4", "5", "6", "10", "11", "12")


@pytest.mark.parametrize("conn", list(_TWELVE))
def test_as_drv_07_twelve_terminal_connections(backend, conn):
    """AS-DRV-07: 12-terminal motor at 220 V Δ∥, 380 V Y∥, 440 V Δ and 760 V Y with 20 N·m:
    every half-winding works at 220 V, so speed and torque are the 380 V wye motor's and each
    half-winding carries half of its phase current (equivalent circuit, Chapman, 5th ed.,
    ch. 6). Tolerances as AS-DRV-01: speed 0,2 %, currents 1 %. The two halves of a phase
    share the current equally (no circulating current, below 1 % of it).
    """
    v_line, lines, links = _TWELVE[conn]
    node = {}
    for ph, terms in lines.items():
        node.update({t: ph for t in terms.split()})
    for i, group in enumerate(links):
        node.update({t: f"k{i}" for t in group.split()})
    b = Builder(conn)
    b.add("v3ph", "V1", ["a", "b", "c", "0"], vrms=f"{v_line / math.sqrt(3):.6f}")
    b.add("induction_motor_12", "M1", [node[p] for p in _TWELVE_PINS], tl="20")
    tran, t = _tran(b, backend, "2")
    ref = steady_state(MOTOR, 380, 60, 20)
    assert _mean(tran, t, "v(m1_rpm)", 1.8, 2) == pytest.approx(ref.speed_rpm, rel=2e-3)
    assert _mean(tran, t, "v(m1_te)", 1.8, 2) == pytest.approx(ref.torque, rel=0.01)
    assert _mean(tran, t, "v(m1_i)", 1.8, 2) == pytest.approx(ref.i1 / 2, rel=0.01)
    sel = t >= 1.8
    i_circ = np.asarray(tran.vectors["v(m1_da)"].data)[sel] / (4 * 2.5 / (2 * math.pi * 60))
    assert float(np.max(np.abs(i_circ))) < 0.01 * ref.i1
    # line current: the phase current in wye, √3 times it in delta; series halves the turns
    i_line = {"delta_parallel": 380 / 220, "wye_parallel": 1, "delta_series": 380 / 440,
              "wye_series": 0.5}[conn] * ref.i1  # fmt: skip
    sel_t = t[sel]
    ia = np.asarray(tran.vectors["i(v_v1_a)"].data)[sel]
    rms = math.sqrt(float(np.trapezoid(ia**2, sel_t)) / (sel_t[-1] - sel_t[0]))
    assert rms == pytest.approx(i_line, rel=0.015)


def test_as_drv_08_twelve_terminal_reversed_half(backend):
    """AS-DRV-08: Δ∥ at 220 V with the half-winding 7-10 reversed (10 on L1, 7 on L2): 440 V
    drive the loop of the two halves, 4·(R1 + jX1) = 11,7 Ω, about 38 A circulating (eficaz),
    where the motor takes 3 to 4 A. Tolerance 3 % (the loop is the whole impedance)."""
    node = {"1": "a", "6": "a", "10": "a", "12": "a", "2": "b", "4": "b", "7": "b", "8": "b"}
    node |= {"3": "c", "5": "c", "9": "c", "11": "c"}
    b = Builder("rev")
    b.add("v3ph", "V1", ["a", "b", "c", "0"], vrms=f"{220 / math.sqrt(3):.6f}")
    b.add("induction_motor_12", "M1", [node[p] for p in _TWELVE_PINS])
    tran, t = _tran(b, backend, "0.5")
    sel = t >= 0.4
    i_circ = np.asarray(tran.vectors["v(m1_da)"].data)[sel] / (4 * 2.5 / (2 * math.pi * 60))
    rms = math.sqrt(float(np.mean(i_circ**2)))
    expected = 2 * 220 / (4 * math.hypot(1.5, 2.5))
    assert rms == pytest.approx(expected, rel=0.03)
