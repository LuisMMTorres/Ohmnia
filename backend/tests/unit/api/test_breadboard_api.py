"""Breadboard endpoints: spec, pinouts, automatic assembly, check and guide."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app
from tests.unit.breadboard.circuits import common_emitter, inverting


@pytest.fixture
def client(reviewed_catalogue):
    with TestClient(app) as c:
        app.state.components = reviewed_catalogue
        yield c


def _part_id(client, kind: str, part: str) -> str:
    rows = client.get("/api/v1/schematic/parts", params={"kind": kind, "text": part}).json()
    return str(next(r["id"] for r in rows if r["part_number"] == part))


def test_spec_lists_board_and_packages(client):
    spec = client.get("/api/v1/breadboard/spec").json()
    assert spec["board"]["rows"] == 63 and len(spec["board"]["rail_rows"]) == 50
    ids = {p["id"] for p in spec["packages"]}
    assert {"to-92", "dip-8", "do-41", "axial-r", "radial-elco", "alim"} <= ids


def test_resolve_shows_datasheet_source_of_the_pinout(client):
    sch = common_emitter(_part_id(client, "npn", "P2N2222A"))
    out = client.post("/api/v1/breadboard/resolve", json={"schematic": sch.model_dump()}).json()
    q = next(p for p in out["parts"] if p["ref"] == "Q1")
    assert q["origin"] == "datasheet" and q["labels"]["1"] == "COLLECTOR"
    assert q["source"]["page"] == 7 and "P2N2222A/D" in q["source"]["document"]
    r = next(p for p in out["parts"] if p["ref"] == "RC")
    assert r["bands"][:3] == ["amarelo", "violeta", "vermelho"]


def test_auto_then_check_then_guide(client):
    sch = inverting(_part_id(client, "opamp", "LM358P"))
    auto = client.post("/api/v1/breadboard/auto", json={"schematic": sch.model_dump()}).json()
    assert auto["report"]["ok"], auto["report"]
    doc = sch.model_dump()
    doc["breadboard"] = auto["breadboard"]
    report = client.post("/api/v1/breadboard/check", json={"schematic": doc}).json()
    assert report["ok"] and report["checked_parts"] == 6  # with the implicit supply
    steps = client.post("/api/v1/breadboard/guide", json={"schematic": doc}).json()
    assert any("canaleta" in s["text"] and "U1" in s["text"] for s in steps)
    # the assembly travels inside the schematic document (both views are one circuit)
    doc["breadboard"]["parts"][0]["legs"] = {}
    report = client.post("/api/v1/breadboard/check", json={"schematic": doc}).json()
    assert not report["ok"]


def test_check_needs_an_assembly(client):
    sch = common_emitter()
    r = client.post("/api/v1/breadboard/check", json={"schematic": sch.model_dump()})
    assert r.status_code == 422 and "montado" in r.json()["detail"]


def test_invalid_hole_is_rejected(client):
    doc = common_emitter().model_dump()
    doc["breadboard"] = {"parts": [{"ref": "R1", "package": "axial-r", "legs": {"1": "z9"}}]}
    r = client.post("/api/v1/breadboard/check", json={"schematic": doc})
    assert r.status_code == 422 and "Furo inexistente" in r.text
