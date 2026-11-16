"""Design assistant on the breadboard: each module's physical circuit, assembled and checked."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app


@pytest.fixture(scope="module")
def client(reviewed_catalogue):
    with TestClient(app) as c:
        app.state.components = reviewed_catalogue
        yield c


def test_every_assemblable_module_passes_the_check(client):
    from circuitos.design import registry

    available = []
    for module_id in registry.MODULES:
        r = client.post(f"/api/v1/design/{module_id}/breadboard", json={"spec": {}})
        assert r.status_code == 200, (module_id, r.text[:300])
        out = r.json()
        if not out["available"]:
            assert "sem peça física" in out["reason"], module_id
            continue
        available.append(module_id)
        report = out["assembly"]["report"]
        assert report["ok"], (module_id, [i["message"] for i in report["issues"]])
        assert out["schematic"]["breadboard"]["parts"]
    print("montáveis:", available)
    assert {"DM-RET1", "DM-SSA", "DM-OPA"} <= set(available)


def test_rectifier_uses_the_chosen_diode_and_its_datasheet_pinout(client):
    out = client.post(
        "/api/v1/design/DM-RET1/breadboard", json={"spec": {"topology": "ponte"}}
    ).json()
    comps = {c["ref"]: c for c in out["schematic"]["components"]}
    assert {"D1", "D2", "D3", "D4", "C1", "RL", "VS"} <= set(comps)
    assert "VSD1" not in comps  # the ammeter is a wire on the board
    assert all(comps[d]["part_id"] for d in ("D1", "D2", "D3", "D4"))
    steps = " ".join(s["text"] for s in out["assembly"]["guide"])
    assert "faixa (catodo)" in steps


def test_op_amp_macromodel_becomes_one_op_amp_with_supplies(client):
    rows = client.get("/api/v1/schematic/parts", params={"kind": "opamp"}).json()
    lm358 = next(r["id"] for r in rows if r["part_number"] == "LM358P")
    body = {"spec": {}, "locks": {"U1": lm358}}
    out = client.post("/api/v1/design/DM-OPA/breadboard", json=body).json()
    assert out["available"], out
    comps = {c["ref"]: c for c in out["schematic"]["components"]}
    assert comps["U1"]["kind"] == "opamp"
    assert comps["U1"]["params"] == {"vcc": "15", "vee": "-15"}
    assert not any(r.startswith(("EU1", "GU1", "RU1", "IU1")) for r in comps)
    assert comps["U1"]["part_id"] == lm358
    refs = {p["ref"] for p in out["schematic"]["breadboard"]["parts"]}
    assert "ALIM" in refs  # the bench supply of the op-amp (V+ and V- from the LM358 pinout)
    assert out["assembly"]["report"]["ok"]


def test_module_with_ideal_switches_is_not_guessed(client):
    out = client.post("/api/v1/design/DM-PAD/breadboard", json={"spec": {}}).json()
    assert not out["available"] and "sem peça física" in out["reason"]
