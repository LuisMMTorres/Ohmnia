"""Derating policy, margin checks and automatic selection (rule 5)."""

import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.base import Stress
from circuitos.selection.derating import DeratingPolicy
from circuitos.selection.select import check, rank


def stress(key, value, unit):
    return Stress(
        designator="D1",
        key=key,
        label=key,
        value=QuantityModel(value=value, unit=unit),
        calc_step_id="x",
    )


def test_presets_are_design_criteria_with_defaults():
    d = DeratingPolicy.from_preset("didatico")
    i = DeratingPolicy.from_preset("industrial")
    assert d.factor("diode.rectifier", "VRRM") == 1.5
    assert i.factor("diode.rectifier", "VRRM") == 2.0
    assert i.tj_margin_K > d.tj_margin_K
    assert d.factor("diode.rectifier", "nada") == 1.0  # keys without a rule: no derating


def test_check_status_bands(reviewed_catalogue):
    rec = next(
        r for r in reviewed_catalogue.search(text="1N4004") if r.part_number == "1N4004"
    )  # VRRM 400 V
    policy = DeratingPolicy.from_preset("didatico")
    ok, atencao, violado = (
        check(rec, [stress("VRRM", v, "V")], policy)[0] for v in (200, 300, 500)
    )
    assert (ok.status, atencao.status, violado.status) == ("ok", "atencao", "violado")
    assert ok.margin_pct == pytest.approx(100)
    assert ok.rating.value == pytest.approx(400)


def test_rank_skips_unreleased_and_inadequate(reviewed_catalogue):
    policy = DeratingPolicy.from_preset("didatico")
    stresses = [stress("VRRM", 100, "V"), stress("IF(AV)", 0.5, "A")]
    ranked = rank(reviewed_catalogue.search(category="diode"), stresses, policy, ["VRRM", "IF(AV)"])
    names = [r.record.part_number for r in ranked]
    assert names, "algum diodo do catálogo atende"
    assert all(r.record.selectable for r in ranked)
    for r in ranked:
        assert all(c.status == "ok" for c in r.checks)
    assert "1N4001" not in names  # 50 V < 1.5 × 100 V
    # cheapest adequate first: the smallest over-rating has the smallest score
    assert [r.score for r in ranked] == sorted(r.score for r in ranked)


def test_rank_never_picks_unreleased(reviewed_catalogue):
    rec = next(r for r in reviewed_catalogue.search(text="1N4007") if r.part_number == "1N4007")
    draft = rec.model_copy(
        update={"review": rec.review.model_copy(update={"status": "em_revisao"})}
    )
    policy = DeratingPolicy.from_preset("didatico")
    assert rank([draft], [stress("VRRM", 10, "V")], policy, ["VRRM"]) == []


def test_fits_position_keeps_polarity_and_lets_diodes_swap():
    from circuitos.selection.select import fits_position

    assert fits_position("diode.signal", "diode.rectifier")  # any diode can conduct there
    assert fits_position("diode", "diode.zener")
    assert not fits_position("diode.zener", "diode.rectifier")  # breakdown is the function
    assert not fits_position("bjt.npn", "bjt.pnp")  # other polarity
    assert not fits_position("thyristor.scr", "thyristor.triac")
    assert not fits_position("opamp", "comparator")


def test_assess_tells_how_a_part_meets_the_position(reviewed_catalogue):
    from circuitos.selection.select import assess

    rec = next(r for r in reviewed_catalogue.search(text="1N4004") if r.part_number == "1N4004")
    policy = DeratingPolicy.from_preset("didatico")

    def fit(v, keys=("VRRM",), **kw):
        return assess(rec, "diode", [stress("VRRM", v, "V")], policy, list(keys), **kw)

    assert fit(200).status == "atende"
    assert fit(300).status == "margem_menor"
    bad = fit(500)
    assert bad.status == "nao_atende" and "VRRM" in (bad.reason or "")
    assert fit(200, keys=("VRRM", "nada")).status == "sem_dados"
    assert fit(200, accepted=False).status == "nao_atende"
    assert assess(rec, "bjt.npn", [], policy, []).status == "incompativel"
