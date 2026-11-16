"""Design endpoints: modules, design run, simulation check, schematic, BOM and report."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, ValidationError

from circuitos.components.repository import ComponentRepository
from circuitos.core.errors import CircuitosError
from circuitos.design import registry
from circuitos.design.base import Circuit, DesignResult, SimComparison
from circuitos.design.engine import Device, TopologyModule, run
from circuitos.design.verify import compare_full, netlist_with_analysis
from circuitos.reports import bom, outputs, report
from circuitos.selection.derating import DeratingPolicy

router = APIRouter(prefix="/api/v1/design")


class ModuleInfo(BaseModel):
    id: str
    title: str
    family: str
    defaults: dict[str, Any]
    json_schema: dict[str, Any]
    spec_labels: dict[str, str]  # field → label in Portuguese
    enum_labels: dict[str, str]  # enum value → label
    summary_labels: dict[str, str]  # summary key → label


class DesignIn(BaseModel):
    spec: dict[str, Any] = Field(default_factory=dict)
    policy: Literal["didatico", "industrial"] = "didatico"
    locks: dict[str, uuid.UUID] = Field(default_factory=dict)
    costs: dict[str, float] = Field(default_factory=dict)  # part number → unit cost (BOM)


class CandidateOut(BaseModel):
    id: uuid.UUID
    part_number: str
    manufacturer: str
    released: bool


class DesignOut(BaseModel):
    result: DesignResult
    circuit: Circuit
    netlist: str
    options: dict[str, list[CandidateOut]]  # designator → every catalogue part of the category


class SimTrace(BaseModel):
    unit: str
    values: list[float]


class SimulateOut(BaseModel):
    comparisons: list[SimComparison]
    t_ms: list[float]  # one period, from 0
    traces: dict[str, SimTrace]  # same labels as DesignResult.traces
    ok: bool
    bode_f: list[float] = Field(default_factory=list)  # Hz
    bode: dict[str, SimTrace] = Field(default_factory=dict)  # |H|, same labels as result.bode


@router.get("/modules")
def modules() -> list[ModuleInfo]:
    out = []
    for m in registry.MODULES.values():
        schema = m.spec_schema
        out.append(
            ModuleInfo(
                id=m.id,
                title=m.title,
                family=m.family,
                defaults=schema().model_dump(),
                json_schema=schema.model_json_schema(),
                spec_labels=outputs.spec_labels(m),
                enum_labels=outputs.enum_labels(m),
                summary_labels={
                    k: v for k, v in outputs.labels(m).items() if k not in report.HIDDEN
                },
            )
        )
    return out


def _repo(request: Request) -> ComponentRepository:
    repo: ComponentRepository = request.app.state.components
    return repo


def _module(module_id: str) -> TopologyModule:
    try:
        return registry.get(module_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _design(
    request: Request, module_id: str, body: DesignIn
) -> tuple[TopologyModule, BaseModel, DesignResult, dict[str, Device], Circuit]:
    module = _module(module_id)
    try:
        spec = module.spec_schema(**body.spec)
    except ValidationError as exc:
        msgs = "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
        raise HTTPException(422, msgs) from exc
    repo = _repo(request)
    try:
        result, devices = run(
            module,
            spec,
            lambda c: repo.search(category=c),
            repo.get,
            DeratingPolicy.from_preset(body.policy),
            body.locks,
        )
        circuit = module.build_circuit(spec, devices, result.summary)
    except (ValueError, CircuitosError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return module, spec, result, devices, circuit


@router.post("/{module_id}")
def design(request: Request, module_id: str, body: DesignIn) -> DesignOut:
    _, _, result, _, circuit = _design(request, module_id, body)
    repo = _repo(request)
    options = {
        r.designator: [
            CandidateOut(
                id=c.id,
                part_number=c.part_number,
                manufacturer=c.manufacturer,
                released=c.selectable,
            )
            for c in repo.search(category=r.category)
        ]
        for r in result.roles
    }
    return DesignOut(
        result=result, circuit=circuit, netlist=netlist_with_analysis(circuit), options=options
    )


def _simulate(circuit: Circuit, result: DesignResult) -> SimulateOut:
    try:
        comparisons, ss, ac = compare_full(circuit, result.summary)
    except CircuitosError as exc:
        raise HTTPException(422, f"Simulação falhou: {exc}") from exc
    units = {k: v.unit for k, v in result.traces.items()}
    traces: dict[str, SimTrace] = {}
    t_ms: list[float] = []
    if ss is not None:
        n = 720
        idx = np.linspace(0, ss.t.size, n, endpoint=False).astype(int)
        t0 = ss.t[0]
        traces = {
            label: SimTrace(
                unit=units.get(label, "V" if expr.startswith("v") else "A"),
                values=[float(v) for v in ss.traces[expr][idx]],
            )
            for label, expr in circuit.probes.items()
        }
        t_ms = [float((ss.t[i] - t0) * 1e3) for i in idx]
    bode_f: list[float] = []
    bode: dict[str, SimTrace] = {}
    if ac is not None:
        bode_f = [float(v) for v in ac.f]
        bode = {
            label: SimTrace(unit="", values=[float(v) for v in ac.mag[expr]])
            for label, expr in circuit.bode_probes.items()
        }
    return SimulateOut(
        comparisons=comparisons,
        t_ms=t_ms,
        traces=traces,
        ok=all(c.ok for c in comparisons),
        bode_f=bode_f,
        bode=bode,
    )


@router.post("/{module_id}/simulate")
def simulate(request: Request, module_id: str, body: DesignIn) -> SimulateOut:
    _, _, result, _, circuit = _design(request, module_id, body)
    return _simulate(circuit, result)


@router.post("/{module_id}/schematic.svg")
def schematic(request: Request, module_id: str, body: DesignIn) -> Response:
    module, spec, result, _, circuit = _design(request, module_id, body)
    svg = outputs.schematic_svg(module, spec, result, circuit.title)
    return Response(svg, media_type="image/svg+xml")


def _datasheet_link(repo: ComponentRepository) -> Callable[[uuid.UUID], str | None]:
    def link(component_id: uuid.UUID) -> str | None:
        record = repo.get_or_none(component_id)
        if record is None:
            return None
        return next((str(d.url) for d in record.datasheets if d.url), None)

    return link


def _bom_lines(request: Request, module_id: str, body: DesignIn) -> tuple[str, list[bom.BomLine]]:
    module, spec, result, _, circuit = _design(request, module_id, body)
    rows = outputs.bom(module, spec, result)
    lines = bom.build(rows, result, _datasheet_link(_repo(request)), body.costs)
    return f"{module.title} — {circuit.title}", lines


@router.post("/{module_id}/bom.csv")
def bom_csv_out(request: Request, module_id: str, body: DesignIn) -> Response:
    _, lines = _bom_lines(request, module_id, body)
    return Response(
        bom.to_csv(lines),  # UTF-8 with BOM so spreadsheet programs read the accents
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{module_id}-bom.csv"'},
    )


@router.post("/{module_id}/bom.xlsx")
def bom_xlsx_out(request: Request, module_id: str, body: DesignIn) -> Response:
    title, lines = _bom_lines(request, module_id, body)
    return Response(
        bom.to_xlsx(lines, title),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{module_id}-bom.xlsx"'},
    )


@router.post("/{module_id}/bom.pdf")
def bom_pdf_out(request: Request, module_id: str, body: DesignIn) -> Response:
    title, lines = _bom_lines(request, module_id, body)
    subtitle = f"Política de margens: {body.policy}. Margem = (nominal / esforço − 1)·100."
    return Response(
        bom.to_pdf(lines, f"Lista de materiais — {title}", subtitle),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{module_id}-bom.pdf"'},
    )


class BomOut(BaseModel):
    title: str
    lines: list[dict[str, Any]]
    total_cost: float | None


@router.post("/{module_id}/bom")
def bom_json(request: Request, module_id: str, body: DesignIn) -> BomOut:
    title, lines = _bom_lines(request, module_id, body)
    return BomOut(
        title=title,
        lines=[
            {**vars(line), "designator": line.designator, "total_cost": line.total_cost}
            for line in lines
        ],
        total_cost=bom.total_cost(lines),
    )


@router.post("/{module_id}/report.html")
def report_html(
    request: Request, module_id: str, body: DesignIn, simulate: bool = True
) -> HTMLResponse:
    module, spec, result, _, circuit = _design(request, module_id, body)
    sim = _simulate(circuit, result).comparisons if simulate else None
    html = report.render(module, spec, result, body.policy, sim)
    return HTMLResponse(
        html, headers={"Content-Disposition": f'inline; filename="{module_id}-relatorio.html"'}
    )
