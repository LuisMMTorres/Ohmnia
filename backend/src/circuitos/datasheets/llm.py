"""Optional LLM-assisted mapping (decision D9): Claude reads the PDF and proposes parameters.

Off unless the ``anthropic`` package is installed and a credential is configured
(``ANTHROPIC_API_KEY``, ``ANTHROPIC_AUTH_TOKEN`` or an ``ant auth login`` profile). The import
screen asks for it explicitly on each import, because the PDF is sent to the Anthropic API.

Rule 1 still holds. The model must quote, for every value, the literal excerpt and the page it
came from; :func:`verify` then checks the quote against the text this program extracted from the
same page and checks that each number appears in the quote. Proposals that fail are returned as
*rejected*, with the reason, and never become candidates. The ones that pass enter like any other
candidate: ``extraido``, pending the user's review.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from circuitos.components.schema import load_schema
from circuitos.core.units import QuantityModel

from .extract import DocumentText
from .mapping import Candidate, condition_name
from .textvalues import compatible, normalise_text, unit_from_text

MODEL = "claude-opus-5-5"
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LlmStatus(BaseModel):
    available: bool
    model: str = MODEL
    reason: str | None = None


def status() -> LlmStatus:
    try:
        importlib.import_module("anthropic")
    except ImportError:
        return LlmStatus(
            available=False,
            reason="Pacote 'anthropic' não instalado (uv sync --extra llm).",
        )
    has_env = any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))
    has_profile = (Path.home() / ".config" / "anthropic").is_dir()
    if not (has_env or has_profile):
        return LlmStatus(
            available=False,
            reason="Sem credencial da API da Anthropic (ANTHROPIC_API_KEY ou 'ant auth login').",
        )
    return LlmStatus(available=True)


class LlmCondition(BaseModel):
    name: str
    value: float
    unit: str


class LlmParameter(BaseModel):
    key: str
    min: float | None = None
    typ: float | None = None
    max: float | None = None
    unit: str
    conditions: list[LlmCondition] = Field(default_factory=list)
    page: int
    excerpt: str


class Rejected(BaseModel):
    proposal: LlmParameter
    reason: str


class LlmResult(BaseModel):
    candidates: list[Candidate]
    rejected: list[Rejected]
    model: str


def _schema(keys: list[str]) -> dict[str, Any]:
    number_or_null = {"anyOf": [{"type": "number"}, {"type": "null"}]}
    item = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "enum": keys},
            "min": number_or_null,
            "typ": number_or_null,
            "max": number_or_null,
            "unit": {"type": "string"},
            "conditions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "number"},
                        "unit": {"type": "string"},
                    },
                    "required": ["name", "value", "unit"],
                    "additionalProperties": False,
                },
            },
            "page": {"type": "integer"},
            "excerpt": {"type": "string"},
        },
        "required": ["key", "min", "typ", "max", "unit", "conditions", "page", "excerpt"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"parameters": {"type": "array", "items": item}},
        "required": ["parameters"],
        "additionalProperties": False,
    }


def _prompt(category: str, part_number: str | None) -> str:
    schema = load_schema(category)
    lines = []
    for key, spec in schema.parameters.items():
        if "@" in key:
            continue
        conds = (
            f"; test conditions: {', '.join(spec.conditions_required)}"
            if spec.conditions_required
            else ""
        )
        lines.append(f"- {key} [{spec.unit}, {spec.kind}]: {spec.description}{conds}")
    part = f" Only report values that apply to part number {part_number}." if part_number else ""
    return (
        f"The attached PDF is a component datasheet. Category: {category} "
        f"({schema.description}).{part}\n\n"
        "Report the parameters below that the datasheet states explicitly. For each one give "
        "min/typ/max exactly as printed (null where the datasheet gives none), the unit as "
        "printed, the test conditions printed on the same row, the 1-based PDF page, and an "
        "excerpt copied character for character from that page, containing the number(s). "
        "Never estimate, convert, read values off a graph or fill a value from general "
        "knowledge: a parameter the document does not state must be left out. Absolute maximum "
        "ratings go in max. Symmetric ratings (±20 V) go in max as a positive number.\n\n"
        "Parameters:\n" + "\n".join(lines)
    )


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", normalise_text(text)).lower()


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in _NUM.findall(normalise_text(text))]


def verify(proposal: LlmParameter, doc: DocumentText, category: str) -> Candidate | Rejected:
    """Accept a proposal only if its quote and numbers are really on the cited page."""
    schema = load_schema(category)
    spec = schema.parameters.get(proposal.key)
    if spec is None:
        return Rejected(proposal=proposal, reason="parâmetro fora do esquema da categoria")
    values = [v for v in (proposal.min, proposal.typ, proposal.max) if v is not None]
    if not values:
        return Rejected(proposal=proposal, reason="nenhum valor informado")
    unit = unit_from_text(proposal.unit) or proposal.unit
    if not compatible(unit, spec.unit):
        return Rejected(
            proposal=proposal, reason=f"unidade {proposal.unit!r} incompatível com {spec.unit}"
        )
    try:
        page = doc.page(proposal.page)
    except Exception:
        return Rejected(proposal=proposal, reason=f"página {proposal.page} não existe no PDF")
    quote = _squash(proposal.excerpt)
    if len(quote) < 3 or quote not in _squash(page.text):
        return Rejected(proposal=proposal, reason="trecho citado não encontrado na página indicada")
    printed = _numbers(proposal.excerpt)
    for v in values:
        if not any(abs(abs(v) - p) <= 1e-9 * max(1.0, p) for p in printed):
            return Rejected(
                proposal=proposal, reason=f"o número {v:g} não aparece no trecho citado"
            )
    conditions: dict[str, QuantityModel] = {}
    for c in proposal.conditions:
        c_unit = unit_from_text(c.unit)
        if c_unit is not None:
            conditions[condition_name(c.name)] = QuantityModel(value=c.value, unit=c_unit)
    bbox = None
    head = _squash(proposal.excerpt)[:24]
    for row in page.rows:
        if head and head in _squash(row.text):
            bbox = row.bbox
            break
    notes = ["proposto pelo modelo de linguagem; trecho e números conferidos no texto do PDF"]
    if page.ocr:
        notes.append("página lida por OCR: confira dígitos e unidade")
    return Candidate(
        key=proposal.key,
        symbol=proposal.key,
        min=proposal.min,
        typ=proposal.typ,
        max=proposal.max,
        unit=unit,
        conditions=conditions,
        conditions_text="; ".join(f"{c.name} = {c.value:g} {c.unit}" for c in proposal.conditions)
        or None,
        page=proposal.page,
        bbox=bbox,
        excerpt=proposal.excerpt,
        method="llm",
        confidence=0.6 if not page.ocr else 0.45,
        notes=notes,
    )


def _client() -> Any:
    anthropic = importlib.import_module("anthropic")
    return anthropic.Anthropic()


def propose(
    pdf: bytes,
    doc: DocumentText,
    category: str,
    part_number: str | None = None,
    client: Any = None,
) -> LlmResult:
    """Ask Claude for parameters and keep only the verifiable ones."""
    schema = load_schema(category)
    keys = [k for k in schema.parameters if "@" not in k]
    client = client or _client()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=[_FALLBACK_BETA],
        fallbacks="default",
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": _schema(keys)},
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.standard_b64encode(pdf).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": _prompt(category, part_number)},
                ],
            }
        ],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("O modelo recusou a solicitação; use o mapeamento por regras.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Resposta do modelo truncada (max_tokens); tente de novo.")
    text = next(b.text for b in response.content if b.type == "text")
    raw = json.loads(text)
    candidates: list[Candidate] = []
    rejected: list[Rejected] = []
    for item in raw.get("parameters", []):
        proposal = LlmParameter.model_validate(item)
        outcome = verify(proposal, doc, category)
        (candidates if isinstance(outcome, Candidate) else rejected).append(outcome)  # type: ignore[arg-type]
    return LlmResult(candidates=candidates, rejected=rejected, model=str(response.model))


__all__ = [
    "MODEL",
    "LlmParameter",
    "LlmResult",
    "LlmStatus",
    "Rejected",
    "propose",
    "status",
    "verify",
]
