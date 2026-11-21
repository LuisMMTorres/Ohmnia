"""Real Espressif Arduino 2.0.17 merged firmware, no physical board."""

import base64
from itertools import pairwise
from pathlib import Path

import pytest

from circuitos.cosim.esp32_firmware import Esp32Runtime
from circuitos.cosim.firmware import engine_status
from circuitos.cosim.firmware_image import FirmwareImage, load_image

FIXTURE = Path(__file__).parents[2] / "fixtures/firmware/esp32.bin"


def image(raw=None):
    return FirmwareImage(
        board="esp32_devkitc",
        filename="probe.merged.bin",
        data_base64=base64.b64encode(FIXTURE.read_bytes() if raw is None else raw).decode(),
    )


def test_merged_image_has_four_megabytes_without_changing_original():
    raw = FIXTURE.read_bytes()
    loaded = load_image(image(raw))
    assert len(loaded.flash) == 4 * 1024**2
    assert loaded.flash[: len(raw)] == raw
    assert loaded.architecture == "xtensa"


def test_corrupt_bootloader_and_application_only_are_rejected():
    raw = bytearray(FIXTURE.read_bytes())
    raw[0x1050] ^= 1
    with pytest.raises(ValueError, match=r"Checksum|SHA-256"):
        load_image(image(raw))
    with pytest.raises(ValueError, match="mesclado"):
        load_image(image(FIXTURE.read_bytes()[0x10000:]))


@pytest.mark.skipif(not engine_status("esp32_devkitc")[0], reason="motor ESP32/Windows ausente")
def test_compiled_gpio_adc_pwm_and_uart():
    rt = Esp32Runtime(image())
    try:
        first = rt.advance(0.33, {"IO4": 3.3, "IO34": 1.65})
        assert first["states"]["IO2"] == 1
        assert any(row[1] in ("2047", "2048") for row in first["serial"])
        states, rows = [], []
        for k in range(1, 501):
            data = rt.advance(0.33 + k * 20e-6, {"IO4": 0, "IO34": 0.825})
            states.append(data["states"]["IO18"])
            rows.extend(data["serial"])
        assert data["states"]["IO2"] == 0
        assert any(row[1] in ("1023", "1024") for row in rows)
        assert 0.40 < sum(value == 1 for value in states) / len(states) < 0.60
        rising = sum(a != 1 and b == 1 for a, b in pairwise(states))
        assert 8 <= rising <= 12  # 1 kHz over a 10 ms window, sampled every 20 us
    finally:
        rt.close()
    assert rt.process.poll() is not None
