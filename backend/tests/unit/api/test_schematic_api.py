import math

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app
from circuitos.schematic.model import NetRef, Probe

from ..schematic.helpers import Builder
from .test_api import wait_done


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def rc_schematic():
    b = Builder("rc")
    b.add("vsin", "V1", ["in", "0"], amplitude="1", freq="1k")
    b.add("resistor", "R1", ["in", "out"], value="1k")
    b.add("capacitor", "C1", ["out", "0"], value="159.155n")
    b.analysis("tran", tstop="10m", tmax="5u").analysis("ac", points="50")
    b.sch.probes = [
        Probe(id="p1", kind="v", target=NetRef(net="out")),
        Probe(id="p2", kind="p", component="R1"),
    ]
    return b.sch.model_dump(mode="json")


def test_library_and_parts(client):
    lib = client.get("/api/v1/schematic/library").json()
    kinds = {s["kind"]: s for s in lib["symbols"]}
    assert {"resistor", "vsin", "v3ph", "transformer", "opamp", "scr", "igbt"} <= set(kinds)
    assert kinds["resistor"]["pins"] == [
        {"name": "1", "dx": -2, "dy": 0},
        {"name": "2", "dx": 2, "dy": 0},
    ]
    assert set(lib["analyses"]) == {"op", "tran", "ac", "dc", "noise"}
    parts = client.get("/api/v1/schematic/parts", params={"kind": "zener"}).json()
    assert all(p["category"] == "diode.zener" for p in parts)
    assert client.get("/api/v1/schematic/parts", params={"kind": "nada"}).status_code == 404


def test_netlist_and_import(client):
    r = client.post("/api/v1/schematic/netlist", json={"schematic": rc_schematic()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "R1 am_r1_1 out 1k" in body["netlist"]
    assert [p["name"] for p in body["probes"]] == ["v(out)", "p(r1)"]
    assert {s["component"] for s in body["spreads"]} == {"R1", "C1"}
    bad = rc_schematic()
    bad["analyses"] = []
    assert client.post("/api/v1/schematic/netlist", json={"schematic": bad}).status_code == 422
    imp = client.post("/api/v1/schematic/import", json={"netlist": body["netlist"]}).json()
    assert {c["ref"] for c in imp["schematic"]["components"]} >= {"V1", "R1", "C1"}
    unknown = rc_schematic()
    unknown["components"][1]["part_id"] = "00000000-0000-0000-0000-000000000000"
    r = client.post("/api/v1/schematic/netlist", json={"schematic": unknown})
    assert r.status_code == 404


@pytest.mark.ngspice
def test_simulate_and_analyse_results(client):
    r = client.post("/api/v1/schematic/simulate", json={"schematic": rc_schematic()})
    assert r.status_code == 202, r.text
    job = wait_done(client, r.json()["job_id"])
    assert job["state"] == "done", job
    plots = {p["kind"]: p for p in job["plots"]}
    tran, ac = plots["tran"]["name"], plots["ac"]["name"]
    base = f"/api/v1/simulations/{job['job_id'] if 'job_id' in job else job['id']}"

    m = client.get(f"{base}/plots/{tran}/measures", params={"vector": "v(out)", "start": 5e-3})
    body = m.json()
    assert body["frequency"]["value"] == pytest.approx(1000, rel=1e-3)
    assert body["period"]["value"] == pytest.approx(1e-3, rel=1e-3)
    assert body["rms"]["value"] == pytest.approx(0.5, rel=3e-3)

    spec = client.get(
        f"{base}/plots/{tran}/spectrum",
        params={"vector": "v(out)", "f0": 1000, "periods": 5, "n_harmonics": 10},
    ).json()
    assert spec["harmonics"][0]["amplitude"] == pytest.approx(1 / math.sqrt(2), rel=3e-3)
    assert spec["thd"] < 5e-3

    e = client.post(
        f"{base}/plots/{tran}/expressions", json={"expr": "integ(p(r1))", "name": "energia"}
    )
    assert e.status_code == 200, e.text
    assert e.json()["unit"] == "J"
    bad = client.post(f"{base}/plots/{tran}/expressions", json={"expr": "v(nada)"})
    assert bad.status_code == 422

    csv = client.get(f"{base}/plots/{ac}/csv", params={"vectors": "v(out)", "form": "mag_db"})
    lines = csv.text.splitlines()
    assert lines[0] == "frequency [Hz];v(out) [dB]"
    assert "," in lines[1]  # decimal comma
    intl = client.get(
        f"{base}/plots/{ac}/csv", params={"vectors": "v(out)", "style": "intl", "form": "real"}
    )
    assert intl.text.splitlines()[0].startswith("frequency [Hz],re v(out)")

    for fmt, magic in (("svg", b"<?xml"), ("png", b"\x89PNG"), ("pdf", b"%PDF")):
        fig = client.post(
            f"{base}/figure",
            json={"plot": tran, "vectors": ["v(out)", "v(in)"], "format": fmt, "title": "RC"},
        )
        assert fig.status_code == 200 and fig.content.startswith(magic)
    bode = client.post(f"{base}/figure", json={"plot": ac, "vectors": ["v(out)"], "kind": "bode"})
    assert bode.status_code == 200
    xy = client.post(
        f"{base}/figure",
        json={"plot": tran, "vectors": ["v(out)"], "kind": "xy", "x_vector": "v(in)"},
    )
    assert xy.status_code == 200
    sp = client.post(
        f"{base}/figure", json={"plot": tran, "vectors": ["v(out)"], "kind": "spectrum", "f0": 1000}
    )
    assert sp.status_code == 200
    st = client.get(
        f"{base}/statistics",
        params={"analysis": "ac", "vector": "v(out)", "kind": "mag_db_at", "at": "1k"},
    ).json()
    assert st["values"][0]["value"] == pytest.approx(-3.0103, abs=0.01)
    assert st["unit"] == "dB"


@pytest.mark.ngspice
def test_monte_carlo_job(client):
    sch = rc_schematic()
    sch["analyses"] = [{"kind": "ac", "params": {"points": "20"}}]
    sch["sweep"] = {"kind": "montecarlo", "runs": 8, "seed": 3}
    r = client.post("/api/v1/schematic/simulate", json={"schematic": sch}).json()
    assert r["runs"] == 9
    job = wait_done(client, r["job_id"])
    assert job["state"] == "done", job
    assert len(job["runs"]) == 9 and job["runs"][1]["values"]
    assert {p["base"] for p in job["plots"]} == {job["plots"][0]["base"]}
    st = client.get(
        f"/api/v1/simulations/{job['id']}/statistics",
        params={"analysis": "ac", "vector": "v(out)", "kind": "mag_db_at", "at": "1k"},
    ).json()
    assert st["stats"]["n"] == 9 and sum(st["histogram"]["counts"]) == 9
    assert st["nominal"] == pytest.approx(-3.0103, abs=0.01)
    fig = client.post(
        f"/api/v1/simulations/{job['id']}/figure",
        json={
            "plot": job["plots"][0]["name"],
            "vectors": ["v(out)"],
            "kind": "bode",
            "all_runs": True,
        },
    )
    assert fig.status_code == 200
    bad = dict(sch, sweep={"kind": "worstcase"})
    assert client.post("/api/v1/schematic/simulate", json={"schematic": bad}).status_code == 422
