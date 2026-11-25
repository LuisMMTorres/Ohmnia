"""Real process isolation and lifecycle, without importing or modifying the user's catalogue."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from circuitos.api.interactive import router
from circuitos.breadboard.autoplace import autoplace
from circuitos.breadboard.reference import build
from circuitos.components.repository import ComponentRepository
from circuitos.simulation.interactive import BenchSessions
from tests.unit.schematic.helpers import Builder

pytestmark = pytest.mark.ngspice


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.state.components = ComponentRepository()
    app.state.benches = BenchSessions()
    with TestClient(app) as c:
        yield c
    app.state.benches.close()


def body():
    b = Builder("Teste de bancada")
    b.add("vdc", "V1", ["in", "0"], dc="0")
    b.add("resistor", "R1", ["in", "0"], value="1k")
    b.sch.breadboard, _ = autoplace(build(b.sch, {}))
    return {"schematic": b.sch.model_dump(), "window_s": 0.001}


def test_two_benches_are_isolated_and_stop_releases_the_process(client):
    ids = [client.post("/api/v1/bench", json=body()).json()["id"] for _ in range(2)]
    assert client.post("/api/v1/bench", json=body()).status_code == 422
    a = client.post(f"/api/v1/bench/{ids[0]}/advance", json={"controls": {"V1": {"dc": "5"}}})
    b = client.post(f"/api/v1/bench/{ids[1]}/advance", json={})
    assert a.status_code == b.status_code == 200
    assert a.json()["data"]["traces"]["i(r1)"]["values"][-1] == pytest.approx(0.005)
    assert b.json()["data"]["traces"]["i(r1)"]["values"][-1] == pytest.approx(0)
    processes = [client.app.state.benches.sessions[key].process for key in ids]
    for key in ids:
        assert client.delete(f"/api/v1/bench/{key}").status_code == 204
        assert client.post(f"/api/v1/bench/{key}/advance", json={}).status_code == 404
    assert all(not p.is_alive() for p in processes)


def test_incomplete_wiring_is_rejected_before_start(client):
    data = body()
    data["schematic"]["breadboard"]["parts"] = []
    assert client.post("/api/v1/bench", json=data).status_code == 422
    assert not client.app.state.benches.sessions


def test_invalid_live_control_closes_the_failed_session(client):
    key = client.post("/api/v1/bench", json=body()).json()["id"]
    r = client.post(f"/api/v1/bench/{key}/advance", json={"controls": {"R1": {"value": "2k"}}})
    assert r.status_code == 422
    assert not client.app.state.benches.sessions
