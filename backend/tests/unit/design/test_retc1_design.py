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
def test_meets_vo_and_selects_scr(reviewed_catalogue, topo):
    res, _ = design(
        reviewed_catalogue,
        topology=topo,
        Vo=QuantityModel(value=40, unit="V"),
        alpha_nom=QuantityModel(value=45, unit="deg"),
    )
    assert res.summary["Vo"].value == pytest.approx(40, rel=1e-3)
    roles = {r.designator: r for r in res.roles}
    scr = next(c for c in res.selection if roles[c.designator].category == "thyristor.scr")
    assert scr.released
    ids = {s.id for s in res.steps}
    assert {"Vm", "Vo", "Vo_ideal", "IT_avg", "VDRM", "PF"} <= ids
    assert all(st.calc_step_id in ids for st in res.stresses)


def test_alpha_range_for_mains_tolerance(reviewed_catalogue):
    res, _ = design(reviewed_catalogue, topology="ponte")
    s = res.summary
    assert s["alpha_min"].value < 30 < s["alpha_max"].value


def test_heatsink_warning_names_the_required_rsa(reviewed_catalogue):
    res, _ = design(reviewed_catalogue, topology="ponte")
    warn = [w for w in res.warnings if w.code == "dissipador"]
    assert warn and "Rθsa" in warn[0].message
    assert res.thermal[0].required_Rsa is not None


def test_counter_emf_must_be_below_vo(reviewed_catalogue):
    with pytest.raises(ValueError):
        design(reviewed_catalogue, topology="ponte", E=QuantityModel(value=80, unit="V"))


def test_freewheel_only_half_wave():
    with pytest.raises(ValueError):
        Retc1Spec(topology="ponte", freewheel=True)
