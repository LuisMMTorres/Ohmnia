"""Controllers in the netlist: EXTERNAL sources for outputs, loads for inputs, and the spec the
co-simulation needs (which source is which pin).

The netlist is static, so which pins are outputs is decided before the run: a dry run of the
program (its first 0,2 s against a quiet circuit) records ``pinMode`` and writes, and a scan of
the program adds pins written with a constant pin number anywhere. The dry run also reports
syntax and runtime errors before ngspice starts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from circuitos.cosim.arduino import BOARDS, Board, Runtime
from circuitos.cosim.clang import CError
from circuitos.cosim.plc import IO_BOOL_IN, IO_REAL_IN, PlcError, PlcRuntime

PLC_DI_ON = 15.0  # V, IEC 61131-2 type 1: ON from 15 V
PLC_DI_OFF = 5.0  # V, OFF up to 5 V
PLC_MIN_SUPPLY = 19.2  # V: 24 V − 20 %
PLC_AI_SHUNT = 250.0  # Ω, 4-20 mA input
PLC_AQ_ROUT = 10.0  # Ω


@dataclass
class ControllerSpec:
    ref: str
    kind: str
    params: dict[str, str]
    pins: dict[str, str]  # symbol pin -> node (lower case)
    reference: str  # node the pins are measured against (GND or M)
    sources: dict[str, str] = field(default_factory=dict)  # external source (lower) -> pin role
    outputs: dict[str, str] = field(default_factory=dict)  # pin -> external source name
    warnings: list[str] = field(default_factory=list)


@dataclass
class SensorSpec:
    """A digital sensor (DHT22, DS18B20, BME280) read by a board's library calls."""

    ref: str
    kind: str
    params: dict[str, str]  # resolved values (symbol defaults or the catalogue part)
    pins: dict[str, str]  # symbol pin -> node (lower case)


class _DryHw:
    def __init__(self) -> None:
        self.outputs: set[int] = set()
        self.pullups: set[int] = set()
        self.warnings: list[str] = []

    def voltage(self, pin: int) -> float:
        return 0.0

    def output(self, pin: int, kind: str, value: float) -> None:
        (self.pullups if kind == "pullup" else self.outputs).add(pin)

    def serial(self, time: float, text: str) -> None:
        pass

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)


_WRITERS = {"digitalWrite", "analogWrite", "dacWrite", "ledcWrite", "ledcAttach", "ledcAttachPin"}


def _scan_writes(node: Any, out: set[int]) -> None:
    if isinstance(node, tuple):
        if node and node[0] == "call" and node[1] in _WRITERS and node[2]:
            first = node[2][0]
            if first[0] == "num":
                out.add(int(first[1]))
        for child in node:
            _scan_writes(child, out)
    elif isinstance(node, list):
        for child in node:
            _scan_writes(child, out)
    elif isinstance(node, dict):
        for child in node.values():
            _scan_writes(child, out)
    elif hasattr(node, "__dict__"):
        for child in vars(node).values():
            _scan_writes(child, out)


def analyse_program(source: str, board: Board) -> tuple[set[int], set[int], list[str]]:
    hw = _DryHw()
    try:
        rt = Runtime(source, board, hw)
        rt.advance(0.2)
    except RecursionError as exc:
        raise CError("recursão profunda demais no programa") from exc
    writes: set[int] = set()
    _scan_writes(rt.prog, writes)
    pinmodes = {p for p, m in rt.modes.items() if m == 1}
    return hw.outputs | writes | pinmodes, hw.pullups - pinmodes, hw.warnings


def controller_lines(
    ref: str, kind: str, params: dict[str, str], pins: dict[str, str]
) -> tuple[list[str], ControllerSpec]:
    x = ref.lower()
    pins = {k: v.lower() for k, v in pins.items()}
    if kind == "plc":
        return _plc_lines(x, ref, params, pins)
    if kind == "stepper_driver":
        from circuitos.schematic.drive_symbols import stepper_driver_lines

        spec = ControllerSpec(ref, kind, params, pins, pins["GND"])
        spec.sources = {f"v{x}_tick": "tick", f"v{x}_refa": "ia", f"v{x}_refb": "ib"}
        return stepper_driver_lines(x, pins, params), spec
    board = BOARDS[kind]
    gnd = pins["GND"]
    spec = ControllerSpec(ref, kind, params, pins, gnd)
    try:
        outputs, pullups, warnings = analyse_program(params.get("program", ""), board)
    except CError as exc:
        raise CError(f"{ref} ({board.label}): {exc}") from exc
    spec.warnings += [f"{ref}: {w}" for w in warnings]
    vcc_pin = "5V" if "5V" in pins else "3V3"
    lines = [
        f"* {ref}: {board.label} (co-simulação)",
        f"V{x}_vcc {pins[vcc_pin]} {gnd} DC {board.vdd:g}",
        f"R{x}_gnd {gnd} 0 1g",
        f"V{x}_tick {x}_tick 0 DC 0 EXTERNAL",
        f"R{x}_tick {x}_tick 0 1meg",
    ]
    spec.sources[f"v{x}_tick"] = "tick"
    for pin, node in pins.items():
        if pin in ("GND", vcc_pin):
            continue
        number = board.pins.get(pin)
        if number is None:
            continue
        p = pin.lower()
        if number in outputs:
            src = f"v{x}_{p}"
            lines += [
                f"{src} {x}_{p}_s {gnd} DC 0 EXTERNAL",
                f"R{x}_{p}_o {x}_{p}_s {node} {board.rout:g}",
            ]
            spec.sources[src] = pin
            spec.outputs[pin] = src
        elif number in pullups:
            lines += [
                f"V{x}_{p}_pu {x}_{p}_pu {gnd} DC {board.vdd:g}",
                f"R{x}_{p}_pu {x}_{p}_pu {node} {board.rpullup:g}",
            ]
        else:
            lines.append(f"R{x}_{p}_in {node} {gnd} 100meg")
    return lines, spec


def _plc_lines(
    x: str, ref: str, params: dict[str, str], pins: dict[str, str]
) -> tuple[list[str], ControllerSpec]:
    m = pins["M"]
    spec = ControllerSpec(ref, "plc", params, pins, m)
    language = params.get("language", "ladder")
    try:
        rt = PlcRuntime(language, st=params.get("st", ""), ladder=params.get("ladder", ""))
        rt.scan({}, 0.01)  # catches errors before the run
    except (PlcError, json.JSONDecodeError) as exc:
        raise CError(f"{ref} (CLP, {language}): {exc}") from exc
    lines = [
        f"* {ref}: CLP (co-simulação)",
        f"R{x}_lp {pins['L+']} {m} 480",
        f"R{x}_mgnd {m} 0 1g",
        f"V{x}_tick {x}_tick 0 DC 0 EXTERNAL",
        f"R{x}_tick {x}_tick 0 1meg",
        f".model sw_{x} sw vt=0.5 vh=0.2 ron=0.05 roff=1e9",
    ]
    spec.sources[f"v{x}_tick"] = "tick"
    for di in IO_BOOL_IN:
        lines.append(f"R{x}_{di.lower()} {pins[di]} {m} 4.7k")
    for ai in IO_REAL_IN:
        shunt = PLC_AI_SHUNT if params.get(ai.lower(), "4-20mA") == "4-20mA" else 100e3
        lines.append(f"R{x}_{ai.lower()} {pins[ai]} {m} {shunt:g}")
    for q in range(4):
        src = f"v{x}_q{q}c"
        lines += [
            f"{src} {x}_q{q}c 0 DC 0 EXTERNAL",
            f"S{x}_q{q} {pins[f'Q{q}a']} {pins[f'Q{q}b']} {x}_q{q}c 0 sw_{x}",
        ]
        spec.sources[src] = f"Q{q}"
        spec.outputs[f"Q{q}"] = src
    src = f"v{x}_aq0"
    lines += [
        f"{src} {x}_aq0_s {m} DC 0 EXTERNAL",
        f"R{x}_aq0_o {x}_aq0_s {pins['AQ0']} {PLC_AQ_ROUT:g}",
    ]
    spec.sources[src] = "AQ0"
    spec.outputs["AQ0"] = src
    return lines, spec
