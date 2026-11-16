"""Queue of datasheets to import: links the user listed, with their check status.

The queue (``data/datasheet-queue.yaml``) holds identification and links only. Importing an item
downloads that one PDF and opens a normal import job (Fase 8), so every value still goes through
extraction, the import screen and the review.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, computed_field

LinkStatus = Literal["ok", "bloqueado", "quebrado", "indisponivel"]

DEFAULT_QUEUE = Path(__file__).parents[4] / "data" / "datasheet-queue.yaml"


def queue_path() -> Path:
    return Path(os.environ.get("CIRCUITOS_DATASHEET_QUEUE", DEFAULT_QUEUE))


class LinkCheck(BaseModel):
    situacao: LinkStatus
    verificado_em: str
    nota: str


class LocalFile(BaseModel):
    """A PDF already on the user's computer (scanned read-only: hash and validity)."""

    caminho: str
    sha256: str
    situacao: Literal["ok", "invalido"]
    nota: str


class QueueItem(BaseModel):
    index: int = 0
    grupo: str
    arquivo: str
    part_number: str
    fabricante: str
    tipo: Literal["peça", "série"] = "peça"
    categoria: str | None = None
    sem_categoria: str | None = None
    url: str | None = None
    link: LinkCheck | None = None
    local: LocalFile | None = None
    no_catalogo: list[str] = Field(default_factory=list)  # filled in by the API

    @computed_field  # type: ignore[prop-decorator]
    @property
    def importable(self) -> bool:
        local_ok = self.local is not None and self.local.situacao == "ok"
        return local_ok or (self.link is not None and self.link.situacao == "ok")


@cache
def _load(path: Path, mtime: float) -> list[QueueItem]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        QueueItem.model_validate({**raw, "index": i})
        for i, raw in enumerate(data.get("datasheets", []))
    ]


def load_queue() -> list[QueueItem]:
    path = queue_path()
    if not path.exists():
        return []
    return [item.model_copy() for item in _load(path, path.stat().st_mtime)]


__all__ = ["LinkStatus", "LocalFile", "QueueItem", "load_queue", "queue_path"]
