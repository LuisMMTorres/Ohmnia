"""Design API: modules, design run, locks, simulation, schematic, BOM and report."""

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app


@pytest.fixture(scope="module")
def client(reviewed_catalogue):
    with TestClient(app) as c:
        app.state.components = reviewed_catalogue
        yield c


def test_modules_lists_the_rectifiers(client):
    body = client.get("/api/v1/design/modules").json()
    ids = {m["id"] for m in body}
    assert {"DM-RET1", "DM-RETC1", "DM-RET3"} <= ids
    ret1 = next(m for m in body if m["id"] == "DM-RET1")
    assert ret1["defaults"]["Vo"] == {"value": 12.0, "unit": "V"}
    assert "properties" in ret1["json_schema"]


def test_design_returns_result_circuit_and_options(client):
    r = client.post("/api/v1/design/DM-RET1", json={"spec": {"topology": "ponte", "filter": "C"}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["summary"]["Vo"]["unit"] == "V"
    assert body["result"]["steps"], "calculation memory must not be empty"
    assert body["result"]["traces"]
    assert ".tran" in body["netlist"]
    opts = body["options"]["D1–D4"]
    assert opts and all({"id", "part_number", "released"} <= set(o) for o in opts)
    chosen = {c["designator"]: c for c in body["result"]["selection"]}
    assert chosen["D1–D4"]["released"]


def test_lock_forces_the_part(client):
    body = client.post("/api/v1/design/DM-RET1", json={"spec": {}}).json()
    chosen = next(c for c in body["result"]["selection"] if c["designator"] == "D1–D4")
    other = next(
        o for o in body["options"]["D1–D4"] if o["id"] != chosen["component_id"] and o["released"]
    )
    locked = client.post(
        "/api/v1/design/DM-RET1", json={"spec": {}, "locks": {"D1–D4": other["id"]}}
    ).json()
    sel = next(c for c in locked["result"]["selection"] if c["designator"] == "D1–D4")
    assert sel["component_id"] == other["id"]
    assert sel["locked"]


def test_invalid_spec_is_422_with_message(client):
    r = client.post(
        "/api/v1/design/DM-RET1", json={"spec": {"topology": "meia_onda", "filter": "LC"}}
    )
    assert r.status_code == 422
    assert "onda completa" in r.json()["detail"]


def test_unknown_module_is_404(client):
    assert client.post("/api/v1/design/DM-XYZ", json={}).status_code == 404


@pytest.mark.ngspice
def test_simulate_agrees_with_the_analysis(client):
    r = client.post("/api/v1/design/DM-RETC1/simulate", json={"spec": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"], body["comparisons"]
    assert len(body["t_ms"]) == len(next(iter(body["traces"].values()))["values"])


def test_schematic_svg(client):
    r = client.post("/api/v1/design/DM-RET3/schematic.svg", json={"spec": {"pulses": 12}})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in r.text and "T12" in r.text


def test_bom_csv(client):
    r = client.post("/api/v1/design/DM-RET1/bom.csv", json={"spec": {"filter": "pi"}})
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("Designador;Qtd")
    assert any(line.startswith("L1;") for line in lines)
    assert any(line.startswith("TR1;") for line in lines)


def test_report_html_without_simulation(client):
    r = client.post("/api/v1/design/DM-RETC1/report.html?simulate=false", json={"spec": {}})
    assert r.status_code == 200
    html = r.text
    for section in ("1. Especificação", "Memória de cálculo", "Roteiro de prática"):
        assert section in html
    assert "renderMathInElement" in html  # KaTeX inlined, works offline
    assert "Conferência com a simulação" not in html


PHASE4 = [
    "DM-ZEN",
    "DM-LIN",
    "DM-BIAS",
    "DM-SSA",
    "DM-DIFF",
    "DM-PA",
    "DM-PAD",
    "DM-CHAVE",
    "DM-FORMA",
]


def test_modules_list_phase4_with_labels(client):
    body = {m["id"]: m for m in client.get("/api/v1/design/modules").json()}
    for mid in PHASE4:
        assert mid in body
        assert body[mid]["summary_labels"], mid


@pytest.mark.parametrize("mid", PHASE4)
def test_phase4_design_schematic_bom_report(client, mid):
    r = client.post(f"/api/v1/design/{mid}", json={"spec": {}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["selection"]
    assert body["result"]["steps"]
    svg = client.post(f"/api/v1/design/{mid}/schematic.svg", json={"spec": {}})
    assert svg.status_code == 200 and "<svg" in svg.text
    bom = client.post(f"/api/v1/design/{mid}/bom.csv", json={"spec": {}})
    assert bom.status_code == 200
    assert len(bom.content.decode("utf-8-sig").strip().splitlines()) >= 2
    rep = client.post(f"/api/v1/design/{mid}/report.html?simulate=false", json={"spec": {}})
    assert rep.status_code == 200
    assert "Roteiro de prática" in rep.text


@pytest.mark.ngspice
def test_simulate_returns_bode_for_amplifier(client):
    r = client.post("/api/v1/design/DM-SSA/simulate", json={"spec": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"], body["comparisons"]
    assert body["bode_f"] and body["bode"]
    first = next(iter(body["bode"].values()))
    assert len(first["values"]) == len(body["bode_f"])


PHASE5 = ["DM-OPA", "DM-FIL", "DM-OPNL", "DM-OSC", "DM-INST"]


def test_modules_list_phase5_with_labels(client):
    body = {m["id"]: m for m in client.get("/api/v1/design/modules").json()}
    for mid in PHASE5:
        assert mid in body
        assert body[mid]["summary_labels"], mid


@pytest.mark.parametrize("mid", PHASE5)
def test_phase5_design_schematic_bom_report(client, mid):
    r = client.post(f"/api/v1/design/{mid}", json={"spec": {}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["selection"]
    assert body["result"]["steps"]
    svg = client.post(f"/api/v1/design/{mid}/schematic.svg", json={"spec": {}})
    assert svg.status_code == 200 and "<svg" in svg.text
    bom = client.post(f"/api/v1/design/{mid}/bom.csv", json={"spec": {}})
    assert bom.status_code == 200
    assert len(bom.content.decode("utf-8-sig").strip().splitlines()) >= 2
    rep = client.post(f"/api/v1/design/{mid}/report.html?simulate=false", json={"spec": {}})
    assert rep.status_code == 200
    assert "Roteiro de prática" in rep.text


@pytest.mark.ngspice
def test_simulate_filter_returns_bode(client):
    r = client.post("/api/v1/design/DM-FIL/simulate", json={"spec": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"], body["comparisons"]
    assert body["bode_f"] and body["bode"]
