"""Content-addressed datasheet archive.

PDFs are stored by SHA-256 under the user's data directory and never committed to the repository
(manufacturer licences). The catalogue YAML keeps URL + hash, so anyone can fetch the exact same
file again and verify it (``scripts/fetch_datasheets.py``).
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

import pymupdf

from circuitos.core.errors import DataIntegrityError

_USER_AGENT = "Mozilla/5.0 (compatible; circuitos-datasheet-fetcher)"


def data_dir() -> Path:
    root = Path(os.environ.get("CIRCUITOS_DATA_DIR", Path.home() / ".circuitos"))
    root.mkdir(parents=True, exist_ok=True)
    return root


class DatasheetStore:
    def __init__(self, root: Path | None = None):
        self.root = (root or data_dir()) / "datasheets"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, sha256: str) -> Path:
        return self.root / sha256[:2] / f"{sha256}.pdf"

    def has(self, sha256: str) -> bool:
        return self.path(sha256).exists()

    def add(self, content: bytes) -> str:
        if not content.startswith(b"%PDF"):
            raise DataIntegrityError("O arquivo não é um PDF")
        digest = hashlib.sha256(content).hexdigest()
        target = self.path(digest)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(content)
            tmp.replace(target)
        return digest

    def fetch(self, url: str, expected_sha256: str | None = None, timeout: float = 60) -> str:
        """Download a datasheet (if not cached) and verify its hash."""
        if expected_sha256 and self.has(expected_sha256):
            return expected_sha256
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
        digest = self.add(content)
        if expected_sha256 and digest != expected_sha256:
            raise DataIntegrityError(
                f"O datasheet em {url} mudou (hash {digest[:12]}…, esperado "
                f"{expected_sha256[:12]}…). Revise os parâmetros antes de atualizar o hash."
            )
        return digest

    def _open(self, sha256: str) -> pymupdf.Document:
        path = self.path(sha256)
        if not path.exists():
            raise DataIntegrityError(f"Datasheet {sha256[:12]}… não está no arquivo local")
        return pymupdf.open(path)

    def page_count(self, sha256: str) -> int:
        with self._open(sha256) as doc:
            return int(doc.page_count)

    def page_text(self, sha256: str, page: int) -> str:
        """Text of a 1-based page."""
        with self._open(sha256) as doc:
            self._check_page(doc, page)
            return str(doc[page - 1].get_text())

    def find(self, sha256: str, text: str) -> list[int]:
        """1-based pages that contain ``text`` (case-insensitive)."""
        needle = text.lower()
        with self._open(sha256) as doc:
            return [i + 1 for i, p in enumerate(doc) if needle in str(p.get_text()).lower()]

    def render_page(self, sha256: str, page: int, zoom: float = 2.0) -> bytes:
        return _render(self.path(sha256), page, zoom)

    @staticmethod
    def _check_page(doc: pymupdf.Document, page: int) -> None:
        if not 1 <= page <= doc.page_count:
            raise DataIntegrityError(f"Página {page} fora do documento (1–{doc.page_count})")


@lru_cache(maxsize=64)
def _render(path: Path, page: int, zoom: float) -> bytes:
    if not path.exists():
        raise DataIntegrityError("Datasheet não está no arquivo local")
    with pymupdf.open(path) as doc:
        DatasheetStore._check_page(doc, page)
        pix = doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        return bytes(pix.tobytes("png"))
