"""Schematic and BOM of every Phase 4 module variant render without error (no simulation)."""

import pytest

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.reports import outputs
from circuitos.selection.derating import DeratingPolicy

VARIANTS = [
    ("DM-FORMA", {"kind": k})
    for k in (
        "ceifador_paralelo",
        "ceifador_serie",
        "ceifador_duplo",
        "grampeador",
        "multiplicador",
    )
] + [
    ("DM-ZEN", {"variant": "transistor", "IL_max": {"value": 300, "unit": "mA"}}),
    (
        "DM-LIN",
        {
            "polarity": "simetrica",
            "Vo": {"value": 15, "unit": "V"},
            "Vin": {"value": 22, "unit": "V"},
        },
    ),
    (
        "DM-LIN",
        {
            "kind": "ajustavel",
            "polarity": "negativa",
            "Vo": {"value": 9, "unit": "V"},
            "Vin": {"value": 15, "unit": "V"},
        },
    ),
    *[("DM-BIAS", {"config": c}) for c in ("fixa", "emissor", "coletor")],
    ("DM-BIAS", {"config": "mos_divisor", "IC": {"value": 10, "unit": "mA"}}),
    *[("DM-SSA", {"config": c}) for c in ("CC", "BC")],
    ("DM-SSA", {"config": "FC", "IC": {"value": 10, "unit": "mA"}}),
    ("DM-DIFF", {"tail": "espelho"}),
    *[("DM-PA", {"cls": c}) for c in ("A", "B")],
    ("DM-CHAVE", {"load": "resistiva"}),
    (
        "DM-CHAVE",
        {
            "device": "mosfet",
            "R_load": {"value": 12, "unit": "ohm"},
            "V_drive": {"value": 10, "unit": "V"},
        },
    ),
]


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
