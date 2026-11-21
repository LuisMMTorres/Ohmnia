"""The co-simulation session: controllers answer ngspice's EXTERNAL sources during the run.

ngspice calls back for the value of each EXTERNAL source at every time step
(``ngSpice_Init_Sync``) and reports every accepted point (``SendData``). At each call the session
lets every controller catch up to the step's time: the program runs until its next wake-up
(MCU) or the scans due run (PLC), reading the node voltages of the last accepted point. The
outputs then hold until the next wake-up: the controllers sample and hold, as real ones do.

Traces (output pins, PWM duty, program variables, PLC variables) are recorded at each wake-up
and added to the transient plot on its own time axis (zero-order hold), so they can be plotted
next to the circuit's voltages. ``Serial`` lines go to ``summary["serial"]``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from circuitos.cosim.arduino import BOARDS, Runtime
from circuitos.cosim.controllers import (
    PLC_AI_SHUNT,
    PLC_DI_OFF,
    PLC_DI_ON,
    PLC_MIN_SUPPLY,
    ControllerSpec,
    SensorSpec,
)
from circuitos.cosim.plc import IO_BOOL_IN, IO_REAL_IN, PlcRuntime
from circuitos.schematic.values import parse_value, try_parse
from circuitos.simulation.results import Plot, Vector

MAX_TRACE = 200_000


class _Adapter:
    spec: ControllerSpec
    trace_t: list[float]
    trace: dict[str, list[float]]

    def tick(self, t: float) -> None:
        raise NotImplementedError

    def value(self, role: str, t: float) -> float:
        raise NotImplementedError

    def _record(self, t: float, values: dict[str, float]) -> None:
        if len(self.trace_t) >= MAX_TRACE:
            return
        if self.trace_t and t <= self.trace_t[-1]:
            for name, v in values.items():  # same instant: keep the latest values
                if name in self.trace:
                    self.trace[name][-1] = v
            return
        n = len(self.trace_t)
        self.trace_t.append(t)
        for k, v in values.items():
            col = self.trace.setdefault(k, [math.nan] * n)
            col.append(v)
        for col in self.trace.values():
            if len(col) < n + 1:
                col.append(col[-1] if col else math.nan)


class McuAdapter(_Adapter):
    def __init__(self, spec: ControllerSpec, session: CoSession):
        self.spec = spec
        self.session = session
        self.board = BOARDS[spec.kind]
        self.by_number = {num: pin for pin, num in self.board.pins.items()}
        self.state: dict[str, tuple[str, float]] = {}
        self.trace_t, self.trace = [], {}
        self.switching = spec.params.get("pwm", "média") == "chaveado"
        instr = float(spec.params.get("instr_us", "10") or 10)
        self.rt = Runtime(spec.params.get("program", ""), self.board, self, instr_us=instr)
        self.last_wake = -1.0

    # Hardware protocol
    def voltage(self, pin: int) -> float:
        name = self.by_number.get(pin)
        if name is None or name not in self.spec.pins:
            return 0.0
        return self.session.v(self.spec.pins[name]) - self.session.v(self.spec.reference)

    def output(self, pin: int, kind: str, value: float) -> None:
        name = self.by_number.get(pin)
        if name is None:
            return
        if kind != "pullup" and name not in self.spec.outputs:
            self.session.warn(
                f"{self.spec.ref}: o pino {name} foi usado como saída depois do início; "
                "declare pinMode(…, OUTPUT) em setup() para ele entrar no circuito"
            )
            return
        self.state[name] = (kind, value)

    def serial(self, time: float, text: str) -> None:
        self.session.serial.setdefault(self.spec.ref, []).append((round(time, 6), text))

    def warn(self, text: str) -> None:
        self.session.warn(f"{self.spec.ref}: {text}")

    def digital_sensors(self, pin: int, kind: str) -> list[SensorLink]:
        name = self.by_number.get(pin)
        node = self.spec.pins.get(name) if name is not None else None
        if node is None:
            return []
        found = [s for s in self.session.sensors if s.kind == kind and s.data == node]
        if kind == "bme280" and self.board.i2c is not None:
            scl = self.by_number.get(self.board.i2c[1])
            scl_node = self.spec.pins.get(scl) if scl is not None else None
            found = [s for s in found if s.spec.pins.get("SCL") == scl_node]
        return found

    # co-simulation
    def tick(self, t: float) -> None:
        if t < self.rt.wake:
            return
        self.rt.advance(t)
        values: dict[str, float] = {}
        for pin in self.spec.outputs:
            values[f"{self.spec.ref}.{pin}"] = self._level(pin)
        for name, var in self.rt.globals.items():
            if not var.array and isinstance(var.value, int | float):
                values[f"{self.spec.ref}.{name}"] = float(var.value)
        self._record(self.rt.time, values)

    def _level(self, pin: str) -> float:
        kind, value = self.state.get(pin, ("digital", 0.0))
        if kind == "dac":
            return value
        return value * self.board.vdd

    def value(self, role: str, t: float) -> float:
        if role == "tick":
            return 0.0
        kind, value = self.state.get(role, ("digital", 0.0))
        if kind == "pwm" and self.switching:
            f = self.board.pwm.get(self.board.pins[role], 1000.0)
            return self.board.vdd if (t * f) % 1.0 < value else 0.0
        return self._level(role)


class PlcAdapter(_Adapter):
    def __init__(self, spec: ControllerSpec, session: CoSession):
        self.spec = spec
        self.session = session
        p = spec.params
        self.rt = PlcRuntime(p.get("language", "ladder"), st=p.get("st", ""),
                             ladder=p.get("ladder", ""))  # fmt: skip
        self.scan_s = max(float(p.get("scan_ms", "10") or 10), 0.1) / 1000
        self.next_scan = 0.0
        self.outputs: dict[str, Any] = {"Q0": False, "Q1": False, "Q2": False, "Q3": False,
                                        "AQ0": 0.0}  # fmt: skip
        self.di: dict[str, bool] = {d: False for d in IO_BOOL_IN}
        self.trace_t, self.trace = [], {}
        self.powered = False
        self.warned_power = False

    def _v(self, pin: str) -> float:
        return self.session.v(self.spec.pins[pin]) - self.session.v(self.spec.reference)

    def tick(self, t: float) -> None:
        while t >= self.next_scan:
            self.powered = self._v("L+") >= PLC_MIN_SUPPLY
            inputs: dict[str, Any] = {}
            for d in IO_BOOL_IN:
                v = self._v(d)
                if v >= PLC_DI_ON:
                    self.di[d] = True
                elif v <= PLC_DI_OFF:
                    self.di[d] = False
                inputs[d] = self.di[d]
            for ai in IO_REAL_IN:
                v = self._v(ai)
                mode = self.spec.params.get(ai.lower(), "4-20mA")
                inputs[ai] = v / PLC_AI_SHUNT * 1000 if mode == "4-20mA" else v
            if self.powered:
                self.outputs = self.rt.scan(inputs, self.scan_s)
            else:
                if not self.warned_power and self.next_scan > 0:
                    self.session.warn(
                        f"{self.spec.ref}: CLP sem alimentação (L+ − M abaixo de "
                        f"{PLC_MIN_SUPPLY:g} V): em STOP, saídas desligadas"
                    )
                    self.warned_power = True
                self.outputs = {k: (0.0 if k == "AQ0" else False) for k in self.outputs}
            snap = {f"{self.spec.ref}.{k}": v for k, v in self.rt.snapshot().items()}
            snap[f"{self.spec.ref}.RUN"] = 1.0 if self.powered else 0.0
            self._record(self.next_scan, snap)
            self.next_scan += self.scan_s

    def value(self, role: str, t: float) -> float:
        if role == "tick":
            return 0.0
        if role == "AQ0":
            return float(self.outputs.get("AQ0", 0.0))
        return 1.0 if self.outputs.get(role) else 0.0


class StepperDriverAdapter(_Adapter):
    """Step counter of a STEP/DIR driver: rising edges on STEP move the current vector.

    The edges are seen at the accepted points of ngspice, so a STEP pulse must last at least
    one time step (the run limits the step to 20 µs with a driver in the circuit).
    """

    def __init__(self, spec: ControllerSpec, session: CoSession):
        self.spec = spec
        self.session = session
        p = spec.params
        self.ifull = float(try_parse(p.get("ifull", "1.5") or "1.5") or 1.5)
        self.micro = max(int(p.get("micro", "1") or 1), 1)
        self.vth = float(try_parse(p.get("vth", "1.65") or "1.65") or 1.65)
        self.steps = 0
        self.high = False
        self.trace_t, self.trace = [], {}
        self.ia = self.ib = 0.0
        self._update(True)

    def _v(self, pin: str) -> float:
        return self.session.v(self.spec.pins[pin]) - self.session.v(self.spec.reference)

    def _update(self, enabled: bool) -> None:
        # electrical angle: 45° at home, 90°/micro per step (full step: both phases at 70,7 %)
        theta = math.pi / 4 + self.steps * (math.pi / 2) / self.micro
        k = self.ifull if enabled else 0.0
        self.ia, self.ib = k * math.cos(theta), k * math.sin(theta)

    def tick(self, t: float) -> None:
        level = self._v("STEP") > self.vth
        if level and not self.high:
            self.steps += 1 if self._v("DIR") > self.vth else -1
        self.high = level
        self._update(self._v("EN") < self.vth)
        ref = self.spec.ref
        self._record(t, {f"{ref}.steps": float(self.steps), f"{ref}.ia_ref": self.ia,
                         f"{ref}.ib_ref": self.ib})  # fmt: skip

    def value(self, role: str, t: float) -> float:
        if role == "ia":
            return self.ia
        if role == "ib":
            return self.ib
        return 0.0


_DATA_PIN = {"dht22": "DATA", "ds18b20": "DQ", "bme280": "SDA"}
_SUPPLY_PIN = {"dht22": "VCC", "ds18b20": "VDD", "bme280": "VDD"}
_RANGES = {"temp": ("tmin", "tmax"), "p": ("pmin", "pmax")}


class SensorLink:
    """A digital sensor of the circuit as the board libraries see it (cosim/libraries.py)."""

    def __init__(self, spec: SensorSpec, session: CoSession):
        self.spec = spec
        self.session = session
        self.kind = spec.kind
        self.ref = spec.ref
        self.data = spec.pins.get(_DATA_PIN[spec.kind], "")
        self._warned: set[str] = set()

    def param(self, name: str) -> float:
        text = self.spec.params.get(name, "")
        if name == "addr":
            return float(int(text.split()[0], 16))
        return parse_value(text)

    def _warn_once(self, key: str, text: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            self.session.warn(f"{self.ref}: {text}")

    def problem(self) -> str | None:
        p = self.spec.pins
        vs = self.session.v(p[_SUPPLY_PIN[self.kind]]) - self.session.v(p["GND"])
        lo, hi = self.param("vsmin"), self.param("vsmax")
        if vs < lo:
            return f"alimentação de {vs:.3g} V, abaixo do mínimo de {lo:g} V"
        if vs > hi:
            self._warn_once(
                "vs", f"alimentação de {vs:.3g} V acima do máximo de {hi:g} V do datasheet"
            )
        return None

    def read(self, quantity: str) -> float:
        value = stimulus_value(self.spec.params.get(quantity, "0"), self.session)
        lo, hi = (0.0, 100.0) if quantity == "rh" else tuple(map(self.param, _RANGES[quantity]))
        if not lo <= value <= hi:
            self._warn_once(
                quantity, f"valor {value:.4g} fora da faixa de medição ({lo:g} a {hi:g})"
            )
        return min(max(value, lo), hi)


def stimulus_value(text: str, session: CoSession) -> float:
    """Value now of a stimulus parameter: constant, time/value pairs or v(node)."""
    t = text.strip()
    if t.lower().startswith("v(") and t.endswith(")"):
        nodes = [n.strip().lower() for n in t[2:-1].split(",")]
        return session.v(nodes[0]) - (session.v(nodes[1]) if len(nodes) > 1 else 0.0)
    values = [float(x) for x in t.replace(",", " ").split()]
    if len(values) == 1:
        return values[0]
    return float(np.interp(session.t, values[::2], values[1::2]))


class CoSession:
    """Shared by the ngspice callbacks of one run."""

    def __init__(self, specs: list[ControllerSpec], sensors: list[SensorSpec] | None = None):
        self.latest: dict[str, float] = {}
        self.read = self._no_reader  # replaced by the backend during the run
        self.serial: dict[str, list[tuple[float, str]]] = {}
        self.warnings: list[str] = []
        self.sources: dict[str, tuple[_Adapter, str]] = {}
        self.adapters: list[_Adapter] = []
        self.sensors = [SensorLink(s, self) for s in sensors or []]
        for spec in specs:
            adapter: _Adapter
            if spec.kind == "plc":
                adapter = PlcAdapter(spec, self)
            elif spec.kind == "stepper_driver":
                adapter = StepperDriverAdapter(spec, self)
            else:
                adapter = McuAdapter(spec, self)
            self.adapters.append(adapter)
            for src, role in spec.sources.items():
                self.sources[src.lower()] = (adapter, role)
        self.t = 0.0
        self.errors: list[str] = []
        self.failed: set[_Adapter] = set()

    def warn(self, text: str) -> None:
        if text not in self.warnings and len(self.warnings) < 50:
            self.warnings.append(text)

    def v(self, node: str) -> float:
        if node in ("0", "gnd"):
            return 0.0
        key = node.lower()
        if key not in self.latest:
            value = self.read(key)
            self.latest[key] = 0.0 if value is None else value
        return self.latest[key]

    @staticmethod
    def _no_reader(_name: str) -> float | None:
        return None

    def source(self, name: str, t: float) -> float:
        entry = self.sources.get(name.lower())
        if entry is None:
            return 0.0
        if t > self.t:
            self.t = t
            self.latest = {}  # node values are read again at each new time step
            for a in self.adapters:
                if a in self.failed:
                    continue
                try:
                    a.tick(t)
                except Exception as exc:
                    self.failed.add(a)
                    self.errors.append(f"{a.spec.ref}: erro no programa em t = {t:.6g} s: {exc}")
        adapter, role = entry
        return adapter.value(role, t)

    def finish(self, plot: Plot) -> None:
        """Add the controller traces to the transient plot (zero-order hold)."""
        if plot.scale is None or plot.scale not in plot.vectors:
            return
        time = np.asarray(plot.vectors[plot.scale].data, dtype=float)
        for a in self.adapters:
            if not a.trace_t:
                continue
            tt = np.asarray(a.trace_t)
            idx = np.clip(np.searchsorted(tt, time, side="right") - 1, 0, len(tt) - 1)
            for name, col in a.trace.items():
                data = np.asarray(col, dtype=float)[idx]
                data[time < tt[0]] = data[0] if len(data) else math.nan
                key = name.lower()
                unit = "V" if key.split(".", 1)[1].upper() in self._volt_names(a) else ""
                plot.vectors[key] = Vector(key, unit, data)

    @staticmethod
    def _volt_names(a: _Adapter) -> set[str]:
        if isinstance(a, PlcAdapter):
            return {"AQ0"}
        if isinstance(a, StepperDriverAdapter):
            return set()
        return {p.upper() for p in a.spec.outputs}
