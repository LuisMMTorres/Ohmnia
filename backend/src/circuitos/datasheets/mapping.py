"""Rule-based mapping of datasheet rows to the parameters of a category schema.

For each visual row (``extract.Row``) the mapper looks for a parameter symbol (or, failing that, a
descriptive phrase), then reads the numbers to its right:

* ``NAME = value unit`` pairs are test conditions (``IF = 1.0 A``, ``TA = 25 °C``);
* the remaining numbers are the value. Their position (min/typ/max) comes from the table header
  when one was seen on the page ("Min Typ Max"), from the part's own column in family tables
  ("1N4001 … 1N4007"), or from the parameter kind (an absolute maximum rating is a ``max``);
* the unit must have the dimension the schema expects, otherwise the row is ignored.

The result is a list of *candidates*, never parameters: each one carries page, bounding box and
the literal row text, and enters the catalogue as ``extraido`` only after the user accepts it on
the import screen. Notes explain every inference the reviewer must check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from circuitos.components.schema import (
    CategorySchema,
    ParameterSpec,
    available_categories,
    load_schema,
)
from circuitos.core.units import QuantityModel

from .extract import Bbox, DocumentText, Row, Word, union
from .textvalues import compatible, normalise_text, number_with_unit, parse_range, unit_from_text

Method = Literal["regras", "llm", "manual"]
Position = Literal["min", "typ", "max"]

_ALIASES_FILE = Path(__file__).with_name("aliases.yaml")
_GREEK = str.maketrans({"θ": "th", "Θ": "th", "ϑ": "th", "ψ": "psi", "Ψ": "psi", "²": "2"})


class Candidate(BaseModel):
    """A value proposed for one parameter, with its origin in the PDF."""

    key: str
    symbol: str
    min: float | None = None
    typ: float | None = None
    max: float | None = None
    unit: str
    conditions: dict[str, QuantityModel] = Field(default_factory=dict)
    conditions_text: str | None = None
    page: int = Field(ge=1)
    bbox: Bbox | None = None
    excerpt: str
    method: Method = "regras"
    confidence: float = Field(default=0.5, ge=0, le=1)
    notes: list[str] = Field(default_factory=list)
    accepted: bool = False

    @property
    def has_value(self) -> bool:
        return any(v is not None for v in (self.min, self.typ, self.max))


# ------------------------------------------------------------------------------------ aliases --


def normalise_symbol(text: str) -> str:
    return re.sub(r"\s+", "", normalise_text(text).translate(_GREEK)).lower()


def _normalise_phrase(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s/-]", " ", normalise_text(text).lower()).split())


@dataclass(frozen=True)
class AliasSpec:
    aliases: tuple[str, ...]  # normalised
    phrases: tuple[str, ...]  # normalised
    range: Literal["upper", "lower"] | None


@cache
def _alias_table() -> dict[str, dict[str, object]]:
    data = yaml.safe_load(_ALIASES_FILE.read_text(encoding="utf-8")) or {}
    return {str(k): dict(v) for k, v in data.items()}


def alias_spec(symbol: str) -> AliasSpec:
    entry = _alias_table().get(symbol, {})
    names: list[str] = []
    # Composed names ("Tj_max", "Rth_ja") are not printed as such; plain symbols are.
    if "_" not in symbol and "@" not in symbol:
        names.append(symbol)
    raw_aliases = entry.get("aliases") or []
    raw_phrases = entry.get("phrases") or []
    if isinstance(raw_aliases, list):
        names.extend(str(a) for a in raw_aliases)
    phrases = [str(p) for p in raw_phrases] if isinstance(raw_phrases, list) else []
    rng = entry.get("range")
    return AliasSpec(
        aliases=tuple(dict.fromkeys(normalise_symbol(n) for n in names)),
        phrases=tuple(_normalise_phrase(p) for p in phrases),
        range="upper" if rng == "upper" else "lower" if rng == "lower" else None,
    )


# -------------------------------------------------------------------------------- conditions --

_CONDITION_NAMES = {
    "ta": "TA",
    "tamb": "TA",
    "tj": "Tj",
    "tvj": "Tj",
    "tc": "TC",
    "tcase": "TC",
    "tl": "TL",
    "tlead": "TL",
    "t": "t_pulse",
    "tp": "t_pulse",
    "tw": "t_pulse",
}


def condition_name(text: str) -> str:
    raw = normalise_text(text).strip().rstrip(":")
    return _CONDITION_NAMES.get(raw.lower().replace(" ", ""), raw.replace(" ", ""))


@dataclass
class _Parsed:
    numbers: list[tuple[float, str | None, Word, bool]]  # value, unit, word, symmetric
    units: list[tuple[str, Word]]  # standalone unit words
    conditions: dict[str, QuantityModel]
    conditions_text: list[str]


def _merge_subscripts(words: list[Word]) -> list[Word]:
    """Join a one-letter quantity with its subscript ("T" "J" → "TJ", "V" "R" → "VR")."""
    out: list[Word] = []
    for w in words:
        if (
            out
            and len(out[-1].text) == 1
            and out[-1].text.isalpha()
            and out[-1].text.isupper()
            and w.text[:1].isalpha()
            and w.x0 - out[-1].x1 < 0.6 * max(out[-1].height, 1.0)
        ):
            prev = out.pop()
            out.append(
                Word(prev.text + w.text, prev.x0, min(prev.y0, w.y0), w.x1, max(prev.y1, w.y1))
            )
        else:
            out.append(w)
    return out


def _parse_tail(words: list[Word]) -> _Parsed:
    """Split the words right of a symbol into conditions, numbers and unit words."""
    words = _merge_subscripts(words)
    out = _Parsed([], [], {}, [])
    i = 0
    while i < len(words):
        w = words[i]
        text = w.text.rstrip(",;")
        # "IF = 1.0 A", "IF= 1A", "IF =1A", "IF=1A"
        if "=" in text and not text.startswith("="):
            name, _, rest = text.partition("=")
            consumed, value = _condition_value(rest, words[i + 1 : i + 3])
            if name and value is not None:
                out.conditions[condition_name(name)] = value
                out.conditions_text.append(" ".join(x.text for x in words[i : i + 1 + consumed]))
                i += 1 + consumed
                continue
        if i + 1 < len(words) and words[i + 1].text.startswith("=") and _looks_like_name(text):
            rest = words[i + 1].text[1:]
            consumed, value = _condition_value(rest, words[i + 2 : i + 4])
            if value is not None:
                out.conditions[condition_name(text)] = value
                out.conditions_text.append(" ".join(x.text for x in words[i : i + 2 + consumed]))
                i += 2 + consumed
                continue
        token = number_with_unit(text)
        if token is not None:
            unit = token.unit
            if unit is None and i + 1 < len(words):
                follow = unit_from_text(words[i + 1].text)
                if follow is not None:
                    unit = follow
                    out.numbers.append((token.value, unit, w, token.symmetric))
                    out.units.append((follow, words[i + 1]))
                    i += 2
                    continue
            out.numbers.append((token.value, unit, w, token.symmetric))
            i += 1
            continue
        unit = unit_from_text(text)
        if unit is not None:
            out.units.append((unit, w))
        i += 1
    return out


def _looks_like_name(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-zθ][\w()θ,]{0,10}", text))


def _condition_value(rest: str, following: list[Word]) -> tuple[int, QuantityModel | None]:
    """Value of a condition after "=": in the same token, or in the next one or two."""
    texts = [rest] if rest else []
    texts += [w.text.rstrip(",;") for w in following]
    joined_first = " ".join(texts[:2])
    for candidate, used in ((texts[0] if texts else "", 1), (joined_first, 2)):
        token = number_with_unit(candidate)
        if token is not None and token.unit is not None:
            consumed = used - (1 if rest else 0)
            return max(consumed, 0), QuantityModel(value=token.value, unit=token.unit)
    return 0, None


# ---------------------------------------------------------------------------- table context --


@dataclass
class _Header:
    columns: dict[Position, float]  # x centre of the Min/Typ/Max headings
    unit_x: float | None
    part_x: float | None


_HEAD = {"min": "min", "min.": "min", "typ": "typ", "typ.": "typ", "max": "max", "max.": "max"}
_UNIT_HEAD = {"unit", "units", "unid.", "unidade", "dim.", "unit."}


def _header_of(row: Row, part: str | None) -> _Header | None:
    cols: dict[Position, float] = {}
    unit_x = None
    part_x = None
    for w in row.words:
        key = w.text.lower().strip("()")
        if key in _HEAD:
            cols[_HEAD[key]] = (w.x0 + w.x1) / 2  # type: ignore[index]
        elif key in _UNIT_HEAD:
            unit_x = (w.x0 + w.x1) / 2
        elif part and normalise_symbol(w.text) == normalise_symbol(part):
            part_x = (w.x0 + w.x1) / 2
    if len(cols) >= 2 or part_x is not None:
        return _Header(cols, unit_x, part_x)
    return None


# --------------------------------------------------------------------------------- matching --


@dataclass
class _Match:
    key: str
    words: list[Word]  # the symbol words (or the row's first words for a phrase)
    by_phrase: bool


def _symbol_matches(row: Row, lookup: dict[str, list[str]]) -> list[_Match]:
    words = row.words
    found: list[_Match] = []
    taken: set[str] = set()
    for start in range(len(words)):
        for length in (4, 3, 2, 1):
            span = words[start : start + length]
            if len(span) < length:
                continue
            nxt = words[start + length].text if start + length < len(words) else ""
            if nxt.startswith("="):
                continue  # a test condition, not the parameter
            joined = normalise_symbol("".join(w.text for w in span)).rstrip("*:,")
            for key in lookup.get(joined, []):
                if key not in taken:
                    found.append(_Match(key, span, by_phrase=False))
                    taken.add(key)
    return found


def _phrase_matches(row: Row, phrases: dict[str, list[str]]) -> list[_Match]:
    text = _normalise_phrase(row.text)
    found = []
    for phrase, keys in phrases.items():
        if phrase and phrase in text:
            n = len(phrase.split())
            for key in keys:
                found.append(_Match(key, row.words[: max(1, min(n, len(row.words)))], True))
    # longest phrase wins for a key
    best: dict[str, _Match] = {}
    for m in found:
        if m.key not in best or len(m.words) > len(best[m.key].words):
            best[m.key] = m
    return list(best.values())


@dataclass
class _Lookup:
    by_alias: dict[str, list[str]]
    by_phrase: dict[str, list[str]]
    specs: dict[str, AliasSpec]


def _build_lookup(schema: CategorySchema) -> _Lookup:
    by_alias: dict[str, list[str]] = {}
    by_phrase: dict[str, list[str]] = {}
    specs: dict[str, AliasSpec] = {}
    for key in schema.parameters:
        if "@" in key:
            continue
        spec = alias_spec(key)
        specs[key] = spec
        for alias in spec.aliases:
            by_alias.setdefault(alias, []).append(key)
        for phrase in spec.phrases:
            by_phrase.setdefault(phrase, []).append(key)
    return _Lookup(by_alias, by_phrase, specs)


# ---------------------------------------------------------------------------- value placing --


def _nearest(x: float, columns: dict[Position, float]) -> Position:
    return min(columns, key=lambda c: abs(columns[c] - x))


def _place(
    key: str,
    spec: ParameterSpec,
    alias: AliasSpec,
    numbers: list[tuple[float, str | None, Word, bool]],
    tail_text: str,
    header: _Header | None,
) -> tuple[dict[Position, float], list[Word], list[str], float] | None:
    """Decide min/typ/max. Returns values, the words used, notes and a confidence."""
    notes: list[str] = []
    if not numbers:
        return None
    if alias.range is not None:
        rng = parse_range(tail_text)
        if rng is not None:
            lo, hi = rng
            words = [n[2] for n in numbers[:3]]
            if alias.range == "upper":
                return {"max": hi}, words, ["limite superior da faixa"], 0.8
            return {"min": lo}, words, ["limite inferior da faixa"], 0.8
    if header is not None and header.part_x is not None:
        part_x = header.part_x
        value, _, word, _ = min(numbers, key=lambda n: abs((n[2].x0 + n[2].x1) / 2 - part_x))
        notes.append("valor lido na coluna do part number (tabela de família), como máximo")
        return {"max": abs(value)}, [word], notes, 0.75
    if header is not None and header.columns:
        placed: dict[Position, float] = {}
        words = []
        for value, _, word, _ in numbers:
            column = _nearest((word.x0 + word.x1) / 2, header.columns)
            if column not in placed:
                placed[column] = value
                words.append(word)
        return placed, words, ["posição pelas colunas Mín./Típ./Máx. do cabeçalho"], 0.8
    symmetric = numbers[0][3]
    if symmetric:
        notes.append("valor com ± no datasheet: guardado em módulo como máximo")
    if spec.kind in ("max_rating", "thermal") or len(numbers) == 1:
        if spec.kind == "characteristic":
            notes.append("sem cabeçalho Mín./Típ./Máx.: valor único tomado como máximo, confira")
            return {"max": numbers[0][0]}, [numbers[0][2]], notes, 0.45
        return {"max": abs(numbers[0][0])}, [numbers[0][2]], notes, 0.7
    values = [n[0] for n in numbers[:3]]
    words = [n[2] for n in numbers[:3]]
    notes.append("sem cabeçalho Mín./Típ./Máx.: posição inferida pela ordem dos números, confira")
    if len(values) == 2:
        a, b = values
        if a <= b:
            return {"min": a, "max": b}, words, notes, 0.35
        return {"typ": b, "max": a}, words, notes, 0.3
    a, b, c = values
    if a <= b <= c:
        return {"min": a, "typ": b, "max": c}, words, notes, 0.4
    return {"max": values[0]}, words[:1], notes, 0.25


def _unit_for(
    spec: ParameterSpec,
    numbers: list[tuple[float, str | None, Word, bool]],
    units: list[tuple[str, Word]],
    header: _Header | None,
) -> tuple[str | None, Word | None]:
    for _, unit, _word, _ in numbers:
        if unit is not None and compatible(unit, spec.unit):
            return unit, None
    if header is not None and header.unit_x is not None and units:
        unit_x = header.unit_x
        unit, word = min(units, key=lambda u: abs((u[1].x0 + u[1].x1) / 2 - unit_x))
        if compatible(unit, spec.unit):
            return unit, word
    for unit, word in reversed(units):
        if compatible(unit, spec.unit):
            return unit, word
    # Celsius written as "°C" next to a range is handled by unit_from_text; "C" alone is coulomb
    return None, None


# -------------------------------------------------------------------------------------- API --


def map_document(
    doc: DocumentText, category: str, part_number: str | None = None
) -> list[Candidate]:
    """Candidates for every parameter of ``category`` found in the document."""
    schema = load_schema(category)
    lookup = _build_lookup(schema)
    candidates: list[Candidate] = []
    for page in doc.pages:
        header: _Header | None = None
        for row in page.rows:
            new_header = _header_of(row, part_number)
            if new_header is not None:
                header = new_header
                continue
            matches = _symbol_matches(row, lookup.by_alias) or _phrase_matches(
                row, lookup.by_phrase
            )
            for match in matches:
                cand = _candidate(row, match, schema, lookup, header, page.ocr)
                if cand is not None:
                    candidates.append(cand)
    return _rank(candidates)


def _candidate(
    row: Row,
    match: _Match,
    schema: CategorySchema,
    lookup: _Lookup,
    header: _Header | None,
    ocr: bool,
) -> Candidate | None:
    spec = schema.parameters[match.key]
    alias = lookup.specs[match.key]
    right = match.words[-1].x1
    tail = [w for w in row.words if w.x0 >= right - 0.5 and w not in match.words]
    parsed = _parse_tail(tail)
    numbers = [n for n in parsed.numbers if n[1] is None or compatible(n[1], spec.unit)]
    if not numbers:
        return None
    unit, unit_word = _unit_for(spec, numbers, parsed.units, header)
    notes: list[str] = []
    confidence_penalty = 0.0
    if unit is None:
        if spec.unit == "degC" and any(n[1] is None for n in numbers):
            unit = "degC"
            notes.append("unidade não lida na linha; assumida °C pela categoria, confira")
        else:
            return None  # no unit of the right dimension: probably not this parameter
    placed = _place(match.key, spec, alias, numbers, " ".join(w.text for w in tail), header)
    if placed is None:
        return None
    values, value_words, place_notes, confidence = placed
    notes.extend(place_notes)
    if match.by_phrase:
        notes.append("encontrado pela descrição do parâmetro, sem o símbolo")
        confidence_penalty += 0.15
    if ocr:
        notes.append("página lida por OCR: confira dígitos e unidade")
        confidence_penalty += 0.15
    for name in spec.conditions_required:
        if not any(o in parsed.conditions for o in name.split("|")):
            notes.append(f"condição de teste {name.replace('|', ' ou ')} não encontrada na linha")
    used = list(match.words) + value_words + ([unit_word] if unit_word else [])
    return Candidate(
        key=match.key,
        symbol=match.key,
        min=values.get("min"),
        typ=values.get("typ"),
        max=values.get("max"),
        unit=unit,
        conditions=parsed.conditions,
        conditions_text="; ".join(parsed.conditions_text) or None,
        page=row.page,
        bbox=union(used),
        excerpt=row.text,
        method="regras",
        confidence=round(max(0.05, confidence - confidence_penalty), 2),
        notes=notes,
    )


def _rank(candidates: list[Candidate]) -> list[Candidate]:
    """Order by key, best first; the best candidate of each key starts accepted."""
    best: dict[str, Candidate] = {}
    for c in candidates:
        if c.key not in best or c.confidence > best[c.key].confidence:
            best[c.key] = c
    ranked = sorted(candidates, key=lambda c: (c.key, -c.confidence, c.page))
    return [c.model_copy(update={"accepted": c is best[c.key]}) for c in ranked]


# ----------------------------------------------------------------------------- categories --

_KEYWORDS = {
    "diode.rectifier": ["rectifier", "general purpose"],
    "diode.fast": ["fast recovery", "ultrafast", "ultra fast", "fast switching"],
    "diode.schottky": ["schottky"],
    "diode.signal": ["switching diode", "small signal"],
    "diode.zener": ["zener"],
    "bridge.single_phase": ["bridge rectifier", "bridge"],
    "bjt.npn": ["npn"],
    "bjt.pnp": ["pnp"],
    "mosfet.n": ["mosfet", "n-channel", "power mosfet", "hexfet"],
    "jfet.n": ["jfet", "junction field"],
    "igbt.n": ["igbt", "insulated gate bipolar"],
    "thyristor.scr": ["scr", "silicon controlled", "thyristor"],
    "thyristor.triac": ["triac"],
    "thyristor.diac": ["diac", "trigger diode"],
    "opamp": ["operational amplifier", "op amp", "op-amp"],
    "comparator": ["comparator"],
    "regulator.positive": ["positive voltage regulator", "voltage regulator", "ldo", "low dropout"],
    "regulator.negative": ["negative voltage regulator"],
    "timer": ["timer", "555"],
    "gate_driver": ["gate driver", "high and low side driver", "half-bridge driver"],
}


class CategoryScore(BaseModel):
    category: str
    score: float
    found: list[str]


def rank_categories(doc: DocumentText, limit: int = 5) -> list[CategoryScore]:
    """Categories ordered by how many of their parameters (and keywords) the document shows."""
    first_pages = " ".join(_normalise_phrase(p.text) for p in doc.pages[:2])
    scores: list[CategoryScore] = []
    for category in available_categories():
        schema = load_schema(category)
        if any(spec.kind == "geometry" for spec in schema.parameters.values()):
            continue  # heatsinks, cores: not imported from a component datasheet
        lookup = _build_lookup(schema)
        found: set[str] = set()
        for row in doc.rows:
            for m in _symbol_matches(row, lookup.by_alias):
                found.add(m.key)
        required = set(schema.required)
        score = sum(2.0 if k in required else 0.5 for k in found) / max(len(required), 1)
        score += sum(3.0 for kw in _KEYWORDS.get(category, []) if kw in first_pages)
        scores.append(CategoryScore(category=category, score=round(score, 2), found=sorted(found)))
    scores.sort(key=lambda s: -s.score)
    return scores[:limit]


__all__ = [
    "AliasSpec",
    "Candidate",
    "CategoryScore",
    "alias_spec",
    "condition_name",
    "map_document",
    "normalise_symbol",
    "rank_categories",
]
