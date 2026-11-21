"""DM-RETC1 through the design engine."""

import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.retc1 import Retc1Module, Retc1Spec
from circuitos.selection.derating import DeratingPolicy

MOD = Retc1Module()


def design(repo, **kw):
    return run(
        MOD,
        Retc1Spec(**kw),
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )


@pytest.mark.parametrize("topo", ["ponte", "semicontrolada", "meia_onda"])
def test_meets_power_and_selects_scr(reviewed_catalogue, topo):
    power = 20 if topo == "meia_onda" else 200
    res, _ = design(
        reviewed_catalogue,
        topology=topo,
        P=QuantityModel(value=power, unit="W"),
        alpha_nom=QuantityModel(value=45, unit="deg"),
    )
    s = res.summary
    assert s["P_out"].value == pytest.approx(power, rel=1e-3)
    assert s["Vm"].value == pytest.approx(70 * 2**0.5, rel=1e-9)
    assert s["Io"].value == pytest.approx(s["Vo"].value / s["R_load"].value, rel=1e-3)
    roles = {r.designator: r for r in res.roles}
    scr = next(c for c in res.selection if roles[c.designator].category == "thyristor.scr")
    assert scr.released
    ids = {s.id for s in res.steps}
    assert {"Vm", "R_load", "Vo", "Vo_ideal", "IT_avg", "VDRM", "PF"} <= ids
    assert all(st.calc_step_id in ids for st in res.stresses)


def test_alpha_range_for_mains_tolerance(reviewed_catalogue):
    res, _ = design(reviewed_catalogue, topology="ponte")
    s = res.summary
    assert s["alpha_min"].value < 30 < s["alpha_max"].value


def test_heatsink_chosen_from_catalogue(reviewed_catalogue):
    res, _ = design(reviewed_catalogue, topology="ponte")
    t = res.thermal[0]
    assert t.required_Rsa is not None and t.heatsink is not None
    assert t.heatsink_Rsa is not None and t.heatsink_Rsa.value <= t.required_Rsa.value
    assert t.status == "ok"
    warn = [w for w in res.warnings if w.code == "dissipador_escolhido"]
    assert warn and t.heatsink in warn[0].message
    assert any(s.id.startswith("Tj_hs_") for s in res.steps)


def test_counter_emf_above_the_secondary_peak_is_refused(reviewed_catalogue):
    with pytest.raises(ValueError):
        design(reviewed_catalogue, topology="ponte", E=QuantityModel(value=120, unit="V"))


def test_power_above_the_maximum_is_refused(reviewed_catalogue):
    with pytest.raises(ValueError):
        design(reviewed_catalogue, topology="meia_onda", P=QuantityModel(value=500, unit="W"))


def test_freewheel_only_half_wave():
    with pytest.raises(ValueError):
        Retc1Spec(topology="ponte", freewheel=True)
