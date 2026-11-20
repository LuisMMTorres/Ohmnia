"""AS-PER: device bench of the sensors, actuators and controllers of the simulator library.

Rule 4: every bench measurement taken on ngspice (with the co-simulation for Arduino, ESP32 and
the PLC) must agree with the closed form the library model implements. The tolerance of each
measurement is in :mod:`circuitos.devices.peripherals` (0,1 % for algebraic models, up to a few
percent where the measurement has a sampling or scan delay, as the PLC inputs).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from circuitos.devices.peripherals import BENCHES, BenchError, run_peripheral

DATA = Path(__file__).resolve().parents[3] / "data" / "components"

pytestmark = pytest.mark.ngspice


@pytest.fixture(scope="module")
def backend():
    from circuitos.simulation.backend import SharedNgspiceBackend

    if not SharedNgspiceBackend.available():
        pytest.skip("biblioteca do ngspice ausente")
    return SharedNgspiceBackend()


def _ok(res) -> None:  # type: ignore[no-untyped-def]
    assert res.tests, "bancada sem ensaios"
    bad = [(t.id, t.error_pct, t.tolerance_pct) for t in res.tests if not t.ok]
    assert not bad, bad
    assert len(res.steps) == len(res.tests)
    for c in res.curves:
        assert all(len(t.values) == len(c.x) for t in c.traces), c.id


@pytest.mark.parametrize("kind", sorted(BENCHES))
def test_as_per_01_default_bench(backend, kind):
    """AS-PER-01: every bench with the symbol defaults and the default test conditions."""
    _ok(run_peripheral(kind, {}, {}, None, backend))


@pytest.mark.parametrize(
    ("kind", "params", "fixture"),
    [
        ("lm35", {"sens": "10m"}, {"vs": "2.5", "tmax": "150"}),  # saturates at VS − 1,5 V
        ("thermocouple", {"type": "J", "tref": "0"}, {"tmin": "-100", "tmax": "700"}),
        ("tx420_rtd", {"lo": "-50", "hi": "150"}, {"dlead": "1"}),  # unequal leads
        ("potentiometer", {"r": "1k"}, {"rl": "1k"}),
        ("relay", {"vnom": "12", "rcoil": "400", "pull": "0.7"}, {}),
        ("dc_motor", {"r": "1", "ke": "0.05", "kt": "0.05"}, {"v": "24", "load": "0.3"}),
        ("contactor", {"coil": "CA", "vnom": "220"}, {}),
        ("soft_starter", {"control": "limitação de corrente"}, {}),
        ("stepper_driver", {"micro": "16"}, {"nfwd": "32", "nback": "8", "rate": "400"}),
        ("arduino_uno", {}, {"duty": "64", "rl_dig": "1k"}),
        ("ntc", {"delta": "0"}, {"tmin": "0", "tmax": "50"}),  # no self-heating, no β check
        ("ldr", {"gamma": "0.8", "rdark": "500k"}, {"rf": "4.7k", "emin": "0.1"}),
        ("hall_linear", {"vq": "1.65", "sens": "30m", "brange": "40"}, {"vs": "3.3"}),
        ("hall_switch", {"bop": "35", "brel": "25"}, {"rpull": "1k"}),
        ("pressure", {"pmax": "100", "voff": "0.5", "vfs": "4.5"}, {}),
        ("ultrasonic", {}, {"dists": "0.02 3.9 4.5", "tair": "0"}),
        ("arduino_mega", {}, {"duty": "200"}),
        ("lm35", {"voff": "0.5"}, {"tmin": "-40", "tmax": "125"}),  # TMP36 offset
        ("kty81", {"r25": "2k"}, {"tmin": "0", "tmax": "100"}),
        ("dht22", {}, {"temp": "-12.34", "rh": "5"}),  # negative temperature (sign bit)
        ("dht22", {}, {"vsup": "3"}),  # below 3,3 V: no answer
        ("ds18b20", {"bits": "9"}, {"temp": "-10.2"}),
        ("ds18b20", {}, {"rpull": "0"}),  # no pull-up on DQ: −127
        ("bme280", {}, {"rpull": "0"}),  # no pull-ups on SDA/SCL: begin() fails
        ("bme280", {"addr": "0x77 (SDO em VDDIO)"}, {"p": "1200"}),  # clamped to 1100 hPa
    ],
)
def test_as_per_02_other_conditions(backend, kind, params, fixture):
    """AS-PER-02: benches away from the defaults (other parts, ranges and loads)."""
    res = run_peripheral(kind, params, fixture, None, backend)
    _ok(res)
    if kind == "lm35" and "voff" not in params:
        assert "LM-SAT" in {t.id for t in res.tests}
    if kind == "dht22" and fixture.get("vsup") == "3":
        assert any("não responde" in w for w in res.warnings)
    if kind == "ultrasonic":  # 4,5 m is beyond the range: no echo
        assert res.tests[-1].measured.magnitude == 0


@pytest.mark.parametrize(
    ("kind", "path", "name", "value"),
    [
        ("relay", "relay/songle-srd-05vdc-sl-c.yaml", "rcoil", 70.0),
        ("lm35", "sensor/ti-lm35dz.yaml", "sens", 10e-3),
        ("acs712", "sensor/allegro-acs712.yaml", "sens", None),
        ("stepper_motor", "motor/stepperonline-omc-17hs19-2004s1.yaml", "r", None),
        ("ntc", "thermistor/vishay-ntcle100e3103jb0.yaml", "beta", 3977.0),
        ("ntc", "thermistor/tdk-b57164k0103j000.yaml", "beta", 4300.0),
        ("ldr", "sensor/token-gl5528-ldr.yaml", "r10", 15e3),  # centre of 10 to 20 kΩ
        ("hall_linear", "sensor/honeywell-ss49e.yaml", "sens", 14e-3),
        ("hall_switch", "sensor/allegro-a3144.yaml", "bop", 21.0),
        ("pressure", "sensor/nxp-mpx5700dp.yaml", "pmax", 700.0),
        ("ultrasonic", "sensor/sparkfun-hc-sr04.yaml", "dmax", 4.0),
        ("lm35", "sensor/analog-devices-tmp36gt9z.yaml", "voff", 0.5),
        ("kty81", "sensor/nxp-kty81-110.yaml", "r25", 1000.0),
        ("kty81", "sensor/nxp-kty81-210.yaml", "r25", 2000.0),
        ("dht22", "sensor/aosong-dht22-am2302.yaml", "tsample", 2.0),
        ("ds18b20", "sensor/analog-devices-ds18b20.yaml", "tconv12", 0.75),
        ("bme280", "sensor/bosch-bme280.yaml", "pmax", 1100.0),
    ],
)
def test_as_per_03_catalogue_part(backend, kind, path, name, value):
    """AS-PER-03: a catalogue part gives its datasheet values to the model on the bench."""
    from circuitos.components.repository import load_records_file
    from circuitos.schematic.values import parse_value

    rec = load_records_file(DATA / path)[0]
    res = run_peripheral(kind, {}, {}, rec, backend)
    _ok(res)
    if value is not None:
        assert parse_value(res.used[name]) == pytest.approx(value, rel=1e-6)


def test_catalogue_filter_of_new_sensors():
    """Only TRIG/ECHO range finders go with the ultrasonic model; NTCs need R25 and β."""
    from circuitos.components.repository import load_records_file
    from circuitos.devices.peripherals import part_applies

    sr04 = load_records_file(DATA / "sensor/sparkfun-hc-sr04.yaml")[0]
    ub500 = load_records_file(DATA / "sensor/pepperl-fuchs-ub500-f42s-e5-v15.yaml")[0]
    assert part_applies("ultrasonic", sr04)
    assert not part_applies("ultrasonic", ub500)
    assert not part_applies("ntc", sr04)


def test_unknown_bench_and_bad_values(backend):
    with pytest.raises(BenchError):
        run_peripheral("resistor", {}, {}, None, backend)
    with pytest.raises(BenchError):
        run_peripheral("lm35", {"sens": "abc"}, {}, None, backend)
