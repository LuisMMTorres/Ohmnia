"""Datasheet import jobs: PDF → candidates → component under review.

An import job keeps everything the import screen needs between requests: the PDF hash, the
extraction warnings, the category ranking, the candidates (from the rules and, optionally, the
LLM), the proposals the LLM made that failed verification, and the user's edits. Committing a job
creates a ``ComponentRecord`` whose parameters are all ``extraido`` with their page, excerpt and
bounding box, in review status ``em_revisao``. From there the existing review screen applies:
nothing reaches automatic selection before the user checks every required value (rule 5).
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import JSON, DateTime, String, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from circuitos.components.models import (
    ComponentRecord,
    DatasheetRef,
    Parameter,
    ReviewState,
    SourceRef,
)
from circuitos.components.repository import ComponentRepository, component_id
from circuitos.components.schema import load_schema
from circuitos.core.errors import DataIntegrityError

from . import llm
from .extract import DocumentText, OcrMode, extract_path
from .mapping import Candidate, CategoryScore, map_document, rank_categories
from .store import DatasheetStore

ImportStatus = Literal["extraido", "importado", "descartado"]


class ImportMeta(BaseModel):
    manufacturer: str = ""
    part_number: str = ""
    category: str = ""
    package: str | None = None
    family: str | None = None
    document_number: str | None = None
    revision: str | None = None
    url: HttpUrl | None = None


class ImportJob(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    sha256: str
    filename: str
    pages: int
    status: ImportStatus = "extraido"
    meta: ImportMeta = Field(default_factory=ImportMeta)
    ranking: list[CategoryScore] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    rejected: list[llm.Rejected] = Field(default_factory=list)
    ocr_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    llm_model: str | None = None
    component_id: uuid.UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ImportSummary(BaseModel):
    id: str
    filename: str
    status: ImportStatus
    part_number: str
    category: str
    candidates: int
    accepted: int
    updated_at: datetime


# ---------------------------------------------------------------------------- persistence --


class _Base(DeclarativeBase):
    pass


class _JobRow(_Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    document: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportRepository:
    """Import jobs, in the same SQLite file as the catalogue."""

    def __init__(self, engine: Engine | str = "sqlite:///:memory:"):
        self.engine = create_engine(engine) if isinstance(engine, str) else engine
        _Base.metadata.create_all(self.engine)
        self._session = sessionmaker(self.engine, expire_on_commit=False)

    def save(self, job: ImportJob) -> ImportJob:
        job = job.model_copy(update={"updated_at": datetime.now(UTC)})
        with self._session.begin() as session:
            row = session.get(_JobRow, job.id) or _JobRow(id=job.id)
            row.sha256 = job.sha256
            row.status = job.status
            row.document = job.model_dump(mode="json")
            row.updated_at = job.updated_at
            session.add(row)
        return job

    def get(self, job_id: str) -> ImportJob:
        with self._session() as session:
            row = session.get(_JobRow, job_id)
            if row is None:
                raise DataIntegrityError(f"Importação {job_id} não encontrada")
            return ImportJob.model_validate(row.document)

    def list(self) -> list[ImportSummary]:
        with self._session() as session:
            rows = session.scalars(select(_JobRow).order_by(_JobRow.updated_at.desc())).all()
            jobs = [ImportJob.model_validate(r.document) for r in rows]
        return [
            ImportSummary(
                id=j.id,
                filename=j.filename,
                status=j.status,
                part_number=j.meta.part_number,
                category=j.meta.category,
                candidates=len(j.candidates),
                accepted=sum(c.accepted for c in j.candidates),
                updated_at=j.updated_at,
            )
            for j in jobs
        ]


# ------------------------------------------------------------------------------ workflow --


def _map(doc: DocumentText, job: ImportJob, pdf: bytes | None, use_llm: bool) -> ImportJob:
    category = job.meta.category
    part = job.meta.part_number or None
    candidates = map_document(doc, category, part) if category else []
    rejected: list[llm.Rejected] = []
    model = None
    warnings = list(job.warnings)
    if use_llm and category and pdf is not None:
        status = llm.status()
        if not status.available:
            warnings.append(f"Extração por modelo de linguagem indisponível: {status.reason}")
        else:
            result = llm.propose(pdf, doc, category, part)
            # the LLM fills keys the rules did not find; where both found one, both are shown
            rule_keys = {c.key for c in candidates}
            extra = [
                c.model_copy(update={"accepted": c.key not in rule_keys}) for c in result.candidates
            ]
            candidates = sorted(candidates + extra, key=lambda c: (c.key, -c.confidence))
            rejected = result.rejected
            model = result.model
    return job.model_copy(
        update={
            "candidates": candidates,
            "rejected": rejected,
            "llm_model": model,
            "warnings": warnings,
        }
    )


def start_import(
    store: DatasheetStore,
    sha256: str,
    filename: str,
    meta: ImportMeta | None = None,
    *,
    use_llm: bool = False,
    ocr: OcrMode = "auto",
) -> ImportJob:
    """Extract the PDF, rank categories and map it to the chosen (or best-ranked) category."""
    path = store.path(sha256)
    if not path.exists():
        raise DataIntegrityError("PDF não encontrado no arquivo local; envie o arquivo de novo")
    doc = extract_path(path, ocr=ocr)
    ranking = rank_categories(doc)
    meta = meta or ImportMeta()
    if not meta.category and ranking:
        meta = meta.model_copy(update={"category": ranking[0].category})
    job = ImportJob(
        sha256=sha256,
        filename=filename,
        pages=len(doc.pages),
        meta=meta,
        ranking=ranking,
        ocr_pages=doc.ocr_pages,
        warnings=doc.warnings,
    )
    pdf = path.read_bytes() if use_llm else None
    return _map(doc, job, pdf, use_llm)


def remap(
    store: DatasheetStore, job: ImportJob, meta: ImportMeta, *, use_llm: bool = False
) -> ImportJob:
    """Map again after the user changed the category or the part number."""
    path = store.path(job.sha256)
    doc = extract_path(path)
    pdf = path.read_bytes() if use_llm else None
    base = job.model_copy(update={"meta": meta, "warnings": doc.warnings})
    return _map(doc, base, pdf, use_llm)


def _location(c: Candidate) -> str:
    origin = {"regras": "extração por regras", "llm": "modelo de linguagem", "manual": "manual"}
    return f"{origin[c.method]}, página {c.page}"


def build_record(job: ImportJob, created_by: str) -> ComponentRecord:
    """The component the accepted candidates describe, ready for the review screen."""
    meta = job.meta
    missing = [
        label
        for label, value in (
            ("fabricante", meta.manufacturer),
            ("part number", meta.part_number),
            ("categoria", meta.category),
        )
        if not value.strip()
    ]
    if missing:
        raise DataIntegrityError("Preencha antes de importar: " + ", ".join(missing))
    schema = load_schema(meta.category)
    accepted = [c for c in job.candidates if c.accepted and c.has_value]
    if not accepted:
        raise DataIntegrityError("Nenhum valor aceito para importar")
    datasheet = DatasheetRef(
        id="ds1",
        manufacturer=meta.manufacturer.strip(),
        document_number=meta.document_number,
        revision=meta.revision,
        url=meta.url,
        sha256=job.sha256,
        retrieved_at=job.created_at,
    )
    seen: Counter[str] = Counter()
    parameters: dict[str, Parameter] = {}
    for c in accepted:
        if c.key not in schema.parameters:
            raise DataIntegrityError(f"{c.key}: parâmetro fora do esquema de {meta.category}")
        seen[c.key] += 1
        key = c.key if seen[c.key] == 1 else f"{c.key}@{seen[c.key]}"
        notes = list(c.notes)
        if c.conditions_text:
            notes.append(f"condições no datasheet: {c.conditions_text}")
        parameters[key] = Parameter(
            symbol=c.key,
            min=c.min,
            typ=c.typ,
            max=c.max,
            unit=c.unit,
            conditions=c.conditions,
            source=SourceRef(
                datasheet_id="ds1",
                page=c.page,
                location=_location(c),
                excerpt=c.excerpt[:500],
                bbox=c.bbox,
            ),
            status="extraido",
            note="; ".join(notes) or None,
        )
    return ComponentRecord(
        id=component_id(meta.manufacturer, meta.part_number),
        category=meta.category,
        schema_version=schema.schema_version,
        manufacturer=meta.manufacturer.strip(),
        part_number=meta.part_number.strip(),
        package=meta.package,
        family=meta.family,
        parameters=parameters,
        datasheets=[datasheet],
        review=ReviewState(status="em_revisao", created_by=created_by),
        notes=[f"Importado do PDF {job.filename} (importação {job.id})."],
    )


def commit(
    jobs: ImportRepository,
    components: ComponentRepository,
    job_id: str,
    created_by: str,
    *,
    replace: bool = False,
) -> ComponentRecord:
    job = jobs.get(job_id)
    if job.status == "importado" and not replace:
        raise DataIntegrityError("Esta importação já gerou um componente")
    record = build_record(job, created_by)
    existing = components.get_or_none(record.id)
    if existing is not None and not replace:
        raise DataIntegrityError(
            f"{record.manufacturer} {record.part_number} já existe no catálogo "
            f"({existing.review.status}); confirme a substituição"
        )
    if existing is not None:
        # keep curves and models digitised earlier for the same part
        record = record.model_copy(
            update={"curves": existing.curves, "spice_models": existing.spice_models}
        )
    components.save(record)
    jobs.save(job.model_copy(update={"status": "importado", "component_id": record.id}))
    return record


__all__ = [
    "ImportJob",
    "ImportMeta",
    "ImportRepository",
    "ImportSummary",
    "build_record",
    "commit",
    "remap",
    "start_import",
]
