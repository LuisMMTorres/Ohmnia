"""Schematic and BOM of every Phase 5 module variant render without error (no simulation)."""

import pytest

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.reports import outputs
from circuitos.selection.derating import DeratingPolicy

VARIANTS = (
    [
        ("DM-OPA", {"config": c})
        for c in (
            "inversor",
            "nao_inversor",
            "seguidor",
            "somador",
            "subtrator",
            "integrador",
            "diferenciador",
            "transimpedancia",
            "transcondutancia",
            "instrumentacao",
        )
    ]
    + [("DM-FIL", {"realization": r}) for r in ("sallen_key", "mfb", "variaveis_estado")]
    + [("DM-FIL", {"kind": "passa_faixa", "f_stop": {"value": 1.5, "unit": "kHz"}})]
    + [
        ("DM-OPNL", {"config": c})
        for c in (
            "comparador",
            "schmitt_inversor",
            "schmitt_nao_inversor",
            "retificador_meia",
            "retificador_onda",
            "logaritmico",
            "limitador",
        )
    ]
    + [("DM-OPNL", {"config": "comparador", "device": "comparador"})]
    + [
        ("DM-OSC", {"config": c})
        for c in (
            "wien",
            "deslocamento_fase",
            "astavel_ampop",
            "ne555_astavel",
            "ne555_monoestavel",
            "multivibrador_tbj",
        )
    ]
    + [
        ("DM-INST", {"config": c})
        for c in (
            "voltimetro",
            "amperimetro",
            "potencia",
            "transmissor_4_20",
            "receptor_4_20",
            "ponte_wheatstone",
            "condicionamento",
        )
    ]
)


@pytest.mark.parametrize(("mid", "raw"), VARIANTS)
def test_schematic_and_bom(reviewed_catalogue, mid, raw):
    repo = reviewed_catalogue
    mod = registry.get(mid)
    spec = mod.spec_schema(**raw)
    res, devices = run(
        mod,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    svg = outputs.schematic_svg(mod, spec, res, mod.title)
    assert svg.startswith("<svg") or "<svg" in svg[:200]
    rows = outputs.bom(mod, spec, res)
    assert rows and all(r.designator for r in rows)
    netlist = mod.build_circuit(spec, devices, res.summary).netlist
    assert netlist.strip()


def test_lc_ladder_bom_without_semiconductors(reviewed_catalogue):
    repo = reviewed_catalogue
    mod = registry.get("DM-FIL")
    spec = mod.spec_schema(realization="passivo_lc")
    res, _ = run(
        mod,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    rows = outputs.bom(mod, spec, res)
    assert rows and all(r.designator[0] in "RLC" for r in rows)
