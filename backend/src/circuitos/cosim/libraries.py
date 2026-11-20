"""Arduino libraries of the digital sensors: DHT, OneWire + DallasTemperature, Adafruit_BME280.

The programs use the classes and methods of the usual libraries (Adafruit DHT sensor library,
OneWire with DallasTemperature, Adafruit BME280). The protocol is modelled at the level of the
library call: the call checks what the real bus needs (sensor powered within its supply range, the
data line pulled up, the right address), takes the time of the transaction from the datasheet
timing and returns the sensor value with the sensor's resolution. The electrical waveform of each
bit on the wire is not simulated (the data line stays at its idle level in the circuit).

Datasheet timing used (values in the catalogue records and in the symbol parameters):

* DHT22 / AM2302 (Aosong, p. 6 to 9): host start ≥ 1 ms low, 20 to 40 µs wait, response 80 µs low
  and 80 µs high, 40 bits each with 50 µs low and 26 to 28 µs ("0") or 70 µs ("1") high; at most
  one reading every 2 s (the library returns the previous one when called sooner).
* DS18B20 (Analog Devices, Rev 6, p. 3 and Table 2 p. 9): reset 480 µs low + 480 µs, time slots
  of 60 µs plus 1 µs recovery, conversion 93,75 / 187,5 / 375 / 750 ms at 9 / 10 / 11 / 12 bits.
* BME280 (Bosch, p. 2 and 33): I2C address 0x76 (SDO to GND) or 0x77 (SDO to VDDIO).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol

LIB_TYPES = {"DHT", "OneWire", "DallasTemperature", "Adafruit_BME280"}

LIB_CONSTANTS = {
    "DHT11": 11,
    "DHT12": 12,
    "DHT21": 21,
    "DHT22": 22,
    "AM2301": 21,
    "AM2302": 22,
    "DEVICE_DISCONNECTED_C": -127,
    "BME280_ADDRESS": 0x77,
    "BME280_ADDRESS_ALTERNATE": 0x76,
}

DEVICE_DISCONNECTED_C = -127.0

# DHT22 single bus (Aosong DHT22, p. 6 to 9), seconds
DHT_START = 1e-3
DHT_WAIT = 30e-6  # 20 to 40 µs: centre of the range
DHT_RESPONSE = 160e-6  # 80 µs low + 80 µs high
DHT_BIT_LOW = 50e-6
DHT_BIT_0 = 27e-6  # 26 to 28 µs: centre of the range
DHT_BIT_1 = 70e-6

# DS18B20 1-Wire (Rev 6, p. 3), seconds
OW_RESET = 960e-6  # tRSTL + tRSTH, 480 µs each
OW_SLOT = 61e-6  # tSLOT 60 µs + tREC 1 µs


class DigitalSensor(Protocol):
    """A digital sensor of the circuit, as the hardware adapter hands it to the libraries."""

    kind: str
    ref: str

    def problem(self) -> str | None:
        """Why the sensor does not answer now (no supply, supply out of range), or None."""
        ...

    def read(self, quantity: str) -> float:
        """Measured quantity at the current time (temp °C, rh %, p hPa), within its range."""
        ...

    def param(self, name: str) -> float: ...


class Bus(Protocol):
    """What the libraries need from the board: time, warnings and the sensors on a pin/bus."""

    def lib_now(self) -> float: ...
    def lib_warn(self, text: str) -> None: ...
    def lib_pullup(self, pin: int) -> None: ...
    def lib_line_high(self, pin: int) -> bool: ...
    def lib_sensors(self, pin: int, kind: str) -> list[DigitalSensor]: ...
    def lib_i2c(self) -> tuple[int, int] | None: ...


@dataclass
class Timed:
    """Result of a library call that takes time on the bus."""

    value: Any
    seconds: float


def _quantize(value: float, step: float) -> float:
    return round(value / step) * step if step > 0 else value


# ------------------------------------------------------------------------------------- DHT


def dht22_frame(rh: float, temp: float) -> list[int]:
    """The 5 bytes of a DHT22 reading: RH × 10, T × 10 (bit 15 = sign) and the checksum."""
    h = max(0, min(round(rh * 10), 0xFFFF))
    t = min(round(abs(temp) * 10), 0x7FFF) | (0x8000 if temp < 0 else 0)
    data = [h >> 8, h & 0xFF, t >> 8, t & 0xFF]
    return [*data, sum(data) & 0xFF]


def frame_time(frame: list[int]) -> float:
    ones = sum(bin(b).count("1") for b in frame)
    bits = 8 * len(frame)
    return (
        DHT_START
        + DHT_WAIT
        + DHT_RESPONSE
        + bits * DHT_BIT_LOW
        + ones * DHT_BIT_1
        + (bits - ones) * DHT_BIT_0
    )


def decode_dht(frame: list[int], dtype: int) -> tuple[float, float]:
    """How the Adafruit library decodes the bytes for the declared sensor type."""
    if dtype == 11:
        rh = frame[0] + frame[1] * 0.1
        temp = frame[2] + (frame[3] & 0x0F) * 0.1
        if frame[2] & 0x80:
            temp = -1 - temp
        return rh, temp
    rh = ((frame[0] << 8) | frame[1]) * 0.1
    temp = ((frame[2] & 0x7F) << 8 | frame[3]) * 0.1
    if frame[2] & 0x80:
        temp = -temp
    return rh, temp


@dataclass
class DhtObject:
    pin: int
    dtype: int
    last: float = -1e9
    result: tuple[float, float] = (math.nan, math.nan)
    started: bool = False

    def call(self, bus: Bus, name: str, args: list[Any]) -> Any:
        if name == "begin":
            self.started = True
            bus.lib_pullup(self.pin)  # the library sets INPUT_PULLUP on the data pin
            return None
        if name in ("readTemperature", "readHumidity", "read"):
            timed = self._read(bus, bool(args and args[-1]) if name == "read" else False)
            rh, temp = timed.value
            if name == "readHumidity":
                value: Any = rh
            elif name == "readTemperature":
                value = temp * 9 / 5 + 32 if args and args[0] else temp
            else:
                value = 0 if math.isnan(rh) else 1
            return Timed(value, timed.seconds)
        if name == "convertCtoF":
            return float(args[0]) * 9 / 5 + 32
        if name == "convertFtoC":
            return (float(args[0]) - 32) * 5 / 9
        raise ValueError(f"DHT.{name}() não é suportado")

    def _read(self, bus: Bus, force: bool) -> Timed:
        now = bus.lib_now()
        if not self.started:
            bus.lib_warn("DHT: chame begin() em setup() antes de ler o sensor")
        sensors = bus.lib_sensors(self.pin, "dht22")
        period = sensors[0].param("tsample") if sensors else 2.0
        if not force and now - self.last < period:
            return Timed(self.result, 0.0)  # the library keeps the last reading
        self.last = now
        nan = (math.nan, math.nan)
        if not sensors:
            bus.lib_warn(f"DHT no pino {self.pin}: nenhum sensor DHT22 ligado a esse pino")
            self.result = nan
            return Timed(nan, DHT_START + 100e-6)  # the library times out
        s = sensors[0]
        if len(sensors) > 1:
            bus.lib_warn(f"DHT no pino {self.pin}: mais de um sensor no mesmo fio")
        why = s.problem()
        if why is None and not bus.lib_line_high(self.pin):
            why = "a linha DATA não está em nível alto em repouso (falta o resistor de pull-up)"
        if why is not None:
            bus.lib_warn(f"o sensor {s.ref} não responde: {why}")
            self.result = nan
            return Timed(nan, DHT_START + 100e-6)
        rh = _quantize(s.read("rh"), s.param("hres"))
        temp = _quantize(s.read("temp"), s.param("tres"))
        frame = dht22_frame(rh, temp)
        if self.dtype not in (21, 22):
            bus.lib_warn(
                f"DHT no pino {self.pin}: declarado como DHT{self.dtype}, mas o sensor é um "
                "DHT22: a biblioteca decodifica os bytes do jeito errado"
            )
        self.result = decode_dht(frame, self.dtype)
        return Timed(self.result, frame_time(frame))


# -------------------------------------------------------------------------- DS18B20 (1-Wire)


@dataclass
class OneWireObject:
    pin: int

    def call(self, bus: Bus, name: str, args: list[Any]) -> Any:
        if name == "reset":
            sensors = [s for s in bus.lib_sensors(self.pin, "ds18b20") if s.problem() is None]
            present = 1 if sensors and bus.lib_line_high(self.pin) else 0
            return Timed(present, OW_RESET)
        raise ValueError(f"OneWire.{name}() não é suportado; use a DallasTemperature")


@dataclass
class DallasObject:
    wire: OneWireObject
    bits: int | None = None
    started: bool = False
    readings: dict[str, float] = field(default_factory=dict)  # sensor ref -> °C

    def _sensors(self, bus: Bus) -> list[DigitalSensor]:
        found = []
        for s in sorted(bus.lib_sensors(self.wire.pin, "ds18b20"), key=lambda s: s.ref):
            why = s.problem()
            if why is None and not bus.lib_line_high(self.wire.pin):
                why = "a linha DQ não está em nível alto em repouso (falta o resistor de pull-up)"
            if why is not None:
                bus.lib_warn(f"o sensor {s.ref} não responde: {why}")
                continue
            found.append(s)
        return found

    def _bits(self, s: DigitalSensor) -> int:
        return self.bits if self.bits is not None else int(s.param("bits"))

    def call(self, bus: Bus, name: str, args: list[Any]) -> Any:
        if name == "begin":
            self.started = True
            return None
        if name == "getDeviceCount":
            return len(self._sensors(bus))
        if name == "setResolution":
            bits = int(args[-1])
            if not 9 <= bits <= 12:
                raise ValueError("setResolution: use 9 a 12 bits")
            self.bits = bits
            return None
        if name == "getResolution":
            sensors = self._sensors(bus)
            return self._bits(sensors[0]) if sensors else 0
        if name == "requestTemperatures":
            if not self.started:
                bus.lib_warn("DallasTemperature: chame begin() em setup() antes de medir")
            sensors = self._sensors(bus)
            self.readings = {}
            wait = 0.0
            for s in sensors:
                bits = self._bits(s)
                lsb = 0.0625 * 2 ** (12 - bits)
                temp = min(max(s.read("temp"), s.param("tmin")), s.param("tmax"))
                self.readings[s.ref] = math.floor(temp / lsb + 0.5) * lsb
                wait = max(wait, s.param("tconv12") / 2 ** (12 - bits))
            # reset + skip ROM + convert T (16 slots), then the conversion time
            return Timed(None, OW_RESET + 16 * OW_SLOT + wait)
        if name in ("getTempCByIndex", "getTempFByIndex"):
            refs = sorted(self.readings)
            i = int(args[0]) if args else 0
            # reset + skip/match ROM + read scratchpad: about 88 slots
            cost = OW_RESET + 88 * OW_SLOT
            if not 0 <= i < len(refs):
                return Timed(DEVICE_DISCONNECTED_C, cost)
            c = self.readings[refs[i]]
            return Timed(c * 9 / 5 + 32 if name == "getTempFByIndex" else c, cost)
        raise ValueError(f"DallasTemperature.{name}() não é suportado")


# ------------------------------------------------------------------------------- BME280 (I2C)


@dataclass
class Bme280Object:
    sensor: DigitalSensor | None = None
    address: int = 0x77

    def call(self, bus: Bus, name: str, args: list[Any]) -> Any:
        if name == "begin":
            self.address = int(args[0]) if args else 0x77
            self.sensor = None
            pins = bus.lib_i2c()
            if pins is None:
                bus.lib_warn("BME280: esta placa não tem I2C no simulador")
                return 0
            sda, scl = pins
            found = [
                s for s in bus.lib_sensors(sda, "bme280") if int(s.param("addr")) == self.address
            ]
            if not found:
                bus.lib_warn(
                    f"BME280: nenhum sensor no endereço 0x{self.address:02X} no I2C da placa "
                    "(confira SDA/SCL e o endereço: 0x76 com SDO em GND, 0x77 com SDO em VDDIO)"
                )
                return 0
            s = found[0]
            why = s.problem()
            if why is None and not (bus.lib_line_high(sda) and bus.lib_line_high(scl)):
                why = "SDA e SCL precisam de resistores de pull-up"
            if why is not None:
                bus.lib_warn(f"o sensor {s.ref} não responde: {why}")
                return 0
            self.sensor = s
            return 1
        if name in ("readTemperature", "readPressure", "readHumidity"):
            dev = self.sensor
            if dev is None or dev.problem() is not None:
                return math.nan
            if name == "readTemperature":
                return dev.read("temp")
            if name == "readHumidity":
                return dev.read("rh")
            return dev.read("p") * 100  # the library returns pascal
        raise ValueError(f"Adafruit_BME280.{name}() não é suportado")


def construct(ctype: str, args: list[Any], lookup: Any) -> Any:
    """Build a library object from its declaration (``DHT dht(2, DHT22);`` and so on)."""
    if ctype == "DHT":
        if len(args) < 2:
            raise ValueError("DHT nome(pino, DHT22);")
        return DhtObject(int(args[0]), int(args[1]))
    if ctype == "OneWire":
        if len(args) != 1:
            raise ValueError("OneWire nome(pino);")
        return OneWireObject(int(args[0]))
    if ctype == "DallasTemperature":
        if len(args) != 1 or not isinstance(args[0], OneWireObject):
            raise ValueError("DallasTemperature nome(&oneWire);")
        return DallasObject(args[0])
    if ctype == "Adafruit_BME280":
        return Bme280Object()
    raise ValueError(f"tipo {ctype} desconhecido")
