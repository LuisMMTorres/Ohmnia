"""Rectifiers: the load can be given by its power or by its mean current.

Giving the mean current that the power-based design produced must land on the same load
resistance and the same power (round trip through the exact model of each module).
"""

import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.ret1 import Ret1Module, Ret1Spec
from circuitos.design.plugins.ret3 import Ret3Module, Ret3Spec
from circuitos.design.plugins.retc1 import Retc1Module, Retc1Spec
from circuitos.selection.derating import DeratingPolicy

POLICY = DeratingPolicy.from_preset("didatico")


def _run(repo, module, spec):
    return run(module, spec, lambda c: repo.search(category=c), repo.get, POLICY)[0]


def _round_trip(repo, module, spec_cls, **kw):
    by_power = _run(repo, module, spec_cls(**kw))
    io = by_power.summary["Io"].value
    by_current = _run(
        repo,
        module,
        spec_cls(**kw, load_by="corrente", Io=QuantityModel(value=io, unit="A")),
    )
    return by_power.summary, by_current


@pytest.mark.parametrize("flt", ["nenhum", "C", "LC", "pi"])
def test_ret1_current_gives_same_load(reviewed_catalogue, flt):
    p, res = _round_trip(reviewed_catalogue, Ret1Module(), Ret1Spec, filter=flt)
    s = res.summary
    assert s["Io"].value == pytest.approx(p["Io"].value, rel=1e-4)
    assert s["R_load"].value == pytest.approx(p["R_load"].value, rel=1e-3)
    assert s["P_out"].value == pytest.approx(p["P_out"].value, rel=1e-3)
    r_step = next(st for st in res.steps if st.id == "R")
    assert "I_o" in r_step.inputs and "P" not in r_step.inputs


@pytest.mark.parametrize("topo", ["ponte", "semicontrolada", "meia_onda"])
def test_retc1_current_gives_same_load(reviewed_catalogue, topo):
    power = 20 if topo == "meia_onda" else 200
    p, res = _round_trip(
        reviewed_catalogue,
        Retc1Module(),
        Retc1Spec,
        topology=topo,
        P=QuantityModel(value=power, unit="W"),
        E=QuantityModel(value=10, unit="V"),
    )
    s = res.summary
    assert s["Io"].value == pytest.approx(p["Io"].value, rel=1e-5)
    assert s["R_load"].value == pytest.approx(p["R_load"].value, rel=1e-4)
    assert s["P_out"].value == pytest.approx(power, rel=1e-3)


def test_ret3_current_is_used_directly(reviewed_catalogue):
    p, res = _round_trip(reviewed_catalogue, Ret3Module(), Ret3Spec)
    s = res.summary
    assert s["Io"].value == pytest.approx(p["Io"].value, rel=1e-9)
    assert s["P_out"].value == pytest.approx(p["P_out"].value, rel=1e-6)


def test_ret3_rejects_non_positive_current():
    with pytest.raises(ValueError, match="corrente"):
        Ret3Spec(load_by="corrente", Io=QuantityModel(value=0, unit="A"))


def test_retc1_unreachable_current_is_explained(reviewed_catalogue):
    with pytest.raises(Exception, match="corrente"):
        _run(
            reviewed_catalogue,
            Retc1Module(),
            Retc1Spec(
                load_by="corrente",
                Io=QuantityModel(value=5, unit="A"),
                E=QuantityModel(value=200, unit="V"),  # above the secondary peak: never fires
            ),
        )
