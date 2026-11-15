"""Result analysis endpoints: CSV, figures, derived expressions, spectrum/THD and statistics."""

from __future__ import annotations

import csv
import io
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from circuitos.api.schemas import VectorInfo
from circuitos.core.units import Q_, VectorModel, parse_unit
from circuitos.reports import figures
from circuitos.schematic.model import AnalysisKind, MeasureKind, ScalarMeasure
from circuitos.schematic.netlist import SchematicError
from circuitos.schematic.runs import scalar_measure, statistics
from circuitos.simulation.jobs import Job, JobQueue
from circuitos.simulation.post import measures
from circuitos.simulation.post.expr import ExpressionError, evaluate
from circuitos.simulation.results import Plot, Vector

router = APIRouter(prefix="/api/v1/simulations")

Form = Literal["real", "imag", "mag", "mag_db", "phase_deg"]


def as_real(data: NDArray[Any], unit: str, form: Form) -> tuple[NDArray[Any], str]:
    if not np.iscomplexobj(data):
        return data, unit
    if form == "real":
        return data.real, unit
    if form == "imag":
        return data.imag, unit
    if form == "mag":
        return np.abs(data), unit
    if form == "mag_db":
        with np.errstate(divide="ignore"):
            return 20 * np.log10(np.abs(data)), "dB"
    return np.degrees(np.unwrap(np.angle(data))), "deg"


def _job(request: Request, job_id: str) -> Job:
    queue: JobQueue = request.app.state.jobs
    try:
        job = queue.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if job.result is None:
        raise HTTPException(409, "Simulação ainda sem resultado")
    return job


def _plot(job: Job, name: str) -> Plot:
    assert job.result is not None
    for p in job.result.plots:
        if p.name == name:
            return p
    raise HTTPException(404, f"Análise {name!r} não encontrada")


def split_vectors(names: str) -> list[str]:
    """Split a comma-separated vector list, keeping commas inside parentheses: v(a,b)."""
    out: list[str] = []
    depth = 0
    cur = ""
    for ch in names:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        depth += (ch == "(") - (ch == ")")
        cur += ch
    out.append(cur)
    return [n.strip().lower() for n in out if n.strip()]


def _vectors(plot: Plot, names: str | None) -> list[str]:
    if not names:
        return [n for n in plot.vectors if n != plot.scale]
    out = split_vectors(names)
    missing = [n for n in out if n not in plot.vectors]
    if missing:
        raise HTTPException(404, f"Vetores inexistentes: {missing}")
    return out


# ------------------------------------------------------------------------------------ CSV


@router.get("/{job_id}/plots/{plot_name}/csv")
def plot_csv(
    request: Request,
    job_id: str,
    plot_name: str,
    vectors: str | None = None,
    form: Form = "mag",
    style: Literal["br", "intl"] = "br",
) -> Response:
    """CSV of a plot: ``br`` uses ``;`` and decimal comma (Excel pt-BR), ``intl`` ``,``/``.``."""
    plot = _plot(_job(request, job_id), plot_name)
    names = _vectors(plot, vectors)
    cols: list[tuple[str, NDArray[Any]]] = []
    if plot.scale:
        x = plot.vectors[plot.scale]
        cols.append((f"{x.name} [{x.unit}]", np.asarray(x.data).real))
    for n in names:
        v = plot.vectors[n]
        if np.iscomplexobj(v.data) and form in ("mag", "mag_db", "phase_deg"):
            y, unit = as_real(v.data, v.unit, form)
            cols.append((f"{n} [{unit}]", y))
        elif np.iscomplexobj(v.data):
            cols.append((f"re {n} [{v.unit}]", v.data.real))
            cols.append((f"im {n} [{v.unit}]", v.data.imag))
        else:
            cols.append((f"{n} [{v.unit}]", np.asarray(v.data)))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";" if style == "br" else ",", lineterminator="\n")
    w.writerow([c[0] for c in cols])
    length = max(len(c[1]) for c in cols)

    def fmt(x: float) -> str:
        text = f"{x:.9g}"
        return text.replace(".", ",") if style == "br" else text

    for k in range(length):
        w.writerow([fmt(float(c[1][k])) if k < len(c[1]) else "" for c in cols])
    filename = f"{plot.name.replace(' ', '_')}.csv"
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------------- figure


class FigureIn(BaseModel):
    plot: str
    vectors: list[str] = Field(min_length=1, max_length=16)
    kind: figures.FigureKind = "time"
    format: figures.FigureFormat = "svg"
    title: str = ""
    x_vector: str | None = None  # XY plots
    all_runs: bool = False  # overlay the same vectors of every run of a sweep
    log_y: bool = False
    start: float | None = None
    stop: float | None = None
    f0: float | None = Field(default=None, gt=0)  # spectrum: fundamental (default: measured)
    periods: int = Field(default=1, ge=1, le=1000)
    n_harmonics: int = Field(default=50, ge=2, le=500)


_MEDIA = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}


def _runs_of(job: Job, plot: Plot, all_runs: bool) -> list[Plot]:
    assert job.result is not None
    if not all_runs:
        return [plot]
    return [p for p in job.result.plots if p.base == plot.base and p.kind == plot.kind]


@router.post("/{job_id}/figure")
def figure(request: Request, job_id: str, body: FigureIn) -> Response:
    job = _job(request, job_id)
    plot = _plot(job, body.plot)
    traces: list[figures.Trace] = []
    phase: list[figures.Trace] = []
    x_unit = ""
    x_label = ""
    for p in _runs_of(job, plot, body.all_runs):
        if body.kind == "xy":
            if not body.x_vector or body.x_vector.lower() not in p.vectors:
                raise HTTPException(422, "Informe o vetor do eixo x (gráfico XY)")
            xv = p.vectors[body.x_vector.lower()]
            x = np.asarray(as_real(xv.data, xv.unit, "real")[0], dtype=float)
            x_unit, x_label = xv.unit, xv.name
        elif p.scale:
            xv = p.vectors[p.scale]
            x = np.asarray(xv.data).real.astype(float)
            x_unit = xv.unit
            x_label = {"s": "tempo", "Hz": "frequência"}.get(xv.unit, xv.name)
        else:
            raise HTTPException(422, "Análise sem eixo (.op): não há figura")
        sel = np.ones(x.size, dtype=bool)
        if body.start is not None:
            sel &= x >= body.start
        if body.stop is not None:
            sel &= x <= body.stop
        suffix = f" ({p.run_label})" if body.all_runs and p.run_label else ""
        if body.kind == "spectrum":
            if p.kind != "tran":
                raise HTTPException(422, "Espectro só da análise transitória")
            for n in body.vectors:
                v = p.vectors.get(n.lower())
                if v is None:
                    raise HTTPException(404, f"Vetor {n!r} não existe em {p.name}")
                t = Q_(x, "s")
                yq = Q_(np.asarray(v.data, dtype=float), parse_unit(v.unit))
                try:
                    fund = body.f0 or float(measures.frequency(t, yq).m_as("Hz"))
                    tw, yw = measures.last_periods(t, yq, Q_(body.periods / fund, "s"), 1)
                    fr, am = measures.spectrum(tw, yw, 2**14, "rect")
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
                keep = fr.m_as("Hz") <= fund * (body.n_harmonics + 1)
                traces.append(
                    figures.Trace(n + suffix, fr.m_as("Hz")[keep], am.magnitude[keep], v.unit)
                )
            x_unit, x_label = "Hz", "frequência"
            continue
        for n in body.vectors:
            v = p.vectors.get(n.lower())
            if v is None:
                raise HTTPException(404, f"Vetor {n!r} não existe em {p.name}")
            form: Form = "mag_db" if body.kind == "bode" else "mag"
            y, unit = as_real(v.data, v.unit, form)
            traces.append(figures.Trace(n + suffix, x[sel], np.asarray(y)[sel], unit))
            if body.kind == "bode" and np.iscomplexobj(v.data):
                ph, _ = as_real(v.data, v.unit, "phase_deg")
                phase.append(figures.Trace(n + suffix, x[sel], np.asarray(ph)[sel], "deg"))
    spec = figures.FigureSpec(
        kind=body.kind,
        title=body.title,
        x_label=x_label,
        x_unit=x_unit,
        log_x=body.kind == "bode",
        log_y=body.log_y,
    )
    try:
        data = figures.render(traces, spec, body.format, phase)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        data,
        media_type=_MEDIA[body.format],
        headers={"Content-Disposition": f'attachment; filename="figura.{body.format}"'},
    )


# ----------------------------------------------------------------------------- expression


class ExpressionIn(BaseModel):
    expr: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=60)
    all_runs: bool = True


@router.post("/{job_id}/plots/{plot_name}/expressions")
def add_expression(request: Request, job_id: str, plot_name: str, body: ExpressionIn) -> VectorInfo:
    """Derived vector (``v(out)*i(r1)``, ``integ(...)``...) stored in the plot (and its runs)."""
    job = _job(request, job_id)
    plot = _plot(job, plot_name)
    name = (body.name or body.expr).strip().lower()
    info: VectorInfo | None = None
    for p in _runs_of(job, plot, body.all_runs):
        vecs = {k: (v.data, v.unit) for k, v in p.vectors.items()}
        try:
            ev = evaluate(body.expr, vecs, p.scale)
        except ExpressionError as exc:
            raise HTTPException(422, str(exc)) from exc
        data = np.asarray(ev.data)
        if data.ndim == 0:
            data = np.full(1, data)
        p.vectors[name] = Vector(name, ev.unit, data)
        if p is plot or info is None:
            info = VectorInfo(
                name=name, unit=ev.unit, length=int(data.size), complex=bool(np.iscomplexobj(data))
            )
    assert info is not None
    return info


# ------------------------------------------------------------------------------- spectrum


class Harmonic(BaseModel):
    k: int
    frequency: float
    amplitude: float
    percent: float  # of the fundamental


class SpectrumOut(BaseModel):
    vector: str
    unit: str
    f0: float
    window_start: float
    window_stop: float
    frequency: VectorModel
    amplitude: VectorModel
    harmonics: list[Harmonic]
    thd: float  # ratio
    rms: float
    dc: float


@router.get("/{job_id}/plots/{plot_name}/spectrum")
def spectrum(
    request: Request,
    job_id: str,
    plot_name: str,
    vector: str,
    f0: float | None = Query(default=None, gt=0),
    periods: int = Query(default=1, ge=1, le=1000),
    n_harmonics: int = Query(default=50, ge=2, le=500),
    window: Literal["rect", "hann"] = "rect",
    fmax: float | None = Query(default=None, gt=0),
) -> SpectrumOut:
    """FFT of the last ``periods`` periods of ``f0`` (coherent window), harmonic table and THD."""
    plot = _plot(_job(request, job_id), plot_name)
    if plot.kind != "tran" or plot.scale is None:
        raise HTTPException(422, "Espectro e THD são calculados sobre a análise transitória")
    vec = plot.vectors.get(vector.lower())
    if vec is None:
        raise HTTPException(404, f"Vetor {vector!r} não encontrado")
    t = plot.vectors[plot.scale].quantity()
    y = Q_(np.asarray(vec.data, dtype=float), parse_unit(vec.unit))
    try:
        fund = f0 if f0 is not None else float(measures.frequency(t, y).m_as("Hz"))
        tw, yw = measures.last_periods(t, y, Q_(periods / fund, "s"), 1)
        freqs, amps = measures.spectrum(tw, yw, 2**14, window)
        h = measures.harmonics(tw, yw, Q_(fund, "Hz"), n_harmonics).magnitude
        thd = float(measures.thd(tw, yw, Q_(fund, "Hz"), n_harmonics).magnitude)
        rms = float(measures.rms(tw, yw).magnitude)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    fm = freqs.m_as("Hz")
    limit = fmax if fmax is not None else fund * (n_harmonics + 1)
    sel = fm <= limit
    return SpectrumOut(
        vector=vec.name,
        unit=vec.unit,
        f0=fund,
        window_start=float(tw.m_as("s")[0]),
        window_stop=float(tw.m_as("s")[-1]),
        frequency=VectorModel(values=fm[sel].tolist(), unit="Hz"),
        amplitude=VectorModel(values=amps.magnitude[sel].tolist(), unit=vec.unit),
        harmonics=[
            Harmonic(
                k=k,
                frequency=k * fund,
                amplitude=float(h[k]),
                percent=float(100 * h[k] / h[1]) if h[1] else 0.0,
            )
            for k in range(1, n_harmonics + 1)
        ],
        thd=thd,
        rms=rms,
        dc=float(h[0]),
    )


# ----------------------------------------------------------------------------- statistics


class RunValue(BaseModel):
    run: int
    label: str
    value: float | None
    error: str | None = None


class StatisticsOut(BaseModel):
    measure: ScalarMeasure
    unit: str
    values: list[RunValue]
    stats: dict[str, float]
    nominal: float | None
    histogram: dict[str, list[float]]


@router.get("/{job_id}/statistics")
def run_statistics(
    request: Request,
    job_id: str,
    vector: str,
    analysis: AnalysisKind = "op",
    kind: MeasureKind = "final",
    at: str | None = None,
    start: str | None = None,
    stop: str | None = None,
    bins: int = Query(default=20, ge=2, le=200),
) -> StatisticsOut:
    """One number per run (Monte Carlo, sweep, worst case), its statistics and histogram."""
    job = _job(request, job_id)
    assert job.result is not None
    m = ScalarMeasure(analysis=analysis, vector=vector, kind=kind, at=at, start=start, stop=stop)
    labels = {r.index: r.label for r in job.result.runs}
    values: list[RunValue] = []
    unit = ""
    seen: set[int] = set()
    for p in job.result.plots:
        if p.kind != analysis or p.run in seen:
            continue
        seen.add(p.run)
        vec = p.vectors.get(vector.lower())
        if vec is not None:
            unit = {"mag_db_at": "dB", "phase_at": "deg", "frequency": "Hz"}.get(kind, vec.unit)
        try:
            values.append(
                RunValue(run=p.run, label=labels.get(p.run, ""), value=scalar_measure(p, m))
            )
        except (SchematicError, ValueError) as exc:
            values.append(
                RunValue(run=p.run, label=labels.get(p.run, ""), value=None, error=str(exc))
            )
    good = [v.value for v in values if v.value is not None]
    if not good:
        raise HTTPException(422, values[0].error if values else f"Sem análise {analysis}")
    counts, edges = np.histogram(good, bins=bins)
    nominal = next((v.value for v in values if v.run == 0), None)
    return StatisticsOut(
        measure=m,
        unit=unit,
        values=values,
        stats=statistics(good),
        nominal=nominal,
        histogram={"edges": edges.tolist(), "counts": counts.astype(float).tolist()},
    )
