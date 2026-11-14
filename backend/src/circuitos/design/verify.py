"""Rule 4: run the circuit of a design in the simulator and compare it with the analytic result.

The last source period of a transient run (started from the analytic steady state with
``uic``, so it settles in a few cycles) is resampled on a uniform grid; each :class:`SimCheck`
is measured on it and compared with the analytic value of the summary.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from circuitos.core.units import Q_, QuantityModel
from circuitos.simulation.backend import SimulatorBackend, make_backend
from circuitos.simulation.results import Plot

from .base import Circuit, SimCheck, SimComparison

FloatArray = NDArray[np.float64]
_SI_OF = {str(Q_(1, u).dimensionality): u for u in ("V", "A", "Hz", "s", "W", "ohm")}
N_SAMPLES = 4096

_TERM = re.compile(r"([+-]?)((?:\d+(?:\.\d*)?(?:e[+-]?\d+)?\*)?)([vi]\([^()]+\))")


def vector_sum(plot: Plot, expression: str) -> FloatArray:
    """Evaluate a weighted sum such as ``"v(a)-v(b)+0.57735*i(vx)"`` on a plot's vectors."""
    expr = expression.replace(" ", "").lower()
    terms = _TERM.findall(expr)
    if not terms or "".join(s + c + t for s, c, t in terms) != expr.lstrip("+"):
        raise ValueError(f"Expressão de medida inválida: {expression!r}")
    total: FloatArray | None = None
    for sign, coef, name in terms:
        k = float(coef[:-1]) if coef else 1.0
        data = k * np.real(plot[name].data).astype(np.float64)
        data = -data if sign == "-" else data
        total = data if total is None else total + data
    assert total is not None
    return total


@dataclass
class SteadyState:
    """Last period of a run: the simulator's own time points and a uniform resampling.

    Averages, RMS values and power use the simulator points (trapezoidal integration, so a
    fast edge counts for its real duration); the spectrum uses the uniform grid.
    """

    t_raw: FloatArray
    raw: dict[str, FloatArray]
    t: FloatArray  # uniform grid over the last period, endpoint excluded
    traces: dict[str, FloatArray]  # expression → uniform samples


def last_period(plot: Plot, period: float, expressions: list[str]) -> SteadyState:
    assert plot.scale is not None
    t = np.real(plot[plot.scale].data).astype(np.float64)
    t0 = t[-1] - period
    full = {e: vector_sum(plot, e) for e in expressions}
    sel = t >= t0
    t_raw = np.concatenate([[t0], t[sel]])
    raw = {e: np.concatenate([[np.interp(t0, t, y)], y[sel]]) for e, y in full.items()}
    grid = np.linspace(t0, t[-1], N_SAMPLES, endpoint=False)
    traces = {e: np.interp(grid, t, y) for e, y in full.items()}
    return SteadyState(t_raw=t_raw, raw=raw, t=grid, traces=traces)


def _avg(t: FloatArray, y: FloatArray) -> float:
    return float(np.trapezoid(y, t) / (t[-1] - t[0]))


def _harmonics(x: FloatArray, n: int = 50) -> FloatArray:
    spec = np.fft.rfft(x) / x.size
    amp = np.abs(spec[: n + 1])
    amp[1:] *= 2
    return np.asarray(amp)


def measure(check: SimCheck, ss: SteadyState) -> float:
    t, x = ss.t_raw, ss.raw[check.probe]
    if check.metric == "avg":
        return _avg(t, x)
    if check.metric == "rms":
        return float(np.sqrt(_avg(t, x**2)))
    if check.metric == "pp":
        return float(np.max(x) - np.min(x))
    if check.metric == "max":
        return float(np.max(x))
    if check.metric == "min":
        return float(np.min(x))
    if check.metric == "thd":
        h = _harmonics(ss.traces[check.probe])
        return float(np.sqrt(np.sum(h[2:] ** 2)) / h[1] * 100)
    assert check.voltage is not None
    v = ss.raw[check.voltage]
    ac = x - _avg(t, x)
    s = float(np.sqrt(_avg(t, v**2) * _avg(t, ac**2)))
    return _avg(t, v * ac) / s if s > 0 else 0.0


def netlist_with_analysis(circuit: Circuit, kind: str = "all") -> str:
    """Netlist with its analysis cards.

    Transient from the analytic initial state (only the last two periods are saved) and/or an
    ``.ac`` sweep. ``kind`` selects "tran", "ac" or "all" (both, for the downloaded netlist).
    """
    cards = []
    if kind in ("tran", "all") and circuit.tran_stop is not None:
        assert circuit.tran_step is not None and circuit.period is not None
        step = circuit.tran_step.to_pint().m_as("s")
        stop = circuit.tran_stop.to_pint().m_as("s")
        start = max(stop - 2 * circuit.period.to_pint().m_as("s"), 0.0)
        cards.append(f".tran {step:.6g} {stop:.6g} {start:.6g} {step:.6g} uic")
    if kind in ("ac", "all") and circuit.ac_start is not None:
        assert circuit.ac_stop is not None
        f1 = circuit.ac_start.to_pint().m_as("Hz")
        f2 = circuit.ac_stop.to_pint().m_as("Hz")
        cards.append(f".ac dec {circuit.ac_points_per_decade} {f1:.6g} {f2:.6g}")
    return "\n".join([f"* {circuit.title}", circuit.netlist, *cards])


@dataclass
class AcResponse:
    f: FloatArray
    mag: dict[str, FloatArray]  # expression → |value|


def ac_vector(plot: Plot, expression: str) -> FloatArray:
    """|expression| of complex AC vectors (weighted sums as in :func:`vector_sum`)."""
    expr = expression.replace(" ", "").lower()
    terms = _TERM.findall(expr)
    if not terms or "".join(s + c + t for s, c, t in terms) != expr.lstrip("+"):
        raise ValueError(f"Expressão de medida inválida: {expression!r}")
    total: NDArray[np.complex128] | None = None
    for sign, coef, name in terms:
        k = float(coef[:-1]) if coef else 1.0
        cdata = np.asarray(plot[name].data, dtype=np.complex128) * complex(k)
        if sign == "-":
            cdata = -cdata
        total = cdata if total is None else total + cdata
    assert total is not None
    return np.asarray(np.abs(total), dtype=np.float64)


def _corner(f: FloatArray, mag: FloatArray, side: str) -> float:
    """Frequency where |H| crosses max/√2 below (side "fl") or above ("fh") the maximum."""
    k = int(np.argmax(mag))
    level = mag[k] / np.sqrt(2)
    lf, lm = np.log10(f), mag
    if side == "fl":
        idx = np.nonzero(lm[: k + 1] < level)[0]
        if idx.size == 0:
            return float(f[0])
        i = int(idx[-1])
        j = i + 1
    else:
        idx = np.nonzero(lm[k:] < level)[0]
        if idx.size == 0:
            return float(f[-1])
        j = k + int(idx[0])
        i = j - 1
    # interpolate in log f, dB
    d0, d1 = 20 * np.log10(lm[i]), 20 * np.log10(lm[j])
    dl = 20 * np.log10(level)
    x = lf[i] + (dl - d0) * (lf[j] - lf[i]) / (d1 - d0)
    return float(10**x)


def measure_ac(check: SimCheck, ac: AcResponse) -> float:
    mag = ac.mag[check.probe]
    if check.metric == "ac_mag":
        assert check.freq is not None
        return float(np.interp(np.log10(check.freq), np.log10(ac.f), mag))
    return _corner(ac.f, mag, "fl" if check.metric == "ac_fl" else "fh")


def compare(
    circuit: Circuit,
    summary: Mapping[str, QuantityModel],
    backend: SimulatorBackend | None = None,
) -> tuple[list[SimComparison], SteadyState | None]:
    comparisons, ss, _ = compare_full(circuit, summary, backend)
    return comparisons, ss


def compare_full(
    circuit: Circuit,
    summary: Mapping[str, QuantityModel],
    backend: SimulatorBackend | None = None,
) -> tuple[list[SimComparison], SteadyState | None, AcResponse | None]:
    backend = backend or make_backend()
    tran_checks = [c for c in circuit.checks if not c.metric.startswith("ac_")]
    ac_checks = [c for c in circuit.checks if c.metric.startswith("ac_")]
    ss: SteadyState | None = None
    ac: AcResponse | None = None
    if circuit.tran_stop is not None:
        assert circuit.period is not None
        plot = backend.run(netlist_with_analysis(circuit, "tran")).plot("tran")
        expressions = sorted(
            {c.probe for c in tran_checks}
            | {c.voltage for c in tran_checks if c.voltage}
            | set(circuit.probes.values())
        )
        ss = last_period(plot, circuit.period.to_pint().m_as("s"), expressions)
    if circuit.ac_start is not None:
        plot = backend.run(netlist_with_analysis(circuit, "ac")).plot("ac")
        assert plot.scale is not None
        f = np.real(plot[plot.scale].data).astype(np.float64)
        exprs = {c.probe for c in ac_checks} | set(circuit.bode_probes.values())
        ac = AcResponse(f=f, mag={e: ac_vector(plot, e) for e in exprs})
    out: list[SimComparison] = []
    for check in circuit.checks:
        analytic = summary[check.summary_key]
        a = analytic.to_pint()
        if check.metric.startswith("ac_"):
            assert ac is not None, "verificação AC sem varredura .ac no circuito"
            sim = measure_ac(check, ac)
        else:
            assert ss is not None, "verificação no tempo sem transitória no circuito"
            sim = measure(check, ss)
        # the simulator works in V, A and Hz; analytic values may carry prefixes (mA, kHz)
        si = _SI_OF.get(str(a.dimensionality))
        if si is not None:
            sim = float(Q_(sim, si).m_as(a.units))
        a_val = float(a.magnitude)
        err = abs(sim - a_val) / abs(a_val) * 100 if a_val != 0 else abs(sim) * 100
        out.append(
            SimComparison(
                quantity=check.quantity,
                analytic=analytic,
                simulated=QuantityModel(value=sim, unit=analytic.unit),
                error_pct=err,
                tolerance_pct=check.tolerance_pct,
                ok=err <= check.tolerance_pct,
            )
        )
    return out, ss, ac
