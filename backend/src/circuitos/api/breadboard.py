"""Breadboard view endpoints: board and packages, pinouts, automatic assembly, check, guide."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from circuitos.breadboard import board, packages
from circuitos.breadboard.autoplace import autoplace
from circuitos.breadboard.check import CheckReport, check
from circuitos.breadboard.guide import Step, guide
from circuitos.breadboard.layout import Breadboard
from circuitos.breadboard.reference import Reference, build
from circuitos.components.models import ComponentRecord
from circuitos.components.repository import ComponentRepository
from circuitos.core.errors import CircuitosError
from circuitos.schematic.model import Schematic
from circuitos.schematic.netlist import SchematicError

router = APIRouter(prefix="/api/v1/breadboard")


class SchematicIn(BaseModel):
    schematic: Schematic


class SourceOut(BaseModel):
    document: str
    page: int | None
    location: str | None
    url: str | None


class PartView(BaseModel):
    ref: str
    kind: str
    package: str | None
    origin: str
    checkable: bool
    pinmap: dict[str, str]
    labels: dict[str, str]
    title: str
    part_number: str | None
    source: SourceOut | None
    status: str | None
    notes: list[str]
    bands: list[str]


class ResolveOut(BaseModel):
    parts: list[PartView]
    nets: dict[str, str]  # leg key "Q1:3" -> net
    net_labels: dict[str, str]
    warnings: list[str]


class AutoOut(BaseModel):
    breadboard: Breadboard
    notes: list[str]
    report: CheckReport
    guide: list[Step]


def records_by_ref(repo: ComponentRepository, sch: Schematic) -> dict[str, ComponentRecord | None]:
    cache: dict[str, ComponentRecord] = {}
    out: dict[str, ComponentRecord | None] = {}
    for c in sch.components:
        if c.part_id is None:
            out[c.ref] = None
            continue
        if c.part_id not in cache:
            try:
                cache[c.part_id] = repo.get(uuid.UUID(c.part_id))
            except (ValueError, CircuitosError) as exc:
                raise HTTPException(404, f"{c.ref}: peça {c.part_id} não encontrada") from exc
        out[c.ref] = cache[c.part_id]
    return out


def reference_for(repo: ComponentRepository, sch: Schematic) -> Reference:
    recs = records_by_ref(repo, sch)
    try:
        ref = build(sch, recs)
    except (SchematicError, ValueError, CircuitosError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return ref


def _view(ref: Reference) -> list[PartView]:
    out = []
    for r in ref.parts.values():
        ds = r.datasheet
        src = None
        if r.source is not None:
            doc = r.source.datasheet_id
            if ds is not None:
                doc = " ".join(x for x in (ds.manufacturer, ds.document_number, ds.revision) if x)
            src = SourceOut(document=doc, page=r.source.page, location=r.source.location,
                            url=str(ds.url) if ds is not None and ds.url else None)  # fmt: skip
        out.append(PartView(
            ref=r.ref, kind=r.kind, package=r.package, origin=r.origin, checkable=r.checkable,
            pinmap=r.pinmap, labels=r.labels, title=r.title, part_number=r.part_number,
            source=src, status=r.status, notes=r.notes, bands=r.bands,
        ))  # fmt: skip
    return out


@router.get("/spec")
def spec() -> dict[str, Any]:
    return {"board": board.spec(), "packages": packages.spec()}


@router.post("/resolve")
def resolve(request: Request, body: SchematicIn) -> ResolveOut:
    ref = reference_for(request.app.state.components, body.schematic)
    return ResolveOut(parts=_view(ref), nets=ref.nets, net_labels=ref.net_labels,
                      warnings=ref.warnings)  # fmt: skip


@router.post("/auto")
def auto(request: Request, body: SchematicIn) -> AutoOut:
    ref = reference_for(request.app.state.components, body.schematic)
    bb, notes = autoplace(ref)
    return AutoOut(breadboard=bb, notes=notes, report=check(ref, bb), guide=guide(ref, bb))


@router.post("/check")
def check_(request: Request, body: SchematicIn) -> CheckReport:
    if body.schematic.breadboard is None:
        raise HTTPException(422, "O circuito ainda não foi montado na protoboard.")
    ref = reference_for(request.app.state.components, body.schematic)
    return check(ref, body.schematic.breadboard)


@router.post("/guide")
def guide_(request: Request, body: SchematicIn) -> list[Step]:
    if body.schematic.breadboard is None:
        raise HTTPException(422, "O circuito ainda não foi montado na protoboard.")
    ref = reference_for(request.app.state.components, body.schematic)
    return guide(ref, body.schematic.breadboard)
