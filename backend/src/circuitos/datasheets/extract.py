"""Text extraction from datasheet PDFs: words with positions, rebuilt into visual rows.

Datasheet tables are mostly borderless, so the reliable unit is the *visual row*: the words that
share a baseline across the whole page width, ordered by x. Rows keep every word's bounding box
(PDF points, origin at the top-left, as PyMuPDF reports), which is what the review screen uses to
highlight the origin of each value.

Scanned pages (no text layer) go through OCR with the Tesseract engine built into PyMuPDF; only
the language files (``tessdata``) must be installed. OCR text is marked on the page, because its
values deserve extra care in the review.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pymupdf

from circuitos.core.errors import DataIntegrityError

from .textvalues import normalise_text

OcrMode = Literal["auto", "never", "always"]

# A page with fewer characters than this in its text layer is treated as scanned.
_MIN_TEXT_CHARS = 40

_TESSDATA_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tessdata",
    r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",
    "/usr/local/share/tessdata",
    "/opt/homebrew/share/tessdata",
)


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0


Bbox = tuple[float, float, float, float]


def union(words: list[Word]) -> Bbox:
    return (
        min(w.x0 for w in words),
        min(w.y0 for w in words),
        max(w.x1 for w in words),
        max(w.y1 for w in words),
    )


@dataclass
class Row:
    page: int
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> Bbox:
        return union(self.words)

    @property
    def height(self) -> float:
        return statistics.median(w.height for w in self.words)

    def cells(self) -> list[list[Word]]:
        """Words grouped by large horizontal gaps (table columns)."""
        if not self.words:
            return []
        gap = max(4.0, 0.9 * self.height)
        groups: list[list[Word]] = [[self.words[0]]]
        for prev, word in zip(self.words, self.words[1:], strict=False):
            if word.x0 - prev.x1 > gap:
                groups.append([word])
            else:
                groups[-1].append(word)
        return groups


@dataclass
class PageText:
    number: int  # 1-based
    width: float
    height: float
    rows: list[Row]
    ocr: bool = False

    @property
    def text(self) -> str:
        return "\n".join(r.text for r in self.rows)


@dataclass
class DocumentText:
    pages: list[PageText] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def page(self, number: int) -> PageText:
        for p in self.pages:
            if p.number == number:
                return p
        raise DataIntegrityError(f"Página {number} não extraída")

    @property
    def rows(self) -> list[Row]:
        return [r for p in self.pages for r in p.rows]


def tessdata_dir() -> str | None:
    """Folder with Tesseract language files, or ``None`` when OCR is not available."""
    for env in ("CIRCUITOS_TESSDATA", "TESSDATA_PREFIX"):
        value = os.environ.get(env)
        if value and Path(value).is_dir():
            return value
    for candidate in _TESSDATA_CANDIDATES:
        if Path(candidate, "eng.traineddata").exists():
            return candidate
    return None


def ocr_available() -> bool:
    return tessdata_dir() is not None


def group_rows(words: list[Word], page: int) -> list[Row]:
    """Visual rows: words whose vertical centres fall inside the band of the row being built."""
    rows: list[Row] = []
    for word in sorted(words, key=lambda w: (w.yc, w.x0)):
        if rows:
            last = rows[-1]
            y0 = min(w.y0 for w in last.words)
            y1 = max(w.y1 for w in last.words)
            tolerance = 0.35 * min(word.height, y1 - y0)
            if y0 - tolerance <= word.yc <= y1 + tolerance and abs(
                word.yc - statistics.median(w.yc for w in last.words)
            ) <= 0.6 * max(word.height, 1.0):
                last.words.append(word)
                continue
        rows.append(Row(page=page, words=[word]))
    for row in rows:
        row.words.sort(key=lambda w: w.x0)
    return rows


def _words(page: pymupdf.Page, textpage: pymupdf.TextPage | None = None) -> list[Word]:
    raw = page.get_text("words", textpage=textpage) if textpage else page.get_text("words")
    out = []
    for x0, y0, x1, y1, text, *_ in raw:
        t = normalise_text(str(text)).strip()
        if t:
            out.append(Word(t, float(x0), float(y0), float(x1), float(y1)))
    return out


def extract_document(
    doc: pymupdf.Document, *, ocr: OcrMode = "auto", language: str = "eng"
) -> DocumentText:
    result = DocumentText()
    tessdata = tessdata_dir()
    if ocr == "always" and tessdata is None:
        raise DataIntegrityError(
            "OCR pedido, mas os arquivos de idioma do Tesseract (tessdata) não foram encontrados"
        )
    for index in range(doc.page_count):
        page = doc[index]
        number = index + 1
        words = _words(page)
        chars = sum(len(w.text) for w in words)
        used_ocr = False
        scanned = chars < _MIN_TEXT_CHARS and bool(page.get_images())
        if ocr == "always" or (ocr == "auto" and scanned):
            if tessdata is None:
                result.warnings.append(
                    f"Página {number} parece digitalizada (sem texto), mas o OCR não está "
                    "disponível: instale o Tesseract com os idiomas eng/por."
                )
            else:
                textpage = page.get_textpage_ocr(
                    language=language, dpi=300, full=True, tessdata=tessdata
                )
                words = _words(page, textpage)
                used_ocr = True
                result.ocr_pages.append(number)
        result.pages.append(
            PageText(
                number=number,
                width=float(page.rect.width),
                height=float(page.rect.height),
                rows=group_rows(words, number),
                ocr=used_ocr,
            )
        )
    return result


def extract_path(path: Path, *, ocr: OcrMode = "auto", language: str = "eng") -> DocumentText:
    with pymupdf.open(path) as doc:
        return extract_document(doc, ocr=ocr, language=language)


__all__ = [
    "DocumentText",
    "OcrMode",
    "PageText",
    "Row",
    "Word",
    "extract_document",
    "extract_path",
    "group_rows",
    "ocr_available",
    "tessdata_dir",
    "union",
]
