"""Unit tests of the LDO, class D, Darlington and JFET additions (no simulator)."""

import math

import pytest

from circuitos.components.models import ComponentRecord, DatasheetRef
from circuitos.core.calc import CalcLog
from circuitos.core.units import Q_
from circuitos.design import registry
from circuitos.design.devmodels import Bjt, Darlington, Jfet
from circuitos.design.engine import Device, run
from circuitos.design.fet import vgs_for
from circuitos.design.plugins.chave.module import darlington_on
from circuitos.design.plugins.lin.module import LM317_REF, app_ref, is_ldo
from circuitos.design.plugins.pad.module import R_OFF, Bridge, PadModule, PadSpec, solve
from circuitos.selection.derating import DeratingPolicy


def _rec(tags: list[str]) -> ComponentRecord:
    return ComponentRecord(
        category="regulator.positive",
        schema_version="1.0",
        manufacturer="x",
        part_number="P",
        tags=tags,
        datasheets=[DatasheetRef(id="d", manufacturer="onsemi", document_number="X/D")],
    )


def test_is_ldo_uses_manufacturer_tag():
    assert is_ldo(_rec(["ldo"]))
    assert not is_ldo(_rec([]))


def test_app_ref_points_to_the_part_datasheet():
    assert app_ref(None) == LM317_REF
    assert app_ref(_rec([])).book == "onsemi X/D"


def _design(repo, mid, raw):
    mod = registry.get(mid)
    spec = mod.spec_schema(**raw)
    res, _ = run(
        mod,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    return res


def test_ldo_flag_selects_only_ldo_parts(reviewed_catalogue):
    q = lambda v, u: {"value": v, "unit": u}  # noqa: E731
    std = _design(reviewed_catalogue, "DM-LIN", {})
    ldo = _design(
        reviewed_catalogue, "DM-LIN", {"ldo": True, "Vin": q(8, "V"), "ripple_pp": q(0.5, "V")}
    )
    assert std.selection[0].part_number.startswith("MC78")
    assert ldo.selection[0].part_number.startswith("NCP1117")
    assert ldo.summary["Co"].to_pint().m_as("uF") == pytest.approx(10)


def test_ldo_adjustable_without_minimum_load_uses_100_iadj(reviewed_catalogue):
    q = lambda v, u: {"value": v, "unit": u}  # noqa: E731
    res = _design(
        reviewed_catalogue,
        "DM-LIN",
        {
            "ldo": True,
            "kind": "ajustavel",
            "Vo": q(3.3, "V"),
            "Io": q(50, "mA"),
            "Vin": q(6, "V"),
        },
    )
    assert res.selection[0].part_number == "LM2931ACD2TR4G"
    assert any(w.code == "criterio" for w in res.warnings)
    assert res.summary["I_R1"].to_pint().m_as("uA") == pytest.approx(20, rel=0.05)


def test_darlington_switch_kcl_balances():
    beta = 30.0
    d = Darlington(Bjt(IS=1e-14, BF=beta), Bjt(IS=1e-14 * (beta + 1), BF=beta))
    ib, ic, vb, vc = darlington_on(d, 12, 120, 5, 7500, 10e3)
    assert ib == pytest.approx((5 - vb) / 7500 - vb / 10e3, rel=1e-9)
    assert ic == pytest.approx((12 - vc) / 120, rel=1e-9)
    assert 0 < vc < vb  # saturated: collector below the base


def test_vgs_for_inverts_shockley():
    m = Jfet(IDSS=8e-3, VP=4.0)
    v = vgs_for(m, 2e-3, CalcLog())
    assert m.id_sat(v) == pytest.approx(2e-3, rel=1e-9)


def test_bridge_thevenin_and_filter():
    br = Bridge(vcc=24, r_on=0.1, rl=8, L=68e-6, C=0.56e-6, f=1e3, k=200, m=0.5)
    assert br.rth == pytest.approx(0.1 * R_OFF / (0.1 + R_OFF))
    assert br.vth == pytest.approx(24, rel=1e-9)
    assert abs(br.h(0)) == pytest.approx(8 / 8.1, rel=1e-6)
    iv = br.intervals()
    assert len(iv) == 3 * 200
    assert iv[0][0] == 0 and iv[-1][1] == pytest.approx(1e-3)
    # duty cycle follows (1 + m sin ωt)/2 at the middle of each carrier period
    n = 50
    t0, t1, _ = iv[3 * n]
    _, t2, _ = iv[3 * n + 1]
    ts = 1 / (br.f * br.k)
    on = (t1 - t0) + (t0 + ts - t2)
    tc = t0 + ts / 2
    assert on / ts == pytest.approx((1 + br.m * math.sin(2 * math.pi * br.f * tc)) / 2, abs=0.01)


def test_bridge_solution_is_periodic():
    br = Bridge(vcc=24, r_on=0.1, rl=8, L=68e-6, C=0.56e-6, f=1e3, k=50, m=0.5)
    sol = solve(br)
    assert sol.il[-1] == pytest.approx(sol.il[0], abs=1e-9)
    assert sol.vo[-1] == pytest.approx(sol.vo[0], abs=1e-9)


def test_pad_rejects_overmodulation():
    mod = PadModule()
    spec = PadSpec(Po={"value": 100, "unit": "W"}, VCC={"value": 12, "unit": "V"})
    devices = {k: Device(record=None, drop=Q_(0, "V")) for k in ("Q1", "Q2")}
    with pytest.raises(ValueError, match="modulação"):
        mod.analyse(spec, devices)


def test_pad_warns_on_filter_placement():
    mod = PadModule()
    devices = {k: Device(record=None, drop=Q_(0, "V")) for k in ("Q1", "Q2")}
    a = mod.analyse(PadSpec(fc={"value": 60, "unit": "kHz"}), devices)
    assert any(w.code == "filtro" for w in a.warnings)
    b = mod.analyse(PadSpec(fc={"value": 2, "unit": "kHz"}), devices)
    assert any(w.code == "filtro" for w in b.warnings)
    assert any(w.code == "estimativa" for w in b.warnings)  # no part: no tr/tf
