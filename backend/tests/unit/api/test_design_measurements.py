"""Results measured on the ngspice run of a design, probes and edits from the schematic."""

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app

URL = "/api/v1/design/DM-RET1"


@pytest.fixture(scope="module")
def client(reviewed_catalogue):
    with TestClient(app) as c:
        app.state.components = reviewed_catalogue
        yield c


def _by_label(items):
    return {m["label"]: m for m in items}


@pytest.mark.ngspice
def test_rectifier_measurements_come_from_the_simulation(client):
    body = {"spec": {"topology": "ponte", "filter": "C"}}
    design = client.post(URL, json=body).json()["result"]["summary"]
    sim = client.post(f"{URL}/simulate", json=body).json()
    meas = sim["measurements"]
    waves = _by_label(meas["waves"])
    powers = _by_label(meas["powers"])
    # every probe of the primary, the secondary, the load and the diode is measured
    for label in (
        "Tensão no primário",
        "Corrente no primário",
        "Tensão no secundário",
        "Corrente no secundário",
        "Tensão na carga",
        "Corrente na carga",
        "Tensão em D1 (anodo − catodo)",
    ):
        assert label in waves and label in sim["traces"]
    # 127 V RMS on the primary and 12 V RMS on the secondary, as asked
    assert waves["Tensão no primário"]["rms"]["value"] == pytest.approx(127, rel=1e-3)
    assert waves["Tensão no secundário"]["rms"]["value"] == pytest.approx(12, rel=1e-3)
    assert waves["Tensão na carga"]["avg"]["value"] == pytest.approx(
        design["Vo"]["value"], rel=0.01
    )
    # the load absorbs the power asked for; the ideal transformer passes it unchanged
    load = powers["Carga"]
    assert load["P"] == {"value": pytest.approx(12, rel=0.01), "unit": "W"}
    assert load["PF"]["value"] == pytest.approx(1, rel=0.01)
    pri = powers["Primário"]
    assert pri["P"]["value"] == pytest.approx(powers["Secundário"]["P"]["value"], rel=1e-3)
    assert pri["S"]["unit"] == "V*A" and pri["Q"]["unit"] == "var"
    assert pri["PF"]["value"] == pytest.approx(design["PF"]["value"], rel=0.02)
    assert pri["S"]["value"] ** 2 == pytest.approx(
        pri["P"]["value"] ** 2 + pri["Q"]["value"] ** 2 + pri["D"]["value"] ** 2, rel=1e-6
    )
    assert not sim["edited"]


@pytest.mark.ngspice
def test_probes_and_edits_from_the_schematic(client):
    els = client.post(f"{URL}/elements", json={"spec": {}}).json()
    names = {e["name"]: e for e in els["elements"]}
    assert names["XD1"]["role"] == "D1–D4" and names["C1"]["edit"] == "value"
    assert "p" in els["nodes"]
    body = {
        "spec": {},
        "overrides": {"C1": "100u"},
        "probes": [
            {"kind": "i", "a": "C1"},
            {"kind": "p", "a": "RL"},
            {"kind": "vdiff", "a": "a", "b": "p"},
        ],
    }
    sim = client.post(f"{URL}/simulate", json=body).json()
    assert sim["edited"]
    assert "Corrente em C1" in sim["traces"] and "Tensão a − p" in sim["traces"]
    assert "Potência instantânea: RL" in sim["traces"]
    powers = _by_label(sim["measurements"]["powers"])
    assert powers["RL"]["P"]["value"] == pytest.approx(powers["Carga"]["P"]["value"], rel=1e-3)
    # a smaller capacitor raises the ripple: the simulation diverges from the design
    assert not sim["ok"]
    edited = client.post(f"{URL}/elements", json=body).json()
    assert next(e for e in edited["elements"] if e["name"] == "C1")["original"] is not None
    bad = client.post(f"{URL}/simulate", json={"spec": {}, "overrides": {"XD1": "1"}})
    assert bad.status_code == 422
