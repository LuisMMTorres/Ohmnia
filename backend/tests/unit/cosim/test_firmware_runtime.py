"""Real Arduino AVR compiler output: GPIO, ADC, millis/delay, PWM and UART."""

import base64
from pathlib import Path

import pytest

from circuitos.cosim.firmware import FirmwareRuntime, engine_status
from circuitos.cosim.firmware_image import FirmwareImage

FIXTURES = Path(__file__).parents[2] / "fixtures" / "firmware"
pytestmark = pytest.mark.skipif(not engine_status()[0], reason="motor AVR8js/Node não instalado")


def compiled_image(short: str) -> FirmwareImage:
    board = {"uno": "arduino_uno", "nano": "arduino_nano", "mega": "arduino_mega"}[short]
    return FirmwareImage(
        board=board,
        filename=short + ".hex",
        data_base64=base64.b64encode((FIXTURES / (short + ".hex")).read_bytes()).decode(),
    )


@pytest.mark.parametrize("short", ["uno", "nano", "mega"])
def test_compiled_arduino_code_reads_inputs_adc_and_runs_pwm(short):
    rt = FirmwareRuntime(compiled_image(short))
    try:
        initial = rt.advance(0.02, {"D2": 5, "A0": 2.5})
        assert initial["states"]["D13"] == 1
        assert initial["serial"] and all(abs(int(row[1]) - 512) <= 1 for row in initial["serial"])
        samples = []
        serial = []
        for k in range(1, 1001):
            data = rt.advance(0.02 + k * 20e-6, {"D2": 0, "A0": 1.25})
            samples.append(data["states"]["D3"])
            serial += data["serial"]
        assert data["states"]["D13"] == 0
        assert serial and abs(int(serial[-1][1]) - 256) <= 1
        assert 0.44 < sum(v == 1 for v in samples) / len(samples) < 0.56
    finally:
        rt.close()
    assert rt.process.poll() is not None


def test_unsupported_spi_produces_an_explicit_error():
    # AVR instructions: LDI r16,0x40; OUT SPCR,r16; RJMP -1.
    # SPCR.SPE activates the interface (ATmega328P register map).
    raw = b":0600000000E40CBDFFCF7F\n:00000001FF\n"
    firmware = FirmwareImage(
        board="arduino_uno", filename="spi.hex", data_base64=base64.b64encode(raw).decode()
    )
    rt = FirmwareRuntime(firmware)
    try:
        with pytest.raises(ValueError, match="SPI"):
            rt.advance(0.001, {})
    finally:
        rt.close()
