"""Reviewing a whole category at once (button "Revisar categoria")."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from circuitos.components.repository import ComponentRepository, component_id
from tests.unit.components.test_repository import FAMILY

# Tj_max (required) cites no page: it cannot become "revisado", so the parts stay blocked.
NO_PAGE = FAMILY.replace(
    "Tj_max: {max: 150, unit: degC, status: extraido, source: {page: 1}}",
    'Tj_max: {max: 150, unit: degC, status: extraido, source: {location: "tabela 1"}}',
)
# trr is optional: without a page it is left out but does not block the release.
OPTIONAL_NO_PAGE = FAMILY.replace(
    "parameters:\n",
    "parameters:\n"
    "  trr: {max: 2, unit: us, status: extraido, conditions: {IF: 0.5 A},"
    ' source: {location: "x"}}\n',
    1,
)


def _repo(tmp_path, text: str) -> ComponentRepository:
    (tmp_path / "fam.yaml").write_text(text, encoding="utf-8")
    repo = ComponentRepository()
    assert not repo.import_directory(tmp_path).errors
    return repo


def test_dry_run_reports_without_saving(tmp_path):
    repo = _repo(tmp_path, FAMILY)
    items = repo.review_category("diode.rectifier", "Lauro", dry_run=True)
    assert [(i.part_number, i.after) for i in items] == [("XF1", "liberado"), ("XF2", "liberado")]
    assert all(i.marked == 7 and not i.blockers for i in items)
    rid = component_id("Fabricante Fictício", "XF1")
    assert repo.get(rid).review.status == "rascunho"
    assert repo.get(rid).parameters["VF"].status == "extraido"


def test_review_marks_sourced_entries_and_releases(tmp_path):
    repo = _repo(tmp_path, OPTIONAL_NO_PAGE)
    items = repo.review_category("diode.rectifier", "Lauro")
    assert all(i.after == "liberado" and i.unsourced == ["trr"] for i in items)
    rec = repo.get(component_id("Fabricante Fictício", "XF2"))
    assert rec.selectable
    assert rec.review.reviewed_by == "Lauro (revisão da categoria)"
    assert rec.parameters["VRRM"].status == "revisado"
    assert rec.parameters["trr"].status == "extraido"  # no page: left as it was


def test_required_entry_without_page_blocks_release(tmp_path):
    repo = _repo(tmp_path, NO_PAGE)
    items = repo.review_category("diode.rectifier", "Lauro")
    assert all(i.after == "em_revisao" and i.unsourced == ["Tj_max"] for i in items)
    assert all(any("Tj_max" in b for b in i.blockers) for i in items)
    rec = repo.get(component_id("Fabricante Fictício", "XF1"))
    assert not rec.selectable
    assert rec.parameters["VF"].status == "revisado"


def test_released_and_other_categories_are_left_alone(tmp_path):
    repo = _repo(tmp_path, FAMILY)
    rid = component_id("Fabricante Fictício", "XF1")
    for key in repo.get(rid).parameters:
        repo.set_parameter_status(rid, key, "revisado")
    repo.release(rid, "Ana")
    items = repo.review_category("diode.rectifier", "Lauro")
    assert [i.part_number for i in items] == ["XF2"]
    assert repo.get(rid).review.reviewed_by == "Ana"
    assert repo.review_category("diode", "Lauro") == []  # exact category only


@pytest.fixture
def client(tmp_path, monkeypatch):
    cat = tmp_path / "cat"
    cat.mkdir()
    (cat / "fam.yaml").write_text(FAMILY, encoding="utf-8")
    monkeypatch.setenv("CIRCUITOS_CATALOG_DIR", str(cat))
    monkeypatch.setenv("CIRCUITOS_DB_URL", f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    monkeypatch.setenv("CIRCUITOS_DATA_DIR", str(tmp_path / "data"))
    from circuitos.api.app import app

    with TestClient(app) as c:
        yield c


def test_api_preview_then_confirm(client):
    url = "/api/v1/components/review-category"
    preview = client.post(url, json={"category": "diode.rectifier", "dry_run": True}).json()
    assert preview["dry_run"] and preview["released"] == 2 and preview["pending"] == 0
    assert client.post(url, json={"category": "diode.rectifier"}).status_code == 422  # no name
    done = client.post(url, json={"category": "diode.rectifier", "reviewer": "Lauro"}).json()
    assert done["released"] == 2
    again = client.post(url, json={"category": "diode.rectifier", "dry_run": True}).json()
    assert again["items"] == [] and again["already_released"] == 2
    assert client.post(url, json={"category": "nada", "dry_run": True}).status_code == 404


# A second family whose required Tj_max cites no page: it must stay blocked.
OTHER_BLOCKED = (
    NO_PAGE.replace("XF1–XF2", "XG1–XG2").replace("XF1:", "XG1:").replace("XF2:", "XG2:")
)


def test_review_all_releases_whole_catalogue_but_keeps_blockers(tmp_path):
    (tmp_path / "other.yaml").write_text(OTHER_BLOCKED, encoding="utf-8")
    repo = _repo(tmp_path, FAMILY)
    rid = component_id("Fabricante Fictício", "XF1")
    for key in repo.get(rid).parameters:
        repo.set_parameter_status(rid, key, "revisado")
    repo.release(rid, "Ana")
    preview = repo.review_all("", dry_run=True)
    assert {i.part_number: i.after for i in preview} == {
        "XF2": "liberado",
        "XG1": "em_revisao",
        "XG2": "em_revisao",
    }
    assert repo.get(component_id("Fabricante Fictício", "XF2")).review.status == "rascunho"
    repo.review_all("Lauro")
    xf2 = repo.get(component_id("Fabricante Fictício", "XF2"))
    assert xf2.selectable
    assert xf2.review.reviewed_by == "Lauro (liberação de todo o catálogo)"
    assert xf2.review.reviewed_at is not None
    assert repo.get(rid).review.reviewed_by == "Ana"  # already released: untouched
    assert not repo.get(component_id("Fabricante Fictício", "XG1")).selectable


def test_api_review_all(client):
    url = "/api/v1/components/review-all"
    preview = client.post(url, json={"dry_run": True}).json()
    assert preview["dry_run"] and preview["released"] == 2 and preview["already_released"] == 0
    assert client.post(url, json={}).status_code == 422  # no name
    done = client.post(url, json={"reviewer": "Lauro"}).json()
    assert done["released"] == 2
    again = client.post(url, json={"dry_run": True}).json()
    assert again["items"] == [] and again["already_released"] == 2
