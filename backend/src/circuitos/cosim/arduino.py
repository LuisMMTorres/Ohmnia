"""Arduino-style runtime: boards, the program interpreter and its time model.

The program runs as a coroutine. Every statement costs ``instr_us`` of simulated time (a
didactic figure: real boards are faster, but the co-simulation only needs the order of
magnitude); ``delay()`` and ``delayMicroseconds()`` hand the time to the circuit. The runtime
resumes when the circuit simulation reaches the wake-up time, so ``analogRead`` sees the node
voltage of that instant and ``digitalWrite`` changes the circuit from then on.

Integer variables wrap to the width of their type on the board (``int`` is 16 bits on the Uno,
32 bits on the ESP32); intermediate results are not truncated (a difference from real C, said in
the manual).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from circuitos.cosim.clang import CError, CType, Func, Program, VarDecl, parse

Gen = Generator[float, None, Any]


@dataclass(frozen=True)
class Board:
    kind: str
    label: str
    vdd: float
    adc_bits: int
    adc_fs: float  # full scale of analogRead (V)
    int_bits: int
    pins: dict[str, int]  # symbol pin name -> pin number used in the program
    analog: frozenset[int]
    pwm: dict[int, float]  # pin -> frequency (Hz)
    dac: frozenset[int] = frozenset()
    vih: float = 0.6  # fraction of vdd
    vil: float = 0.3
    rout: float = 25.0  # Ω, output pin
    rpullup: float = 35e3  # Ω, INPUT_PULLUP
    adc_effective: tuple[float, float] | None = None  # V, accurate range
    led: int = 13
    constants: dict[str, int] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)  # parameter -> where it comes from


_UNO_PINS = {f"D{n}": n for n in range(2, 14)} | {f"A{n}": 14 + n for n in range(6)}
_NANO_PINS = {f"D{n}": n for n in range(2, 14)} | {f"A{n}": 14 + n for n in range(8)}
MEGA_DIGITAL = (*range(2, 14), *range(22, 30), 44, 45, 46)
_MEGA_PINS = {f"D{n}": n for n in MEGA_DIGITAL} | {f"A{n}": 54 + n for n in range(16)}
_ESP_GPIO = (
    2,
    4,
    5,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    21,
    22,
    23,
    25,
    26,
    27,
    32,
    33,
    34,
    35,
    36,
    39,
)

BOARDS: dict[str, Board] = {
    "arduino_uno": Board(
        kind="arduino_uno",
        label="Arduino Uno R3",
        vdd=5.0,
        adc_bits=10,
        adc_fs=5.0,
        int_bits=16,
        pins=_UNO_PINS,
        analog=frozenset(range(14, 20)),
        pwm={3: 490.0, 5: 980.0, 6: 980.0, 9: 490.0, 10: 490.0, 11: 490.0},
        constants={f"A{n}": 14 + n for n in range(6)} | {"LED_BUILTIN": 13},
        sources={
            "vdd": "Arduino UNO R3 User Manual (SKU A000066), p. 5: alimentação USB 5 V",
            "pwm": "idem, p. 2: seis canais PWM (pinos 3, 5, 6, 9, 10, 11); frequências de "
            "490/980 Hz da referência da linguagem Arduino",
            "adc": "analogRead de 10 bits com referência de 5 V (referência da linguagem Arduino)",
            "didatico": "limiares de entrada (0,6/0,3 VDD), resistência de saída 25 Ω e pull-up "
            "de 35 kΩ: valores didáticos (o datasheet do ATmega328P não está na sua pasta)",
        },
    ),
    "arduino_nano": Board(
        kind="arduino_nano",
        label="Arduino Nano",
        vdd=5.0,
        adc_bits=10,
        adc_fs=5.0,
        int_bits=16,
        pins=_NANO_PINS,
        analog=frozenset(range(14, 22)),
        pwm={3: 490.0, 5: 980.0, 6: 980.0, 9: 490.0, 10: 490.0, 11: 490.0},
        constants={f"A{n}": 14 + n for n in range(8)} | {"LED_BUILTIN": 13},
        sources={
            "vdd": "Arduino Nano (catálogo, p. 2): ATmega328P a 16 MHz, o mesmo do Uno, 5 V",
            "pwm": "idem, p. 2: 8 entradas analógicas e 6 canais PWM (pinos 3, 5, 6, 9, 10, 11); "
            "frequências de 490/980 Hz da referência da linguagem Arduino",
            "adc": "analogRead de 10 bits com referência de 5 V (referência da linguagem Arduino)",
            "didatico": "limiares de entrada (0,6/0,3 VDD), resistência de saída 25 Ω e pull-up "
            "de 35 kΩ: os mesmos valores didáticos do Uno",
        },
    ),
    "arduino_mega": Board(
        kind="arduino_mega",
        label="Arduino Mega 2560 Rev3",
        vdd=5.0,
        adc_bits=10,
        adc_fs=5.0,
        int_bits=16,
        pins=_MEGA_PINS,
        analog=frozenset(range(54, 70)),
        pwm={n: (980.0 if n in (4, 13) else 490.0) for n in (*range(2, 14), 44, 45, 46)},
        constants={f"A{n}": 54 + n for n in range(16)} | {"LED_BUILTIN": 13},
        sources={
            "vdd": "Arduino Mega 2560 Rev3 (catálogo, p. 2): ATmega2560 a 16 MHz, 5 V",
            "pwm": "idem, p. 2: 16 entradas analógicas e 15 canais PWM (pinos 2 a 13 e 44 a 46); "
            "490 Hz, 980 Hz nos pinos 4 e 13, pela referência da linguagem Arduino",
            "adc": "analogRead de 10 bits com referência de 5 V (referência da linguagem Arduino)",
            "didatico": "limiares de entrada (0,6/0,3 VDD), resistência de saída 25 Ω e pull-up "
            "de 35 kΩ: os mesmos valores didáticos do Uno",
        },
    ),
    "esp32_devkitc": Board(
        kind="esp32_devkitc",
        label="ESP32-DevKitC (ESP32-WROOM-32)",
        vdd=3.3,
        adc_bits=12,
        adc_fs=3.3,
        int_bits=32,
        pins={f"IO{n}": n for n in _ESP_GPIO},
        analog=frozenset({32, 33, 34, 35, 36, 39}),
        pwm={n: 1000.0 for n in _ESP_GPIO if n not in (34, 35, 36, 39)},
        dac=frozenset({25, 26}),
        vih=0.75,
        vil=0.25,
        rout=16.5,
        rpullup=45e3,
        adc_effective=(0.15, 2.45),
        led=2,
        constants={
            "A0": 36,
            "A3": 39,
            "A4": 32,
            "A5": 33,
            "A6": 34,
            "A7": 35,
            "LED_BUILTIN": 2,
            "DAC1": 25,
            "DAC2": 26,
        },
        sources={
            "vdd": "ESP32-WROOM-32 Datasheet v3.8, p. 26, Table 14: VDD 3,3 V",
            "limiares": "idem, Table 14: VIH ≥ 0,75 VDD, VIL ≤ 0,25 VDD",
            "rout": "idem, Table 14: VOH ≥ 0,8 VDD com IOH = 40 mA → (3,3 − 2,64)/0,04 = 16,5 Ω",
            "dac": "idem, p. 24: dois DAC de 8 bits com referência na alimentação",
            "adc": "idem, p. 24: faixa efetiva 150 a 2450 mV com atenuação de 11 dB; leitura de "
            "12 bits (0 a 4095) com fundo de escala didático de 3,3 V",
            "didatico": "frequência PWM de 1 kHz e pull-up de 45 kΩ: valores didáticos",
        },
    ),
}


class Hardware(Protocol):
    def voltage(self, pin: int) -> float: ...
    def output(self, pin: int, kind: str, value: float) -> None: ...  # digital, pwm, dac, pullup
    def serial(self, time: float, text: str) -> None: ...
    def warn(self, text: str) -> None: ...


class _Break(Exception):  # noqa: N818 (control flow)
    pass


class _Continue(Exception):  # noqa: N818 (control flow)
    pass


class _Return(Exception):  # noqa: N818 (control flow)
    def __init__(self, value: Any):
        self.value = value


_INT_WIDTH = {
    "char": (8, True),
    "int8_t": (8, True),
    "byte": (8, False),
    "uint8_t": (8, False),
    "unsigned char": (8, False),
    "bool": (1, False),
    "boolean": (1, False),
    "short": (16, True),
    "int16_t": (16, True),
    "uint16_t": (16, False),
    "word": (16, False),
    "unsigned short": (16, False),
    "long": (32, True),
    "int32_t": (32, True),
    "unsigned long": (32, False),
    "uint32_t": (32, False),
    "long int": (32, True),
    "unsigned long int": (32, False),
    "size_t": (32, False),
    "long long": (64, True),
    "unsigned long long": (64, False),
}


@dataclass
class _Var:
    value: Any
    ctype: CType
    array: bool = False


class Runtime:
    """One board running one program; ``advance(t)`` runs it up to simulated time ``t``."""

    QUANTUM = 1e-4  # s: statements are batched until they cost this much time

    def __init__(
        self,
        source: str,
        board: Board,
        hw: Hardware,
        instr_us: float = 10.0,
        seed: int = 1,
    ):
        self.prog: Program = parse(source)
        self.board = board
        self.hw = hw
        self.instr = instr_us * 1e-6
        self.time = 0.0
        self.wake = 0.0
        self.pending = 0.0
        self.frames: list[dict[str, _Var]] = []
        self.globals: dict[str, _Var] = {}
        self.modes: dict[int, int] = {}
        self.inputs: dict[int, int] = {}
        self.ledc_bits: dict[int, int] = {}
        self.ledc_channel: dict[int, int] = {}  # core 2.x: channel -> pin
        self.line = ""
        self.rng = random.Random(seed)
        self.finished = False
        self.const = {
            "HIGH": 1,
            "LOW": 0,
            "INPUT": 0,
            "OUTPUT": 1,
            "INPUT_PULLUP": 2,
            "DEC": 10,
            "HEX": 16,
            "BIN": 2,
            "OCT": 8,
            "NULL": 0,
            **board.constants,
        }
        self.fconst = {
            "PI": math.pi,
            "HALF_PI": math.pi / 2,
            "TWO_PI": 2 * math.pi,
            "DEG_TO_RAD": math.pi / 180,
            "RAD_TO_DEG": 180 / math.pi,
        }
        self._gen: Iterator[float] = self._main()
        self._builtins = self._make_builtins()

    # ---------------------------------------------------------------- scheduling
    def advance(self, t: float) -> None:
        while not self.finished and self.wake <= t:
            self.time = self.wake
            try:
                dt = next(self._gen)
            except StopIteration:
                self.finished = True
                return
            self.wake = self.time + max(dt, 1e-9)

    def now(self) -> float:
        return self.time + self.pending

    def _main(self) -> Generator[float, None, None]:
        for d in self.prog.globals:
            yield from self._declare(d, self.globals)
        self.frames = [{}]
        setup = self.prog.funcs.get("setup")
        loop = self.prog.funcs.get("loop")
        if setup is None or loop is None:
            raise CError("o programa precisa das funções setup() e loop()")
        yield from self._call_user(setup, [])
        while True:
            yield from self._call_user(loop, [])
            self.pending += self.instr
            if self.pending >= self.QUANTUM:
                yield self._flush()

    def _flush(self) -> float:
        dt, self.pending = self.pending, 0.0
        return dt

    def _tick(self) -> Gen:
        self.pending += self.instr
        if self.pending >= self.QUANTUM:
            yield self._flush()

    # ---------------------------------------------------------------- variables
    def _lookup(self, name: str) -> _Var | None:
        for frame in reversed(self.frames):
            if name in frame:
                return frame[name]
        return self.globals.get(name)

    def _convert(self, value: Any, ctype: CType) -> Any:
        base = ctype.base
        if base in ("float", "double"):
            return float(value)
        if base == "String":
            return value if isinstance(value, str) else self._fmt(value)
        if base in ("bool", "boolean"):
            return 1 if value else 0
        if isinstance(value, str):
            raise CError(f"texto atribuído a variável {base}")
        v = math.trunc(value) if isinstance(value, float) else int(value)
        bits, signed = _INT_WIDTH.get(base, (self.board.int_bits, not base.startswith("unsigned")))
        if base == "unsigned int":
            bits, signed = self.board.int_bits, False
        mask = (1 << bits) - 1
        v &= mask
        if signed and v >> (bits - 1):
            v -= 1 << bits
        return v

    def _declare(self, d: VarDecl, scope: dict[str, _Var]) -> Gen:
        if d.size is not None:
            items: list[Any] = []
            if isinstance(d.init, list):
                for e in d.init:
                    items.append(self._convert((yield from self._ev(e)), d.ctype))
            n = len(items) if d.size == "auto" else int((yield from self._ev(d.size)))
            if d.ctype.base == "char" and isinstance(d.init, tuple) and d.init[0] == "str":
                scope[d.name] = _Var(str(d.init[1]), CType("String"), False)
                return
            zero = 0.0 if d.ctype.is_float else 0
            items += [zero] * max(0, n - len(items))
            scope[d.name] = _Var(items[:n], d.ctype, True)
            return
        if d.init is None:
            value: Any = "" if d.ctype.base == "String" else (0.0 if d.ctype.is_float else 0)
        else:
            value = yield from self._ev(d.init)
        if d.ctype.base == "char" and isinstance(value, str):
            scope[d.name] = _Var(value, CType("String"))
            return
        scope[d.name] = _Var(self._convert(value, d.ctype), d.ctype)

    # ---------------------------------------------------------------- statements
    def _call_user(self, f: Func, args: list[Any]) -> Gen:
        if len(args) != len(f.params):
            raise CError(f"{f.name}() espera {len(f.params)} argumento(s)", f.line)
        frame = {n: _Var(self._convert(a, t), t) for (t, n), a in zip(f.params, args, strict=True)}
        saved = self.frames
        self.frames = [frame]
        try:
            yield from self._block(f.body)
        except _Return as r:
            return None if r.value is None else self._convert(r.value, f.ret)
        finally:
            self.frames = saved
        return None

    def _block(self, body: list[Any]) -> Gen:
        self.frames.append({})
        try:
            for s in body:
                yield from self._stmt(s)
        finally:
            self.frames.pop()

    def _stmt(self, s: Any) -> Gen:
        kind = s[0]
        yield from self._tick()
        if kind == "expr":
            try:
                yield from self._ev(s[1])
            except CError as exc:
                if exc.line is None:
                    raise CError(str(exc), s[2]) from exc
                raise
        elif kind == "decl":
            for d in s[1]:
                yield from self._declare(d, self.frames[-1])
        elif kind == "block":
            yield from self._block(s[1])
        elif kind == "if":
            if (yield from self._ev(s[1])):
                yield from self._stmt(s[2])
            elif s[3] is not None:
                yield from self._stmt(s[3])
        elif kind == "while":
            while (yield from self._ev(s[1])):
                try:
                    yield from self._stmt(s[2])
                except _Break:
                    break
                except _Continue:
                    pass
                yield from self._tick()
        elif kind == "do":
            while True:
                try:
                    yield from self._stmt(s[1])
                except _Break:
                    break
                except _Continue:
                    pass
                if not (yield from self._ev(s[2])):
                    break
        elif kind == "for":
            self.frames.append({})
            try:
                if s[1] is not None:
                    yield from self._stmt(s[1])
                while s[2] is None or (yield from self._ev(s[2])):
                    try:
                        yield from self._stmt(s[4])
                    except _Break:
                        break
                    except _Continue:
                        pass
                    if s[3] is not None:
                        yield from self._ev(s[3])
                    yield from self._tick()
            finally:
                self.frames.pop()
        elif kind == "switch":
            value = yield from self._ev(s[1])
            matched = False
            try:
                for values, body in s[2]:
                    if not matched:
                        if values is None:
                            matched = True
                        else:
                            for v in values:
                                if (yield from self._ev(v)) == value:
                                    matched = True
                    if matched:
                        for st in body:
                            yield from self._stmt(st)
                if not matched:
                    for values, body in s[2]:
                        if values is None:
                            for st in body:
                                yield from self._stmt(st)
            except _Break:
                pass
        elif kind == "break":
            raise _Break
        elif kind == "continue":
            raise _Continue
        elif kind == "return":
            raise _Return(None if s[1] is None else (yield from self._ev(s[1])))

    # ---------------------------------------------------------------- expressions
    def _ev(self, e: Any) -> Gen:
        k = e[0]
        if k == "num":
            return e[1]
        if k == "str":
            return e[1]
        if k == "var":
            name = e[1]
            v = self._lookup(name)
            if v is not None:
                return v.value
            if name in self.const:
                return self.const[name]
            if name in self.fconst:
                return self.fconst[name]
            raise CError(f"variável '{name}' não declarada")
        if k == "bin":
            op = e[1]
            if op == "&&":
                return 1 if ((yield from self._ev(e[2])) and (yield from self._ev(e[3]))) else 0
            if op == "||":
                return 1 if ((yield from self._ev(e[2])) or (yield from self._ev(e[3]))) else 0
            a = yield from self._ev(e[2])
            b = yield from self._ev(e[3])
            return _binop(op, a, b)
        if k == "un":
            a = yield from self._ev(e[2])
            op = e[1]
            if op == "!":
                return 0 if a else 1
            if op == "-":
                return -a
            if op == "~":
                return ~int(a)
            return a
        if k == "assign":
            return (yield from self._assign(e[1], e[2], e[3]))
        if k == "incdec":
            target = e[3]
            old = yield from self._ev(target)
            new = old + (1 if e[1] == "++" else -1)
            stored = yield from self._store(target, new)
            return stored if e[2] else old
        if k == "cond":
            if (yield from self._ev(e[1])):
                return (yield from self._ev(e[2]))
            return (yield from self._ev(e[3]))
        if k == "cast":
            a = yield from self._ev(e[2])
            return self._convert(a, CType(e[1]))
        if k == "index":
            v = self._lookup(e[1])
            if v is None or not v.array:
                raise CError(f"'{e[1]}' não é vetor")
            i = int((yield from self._ev(e[2])))
            if not 0 <= i < len(v.value):
                raise CError(f"índice {i} fora do vetor {e[1]}[{len(v.value)}]")
            return v.value[i]
        if k == "comma":
            yield from self._ev(e[1])
            return (yield from self._ev(e[2]))
        if k == "call":
            name, args = e[1], e[2]
            values = []
            for a in args:
                values.append((yield from self._ev(a)))
            f = self.prog.funcs.get(name)
            if f is not None:
                return (yield from self._call_user(f, values))
            b = self._builtins.get(name)
            if b is None:
                raise CError(f"função '{name}' não existe", e[3])
            result = b(*values)
            if isinstance(result, _Wait):
                yield self.pending + result.seconds
                self.pending = 0.0
                return None
            return result
        if k == "member":
            obj, name, args = e[1], e[2], e[3]
            values = []
            for a in args or []:
                values.append((yield from self._ev(a)))
            return self._member(obj, name, values)
        raise CError(f"expressão não suportada: {k}")

    def _assign(self, op: str, target: Any, value_e: Any) -> Gen:
        value = yield from self._ev(value_e)
        if op != "=":
            old = yield from self._ev(target)
            value = _binop(op[:-1], old, value)
        return (yield from self._store(target, value))

    def _store(self, target: Any, value: Any) -> Gen:
        if target[0] == "var":
            v = self._lookup(target[1])
            if v is None:
                raise CError(f"variável '{target[1]}' não declarada")
            if v.ctype.const:
                raise CError(f"'{target[1]}' é constante")
            v.value = self._convert(value, v.ctype)
            return v.value
        v = self._lookup(target[1])
        if v is None or not v.array:
            raise CError(f"'{target[1]}' não é vetor")
        i = int((yield from self._ev(target[2])))
        if not 0 <= i < len(v.value):
            raise CError(f"índice {i} fora do vetor {target[1]}[{len(v.value)}]")
        v.value[i] = self._convert(value, v.ctype)
        return v.value[i]

    # ---------------------------------------------------------------- Arduino API
    def _member(self, obj: str, name: str, args: list[Any]) -> Any:
        if obj in ("Serial", "Serial1", "Serial2"):
            if name in ("begin", "flush", "end"):
                return None
            if name in ("print", "println"):
                text = self._fmt(*args) if args else ""
                self._serial(text + ("\n" if name == "println" else ""))
                return len(text)
            if name == "printf":
                if not args:
                    return 0
                self._serial(_printf(str(args[0]), args[1:]))
                return None
            if name in ("available", "read"):
                return 0 if name == "available" else -1
        raise CError(f"{obj}.{name}() não é suportado")

    def _serial(self, text: str) -> None:
        self.line += text
        while "\n" in self.line:
            line, self.line = self.line.split("\n", 1)
            self.hw.serial(self.now(), line.rstrip("\r"))

    def _fmt(self, value: Any = "", base: Any = None) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, float):
            digits = 2 if base is None else int(base)
            return f"{value:.{digits}f}"
        if base in (16, 2, 8):
            v = int(value) & ((1 << self.board.int_bits) - 1) if value < 0 else int(value)
            return {16: f"{v:X}", 2: f"{v:b}", 8: f"{v:o}"}[base]
        return str(int(value))

    def _pin(self, pin: Any) -> int:
        p = int(pin)
        if p not in self.board.pins.values() and p != self.board.led:
            raise CError(f"pino {p} não existe no {self.board.label}")
        return p

    def _make_builtins(self) -> dict[str, Callable[..., Any]]:
        b = self.board
        hw = self.hw

        def pin_mode(pin: Any, mode: Any) -> None:
            p = self._pin(pin)
            self.modes[p] = int(mode)
            if int(mode) == 2:
                hw.output(p, "pullup", 1.0)

        def digital_write(pin: Any, value: Any) -> None:
            p = self._pin(pin)
            if self.modes.get(p) != 1:
                hw.warn(f"digitalWrite no pino {p} sem pinMode(OUTPUT)")
            hw.output(p, "digital", 1.0 if value else 0.0)

        def digital_read(pin: Any) -> int:
            p = self._pin(pin)
            v = hw.voltage(p)
            state = self.inputs.get(p, 0)
            if v >= b.vih * b.vdd:
                state = 1
            elif v <= b.vil * b.vdd:
                state = 0
            self.inputs[p] = state
            return state

        def adc_code(p: int) -> int:
            if p not in b.analog:
                raise CError(f"o pino {p} não é entrada analógica no {b.label}")
            v = hw.voltage(p)
            if b.adc_effective and not b.adc_effective[0] <= v <= b.adc_effective[1]:
                lo, hi = b.adc_effective
                hw.warn(
                    f"analogRead({p}) com {v:.3g} V: fora da faixa efetiva do ADC "
                    f"({lo * 1000:.0f} a {hi * 1000:.0f} mV): no ESP32 real a leitura perde "
                    "precisão"
                )
            full = (1 << b.adc_bits) - 1
            return round(min(max(v, 0.0), b.adc_fs) / b.adc_fs * full)

        def analog_read(pin: Any) -> int:
            return adc_code(self._pin(pin))

        def analog_read_mv(pin: Any) -> int:
            p = self._pin(pin)
            return round(adc_code(p) / ((1 << b.adc_bits) - 1) * b.adc_fs * 1000)

        def pwm(p: int, duty: float) -> None:
            if p not in b.pwm:
                hw.warn(f"o pino {p} não tem PWM no {b.label}: saída digital")
                hw.output(p, "digital", 1.0 if duty >= 0.5 else 0.0)
                return
            hw.output(p, "pwm", min(max(duty, 0.0), 1.0))

        def analog_write(pin: Any, value: Any) -> None:
            p = self._pin(pin)
            bits = self.ledc_bits.get(p, 8)
            pwm(p, float(value) / ((1 << bits) - 1))

        def dac_write(pin: Any, value: Any) -> None:
            p = self._pin(pin)
            if p not in b.dac:
                raise CError(f"o pino {p} não tem DAC no {b.label}")
            hw.output(p, "dac", min(max(int(value), 0), 255) / 255 * b.vdd)

        def ledc_attach(pin: Any, freq: Any, bits: Any) -> bool:
            self.ledc_bits[self._pin(pin)] = int(bits)
            return True

        def ledc_setup(channel: Any, freq: Any, bits: Any) -> int:
            self.ledc_bits[-1 - int(channel)] = int(bits)
            return int(freq)

        def ledc_attach_pin(pin: Any, channel: Any) -> None:
            p = self._pin(pin)
            self.ledc_channel[int(channel)] = p
            self.ledc_bits[p] = self.ledc_bits.get(-1 - int(channel), 8)

        def ledc_write(target: Any, duty: Any) -> None:
            p = self.ledc_channel.get(int(target), int(target))
            bits = self.ledc_bits.get(p, 8)
            pwm(self._pin(p), float(duty) / ((1 << bits) - 1))

        def map_(x: Any, a: Any, b_: Any, c: Any, d: Any) -> Any:
            if b_ == a:
                raise CError("map() com faixa de entrada nula")
            r = (x - a) * (d - c) / (b_ - a) + c
            return int(r) if all(isinstance(v, int) for v in (x, a, b_, c, d)) else r

        def random_(a: Any, b_: Any = None) -> int:
            lo, hi = (0, int(a)) if b_ is None else (int(a), int(b_))
            return self.rng.randrange(lo, hi) if hi > lo else lo

        return {
            "pinMode": pin_mode,
            "digitalWrite": digital_write,
            "digitalRead": digital_read,
            "analogRead": analog_read,
            "analogReadMilliVolts": analog_read_mv,
            "analogWrite": analog_write,
            "dacWrite": dac_write,
            "ledcAttach": ledc_attach,
            "ledcSetup": ledc_setup,
            "ledcAttachPin": ledc_attach_pin,
            "ledcWrite": ledc_write,
            "analogReadResolution": lambda bits: None,
            "analogSetAttenuation": lambda a: None,
            "delay": lambda ms: _Wait(max(float(ms), 0.0) * 1e-3),
            "delayMicroseconds": lambda us: _Wait(max(float(us), 0.0) * 1e-6),
            "millis": lambda: int(self.now() * 1000) & 0xFFFFFFFF,
            "micros": lambda: int(self.now() * 1e6) & 0xFFFFFFFF,
            "map": map_,
            "constrain": lambda x, a, b_: min(max(x, a), b_),
            "abs": abs,
            "fabs": lambda x: abs(float(x)),
            "min": min,
            "max": max,
            "sq": lambda x: x * x,
            "pow": lambda x, y: float(x) ** float(y),
            "sqrt": lambda x: math.sqrt(x),
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "atan": math.atan,
            "atan2": math.atan2,
            "exp": math.exp,
            "log": math.log,
            "log10": math.log10,
            "floor": lambda x: float(math.floor(x)),
            "ceil": lambda x: float(math.ceil(x)),
            "round": lambda x: float(round(x)),
            "random": random_,
            "randomSeed": lambda s: self.rng.seed(int(s)),
            "isnan": lambda x: 1 if isinstance(x, float) and math.isnan(x) else 0,
            "yield": lambda: None,
        }


@dataclass
class _Wait:
    seconds: float


def _binop(op: str, a: Any, b: Any) -> Any:
    if isinstance(a, str) or isinstance(b, str):
        if op == "+":
            return f"{a}{b}"
        if op in ("==", "!="):
            return 1 if (a == b) == (op == "==") else 0
        raise CError(f"operador {op} com texto")
    both_int = isinstance(a, int) and isinstance(b, int)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise CError("divisão por zero")
        return int(a / b) if both_int else a / b
    if op == "%":
        if not both_int:
            raise CError("operador % exige inteiros (use fmod)")
        if b == 0:
            raise CError("resto da divisão por zero")
        return int(math.fmod(a, b))
    if op == "==":
        return 1 if a == b else 0
    if op == "!=":
        return 1 if a != b else 0
    if op == "<":
        return 1 if a < b else 0
    if op == "<=":
        return 1 if a <= b else 0
    if op == ">":
        return 1 if a > b else 0
    if op == ">=":
        return 1 if a >= b else 0
    if not both_int:
        raise CError(f"operador {op} exige inteiros")
    if op == "&":
        return a & b
    if op == "|":
        return a | b
    if op == "^":
        return a ^ b
    if op == "<<":
        return a << b
    if op == ">>":
        return a >> b
    raise CError(f"operador {op} não suportado")


def _printf(fmt: str, args: list[Any]) -> str:
    import re

    it = iter(args)

    def rep(m: re.Match[str]) -> str:
        spec = m.group(0)
        if spec == "%%":
            return "%"
        try:
            v = next(it)
        except StopIteration:
            return spec
        conv = spec[-1]
        py = spec[:-1].replace("l", "") + ("d" if conv in "iu" else conv)
        try:
            return py % (int(v) if conv in "diuxXc" else v)
        except (TypeError, ValueError):
            return str(v)

    return re.sub(r"%[-+ 0#]*\d*(?:\.\d+)?l*[diuxXfeEgcs%]", rep, fmt)
