"""Project documents and their storage.

A project is the *input* of a design: module, specification, derating policy, components locked
by hand and the unit costs typed for the BOM. The results are always recomputed from it, so a
project opened after a catalogue review or a bug fix shows the current answer, never a stale one.

The file format is open JSON (``"format": "circuitos-projeto"``, ``"format_version": 1``), the same
document stored in SQLite. Every save that changes something adds a revision; older revisions stay
in ``history`` and can be restored (which itself is a new revision, so nothing is lost).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, String, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from circuitos.core.errors import DataIntegrityError

FORMAT: Literal["circuitos-projeto"] = "circuitos-projeto"
FORMAT_VERSION = 1

Policy = Literal["didatico", "industrial"]


def _now() -> datetime:
    return datetime.now(UTC)


class Revision(BaseModel):
    number: int = Field(ge=1)
    saved_at: datetime = Field(default_factory=_now)
    spec: dict[str, Any] = Field(default_factory=dict)
    policy: Policy = "didatico"
    locks: dict[str, uuid.UUID] = Field(default_factory=dict)
    costs: dict[str, float] = Field(default_factory=dict)
    note: str | None = None

    def same_content(self, other: Revision) -> bool:
        keys = ("spec", "policy", "locks", "costs")
        return all(getattr(self, k) == getattr(other, k) for k in keys)


class ProjectDocument(BaseModel):
    format: Literal["circuitos-projeto"] = FORMAT
    format_version: int = FORMAT_VERSION
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(min_length=1, max_length=200)
    module_id: str
    description: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    current: Revision
    history: list[Revision] = Field(default_factory=list)

    def revisions(self) -> list[Revision]:
        return [*self.history, self.current]


class ProjectSummary(BaseModel):
    id: uuid.UUID
    name: str
    module_id: str
    revision: int
    updated_at: datetime


class _Base(DeclarativeBase):
    pass


class _ProjectRow(_Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    module_id: Mapped[str] = mapped_column(String(32), index=True)
    document: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectRepository:
    """Projects in the same SQLite file as the catalogue."""

    def __init__(self, engine: Engine | str = "sqlite:///:memory:"):
        self.engine = create_engine(engine) if isinstance(engine, str) else engine
        _Base.metadata.create_all(self.engine)
        self._session = sessionmaker(self.engine, expire_on_commit=False)

    # ------------------------------------------------------------------------------ store --
    def _put(self, doc: ProjectDocument) -> ProjectDocument:
        with self._session.begin() as session:
            row = session.get(_ProjectRow, str(doc.id)) or _ProjectRow(id=str(doc.id))
            row.name = doc.name
            row.module_id = doc.module_id
            row.document = doc.model_dump(mode="json")
            row.updated_at = doc.updated_at
            session.add(row)
        return doc

    def get(self, project_id: uuid.UUID) -> ProjectDocument:
        with self._session() as session:
            row = session.get(_ProjectRow, str(project_id))
            if row is None:
                raise DataIntegrityError(f"Projeto {project_id} não encontrado")
            return ProjectDocument.model_validate(row.document)

    def list(self) -> list[ProjectSummary]:
        with self._session() as session:
            rows = session.scalars(select(_ProjectRow).order_by(_ProjectRow.updated_at.desc()))
            docs = [ProjectDocument.model_validate(r.document) for r in rows]
        return [
            ProjectSummary(
                id=d.id,
                name=d.name,
                module_id=d.module_id,
                revision=d.current.number,
                updated_at=d.updated_at,
            )
            for d in docs
        ]

    def delete(self, project_id: uuid.UUID) -> None:
        with self._session.begin() as session:
            row = session.get(_ProjectRow, str(project_id))
            if row is None:
                raise DataIntegrityError(f"Projeto {project_id} não encontrado")
            session.delete(row)

    # --------------------------------------------------------------------------- workflow --
    def create(
        self,
        name: str,
        module_id: str,
        content: Revision,
        description: str = "",
    ) -> ProjectDocument:
        first = content.model_copy(update={"number": 1, "saved_at": _now()})
        doc = ProjectDocument(
            name=name.strip(), module_id=module_id, description=description, current=first
        )
        return self._put(doc)

    def save(
        self,
        project_id: uuid.UUID,
        content: Revision,
        name: str | None = None,
        description: str | None = None,
    ) -> ProjectDocument:
        """New revision if the design input changed; name/description edits do not count."""
        doc = self.get(project_id)
        update: dict[str, Any] = {"updated_at": _now()}
        if name is not None and name.strip():
            update["name"] = name.strip()
        if description is not None:
            update["description"] = description
        if not content.same_content(doc.current):
            new = content.model_copy(update={"number": doc.current.number + 1, "saved_at": _now()})
            update["history"] = [*doc.history, doc.current]
            update["current"] = new
        elif content.note and content.note != doc.current.note:
            update["current"] = doc.current.model_copy(update={"note": content.note})
        return self._put(doc.model_copy(update=update))

    def restore(self, project_id: uuid.UUID, number: int) -> ProjectDocument:
        doc = self.get(project_id)
        old = next((r for r in doc.revisions() if r.number == number), None)
        if old is None:
            raise DataIntegrityError(f"Revisão {number} não existe")
        content = old.model_copy(update={"note": f"restaurada da revisão {number}"})
        return self.save(project_id, content)

    def duplicate(self, project_id: uuid.UUID, name: str | None = None) -> ProjectDocument:
        doc = self.get(project_id)
        copy = doc.current.model_copy(
            update={"note": f"cópia de “{doc.name}”, revisão {doc.current.number}"}
        )
        return self.create(name or f"{doc.name} (cópia)", doc.module_id, copy, doc.description)

    def import_document(self, data: dict[str, Any]) -> ProjectDocument:
        """A project file from another machine. A clash of ids gets a new id, never an overwrite."""
        if data.get("format") != FORMAT:
            raise DataIntegrityError("O arquivo não é um projeto do sistema (format ausente)")
        version = data.get("format_version")
        if not isinstance(version, int) or version > FORMAT_VERSION:
            raise DataIntegrityError(
                f"Versão do formato {version!r} não suportada (esta versão lê até {FORMAT_VERSION})"
            )
        doc = ProjectDocument.model_validate(data)
        try:
            self.get(doc.id)
        except DataIntegrityError:
            return self._put(doc)
        return self._put(
            doc.model_copy(update={"id": uuid.uuid4(), "name": f"{doc.name} (importado)"})
        )


__all__ = [
    "FORMAT",
    "FORMAT_VERSION",
    "ProjectDocument",
    "ProjectRepository",
    "ProjectSummary",
    "Revision",
]
