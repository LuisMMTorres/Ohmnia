"""DS-EXT: the rule-based import measured against the hand-transcribed catalogue.

For every catalogue record with a datasheet (URL + SHA-256), the PDF is fetched (marker
``datasheet``: network, run with ``pytest -m datasheet``), mapped by the rules with the part
number, and compared parameter by parameter with the catalogue values (``evaluate.compare``).

What is asserted is the property that matters for safety, not the coverage: among the values the
mapper *accepts* for a parameter the catalogue has, wrong ones must be rare. Missing values only
cost the user typing; wrong ones cost a careful review. The totals are printed for
``docs/validacao/importacao-datasheets.md``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from circuitos.components.repository import load_records_file
from circuitos.core.errors import DataIntegrityError
from circuitos.datasheets.evaluate import compare
from circuitos.datasheets.extract import extract_path
from circuitos.datasheets.mapping import map_document
from circuitos.datasheets.store import DatasheetStore

pytestmark = pytest.mark.datasheet

CATALOGUE = Path(__file__).resolve().parents[3] / "data" / "components"
MAX_WRONG_SHARE = 0.10  # of the values found


def test_ds_ext_rules_against_catalogue(capsys: pytest.CaptureFixture[str]) -> None:
    store = DatasheetStore()
    totals: Counter[str] = Counter()
    wrong: list[str] = []
    skipped: list[str] = []
    for path in sorted(CATALOGUE.rglob("*.yaml")):
        try:
            records = load_records_file(path)
        except Exception:
            continue
        for rec in records:
            ds = next((d for d in rec.datasheets if d.url and d.sha256), None)
            if ds is None or ds.sha256 is None:
                continue
            try:
                store.fetch(str(ds.url), expected_sha256=ds.sha256)
            except (DataIntegrityError, OSError) as exc:
                skipped.append(f"{rec.part_number}: {exc}")
                continue
            doc = extract_path(store.path(ds.sha256))
            rows = compare(rec, map_document(doc, rec.category, rec.part_number))
            totals.update(r.outcome for r in rows)
            wrong += [
                f"{rec.part_number} {r.key}: catálogo {r.catalogue}, extraído {r.extracted} "
                f"(p. {r.page_extracted})"
                for r in rows
                if r.outcome == "diferente"
            ]
    with capsys.disabled():
        print(f"\nDS-EXT: {dict(totals)}; {len(skipped)} datasheet(s) indisponível(is)")
        for line in wrong:
            print("  ", line)
    found = totals["igual"] + totals["diferente"]
    assert found > 0
    assert totals["diferente"] / found <= MAX_WRONG_SHARE
