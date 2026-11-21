"""DS-CATALOGO: every catalogue value appears on the datasheet page it cites.

Downloads the official PDFs (hash-checked) and searches the cited page for the number. This
catches transcription slips (wrong page, wrong column value) before the human review. It cannot
tell which column a number came from: that remains the reviewer's job.
"""

import re
import urllib.error
from pathlib import Path

import pytest

from circuitos.components.repository import ComponentRepository
from circuitos.datasheets.store import DatasheetStore

CATALOG = Path(__file__).parents[3] / "data" / "components"
pytestmark = pytest.mark.datasheet

# ".66" (no leading zero) is common in older US tables
_NUMBER = re.compile(r"[-−–]?(?:\d+(?:[.,]\d+)?|\.\d+)")


def _numbers(text: str) -> set[float]:
    out = set()
    for token in _NUMBER.findall(text.replace(" ", "").replace("10 000", "10000")):
        if re.fullmatch(r"[-−–]?\d{1,3},\d{3}", token):
            # "1,200" in US tables is a thousands separator
            out.add(round(abs(float(token.replace(",", "").lstrip("-−–"))), 6))
        token = token.replace(",", ".").replace("−", "-").replace("–", "-")
        try:
            out.add(round(float(token), 6))
            out.add(round(abs(float(token)), 6))
        except ValueError:
            pass
    return out


def _cases():
    repo = ComponentRepository()
    repo.import_directory(CATALOG)
    for record in repo.search():
        sha = {d.id: d for d in record.datasheets}
        for key, p in record.parameters.items():
            for value in (p.min, p.typ, p.max):
                if value is not None and p.source is not None:
                    ds = sha[p.source.datasheet_id]
                    if ds.sha256 is None:
                        continue  # web page source (no PDF): see test_web_values_in_excerpt
                    yield pytest.param(
                        str(ds.url),
                        ds.sha256,
                        p.source.page,
                        value,
                        id=f"{record.part_number}-{key}-{value:g}",
                    )


@pytest.fixture(scope="module")
def store():
    return DatasheetStore()


@pytest.mark.parametrize(("url", "sha", "page", "value"), list(_cases()))
def test_value_on_cited_page(store, url, sha, page, value):
    try:
        store.fetch(url, expected_sha256=sha)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"sem acesso ao datasheet: {exc}")
    numbers = _numbers(store.page_text(sha, page))
    assert round(value, 6) in numbers or round(abs(value), 6) in numbers, (
        f"{value:g} não aparece na página {page}"
    )


def test_web_values_in_excerpt():
    """Records taken from a manufacturer web page (no PDF to hash) quote the value they cite."""
    repo = ComponentRepository()
    repo.import_directory(CATALOG)
    missing = []
    for record in repo.search():
        docs = {d.id: d for d in record.datasheets}
        for key, p in record.parameters.items():
            if p.source is None or docs[p.source.datasheet_id].sha256 is not None:
                continue
            numbers = _numbers(p.source.excerpt or "")
            for value in (p.min, p.typ, p.max):
                if value is not None and round(abs(value), 6) not in numbers:
                    missing.append(f"{record.part_number}.{key}={value:g}")
    assert not missing, missing
