"""AS-RET-03: DM-RET3 analytic design × ngspice.

The analysis assumes a constant load current; the simulated load is R in series with
L = 30·R/ω (and E), so a small current ripple remains; every node has 10 MΩ to ground
(``.options rshunt``) so the series bridges never float. Compared: mean output voltage and
load current (1 %), RMS line current and power factor (2 %), THD of the line current (10 %:
the residual ripple of Io changes the
harmonics). Measured on 2026-11-14: worst error 0,25 %.
"""

import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.ret3 import Ret3Module, Ret3Spec
from circuitos.design.verify import compare
from circuitos.selection.derating import DeratingPolicy

pytestmark = pytest.mark.ngspice

MOD = Ret3Module()
CASES = {
    "6p_controlado": dict(pulses=6),
    "6p_diodos": dict(pulses=6, controlled=False),
    "6p_sem_Ls": dict(pulses=6, Ls=QuantityModel(value=0, unit="mH")),
    "3p_controlado": dict(pulses=3, P=QuantityModel(value=1500, unit="W")),
    "12p_controlado": dict(pulses=12, Vsec=QuantityModel(value=180, unit="V")),
}


@pytest.mark.parametrize("name", list(CASES))
def test_as_ret_03(reviewed_catalogue, name):
    repo = reviewed_catalogue
    spec = Ret3Spec(**CASES[name])
    res, devices = run(
        MOD,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    comparisons, _ = compare(MOD.build_circuit(spec, devices, res.summary), res.summary)
    bad = [c for c in comparisons if not c.ok]
    assert not bad, "\n".join(
        f"{c.quantity}: analítico {c.analytic.value:.5g}, simulado {c.simulated.value:.5g} "
        f"({c.error_pct:.2f} % > {c.tolerance_pct} %)"
        for c in bad
    )
