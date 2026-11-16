"""HTML design report with calculation memory and lab guide (Jinja2)."""

from __future__ import annotations

import base64
import datetime as dt
import functools
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from circuitos.core.units import QuantityModel, format_eng
from circuitos.design.base import DesignResult, SimComparison

from . import outputs
from .bom import BomLine
from .bom import build as bom_build
from .bom import total_cost as bom_total
from .sections import FigFormat, SimWaves, operating_limits, waveform_figures

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)

_KATEX = Path(__file__).parent / "vendor" / "katex"


@functools.cache
def katex_assets() -> dict[str, str]:
    """KaTeX 0.16.11 (MIT) inlined so the report renders the equations offline.

    Only the woff2 fonts are embedded, as data URIs.
    """

    def font(match: re.Match[str]) -> str:
        name = match.group(1)
        data = base64.b64encode((_KATEX / "fonts" / f"{name}.woff2").read_bytes()).decode()
        return f'src:url(data:font/woff2;base64,{data}) format("woff2")'

    css = (_KATEX / "katex.min.css").read_text(encoding="utf-8")
    css = re.sub(r'src:url\(fonts/([\w-]+)\.woff2\) format\("woff2"\)[^;}]*', font, css)
    return {
        "css": css,
        "js": (_KATEX / "katex.min.js").read_text(encoding="utf-8"),
        "auto_render": (_KATEX / "auto-render.min.js").read_text(encoding="utf-8"),
    }


from .labels import ENUM_LABELS, HIDDEN, LABELS, SPEC_LABELS  # noqa: E402

__all__ = ["ENUM_LABELS", "HIDDEN", "LABELS", "SPEC_LABELS", "context", "katex_assets", "render"]

QUESTIONS: dict[str, list[str]] = {
    "DM-RET1": [
        "Por que a corrente no diodo com filtro capacitivo é um pulso estreito e alto? Relacione "
        "com o fator de potência medido.",
        "O que acontece com a ondulação e com a corrente de pico se C dobrar?",
        "Compare a tensão média medida com a calculada: qual parcela da diferença vem da "
        "resistência do enrolamento do transformador?",
    ],
    "DM-RETC1": [
        "Explique por que a tensão média cai com α e por que, com carga RL, ela pode ficar "
        "negativa em parte do ciclo.",
        "Em que condição a corrente se torna contínua? Confira com ωL/R da montagem.",
        "Qual o efeito do diodo de roda livre (ou da ponte semicontrolada) no fator de potência?",
    ],
    "DM-RET3": [
        "Por que a ponte de 6 pulsos tem harmônicas 6k ± 1 na corrente de linha e o arranjo de "
        "12 pulsos elimina a 5ª e a 7ª?",
        "Meça o ângulo de comutação μ nos entalhes da tensão de saída e compare com o calculado.",
        "Como a indutância da fonte reduz a tensão média? Estime ωLs a partir da queda medida.",
    ],
}


def _fmt(q: QuantityModel | None) -> str:
    if q is None:
        return "—"
    if q.unit in ("", "dimensionless"):
        return f"{q.value:.3g}".replace(".", ",")
    if q.unit in ("percent", "%"):
        return f"{q.value:.3g} %".replace(".", ",")
    if q.unit in ("deg", "degree"):
        return f"{q.value:.3g}°".replace(".", ",")
    if q.unit in ("degC", "°C"):
        return f"{q.value:.3g} °C".replace(".", ",")
    try:
        return format_eng(q.to_pint())
    except Exception:  # unusual units: plain text
        return f"{q.value:.3g} {q.unit}".replace(".", ",")


def _spec_rows(
    spec: BaseModel, spec_labels: dict[str, str], enum_labels: dict[str, str]
) -> list[tuple[str, str]]:
    rows = []
    for key, value in spec.model_dump().items():
        label = spec_labels.get(key, key)
        if isinstance(value, dict) and "value" in value:
            text = _fmt(QuantityModel(**value))
        elif isinstance(value, bool):
            text = "sim" if value else "não"
        elif isinstance(value, float):
            text = f"{value:g}".replace(".", ",")
        else:
            text = enum_labels.get(str(value), str(value).replace("_", " "))
        rows.append((label, text))
    return rows


def context(
    module: Any,
    spec: BaseModel,
    result: DesignResult,
    policy: str,
    sim: list[SimComparison] | None = None,
    waves: SimWaves | None = None,
    bom_lines: list[BomLine] | None = None,
    project: str | None = None,
    figure_format: FigFormat = "svg",
) -> dict[str, Any]:
    """Everything the HTML and the PDF report show, computed once."""
    module_id, title = module.id, module.title
    labels = outputs.labels(module)
    sim_by_key: dict[str, QuantityModel] = {}
    if sim:
        for c in sim:
            for key, q in result.summary.items():
                if q == c.analytic:
                    sim_by_key.setdefault(key, c.simulated)
    lab = [
        {
            "quantity": item.quantity,
            "instrument": item.instrument,
            "calc": _fmt(result.summary.get(item.summary_key)),
            "sim": _fmt(sim_by_key.get(item.summary_key)),
        }
        for item in outputs.lab(module)
        if item.summary_key in result.summary
    ]
    summary_rows = [
        (labels.get(k, k), _fmt(q)) for k, q in result.summary.items() if k not in HIDDEN
    ]
    alpha = result.summary.get("alpha")
    if bom_lines is None:
        bom_lines = bom_build(outputs.bom(module, spec, result), result)
    return {
        "title": title,
        "title_lower": title[0].lower() + title[1:],
        "project": project,
        "module_id": module_id,
        "generated": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "policy": policy,
        "spec_rows": _spec_rows(spec, outputs.spec_labels(module), outputs.enum_labels(module)),
        "schematic": outputs.schematic_svg(module, spec, result, title),
        "summary_rows": summary_rows,
        "summary_keys": set(result.summary),
        "warnings": result.warnings,
        "selection": result.selection,
        "margins": result.margins,
        "thermal": result.thermal,
        "limits": operating_limits(result, policy),
        "figures": waveform_figures(result, waves, figure_format),
        "bom": bom_lines,
        "bom_total": bom_total(bom_lines),
        "sim": sim,
        "steps": result.steps,
        "lab": lab,
        "safety": outputs.safety(module),
        "practice": getattr(module, "practice", None),
        "questions": QUESTIONS.get(module_id) or outputs.questions(module),
        "alpha": _fmt(alpha),
        "status": {"ok": "ok", "atencao": "atenção", "violado": "violado"},
        "fmt": _fmt,
        "num": lambda v: "" if v is None else f"{v:.2f}".replace(".", ","),
    }


def render(
    module: Any,
    spec: BaseModel,
    result: DesignResult,
    policy: str,
    sim: list[SimComparison] | None = None,
    waves: SimWaves | None = None,
    bom_lines: list[BomLine] | None = None,
    project: str | None = None,
) -> str:
    """HTML report (equations by KaTeX, inlined: works offline and prints to A4)."""
    ctx = context(module, spec, result, policy, sim, waves, bom_lines, project, "svg")
    return _ENV.get_template("report.html.j2").render(
        **ctx, katex=katex_assets(), svg=lambda b: b.decode("utf-8")
    )
