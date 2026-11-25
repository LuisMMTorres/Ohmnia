"""Design assistant on the breadboard: each module's physical circuit, assembled and checked."""

from __future__ import annotations

import typing

import pytest
from fastapi.testclient import TestClient

from circuitos.api.app import app
from circuitos.breadboard import board
from circuitos.breadboard.check import board_nets
from circuitos.breadboard.layout import Breadboard


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


# ------------------------------------------------------------- every variant, every leg wired

# variants the default values reject (a boost needs Vo > Vin, and so on)
_EXTRA = {
    "DM-CC": [
        {"topology": "boost", "Vin": {"value": 12, "unit": "V"}, "Vo": {"value": 24, "unit": "V"}}
    ],
    "DM-FIL": [
        {"kind": "passa_altas", "f_stop": {"value": 300, "unit": "Hz"}},
        {
            "kind": "rejeita_faixa",
            "B": {"value": 500, "unit": "Hz"},
            "f_stop": {"value": 1, "unit": "kHz"},
        },
    ],
    "DM-INV": [{"phases": 3, "modulation": "spwm"}, {"phases": 3, "modulation": "svpwm"}],
}  # fmt: skip


def _variants(module_id, schema):
    """The defaults, then each choice field (Literal or bool) changed alone."""
    out = [{}]
    for name, f in schema.model_fields.items():
        if "series" in name:
            continue  # E-series only change values, not the circuit
        if f.annotation is bool:
            out.append({name: not f.default})
        elif typing.get_origin(f.annotation) is typing.Literal:
            out += [{name: v} for v in typing.get_args(f.annotation) if v != f.default]
    return out + _EXTRA.get(module_id, [])


def _unwired(ref, bb):
    """Legs whose node on the board differs from the netlist, computed here from the strips and
    jumpers (independent of the check): every leg of a node must share its conductor with the
    other legs of that node, and with no leg of another node."""
    uf = board_nets(bb)
    have = {}
    for p in bb.parts:
        r = ref.parts.get(p.ref)
        for pin, hole in p.legs.items():
            net = ref.nets.get(f"{p.ref}:{pin}") if r and pin in r.pinmap else None
            if net is not None:
                have[f"{p.ref}:{pin}"] = (net, uf.find(board.strip(hole, bb.rails_split)))
    wrong = []
    by_net: dict[str, set[str]] = {}
    by_conductor: dict[str, set[str]] = {}
    for net, cond in have.values():
        by_net.setdefault(net, set()).add(cond)
        by_conductor.setdefault(cond, set()).add(net)
    for net, conds in by_net.items():
        if len(conds) > 1:
            wrong.append(f"nó {net} partido em {len(conds)} condutores")
    for cond, nets in by_conductor.items():
        if len(nets) > 1:
            wrong.append(f"nós {sorted(nets)} em curto ({cond})")
    for p in bb.parts:
        r = ref.parts.get(p.ref)
        if r is not None and r.origin == "sem_pinagem":
            wrong.append(f"{p.ref} ({r.part_number}) sem pinagem: pernas soltas")
    return wrong


def test_every_variant_wires_every_leg_of_every_part(client, reviewed_catalogue):
    """Each module, with each of its choices, gives an assembly where every leg of every part is
    on the conductor of its node (no part standing loose on the board, no part left out), and
    every jumper is straight: the holes are chosen so the wire runs along a row or a column."""
    from circuitos.api.breadboard import reference_for
    from circuitos.design import registry
    from circuitos.schematic.model import Schematic

    failures = []
    for module_id, module in registry.MODULES.items():
        for spec in _variants(module_id, module.spec_schema):
            r = client.post(f"/api/v1/design/{module_id}/breadboard", json={"spec": spec})
            if r.status_code == 422:
                continue  # the spec itself is refused (e.g. freewheel diode on a bridge)
            assert r.status_code == 200, (module_id, spec, r.text[:300])
            out = r.json()
            if not out["available"]:
                continue
            sch = Schematic.model_validate(out["schematic"])
            ref = reference_for(reviewed_catalogue, sch)
            bb = Breadboard.model_validate(out["schematic"]["breadboard"])
            report = out["assembly"]["report"]
            problems = _unwired(ref, bb)
            if not report["ok"]:
                problems.append(report["summary"])
            for w in bb.wires:  # every jumper along a row or a column, never diagonal
                (xa, ya), (xb, yb) = board.xy(w.a), board.xy(w.b)
                if xa != xb and ya != yb:
                    problems.append(f"fio {w.a}–{w.b} na diagonal")
            placed = {p.ref for p in bb.parts}
            problems += [f"{x} fora da protoboard" for x, p in ref.parts.items()
                         if p.checkable and x not in placed]  # fmt: skip
            if problems:
                failures.append((module_id, spec, problems[:5]))
    assert not failures, failures
