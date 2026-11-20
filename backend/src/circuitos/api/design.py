"""Design endpoints: modules, design run, simulation check, schematic, BOM and report."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, ValidationError

from circuitos.api.breadboard import AutoOut, reference_for
from circuitos.breadboard.autoplace import autoplace
from circuitos.breadboard.check import check
from circuitos.breadboard.guide import guide
from circuitos.breadboard.physical import physical_circuit
from circuitos.components.models import ComponentRecord
from circuitos.components.repository import ComponentRepository
from circuitos.core.errors import CircuitosError
from circuitos.design import registry
from circuitos.design.base import Circuit, DesignResult, SimComparison
from circuitos.design.engine import Device, TopologyModule, run
from circuitos.design.measure import Measurements, measure_all, measured_traces
from circuitos.design.netlist_edit import (
    Element,
    UserProbe,
    add_probes,
    apply_overrides,
    elements,
    nodes,
)
from circuitos.design.verify import compare_full, netlist_with_analysis
from circuitos.reports import bom, kicad, outputs, pdf, report
from circuitos.reports.sections import SimWaves
from circuitos.schematic.model import Schematic
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
    project: str | None = None  # project name for the report title
    # element → new value, typed on the schematic (the simulation runs the edited circuit)
    overrides: dict[str, str] = Field(default_factory=dict)
    # waveforms added by clicking the schematic (simulation only)
    probes: list[UserProbe] = Field(default_factory=list)


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
    # peak, mean, RMS of every probe and S, P, Q, FP of every power port, all from ngspice
    measurements: Measurements | None = None
    # values were changed on the schematic: the analytic results describe the original design
    edited: bool = False


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
        if body.overrides:
            circuit = circuit.model_copy(
                update={"netlist": apply_overrides(circuit.netlist, body.overrides)}
            )
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


def _simulate(
    circuit: Circuit,
    result: DesignResult,
    probes: list[UserProbe] | None = None,
    edited: bool = False,
) -> SimulateOut:
    try:
        circuit, power_probes = add_probes(circuit, probes or [])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        comparisons, ss, ac = compare_full(circuit, result.summary)
    except CircuitosError as exc:
        raise HTTPException(422, f"Simulação falhou: {exc}") from exc
    units = {k: v.unit for k, v in result.traces.items()}
    traces: dict[str, SimTrace] = {}
    t_ms: list[float] = []
    measurements: Measurements | None = None
    if ss is not None:
        n = 720
        idx = np.linspace(0, ss.t.size, n, endpoint=False).astype(int)
        t0 = ss.t[0]
        traces = {
            label: SimTrace(
                unit=units.get(label, unit),
                values=[float(v) for v in values[idx]],
            )
            for label, (unit, values) in measured_traces(circuit, ss, power_probes).items()
        }
        t_ms = [float((ss.t[i] - t0) * 1e3) for i in idx]
        measurements = measure_all(circuit, ss)
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
        measurements=measurements,
        edited=edited,
    )


@router.post("/{module_id}/simulate")
def simulate(request: Request, module_id: str, body: DesignIn) -> SimulateOut:
    _, _, result, _, circuit = _design(request, module_id, body)
    return _simulate(circuit, result, body.probes, bool(body.overrides))


class ElementOut(Element):
    role: str | None = None  # designator of the catalogue role (its part can be swapped)
    original: str | None = None  # value of the design, when edited


class ElementsOut(BaseModel):
    elements: list[ElementOut]
    nodes: list[str]


@router.post("/{module_id}/elements")
def circuit_elements(request: Request, module_id: str, body: DesignIn) -> ElementsOut:
    """Elements and nodes of the simulated circuit, for editing values and adding probes."""
    module, spec, result, devices, circuit = _design(request, module_id, body)
    designators = {r.designator for r in result.roles}
    base = {
        e.name.lower(): e.value
        for e in elements(module.build_circuit(spec, devices, result.summary).netlist)
    }
    out = []
    for el in elements(circuit.netlist):
        ref = el.name[1:] if el.letter == "X" and len(el.name) > 1 else el.name
        role = kicad._match(ref, designators)
        designator = next(
            (d for d in designators if role is not None and kicad._match(ref, {d})), None
        )
        orig = base.get(el.name.lower())
        out.append(
            ElementOut(
                **el.model_dump(),
                role=designator,
                original=orig if orig is not None and orig != el.value else None,
            )
        )
    return ElementsOut(elements=out, nodes=nodes(circuit.netlist))


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
            {
                **vars(line),
                "designator": line.designator,
                "total_cost": line.total_cost,
                "cost_key": line.cost_key,
            }
            for line in lines
        ],
        total_cost=bom.total_cost(lines),
    )


def _waves(out: SimulateOut) -> SimWaves:
    return SimWaves(
        t_s=[v / 1e3 for v in out.t_ms],
        traces={k: (v.unit, v.values) for k, v in out.traces.items()},
        bode_f=out.bode_f,
        bode={k: v.values for k, v in out.bode.items()},
    )


def _report_ctx_args(
    request: Request, module_id: str, body: DesignIn, simulate: bool
) -> tuple[
    Any, BaseModel, DesignResult, list[SimComparison] | None, SimWaves | None, list[bom.BomLine]
]:
    module, spec, result, _, circuit = _design(request, module_id, body)
    sim_out = _simulate(circuit, result) if simulate else None
    lines = bom.build(
        outputs.bom(module, spec, result), result, _datasheet_link(_repo(request)), body.costs
    )
    return (
        module,
        spec,
        result,
        sim_out.comparisons if sim_out else None,
        _waves(sim_out) if sim_out else None,
        lines,
    )


@router.post("/{module_id}/report.html")
def report_html(
    request: Request, module_id: str, body: DesignIn, simulate: bool = True
) -> HTMLResponse:
    module, spec, result, sim, waves, lines = _report_ctx_args(request, module_id, body, simulate)
    html = report.render(module, spec, result, body.policy, sim, waves, lines, body.project)
    return HTMLResponse(
        html, headers={"Content-Disposition": f'inline; filename="{module_id}-relatorio.html"'}
    )


@router.post("/{module_id}/report.pdf")
def report_pdf(request: Request, module_id: str, body: DesignIn, simulate: bool = True) -> Response:
    module, spec, result, sim, waves, lines = _report_ctx_args(request, module_id, body, simulate)
    ctx = report.context(
        module, spec, result, body.policy, sim, waves, lines, body.project, figure_format="png"
    )
    return Response(
        pdf.render_pdf(ctx),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{module_id}-relatorio.pdf"'},
    )


@router.post("/{module_id}/kicad.net")
def kicad_netlist(request: Request, module_id: str, body: DesignIn) -> Response:
    """KiCad netlist with the parts of the bill of materials (model elements left out)."""
    module, spec, result, _, circuit = _design(request, module_id, body)
    keep = {r.designator for r in outputs.bom(module, spec, result)}
    repo = _repo(request)
    packages: dict[str, str] = {}
    for c in result.selection:
        record = repo.get_or_none(c.component_id)
        if record is not None and record.package:
            packages[c.designator] = record.package
    text = kicad.to_kicad(
        netlist_with_analysis(circuit), f"{module.title} — {circuit.title}", keep, packages
    )
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{module_id}.net"'},
    )


class DesignBreadboardOut(BaseModel):
    available: bool
    reason: str | None = None
    schematic: Schematic | None = None
    assembly: AutoOut | None = None
    notes: list[str] = Field(default_factory=list)


@router.post("/{module_id}/breadboard")
def design_breadboard(request: Request, module_id: str, body: DesignIn) -> DesignBreadboardOut:
    """The designed circuit as you assemble it: real parts, automatic layout, check and guide."""
    module, spec, result, _, circuit = _design(request, module_id, body)
    repo = _repo(request)
    chosen = {c.designator: repo.get_or_none(c.component_id) for c in result.selection}

    def record_for(ref: str) -> ComponentRecord | None:
        for designator, record in chosen.items():
            if kicad._match(ref, {designator}):
                return record
        return None

    vcc = getattr(spec, "VCC", None)
    supply = vcc.to_pint().m_as("V") if vcc is not None else None
    title = f"{module.title} — {circuit.title}"
    phys = physical_circuit(netlist_with_analysis(circuit), title, record_for, supply)
    if phys.schematic is None:
        return DesignBreadboardOut(
            available=False,
            reason=(
                "A simulação deste módulo representa parte do circuito por modelos sem peça física "
                f"equivalente ({', '.join(phys.unsupported)}). Monte-o no simulador livre, com as "
                "peças reais, e use a conferência da protoboard."
            ),
            notes=phys.notes,
        )
    ref = reference_for(repo, phys.schematic)
    bb, layout_notes = autoplace(ref)
    sch = phys.schematic.model_copy(update={"breadboard": bb})
    return DesignBreadboardOut(
        available=True,
        schematic=sch,
        assembly=AutoOut(
            breadboard=bb, notes=layout_notes, report=check(ref, bb), guide=guide(ref, bb)
        ),
        notes=phys.notes,
    )
