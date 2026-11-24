"""Every design module draws its circuit (no "see the netlist" placeholder box).

The drawing must name the passive parts of the simulated netlist, so the user can match
the schematic with the netlist and click a part to probe it.
"""

import re

import pytest

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.reports import outputs
from circuitos.selection.derating import DeratingPolicy

from .test_phase5_outputs import VARIANTS as PHASE5

POWER = (
    [("DM-CC", {"topology": t}) for t in ("buck", "buckboost", "cuk", "sepic", "zeta")]
    + [("DM-CC", {"topology": "boost", "Vo": {"value": 48, "unit": "V"}, "compensator": "II"})]
    + [
        ("DM-CCI", {"topology": t})
        for t in ("flyback", "forward", "pushpull", "halfbridge", "fullbridge")
    ]
    + [("DM-INV", {"phases": 1, "filter": True}), ("DM-INV", {"phases": 1})]
    + [("DM-INV", {"phases": 3, "modulation": "spwm", "filter": True})]
    + [("DM-CACA", {"trigger": "diac"}), ("DM-CACA", {"L": {"value": 50, "unit": "mH"}})]
    + [("DM-CMD", {"snubber": True}), ("DM-CMD", {"snubber": False})]
    + [("DM-FIL", {"realization": "passivo_lc"})]
)

# netlist parts that are simulation aids, not parts of the drawn circuit: op-amp macromodel,
# node references (RREF, RNG, RCN), the latch of the 555 model (RLQ, CLQ), 1 mΩ links that
# stand for a wire (Rtr, Rdis), 100 pF node capacitors of the inverter legs (COa...) and the
# energy integrator of the snubber test (RIS, CE, RE)
AIDS = re.compile(
    r"^([RC]U\d|R(REF|NG|CN)$|RLK$|RST$|CST$|RLQ$|CLQ$|Rtr$|Rdis$|CO[abc]$|RIS$|CE$|RE$)"
)


def _texts(svg: str) -> set[str]:
    return {t.strip() for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg)}


# DM-OPA keeps its own drawings (reports/schematic.py); these modules use the new ones
DRAWN = [v for v in PHASE5 if v[0] != "DM-OPA"] + POWER


@pytest.mark.parametrize(("mid", "raw"), DRAWN)
def test_schematic_draws_the_circuit(reviewed_catalogue, mid, raw):
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
    assert "ligação completa na netlist" not in svg
    texts = {t.lower() for t in _texts(svg)}
    netlist = mod.build_circuit(spec, devices, res.summary).netlist
    top = netlist.split(".ends")[-1]  # skip subcircuit bodies
    names = [ln.split()[0] for ln in top.splitlines() if ln[:1] in ("R", "C", "L")]
    missing = [n for n in names if n.lower() not in texts and not AIDS.match(n)]
    assert not missing, f"{mid} {raw}: parts of the netlist not drawn: {missing}"
