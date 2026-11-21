"""UF2 target isolation and real compiled Pico firmware integration."""

import base64
import struct
from itertools import pairwise
from pathlib import Path

import pytest

from circuitos.cosim.firmware import FirmwareRuntime, engine_status
from circuitos.cosim.firmware_image import FirmwareImage, load_image


def uf2(family=0xE48BFF56, address=0x10000000, number=0, total=1):
    block = bytearray(512)
    struct.pack_into(
        "<8I", block, 0, 0x0A324655, 0x9E5D5157, 0x2000, address, 256, number, total, family
    )
    struct.pack_into("<I", block, 508, 0x0AB16F30)
    return block


def image(raw, board="rpi_pico", name="probe.uf2"):
    return FirmwareImage(board=board, filename=name, data_base64=base64.b64encode(raw).decode())


@pytest.mark.parametrize(
    "board,family,architecture",
    [
        ("rpi_pico", 0xE48BFF56, "arm"),
        ("rpi_pico2", 0xE48BFF59, "arm"),
        ("rpi_pico2", 0xE48BFF5A, "riscv"),
    ],
)
def test_uf2_family_selects_architecture(board, family, architecture):
    loaded = load_image(image(uf2(family), board))
    assert loaded.architecture == architecture
    assert loaded.size == 256


@pytest.mark.parametrize(
    "raw,match",
    [
        (uf2()[:-1], "truncado"),
        (uf2(0xE48BFF59), "família"),
        (uf2(total=2), "incompleta"),
        (uf2(address=0x20000000), "RAM"),
        (uf2(address=0x10200000), "flash"),
        (uf2(address=0x10000001), "alinhamento"),
        (uf2(total=2) + uf2(total=2), "duplicada"),
    ],
)
def test_invalid_uf2_is_rejected(raw, match):
    with pytest.raises(ValueError, match=match):
        load_image(image(raw))


@pytest.mark.parametrize("short", ["pico", "pico2", "pico2-riscv"])
def test_compiled_gpio_adc_and_pwm(short):
    board = "rpi_" + short.split("-")[0]
    if not engine_status(board)[0]:
        pytest.skip("motor Pico/Node ausente")
    raw = (Path(__file__).parents[2] / "fixtures/firmware" / (short + ".uf2")).read_bytes()
    runtime = FirmwareRuntime(image(raw, board))
    try:
        first = runtime.advance(0.1, {"GP2": 3.3, "GP26": 1.65})
        assert first["states"]["GP3"] == 1
        assert any("2048" in row[1] or "2047" in row[1] for row in first["serial"])
        values = []
        rows = []
        for k in range(1, 501):
            data = runtime.advance(0.1 + k * 20e-6, {"GP2": 0, "GP26": 0.825})
            values.append(data["states"]["GP4"])
            rows.extend(data["serial"])
        assert data["states"]["GP3"] == 0
        assert any("1024" in row[1] or "1023" in row[1] for row in rows)
        assert 0.40 < sum(v == 1 for v in values) / len(values) < 0.60
        rising = sum(a != 1 and b == 1 for a, b in pairwise(values))
        assert 8 <= rising <= 12  # 1 kHz over a 10 ms window, sampled every 20 us
    finally:
        runtime.close()
    assert runtime.process.poll() is not None
