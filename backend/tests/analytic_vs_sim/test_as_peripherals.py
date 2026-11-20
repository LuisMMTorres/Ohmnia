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
    ],
)
def test_as_per_02_other_conditions(backend, kind, params, fixture):
    """AS-PER-02: benches away from the defaults (other parts, ranges and loads)."""
    res = run_peripheral(kind, params, fixture, None, backend)
    _ok(res)
    if kind == "lm35":
        assert "LM-SAT" in {t.id for t in res.tests}


@pytest.mark.parametrize(
    ("kind", "path", "name", "value"),
    [
        ("relay", "relay/songle-srd-05vdc-sl-c.yaml", "rcoil", 70.0),
        ("lm35", "sensor/ti-lm35dz.yaml", "sens", 10e-3),
        ("acs712", "sensor/allegro-acs712.yaml", "sens", None),
        ("stepper_motor", "motor/stepperonline-omc-17hs19-2004s1.yaml", "r", None),
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


def test_unknown_bench_and_bad_values(backend):
    with pytest.raises(BenchError):
        run_peripheral("resistor", {}, {}, None, backend)
    with pytest.raises(BenchError):
        run_peripheral("lm35", {"sens": "abc"}, {}, None, backend)
