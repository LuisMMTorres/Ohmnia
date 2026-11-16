"""PDF design report, rendered on the server (PyMuPDF Story; no browser, no GTK).

Same content as the HTML report (:func:`circuitos.reports.report.context`). Equations are
rendered by Matplotlib's mathtext to images; an equation mathtext cannot read is printed as its
LaTeX source, so nothing is silently dropped. The schematic (SVG) and the waveform figures go in
as PNG. A4 portrait, with page numbers.
"""

from __future__ import annotations

import io
import re
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import pymupdf
from jinja2 import Environment, FileSystemLoader, select_autoescape
from matplotlib import mathtext
from matplotlib.font_manager import FontProperties

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)

_SIZE_CMDS = re.compile(r"\\(?:Big|big|Bigg|bigg)[lr]?")
_REPLACE = {r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\;": r"\ ", r"\!": ""}


_SQRT_BARE = re.compile(r"\\sqrt\s*([A-Za-z0-9])")
_RELATIONS = re.compile(r"\\(ge|le|ne)(?![a-zA-Z])")


def _normalise(latex: str) -> str:
    r"""Rewrite the KaTeX spellings mathtext does not accept (\ge, \sqrt2, \Big|…)."""
    s = _SIZE_CMDS.sub("", latex)
    for a, b in _REPLACE.items():
        s = s.replace(a, b)
    s = _RELATIONS.sub(lambda m: "\\" + m.group(1) + "q", s)
    s = _SQRT_BARE.sub(lambda m: "\\sqrt{" + m.group(1) + "}", s)
    return s.strip()


_EQ_DPI = 170


@lru_cache(maxsize=512)
def equation_png(latex: str, size: float = 10.0) -> bytes | None:
    """PNG of an equation, or None when mathtext cannot parse it."""
    buf = io.BytesIO()
    try:
        mathtext.math_to_image(
            f"${_normalise(latex)}$", buf, prop=FontProperties(size=size), dpi=_EQ_DPI, format="png"
        )
    except Exception:
        return None
    return buf.getvalue()


def svg_to_png(svg: str, dpi: int = 130) -> bytes:
    with pymupdf.open(stream=svg.encode("utf-8"), filetype="svg") as doc:
        return bytes(doc[0].get_pixmap(dpi=dpi, alpha=False).tobytes("png"))


_CSS = """
* { font-family: sans-serif; font-size: 9px; color: #1f2937; }
h1 { font-size: 16px; margin: 0; }
h2 { font-size: 12px; margin-top: 12px; border-bottom: 0.5px solid #9ca3af; }
h3 { font-size: 10px; margin-top: 6px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 0.5px solid #d1d5db; padding: 2px 3px; vertical-align: top; }
th { background-color: #f3f4f6; }
.muted { color: #6b7280; font-size: 8px; }
.ok { color: #15803d; } .atencao { color: #b45309; } .violado { color: #b91c1c; }
.warn { background-color: #fffbeb; padding: 3px; }
.verdict { font-weight: bold; padding: 4px; }
code { font-family: monospace; font-size: 8px; }
"""


def render_pdf(ctx: dict[str, Any]) -> bytes:
    """PDF bytes from the shared report context (built with ``figure_format="png"``)."""
    archive = pymupdf.Archive()
    images: dict[str, str] = {}

    def add(name: str, data: bytes) -> str:
        archive.add((data, name))
        images[name] = name
        return name

    def eq(latex: str, size: float = 10.0) -> str:
        png = equation_png(latex, size)
        if png is None:
            return f"<code>{_escape(latex)}</code>"
        name = add(f"eq{len(images)}.png", png)
        # PNG rendered at _EQ_DPI: place it at its true size in points (≤ the text width)
        w_px, h_px = struct.unpack(">II", png[16:24])
        w, h = w_px * 72 / _EQ_DPI, h_px * 72 / _EQ_DPI
        if w > 500:
            w, h = 500, h * 500 / w
        return f'<img src="{name}" width="{w:.1f}" height="{h:.1f}"/>'

    schematic = add("schematic.png", svg_to_png(ctx["schematic"]))
    figures = [add(f"fig{i}.png", f.data) for i, f in enumerate(ctx["figures"])]
    html = _ENV.get_template("report_pdf.html.j2").render(
        **ctx, schematic_img=schematic, figure_imgs=figures, eq=eq
    )
    story = pymupdf.Story(html=html, user_css=_CSS, archive=archive)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page = pymupdf.paper_rect("a4")
    where = pymupdf.Rect(page.x0 + 40, page.y0 + 40, page.x1 - 40, page.y1 - 48)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return _number_pages(buf.getvalue(), ctx.get("project") or ctx["title"])


def _number_pages(pdf: bytes, title: str) -> bytes:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        total = doc.page_count
        for i, page in enumerate(doc):
            r = page.rect
            page.insert_text(
                (40, r.height - 24),
                f"{title} · página {i + 1} de {total}",
                fontsize=7,
                color=(0.42, 0.45, 0.5),
            )
        return bytes(doc.tobytes(deflate=True))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = ["equation_png", "render_pdf", "svg_to_png"]
