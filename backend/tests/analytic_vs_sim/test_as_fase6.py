"""AS-CC-01, AS-CCI, AS-INV-01, AS-CACA, AS-CMD: Phase 6 analytic × ngspice.

Each case designs with the reviewed catalogue, builds the circuit the result describes and
compares every SimCheck (averages, ripples, rms values, THD up to the 50th harmonic, peak
inrush current, turn-off energy). The tolerance of each check is in the module
(``SimCheck.tolerance_pct`` with its justification); a divergence above it fails here and is a
warning in the result.
"""

import pytest

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.design.verify import compare_full
from circuitos.selection.derating import DeratingPolicy

pytestmark = pytest.mark.ngspice


def q(v: float, u: str) -> dict[str, object]:
    return {"value": v, "unit": u}


UP = {"Vin": q(12, "V"), "Vo": q(24, "V"), "Io": q(1, "A")}
CC = {
    "cc_buck": ("DM-CC", {}),
    "cc_boost": ("DM-CC", {"topology": "boost", **UP}),
    "cc_buckboost": ("DM-CC", {"topology": "buckboost", **UP}),
    "cc_cuk": ("DM-CC", {"topology": "cuk"}),
    "cc_sepic": ("DM-CC", {"topology": "sepic"}),
    "cc_zeta": ("DM-CC", {"topology": "zeta"}),
    "cc_buck_mcd": ("DM-CC", {"mode": "MCD"}),
    "cc_boost_mcd": ("DM-CC", {"topology": "boost", "mode": "MCD", **UP}),
    "cc_buck_igbt": (
        "DM-CC",
        {"switch": "igbt", "Vin": q(300, "V"), "Vo": q(150, "V"), "fs": q(20, "kHz")},
    ),
}
CCI = {
    f"cci_{t}": ("DM-CCI", {"topology": t})
    for t in ("flyback", "forward", "pushpull", "halfbridge", "fullbridge")
}
INV = {
    "inv_quadrada": ("DM-INV", {"modulation": "quadrada"}),
    "inv_quase_quadrada": ("DM-INV", {"modulation": "quase_quadrada"}),
    "inv_bipolar": ("DM-INV", {"modulation": "spwm_bipolar"}),
    "inv_unipolar": ("DM-INV", {}),
    "inv_3f_quadrada": ("DM-INV", {"phases": 3, "modulation": "quadrada"}),
    "inv_3f_spwm": ("DM-INV", {"phases": 3, "modulation": "spwm"}),
    "inv_3f_svpwm": ("DM-INV", {"phases": 3, "modulation": "svpwm", "ma": 1.1}),
    "inv_filtro": ("DM-INV", {"filter": True}),
    "inv_filtro_mf201": ("DM-INV", {"filter": True, "mf": 201}),
    "inv_3f_filtro": ("DM-INV", {"phases": 3, "modulation": "spwm", "filter": True}),
    "inv_mosfet": (
        "DM-INV",
        {"switch": "mosfet", "Vdc": q(48, "V"), "R": q(2, "ohm"), "L": q(2, "mH")},
    ),
}
CACA = {
    "caca_r": ("DM-CACA", {}),
    "caca_rl": ("DM-CACA", {"L": q(100, "mH")}),
    "caca_rl_alpha40": ("DM-CACA", {"L": q(100, "mH"), "alpha_deg": 40}),
    "caca_ciclo": ("DM-CACA", {"control": "ciclo_integral"}),
    "caca_ciclo_rl": ("DM-CACA", {"control": "ciclo_integral", "L": q(50, "mH")}),
    "caca_diac": ("DM-CACA", {"trigger": "diac"}),
}
CMD = {
    "cmd_igbt": ("DM-CMD", {}),
    "cmd_mosfet": (
        "DM-CMD",
        {"switch": "mosfet", "Vbus": q(48, "V"), "Io": q(5, "A"), "fs": q(100, "kHz")},
    ),
}
CASES = CC | CCI | INV | CACA | CMD


@pytest.mark.parametrize("name", list(CASES))
def test_as_fase6(reviewed_catalogue, name):
    repo = reviewed_catalogue
    mid, raw = CASES[name]
    mod = registry.get(mid)
    spec = mod.spec_schema(**raw)
    res, devices = run(
        mod,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    assert res.selection, "nenhum componente selecionado"
    comparisons, _, _ = compare_full(mod.build_circuit(spec, devices, res.summary), res.summary)
    assert comparisons
    bad = [c for c in comparisons if not c.ok]
    assert not bad, "\n".join(
        f"{c.quantity}: analítico {c.analytic.value:.5g}, simulado {c.simulated.value:.5g} "
        f"({c.error_pct:.2f} % > {c.tolerance_pct} %)"
        for c in bad
    )
