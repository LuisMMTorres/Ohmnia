"""Sensor libraries of the Arduino runtime (DHT, OneWire + DallasTemperature, BME280)."""

from __future__ import annotations

import math

import pytest

from circuitos.cosim.arduino import BOARDS, Runtime
from circuitos.cosim.clang import CError
from circuitos.cosim.libraries import decode_dht, dht22_frame, frame_time


class _Sensor:
    def __init__(self, kind: str, ref: str = "U2", **values: float):
        self.kind = kind
        self.ref = ref
        self.values = {"temp": 25.0, "rh": 50.0, "p": 1013.25} | values
        self.params = {
            "tres": 0.1,
            "hres": 0.1,
            "tsample": 2.0,
            "bits": 12.0,
            "tconv12": 0.75,
            "tmin": -55.0,
            "tmax": 125.0,
            "addr": 0x76,
        }
        self.dead: str | None = None

    def problem(self) -> str | None:
        return self.dead

    def read(self, quantity: str) -> float:
        return self.values[quantity]

    def param(self, name: str) -> float:
        return self.params[name]


class _Hw:
    def __init__(self, sensors: list[_Sensor], high: bool = True):
        self.sensors = sensors
        self.high = high
        self.warnings: list[str] = []
        self.pullups: set[int] = set()

    def voltage(self, pin: int) -> float:
        return 5.0 if self.high else 0.0

    def output(self, pin: int, kind: str, value: float) -> None:
        if kind == "pullup":
            self.pullups.add(pin)

    def serial(self, time: float, text: str) -> None:
        pass

    def warn(self, text: str) -> None:
        self.warnings.append(text)

    def digital_sensors(self, pin: int, kind: str) -> list[_Sensor]:
        return [s for s in self.sensors if s.kind == kind]


def _run(program: str, hw: _Hw, t: float = 1.0) -> Runtime:
    rt = Runtime(program, BOARDS["arduino_uno"], hw)
    rt.advance(t)
    return rt


def test_dht22_frame_and_decoding():
    """DHT22 frame: RH × 10, T × 10 with the sign bit, checksum (Aosong DHT22, p. 7 and 8)."""
    frame = dht22_frame(65.2, -10.1)
    assert frame == [0x02, 0x8C, 0x80, 0x65, (0x02 + 0x8C + 0x80 + 0x65) & 0xFF]
    assert decode_dht(frame, 22) == pytest.approx((65.2, -10.1))
    ones = sum(bin(b).count("1") for b in frame)
    assert frame_time(frame) == pytest.approx(
        1e-3 + 30e-6 + 160e-6 + 40 * 50e-6 + ones * 70e-6 + (40 - ones) * 27e-6
    )


def test_dht_reads_with_resolution_and_keeps_the_last_reading():
    hw = _Hw([_Sensor("dht22", temp=23.47, rh=61.23)])
    program = """DHT dht(2, DHT22);
float t; float h; int n;
void setup() { dht.begin(); }
void loop() {
  unsigned long a = micros();
  t = dht.readTemperature();
  h = dht.readHumidity();
  if (micros() - a > 1000) n = n + 1;
  delay(500);
}"""
    rt = _run(program, hw, 4.9)
    assert rt.globals["t"].value == pytest.approx(23.5)
    assert rt.globals["h"].value == pytest.approx(61.2)
    assert rt.globals["n"].value == 3  # 0, 2 and 4 s: the library waits 2 s between readings
    assert 2 in hw.pullups  # begin() sets INPUT_PULLUP


def test_dht_without_sensor_or_pullup_gives_nan():
    program = """DHT dht(2, DHT22);
float t;
void setup() { dht.begin(); t = dht.readTemperature(); }
void loop() { delay(100); }"""
    hw = _Hw([], high=True)
    hw.sensors = []
    assert math.isnan(_run(program, hw).globals["t"].value)
    low = _Hw([_Sensor("dht22")], high=False)
    assert math.isnan(_run(program, low).globals["t"].value)
    assert any("pull-up" in w for w in low.warnings)


def test_dallas_temperature_resolution_and_disconnected():
    program = """OneWire ow(2);
DallasTemperature s(&ow);
float a; float b; int n;
void setup() { s.begin(); s.setResolution(10); }
void loop() { s.requestTemperatures(); a = s.getTempCByIndex(0); b = s.getTempCByIndex(1);
  n = s.getDeviceCount(); delay(10); }"""
    rt = _run(program, _Hw([_Sensor("ds18b20", temp=21.13)]))
    assert rt.globals["a"].value == pytest.approx(21.25)  # 0,25 °C steps at 10 bits
    assert rt.globals["b"].value == -127
    assert rt.globals["n"].value == 1


def test_bme280_address():
    program = """Adafruit_BME280 bme;
int ok; int ko; float p;
void setup() { ko = bme.begin(0x77); ok = bme.begin(0x76); p = bme.readPressure(); }
void loop() { delay(10); }"""
    rt = _run(program, _Hw([_Sensor("bme280", p=950.0)]))
    assert (rt.globals["ok"].value, rt.globals["ko"].value) == (1, 0)
    assert rt.globals["p"].value == pytest.approx(95000.0)


def test_library_errors_in_portuguese():
    with pytest.raises(CError, match="DHT nome"):
        _run("DHT dht(2);\nvoid setup() {}\nvoid loop() {}", _Hw([]))
    with pytest.raises(CError, match="não é suportado"):
        _run("DHT dht(2, DHT22);\nvoid setup() { dht.foo(); }\nvoid loop() {}", _Hw([]))
