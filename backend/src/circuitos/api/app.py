"""FastAPI application: thin translation layer between HTTP/WebSocket and the domain core."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pint
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from numpy.typing import NDArray

from circuitos import __version__
from circuitos.api.catalog import open_repository
from circuitos.api.catalog import router as catalog_router
from circuitos.api.design import router as design_router
from circuitos.api.devices import router as devices_router
from circuitos.api.imports import router as imports_router
from circuitos.api.projects import router as projects_router
from circuitos.api.results import Form, as_real, split_vectors
from circuitos.api.results import router as results_router
from circuitos.api.schemas import (
    JobErrorOut,
    JobOut,
    Measurements,
    PlotData,
    PlotInfo,
    RunOut,
    SimulationIn,
    SnapIn,
    SnapOut,
    VectorInfo,
)
from circuitos.api.schematic import router as schematic_router
from circuitos.core import eseries
from circuitos.core.errors import CircuitosError
from circuitos.core.units import Q_, QuantityModel, VectorModel, format_eng, parse_unit
from circuitos.datasheets.store import DatasheetStore
from circuitos.simulation.backend import BatchNgspiceBackend, SharedNgspiceBackend
from circuitos.simulation.jobs import Job, JobQueue
from circuitos.simulation.post import measures
from circuitos.simulation.post.decimate import minmax_decimate
from circuitos.simulation.results import Plot, SimulationRequest

API = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.jobs = JobQueue(max_workers=int(os.environ.get("CIRCUITOS_SIM_WORKERS", "2")))
    app.state.components = open_repository()
    app.state.datasheets = DatasheetStore()
    yield
    app.state.jobs.shutdown()


app = FastAPI(title="Sistema de Projeto de Circuitos", version=__version__, lifespan=lifespan)
app.include_router(catalog_router)
app.include_router(devices_router)
app.include_router(design_router)
app.include_router(schematic_router)
app.include_router(imports_router)
app.include_router(projects_router)
app.include_router(results_router)


def _jobs() -> JobQueue:
    queue: JobQueue = app.state.jobs
    return queue


def _job_or_404(job_id: str) -> Job:
    try:
        return _jobs().get(job_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _plot_info(plot: Plot) -> PlotInfo:
    return PlotInfo(
        name=plot.name,
        kind=plot.kind,
        title=plot.title,
        scale=plot.scale,
        vectors=[
            VectorInfo(name=v.name, unit=v.unit, length=int(v.data.size), complex=v.is_complex)
            for v in plot.vectors.values()
        ],
        run=plot.run,
        run_label=plot.run_label,
        base=plot.base or plot.name,
    )


def _job_out(job: Job, *, with_log: bool = False) -> JobOut:
    out = JobOut(id=job.id, state=job.state, progress=job.progress, message=job.message)
    if job.result is not None:
        out.backend = job.result.backend
        out.elapsed_s = job.result.elapsed_s
        out.plots = [_plot_info(p) for p in job.result.plots]
        out.runs = [RunOut(index=r.index, label=r.label, values=r.values) for r in job.result.runs]
        out.summary = job.result.summary or None
        out.warnings = job.result.warnings
        if with_log:
            out.log = job.result.log
    if job.error is not None:
        out.error = JobErrorOut(
            kind=job.error.kind,
            message=job.error.message,
            suggestions=job.error.suggestions,
            log=job.error.log,
        )
    return out


def _plot_or_404(job: Job, plot_name: str) -> Plot:
    if job.result is None:
        raise HTTPException(409, "Simulação ainda sem resultado")
    for plot in job.result.plots:
        if plot.name == plot_name:
            return plot
    raise HTTPException(404, f"Análise {plot_name!r} não encontrada")


# ---------------------------------------------------------------------------------------------


@app.get(f"{API}/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "simulator": {
            "shared_library": SharedNgspiceBackend.available(),
            "executable": BatchNgspiceBackend.available(),
        },
    }


@app.get(f"{API}/eseries/{{name}}")
def get_series(name: eseries.SeriesName) -> dict[str, object]:
    return {
        "name": name,
        "values": list(eseries.series(name)),
        "tolerance": eseries.TOLERANCE[name],
    }


@app.post(f"{API}/eseries/snap")
def snap_value(body: SnapIn) -> SnapOut:
    try:
        result = eseries.snap(body.value.to_pint(), body.series, body.mode)
    except (ValueError, CircuitosError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return SnapOut(
        value=QuantityModel.from_pint(result, body.value.unit),
        formatted=format_eng(result),
        tolerance=eseries.TOLERANCE[body.series],
    )


@app.post(f"{API}/simulations", status_code=202)
def submit_simulation(body: SimulationIn) -> JobOut:
    job = _jobs().submit(SimulationRequest(body.netlist, body.timeout_s, body.backend))
    return _job_out(job)


@app.get(f"{API}/simulations/{{job_id}}")
def simulation_status(job_id: str, log: bool = False) -> JobOut:
    return _job_out(_job_or_404(job_id), with_log=log)


@app.delete(f"{API}/simulations/{{job_id}}")
def cancel_simulation(job_id: str) -> JobOut:
    job = _job_or_404(job_id)
    _jobs().cancel(job_id)
    return _job_out(job)


@app.get(f"{API}/simulations/{{job_id}}/plots/{{plot_name}}")
def plot_data(
    job_id: str,
    plot_name: str,
    vectors: str | None = Query(default=None, description="Lista separada por vírgulas"),
    max_points: int = Query(default=5000, ge=10, le=2_000_000),
    form: Form = "mag",
) -> PlotData:
    plot = _plot_or_404(_job_or_404(job_id), plot_name)
    names = split_vectors(vectors) if vectors else [n for n in plot.vectors if n != plot.scale]
    missing = [n for n in names if n not in plot.vectors]
    if missing:
        raise HTTPException(404, f"Vetores inexistentes: {missing}")
    traces = [as_real(plot.vectors[n].data, plot.vectors[n].unit, form) for n in names]
    x_vec = plot.vectors.get(plot.scale) if plot.scale else None
    decimated = False
    x: NDArray[Any] | None
    ys: list[NDArray[Any]]
    if x_vec is not None and plot.kind == "tran":
        x, ys = minmax_decimate(x_vec.data, [t[0] for t in traces], max_points)
        decimated = x.size < x_vec.data.size
    else:
        x = x_vec.data if x_vec is not None else None
        ys = [t[0] for t in traces]
    return PlotData(
        plot=plot.name,
        kind=plot.kind,
        x=VectorModel(values=x.tolist(), unit=x_vec.unit) if x is not None and x_vec else None,
        x_name=plot.scale,
        traces={
            n: VectorModel(values=np.nan_to_num(y, neginf=-1e300).tolist(), unit=t[1])
            for n, y, t in zip(names, ys, traces, strict=True)
        },
        decimated=decimated,
    )


@app.get(f"{API}/simulations/{{job_id}}/plots/{{plot_name}}/measures")
def plot_measures(
    job_id: str,
    plot_name: str,
    vector: str,
    start: float | None = None,
    stop: float | None = None,
) -> Measurements:
    plot = _plot_or_404(_job_or_404(job_id), plot_name)
    if plot.kind != "tran" or plot.scale is None:
        raise HTTPException(422, "Medições disponíveis apenas para análise transitória")
    vec = plot.vectors.get(vector.lower())
    if vec is None:
        raise HTTPException(404, f"Vetor {vector!r} não encontrado")
    t = plot.vectors[plot.scale].quantity()
    y = Q_(vec.data, parse_unit(vec.unit))
    try:
        t, y = measures.window(
            t,
            y,
            Q_(start, "s") if start is not None else None,
            Q_(stop, "s") if stop is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    m = np.asarray(y.magnitude)
    out = Measurements(
        vector=vec.name,
        mean=QuantityModel.from_pint(measures.mean(t, y)),
        rms=QuantityModel.from_pint(measures.rms(t, y)),
        peak=QuantityModel.from_pint(measures.peak(y)),
        peak_to_peak=QuantityModel.from_pint(measures.peak_to_peak(y)),
        minimum=QuantityModel.from_pint(Q_(float(m.min()), y.units)),
        maximum=QuantityModel.from_pint(Q_(float(m.max()), y.units)),
    )
    optional: dict[str, Callable[[], pint.Quantity]] = {
        "frequency": lambda: measures.frequency(t, y),
        "duty_cycle": lambda: measures.duty_cycle(t, y),
        "rise_time": lambda: measures.rise_time(t, y),
        "fall_time": lambda: measures.fall_time(t, y),
        "overshoot": lambda: measures.overshoot(t, y),
        "undershoot": lambda: measures.undershoot(t, y),
    }
    for key, fn in optional.items():
        try:
            setattr(out, key, QuantityModel.from_pint(fn()))
        except (ValueError, ZeroDivisionError, FloatingPointError):
            continue
    try:
        base, top = measures.levels(t, y)
        out.base, out.top = QuantityModel.from_pint(base), QuantityModel.from_pint(top)
    except ValueError:
        pass
    if out.frequency is not None:
        out.period = QuantityModel(value=1.0 / out.frequency.value, unit="s")
    return out


@app.websocket(f"{API}/simulations/{{job_id}}/ws")
async def simulation_progress(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        job = _jobs().get(job_id)
    except KeyError:
        await websocket.close(code=4404)
        return
    last: tuple[str, float, str] | None = None
    try:
        while True:
            current = (job.state, round(job.progress, 3), job.message)
            if current != last:
                await websocket.send_json(_job_out(job).model_dump())
                last = current
            if job.finished:
                break
            await asyncio.sleep(0.1)
        await websocket.close()
    except WebSocketDisconnect:
        return


_DIST = Path(
    os.environ.get("CIRCUITOS_FRONTEND_DIST", Path(__file__).parents[4] / "frontend" / "dist")
)
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
