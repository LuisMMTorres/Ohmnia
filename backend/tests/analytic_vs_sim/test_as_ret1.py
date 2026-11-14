"""AS-RET-01: DM-RET1 analytic design × ngspice, for every topology and filter.

The design (with the diodes the engine selected from the reviewed catalogue) is turned into its
circuit (``Ret1Module.build_circuit``: the same constant-drop diode, ideal source, L and C) and
simulated; the last period is compared with the analytic summary on every ``SimCheck`` of the
circuit: mean, RMS and peak-to-peak load voltage, mean diode current, input power factor and
THD of the input current.

Tolerances (in each SimCheck): 1 % for mean and RMS values and the diode current, 2 % for the
ripple and the power factor, 5 % for the THD, which depends on the time step of the run.
Measured on 2026-11-14: worst errors 0,10 % (ripple), 1,2 % (power factor, center tap π),
0,24 % (THD, LC).
"""

import pytest

from circuitos.core.units import QuantityModel
from circuitos.design.engine import run
from circuitos.design.plugins.ret1 import Ret1Module, Ret1Spec
from circuitos.design.verify import compare
from circuitos.selection.derating import DeratingPolicy

pytestmark = pytest.mark.ngspice

MOD = Ret1Module()
CASES = [
    (t, f)
    for t in ("meia_onda", "center_tap", "ponte")
    for f in ("nenhum", "C", "LC", "pi")
    if not (t == "meia_onda" and f in ("LC", "pi"))
]


def _check(repo, spec):
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
    assert len(comparisons) == 6


@pytest.mark.parametrize("topo,flt", CASES)
def test_as_ret_01_default_point(reviewed_catalogue, topo, flt):
    _check(reviewed_catalogue, Ret1Spec(topology=topo, filter=flt))


@pytest.mark.parametrize("topo,flt", [("ponte", "C"), ("center_tap", "LC"), ("ponte", "pi")])
def test_as_ret_01_other_point(reviewed_catalogue, topo, flt):
    """24 V, 2 A, 10 % ripple, 220 V / 50 Hz."""
    spec = Ret1Spec(
        topology=topo,
        filter=flt,
        Vin=QuantityModel(value=220, unit="V"),
        f=QuantityModel(value=50, unit="Hz"),
        Vo=QuantityModel(value=24, unit="V"),
        Io=QuantityModel(value=2, unit="A"),
        ripple_pct=10,
    )
    _check(reviewed_catalogue, spec)
