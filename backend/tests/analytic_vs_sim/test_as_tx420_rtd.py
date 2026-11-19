"""AS-TX: 4-20 mA head transmitter for a three-wire RTD against its closed form.

Rule 4: the SPICE model must agree with the equations it implements.

* RTD: R(T) = R0 (1 + A T + B T²), IEC 60751 (Callendar-Van Dusen for T ≥ 0 °C), A and B of the
  standard (the defaults of the symbol), inverted for T.
* Three-wire connection: with excitation I out of terminal 1 and back into terminal 2, and
  terminal 3 as a sense lead with no current, R_med = (V13 − V32)/I = R + R_fio1 − R_fio2.
* Loop current: 4 mA + 16 mA (T − T_ini)/(T_fim − T_ini).

Tolerance: 0,1 % on the loop current (the model is algebraic; the margin covers ngspice's
default relative tolerance).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from circuitos.schematic.model import Analysis
from circuitos.schematic.runs import SchematicPlan
from tests.unit.schematic.helpers import Builder

pytestmark = pytest.mark.ngspice

A, B, R0 = 3.9083e-3, -5.775e-7, 100.0


@pytest.fixture(scope="module")
def backend():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    return SharedNgspiceBackend()


def _rtd(t: float) -> float:
    return R0 * (1 + A * t + B * t * t)


def _temp(r: float) -> float:
    return (-A + math.sqrt(A * A - 4 * B * (1 - r / R0))) / (2 * B)


def _loop(lead1: float, lead2: float, temp: float, backend) -> float:  # type: ignore[no-untyped-def]
    b = Builder("tx-rtd")
    b.add("vdc", "V1", ["p24", "0"], dc="24")
    b.add("tx420_rtd", "TT1", ["p24", "ai", "t1", "t2", "t3"], lo="0", hi="100")
    b.add("resistor", "RL", ["ai", "0"], value="250")  # PLC input
    b.add("resistor", "RW1", ["t1", "x"], value=str(lead1))
    b.add("resistor", "RW2", ["y", "t2"], value=str(lead2))
    b.add("resistor", "RW3", ["y", "t3"], value=str(lead2))
    b.add("pt100", "RT1", ["x", "y"], temp=str(temp))
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "1m", "tmax": "0.1m"})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    return float(np.asarray(tran.vectors["v(ai)"].data)[-1]) / 250


def test_as_tx_01_three_wires_cancel_equal_leads(backend):
    """AS-TX-01: Pt100 at 50 °C, 5 Ω in each lead, range 0 to 100 °C → 12 mA."""
    assert _loop(5, 5, 50, backend) == pytest.approx(12e-3, rel=1e-3)


def test_as_tx_02_unequal_leads_leave_their_difference(backend):
    """AS-TX-02: leads of 6 Ω and 5 Ω: the transmitter reads R(50 °C) + 1 Ω."""
    t_read = _temp(_rtd(50) + 1)
    expected = 4e-3 + 16e-3 * t_read / 100
    assert t_read == pytest.approx(52.60, abs=0.01)  # about 2,6 °C high
    assert _loop(6, 5, 50, backend) == pytest.approx(expected, rel=1e-3)
