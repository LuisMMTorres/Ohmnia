"""Bounded firmware loading. Files contain AVR instructions, never host executables."""

from __future__ import annotations

import base64
import binascii
import hashlib
import struct
from dataclasses import dataclass

from pydantic import BaseModel, Field

AVR_FLASH = {"arduino_uno": 32768, "arduino_nano": 32768, "arduino_mega": 262144}
MAX_FILE_BYTES = 1024 * 1024


class FirmwareImage(BaseModel):
    board: str = Field(max_length=40)
    filename: str = Field(min_length=1, max_length=200)
    data_base64: str = Field(min_length=1, max_length=MAX_FILE_BYTES * 4 // 3 + 4)


@dataclass(frozen=True)
class LoadedImage:
    flash: bytes
    entry: int
    sha256: str
    size: int


def load_image(image: FirmwareImage, board: str | None = None) -> LoadedImage:
    if board is not None and image.board != board:
        raise ValueError("O firmware foi associado a outra placa. Importe-o na placa correta.")
    if image.board not in AVR_FLASH:
        raise ValueError("A execução de firmware desta placa ainda não está disponível.")
    try:
        raw = base64.b64decode(image.data_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Arquivo de firmware inválido (base64)") from exc
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("O arquivo de firmware deve ter entre 1 byte e 1 MiB")
    flash = bytearray(b"\xff" * AVR_FLASH[image.board])
    used: set[int] = set()

    def write(address: int, data: bytes) -> None:
        if address < 0 or address + len(data) > len(flash):
            raise ValueError("O firmware ultrapassa a memória flash da placa selecionada")
        for i, value in enumerate(data, address):
            if i in used:
                raise ValueError("Regiões sobrepostas no arquivo de firmware")
            used.add(i)
            flash[i] = value

    suffix = image.filename.rsplit(".", 1)[-1].lower()
    entry = 0
    if suffix == "hex":
        try:
            lines = raw.decode("ascii").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError("Intel HEX deve conter texto ASCII") from exc
        upper, end = 0, False
        for line in lines:
            if not line.strip():
                continue
            if end or not line.startswith(":"):
                raise ValueError("Registro Intel HEX inválido ou após o fim do arquivo")
            try:
                row = bytes.fromhex(line[1:])
            except ValueError as exc:
                raise ValueError("Registro Intel HEX inválido") from exc
            if len(row) < 5 or len(row) != row[0] + 5 or sum(row) & 255:
                raise ValueError("Tamanho ou checksum Intel HEX inválido")
            address, kind, data = int.from_bytes(row[1:3], "big"), row[3], row[4:-1]
            if kind == 0:
                write(upper + address, data)
            elif kind == 1 and not data and address == 0:
                end = True
            elif kind in (2, 4) and len(data) == 2 and address == 0:
                upper = int.from_bytes(data, "big") << (4 if kind == 2 else 16)
            elif kind == 5 and len(data) == 4 and address == 0:
                entry = int.from_bytes(data, "big")
            else:
                raise ValueError(f"Tipo de registro Intel HEX não suportado: {kind}")
        if not end:
            raise ValueError("Falta o registro de fim do Intel HEX")
    elif suffix == "elf":
        if len(raw) < 52 or raw[:7] != b"\x7fELF\x01\x01\x01":
            raise ValueError("Use um ELF AVR de 32 bits, little-endian")
        if struct.unpack_from("<H", raw, 18)[0] != 83:
            raise ValueError("O ELF não foi compilado para AVR")
        architecture = struct.unpack_from("<I", raw, 36)[0] & 0x7F
        expected = 6 if image.board == "arduino_mega" else 5
        if architecture not in (0, expected):
            raise ValueError("A arquitetura do ELF não corresponde à placa selecionada")
        entry, phoff = struct.unpack_from("<II", raw, 24)
        phsize, phnum = struct.unpack_from("<HH", raw, 42)
        if phsize != 32 or not phnum or phoff + phsize * phnum > len(raw):
            raise ValueError("Tabela de segmentos ELF inválida")
        for k in range(phnum):
            kind, offset, _, physical, size, _, _, _ = struct.unpack_from(
                "<8I", raw, phoff + k * phsize
            )
            if kind != 1 or not size or physical >= 0x800000:
                continue  # AVR EEPROM/SRAM segments are not program flash
            if offset + size > len(raw):
                raise ValueError("Segmento ELF truncado")
            write(physical, raw[offset : offset + size])
    else:
        raise ValueError("Para esta placa, exporte o firmware .hex ou .elf pela IDE")
    if not used or entry not in used or entry % 2:
        raise ValueError("O firmware não contém um ponto de entrada AVR válido")
    return LoadedImage(bytes(flash), entry, hashlib.sha256(raw).hexdigest(), len(used))
