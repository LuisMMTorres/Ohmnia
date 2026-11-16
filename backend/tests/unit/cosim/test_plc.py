# ruff: noqa: E501  (embedded program sources)
"""PLC runtime: ladder, structured text, function blocks and the scan cycle."""

from __future__ import annotations

import pytest

from circuitos.cosim.plc import PlcError, PlcRuntime, time_ms

SCAN = 0.01


def scans(rt: PlcRuntime, n: int, **inputs):  # type: ignore[no-untyped-def]
    out = {}
    for _ in range(n):
        out = rt.scan({k.upper(): v for k, v in inputs.items()}, SCAN)
    return out


SEAL_IN = {
    "rungs": [
        {
            # start (I0) OR self-holding (Q0), AND NOT stop (I1) → motor (Q0)
            "branches": [[{"type": "NO", "var": "I0"}], [{"type": "NO", "var": "Q0"}]],
            "coils": [],
        },
    ]
}


def test_time_literals():
    assert time_ms("T#5s") == 5000
    assert time_ms("T#1m30s") == 90000
    assert time_ms("TIME#250ms") == 250
    assert time_ms("T#1.5s") == 1500


def test_ladder_start_stop_seal_in():
    ladder = {
        "rungs": [
            {
                "branches": [
                    [{"type": "NO", "var": "I0"}, {"type": "NC", "var": "I1"}],
                    [{"type": "NO", "var": "Q0"}, {"type": "NC", "var": "I1"}],
                ],
                "coils": [{"type": "coil", "var": "Q0"}],
            }
        ]
    }
    rt = PlcRuntime("ladder", ladder=ladder)
    assert scans(rt, 1, I0=True, I1=False)["Q0"] is True
    assert scans(rt, 3, I0=False, I1=False)["Q0"] is True  # holds itself
    assert scans(rt, 1, I0=False, I1=True)["Q0"] is False
    assert scans(rt, 1, I0=False, I1=False)["Q0"] is False


def test_ladder_timer_counter_and_comparison():
    ladder = {
        "rungs": [
            {"branches": [[{"type": "NO", "var": "I0"}, {"type": "TON", "name": "T1", "pt": "T#100ms"}]],
             "coils": [{"type": "coil", "var": "Q0"}]},
            {"branches": [[{"type": "P", "var": "I2"}, {"type": "CTU", "name": "C1", "pv": 3, "reset": "I3"}]],
             "coils": [{"type": "coil", "var": "Q1"}]},
            {"branches": [[{"type": "CMP", "expr": "AI0 > 12.0"}]],
             "coils": [{"type": "set", "var": "Q2"}]},
            {"branches": [[{"type": "CMP", "expr": "AI0 < 8.0"}]],
             "coils": [{"type": "reset", "var": "Q2"}]},
            {"branches": [[{"type": "NO", "var": "Q2"}]],
             "coils": [{"type": "move", "dst": "AQ0", "src": "(AI0 - 4.0) / 16.0 * 10.0"}]},
        ]
    }  # fmt: skip
    rt = PlcRuntime("ladder", ladder=ladder)
    assert scans(rt, 9, I0=True)["Q0"] is False  # 90 ms
    assert scans(rt, 2, I0=True)["Q0"] is True  # 110 ms
    for _ in range(3):
        scans(rt, 1, I2=True)
        out = scans(rt, 1, I2=False)
    assert out["Q1"] is True
    assert scans(rt, 1, I3=True)["Q1"] is False
    out = scans(rt, 1, AI0=13.0)
    assert out["Q2"] is True and out["AQ0"] == pytest.approx(5.625)
    assert scans(rt, 1, AI0=10.0)["Q2"] is True  # hysteresis band: keeps
    assert scans(rt, 1, AI0=7.0)["Q2"] is False


def test_structured_text_hysteresis_case_and_loops():
    st = """
    PROGRAM main
    VAR
      heat : BOOL;
      mode : INT := 0;
      i, total : INT;
      t1 : TON;
    END_VAR
    (* hysteresis on a 4-20 mA temperature reading *)
    IF AI0 < 10.0 THEN heat := TRUE;
    ELSIF AI0 > 14.0 THEN heat := FALSE;
    END_IF;
    Q0 := heat;
    t1(IN := heat, PT := T#50ms);
    Q1 := t1.Q;
    CASE mode OF
      0: mode := 1;
      1, 2: mode := mode + 1;
      3..5: mode := 0;
    END_CASE;
    total := 0;
    FOR i := 1 TO 4 DO total := total + i; END_FOR;
    AQ0 := LIMIT(0.0, INT_TO_REAL(total), 10.0);
    END_PROGRAM
    """
    rt = PlcRuntime("st", st=st)
    out = scans(rt, 1, AI0=8.0)
    assert out["Q0"] is True and out["AQ0"] == 10.0
    assert scans(rt, 6, AI0=12.0)["Q1"] is True  # still heating (band), timer elapsed
    assert scans(rt, 1, AI0=15.0)["Q0"] is False
    assert rt.vars["MODE"] in (0, 1, 2, 3)
    snap = rt.snapshot()
    assert "T1.ET" in snap and snap["Q0"] == 0.0


def test_pid_brings_a_first_order_plant_to_the_set_point():
    st = """
    VAR pid1 : PID; END_VAR
    pid1(SP := 50.0, PV := AI0, KP := 2.0, TI := 1.0, TD := 0.0, OUT_MIN := 0.0, OUT_MAX := 10.0);
    AQ0 := pid1.OUT;
    """
    rt = PlcRuntime("st", st=st)
    y = 0.0
    for _ in range(3000):  # 30 s, plant: tau = 2 s, gain 10 units per volt
        u = rt.scan({"AI0": y}, SCAN)["AQ0"]
        y += SCAN / 2.0 * (10.0 * u - y)
    assert y == pytest.approx(50.0, abs=0.5)


@pytest.mark.parametrize(
    ("lang", "src", "fragment"),
    [
        ("st", "x := 1;", "não declarada"),
        ("st", "VAR a : FOO; END_VAR", "FOO"),
        ("st", "VAR i : INT; END_VAR WHILE TRUE DO i := i + 1; END_WHILE;", "watchdog"),
        ("st", "Q0 := ;", "expressão"),
        ("ladder", '{"rungs": [{"branches": [[{"type": "XX"}]], "coils": []}]}', "XX"),
        ("cobol", "", "linguagem"),
    ],
)
def test_errors_in_portuguese(lang, src, fragment):
    with pytest.raises(PlcError, match=fragment):
        rt = PlcRuntime(lang, st=src, ladder=src)
        rt.scan({}, SCAN)
