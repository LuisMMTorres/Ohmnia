import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def find(client, category, text):
    items = client.get("/api/v1/components", params={"category": category, "q": text}).json()
    items = items["items"] if isinstance(items, dict) else items
    return next(c for c in items if c["part_number"] == text)


def test_diode_bench_with_datasheet_markers(client):
    comp = find(client, "diode.rectifier", "1N4007")
    body = client.post("/api/v1/devices/diode/iv", json={"component_id": comp["id"]}).json()
    assert set(body["curves"]) == {"25 °C", "100 °C"}
    assert body["markers"] and body["warnings"]
    assert body["spice_model"].startswith(".model")


def test_diode_bench_rejects_bad_range(client):
    r = client.post(
        "/api/v1/devices/diode/iv",
        json={"v_min": {"value": 1, "unit": "V"}, "v_max": {"value": 0.5, "unit": "V"}},
    )
    assert r.status_code == 422


def test_zener_bench_default_model(client):
    body = client.post("/api/v1/devices/zener/iv", json={}).json()
    assert len(body["curves"]) == 2
    assert [s["id"] for s in body["steps"]] == ["VZ_0", "rz_0", "VZ_1", "rz_1"]
    assert body["spice_model"].startswith(".subckt")
    assert body["markers"] == []


def test_zener_bench_fit_to_datasheet(client):
    comp = find(client, "diode.zener", "1N4733A")
    record = client.get(f"/api/v1/components/{comp['id']}").json()
    record = record.get("record", record)
    vz = record["parameters"]["VZ"]
    zzt = record["parameters"]["ZZT"]
    body = client.post(
        "/api/v1/devices/zener/iv",
        json={
            "component_id": comp["id"],
            "fit": True,
            "temperatures": [{"value": 30, "unit": "degC"}],
        },
    ).json()
    assert [s["id"] for s in body["steps"]][:2] == ["Rz_fit", "VZ0_fit"]
    vz_step = next(s for s in body["steps"] if s["id"] == "VZ_0")
    rz_step = next(s for s in body["steps"] if s["id"] == "rz_0")
    # the fitted model reproduces the datasheet test point (values read from the catalogue)
    assert vz_step["output"]["value"] == pytest.approx(vz["typ"], rel=1e-6)
    assert rz_step["output"]["value"] == pytest.approx(zzt["typ"], rel=1e-6)
    assert any(m["key"] == "VZ_typ" for m in body["markers"])
    assert any("não conferidos" in w for w in body["warnings"])


def test_zener_bench_rejects_other_category(client):
    comp = find(client, "diode.rectifier", "1N4007")
    r = client.post("/api/v1/devices/zener/iv", json={"component_id": comp["id"]})
    assert r.status_code == 422
