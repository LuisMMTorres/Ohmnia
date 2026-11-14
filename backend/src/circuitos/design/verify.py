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

from circuitos.core.units import QuantityModel
from circuitos.simulation.backend import SimulatorBackend, make_backend
from circuitos.simulation.results import Plot

from .base import Circuit, SimCheck, SimComparison

FloatArray = NDArray[np.float64]
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
    if check.metric == "thd":
        h = _harmonics(ss.traces[check.probe])
        return float(np.sqrt(np.sum(h[2:] ** 2)) / h[1] * 100)
    assert check.voltage is not None
    v = ss.raw[check.voltage]
    ac = x - _avg(t, x)
    s = float(np.sqrt(_avg(t, v**2) * _avg(t, ac**2)))
    return _avg(t, v * ac) / s if s > 0 else 0.0


def netlist_with_analysis(circuit: Circuit) -> str:
    """Transient from the analytic initial state; only the last two periods are saved."""
    step = circuit.tran_step.to_pint().m_as("s")
    stop = circuit.tran_stop.to_pint().m_as("s")
    start = max(stop - 2 * circuit.period.to_pint().m_as("s"), 0.0)
    return "\n".join(
        [
            f"* {circuit.title}",
            circuit.netlist,
            f".tran {step:.6g} {stop:.6g} {start:.6g} {step:.6g} uic",
        ]
    )


def compare(
    circuit: Circuit,
    summary: Mapping[str, QuantityModel],
    backend: SimulatorBackend | None = None,
) -> tuple[list[SimComparison], SteadyState]:
    backend = backend or make_backend()
    plot = backend.run(netlist_with_analysis(circuit)).plot("tran")
    expressions = sorted(
        {c.probe for c in circuit.checks}
        | {c.voltage for c in circuit.checks if c.voltage}
        | set(circuit.probes.values())
    )
    ss = last_period(plot, circuit.period.to_pint().m_as("s"), expressions)
    out: list[SimComparison] = []
    for check in circuit.checks:
        analytic = summary[check.summary_key]
        a = analytic.to_pint()
        sim = measure(check, ss)
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
    return out, ss
