"""Windows lockstep client for etree-esp32 v1.1.0.

Wire ABI: electronicstree/etree-esp32, esp32link.h v14 (MIT).
The separately installed GPL engine runs in its own process, without network flags.
"""

from __future__ import annotations

import ctypes
import mmap
import os
import struct
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from circuitos.cosim.firmware_image import FirmwareImage, load_image

SIZE, RING_SIZE, RING_A, RING_B = 787464, 16384, 776, 394120


def engine_path() -> Path | None:
    configured = os.environ.get("CIRCUITOS_ESP32_ENGINE")
    candidate = (
        Path(configured)
        if configured
        else (
            Path(__file__).resolve().parents[4]
            / "var/tools/esp32-engine-1.1.0/etree-esp32/etree-esp32.exe"
        )
    )
    return candidate if candidate.is_file() else None


class Esp32Runtime:
    def __init__(self, image: FirmwareImage):
        executable = engine_path()
        if os.name != "nt" or executable is None:
            raise ValueError(
                "Instale o motor ESP32 para Windows e configure CIRCUITOS_ESP32_ENGINE"
            )
        loaded = load_image(image)
        self.temp = tempfile.TemporaryDirectory(prefix="ohmnia-esp32-")
        self.process: subprocess.Popen[bytes] | None = None
        self.handles: list[Any] = []
        self.memory: mmap.mmap | None = None
        self.states: dict[str, int] = {}
        self.levels: dict[int, int] = {}
        self.directions: dict[int, int] = {}
        self.pulls: dict[int, int] = {}
        self.pwm: dict[int, tuple[int, int, int]] = {}
        self.pending: dict[int, bytearray] = {}
        self.last_time = 0.0
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.CreateEventW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_wchar_p,
        ]
        self.k.CreateEventW.restype = ctypes.c_void_p
        self.k.SetEvent.argtypes = [ctypes.c_void_p]
        self.k.CloseHandle.argtypes = [ctypes.c_void_p]
        self.k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        if struct.calcsize("P") != 8:
            raise ValueError("O motor ESP32 requer Python de 64 bits")
        try:
            tag = f"ohmnia_{os.getpid()}_{uuid.uuid4().hex}"
            prefix = "Local\\esp32link_" + tag
            self.memory = mmap.mmap(-1, SIZE, tagname=prefix + "_map")
            struct.pack_into("<III", self.memory, 0, 0x4C323345, 14, SIZE)
            struct.pack_into("<100h", self.memory, 48, 40, *range(40), *([-1] * 59))
            for suffix in ("_grant", "_reached"):
                handle = self.k.CreateEventW(None, False, False, prefix + suffix)
                if not handle:
                    raise OSError(ctypes.get_last_error(), "CreateEventW")
                self.handles.append(handle)
            flash = Path(self.temp.name) / "firmware.bin"
            flash.write_bytes(loaded.flash)
            self.log = (Path(self.temp.name) / "engine.log").open("wb")
            self.process = subprocess.Popen(
                [
                    str(executable),
                    "--link",
                    tag,
                    "--parent",
                    str(os.getpid()),
                    "--flash",
                    str(flash),
                    "--slice-us",
                    "10",
                    "--shift",
                    "2",
                ],
                cwd=executable.parent,
                stdout=self.log,
                stderr=self.log,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            deadline = time.monotonic() + 15
            while self._read32(12) == 0 and time.monotonic() < deadline:
                self._wait(200)
                self._check()
            if self._read32(12) != 1:
                raise ValueError("O motor ESP32 não terminou a inicialização em 15 s")
            self.base = struct.unpack_from("<q", self.memory, 24)[0]
        except Exception:
            self.close()
            raise

    def _read32(self, offset: int) -> int:
        assert self.memory is not None
        return int(struct.unpack_from("<I", self.memory, offset)[0])

    def _store(self, offset: int, value: int, wide: bool = False) -> None:
        assert self.memory is not None
        # Aligned native-width stores on Windows x64. The engine is paused;
        # SetEvent(grant)/Wait(reached) provide release/acquire synchronization.
        struct.pack_into(
            "<q" if wide else "<I", self.memory, offset, value if wide else value & 0xFFFFFFFF
        )

    def _wait(self, milliseconds: int) -> None:
        status = self.k.WaitForSingleObject(self.handles[1], milliseconds)
        if status not in (0, 258):
            raise ValueError("Falha ao aguardar sincronização ESP32")

    def _check(self) -> None:
        if self._read32(12) in (2, 3) or self.process is None or self.process.poll() is not None:
            assert self.memory is not None
            error = self.memory[248:760].split(b"\0", 1)[0].decode("utf-8", errors="replace")
            raise ValueError(
                "Motor ESP32 encerrado: " + (error or "consulte a instalação do motor")
            )

    def _push(self, kind: int, pin: int, value: int) -> None:
        assert self.memory is not None
        head, tail = self._read32(RING_B), self._read32(RING_B + 64)
        if (head - tail) & 0xFFFFFFFF >= RING_SIZE:
            raise ValueError("Fila de entradas ESP32 cheia")
        struct.pack_into(
            "<qHHIII",
            self.memory,
            RING_B + 128 + (head % RING_SIZE) * 24,
            0,
            kind,
            pin,
            value,
            0,
            0,
        )
        self._store(RING_B, head + 1)

    def advance(self, t: float, inputs: dict[str, float]) -> dict[str, Any]:
        if not self.last_time <= t <= self.last_time + 0.5:
            raise ValueError("Intervalo de firmware ESP32 inválido")
        rows = []
        # Large standalone advances are split so the engine's event ring cannot
        # fill and the watchdog still bounds each individual synchronization.
        while self.last_time + 0.001 < t:
            data = self._advance(self.last_time + 0.001, inputs)
            rows.extend(data["serial"])
            if len(rows) > 10000:
                raise ValueError("Saída Serial ESP32 excedeu 10.000 linhas por avanço")
        data = self._advance(t, inputs)
        data["serial"] = rows + data["serial"]
        return data

    def _advance(self, t: float, inputs: dict[str, float]) -> dict[str, Any]:
        assert self.memory is not None
        if not self.last_time <= t <= self.last_time + 0.5:
            raise ValueError("Intervalo de firmware ESP32 inválido")
        self.last_time = t
        for pin, voltage in inputs.items():
            if pin.startswith("IO"):
                gpio = int(pin[2:])
                self._push(64, gpio + 1, int(voltage >= 2.475))
                # QEMU SENS ADC_values: ADC1[0..7], ADC2[8..17].
                channels = {
                    36: 0,
                    39: 3,
                    32: 4,
                    33: 5,
                    34: 6,
                    35: 7,
                    4: 8,
                    2: 10,
                    15: 11,
                    13: 12,
                    12: 13,
                    14: 14,
                    27: 15,
                    25: 16,
                    26: 17,
                }
                if gpio in channels:
                    self._push(66, channels[gpio], round(max(0, min(1, voltage / 3.3)) * 4095))
        target = self.base + round(t * 1e9)
        self._store(32, target, wide=True)
        self.k.SetEvent(self.handles[0])
        deadline = time.monotonic() + 10
        while struct.unpack_from("<q", self.memory, 40)[0] < target:
            self._wait(100)
            self._check()
            if time.monotonic() > deadline:
                raise ValueError("O motor ESP32 não respondeu em 10 s")
        serial: list[tuple[float, str]] = []
        tail, head = self._read32(RING_A + 64), self._read32(RING_A)
        while tail != head:
            ns, kind, pin, value, frequency, _ = struct.unpack_from(
                "<qHHIII", self.memory, RING_A + 128 + (tail % RING_SIZE) * 24
            )
            gpio = pin - 1
            if kind == 1:
                self.levels[gpio] = value
            elif kind == 2:
                self.directions[gpio] = value
            elif kind == 5:
                self.pulls[gpio] = value
            elif kind == 6:
                if value == 0xFFFFFFFF:
                    self.pwm.pop(gpio, None)
                else:
                    self.pwm[gpio] = (ns, value, frequency)
            elif kind == 3:
                pending = self.pending.setdefault(pin, bytearray())
                if value == 10:
                    if len(serial) < 256:
                        serial.append(((ns - self.base) / 1e9, pending.decode("utf-8", "replace")))
                    pending.clear()
                elif value != 13 and len(pending) < 1024:
                    pending.append(value & 255)
            elif kind not in (4, 9):
                raise ValueError(f"Periférico ESP32 ainda não conectado (evento {kind})")
            tail = (tail + 1) & 0xFFFFFFFF
        self._store(RING_A + 64, tail)
        for gpio in range(40):
            state = (
                self.levels.get(gpio, 0)
                if self.directions.get(gpio, 0)
                else {1: 3, 2: 4}.get(self.pulls.get(gpio, 0), 2)
            )
            if gpio in self.pwm:
                start, duty, frequency = self.pwm[gpio]
                state = int(((target - start) / 1e9 * frequency) % 1 < duty / 100000)
            self.states[f"IO{gpio}"] = state
        return {"states": self.states, "serial": serial, "time": t}

    def close(self) -> None:
        if self.memory is not None:
            self._store(16, 1)
        if self.handles:
            self.k.SetEvent(self.handles[0])
        if self.process is not None:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for handle in self.handles:
            self.k.CloseHandle(handle)
        self.handles.clear()
        if self.memory is not None:
            self.memory.close()
            self.memory = None
        if hasattr(self, "log"):
            self.log.close()
        self.temp.cleanup()
