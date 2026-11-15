"""Schematic editor endpoints: symbol library, catalogue parts, netlist, import and simulation."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.components.repository import ComponentRepository
from circuitos.core.calc import CalcStep
from circuitos.core.errors import CircuitosError
from circuitos.schematic.importer import import_netlist
from circuitos.schematic.library import ANALYSES, SYMBOLS
from circuitos.schematic.model import Schematic
from circuitos.schematic.netlist import Netlist, SchematicError
from circuitos.schematic.runs import SchematicPlan
from circuitos.simulation.jobs import JobQueue
from circuitos.simulation.results import SimulationRequest

router = APIRouter(prefix="/api/v1/schematic")


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


class NetlistOut(BaseModel):
    netlist: str
    nets: dict[str, list[str]]
    probes: list[ProbeOut]
    warnings: list[str]
    spreads: list[SpreadOut]
    steps: list[CalcStep]


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
            out.append(
                PartOut(
                    id=r.id,
                    part_number=r.part_number,
                    manufacturer=r.manufacturer,
                    category=r.category,
                    released=r.selectable,
                    status=r.review.status,
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
