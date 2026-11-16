"""Co-simulation with ngspice: programs and circuit in the same run."""

from __future__ import annotations

import numpy as np
import pytest

from circuitos.schematic.library import pin_defs
from circuitos.schematic.model import Analysis, Component
from circuitos.schematic.netlist import SchematicError
from circuitos.schematic.runs import SchematicPlan
from tests.unit.schematic.helpers import Builder

pytestmark = pytest.mark.ngspice


@pytest.fixture(scope="module")
def backend():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    return SharedNgspiceBackend()


def add(b: Builder, kind: str, ref: str, nodes: dict[str, str], **params: str):  # type: ignore[no-untyped-def]
    probe = Component(id="p", kind=kind, ref=ref, x=0, y=0)
    pins = [p.name for p in pin_defs(probe)]
    return b.add(kind, ref, [nodes.get(p, f"nc_{ref}_{p}".lower()) for p in pins], **params)


BANG_BANG = """
int v; bool on = false;
void setup() { pinMode(9, OUTPUT); Serial.begin(9600); }
void loop() {
  v = analogRead(A0);                  // capacitor voltage, 0..1023
  if (v < 400) on = true;              // about 1,96 V
  if (v > 600) on = false;             // about 2,93 V
  digitalWrite(9, on ? HIGH : LOW);
  if (millis() % 50 == 0) Serial.println(v);
  delay(1);
}
"""


def test_arduino_on_off_control_of_an_rc(backend):
    b = Builder("liga-desliga com Arduino")
    add(b, "arduino_uno", "U1", {"GND": "0", "D9": "d9", "A0": "x"}, program=BANG_BANG)
    b.add("resistor", "R1", ["d9", "x"], value="1k")
    b.add("capacitor", "C1", ["x", "0"], value="10u")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "300m"})]
    res = SchematicPlan(b.sch).execute(backend)
    tran = next(p for p in res.plots if p.kind == "tran")
    t = tran.vectors[tran.scale].data
    vx = tran.vectors["v(x)"].data
    late = vx[t > 0.1]
    assert late.min() > 1.7 and late.max() < 3.2  # held inside the hysteresis band
    assert late.max() - late.min() > 0.7  # and it does switch
    d9 = tran.vectors["u1.d9"].data
    assert set(np.unique(np.round(d9[t > 0.1]))) == {0.0, 5.0}
    assert "u1.v" in tran.vectors
    serial = res.summary["cosim"]["serial"]["U1"]
    assert serial and all(line[1].isdigit() for line in serial)


def test_program_error_is_reported_with_time(backend):
    b = Builder("erro")
    add(
        b,
        "arduino_uno",
        "U1",
        {"GND": "0", "A0": "x"},
        program="int k = 0; void setup() {} void loop() { delay(10); k = 10 / (k - k); }",
    )
    b.add("resistor", "R1", ["x", "0"], value="1k")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "50m"})]
    with pytest.raises(SchematicError, match="divisão por zero"):
        SchematicPlan(b.sch).execute(backend)


def test_syntax_error_stops_before_ngspice(backend):
    b = Builder("sintaxe")
    add(b, "arduino_uno", "U1", {"GND": "0"}, program="void setup() { x = ; } void loop() {}")
    b.sch.analyses = [Analysis(kind="tran", params={"tstop": "10m"})]
    with pytest.raises(SchematicError, match="U1"):
        SchematicPlan(b.sch).execute(backend)
