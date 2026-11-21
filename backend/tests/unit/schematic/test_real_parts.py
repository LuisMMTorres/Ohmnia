"""Real catalogue parts for the symbols that had only didactic defaults (2026-11-21).

Each symbol takes its values from the datasheet of the part placed with it: WEG W22 motors,
WEG CWM contactors, Hammond 1182 and BLOCK TT3 transformers, Hammond 175 autotransformers,
P-channel MOSFET and JFET.
"""

from pathlib import Path

import pytest

from circuitos.components.repository import ComponentRepository
from circuitos.schematic.library import symbol
from circuitos.schematic.netlist import build_netlist

from .helpers import Builder

CATALOG = Path(__file__).parents[4] / "data" / "components"


@pytest.fixture(scope="module")
def repo():
    r = ComponentRepository()
    r.import_directory(CATALOG)
    return r


def part(repo, number):
    return next(r for r in repo.search(text=number) if r.part_number == number)


def test_every_didactic_symbol_now_has_catalogue_parts(repo):
    cats = {r.category for r in repo.search()}
    for kind in (
        "pmos",
        "pjf",
        "transformer_1ph",
        "transformer_3ph",
        "autotransformer",
        "induction_motor",
        "contactor",
        "lamp",
    ):
        sym = symbol(kind)
        assert sym.catalogue, kind
        assert any(c in cats for c in sym.catalogue), kind


def test_transformer_takes_nameplate_and_copper_loss(repo):
    t = part(repo, "1182L18")
    b = Builder("t")
    b.add("vsin", "V1", ["p", "0"], amplitude="330", freq="60")
    b.add("transformer_1ph", "T1", ["p", "0", "s", "0"], part_id=str(t.id), vp="1", vs="1")
    b.add("resistor", "R1", ["s", "0"], value="10")
    b.analysis("tran", tstop="50m")
    nl = build_netlist(b.sch, {str(t.id): t})
    lines = {ln.split()[0]: ln.split() for ln in nl.text.splitlines() if ln.startswith("L_T1")}
    # 234 V / 36 V from the data sheet (series windings), not the 1 V / 1 V typed in the symbol
    ratio = float(lines["L_T1_p"][3]) / float(lines["L_T1_s"][3])
    assert ratio == pytest.approx((234 / 36) ** 2, rel=1e-6)
    assert any("1182L18" in w and "regulação (10,5 %)" in w for w in nl.warnings)


def test_three_phase_copper_loss_from_short_circuit_losses(repo):
    from circuitos.schematic.transformers import catalogue_params

    t = part(repo, "TT3 5-4-4")
    values, _ = catalogue_params("transformer_3ph", t, "T1")
    assert values["vp"] == 400 and values["vs"] == 400 and values["sn"] == 5000
    assert values["rcu"] == pytest.approx(100 * 186.99 / 5000)


def test_autotransformer_from_catalogue(repo):
    from circuitos.schematic.transformers import catalogue_params

    t = part(repo, "175D-NA")
    values, warnings = catalogue_params("autotransformer", t, "T1")
    assert (values["vh"], values["vx"], values["sn"]) == (230, 115, 500)
    assert any("não informa perdas" in w for w in warnings)


def test_contactor_thresholds_from_datasheet(repo):
    k = part(repo, "CWM9")
    b = Builder("k")
    b.add("vsin", "V1", ["a", "0"], amplitude="311", freq="60")
    b.add("contactor", "K1", ["a", "0", "l1", "t1", "l2", "t2", "l3", "t3"], part_id=str(k.id))
    b.analysis("tran", tstop="10m")
    nl = build_netlist(b.sch, {str(k.id): k})
    # closes at 0,76 Us and opens at 0,25 Us (WEG CWM, p. 24): vt = 0,505, vh = 0,255
    assert "vt=0.505 vh=0.255" in nl.text
    assert "Rk1_coil" in nl.text or "RK1_coil" in nl.text


def test_p_channel_parts_emit_p_models(repo):
    m, j = part(repo, "IRF9540N"), part(repo, "2N5460")
    b = Builder("p")
    b.add("vdc", "V1", ["s", "0"], dc="10")
    b.add("pmos", "M1", ["d", "g", "s"], part_id=str(m.id))
    b.add("pjf", "J1", ["d2", "0", "s"], part_id=str(j.id))
    b.add("resistor", "R1", ["d", "0"], value="100")
    b.add("resistor", "R2", ["d2", "0"], value="100")
    b.add("vdc", "VG", ["g", "0"], dc="0")
    b.analysis("op")
    nl = build_netlist(b.sch, {str(m.id): m, str(j.id): j})
    assert "PMOS(LEVEL=1 VTO=-3" in nl.text  # middle of |VGS(th)| 2 to 4 V
    assert "PJF(VTO=-" in nl.text  # SPICE keeps VTO negative for a depletion PJF
