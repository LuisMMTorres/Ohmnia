"""DM-RET1 through the design engine: selection, locks, warnings, audit trail."""

import pytest

from circuitos.core.errors import CircuitosError
from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.ret1 import Ret1Module, Ret1Spec
from circuitos.selection.derating import DeratingPolicy

MOD = Ret1Module()
POLICY = DeratingPolicy.from_preset("didatico")


def design(repo, **kw):
    spec = Ret1Spec(**kw)
    return run(
        MOD, spec, lambda c: repo.search(category=c), repo.get, POLICY, kw.pop("locks", None)
    )


@pytest.mark.parametrize(
    "topo,flt",
    [
        (t, f)
        for t in ("meia_onda", "center_tap", "ponte")
        for f in ("nenhum", "C", "LC", "pi")
        if not (t == "meia_onda" and f in ("LC", "pi"))
    ],
)
def test_meets_the_specification(reviewed_catalogue, topo, flt):
    res, _ = design(reviewed_catalogue, topology=topo, filter=flt)
    s = res.summary
    assert res.converged and res.iterations >= 2
    assert s["Vo"].value == pytest.approx(12, rel=1e-3)
    if flt != "nenhum":
        assert s["dVo"].value <= 0.05 * 12 * 1.05  # ripple target 5 % (capacitor rounded up)
    assert 0 < s["PF"].value <= 1
    assert res.selection and res.selection[0].released
    assert all(c.status == "ok" for c in res.margins)
    # every stress points to a step of the log (rule 3)
    ids = {st.id for st in res.steps}
    assert all(st.calc_step_id in ids for st in res.stresses)
    assert f"drop_{res.roles[0].designator}" in ids


def test_bridge_piv_is_the_peak(reviewed_catalogue):
    res, _ = design(reviewed_catalogue, topology="ponte", filter="C")
    assert res.summary["PIV"].value == pytest.approx(res.summary["Vm"].value)
    res, _ = design(reviewed_catalogue, topology="center_tap", filter="C")
    s = res.summary
    assert s["PIV"].value == pytest.approx(s["Vm"].value + s["VC_max"].value, rel=1e-3)


def test_lock_wins_and_unreleased_lock_warns(reviewed_catalogue):
    rec = next(r for r in reviewed_catalogue.search(text="1N4007") if r.part_number == "1N4007")
    res, _ = design(reviewed_catalogue, topology="ponte", filter="C", locks={"D1–D4": rec.id})
    assert res.selection[0].part_number == "1N4007" and res.selection[0].locked
    assert "nao_revisado" not in {w.code for w in res.warnings}


def test_lock_of_wrong_category_is_refused(reviewed_catalogue):
    q = reviewed_catalogue.search(category="bjt")[0]
    with pytest.raises(CircuitosError):
        design(reviewed_catalogue, topology="ponte", filter="C", locks={"D1–D4": q.id})


def test_no_candidate_falls_back_to_ideal_with_warning(reviewed_catalogue):
    res, devices = design(
        reviewed_catalogue,
        topology="ponte",
        filter="C",
        Vo=QuantityModel(value=3000, unit="V"),
        Io=QuantityModel(value=0.01, unit="A"),
    )
    assert "sem_candidato" in {w.code for w in res.warnings}
    assert next(iter(devices.values())).record is None


def test_half_wave_warns_about_dc_in_transformer(reviewed_catalogue):
    res, _ = design(reviewed_catalogue, topology="meia_onda", filter="C")
    assert "cc_no_transformador" in {w.code for w in res.warnings}


def test_lc_and_pi_need_full_wave(reviewed_catalogue):
    with pytest.raises(ValueError):
        design(reviewed_catalogue, topology="meia_onda", filter="LC")


def test_junction_temperature_reported(reviewed_catalogue):
    res, _ = design(reviewed_catalogue, topology="ponte", filter="C")
    assert res.thermal and res.thermal[0].Tj.value > 40
