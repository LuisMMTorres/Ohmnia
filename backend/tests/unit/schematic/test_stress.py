"""Damage check: simulated stress against the ratings of the part (catalogue or user)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from circuitos.components.repository import load_record_file
from circuitos.schematic import stress
from circuitos.schematic.netlist import build_netlist
from tests.unit.schematic.helpers import Builder

CATALOG = Path(__file__).parents[4] / "data" / "components"
D1N4148 = CATALOG / "diode" / "vishay-1n4148.yaml"
Q2N3904 = CATALOG / "bjt" / "onsemi-2n3904.yaml"


def _diode_circuit(r: str):
    rec = load_record_file(D1N4148)
    b = Builder("diodo")
    b.add("vdc", "V1", ["a", "0"], dc="5")
    b.add("resistor", "R1", ["a", "k1"], value=r)
    b.add("diode", "D1", ["k1", "0"], part_id=str(rec.id))
    b.analysis("tran", tstop="1m")
    return b, rec


def test_catalogue_diode_gets_its_ratings_with_their_page():
    """1N4148 (Vishay 81857 rev. 1.6, p. 1): VRRM 100 V, IF(AV) 150 mA, IFSM 2 A, Ptot 440 mW,
    Tj 175 °C with Rθja 350 K/W; the current is sensed in series with the anode."""
    b, rec = _diode_circuit("1k")
    nl = build_netlist(b.sch, {str(rec.id): rec})
    names = {lim.name: lim for lim in nl.limits if lim.ref == "D1"}
    assert set(names) == {"VRRM", "IF(AV)", "IFSM", "Ptot", "Tj max"}
    assert names["VRRM"].limit == 100
    assert names["IF(AV)"].limit == pytest.approx(0.15)
    assert "p. 1" in names["VRRM"].source and "81857" in names["VRRM"].source
    assert names["IF(AV)"].current == "i(vsn_d1_a)"
    assert "vsn_d1_a k1 sn_d1_a DC 0" in nl.text


def test_generic_parts_are_checked_only_with_a_rating_typed_by_the_user():
    b = Builder("r")
    b.add("vdc", "V1", ["a", "0"], dc="12")
    b.add("resistor", "R1", ["a", "0"], value="100")
    b.add("resistor", "R2", ["a", "0"], value="100", p_rated="0.25")
    b.add("capacitor", "C1", ["a", "0"], value="1u", v_rated="10")
    b.analysis("op")
    nl = build_netlist(b.sch)
    assert {(lim.ref, lim.name) for lim in nl.limits} == {("R2", "P nominal"), ("C1", "V nominal")}


def test_evaluate_uses_peak_for_voltage_and_second_half_mean_for_current():
    lim_v = stress.Limit("D1", "V", "VRRM", 100, "V", "peak", v_pos="k", v_neg="a")
    lim_i = stress.Limit("D1", "I", "IF(AV)", 0.15, "A", "mean", current="i(vs)")
    t = np.linspace(0, 1, 101)
    vecs = {
        "v(k)": np.where(t < 0.5, 0.0, 120.0),  # reverse 120 V in the second half
        "v(a)": np.zeros_like(t),
        "i(vs)": np.where(t < 0.5, 5.0, 0.1),  # start-up surge, then 100 mA
    }
    out = stress.evaluate([lim_v, lim_i], vecs, t)
    assert [(d.name, round(d.value)) for d in out] == [("VRRM", 120)]
    assert "VRRM = 100 V" in out[0].cause


def test_junction_temperature_is_ambient_plus_power_times_rth():
    lim = stress.Limit(
        "Q1", "T", "Tj max", 150, "°C", "mean", v_pos="c", current="i(s)", rth=200, t_amb=27
    )
    vecs = {"v(c)": np.array([10.0, 10.0]), "i(s)": np.array([0.07, 0.07])}
    (d,) = stress.evaluate([lim], vecs, None)
    assert d.value == pytest.approx(27 + 0.7 * 200)  # 167 °C > 150 °C
    assert d.quantity == "T"


@pytest.mark.ngspice
@pytest.mark.parametrize(("r", "burns"), [("10", True), ("1k", False)])
def test_as_diode_without_enough_resistance_burns(r, burns):
    """AS-: 5 V on a 1N4148 through R. With 10 Ω, I ≈ (5 − VF)/10 ≈ 0,4 A, above IF(AV) =
    150 mA (tol.: the simulated mean current agrees with the operating point within 2 %); with
    1 kΩ, ≈ 4,3 mA, nothing is exceeded."""
    from circuitos.schematic.runs import SchematicPlan
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    b, rec = _diode_circuit(r)
    res = SchematicPlan(b.sch, {str(rec.id): rec}).execute(SharedNgspiceBackend())
    nl = build_netlist(b.sch, {str(rec.id): rec})
    tran = next(p for p in res.plots if p.kind == "tran")
    vecs = {k.lower(): np.asarray(v.data) for k, v in tran.vectors.items()}
    out = stress.evaluate(nl.limits, vecs, vecs["time"])
    names = {d.name for d in out}
    if not burns:
        assert not out
        return
    assert names == {"IF(AV)"}  # P ≈ 0,4 A · 0,95 V ≈ 0,38 W, still below Ptot = 0,44 W
    d = next(d for d in out if d.name == "IF(AV)")
    vk = float(vecs["v(k1)"][-1])
    assert d.value == pytest.approx((5 - vk) / 10, rel=0.02)


@pytest.mark.ngspice
def test_as_resistor_power_matches_v_squared_over_r():
    """AS-: 12 V on 100 Ω rated 1/4 W: P = V²/R = 1,44 W (tol. 0,5 %), above the rating."""
    from circuitos.schematic.runs import SchematicPlan
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    b = Builder("r")
    b.add("vdc", "V1", ["a", "0"], dc="12")
    b.add("resistor", "R1", ["a", "0"], value="100", p_rated="0.25")
    b.analysis("tran", tstop="1m")
    res = SchematicPlan(b.sch, {}).execute(SharedNgspiceBackend())
    nl = build_netlist(b.sch)
    tran = next(p for p in res.plots if p.kind == "tran")
    vecs = {k.lower(): np.asarray(v.data) for k, v in tran.vectors.items()}
    (d,) = stress.evaluate(nl.limits, vecs, vecs["time"])
    assert d.value == pytest.approx(1.44, rel=5e-3)
    assert "potência" in d.cause
