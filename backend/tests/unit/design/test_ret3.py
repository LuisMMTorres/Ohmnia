"""DM-RET3 model consistency and design flow."""

import math

import numpy as np
import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.ret3 import Ret3Module, Ret3Spec
from circuitos.design.plugins.ret3 import model as m
from circuitos.selection.derating import DeratingPolicy

F = 60.0


@pytest.mark.parametrize("p", [3, 6, 12])
@pytest.mark.parametrize("deg,Ls", [(0, 0.0), (30, 1e-3), (60, 2e-3)])
def test_energy_balance_and_formula(p, deg, Ls):
    a = math.radians(deg)
    w = m.waves(p, 400, a, 15, Ls, F, 1.2)
    assert m.mean(w.vo) == pytest.approx(m.mean_output(p, 400, a, 15, Ls, F, 1.2), rel=1e-3)
    n = {3: 1, 6: 2, 12: 4}[p]
    p_dc = (m.mean(w.vo) + n * 1.2) * 15
    assert m.input_power(w) == pytest.approx(p_dc, rel=1e-3)
    assert 0 < m.power_factor(w) <= 1


def test_twelve_pulse_primary_current_carries_the_power():
    w = m.waves(12, 400, math.radians(20), 15, 1e-3, F, 0.0)
    per_phase = sum(float(np.mean(e * i)) for e, i in zip(w.e, w.i_ref, strict=True))
    assert per_phase == pytest.approx(m.input_power(w), rel=1e-3)


def test_inverse_of_mean_output():
    for p in (3, 6, 12):
        v = m.peak_line_voltage_for(p, 200, math.radians(25), 10, 1e-3, F, 1.0)
        assert m.mean_output(p, v, math.radians(25), 10, 1e-3, F, 1.0) == pytest.approx(200)


def test_overlap_impossible():
    with pytest.raises(ValueError):
        m.overlap_angle(0.0, 1000, 0.1, 100, F)


def test_design_flow(reviewed_catalogue):
    repo = reviewed_catalogue
    for kw in (
        dict(pulses=6),
        dict(pulses=6, controlled=False),
        dict(pulses=12, Vsec=QuantityModel(value=180, unit="V")),
    ):
        spec = Ret3Spec(**kw)
        res, _ = run(
            Ret3Module(),
            spec,
            lambda c: repo.search(category=c),
            repo.get,
            DeratingPolicy.from_preset("didatico"),
        )
        s = res.summary
        assert s["P_out"].value == pytest.approx(spec.P.value, rel=1e-3)
        assert s["Vll_m"].value == pytest.approx(spec.Vsec.value * 2**0.5, rel=1e-9)
        assert res.selection and res.selection[0].released
        ids = {s.id for s in res.steps}
        assert {"Vll_m", "mu", "dV_mu", "PF", "THD_i"} <= ids


def test_spec_validation():
    with pytest.raises(ValueError):
        Ret3Spec(alpha_nom=QuantityModel(value=100, unit="deg"))
    with pytest.raises(ValueError):
        Ret3Spec(P=QuantityModel(value=0, unit="W"))
    with pytest.raises(ValueError):  # E above the mean output
        run(
            Ret3Module(),
            Ret3Spec(E=QuantityModel(value=300, unit="V")),
            lambda c: [],
            lambda i: None,
            DeratingPolicy.from_preset("didatico"),
        )
