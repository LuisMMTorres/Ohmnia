"""Runs of a schematic: single run, parametric step, temperature sweep, Monte Carlo, worst case.

Every run is a complete netlist (the schematic with some parameters replaced) simulated by the
same backend instance, so the job queue sees a single job. After each run the probe expressions
are evaluated into named vectors (``v(out)``, ``i(r1)``, ``p(q1)``) of every plot.

* **Monte Carlo:** run 0 is nominal; each later run draws every toleranced parameter
  independently, Gaussian with 3σ at the tolerance limit (truncated there) or uniform over the
  range. The ranges are the ``tol`` of generic parts and the datasheet minimum/maximum of
  catalogue parts (:class:`circuitos.schematic.parts.Spread`).
* **Worst case (sensitivity / extreme value):** a nominal run, one run per parameter at its
  upper limit to get the sign of its effect on the measure, then the two runs with every
  parameter at the limit that pushes the measure up (maximum) or down (minimum). With a
  monotonic measure this is the exact worst case; the summary lists the sensitivities.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from circuitos.components.models import ComponentRecord
from circuitos.schematic.library import symbol
from circuitos.schematic.model import ScalarMeasure, Schematic, Sweep
from circuitos.schematic.netlist import Netlist, SchematicError, build_netlist
from circuitos.schematic.values import format_value, parse_value
from circuitos.simulation.post.expr import ExpressionError, evaluate
from circuitos.simulation.results import Plot, RunInfo, SimulationResult, Vector

MAX_RUNS = 1000
Progress = Callable[[float, str], None]


def _noop(_f: float, _m: str) -> None:
    return None


@dataclass
class RunSpec:
    label: str
    overrides: dict[tuple[str, str], float] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    temperature: float | None = None
    values: dict[str, str] = field(default_factory=dict)


# ------------------------------------------------------------------------------ sweeps


def sweep_values(sw: Sweep) -> list[float]:
    if sw.spacing == "list":
        if not sw.values:
            raise SchematicError("Informe a lista de valores da varredura")
        out = [parse_value(v) for v in sw.values]
    else:
        if sw.start is None or sw.stop is None:
            raise SchematicError("Informe início e fim da varredura")
        a, b = parse_value(sw.start), parse_value(sw.stop)
        if sw.spacing == "lin":
            if not sw.step:
                raise SchematicError("Informe o passo da varredura linear")
            st = abs(parse_value(sw.step))
            if st == 0:
                raise SchematicError("Passo nulo")
            n = math.floor(abs(b - a) / st + 1e-9) + 1
            if n > MAX_RUNS:
                raise SchematicError(f"Varredura com {n} pontos (máximo {MAX_RUNS})")
            sign = 1 if b >= a else -1
            out = [a + sign * k * st for k in range(n)]
        else:
            if a <= 0 or b <= 0:
                raise SchematicError("Varredura logarítmica precisa de valores positivos")
            per = sw.points or 5
            base = 10.0 if sw.spacing == "dec" else 2.0
            n = math.floor(abs(math.log(b / a, base)) * per + 1e-9) + 1
            if n > MAX_RUNS:
                raise SchematicError(f"Varredura com {n} pontos (máximo {MAX_RUNS})")
            ratio = base ** (1 / per) if b >= a else base ** (-1 / per)
            out = [a * ratio**k for k in range(n)]
    if len(out) > MAX_RUNS:
        raise SchematicError(f"Varredura com {len(out)} pontos (máximo {MAX_RUNS})")
    return out


def _step_runs(sch: Schematic) -> list[RunSpec]:
    sw = sch.sweep
    values = sweep_values(sw)
    target = (sw.target or "").strip()
    if sw.kind == "temp" or target.lower() == "temp":
        return [
            RunSpec(f"T = {t:g} °C", temperature=t, values={"temp": f"{t:g} °C"}) for t in values
        ]
    if not target:
        raise SchematicError("Escolha o parâmetro da varredura (ex.: R1.value ou param:R0)")
    if target.lower().startswith("param:"):
        name = target.split(":", 1)[1].strip()
        if name not in sch.params:
            raise SchematicError(f"Parâmetro .param {name!r} não existe")
        return [
            RunSpec(
                f"{name} = {format_value(v)}",
                params={name: format_value(v, 9)},
                values={name: format_value(v)},
            )
            for v in values
        ]
    ref, _, pname = target.partition(".")
    try:
        comp = sch.component(ref)
    except KeyError as exc:
        raise SchematicError(str(exc)) from exc
    try:
        symbol(comp.kind).param(pname)
    except KeyError as exc:
        raise SchematicError(f"{comp.ref} não tem o parâmetro {pname!r}") from exc
    return [
        RunSpec(
            f"{comp.ref}.{pname} = {format_value(v)}",
            overrides={(comp.ref, pname): v},
            values={f"{comp.ref}.{pname}": format_value(v)},
        )
        for v in values
    ]


def monte_carlo_runs(sw: Sweep, spreads: Mapping[str, Any]) -> list[RunSpec]:
    if not spreads:
        raise SchematicError(
            "Nenhum componente tem tolerância: preencha 'tol' ou use peças do catálogo com "
            "faixa no datasheet"
        )
    rng = np.random.default_rng(sw.seed)
    runs = [RunSpec("nominal")]
    for k in range(1, sw.runs + 1):
        spec = RunSpec(f"MC {k}")
        for ref, sp in sorted(spreads.items()):
            if sw.distribution == "gauss":
                u = float(np.clip(rng.normal(0.0, 1.0 / 3.0), -1.0, 1.0))
            else:
                u = float(rng.uniform(-1.0, 1.0))
            value = sp.at(u)
            spec.overrides[(ref, sp.param)] = value
            spec.values[f"{ref}.{sp.param}"] = format_value(value)
        runs.append(spec)
    return runs


# ---------------------------------------------------------------------------- measures


def _plot_for(plots: list[Plot], m: ScalarMeasure, run: int | None = None) -> Plot:
    for p in plots:
        if p.kind == m.analysis and (run is None or p.run == run):
            return p
    raise SchematicError(f"Sem análise {m.analysis} no resultado para a medida")


def scalar_measure(plot: Plot, m: ScalarMeasure) -> float:
    """Number taken from one plot (Monte Carlo statistics, worst-case target)."""
    key = m.vector.strip().lower()
    vec = plot.vectors.get(key)
    if vec is None:
        raise SchematicError(f"Vetor {m.vector!r} não existe em {plot.base or plot.name}")
    y = np.asarray(vec.data)
    if m.kind in ("final", "max", "min", "pp", "mean", "rms") and plot.kind != "tran":
        y = np.abs(y) if np.iscomplexobj(y) else y
    if m.kind == "final":
        return float(np.real(y[-1]))
    x_vec = plot.vectors.get(plot.scale) if plot.scale else None
    if x_vec is None:
        if m.kind in ("max", "min", "mean", "rms"):
            return float(np.real(y[-1]))
        raise SchematicError(f"A medida {m.kind} precisa de uma análise com eixo")
    x = np.asarray(x_vec.data).real.astype(float)
    if m.kind in ("at", "mag_db_at", "phase_at"):
        if m.at is None:
            raise SchematicError("Informe o ponto da medida")
        xa = parse_value(m.at)
        if m.kind == "at":
            return float(np.interp(xa, x, np.abs(y) if np.iscomplexobj(y) else y))
        if not np.iscomplexobj(y):
            raise SchematicError("Medidas de módulo e fase são da análise AC")
        lx = np.log10(np.maximum(x, 1e-300))
        la = math.log10(xa) if xa > 0 else lx[0]
        z = np.interp(la, lx, y.real) + 1j * np.interp(la, lx, y.imag)
        if m.kind == "mag_db_at":
            return float(20 * np.log10(abs(z)))
        return float(np.degrees(np.angle(z)))
    a = parse_value(m.start) if m.start else x[0]
    b = parse_value(m.stop) if m.stop else x[-1]
    sel = (x >= a) & (x <= b)
    if sel.sum() < 2:
        raise SchematicError("Janela da medida sem pontos")
    xs, ys = x[sel], np.real(y[sel]).astype(float)
    if m.kind == "max":
        return float(ys.max())
    if m.kind == "min":
        return float(ys.min())
    if m.kind == "pp":
        return float(ys.max() - ys.min())
    if m.kind == "mean":
        return float(np.trapezoid(ys, xs) / (xs[-1] - xs[0]))
    if m.kind == "rms":
        return float(np.sqrt(np.trapezoid(ys**2, xs) / (xs[-1] - xs[0])))
    # frequency from rising crossings of the mean
    lv = float(np.trapezoid(ys, xs) / (xs[-1] - xs[0]))
    s = ys - lv
    idx = np.where((s[:-1] < 0) & (s[1:] >= 0))[0]
    if idx.size < 2:
        raise SchematicError("Menos de dois cruzamentos: frequência indeterminada")
    tc = xs[idx] - s[idx] * (xs[idx + 1] - xs[idx]) / (s[idx + 1] - s[idx])
    return float(1.0 / np.mean(np.diff(tc)))


def statistics(values: list[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=float)
    out = {
        "n": float(a.size),
        "mean": float(a.mean()),
        "std": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "min": float(a.min()),
        "max": float(a.max()),
    }
    out["p1"] = float(np.percentile(a, 0.135))  # −3σ of a normal distribution
    out["p99"] = float(np.percentile(a, 99.865))  # +3σ
    return out


# -------------------------------------------------------------------------------- plan


def add_probe_vectors(plot: Plot, probes: list[Any]) -> None:
    vectors = {k: (v.data, v.unit) for k, v in plot.vectors.items()}
    for pv in probes:
        try:
            ev = evaluate(pv.expr, vectors, plot.scale)
        except ExpressionError:
            continue  # e.g. noise plots have no node voltages
        name = pv.name.lower()
        plot.vectors[name] = Vector(name, pv.unit, ev.data)
        vectors[name] = (ev.data, pv.unit)


@dataclass
class SchematicPlan:
    """Pickled into the simulation worker; ``records`` holds the catalogue parts it uses."""

    schematic: Schematic
    records: dict[str, ComponentRecord] = field(default_factory=dict)

    def nominal(self) -> Netlist:
        return build_netlist(self.schematic, self.records)

    def runs(self, nominal: Netlist | None = None) -> list[RunSpec]:
        sw = self.schematic.sweep
        if sw.kind == "none":
            return [RunSpec("")]
        if sw.kind in ("step", "temp"):
            return _step_runs(self.schematic)
        if sw.kind == "montecarlo":
            return monte_carlo_runs(sw, (nominal or self.nominal()).spreads)
        raise SchematicError("O pior caso é executado por execute()")

    def _netlist(self, spec: RunSpec) -> Netlist:
        return build_netlist(
            self.schematic,
            self.records,
            overrides=spec.overrides,
            params=spec.params,
            temperature=spec.temperature,
            title_suffix=f" [{spec.label}]" if spec.label else "",
        )

    def _run_one(
        self, backend: Any, spec: RunSpec, index: int, total: int, progress: Progress
    ) -> tuple[list[Plot], str, list[str]]:
        nl = self._netlist(spec)

        def sub(fraction: float, message: str) -> None:
            label = f" ({spec.label})" if spec.label else ""
            progress((index + fraction) / total, f"{message}{label}")

        res = backend.run(nl.text, sub)
        for p in res.plots:
            add_probe_vectors(p, nl.probes)
            p.base = p.name
            p.run = index
            p.run_label = spec.label
            if total > 1:
                p.name = f"{p.name} r{index}"
        return res.plots, res.log, nl.warnings + res.warnings

    def execute(self, backend: Any, progress: Progress = _noop) -> SimulationResult:
        start = time.perf_counter()
        nominal = self.nominal()
        if nominal.controllers:  # Arduino, ESP32 or PLC: co-simulation (Fase 11)
            from circuitos.cosim.run import run_cosim

            return run_cosim(
                self.schematic, self.records, nominal, backend, progress, add_probe_vectors
            )
        if self.schematic.sweep.kind == "worstcase":
            return self._worst_case(backend, nominal, progress, start)
        specs = self.runs(nominal)
        plots: list[Plot] = []
        logs: list[str] = []
        warnings: list[str] = list(nominal.warnings)
        for k, spec in enumerate(specs):
            p, log, w = self._run_one(backend, spec, k, len(specs), progress)
            plots += p
            logs.append(log if len(specs) == 1 else f"=== {spec.label} ===\n{log[-4000:]}")
            warnings += w
        summary: dict[str, Any] = {"kind": self.schematic.sweep.kind}
        if self.schematic.sweep.kind == "montecarlo":
            summary["spreads"] = _spread_table(nominal)
        progress(1.0, "concluído")
        return SimulationResult(
            backend=getattr(backend, "name", "ngspice"),
            plots=plots,
            log="\n".join(logs),
            warnings=list(dict.fromkeys(warnings)),
            elapsed_s=time.perf_counter() - start,
            runs=[RunInfo(k, s.label, s.values) for k, s in enumerate(specs)],
            summary=summary,
        )

    def _worst_case(
        self, backend: Any, nominal: Netlist, progress: Progress, start: float
    ) -> SimulationResult:
        m = self.schematic.sweep.measure
        if m is None:
            raise SchematicError("O pior caso precisa de uma medida (vetor e tipo)")
        spreads = nominal.spreads
        if not spreads:
            raise SchematicError(
                "Nenhum componente tem tolerância: preencha 'tol' ou use peças do catálogo"
            )
        names = sorted(spreads)
        total = len(names) + 3
        plots: list[Plot] = []
        logs: list[str] = []
        warnings = list(nominal.warnings)
        specs: list[RunSpec] = []

        def do(spec: RunSpec) -> float:
            k = len(specs)
            specs.append(spec)
            p, log, w = self._run_one(backend, spec, k, total, progress)
            plots.extend(p)
            logs.append(f"=== {spec.label} ===\n{log[-4000:]}")
            warnings.extend(w)
            return scalar_measure(_plot_for(p, m), m)

        m0 = do(RunSpec("nominal"))
        rows: list[dict[str, Any]] = []
        for ref in names:
            sp = spreads[ref]
            key = (ref, sp.param)
            mi = do(
                RunSpec(
                    f"{ref}.{sp.param} máx.",
                    overrides={key: sp.hi},
                    values={f"{ref}.{sp.param}": format_value(sp.hi)},
                )
            )
            rows.append(
                {
                    "parameter": f"{ref}.{sp.param}",
                    "nominal": sp.nom,
                    "low": sp.lo,
                    "high": sp.hi,
                    "source": sp.source,
                    "measure_at_high": mi,
                    "delta": mi - m0,
                }
            )
        hi_spec = RunSpec("pior caso máx.")
        lo_spec = RunSpec("pior caso mín.")
        for r in rows:
            ref, param = r["parameter"].split(".", 1)
            up = r["delta"] >= 0
            hi_spec.overrides[(ref, param)] = r["high"] if up else r["low"]
            lo_spec.overrides[(ref, param)] = r["low"] if up else r["high"]
            hi_spec.values[r["parameter"]] = format_value(hi_spec.overrides[(ref, param)])
            lo_spec.values[r["parameter"]] = format_value(lo_spec.overrides[(ref, param)])
            r["direction"] = "+" if up else "−"
        m_hi = do(hi_spec)
        m_lo = do(lo_spec)
        progress(1.0, "concluído")
        summary = {
            "kind": "worstcase",
            "measure": m.model_dump(),
            "nominal": m0,
            "max": m_hi,
            "min": m_lo,
            "sensitivities": rows,
        }
        if not m_lo <= m0 <= m_hi:
            warnings.append(
                "A medida nominal ficou fora do intervalo do pior caso: o efeito de algum "
                "parâmetro não é monotônico; confira com Monte Carlo."
            )
        return SimulationResult(
            backend=getattr(backend, "name", "ngspice"),
            plots=plots,
            log="\n".join(logs),
            warnings=list(dict.fromkeys(warnings)),
            elapsed_s=time.perf_counter() - start,
            runs=[RunInfo(k, s.label, s.values) for k, s in enumerate(specs)],
            summary=summary,
        )


def _spread_table(nl: Netlist) -> list[dict[str, Any]]:
    return [
        {
            "parameter": f"{ref}.{sp.param}",
            "nominal": sp.nom,
            "low": sp.lo,
            "high": sp.hi,
            "source": sp.source,
        }
        for ref, sp in sorted(nl.spreads.items())
    ]
