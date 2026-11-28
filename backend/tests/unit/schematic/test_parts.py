"""Catalogue parts in the free simulator: the models come from the datasheet values."""

import pytest

from circuitos.schematic.model import Sweep
from circuitos.schematic.netlist import SchematicError, build_netlist
from circuitos.schematic.runs import SchematicPlan
from circuitos.simulation.backend import make_backend

from .helpers import Builder


def part(repo, number):
    return next(r for r in repo.search(text=number) if r.part_number == number)


@pytest.fixture(scope="module")
def parts(reviewed_catalogue):
    names = ("1N4733A", "BC547B", "IRF840", "2N5457", "LM741CP", "2N5060", "MAC97A6", "1N4148")
    names += ("FGH40N60SMD", "TIP120")
    out = {}
    for n in names:
        found = [r for r in reviewed_catalogue.search(text=n) if r.part_number == n]
        if found:
            out[n] = found[0]
    return out


def records(*recs):
    return {str(r.id): r for r in recs}


@pytest.mark.ngspice
def test_zener_regulates_at_datasheet_vz(parts):
    z = parts["1N4733A"]
    b = Builder("zener")
    b.add("vdc", "V1", ["in", "0"], dc="12")
    b.add("resistor", "R1", ["in", "k"], value="100")
    b.add("zener", "D1", ["0", "k"], part_id=str(z.id))
    b.analysis("op")
    nl = build_netlist(b.sch, records(z))
    assert nl.spreads["D1"].param == "vz"  # ±5 % VZ tolerance of the datasheet
    assert nl.spreads["D1"].hi == pytest.approx(5.1 * 1.05)
    res = SchematicPlan(b.sch, records(z)).execute(make_backend())
    vz = res.plot("op")["v(k)"].data[0]
    iz = (12 - vz) / 100
    # V_Z = V_Z0 + r_z·I_Z with V_Z0 = V_Z − I_ZT·Z_ZT (1N4733A: 5,1 V at 49 mA, Z_ZT = 7 Ω)
    assert vz == pytest.approx(5.1 + (iz - 0.049) * 7, rel=1e-4)


@pytest.mark.ngspice
def test_transistors_opamp_and_switches_simulate(parts):
    p = parts
    b = Builder("catálogo")
    b.add("vdc", "VCC", ["vcc", "0"], dc="15")
    b.add("vdc", "VEE", ["vee", "0"], dc="-15")
    b.add("vdc", "VB", ["vb", "0"], dc="0.7")
    b.add("npn", "Q1", ["c1", "vb", "0"], part_id=str(p["BC547B"].id), ic_op="2m")
    b.add("resistor", "RC1", ["vcc", "c1"], value="1k")
    b.add("vdc", "VG", ["g", "0"], dc="10")
    b.add("nmos", "M1", ["d", "g", "0"], part_id=str(p["IRF840"].id))
    b.add("resistor", "RD", ["vcc", "d"], value="100")
    b.add("njf", "J1", ["dj", "0", "0"], part_id=str(p["2N5457"].id))
    b.add("resistor", "RJ", ["vcc", "dj"], value="100")
    b.add("vdc", "VI", ["vi", "0"], dc="1")
    b.add("opamp", "U1", ["uo", "vi", "uo"], part_id=str(p["LM741CP"].id))
    b.add("diode", "D2", ["vcc", "dd"], part_id=str(p["1N4148"].id))
    b.add("resistor", "RDD", ["dd", "0"], value="1k")
    b.add("igbt", "Q2", ["ci", "g", "0"], part_id=str(p["FGH40N60SMD"].id))
    b.add("resistor", "RI", ["vcc", "ci"], value="1")
    b.add("npn", "Q3", ["cd", "vb2", "0"], part_id=str(p["TIP120"].id))
    b.add("vdc", "VB2", ["vb2", "0"], dc="1.3")
    b.add("resistor", "RCD", ["vcc", "cd"], value="100")
    b.analysis("op")
    recs = records(*(p[n] for n in ("BC547B", "IRF840", "2N5457", "LM741CP", "1N4148")))
    recs.update(records(p["FGH40N60SMD"], p["TIP120"]))
    plan = SchematicPlan(b.sch, recs)
    nl = plan.nominal()
    assert "Q1" in nl.spreads and nl.spreads["Q1"].param == "bf"
    assert "M1" in nl.spreads and nl.spreads["M1"].param == "vto"
    op = plan.execute(make_backend()).plot("op")
    assert 0 < op["v(c1)"].data[0] < 15  # BJT conducts
    assert op["v(d)"].data[0] < 1.0  # MOSFET in triode with VGS = 10 V
    assert op["v(uo)"].data[0] == pytest.approx(1.0, abs=5e-3)  # follower (with Vos, Ib)
    vf = 15 - op["v(dd)"].data[0]
    assert vf == pytest.approx(1.0, abs=1e-2)  # 1N4148: VF max 1 V (constant-drop model)
    assert op["v(ci)"].data[0] < 3.0  # IGBT on
    assert op["v(cd)"].data[0] < 15


@pytest.mark.ngspice
def test_scr_latches_and_triac_conducts_both_ways(parts):
    scr, triac = parts["2N5060"], parts["MAC97A6"]
    b = Builder("tiristores")
    b.add("vsin", "V1", ["ac", "0"], amplitude="50", freq="60")
    b.add("resistor", "RL", ["ac", "a"], value="100")
    b.add("scr", "T1", ["a", "0", "g"], part_id=str(scr.id))
    b.add("vpulse", "VG", ["gs", "0"], v1="0", v2="5", delay="1m", width="200u", period="16.6667m")
    b.add("resistor", "RG", ["gs", "g"], value="1k")
    b.add("resistor", "RL2", ["ac", "m"], value="100")
    b.add("triac", "T2", ["m", "0", "g2"], part_id=str(triac.id))
    b.add(
        "vpulse", "VG2", ["g2s", "0"], v1="0", v2="5", delay="1m", width="200u", period="8.33333m"
    )
    b.add("resistor", "RG2", ["g2s", "g2"], value="100")
    b.analysis("tran", tstop="33.3m", tmax="20u")
    res = SchematicPlan(b.sch, records(scr, triac)).execute(make_backend())
    tran = res.plot("tran")
    va, vm = tran["v(a)"].data, tran["v(m)"].data
    assert va.min() < -40  # SCR blocks the negative half-cycle
    i_triac = (tran["v(ac)"].data - vm) / 100
    assert i_triac.max() > 0.3 and i_triac.min() < -0.3  # TRIAC fired in both half-cycles
    assert any("I_GT" in w for w in res.warnings)


def test_part_checks(parts, reviewed_catalogue):
    z = parts["1N4733A"]
    b = Builder()
    b.add("vdc", "V1", ["a", "0"])
    b.add("npn", "Q1", ["a", "a", "0"], part_id=str(z.id))
    b.analysis("op")
    with pytest.raises(SchematicError, match="não serve"):
        build_netlist(b.sch, records(z))
    with pytest.raises(SchematicError, match="não encontrada"):
        build_netlist(b.sch, {})
    draft = z.model_copy(update={"review": z.review.model_copy(update={"status": "rascunho"})})
    c = Builder()
    c.add("vdc", "V1", ["a", "0"])
    c.add("zener", "D1", ["0", "a"], part_id=str(z.id))
    c.analysis("op")
    nl = build_netlist(c.sch, records(draft))
    assert any("não foi revisado" in w for w in nl.warnings)


@pytest.mark.ngspice
def test_monte_carlo_uses_datasheet_vz_range(parts):
    z = parts["1N4733A"]
    b = Builder("mc zener")
    b.add("vdc", "V1", ["in", "0"], dc="12")
    b.add("resistor", "R1", ["in", "k"], value="1k", tol="0")
    b.add("zener", "D1", ["0", "k"], part_id=str(z.id))
    b.analysis("op")
    b.sch.sweep = Sweep(kind="montecarlo", runs=20, distribution="uniform")
    res = SchematicPlan(b.sch, records(z)).execute(make_backend())
    vz = [p["v(k)"].data[0] for p in res.plots]
    assert max(vz) - min(vz) > 0.2
    # at I_Z ≈ 7 mA the voltage sits below V_Z by (I_ZT − I_Z)·Z_ZT < 0,049·7 V
    assert all(5.1 * 0.95 - 0.049 * 7 < v < 5.1 * 1.05 for v in vz)


@pytest.mark.ngspice
def test_p_channel_parts_conduct_with_negative_bias():
    """IRF9540N (mosfet.p) and 2N5460 (jfet.p) keep magnitudes in the catalogue; the models are
    PMOS/PJF: the MOSFET conducts with VGS = −10 V (RDS(on) max 0,117 Ω at VGS = −10 V, so the
    drop on 1 A is below 0,2 V) and the JFET with VGS = 0 (ID between IDSS min 1 and max 5 mA)."""
    from pathlib import Path

    from circuitos.components.repository import load_records_file

    root = Path(__file__).resolve().parents[4] / "data" / "components"
    p = {}
    for f in ("mosfet/infineon-irf9540n.yaml", "jfet/onsemi-2n5460.yaml"):
        for r in load_records_file(root / f):
            p[r.part_number] = r
    b = Builder("canal P")
    b.add("vdc", "VDD", ["vdd", "0"], dc="12")
    b.add("vdc", "VG", ["g", "0"], dc="2")
    b.add("pmos", "M1", ["d", "g", "vdd"], part_id=str(p["IRF9540N"].id))
    b.add("resistor", "RD", ["d", "0"], value="12")
    b.add("pjf", "J1", ["dj", "0", "0"], part_id=str(p["2N5460"].id))
    b.add("vdc", "VN", ["n", "0"], dc="-15")
    b.add("resistor", "RJ", ["dj", "n"], value="100")
    b.analysis("op")
    recs = records(p["IRF9540N"], p["2N5460"])
    text = build_netlist(b.sch, recs).text
    assert " PMOS(" in text and " PJF(" in text
    op = SchematicPlan(b.sch, recs).execute(make_backend()).plot("op")
    assert 12 - op["v(d)"].data[0] < 0.2
    i_j = (op["v(dj)"].data[0] + 15) / 100
    assert 1e-3 <= i_j <= 5e-3


@pytest.mark.ngspice
def test_generic_p_jfet_is_depletion():
    """Generic PJF (VTO = −2 V, SPICE convention for depletion): conducts at VGS = 0 with
    ID = BETA·VTO² = 4 mA."""
    b = Builder("pjf")
    b.add("vdc", "VN", ["n", "0"], dc="-15")
    b.add("pjf", "J1", ["dj", "0", "0"])
    b.add("resistor", "RJ", ["dj", "n"], value="100")
    b.analysis("op")
    op = SchematicPlan(b.sch).execute(make_backend()).plot("op")
    assert (op["v(dj)"].data[0] + 15) / 100 == pytest.approx(4e-3, rel=1e-3)


@pytest.mark.ngspice
def test_opamp_supply_pins_draw_the_datasheet_quiescent_current(parts):
    """LM741C with V+ and V− wired to ±15 V and no load: each supply delivers the catalogue IQ
    (typical; TI SNOSC25D, p. 6) plus the output current."""
    p = parts["LM741CP"]
    b = Builder("741 alimentado pelos pinos")
    b.add("vdc", "VP", ["vp", "0"], dc="15")
    b.add("vdc", "VN", ["vn", "0"], dc="-15")
    b.add("opamp", "U1", ["0", "0", "o", "vp", "vn"], part_id=str(p.id))
    b.add("resistor", "RL", ["o", "0"], value="1meg")
    b.analysis("op")
    op = SchematicPlan(b.sch, records(p)).execute(make_backend()).plot("op")
    iq = p.parameters["IQ"].typ * 1e-3
    io = op["v(o)"].data[0] / 1e6
    assert -op["i(vp)"].data[0] == pytest.approx(iq + max(io, 0), rel=1e-3)
    assert op["i(vn)"].data[0] == pytest.approx(iq + max(-io, 0), rel=1e-3)
