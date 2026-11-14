"""Heat sink choice from the extrusion catalogue (HS Dissipadores, ΔT correction of p. 10)."""

import uuid

import pytest

from circuitos.components.models import ComponentRecord, Parameter, ReviewState
from circuitos.thermal import heatsink as hs


def sink(name, rsa, lifecycle="desconhecido", released=True):
    return ComponentRecord(
        id=uuid.uuid4(),
        category="heatsink.extrusion",
        schema_version="1.0",
        manufacturer="teste",
        part_number=name,
        lifecycle=lifecycle,
        parameters={
            "Rth_sa": Parameter(symbol="Rth_sa", typ=rsa, unit="K/W"),
            "dT_ref": Parameter(symbol="dT_ref", typ=75, unit="K"),
        },
        review=ReviewState(status="liberado" if released else "rascunho"),
    )


def test_dt_factor_matches_catalogue_table():
    assert hs.dt_factor(75) == 1.0
    assert hs.dt_factor(30) == pytest.approx(1.257)
    assert hs.dt_factor(45) == pytest.approx((1.170 + 1.106) / 2)
    assert hs.dt_factor(10) == pytest.approx(1.257)  # kept at the table end
    assert hs.dt_factor(100) == 1.0


def test_fit_solves_the_rise_consistently():
    f = hs.fit(sink("A", 4.89), P=10, TA=40, rth_jc=1.0, rth_cs=0.5)
    assert f is not None
    assert f.dT == pytest.approx(10 * 4.89 * hs.dt_factor(f.dT), rel=1e-6)
    assert f.Tj == pytest.approx(40 + 10 * 1.5 + f.dT)


def test_choose_takes_the_smallest_adequate_released_in_stock():
    sinks = [
        sink("grande", 0.7),
        sink("medio", 2.0),
        sink("pequeno", 8.0),
        sink("medio_sem_estoque", 2.5, lifecycle="nrnd"),
        sink("nao_liberado", 3.0, released=False),
    ]
    f = hs.choose(sinks, P=10, TA=40, tj_limit=110, rth_jc=1.0, rth_cs=0.5)
    assert f is not None and f.record.part_number == "medio"
    assert hs.choose(sinks, P=100, TA=40, tj_limit=110, rth_jc=1.0, rth_cs=0.5) is None
