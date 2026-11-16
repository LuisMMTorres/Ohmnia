"""Datasheet import, curve digitising and SPICE model endpoints (Phase 8)."""

from __future__ import annotations

import re
import urllib.error
import uuid
from pathlib import Path
from typing import Annotated, Literal

import pymupdf
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from circuitos.api.catalog import ComponentDetail, _detail, _get, _repo, _store
from circuitos.components.models import AxisSpec, ComponentRecord, Curve, SourceRef, SpiceModel
from circuitos.core.errors import CircuitosError, DataIntegrityError
from circuitos.core.units import QuantityModel
from circuitos.datasheets import llm
from circuitos.datasheets.digitize import (
    Calibration,
    Rect,
    VectorPath,
    open_page,
    trace_colour,
    vector_paths,
)
from circuitos.datasheets.extract import OcrMode, extract_path, ocr_available
from circuitos.datasheets.fit import fit_for
from circuitos.datasheets.imports import (
    ImportJob,
    ImportMeta,
    ImportRepository,
    ImportSummary,
    commit,
    remap,
    start_import,
)
from circuitos.datasheets.mapping import Candidate
from circuitos.datasheets.queue import QueueItem, load_queue
from circuitos.datasheets.spice_import import check_model, parse_models
from circuitos.datasheets.store import DatasheetStore

router = APIRouter(prefix="/api/v1")

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_PDF = 60 * 1024 * 1024


def _imports(request: Request) -> ImportRepository:
    jobs: ImportRepository | None = getattr(request.app.state, "imports", None)
    if jobs is None:
        jobs = ImportRepository(_repo(request).engine)
        request.app.state.imports = jobs
    return jobs


def _job(request: Request, job_id: str) -> ImportJob:
    try:
        return _imports(request).get(job_id)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


def _check_sha(sha256: str) -> None:
    if not _SHA.match(sha256):
        raise HTTPException(422, "Hash inválido")


class ImportCapabilities(BaseModel):
    ocr: bool
    llm: llm.LlmStatus


@router.get("/imports/capabilities")
def capabilities() -> ImportCapabilities:
    return ImportCapabilities(ocr=ocr_available(), llm=llm.status())


# ------------------------------------------------------------------------------- upload ----


class Uploaded(BaseModel):
    sha256: str
    pages: int
    filename: str


@router.post("/datasheets")
async def upload_datasheet(request: Request, filename: str = "datasheet.pdf") -> Uploaded:
    """Raw PDF in the request body (``Content-Type: application/pdf``)."""
    content = await request.body()
    if len(content) > _MAX_PDF:
        raise HTTPException(413, "PDF maior que 60 MB")
    store = _store(request)
    try:
        sha = store.add(content)
        pages = store.page_count(sha)
    except DataIntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Uploaded(sha256=sha, pages=pages, filename=filename)


class TextRow(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]


class PageTextOut(BaseModel):
    page: int
    width: float
    height: float
    ocr: bool
    rows: list[TextRow]


@router.get("/datasheets/{sha256}/pages/{page}/text")
def page_text(request: Request, sha256: str, page: int) -> PageTextOut:
    _check_sha(sha256)
    store = _store(request)
    if not store.has(sha256):
        raise HTTPException(404, "Datasheet não está no arquivo local")
    doc = extract_path(store.path(sha256))
    try:
        p = doc.page(page)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return PageTextOut(
        page=page,
        width=p.width,
        height=p.height,
        ocr=p.ocr,
        rows=[TextRow(text=r.text, bbox=r.bbox) for r in p.rows],
    )


# ------------------------------------------------------------------------------- imports ---


class ImportIn(BaseModel):
    sha256: str
    filename: str = "datasheet.pdf"
    meta: ImportMeta = Field(default_factory=ImportMeta)
    use_llm: bool = False
    ocr: OcrMode = "auto"


@router.post("/imports")
def create_import(request: Request, body: ImportIn) -> ImportJob:
    _check_sha(body.sha256)
    try:
        job = start_import(
            _store(request),
            body.sha256,
            body.filename,
            body.meta,
            use_llm=body.use_llm,
            ocr=body.ocr,
        )
    except (CircuitosError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _imports(request).save(job)


@router.get("/imports")
def list_imports(request: Request) -> list[ImportSummary]:
    return _imports(request).list()


@router.get("/imports/{job_id}")
def get_import(request: Request, job_id: str) -> ImportJob:
    return _job(request, job_id)


class ImportEdit(BaseModel):
    meta: ImportMeta
    candidates: list[Candidate]


@router.put("/imports/{job_id}")
def edit_import(request: Request, job_id: str, body: ImportEdit) -> ImportJob:
    job = _job(request, job_id)
    if job.status != "extraido":
        raise HTTPException(409, "Importação já concluída ou descartada")
    for c in body.candidates:
        if c.page > job.pages:
            raise HTTPException(422, f"{c.key}: página {c.page} fora do PDF")
    updated = job.model_copy(update={"meta": body.meta, "candidates": body.candidates})
    return _imports(request).save(updated)


class RemapIn(BaseModel):
    meta: ImportMeta
    use_llm: bool = False


@router.post("/imports/{job_id}/remap")
def remap_import(request: Request, job_id: str, body: RemapIn) -> ImportJob:
    job = _job(request, job_id)
    try:
        updated = remap(_store(request), job, body.meta, use_llm=body.use_llm)
    except (CircuitosError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _imports(request).save(updated)


class CommitIn(BaseModel):
    created_by: str
    replace: bool = False


@router.post("/imports/{job_id}/commit")
def commit_import(request: Request, job_id: str, body: CommitIn) -> ComponentDetail:
    _job(request, job_id)
    if not body.created_by.strip():
        raise HTTPException(422, "Informe quem fez a importação")
    try:
        record = commit(
            _imports(request),
            _repo(request),
            job_id,
            body.created_by.strip(),
            replace=body.replace,
        )
    except DataIntegrityError as exc:
        status = 409 if "já existe" in str(exc) or "já gerou" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    except ValueError as exc:  # parameter validation (pydantic)
        raise HTTPException(422, str(exc)) from exc
    return _detail(record)


@router.delete("/imports/{job_id}")
def discard_import(request: Request, job_id: str) -> ImportJob:
    job = _job(request, job_id)
    return _imports(request).save(job.model_copy(update={"status": "descartado"}))


# ----------------------------------------------------------------------------- digitising --


def _page_of(request: Request, sha256: str, page: int) -> tuple[pymupdf.Document, pymupdf.Page]:
    _check_sha(sha256)
    store = _store(request)
    if not store.has(sha256):
        raise HTTPException(404, "Datasheet não está no arquivo local")
    try:
        return open_page(store.path(sha256), page)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/datasheets/{sha256}/pages/{page}/vector-paths")
def find_vector_paths(request: Request, sha256: str, page: int, rect: Rect) -> list[VectorPath]:
    doc, p = _page_of(request, sha256, page)
    with doc:
        return vector_paths(p, rect)


class TraceIn(BaseModel):
    rect: Rect
    colour: tuple[int, int, int]
    tolerance: Annotated[int, Field(ge=0, le=300)] = 60
    columns: Annotated[int, Field(ge=5, le=400)] = 60


@router.post("/datasheets/{sha256}/pages/{page}/trace")
def trace(request: Request, sha256: str, page: int, body: TraceIn) -> list[tuple[float, float]]:
    doc, p = _page_of(request, sha256, page)
    with doc:
        return trace_colour(p, body.rect, body.colour, body.tolerance, columns=body.columns)


class CurveIn(BaseModel):
    name: str
    x: AxisSpec
    y: AxisSpec
    family: dict[str, QuantityModel] = Field(default_factory=dict)
    calibration: Calibration
    positions: list[tuple[float, float]] = Field(min_length=2)
    datasheet_id: str
    page: int = Field(ge=1)
    location: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    method: Literal["manual", "vetor", "cor"] = "manual"
    digitized_by: str


def _save(request: Request, record: ComponentRecord) -> ComponentDetail:
    try:
        validated = ComponentRecord.model_validate(record.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _detail(_repo(request).save(validated))


@router.post("/components/{component_id}/curves")
def add_curve(request: Request, component_id: uuid.UUID, body: CurveIn) -> ComponentDetail:
    record = _get(request, component_id)
    if body.x.scale != body.calibration.x.scale or body.y.scale != body.calibration.y.scale:
        raise HTTPException(422, "Escala dos eixos difere da calibração")
    if not body.digitized_by.strip():
        raise HTTPException(422, "Informe quem digitalizou a curva")
    try:
        curve = Curve(
            name=body.name,
            x=body.x,
            y=body.y,
            family=body.family,
            points=body.calibration.to_values(body.positions),
            source=SourceRef(
                datasheet_id=body.datasheet_id,
                page=body.page,
                location=body.location or body.name,
                bbox=body.bbox,
            ),
            method=body.method,
            digitized_by=body.digitized_by.strip(),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _save(request, record.model_copy(update={"curves": [*record.curves, curve]}))


@router.delete("/components/{component_id}/curves/{curve_id}")
def delete_curve(request: Request, component_id: uuid.UUID, curve_id: str) -> ComponentDetail:
    record = _get(request, component_id)
    curves = [c for c in record.curves if c.id != curve_id]
    if len(curves) == len(record.curves):
        raise HTTPException(404, "Curva não encontrada")
    return _save(request, record.model_copy(update={"curves": curves}))


# --------------------------------------------------------------------------- SPICE models --


class ModelImportIn(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)
    source_note: str | None = None


@router.post("/components/{component_id}/spice-models/import")
def import_models(
    request: Request, component_id: uuid.UUID, body: ModelImportIn
) -> ComponentDetail:
    record = _get(request, component_id)
    try:
        models = parse_models(body.text, body.source_note)
    except CircuitosError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not models:
        raise HTTPException(422, "Nenhum .model ou .subckt encontrado no arquivo")
    checked: list[SpiceModel] = []
    for m in models:
        try:
            result = check_model(m, library=body.text)
            checked.append(m.model_copy(update={"checked": result.ok, "check_log": result.log}))
        except CircuitosError as exc:
            checked.append(m.model_copy(update={"checked": False, "check_log": str(exc)}))
    return _save(
        request, record.model_copy(update={"spice_models": [*record.spice_models, *checked]})
    )


class FitIn(BaseModel):
    curve_ids: list[str] = Field(default_factory=list)
    name: str | None = None


@router.post("/components/{component_id}/spice-models/fit")
def fit_model(request: Request, component_id: uuid.UUID, body: FitIn) -> ComponentDetail:
    record = _get(request, component_id)
    try:
        model = fit_for(record, body.curve_ids, body.name)
    except CircuitosError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _save(request, record.model_copy(update={"spice_models": [*record.spice_models, model]}))


@router.delete("/components/{component_id}/spice-models/{model_id}")
def delete_model(request: Request, component_id: uuid.UUID, model_id: str) -> ComponentDetail:
    record = _get(request, component_id)
    models = [m for m in record.spice_models if m.id != model_id]
    if len(models) == len(record.spice_models):
        raise HTTPException(404, "Modelo não encontrado")
    return _save(request, record.model_copy(update={"spice_models": models}))


# ---------------------------------------------------------------------- datasheet queue --


def _norm_part(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def _same_part(record: ComponentRecord, queued: str) -> bool:
    """Exact part number, or the record's declared family (LM358P belongs to family LM358).

    A prefix match would be wrong: IRF540 and IRF540N are different parts.
    """
    want = _norm_part(queued)
    names = [record.part_number, *re.split(r"[/,;]", record.family or "")]
    return any(_norm_part(n) == want for n in names if n.strip())


@router.get("/datasheet-queue")
def datasheet_queue(request: Request) -> list[QueueItem]:
    """Datasheets the user listed for import, with link status and catalogue matches."""
    repo = _repo(request)
    items = load_queue()
    for item in items:
        found = repo.search(text=item.part_number)
        item.no_catalogo = [
            f"{r.manufacturer} {r.part_number} ({r.review.status})"
            for r in found
            if _same_part(r, item.part_number)
        ]
    return items


class QueueImportIn(BaseModel):
    use_llm: bool = False


def _queued_pdf(store: DatasheetStore, item: QueueItem) -> str:
    """The PDF of a queue item: already stored, the local copy, or downloaded from the link."""
    local = item.local
    if local is not None and local.situacao == "ok":
        if store.has(local.sha256):
            return local.sha256
        path = Path(local.caminho)
        if path.exists():
            try:
                sha = store.add(path.read_bytes())
            except DataIntegrityError as exc:
                raise HTTPException(422, f"{item.arquivo}: {exc}") from exc
            if sha != local.sha256:
                raise HTTPException(
                    409,
                    f"{path} mudou desde a verificação (hash diferente); confira o arquivo",
                )
            return sha
        if item.url is None:
            raise HTTPException(404, f"Arquivo local não encontrado: {path}")
    if item.url is None or item.link is None or item.link.situacao != "ok":
        raise HTTPException(422, f"{item.arquivo}: sem PDF local válido nem link que funcione")
    try:
        return store.fetch(item.url)
    except DataIntegrityError as exc:
        raise HTTPException(422, f"{item.arquivo}: o endereço não devolveu um PDF ({exc})") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(
            502,
            f"Não foi possível baixar {item.url}: {exc}. Baixe pelo navegador e envie o PDF "
            "na tela de importação.",
        ) from exc


@router.post("/datasheet-queue/{index}/import")
def import_from_queue(request: Request, index: int, body: QueueImportIn) -> ImportJob:
    """Download this one PDF and open an import job with the queue's identification."""
    items = load_queue()
    if not 0 <= index < len(items):
        raise HTTPException(404, "Item da fila não encontrado")
    item = items[index]
    store = _store(request)
    sha = _queued_pdf(store, item)
    meta = ImportMeta(
        manufacturer=item.fabricante,
        part_number=item.part_number,
        category=item.categoria or "",
        url=item.url if item.link is not None and item.link.situacao == "ok" else None,
    )
    try:
        job = start_import(store, sha, item.arquivo, meta, use_llm=body.use_llm)
    except (CircuitosError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _imports(request).save(job)
