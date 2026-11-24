"""DM-RETC1 firing circuit (synchronised ramp, LM393, BC337, MOC3021): sizing and outputs."""

import math

import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.retc1 import Retc1Module, Retc1Spec
from circuitos.reports import outputs, rectifiers
from circuitos.selection.derating import DeratingPolicy

MOD = Retc1Module()


def q(v, u):
    return QuantityModel(value=v, unit=u)


def design(repo, **kw):
    spec = Retc1Spec(firing=True, **kw)
    res, devices = run(
        MOD, spec, lambda c: repo.search(category=c), repo.get, DeratingPolicy.from_preset("didatico")
    )
    return spec, res, devices


def val(res, key):
    return res.summary[key].to_pint().to_base_units().magnitude


def test_off_by_default_keeps_the_ideal_gate_pulses(firing_catalogue):
    spec = Retc1Spec()
    res, devices = run(
        MOD,
        spec,
        lambda c: firing_catalogue.search(category=c),
        firing_catalogue.get,
        DeratingPolicy.from_preset("didatico"),
    )
    assert [r.designator for r in res.roles] == ["T1–T4"]
    assert not any(k.startswith("fd_") for k in res.summary)
    assert "VG1" in MOD.build_circuit(spec, devices, res.summary).netlist


@pytest.mark.parametrize("topo,n", [("ponte", 4), ("semicontrolada", 2), ("meia_onda", 1)])
def test_selects_real_parts_for_every_role(firing_catalogue, topo, n):
    _, res, _ = design(firing_catalogue, topology=topo, P=q(25 if topo == "meia_onda" else 200, "W"))
    parts = {c.designator: c.part_number for c in res.selection}
    moc = next(d for d in parts if d.startswith("U") and d != "U1")
    assert parts[moc] == "MOC3021"  # the zero-crossing MOC3041 cannot fire at α
    assert parts["U1"] == "LM393"
    assert next(r for r in res.roles if r.designator == moc).count == n
    assert parts["DS1–DS4"] == "1N4148"  # signal diodes preferred in the synchronism bridge
    assert not [w for w in res.warnings if w.code.startswith("disparo")]
    ids = {s.id for s in res.steps}
    assert all(st.calc_step_id in ids for st in res.stresses)


def test_ramp_equation_gives_the_nominal_angle(firing_catalogue):
    _, res, _ = design(firing_catalogue, alpha_nom=q(50, "deg"))
    f = 60.0
    w = 2 * math.pi * f
    tau = val(res, "fd_R5") * val(res, "fd_C1")
    vcc, v0, vc = val(res, "fd_Vcc"), val(res, "fd_V0"), val(res, "fd_Vctrl")
    theta_r = val(res, "fd_theta_r")  # rad (base units)
    alpha = theta_r + w * tau * math.log((vcc - v0) / (vcc - vc))
    assert math.degrees(alpha) == pytest.approx(50, abs=1e-6)
    assert res.summary["alpha_fire"].value == pytest.approx(50)
    assert v0 < vc < val(res, "fd_Vpk") < vcc


def test_gate_and_led_sizing_follow_the_datasheets(firing_catalogue):
    spec, res, devices = design(firing_catalogue)
    moc = next(d for k, d in devices.items() if k.startswith("U2")).record
    scr = devices["T1–T4"].record
    vm_max = val(res, "Vm") * 1.1
    itsm = moc.parameters["ITSM"].max
    igm = scr.parameters["IGM"].max
    assert val(res, "fd_RG") >= vm_max / min(itsm, igm)
    ift = moc.parameters["IFT"].max * 1e-3
    assert val(res, "fd_IF_min") >= 1.2 * ift * 0.999
    assert val(res, "fd_IF") <= moc.parameters["IF"].max * 1e-3
    assert val(res, "fd_Vcc") / val(res, "fd_R7") <= 4e-3 + 1e-12  # LM393 V_OL test current
    assert res.summary["fd_alpha_gate"].value < 30


def test_missing_parts_warn_and_fall_back_to_ideal_pulses(reviewed_catalogue):
    spec, res, devices = design(reviewed_catalogue)  # no MOC3021/LM393 released there
    assert any(w.code == "disparo_sem_dados" for w in res.warnings)
    assert "fd_RG" not in res.summary
    assert "VG1" in MOD.build_circuit(spec, devices, res.summary).netlist


def test_angle_outside_the_window_warns(firing_catalogue):
    _, res, _ = design(firing_catalogue, alpha_nom=q(2, "deg"), Vsec=q(90, "V"))
    assert any(w.code == "disparo_fora_da_faixa" for w in res.warnings)


def test_netlist_replaces_the_ideal_gates(firing_catalogue):
    spec, res, devices = design(firing_catalogue)
    net = MOD.build_circuit(spec, devices, res.summary).netlist
    assert "VG1" not in net and "XU1A zs vth zr CMPOC" in net
    for k in range(1, 5):
        assert f"XT{k} " in net and f"RG{k} " in net and f"XU{k + 1} " in net


def test_outputs_show_the_firing_circuit(firing_catalogue):
    spec, res, _ = design(firing_catalogue)
    svg = rectifiers.schematic_svg(spec, res, "t")
    for label in ("U1A", "U1B", "RV1", "RLED", "RG1", "RGK1", "C1", "TS1", "MOC3021"):
        assert label in svg
    rows = {r.designator for r in rectifiers.bom(spec, res)}
    assert {"TS1", "R1", "R5", "C1", "RV1", "RLED", "RG1–RG4", "RGK1–RGK4", "U1"} <= rows
    lab = [i.summary_key for i in outputs.lab(MOD) if i.summary_key in res.summary]
    assert "alpha_fire" in lab and "fd_Vctrl" in lab
    practice = MOD.practice_for(spec, res)
    assert practice is not None and len(practice["procedure"]) >= 5
    assert MOD.practice_for(Retc1Spec(), res) is None
