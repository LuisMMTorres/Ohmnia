"""Firmware/circuit feedback: ADC input and the output pin's existing 25-ohm model."""

import base64
from pathlib import Path

import numpy as np
import pytest

from circuitos.cosim.firmware import engine_status
from circuitos.cosim.firmware_image import FirmwareImage
from circuitos.schematic.library import symbol
from circuitos.schematic.runs import SchematicPlan
from circuitos.simulation.backend import SharedNgspiceBackend
from tests.unit.schematic.helpers import Builder

pytestmark = pytest.mark.ngspice


@pytest.mark.skipif(not engine_status()[0], reason="motor AVR8js/Node não instalado")
def test_firmware_reads_the_circuit_and_drives_a_loaded_output():
    if not SharedNgspiceBackend.available():
        pytest.skip("ngspice ausente")
    raw = (Path(__file__).parents[1] / "fixtures/firmware/uno.hex").read_bytes()
    b = Builder("Firmware AVR e circuito")
    nodes = {"GND": "0", "5V": "vcc", "D2": "input", "D13": "out", "A0": "analog"}
    c = b.add(
        "arduino_uno", "U1", [nodes.get(p.name, "nc_" + p.name) for p in symbol("arduino_uno").pins]
    )
    c.firmware = FirmwareImage(
        board=c.kind, filename="uno.hex", data_base64=base64.b64encode(raw).decode()
    )
    c.params["program"] = "deliberately invalid source: the firmware must run instead"
    b.add("vdc", "VA", ["analog", "0"], dc="2.5")
    b.add("vpwl", "VI", ["input", "0"], points="0 5 20m 5 20.001m 0")
    b.add("resistor", "RL", ["out", "0"], value="1k")
    b.analysis("tran", tstop="35m", tmax="10u")
    result = SchematicPlan(b.sch, {}).execute(SharedNgspiceBackend())
    plot = next(p for p in result.plots if p.kind == "tran")
    t = plot.vectors[plot.scale].data
    y = plot.vectors["v(out)"].data
    # Existing didactic pin model: 5 V with Rout=25 ohm into a 1 kohm load.
    assert np.mean(y[(t > 0.01) & (t < 0.019)]) == pytest.approx(5 * 1000 / 1025, rel=0.002)
    assert abs(float(y[-1])) < 0.01
    serial = result.summary["cosim"]["serial"]["U1"]
    assert serial and all(abs(int(row[1]) - 512) <= 1 for row in serial)


@pytest.mark.parametrize("kind", ["rpi_pico", "rpi_pico2"])
def test_pico_firmware_voltage_feedback(kind):
    if not SharedNgspiceBackend.available() or not engine_status(kind)[0]:
        pytest.skip("ngspice ou motor Pico ausente")
    short = kind.removeprefix("rpi_")
    raw = (Path(__file__).parents[1] / f"fixtures/firmware/{short}.uf2").read_bytes()
    b = Builder("Firmware Pico e circuito")
    nodes = {"GND": "0", "3V3": "vcc", "GP2": "input", "GP3": "out", "GP26": "analog"}
    c = b.add(kind, "U1", [nodes.get(p.name, "nc_" + p.name) for p in symbol(kind).pins])
    c.firmware = FirmwareImage(
        board=kind, filename=short + ".uf2", data_base64=base64.b64encode(raw).decode()
    )
    c.params["program"] = "invalid source: execute compiled firmware"
    b.add("vdc", "VA", ["analog", "0"], dc="1.65")
    b.add("vpwl", "VI", ["input", "0"], points="0 3.3 20m 3.3 20.001m 0")
    b.add("resistor", "RL", ["out", "0"], value="1k")
    b.analysis("tran", tstop="35m", tmax="10u")
    result = SchematicPlan(b.sch, {}).execute(SharedNgspiceBackend())
    plot = next(p for p in result.plots if p.kind == "tran")
    t, y = plot.vectors[plot.scale].data, plot.vectors["v(out)"].data
    assert np.mean(y[(t > 0.01) & (t < 0.019)]) == pytest.approx(3.3 * 1000 / 1025, rel=0.002)
    assert abs(float(y[-1])) < 0.01
    serial = result.summary["cosim"]["serial"]["U1"]
    assert serial and all(abs(int(row[1].split(": ")[-1]) - 2048) <= 1 for row in serial)


def test_esp32_firmware_voltage_feedback():
    if not SharedNgspiceBackend.available() or not engine_status("esp32_devkitc")[0]:
        pytest.skip("ngspice ou motor ESP32 ausente")
    kind = "esp32_devkitc"
    raw = (Path(__file__).parents[1] / "fixtures/firmware/esp32.bin").read_bytes()
    b = Builder("Firmware ESP32 e circuito")
    nodes = {"GND": "0", "3V3": "vcc", "IO4": "input", "IO2": "out", "IO34": "analog"}
    c = b.add(kind, "U1", [nodes.get(p.name, "nc_" + p.name) for p in symbol(kind).pins])
    c.firmware = FirmwareImage(
        board=kind, filename="esp32.merged.bin", data_base64=base64.b64encode(raw).decode()
    )
    b.add("vdc", "VA", ["analog", "0"], dc="1.65")
    b.add("vpwl", "VI", ["input", "0"], points="0 3.3 340m 3.3 340.001m 0")
    b.add("resistor", "RL", ["out", "0"], value="1k")
    b.analysis("tran", tstop="350m", tmax="10u")
    result = SchematicPlan(b.sch, {}).execute(SharedNgspiceBackend())
    plot = next(p for p in result.plots if p.kind == "tran")
    t, y = plot.vectors[plot.scale].data, plot.vectors["v(out)"].data
    assert np.mean(y[(t > 0.333) & (t < 0.339)]) == pytest.approx(3.3 * 1000 / 1016.5, rel=0.002)
    assert abs(float(y[-1])) < 0.01
    serial = result.summary["cosim"]["serial"]["U1"]
    assert any(row[1] in ("2047", "2048") for row in serial)
