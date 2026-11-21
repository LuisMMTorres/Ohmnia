"""Firmware containers: corruption and target mismatches must fail before simulation."""

import base64
import struct

import pytest

from circuitos.cosim.firmware_image import FirmwareImage, load_image
from circuitos.schematic.model import Component, Schematic


def record(address: int, kind: int, payload: bytes = b"") -> str:
    data = bytes([len(payload), address >> 8, address & 255, kind]) + payload
    return ":" + (data + bytes([-sum(data) & 255])).hex().upper()


def image(data: bytes, name: str = "test.hex", board: str = "arduino_uno") -> FirmwareImage:
    return FirmwareImage(board=board, filename=name, data_base64=base64.b64encode(data).decode())


def test_hex_checks_checksum_eof_and_flash_bounds():
    data = (record(0, 0, b"\x00\x00\xff\xcf") + "\n" + record(0, 1)).encode()
    assert load_image(image(data)).flash[:4] == b"\x00\x00\xff\xcf"
    corrupt = bytearray(data)
    corrupt[10] = ord("1")
    with pytest.raises(ValueError, match="checksum"):
        load_image(image(bytes(corrupt)))
    with pytest.raises(ValueError, match="fim"):
        load_image(image(record(0, 0, b"\x00\x00").encode()))
    with pytest.raises(ValueError, match="memória"):
        load_image(image((record(0x8000, 0, b"\x00\x00") + "\n" + record(0, 1)).encode()))


def test_wrong_board_and_non_avr_elf_are_rejected():
    data = (record(0, 0, b"\x00\x00") + "\n" + record(0, 1)).encode()
    with pytest.raises(ValueError, match="placa"):
        load_image(image(data), "arduino_mega")
    elf = bytearray(84)
    elf[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHIIIIIHHHHHH", elf, 16, 2, 40, 1, 0, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    with pytest.raises(ValueError, match="AVR"):
        load_image(image(bytes(elf), "arm.elf"))


def test_hex_overlaps_and_trailing_records_are_rejected():
    for records in (
        [record(0, 0, b"\x00"), record(0, 0, b"\x01"), record(0, 1)],
        [record(0, 0, b"\x00"), record(0, 1), record(1, 0, b"\x01")],
    ):
        with pytest.raises(ValueError):
            load_image(image("\n".join(records).encode()))


def test_other_architectures_have_an_explicit_status():
    with pytest.raises(ValueError, match="mesclado"):
        load_image(image(b"firmware", "test.bin", "esp32_devkitc"))


def test_project_preserves_firmware_and_the_previous_source():
    raw = (record(0, 0, b"\x00\x00") + "\n" + record(0, 1)).encode()
    c = Component(
        id="u",
        kind="arduino_uno",
        ref="U1",
        x=0,
        y=0,
        params={"program": "void setup() {} void loop() {}"},
        firmware=image(raw),
    )
    restored = Schematic.model_validate_json(Schematic(components=[c]).model_dump_json())
    assert restored.components[0].firmware == c.firmware
    assert restored.components[0].params == c.params
    with pytest.raises(ValueError, match="outra placa"):
        Component.model_validate({**c.model_dump(), "kind": "arduino_nano"})


def test_elf_uses_flash_load_addresses_and_checks_avr_subarchitecture():
    elf = bytearray(122)
    elf[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHIIIIIHHHHHH", elf, 16, 2, 83, 1, 0, 52, 0, 5, 52, 32, 2, 0, 0, 0)
    struct.pack_into("<8I", elf, 52, 1, 116, 0, 0, 4, 4, 5, 2)
    struct.pack_into("<8I", elf, 84, 1, 120, 0x800100, 4, 2, 2, 6, 1)
    elf[116:] = b"\x00\x00\xff\xcf\x12\x34"
    assert load_image(image(bytes(elf), "program.elf")).flash[:6] == elf[116:]
    with pytest.raises(ValueError, match="arquitetura"):
        load_image(image(bytes(elf), "program.elf", "arduino_mega"))
