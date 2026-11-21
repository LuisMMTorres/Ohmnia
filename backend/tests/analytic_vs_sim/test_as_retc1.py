"""AS-RET-02: DM-RETC1 analytic design × ngspice (SCR latch and constant-drop diodes).

Cases: full bridge (continuous, discontinuous, RLE), semicontrolled (continuous and RLE
discontinuous), half wave (RL without freewheeling, RL with freewheeling diode). Each case runs
the full design flow (selection from the reviewed catalogue), builds the circuit and compares
mean and RMS load voltage, mean load current, RMS secondary current (1 %), power factor (2 %)
and THD of the input current (5 %). Measured on 2026-11-14: worst error 0,03 %.
"""

import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.retc1 import Retc1Module, Retc1Spec
from circuitos.design.verify import compare
from circuitos.selection.derating import DeratingPolicy

pytestmark = pytest.mark.ngspice

MOD = Retc1Module()


def q(v, u):
    return QuantityModel(value=v, unit=u)


CASES = {
    "ponte_continua": dict(topology="ponte"),
    "ponte_descontinua": dict(topology="ponte", L=q(5, "mH")),
    "ponte_rle": dict(topology="ponte", E=q(40, "V"), L=q(20, "mH")),
    "semi_continua": dict(topology="semicontrolada", alpha_nom=q(60, "deg")),
    "semi_rle": dict(
        topology="semicontrolada", E=q(30, "V"), L=q(10, "mH"), alpha_nom=q(60, "deg")
    ),
    "meia_onda_rl": dict(topology="meia_onda", P=q(25, "W")),
    "meia_onda_roda_livre": dict(topology="meia_onda", freewheel=True, P=q(120, "W")),
}


@pytest.mark.parametrize("name", list(CASES))
def test_as_ret_02(reviewed_catalogue, name):
    repo = reviewed_catalogue
    spec = Retc1Spec(**CASES[name])
    res, devices = run(
        MOD,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    circuit = MOD.build_circuit(spec, devices, res.summary)
    comparisons, _ = compare(circuit, res.summary)
    bad = [c for c in comparisons if not c.ok]
    assert not bad, "\n".join(
        f"{c.quantity}: analítico {c.analytic.value:.5g}, simulado {c.simulated.value:.5g} "
        f"({c.error_pct:.2f} % > {c.tolerance_pct} %)"
        for c in bad
    )
