"""AS-RET-03: DM-RETC1 with the real firing circuit × ngspice.

The ideal gate pulses of AS-RET-02 are replaced by the sized firing circuit (synchronised RC
ramp, LM393 comparators with V_OL as on resistance, BC337 switch, MOC3021 phototriac couplers
firing each SCR from its anode, SCRs that latch on the gate current I_GT). Checks: the firing
angle the circuit produces (2 %), ramp peak and LED current (1 %) and, because the SCRs now
fire from that circuit, the same load and input quantities of AS-RET-02 (1 %, PF 2 %, THD 5 %).
Measured on 2026-11-24: angle within 0,06 %, worst load quantity 0,11 %.
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
    "semi_continua": dict(topology="semicontrolada", alpha_nom=q(60, "deg")),
    "meia_onda_rl": dict(topology="meia_onda", P=q(25, "W")),
    "meia_onda_roda_livre": dict(
        topology="meia_onda", freewheel=True, P=q(120, "W"), alpha_nom=q(90, "deg")
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_as_ret_03(firing_catalogue, name):
    repo = firing_catalogue
    spec = Retc1Spec(firing=True, **CASES[name])
    res, devices = run(
        MOD,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    assert "fd_RG" in res.summary
    circuit = MOD.build_circuit(spec, devices, res.summary)
    assert "VG1" not in circuit.netlist
    comparisons, _ = compare(circuit, res.summary)
    assert {c.quantity for c in comparisons} >= {
        "Ângulo de disparo produzido pelo circuito",
        "Pico da rampa em C1",
        "Corrente nos LEDs dos optoacopladores",
    }
    bad = [c for c in comparisons if not c.ok]
    assert not bad, "\n".join(
        f"{c.quantity}: analítico {c.analytic.value:.5g}, simulado {c.simulated.value:.5g} "
        f"({c.error_pct:.2f} % > {c.tolerance_pct} %)"
        for c in bad
    )
