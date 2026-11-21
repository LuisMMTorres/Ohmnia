"""Projects: save, open, revise, restore, duplicate, export and import (prompt, section 4.9)."""

from __future__ import annotations

import json
import tempfile

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app
from circuitos.components.repository import ComponentRepository

API = "/api/v1/projects"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        app.state.components = ComponentRepository(
            f"sqlite:///{tempfile.mkdtemp(prefix='circuitos-prj-')}/c.db"
        )
        app.state.projects = None
        yield c


def _create(client, name="Fonte 12 V", spec=None):
    body = {"name": name, "module_id": "DM-RET1", "spec": spec or {"filter": "C"}}
    r = client.post(API, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_stores_the_full_validated_spec(client):
    doc = _create(client)
    assert doc["format"] == "circuitos-projeto" and doc["format_version"] == 1
    assert doc["current"]["number"] == 1
    # defaults are filled in, so the project reopens exactly as designed
    assert doc["current"]["spec"]["filter"] == "C" and "Vsec" in doc["current"]["spec"]


def test_edited_circuit_is_saved_duplicated_and_restored_without_changing_original(client):
    from circuitos.schematic.model import Component, Schematic

    original = _create(client, "Circuit original")
    circuit = Schematic(
        components=[Component(id="r1", ref="R1", kind="resistor", x=0, y=0)],
        bench_scope_channels=4,
        bench_scope_connections={"1": {"positive": "2:a12", "negative": "vn1"}},
    )
    saved = client.post(
        API,
        json={
            "name": "Edited copy",
            "module_id": original["module_id"],
            "spec": original["current"]["spec"],
            "schematic": circuit.model_dump(mode="json"),
        },
    ).json()
    assert saved["id"] != original["id"]
    assert saved["current"]["schematic"]["bench_scope_channels"] == 4
    assert saved["current"]["schematic"]["bench_scope_connections"]["1"] == {
        "positive": "2:a12",
        "negative": "vn1",
    }
    assert client.get(f"{API}/{original['id']}").json()["current"]["schematic"] is None
    content = {
        "spec": saved["current"]["spec"],
        "schematic": {**saved["current"]["schematic"], "components": []},
    }
    revised = client.put(f"{API}/{saved['id']}", json=content).json()
    assert revised["current"]["number"] == 2
    assert revised["current"]["schematic"]["components"] == []
    restored = client.post(f"{API}/{saved['id']}/restore/1").json()
    assert restored["current"]["schematic"]["components"][0]["ref"] == "R1"
    duplicate = client.post(f"{API}/{saved['id']}/duplicate", json={}).json()
    assert duplicate["current"]["schematic"] == restored["current"]["schematic"]


def test_invalid_spec_or_module_is_rejected(client):
    r = client.post(API, json={"name": "x", "module_id": "DM-RET1", "spec": {"filter": "nada"}})
    assert r.status_code == 422
    r = client.post(API, json={"name": "x", "module_id": "DM-NADA", "spec": {}})
    assert r.status_code == 404


def test_save_revises_only_when_the_input_changes(client):
    doc = _create(client, "Revisões")
    pid = doc["id"]
    same = client.put(f"{API}/{pid}", json={"spec": doc["current"]["spec"], "name": "Revisões A"})
    assert same.json()["current"]["number"] == 1 and same.json()["name"] == "Revisões A"
    spec2 = {**doc["current"]["spec"], "filter": "LC"}
    r2 = client.put(f"{API}/{pid}", json={"spec": spec2, "note": "filtro LC"}).json()
    assert r2["current"]["number"] == 2 and len(r2["history"]) == 1
    restored = client.post(f"{API}/{pid}/restore/1").json()
    assert restored["current"]["number"] == 3
    assert restored["current"]["spec"]["filter"] == "C"
    assert "restaurada" in restored["current"]["note"]
    assert client.post(f"{API}/{pid}/restore/9").status_code == 404


def test_duplicate_list_delete(client):
    doc = _create(client, "Original")
    dup = client.post(f"{API}/{doc['id']}/duplicate", json={}).json()
    assert dup["id"] != doc["id"] and dup["name"] == "Original (cópia)"
    assert dup["current"]["spec"] == doc["current"]["spec"]
    names = [p["name"] for p in client.get(API).json()]
    assert "Original" in names and "Original (cópia)" in names
    assert client.delete(f"{API}/{dup['id']}").status_code == 200
    assert client.get(f"{API}/{dup['id']}").status_code == 404


def test_export_and_import_round_trip(client):
    doc = _create(client, "Exportável")
    r = client.get(f"{API}/{doc['id']}/file")
    assert r.status_code == 200
    disposition = r.headers["content-disposition"]
    assert 'filename="Exportavel.circuito.json"' in disposition
    assert "filename*=UTF-8''Export%C3%A1vel.circuito.json" in disposition
    data = json.loads(r.content)
    # same id already here: imported as a new project, never overwritten
    imp = client.post(f"{API}/import", content=json.dumps(data)).json()
    assert imp["id"] != doc["id"] and imp["name"].endswith("(importado)")
    assert imp["current"]["spec"] == doc["current"]["spec"]
    bad = client.post(f"{API}/import", content=json.dumps({**data, "format_version": 99}))
    assert bad.status_code == 422
    assert client.post(f"{API}/import", content=b"not json").status_code == 422


def test_opened_project_designs_again(client):
    doc = _create(client, "Reabrir")
    cur = client.get(f"{API}/{doc['id']}").json()["current"]
    r = client.post("/api/v1/design/DM-RET1", json={"spec": cur["spec"], "policy": cur["policy"]})
    assert r.status_code == 200
