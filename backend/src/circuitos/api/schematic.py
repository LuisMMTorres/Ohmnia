"""Schematic editor endpoints: symbol library, catalogue parts, netlist, import and simulation."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.components.repository import ComponentRepository
from circuitos.core.calc import CalcStep
from circuitos.core.errors import CircuitosError
from circuitos.cosim.firmware import engine_status
from circuitos.cosim.firmware_image import AVR_FLASH, FirmwareImage, load_image
from circuitos.reports import kicad
from circuitos.schematic import stress
from circuitos.schematic.importer import import_netlist
from circuitos.schematic.library import ANALYSES, SYMBOLS
from circuitos.schematic.model import Schematic
from circuitos.schematic.netlist import Netlist, SchematicError
from circuitos.schematic.parts import led_colour
from circuitos.schematic.runs import SchematicPlan
from circuitos.simulation.jobs import JobQueue
from circuitos.simulation.results import SimulationRequest

router = APIRouter(prefix="/api/v1/schematic")


@router.get("/firmware/capabilities")
def firmware_capabilities() -> list[dict[str, Any]]:
    ready, message = engine_status()
    return [
        {
            "board": kind,
            "available": ready and kind in AVR_FLASH,
            "formats": ["hex", "elf"] if kind in AVR_FLASH else [],
            "message": (
                "Firmware AVR: GPIO, ADC, temporizadores/PWM e Serial0." if ready else message
            )
            if kind in AVR_FLASH
            else "Motor de firmware ainda não integrado para esta placa.",
        }
        for kind in (*AVR_FLASH, "esp32_devkitc", "rpi_pico", "rpi_pico2")
    ]


@router.post("/firmware/validate")
def validate_firmware(body: FirmwareImage) -> dict[str, Any]:
    try:
        loaded = load_image(body)
        ready, message = engine_status()
        if not ready:
            raise ValueError(message)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "sha256": loaded.sha256,
        "size": loaded.size,
        "entry": loaded.entry,
        "warning": "HEX não identifica a placa de origem. Confira o modelo selecionado na IDE.",
    }


class SchematicIn(BaseModel):
    schematic: Schematic


class SimulateIn(SchematicIn):
    timeout_s: float = Field(default=120.0, gt=0, le=3600)
    backend: Literal["auto", "shared", "batch"] = "auto"


class ProbeOut(BaseModel):
    name: str
    expr: str
    unit: str
    probe_id: str | None


class SpreadOut(BaseModel):
    component: str
    param: str
    low: float
    nominal: float
    high: float
    source: str


class IndicatorOut(BaseModel):
    """LED or lamp: the current vector and the values that turn it into brightness."""

    kind: str
    vector: str
    i_ref: float | None = None
    i_max: float | None = None
    colour: str | None = None
    r: float | None = None
    p_nom: float | None = None
    v_nom: float | None = None


class LimitOut(BaseModel):
    """A rating of a part (catalogue or typed by the user) checked after the simulation."""

    ref: str
    quantity: Literal["V", "I", "P", "T"]
    name: str
    limit: float
    unit: str
    measure: Literal["peak", "mean", "rms", "peak_abs"]
    v_pos: str | None = None
    v_neg: str | None = None
    current: str | None = None
    current_sign: float = 1.0
    resistance: float | None = None
    rth: float | None = None
    t_amb: float | None = None
    source: str = ""
    advice: str = ""
    reviewed: bool = True


class DamageIn(BaseModel):
    job_id: str
    limits: list[LimitOut] = Field(max_length=5000)


class DamageOut(BaseModel):
    """A rating exceeded in the simulation: the part would burn or be damaged."""

    ref: str
    quantity: Literal["V", "I", "P", "T"]
    name: str
    value: float
    limit: float
    unit: str
    cause: str
    advice: str
    source: str
    reviewed: bool


class NetlistOut(BaseModel):
    netlist: str
    nets: dict[str, list[str]]
    probes: list[ProbeOut]
    warnings: list[str]
    spreads: list[SpreadOut]
    steps: list[CalcStep]
    indicators: dict[str, IndicatorOut] = {}
    limits: list[LimitOut] = []


class ImportIn(BaseModel):
    netlist: str = Field(min_length=1, max_length=2_000_000)


class ImportOut(BaseModel):
    schematic: Schematic
    warnings: list[str]


class PartOut(BaseModel):
    id: uuid.UUID
    part_number: str
    manufacturer: str
    category: str
    released: bool
    status: str
    summary: str = ""  # short description for the palette (LED colour, lamp rating)
    colour: str | None = None  # LED colour name (catalogue attribute)


def _num(rec: ComponentRecord, key: str) -> float | None:
    p = rec.parameters.get(key)
    if p is None:
        return None
    return next((v for v in (p.typ, p.max, p.min) if v is not None), None)


def _part_summary(rec: ComponentRecord) -> tuple[str, str | None]:
    """Palette text of a LED (colour, package, V_F) or a lamp (rating and category)."""
    if rec.category == "optoelectronic.led":
        colour = led_colour(rec)
        pkg = rec.package or ""
        size = "3 mm" if "3 mm" in pkg else "5 mm" if "5 mm" in pkg else ""
        vf = _num(rec, "VF")
        bits = [colour or "", size, f"VF {vf:g} V".replace(".", ",") if vf else ""]
        return " · ".join(b for b in bits if b), colour
    if rec.category.startswith("lamp"):
        vn, pn = _num(rec, "V_nom"), _num(rec, "P_nom")
        cat = rec.attributes.get("categoria")
        rating = f"{vn:g} V {pn:g} W".replace(".", ",") if vn and pn else ""
        return " · ".join(b for b in (rating, cat.value if cat else "") if b), None
    return "", None


class SimulateOut(BaseModel):
    job_id: str
    netlist: str
    runs: int
    warnings: list[str]


def _records(request: Request, sch: Schematic) -> dict[str, ComponentRecord]:
    repo: ComponentRepository = request.app.state.components
    out: dict[str, ComponentRecord] = {}
    for c in sch.components:
        if c.part_id is None or c.part_id in out:
            continue
        try:
            out[c.part_id] = repo.get(uuid.UUID(c.part_id))
        except (ValueError, CircuitosError) as exc:
            raise HTTPException(404, f"{c.ref}: peça {c.part_id} não encontrada") from exc
    return out


def _netlist_out(nl: Netlist) -> NetlistOut:
    return NetlistOut(
        netlist=nl.text,
        nets=nl.nets,
        probes=[ProbeOut(**dataclasses.asdict(p)) for p in nl.probes],
        warnings=nl.warnings,
        spreads=[
            SpreadOut(
                component=ref,
                param=sp.param,
                low=sp.lo,
                nominal=sp.nom,
                high=sp.hi,
                source=sp.source,
            )
            for ref, sp in sorted(nl.spreads.items())
        ],
        steps=nl.steps,
        indicators={
            ref: IndicatorOut(**dataclasses.asdict(ind)) for ref, ind in nl.indicators.items()
        },
        limits=[LimitOut(**dataclasses.asdict(lim)) for lim in nl.limits],
    )


@router.get("/library")
def library() -> dict[str, Any]:
    return {
        "symbols": [
            {
                "kind": s.kind,
                "label": s.label,
                "group": s.group,
                "prefix": s.ref_prefix or s.prefix or "G",
                "pins": [dataclasses.asdict(p) for p in s.pins],
                "params": [dataclasses.asdict(p) for p in s.params],
                "catalogue": list(s.catalogue),
                "tolerance": s.tolerance,
                "description": s.description,
            }
            for s in SYMBOLS.values()
        ],
        "analyses": {
            k: {"label": label, "params": [dataclasses.asdict(p) for p in params]}
            for k, (label, params) in ANALYSES.items()
        },
    }


@router.get("/parts")
def parts(request: Request, kind: str, text: str | None = None) -> list[PartOut]:
    sym = SYMBOLS.get(kind)
    if sym is None:
        raise HTTPException(404, f"Tipo {kind!r} desconhecido")
    repo: ComponentRepository = request.app.state.components
    out: list[PartOut] = []
    for cat in sym.catalogue:
        for r in repo.search(category=cat, text=text):
            summary, colour = _part_summary(r)
            out.append(
                PartOut(
                    id=r.id,
                    part_number=r.part_number,
                    manufacturer=r.manufacturer,
                    category=r.category,
                    released=r.selectable,
                    status=r.review.status,
                    summary=summary,
                    colour=colour,
                )
            )
    return out


@router.post("/netlist")
def netlist(request: Request, body: SchematicIn) -> NetlistOut:
    plan = SchematicPlan(body.schematic, _records(request, body.schematic))
    try:
        return _netlist_out(plan.nominal())
    except (SchematicError, ValueError, CircuitosError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/kicad.net")
def kicad_netlist(request: Request, body: SchematicIn) -> Response:
    """KiCad netlist of the drawn circuit (sources and probes stay out)."""
    plan = SchematicPlan(body.schematic, _records(request, body.schematic))
    try:
        text = plan.nominal().text
    except (SchematicError, ValueError, CircuitosError) as exc:
        raise HTTPException(422, str(exc)) from exc
    title = text.splitlines()[0] if text else "circuito"
    return Response(
        kicad.to_kicad(text, title),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="circuito.net"'},
    )


@router.post("/import")
def import_(body: ImportIn) -> ImportOut:
    try:
        result = import_netlist(body.netlist)
    except (SchematicError, ValueError) as exc:
        raise HTTPException(422, f"Netlist não importada: {exc}") from exc
    return ImportOut(schematic=result.schematic, warnings=result.warnings)


@router.post("/simulate", status_code=202)
def simulate(request: Request, body: SimulateIn) -> SimulateOut:
    plan = SchematicPlan(body.schematic, _records(request, body.schematic))
    try:
        nominal = plan.nominal()
        sweep = body.schematic.sweep
        measure = sweep.measure
        if sweep.kind == "worstcase" and (measure is None or not measure.vector.strip()):
            raise SchematicError(
                "O pior caso precisa de uma medida: informe o sinal (ex.: v(out)) e o tipo"
            )
        n_runs = len(nominal.spreads) + 3 if sweep.kind == "worstcase" else len(plan.runs(nominal))
    except (SchematicError, ValueError, CircuitosError) as exc:
        raise HTTPException(422, str(exc)) from exc
    jobs: JobQueue = request.app.state.jobs
    timeout = min(body.timeout_s * max(n_runs, 1), 3600.0)
    job = jobs.submit(SimulationRequest(nominal.text, timeout, body.backend, plan=plan))
    return SimulateOut(job_id=job.id, netlist=nominal.text, runs=n_runs, warnings=nominal.warnings)


@router.post("/damage")
def damage(request: Request, body: DamageIn) -> list[DamageOut]:
    """Ratings exceeded in a finished simulation (transient, else operating point)."""
    jobs: JobQueue = request.app.state.jobs
    try:
        job = jobs.get(body.job_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if job.result is None:
        raise HTTPException(409, "Simulação ainda sem resultado")
    plots = job.result.plots
    plot = next((p for p in plots if p.kind == "tran"), None) or next(
        (p for p in plots if p.kind == "op"), None
    )
    if plot is None:
        return []
    vectors = {k.lower(): v.data for k, v in plot.vectors.items()}
    time = plot.vectors[plot.scale].data if plot.kind == "tran" and plot.scale else None
    limits = [stress.Limit(**lim.model_dump()) for lim in body.limits]
    return [DamageOut(**dataclasses.asdict(d)) for d in stress.evaluate(limits, vectors, time)]


@router.get("/examples")
def examples() -> list[dict[str, Any]]:
    """Integrated examples (microcontrollers, PLC, sensors and actuators, Fase 11)."""
    from circuitos.cosim.examples import EXAMPLES

    return [
        {"name": name, "description": desc, "schematic": make().model_dump()}
        for name, (desc, make) in EXAMPLES.items()
    ]
