"""ESP32 classic merged flash, following Espressif esptool image/partition formats."""

from __future__ import annotations

import hashlib
import struct

from circuitos.cosim.firmware_image import LoadedImage


def load_esp32(raw: bytes, filename: str) -> LoadedImage:
    if not filename.lower().endswith(".bin") or not 0x10000 < len(raw) <= 4 * 1024**2:
        raise ValueError(
            "Use BIN mesclado de até 4 MiB, incluindo bootloader e tabela de partições"
        )

    def verify(offset: int, limit: int) -> None:
        if offset + 24 > len(raw) or raw[offset] != 0xE9:
            raise ValueError("Imagem ESP32 sem cabeçalho válido; exporte BIN mesclado")
        if struct.unpack_from("<H", raw, offset + 12)[0] != 0:
            raise ValueError("O firmware não foi compilado para ESP32 clássico (WROOM-32)")
        segments = raw[offset + 1]
        if not 1 <= segments <= 16 or raw[offset + 2] != 2:
            raise ValueError("Use imagem ESP32 com flash em modo DIO")
        cursor, checksum = offset + 24, 0xEF
        for _ in range(segments):
            if cursor + 8 > min(len(raw), limit):
                raise ValueError("Segmento ESP32 truncado")
            size = struct.unpack_from("<I", raw, cursor + 4)[0]
            cursor += 8
            if cursor + size > min(len(raw), limit):
                raise ValueError("Segmento ESP32 ultrapassa a partição")
            for byte in raw[cursor : cursor + size]:
                checksum ^= byte
            cursor += size
        end = (cursor + 16) // 16 * 16
        if end > min(len(raw), limit) or raw[end - 1] != checksum:
            raise ValueError("Checksum ESP32 inválido")
        if raw[offset + 23] and (
            end + 32 > min(len(raw), limit)
            or hashlib.sha256(raw[offset:end]).digest() != raw[end : end + 32]
        ):
            raise ValueError("SHA-256 ESP32 inválido")

    verify(0x1000, 0x8000)
    apps = 0
    partition_bytes = bytearray()
    intervals: list[tuple[int, int]] = []
    for offset in range(0x8000, min(len(raw), 0x9000), 32):
        entry = raw[offset : offset + 32]
        magic = struct.unpack_from("<H", entry)[0]
        if magic == 0xFFFF:
            break
        if magic == 0xEBEB:
            if hashlib.md5(partition_bytes).digest() != entry[16:32]:
                raise ValueError("MD5 da tabela de partições inválido")
            break
        if magic != 0x50AA:
            raise ValueError("Tabela de partições ESP32 inválida (esperada em 0x8000)")
        partition_bytes.extend(entry)
        start, size = struct.unpack_from("<II", entry, 4)
        if start < 0x9000 or not size or start + size > 4 * 1024**2:
            raise ValueError("Partição ESP32 fora da flash de 4 MiB")
        if any(start < end and start + size > previous for previous, end in intervals):
            raise ValueError("Partições ESP32 sobrepostas")
        intervals.append((start, start + size))
        if entry[2] == 0 and start < len(raw) and raw[start] != 0xFF:
            verify(start, start + size)
            apps += 1
    if not apps:
        raise ValueError("BIN mesclado sem aplicação executável na tabela de partições")
    # QEMU infers the physical flash capacity from the file size. Keep the
    # DevKitC/WROOM-32 profile at 4 MiB even for short merged exports.
    return LoadedImage(
        raw.ljust(4 * 1024**2, b"\xff"), 0x1000, hashlib.sha256(raw).hexdigest(), len(raw), "xtensa"
    )
