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


def test_bjt_bench_fit_and_markers(client):
    comp = find(client, "bjt", "2N3904")
    body = client.post(
        "/api/v1/devices/bjt/output", json={"component_id": comp["id"], "fit": True}
    ).json()
    assert len(body["curves"]) == 5
    assert body["steps"][0]["id"] == "BF_fit"
    # 2N3904 hFE at 10 mA has min 100 and max 300 → geometric mean
    assert body["model"]["BF"] == pytest.approx((100 * 300) ** 0.5)
    assert any(m["key"] == "VCE(sat)" for m in body["markers"])


def test_bjt_bench_pnp_warning(client):
    comp = find(client, "bjt", "2N3906")
    body = client.post("/api/v1/devices/bjt/output", json={"component_id": comp["id"]}).json()
    assert any("PNP" in w for w in body["warnings"])


def test_mosfet_bench_fit(client):
    comp = find(client, "mosfet", "IRF540")
    body = client.post(
        "/api/v1/devices/mosfet/output", json={"component_id": comp["id"], "fit": True}
    ).json()
    assert [s["id"] for s in body["steps"]][:2] == ["VT_fit", "KP_fit"]
    assert body["model"]["VTO"]["value"] == pytest.approx(3.0)
    assert body["markers"][0]["key"] == "RDS(on)"
    assert len(body["curves"]) == 5


def test_transistor_bench_rejects_wrong_category(client):
    comp = find(client, "diode.rectifier", "1N4007")
    assert (
        client.post("/api/v1/devices/bjt/output", json={"component_id": comp["id"]}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/devices/mosfet/output", json={"component_id": comp["id"]}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices/mosfet/output", json={"vds_max": {"value": -1, "unit": "V"}}
        ).status_code
        == 422
    )


def test_thyristor_bench_default_scr(client):
    body = client.post("/api/v1/devices/thyristor/waveform", json={}).json()
    assert set(body["traces"]) == {
        "Tensão da fonte",
        "Tensão na carga",
        "Tensão no tiristor",
        "Corrente",
        "Corrente de porta",
    }
    ids = [s["id"] for s in body["steps"]]
    assert ids == ["gate_Q1", "i_latch", "theta_off", "Vavg_ideal", "Vrms_ideal"]
    ideal = body["steps"][3]["output"]["value"]
    assert body["summary"]["Vavg"]["value"] == pytest.approx(ideal, rel=0.03)
    assert [e["kind"] for e in body["events"]] == ["on", "off", "on", "off"]
    assert body["spice_model"].startswith(".subckt")


def test_thyristor_bench_fit_scr(client):
    comp = find(client, "thyristor.scr", "2N5060")
    body = client.post(
        "/api/v1/devices/thyristor/waveform", json={"component_id": comp["id"], "fit": True}
    ).json()
    ids = [s["id"] for s in body["steps"]]
    assert ids[:3] == ["IGT", "IH", "rT_fit"]
    assert body["model"]["IGT_Q1"]["value"] == pytest.approx(0.2)
    assert body["model"]["IH"]["value"] == pytest.approx(5.0)
    assert any("IL" in w for w in body["warnings"])


def test_thyristor_bench_fit_triac_quadrants(client):
    comp = find(client, "thyristor.triac", "MAC218A6FP")
    body = client.post(
        "/api/v1/devices/thyristor/waveform",
        json={
            "component_id": comp["id"],
            "fit": True,
            "model": {"kind": "triac"},
            "drive": {"IG": {"value": 60, "unit": "mA"}, "gate_mode": "positivo"},
        },
    ).json()
    assert body["model"]["IGT_Q4"]["value"] == pytest.approx(75)
    # 60 mA fires Q1 (50 mA) but not Q4 (75 mA): one turn-on per period
    assert sum(1 for e in body["events"] if e["kind"] == "on") == 2
    assert any("Q4" in w for w in body["warnings"])


def test_thyristor_bench_rejects_bad_input(client):
    url = "/api/v1/devices/thyristor/waveform"
    assert (
        client.post(url, json={"drive": {"alpha": {"value": 200, "unit": "deg"}}}).status_code
        == 422
    )
    comp = find(client, "bjt.npn", "2N3904")
    assert client.post(url, json={"component_id": comp["id"]}).status_code == 422


def test_thyristor_bench_no_fire_warning(client):
    body = client.post(
        "/api/v1/devices/thyristor/waveform", json={"drive": {"IG": {"value": 1, "unit": "mA"}}}
    ).json()
    assert body["events"] == []
    assert any("não conduziu" in w for w in body["warnings"])


def test_pn_bench_default(client):
    body = client.post("/api/v1/devices/pn", json={}).json()
    assert [s["id"] for s in body["steps"]] == ["ni", "V0", "W", "xn", "Emax", "Cj", "IS"]
    assert set(body["depletion"]) == {"W", "xn (lado n)", "xp (lado p)"}
    assert body["capacitance"]["unit"] == "pF"
    assert len(body["ni"]["values"]) == len(body["temperature"]["values"])
    assert any("assimétrica" in w for w in body["warnings"])
    assert body["spice_model"].startswith(".model DPN")


def test_pn_bench_rejects_bad_input(client):
    url = "/api/v1/devices/pn"
    assert client.post(url, json={"NA": {"value": -1, "unit": "1/cm**3"}}).status_code == 422
    assert client.post(url, json={"vr_max": {"value": 0, "unit": "V"}}).status_code == 422
    body = client.post(url, json={"NA": {"value": 1e20, "unit": "1/cm**3"}}).json()
    assert any("degenerado" in w for w in body["warnings"])


@pytest.mark.ngspice
def test_opamp_bench_default_model(client):
    body = client.post("/api/v1/devices/opamp/bench", json={}).json()
    assert body["tests"] and all(t["ok"] for t in body["tests"]), body["tests"]
    assert {t["id"] for t in body["tests"]} >= {"BV-AMPOP-GBW", "BV-AMPOP-SR", "BV-AMPOP-CMRR"}
    assert len(body["bode_f"]["values"]) == len(body["bode_mag_db"]["values"])


@pytest.mark.ngspice
def test_opamp_bench_catalogue_part(client):
    comp = find(client, "opamp", "TL071CP")
    r = client.post("/api/v1/devices/opamp/bench", json={"component_id": comp["id"]})
    assert r.status_code == 200, r.text
    assert all(t["ok"] for t in r.json()["tests"])


def test_opamp_bench_rejects_other_category(client):
    comp = find(client, "diode.rectifier", "1N4007")
    r = client.post("/api/v1/devices/opamp/bench", json={"component_id": comp["id"]})
    assert r.status_code in (400, 422)
