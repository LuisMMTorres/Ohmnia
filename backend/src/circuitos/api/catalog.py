"""Component catalogue and datasheet endpoints."""

from __future__ import annotations

import os
import re
import urllib.error
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from circuitos.components.models import ComponentRecord, ParameterStatus
from circuitos.components.repository import ComponentRepository, ParamFilter, dump_record
from circuitos.components.schema import (
    CategorySchema,
    available_categories,
    load_schema,
    release_blockers,
)
from circuitos.core.errors import CircuitosError, DataIntegrityError
from circuitos.core.units import QuantityModel, parse_quantity
from circuitos.datasheets.store import DatasheetStore, data_dir

router = APIRouter(prefix="/api/v1")

DEFAULT_CATALOG = Path(__file__).parents[4] / "data" / "components"


def catalog_dir() -> Path:
    return Path(os.environ.get("CIRCUITOS_CATALOG_DIR", DEFAULT_CATALOG))


def open_repository() -> ComponentRepository:
    url = os.environ.get("CIRCUITOS_DB_URL", f"sqlite:///{data_dir() / 'catalog.db'}")
    repo = ComponentRepository(url)
    if catalog_dir().is_dir():
        repo.import_directory(catalog_dir())
    return repo


def _repo(request: Request) -> ComponentRepository:
    repo: ComponentRepository = request.app.state.components
    return repo


def _store(request: Request) -> DatasheetStore:
    store: DatasheetStore = request.app.state.datasheets
    return store


_FILTER = re.compile(r"^\s*([^<>=\s]+)\s*(>=|<=)\s*(.+?)\s*$")


def parse_filter(text: str) -> ParamFilter:
    match = _FILTER.match(text)
    if not match:
        raise HTTPException(422, f"Filtro inválido: {text!r}. Use, por exemplo, 'VRRM>=600 V'")
    symbol, op, value = match.groups()
    try:
        quantity = parse_quantity(value)
    except CircuitosError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ParamFilter(
        symbol=symbol,
        op=op,
        value=QuantityModel(value=float(quantity.magnitude), unit=f"{quantity.units:~C}"),
    )


class ComponentSummary(BaseModel):
    id: uuid.UUID
    category: str
    manufacturer: str
    part_number: str
    family: str | None
    package: str | None
    review_status: str
    parameters_reviewed: int
    parameters_total: int
    highlights: dict[str, str]


_HIGHLIGHT_DIODE = ["VRRM", "IF(AV)", "IFSM", "VF", "trr"]
_HIGHLIGHT = {
    "diode.zener": ["VZ", "IZT", "ZZT", "IR", "Ptot"],
    "bjt.npn": ["VCEO", "IC", "Ptot", "hFE", "fT"],
    "bjt.pnp": ["VCEO", "IC", "Ptot", "hFE", "fT"],
    "mosfet.n": ["VDS", "ID", "RDS(on)", "VGS(th)", "Qg"],
    "thyristor.scr": ["VDRM", "IT(RMS)", "ITSM", "IGT", "IH"],
    "thyristor.triac": ["VDRM", "IT(RMS)", "ITSM", "IGT@Q1", "IH"],
    "thyristor.diac": ["VBO", "dV", "IBO", "Ptot"],
}
_UNIT_TEXT = {"degC": "°C", "uA": "µA", "us": "µs", "ohm": "Ω", "percent": "%", "dimensionless": ""}


def _fmt(record: ComponentRecord, key: str) -> str | None:
    param = record.parameters.get(key)
    if param is None or not param.has_value:
        return None
    # Characteristics are shown by their nominal value; ratings by their limit.
    order = ("typ", "max", "min") if param.typ is not None else ("max", "min")
    value = next(v for k in order if (v := getattr(param, k)) is not None)
    unit = _UNIT_TEXT.get(param.unit, param.unit)
    return f"{value:g} {unit}".strip().replace(".", ",")


def summarise(record: ComponentRecord) -> ComponentSummary:
    params = record.parameters.values()
    return ComponentSummary(
        id=record.id,
        category=record.category,
        manufacturer=record.manufacturer,
        part_number=record.part_number,
        family=record.family,
        package=record.package,
        review_status=record.review.status,
        parameters_reviewed=sum(p.status == "revisado" for p in params),
        parameters_total=len(record.parameters),
        highlights={
            k: v
            for k in _HIGHLIGHT.get(record.category, _HIGHLIGHT_DIODE)
            if (v := _fmt(record, k))
        },
    )


class ComponentDetail(BaseModel):
    record: ComponentRecord
    schema_: CategorySchema
    release_blockers: list[str]


def _detail(record: ComponentRecord) -> ComponentDetail:
    return ComponentDetail(
        record=record,
        schema_=load_schema(record.category),
        release_blockers=release_blockers(record),
    )


@router.get("/components")
def list_components(
    request: Request,
    category: str | None = None,
    q: str | None = None,
    status: str | None = None,
    filter: Annotated[list[str] | None, Query()] = None,
) -> list[ComponentSummary]:
    filters = [parse_filter(f) for f in filter or []]
    records = _repo(request).search(
        category=category, text=q, review_status=status, filters=filters
    )
    return [summarise(r) for r in records]


@router.get("/components/categories")
def categories() -> list[str]:
    return available_categories()


@router.get("/components/schemas/{category}")
def category_schema(category: str) -> CategorySchema:
    try:
        return load_schema(category)
    except CircuitosError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/components/stats")
def component_stats(request: Request) -> dict[str, int]:
    return _repo(request).categories()


def _get(request: Request, component_id: uuid.UUID) -> ComponentRecord:
    try:
        return _repo(request).get(component_id)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/components/{component_id}")
def get_component(request: Request, component_id: uuid.UUID) -> ComponentDetail:
    return _detail(_get(request, component_id))


class ParameterReview(BaseModel):
    status: ParameterStatus
    note: str | None = None


@router.post("/components/{component_id}/parameters/{key}/review")
def review_parameter(
    request: Request, component_id: uuid.UUID, key: str, body: ParameterReview
) -> ComponentDetail:
    _get(request, component_id)
    try:
        record = _repo(request).set_parameter_status(component_id, key, body.status, body.note)
    except (DataIntegrityError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _detail(record)


class ReleaseIn(BaseModel):
    reviewer: str


@router.post("/components/{component_id}/release")
def release_component(
    request: Request, component_id: uuid.UUID, body: ReleaseIn
) -> ComponentDetail:
    _get(request, component_id)
    if not body.reviewer.strip():
        raise HTTPException(422, "Informe o nome de quem revisou")
    try:
        record = _repo(request).release(component_id, body.reviewer.strip())
    except DataIntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _detail(record)


class CategoryReviewIn(BaseModel):
    category: str
    reviewer: str = ""
    dry_run: bool = False


class CategoryReviewItemOut(BaseModel):
    id: uuid.UUID
    manufacturer: str
    part_number: str
    before: str
    after: str
    marked: int
    unsourced: list[str]
    blockers: list[str]


class CategoryReviewOut(BaseModel):
    category: str
    dry_run: bool
    items: list[CategoryReviewItemOut]
    released: int
    pending: int
    already_released: int


@router.post("/components/review-category")
def review_category(request: Request, body: CategoryReviewIn) -> CategoryReviewOut:
    """Review every pending record of a category at once (preview with dry_run)."""
    if body.category not in _repo(request).categories():
        raise HTTPException(404, f"Categoria sem componentes: {body.category}")
    if not body.dry_run and not body.reviewer.strip():
        raise HTTPException(422, "Informe o nome de quem revisou")
    repo = _repo(request)
    already = sum(
        r.review.status == "liberado"
        for r in repo.search(category=body.category)
        if r.category == body.category
    )
    items = repo.review_category(body.category, body.reviewer.strip(), dry_run=body.dry_run)
    return CategoryReviewOut(
        category=body.category,
        dry_run=body.dry_run,
        items=[CategoryReviewItemOut(**vars(i)) for i in items],
        released=sum(i.after == "liberado" for i in items),
        pending=sum(i.after != "liberado" for i in items),
        already_released=already,
    )


class AllReviewIn(BaseModel):
    reviewer: str = ""
    dry_run: bool = False


@router.post("/components/review-all")
def review_all(request: Request, body: AllReviewIn) -> CategoryReviewOut:
    """Review and release every pending component of the catalogue (preview with dry_run)."""
    if not body.dry_run and not body.reviewer.strip():
        raise HTTPException(422, "Informe o nome de quem revisou")
    repo = _repo(request)
    already = len(repo.search(review_status="liberado"))
    items = repo.review_all(body.reviewer.strip(), dry_run=body.dry_run)
    return CategoryReviewOut(
        category="",
        dry_run=body.dry_run,
        items=[CategoryReviewItemOut(**vars(i)) for i in items],
        released=sum(i.after == "liberado" for i in items),
        pending=sum(i.after != "liberado" for i in items),
        already_released=already,
    )


class PartsReviewIn(BaseModel):
    ids: list[uuid.UUID]
    reviewer: str = ""
    dry_run: bool = False


class PartsReviewOut(BaseModel):
    dry_run: bool
    items: list[CategoryReviewItemOut]
    released: int
    pending: int


@router.post("/components/review-parts")
def review_parts(request: Request, body: PartsReviewIn) -> PartsReviewOut:
    """Review and release the given parts (those of one circuit); preview with dry_run."""
    if not body.ids:
        raise HTTPException(422, "Nenhum componente indicado")
    if not body.dry_run and not body.reviewer.strip():
        raise HTTPException(422, "Informe o nome de quem revisou")
    try:
        items = _repo(request).review_records(body.ids, body.reviewer.strip(), dry_run=body.dry_run)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return PartsReviewOut(
        dry_run=body.dry_run,
        items=[CategoryReviewItemOut(**vars(i)) for i in items],
        released=sum(i.after == "liberado" for i in items),
        pending=sum(i.after != "liberado" for i in items),
    )


@router.get("/components/{component_id}/yaml")
def export_component(request: Request, component_id: uuid.UUID) -> Response:
    record = _get(request, component_id)
    return Response(dump_record(record), media_type="text/yaml; charset=utf-8")


# --------------------------------------------------------------------------- datasheets --

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _ensure_local(request: Request, sha256: str) -> DatasheetStore:
    """Fetch the PDF from its catalogue URL the first time it is needed."""
    if not _SHA.match(sha256):
        raise HTTPException(422, "Hash inválido")
    store = _store(request)
    if store.has(sha256):
        return store
    for record in _repo(request).search():
        for ds in record.datasheets:
            if ds.sha256 == sha256 and ds.url is not None:
                try:
                    store.fetch(str(ds.url), expected_sha256=sha256)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    raise HTTPException(
                        502, f"Não foi possível baixar o datasheet de {ds.url}: {exc}"
                    ) from exc
                except DataIntegrityError as exc:
                    raise HTTPException(409, str(exc)) from exc
                return store
    raise HTTPException(404, "Datasheet desconhecido")


class DatasheetInfo(BaseModel):
    sha256: str
    pages: int


@router.get("/datasheets/{sha256}")
def datasheet_info(request: Request, sha256: str) -> DatasheetInfo:
    store = _ensure_local(request, sha256)
    return DatasheetInfo(sha256=sha256, pages=store.page_count(sha256))


@router.get("/datasheets/{sha256}/pages/{page}.png")
def datasheet_page(
    request: Request, sha256: str, page: int, zoom: Annotated[float, Query(ge=0.5, le=4)] = 2.0
) -> Response:
    store = _ensure_local(request, sha256)
    try:
        png = store.render_page(sha256, page, zoom)
    except DataIntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@router.get("/datasheets/{sha256}/pdf")
def datasheet_pdf(request: Request, sha256: str) -> Response:
    store = _ensure_local(request, sha256)
    return Response(store.path(sha256).read_bytes(), media_type="application/pdf")
