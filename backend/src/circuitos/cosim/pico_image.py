"""Strict flash-only UF2/ELF loader, following raspberrypi/pico-sdk boot/uf2.h."""

from __future__ import annotations

import hashlib
import struct

from circuitos.cosim.firmware_image import LoadedImage

PICO_FLASH = {"rpi_pico": 2 * 1024**2, "rpi_pico2": 4 * 1024**2}
BASE = 0x10000000


def load_pico(raw: bytes, filename: str, board: str) -> LoadedImage:
    flash = bytearray(b"\xff" * PICO_FLASH[board])
    used = bytearray(len(flash))
    architecture = "arm"
    entry = BASE

    def write(address: int, data: bytes) -> None:
        offset = address - BASE
        if offset < 0 or offset + len(data) > len(flash):
            raise ValueError("Firmware fora da flash da placa; imagens em RAM não são suportadas")
        if any(used[offset : offset + len(data)]):
            raise ValueError("Regiões sobrepostas no firmware")
        flash[offset : offset + len(data)] = data
        used[offset : offset + len(data)] = b"\x01" * len(data)

    if filename.lower().endswith(".uf2"):
        if not raw or len(raw) % 512:
            raise ValueError("UF2 truncado: são necessários blocos completos de 512 bytes")
        seen: set[int] = set()
        count = len(raw) // 512
        # Arduino-Pico's RP2350-E10 download workaround is not program flash.
        # Accept only its exact legacy dummy block, never arbitrary absolute writes.
        first = struct.unpack_from("<8I", raw)
        workaround = (
            board == "rpi_pico2"
            and first == (0x0A324655, 0x9E5D5157, 0x2000, 0x10FFFF00, 256, 0, 2, 0xE48BFF57)
            and raw[32:288] == b"\xef" * 256
        )
        if workaround:
            count -= 1
        expected_family = None
        for offset in range(0, len(raw), 512):
            magic0, magic1, flags, address, size, number, total, family = struct.unpack_from(
                "<8I", raw, offset
            )
            if (magic0, magic1, struct.unpack_from("<I", raw, offset + 508)[0]) != (
                0x0A324655,
                0x9E5D5157,
                0x0AB16F30,
            ):
                raise ValueError("Assinatura UF2 inválida")
            if workaround and offset == 0:
                continue
            if address % 256:
                raise ValueError("Endereço UF2 sem alinhamento de 256 bytes")
            # Deliberately reject containers, RAM images and optional extensions.
            if flags != 0x2000 or size != 256:
                raise ValueError(
                    "Use UF2 de flash, com identificação da família e blocos de 256 bytes"
                )
            families = {0xE48BFF56} if board == "rpi_pico" else {0xE48BFF59, 0xE48BFF5A}
            if family not in families or expected_family not in (None, family):
                raise ValueError("A família UF2 não corresponde à placa ou arquitetura selecionada")
            expected_family = family
            architecture = "riscv" if family == 0xE48BFF5A else "arm"
            if total != count or number >= count or number in seen:
                raise ValueError("Sequência de blocos UF2 incompleta ou duplicada")
            seen.add(number)
            write(address, raw[offset + 32 : offset + 32 + size])
    elif filename.lower().endswith(".elf"):
        if len(raw) < 52 or raw[:7] != b"\x7fELF\x01\x01\x01":
            raise ValueError("Use ELF de 32 bits little-endian")
        machine = struct.unpack_from("<H", raw, 18)[0]
        if machine != 40 and not (board == "rpi_pico2" and machine == 243):
            raise ValueError("Arquitetura ELF incompatível com esta placa")
        architecture = "riscv" if machine == 243 else "arm"
        entry, phoff = struct.unpack_from("<II", raw, 24)
        phsize, phnum = struct.unpack_from("<HH", raw, 42)
        if phsize != 32 or not phnum or phoff + phsize * phnum > len(raw):
            raise ValueError("Tabela ELF inválida")
        for k in range(phnum):
            kind, offset, _, physical, size, _, _, _ = struct.unpack_from(
                "<8I", raw, phoff + k * 32
            )
            if kind != 1 or not size:
                continue
            if offset + size > len(raw):
                raise ValueError("Segmento ELF truncado")
            write(physical, raw[offset : offset + size])
        if not BASE <= (entry & ~1) < BASE + len(flash) or not used[(entry & ~1) - BASE]:
            raise ValueError("Entrada ELF fora da imagem de flash")
    else:
        raise ValueError("Para Pico/Pico 2, exporte firmware .uf2 ou .elf")
    if not used[0]:
        raise ValueError("A imagem não contém o início de flash necessário à inicialização")
    return LoadedImage(
        bytes(flash), entry, hashlib.sha256(raw).hexdigest(), sum(used), architecture
    )
