"""Digital sensors, light indicators and stress limits share the same netlist."""

from circuitos.schematic.netlist import build_netlist
from tests.unit.schematic.helpers import Builder


def test_digital_sensor_and_led_keep_their_simulation_metadata():
    b = Builder("digital sensor with a light indicator")
    b.add("vdc", "V1", ["vcc", "0"], dc="5")
    b.add("resistor", "RP", ["vcc", "data"], value="4.7k")
    b.add("dht22", "U1", ["vcc", "data", "0"])
    b.add("resistor", "R1", ["vcc", "anode"], value="1k", p_rated="0.25")
    b.add("led", "D1", ["anode", "0"])
    b.analysis("tran", tstop="1m")

    netlist = build_netlist(b.sch)

    assert [sensor.ref for sensor in netlist.digital_sensors] == ["U1"]
    assert netlist.indicators["D1"].kind == "led"
    assert any(limit.ref == "R1" and limit.name == "P nominal" for limit in netlist.limits)
