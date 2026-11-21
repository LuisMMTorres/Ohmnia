"""Isolated AVR worker and synchronous, bounded co-simulation protocol."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from circuitos.cosim.firmware_image import AVR_FLASH, FirmwareImage, load_image

if TYPE_CHECKING:
    from circuitos.cosim.controllers import ControllerSpec

WORKER = Path(__file__).with_name("firmware_worker")


def engine_status() -> tuple[bool, str]:
    node = os.environ.get("CIRCUITOS_NODE") or shutil.which("node")
    if not node or not shutil.which(node):
        return False, "Instale o Node.js ou configure CIRCUITOS_NODE para executar firmware."
    if not (WORKER / "node_modules/avr8js/package.json").is_file():
        return False, "Instale o motor: npm ci --prefix backend/src/circuitos/cosim/firmware_worker"
    return True, node


class FirmwareRuntime:
    def __init__(self, image: FirmwareImage):
        loaded = load_image(image)
        ready, node = engine_status()
        if not ready:
            raise ValueError(node)
        self.closed = threading.Event()
        self.deadline = 0.0
        self.expired = False
        self.process = subprocess.Popen(
            [node, str(WORKER / "worker.mjs")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.watchdog = threading.Thread(target=self._watch, daemon=True)
        self.watchdog.start()
        try:
            self._exchange(
                {
                    "command": "init",
                    "board": image.board,
                    "flash": base64.b64encode(loaded.flash).decode(),
                    "entry": loaded.entry,
                }
            )
        except Exception:
            self.close()
            raise

    def _watch(self) -> None:
        while not self.closed.wait(0.1):
            if self.deadline and time.monotonic() > self.deadline:
                self.expired = True
                with contextlib.suppress(OSError):
                    self.process.kill()  # also unblocks the synchronous pipe read
                return

    def _exchange(self, message: dict[str, Any]) -> dict[str, Any]:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.deadline = time.monotonic() + 10
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
        except OSError as exc:
            self.close()
            raise ValueError("Falha de comunicação com o motor de firmware") from exc
        finally:
            self.deadline = 0
        if self.expired:
            raise ValueError("O motor de firmware não respondeu em 10 s")
        if not line:
            raise ValueError("O motor de firmware foi encerrado")
        response: dict[str, Any] = json.loads(line)
        if "error" in response:
            raise ValueError(str(response["error"]))
        return response

    def advance(self, time: float, inputs: dict[str, float]) -> dict[str, Any]:
        return self._exchange({"command": "advance", "time": time, "inputs": inputs})

    def close(self) -> None:
        self.closed.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if threading.current_thread() is not self.watchdog:
            self.watchdog.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None:
                with contextlib.suppress(OSError):
                    stream.close()


def firmware_lines(
    ref: str, kind: str, params: dict[str, str], pins: dict[str, str], firmware: FirmwareImage
) -> tuple[list[str], ControllerSpec]:
    from circuitos.cosim.arduino import BOARDS
    from circuitos.cosim.controllers import ControllerSpec

    if kind not in AVR_FLASH:
        raise ValueError("Esta placa ainda não possui motor de firmware compilado")
    load_image(firmware, kind)
    ready, message = engine_status()
    if not ready:
        raise ValueError(message)
    x, board, gnd = ref.lower(), BOARDS[kind], pins["GND"]
    spec = ControllerSpec(ref, kind, params, pins, gnd, firmware=firmware)
    lines = [
        f"* {ref}: firmware AVR8js 0.21.1, 16 MHz",
        f"V{x}_vcc {pins['5V']} {gnd} DC {board.vdd}",
        f"R{x}_gnd {gnd} 0 1g",
        f"V{x}_tick {x}_tick 0 DC 0 EXTERNAL",
    ]
    spec.sources[f"v{x}_tick"] = "tick"
    for pin in board.pins:
        if pin not in pins:
            continue
        node, p = pins[pin], pin.lower()
        lines.append(f"R{x}_{p}_in {node} {gnd} 100meg")
        if kind == "arduino_nano" and pin in ("A6", "A7"):
            continue  # ADC-only pins on the Nano
        source = f"{x}_fw_{p}"
        for suffix, role in (("v", pin), ("en", f"{pin}:en"), ("pu", f"{pin}:pu")):
            name = f"v{source}_{suffix}"
            lines.append(f"{name} {source}_{suffix} 0 DC 0 EXTERNAL")
            spec.sources[name] = role
        spec.outputs[pin] = f"v{source}_v"
        lines.append(
            f"B{source} {node} {gnd} I = V({source}_en)*"
            f"(V({node},{gnd})-V({source}_v))/{board.rout:g} + "
            f"V({source}_pu)*(V({node},{gnd})-{board.vdd:g})/{board.rpullup:g}"
        )
    spec.warnings.append(
        f"{ref}: firmware AVR: GPIO, ADC, timers/PWM e Serial0; I2C/SPI, EEPROM e watchdog "
        "ainda não conectados. A ligação elétrica mantém os parâmetros didáticos da placa. "
        "Use passo transitório de no máximo 10 µs (menor para sinais rápidos)."
    )
    return lines, spec
