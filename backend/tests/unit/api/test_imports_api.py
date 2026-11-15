"""Import flow through the API: upload → extract → edit → commit → review → release,
then curves and SPICE models on the imported (fictitious) component."""

from __future__ import annotations

import math
import tempfile

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app
from circuitos.components.repository import ComponentRepository

from ..datasheets.synthetic import rectifier_pdf
from ..datasheets.test_digitize import CAL, PLOT, _figure, law

API = "/api/v1"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db = f"sqlite:///{tempfile.mkdtemp(prefix='circuitos-imp-')}/c.db"
        app.state.components = ComponentRepository(db)
        app.state.imports = None
        yield c


@pytest.fixture(scope="module")
def job(client):
    up = client.post(
        f"{API}/datasheets?filename=teste-d1.pdf",
        content=rectifier_pdf(),
        headers={"Content-Type": "application/pdf"},
    )
    assert up.status_code == 200, up.text
    sha = up.json()["sha256"]
    res = client.post(
        f"{API}/imports",
        json={
            "sha256": sha,
            "filename": "teste-d1.pdf",
            "meta": {"manufacturer": "Teste", "part_number": "TESTE-D1"},
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_capabilities(client):
    body = client.get(f"{API}/imports/capabilities").json()
    assert set(body) == {"ocr", "llm"}
    assert "available" in body["llm"]


def test_upload_rejects_non_pdf(client):
    res = client.post(f"{API}/datasheets", content=b"not a pdf")
    assert res.status_code == 422


def test_import_detects_category_and_candidates(client, job):
    assert job["meta"]["category"] == "diode.rectifier"
    assert job["ranking"][0]["category"] == "diode.rectifier"
    keys = {c["key"] for c in job["candidates"] if c["accepted"]}
    assert {"VRRM", "IF(AV)", "IFSM", "VF", "IR", "Tj_max"} <= keys
    text = client.get(f"{API}/datasheets/{job['sha256']}/pages/1/text").json()
    assert any("Forward voltage" in r["text"] for r in text["rows"])


def test_edit_commit_review_release(client, job):
    edited = {**job["meta"], "package": "DO-41", "document_number": "TST-001"}
    cands = job["candidates"]
    res = client.put(f"{API}/imports/{job['id']}", json={"meta": edited, "candidates": cands})
    assert res.status_code == 200 and res.json()["meta"]["package"] == "DO-41"

    assert (
        client.post(f"{API}/imports/{job['id']}/commit", json={"created_by": " "}).status_code
        == 422
    )
    res = client.post(f"{API}/imports/{job['id']}/commit", json={"created_by": "Teste"})
    assert res.status_code == 200, res.text
    detail = res.json()
    record = detail["record"]
    assert record["review"]["status"] == "em_revisao"
    assert record["datasheets"][0]["sha256"] == job["sha256"]
    vrrm = record["parameters"]["VRRM"]
    assert vrrm["status"] == "extraido" and vrrm["max"] == 800
    assert vrrm["source"]["page"] == 1 and vrrm["source"]["bbox"] is not None
    # rule 5: nothing released before review
    assert detail["release_blockers"]
    again = client.post(f"{API}/imports/{job['id']}/commit", json={"created_by": "Teste"})
    assert again.status_code == 409

    cid = record["id"]
    for key, p in record["parameters"].items():
        if p["status"] == "extraido":
            r = client.post(
                f"{API}/components/{cid}/parameters/{key}/review", json={"status": "revisado"}
            )
            assert r.status_code == 200, r.text
    rel = client.post(f"{API}/components/{cid}/release", json={"reviewer": "Teste"})
    assert rel.status_code == 200, rel.text
    assert rel.json()["record"]["review"]["status"] == "liberado"


def _component_id(client):
    rows = client.get(f"{API}/components", params={"q": "TESTE-D1"}).json()
    return rows[0]["id"]


@pytest.mark.ngspice
def test_curve_fit_and_models(client, job):
    cid = _component_id(client)
    positions = []
    for k in range(12):
        v = 0.70 + 0.02 * k
        if 1e-3 <= law(v) <= 10:
            positions.append((CAL.x.position(v), CAL.y.position(law(v))))
    body = {
        "name": "IF×VF a 25 °C",
        "x": {"quantity": "VF", "unit": "V", "scale": "lin"},
        "y": {"quantity": "IF", "unit": "A", "scale": "log"},
        "family": {"Tj": {"value": 25, "unit": "degC"}},
        "calibration": CAL.model_dump(),
        "positions": positions,
        "datasheet_id": "ds1",
        "page": 1,
        "method": "manual",
        "digitized_by": "Teste",
    }
    res = client.post(f"{API}/components/{cid}/curves", json=body)
    assert res.status_code == 200, res.text
    curve = res.json()["record"]["curves"][0]
    v0, i0 = curve["points"][0]
    assert i0 == pytest.approx(law(v0), rel=1e-6)

    fit = client.post(f"{API}/components/{cid}/spice-models/fit", json={"curve_ids": [curve["id"]]})
    assert fit.status_code == 200, fit.text
    model = fit.json()["record"]["spice_models"][-1]
    assert model["origin"] == "ajustado" and model["fit"]["simulated"]
    # synthetic law has n·Vt = 50 mV and no series resistance
    assert model["params"]["N"] * 0.025693 == pytest.approx(0.05, rel=0.02)
    assert model["fit"]["max_error_pct"] < 1

    lib = ".model DFAB D(IS=1e-12 N=1.5 RS=0.02)"
    imp = client.post(
        f"{API}/components/{cid}/spice-models/import",
        json={"text": lib, "source_note": "fabricante.lib"},
    )
    assert imp.status_code == 200, imp.text
    fab = imp.json()["record"]["spice_models"][-1]
    assert fab["origin"] == "fabricante" and fab["checked"]

    gone = client.delete(f"{API}/components/{cid}/spice-models/{fab['id']}")
    assert gone.status_code == 200
    gone = client.delete(f"{API}/components/{cid}/curves/{curve['id']}")
    assert gone.status_code == 200 and gone.json()["record"]["curves"] == []


def test_vector_paths_endpoint(client):
    doc = _figure()
    data = doc.tobytes()
    up = client.post(f"{API}/datasheets", content=data).json()
    res = client.post(
        f"{API}/datasheets/{up['sha256']}/pages/1/vector-paths", json=PLOT.model_dump()
    )
    assert res.status_code == 200
    red = [p for p in res.json() if p["colour"] == [1.0, 0.0, 0.0]]
    assert len(red) == 1 and len(red[0]["points"]) > 10
    assert math.isfinite(red[0]["bbox"][0])
