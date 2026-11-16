"""Bill of materials with stresses, margins and exports (prompt, section 4.8).

The design modules produce :class:`~circuitos.reports.common.BomRow` rows (what to buy). This
module adds what the engineer needs to judge each line, all taken from the design result:

* the governing stress × rating × margin (the check with the smallest margin for that position);
* the estimated junction temperature and the heat sink;
* the datasheet link of the chosen part;
* an optional unit cost, typed by the user.

Identical lines (same part, value and description) are grouped, with their designators joined.
Exports: CSV (semicolon, UTF-8 with BOM, for spreadsheets in pt-BR), XLSX and PDF.
"""

from __future__ import annotations

import csv
import html
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

import pymupdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from circuitos.core.units import QuantityModel, format_eng
from circuitos.design.base import DesignResult, MarginCheck

from .common import BomRow

_PLACEHOLDERS = ("(a escolher)", "(a especificar)", "(sem candidato liberado)")
STATUS_LABEL = {"ok": "ok", "atencao": "atenção", "violado": "violado"}


def _fmt(q: QuantityModel | None) -> str:
    if q is None:
        return ""
    if q.unit in ("degC", "°C"):
        return f"{q.value:.3g} °C".replace(".", ",")
    try:
        return format_eng(q.to_pint())
    except Exception:
        return f"{q.value:.3g} {q.unit}".replace(".", ",")


@dataclass
class BomLine:
    designators: list[str]
    quantity: int
    description: str
    part_number: str
    manufacturer: str
    value: str
    note: str
    parameter: str = ""  # governing check, e.g. "VRRM"
    stress: str = ""
    rating: str = ""
    margin_pct: float | None = None
    margin_status: str = ""
    tj: str = ""
    tj_max: str = ""
    heatsink: str = ""
    datasheet: str | None = None
    unit_cost: float | None = None
    checks: list[str] = field(default_factory=list)  # every margin check, for the PDF/XLSX notes

    @property
    def designator(self) -> str:
        return ", ".join(self.designators)

    @property
    def cost_key(self) -> str:
        """Unspecified parts ("(a escolher)") are priced per position, real parts per code."""
        return self.designator if self.part_number in _PLACEHOLDERS else self.part_number

    @property
    def total_cost(self) -> float | None:
        return None if self.unit_cost is None else self.unit_cost * self.quantity


def _governing(checks: list[MarginCheck]) -> MarginCheck | None:
    return min(checks, key=lambda m: m.margin_pct) if checks else None


def build(
    rows: list[BomRow],
    result: DesignResult,
    datasheet_of: Callable[[UUID], str | None] | None = None,
    costs: dict[str, float] | None = None,
) -> list[BomLine]:
    """Join each BOM row with the margins, temperature and datasheet of its position."""
    margins: dict[str, list[MarginCheck]] = {}
    for m in result.margins:
        margins.setdefault(m.designator, []).append(m)
    thermal = {t.designator: t for t in result.thermal}
    chosen = {c.designator: c for c in result.selection}
    costs = costs or {}
    lines: list[BomLine] = []
    for r in rows:
        line = BomLine(
            designators=[r.designator],
            quantity=r.quantity,
            description=r.description,
            part_number=r.part_number,
            manufacturer=r.manufacturer,
            value=r.value,
            note=r.note,
        )
        line.unit_cost = costs.get(line.cost_key)
        g = _governing(margins.get(r.designator, []))
        if g is not None:
            line.parameter = g.parameter
            line.stress = _fmt(g.stress)
            line.rating = _fmt(g.rating)
            line.margin_pct = g.margin_pct
            line.margin_status = g.status
            line.checks = [
                f"{m.parameter}: {_fmt(m.stress)} / {_fmt(m.rating)} "
                f"({m.margin_pct:.0f} %, {STATUS_LABEL[m.status]})"
                for m in margins[r.designator]
            ]
        t = thermal.get(r.designator)
        if t is not None:
            line.tj = _fmt(t.Tj)
            line.tj_max = _fmt(t.Tj_max)
            line.heatsink = t.heatsink or ("nenhum" if t.path.startswith("sem") else "")
        c = chosen.get(r.designator)
        if c is not None and datasheet_of is not None:
            line.datasheet = datasheet_of(c.component_id)
        lines.append(line)
    return group(lines)


def group(lines: list[BomLine]) -> list[BomLine]:
    """Merge lines for the same part (part number, manufacturer, value, description)."""
    out: list[BomLine] = []
    index: dict[tuple[str, str, str, str], BomLine] = {}
    for line in lines:
        placeholder = line.part_number in _PLACEHOLDERS
        key = (line.part_number, line.manufacturer, line.value, line.description)
        # unspecified parts merge only when their value is also the same (it is in the key)
        if placeholder and not line.value:
            out.append(line)
            continue
        existing = index.get(key)
        if existing is None:
            index[key] = line
            out.append(line)
            continue
        existing.designators += line.designators
        existing.quantity += line.quantity
        existing.checks += line.checks
        if line.margin_pct is not None and (
            existing.margin_pct is None or line.margin_pct < existing.margin_pct
        ):
            for attr in ("parameter", "stress", "rating", "margin_pct", "margin_status"):
                setattr(existing, attr, getattr(line, attr))
        if line.note and line.note not in existing.note:
            existing.note = f"{existing.note}; {line.note}" if existing.note else line.note
    return out


HEADERS = [
    "Designador",
    "Qtd",
    "Descrição",
    "Código",
    "Fabricante",
    "Valor",
    "Parâmetro crítico",
    "Esforço",
    "Nominal",
    "Margem (%)",
    "Situação",
    "Tj estimada",
    "Tj máx.",
    "Dissipador",
    "Custo unit.",
    "Custo total",
    "Datasheet",
    "Observação",
]


def _cells(line: BomLine) -> list[object]:
    return [
        line.designator,
        line.quantity,
        line.description,
        line.part_number,
        line.manufacturer,
        line.value,
        line.parameter,
        line.stress,
        line.rating,
        None if line.margin_pct is None else round(line.margin_pct, 1),
        STATUS_LABEL.get(line.margin_status, ""),
        line.tj,
        line.tj_max,
        line.heatsink,
        line.unit_cost,
        line.total_cost,
        line.datasheet or "",
        line.note,
    ]


def _num(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    return str(v)


def to_csv(lines: list[BomLine]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(HEADERS)
    for line in lines:
        w.writerow([_num(c) for c in _cells(line)])
    total = total_cost(lines)
    if total is not None:
        w.writerow(["Total", "", "", "", "", "", "", "", "", "", "", "", "", "", "", _num(total)])
    return "﻿" + buf.getvalue()


def total_cost(lines: list[BomLine]) -> float | None:
    costs = [line.total_cost for line in lines if line.total_cost is not None]
    return sum(costs) if costs else None


_FILL = {
    "ok": PatternFill("solid", fgColor="DFF5E1"),
    "atencao": PatternFill("solid", fgColor="FFF4CE"),
    "violado": PatternFill("solid", fgColor="FDE2E1"),
}


def to_xlsx(lines: list[BomLine], title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Lista de materiais"
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(HEADERS)
    for cell in ws[2]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for line in lines:
        ws.append(_cells(line))
        row = ws.max_row
        status = line.margin_status
        if status in _FILL:
            ws.cell(row=row, column=11).fill = _FILL[status]
        if line.datasheet:
            link = ws.cell(row=row, column=17)
            link.hyperlink = line.datasheet
            link.style = "Hyperlink"
        for col in (15, 16):
            ws.cell(row=row, column=col).number_format = "#,##0.00"
    total = total_cost(lines)
    if total is not None:
        ws.append(["Total"] + [None] * 14 + [total])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=16).number_format = "#,##0.00"
    widths = [14, 5, 34, 18, 18, 14, 12, 12, 12, 9, 9, 10, 9, 18, 10, 10, 30, 40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A3"
    checks = wb.create_sheet("Verificações")
    checks.append(["Designador", "Verificação (esforço / nominal, margem, situação)"])
    for line in lines:
        for c in line.checks:
            checks.append([line.designator, c])
    checks.column_dimensions["A"].width = 16
    checks.column_dimensions["B"].width = 90
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_PDF_CSS = """
* { font-family: sans-serif; }
h1 { font-size: 14px; margin: 0 0 4px 0; }
p { font-size: 8px; color: #555; margin: 0 0 6px 0; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 0.5px solid #999; padding: 2px 3px; font-size: 7px; vertical-align: top; }
th { background-color: #e8ecf2; }
td.ok { background-color: #dff5e1; }
td.atencao { background-color: #fff4ce; }
td.violado { background-color: #fde2e1; }
"""

_PDF_COLUMNS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17]


def to_pdf(lines: list[BomLine], title: str, subtitle: str = "") -> bytes:
    """A4 landscape table; long lists continue on the next pages."""
    head = "".join(f"<th>{html.escape(HEADERS[i])}</th>" for i in _PDF_COLUMNS)
    body = []
    for line in lines:
        cells = _cells(line)
        tds = []
        for i in _PDF_COLUMNS:
            css = f' class="{line.margin_status}"' if i == 10 and line.margin_status else ""
            tds.append(f"<td{css}>{html.escape(_num(cells[i]))}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    total = total_cost(lines)
    foot = f"<p>Custo total estimado: {html.escape(_num(total))}</p>" if total is not None else ""
    doc_html = (
        f"<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>"
        f"<table><tr>{head}</tr>{''.join(body)}</table>{foot}"
    )
    story = pymupdf.Story(html=doc_html, user_css=_PDF_CSS)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page = pymupdf.paper_rect("a4-l")
    where = pymupdf.Rect(page.x0 + 28, page.y0 + 28, page.x1 - 28, page.y1 - 28)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buf.getvalue()


__all__ = ["HEADERS", "BomLine", "build", "group", "to_csv", "to_pdf", "to_xlsx", "total_cost"]
