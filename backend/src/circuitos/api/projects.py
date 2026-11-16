"""Project endpoints: list, create, open, save (new revision), restore, duplicate, files."""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from circuitos.api.catalog import _repo
from circuitos.core.errors import DataIntegrityError
from circuitos.design import registry
from circuitos.projects.store import (
    Policy,
    ProjectDocument,
    ProjectRepository,
    ProjectSummary,
    Revision,
)

router = APIRouter(prefix="/api/v1/projects")


def _projects(request: Request) -> ProjectRepository:
    repo: ProjectRepository | None = getattr(request.app.state, "projects", None)
    if repo is None:
        repo = ProjectRepository(_repo(request).engine)
        request.app.state.projects = repo
    return repo


class ProjectContent(BaseModel):
    spec: dict[str, Any] = Field(default_factory=dict)
    policy: Policy = "didatico"
    locks: dict[str, uuid.UUID] = Field(default_factory=dict)
    costs: dict[str, float] = Field(default_factory=dict)
    note: str | None = None


def _validated(module_id: str, content: ProjectContent) -> Revision:
    """The spec must be valid for the module: a project is reopened exactly as saved."""
    try:
        module = registry.get(module_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        spec = module.spec_schema(**content.spec)
    except ValidationError as exc:
        msgs = "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
        raise HTTPException(422, f"Especificação inválida: {msgs}") from exc
    return Revision(
        number=1,
        spec=spec.model_dump(mode="json"),
        policy=content.policy,
        locks=content.locks,
        costs=content.costs,
        note=content.note,
    )


def _get(request: Request, project_id: uuid.UUID) -> ProjectDocument:
    try:
        return _projects(request).get(project_id)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


class CreateIn(ProjectContent):
    name: str = Field(min_length=1, max_length=200)
    module_id: str
    description: str = ""


@router.get("")
def list_projects(request: Request) -> list[ProjectSummary]:
    return _projects(request).list()


@router.post("")
def create_project(request: Request, body: CreateIn) -> ProjectDocument:
    revision = _validated(body.module_id, body)
    return _projects(request).create(body.name, body.module_id, revision, body.description)


@router.get("/{project_id}")
def get_project(request: Request, project_id: uuid.UUID) -> ProjectDocument:
    return _get(request, project_id)


class SaveIn(ProjectContent):
    name: str | None = None
    description: str | None = None


@router.put("/{project_id}")
def save_project(request: Request, project_id: uuid.UUID, body: SaveIn) -> ProjectDocument:
    doc = _get(request, project_id)
    revision = _validated(doc.module_id, body)
    return _projects(request).save(project_id, revision, body.name, body.description)


@router.post("/{project_id}/restore/{number}")
def restore_revision(request: Request, project_id: uuid.UUID, number: int) -> ProjectDocument:
    _get(request, project_id)
    try:
        return _projects(request).restore(project_id, number)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


class DuplicateIn(BaseModel):
    name: str | None = None


@router.post("/{project_id}/duplicate")
def duplicate_project(
    request: Request, project_id: uuid.UUID, body: DuplicateIn
) -> ProjectDocument:
    _get(request, project_id)
    return _projects(request).duplicate(project_id, body.name)


@router.delete("/{project_id}")
def delete_project(request: Request, project_id: uuid.UUID) -> dict[str, str]:
    _get(request, project_id)
    _projects(request).delete(project_id)
    return {"status": "removido"}


def _filename(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", name, flags=re.UNICODE).strip("-") or "projeto"
    return f"{slug}.circuito.json"


def content_disposition(filename: str) -> str:
    """RFC 6266: ASCII fallback plus the UTF-8 name (accents survive in every browser)."""
    ascii_name = (
        unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode() or "arquivo"
    )
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/{project_id}/file")
def export_project(request: Request, project_id: uuid.UUID) -> Response:
    doc = _get(request, project_id)
    text = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return Response(
        text,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": content_disposition(_filename(doc.name))},
    )


@router.post("/import")
async def import_project(request: Request) -> ProjectDocument:
    """Body: the JSON of a ``.circuito.json`` file."""
    try:
        data = json.loads(await request.body())
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "Arquivo não é JSON válido") from exc
    if not isinstance(data, dict):
        raise HTTPException(422, "Arquivo de projeto inválido")
    module_id = data.get("module_id")
    if not isinstance(module_id, str) or module_id not in registry.MODULES:
        raise HTTPException(422, f"Módulo de projeto desconhecido: {module_id!r}")
    try:
        return _projects(request).import_document(data)
    except (DataIntegrityError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
