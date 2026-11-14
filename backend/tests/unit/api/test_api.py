import time

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app

RC = """rc
V1 in 0 PULSE(0 1 0 1n 1n 5m 10m) AC 1
R1 in out 1k
C1 out 0 1u
.op
.tran 1u 20m
.ac dec 10 10 100k
"""


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait_done(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(f"/api/v1/simulations/{job_id}").json()
        if body["state"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(0.1)
    raise AssertionError("timeout")


def test_health(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"


def test_eseries(client):
    assert len(client.get("/api/v1/eseries/E12").json()["values"]) == 12
    r = client.post(
        "/api/v1/eseries/snap", json={"value": {"value": 4.6, "unit": "kohm"}, "series": "E24"}
    ).json()
    assert r["value"] == {"value": 4.7, "unit": "kohm"} and r["formatted"] == "4,7 kΩ"
    bad = client.post("/api/v1/eseries/snap", json={"value": {"value": -1, "unit": "ohm"}})
    assert bad.status_code == 422


def test_component_schema(client):
    assert "diode.rectifier" in client.get("/api/v1/components/categories").json()
    assert client.get("/api/v1/components/schemas/diode.rectifier").json()["required"]
    assert client.get("/api/v1/components/schemas/nada").status_code == 404


@pytest.mark.ngspice
def test_simulation_flow(client):
    r = client.post("/api/v1/simulations", json={"netlist": RC})
    assert r.status_code == 202
    job = wait_done(client, r.json()["id"])
    assert job["state"] == "done", job
    names = {p["kind"]: p["name"] for p in job["plots"]}
    tran = client.get(
        f"/api/v1/simulations/{job['id']}/plots/{names['tran']}",
        params={"vectors": "v(out),v(in)", "max_points": 200},
    ).json()
    assert tran["decimated"] and len(tran["x"]["values"]) <= 210
    assert tran["traces"]["v(out)"]["unit"] == "V"
    ac = client.get(
        f"/api/v1/simulations/{job['id']}/plots/{names['ac']}", params={"form": "mag_db"}
    ).json()
    assert ac["traces"]["v(out)"]["values"][0] == pytest.approx(0, abs=0.1)
    for form in ("real", "imag", "mag", "phase_deg"):
        assert (
            client.get(
                f"/api/v1/simulations/{job['id']}/plots/{names['ac']}", params={"form": form}
            ).status_code
            == 200
        )
    op = client.get(f"/api/v1/simulations/{job['id']}/plots/{names['op']}").json()
    assert op["x"] is None
    m = client.get(
        f"/api/v1/simulations/{job['id']}/plots/{names['tran']}/measures",
        params={"vector": "v(in)", "start": 0.01, "stop": 0.02},
    ).json()
    assert m["mean"]["value"] == pytest.approx(0.5, rel=1e-2)
    assert (
        client.get(
            f"/api/v1/simulations/{job['id']}/plots/{names['ac']}/measures",
            params={"vector": "v(out)"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/simulations/{job['id']}/plots/{names['tran']}/measures",
            params={"vector": "v(x)"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/simulations/{job['id']}/plots/{names['tran']}/measures",
            params={"vector": "v(in)", "start": 1, "stop": 2},
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/simulations/{job['id']}/plots/nada").status_code == 404
    assert (
        client.get(
            f"/api/v1/simulations/{job['id']}/plots/{names['tran']}", params={"vectors": "v(zz)"}
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/simulations/{job['id']}", params={"log": True}).json()["log"]


@pytest.mark.ngspice
def test_simulation_error_and_websocket(client):
    r = client.post("/api/v1/simulations", json={"netlist": "t\nR1 a 0\n.op\n"})
    job_id = r.json()["id"]
    with client.websocket_connect(f"/api/v1/simulations/{job_id}/ws") as ws:
        messages = []
        while True:
            try:
                messages.append(ws.receive_json())
            except Exception:
                break
    assert messages[-1]["state"] == "failed"
    assert messages[-1]["error"]["message"]


@pytest.mark.ngspice
def test_cancel(client):
    long = "t\nV1 a 0 SIN(0 1 1k)\nR1 a b 1k\nC1 b 0 1u\n.tran 1n 20\n"
    job_id = client.post("/api/v1/simulations", json={"netlist": long}).json()["id"]
    time.sleep(0.5)
    assert client.delete(f"/api/v1/simulations/{job_id}").json()["state"] == "cancelled"
    assert client.get(f"/api/v1/simulations/{job_id}/plots/tran1").status_code == 409


def test_unknown_job(client):
    assert client.get("/api/v1/simulations/nada").status_code == 404
    from starlette.websockets import WebSocketDisconnect

    with (
        client.websocket_connect("/api/v1/simulations/nada/ws") as ws,
        pytest.raises(WebSocketDisconnect),
    ):
        ws.receive_json()
