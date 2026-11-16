# ruff: noqa: E501  (embedded program sources)
"""Arduino-style interpreter: language, Arduino API and the time model, with a fake circuit."""

from __future__ import annotations

import pytest

from circuitos.cosim.arduino import BOARDS, Runtime
from circuitos.cosim.clang import CError


class FakeHw:
    def __init__(self, volts=None):
        self.volts = volts or {}
        self.events: list[tuple[float, int, str, float]] = []
        self.lines: list[tuple[float, str]] = []
        self.warnings: list[str] = []
        self.rt: Runtime | None = None

    def voltage(self, pin):
        v = self.volts.get(pin, 0.0)
        return v(self.rt.now()) if callable(v) else v

    def output(self, pin, kind, value):
        self.events.append((round(self.rt.now(), 6), pin, kind, value))

    def serial(self, time, text):
        self.lines.append((round(time, 6), text))

    def warn(self, text):
        self.warnings.append(text)


def run(src, until, board="arduino_uno", volts=None):
    hw = FakeHw(volts)
    rt = Runtime(src, BOARDS[board], hw)
    hw.rt = rt
    rt.advance(until)
    return rt, hw


def test_blink_follows_delay_in_simulated_time():
    src = """
    void setup() { pinMode(13, OUTPUT); }
    void loop() { digitalWrite(13, HIGH); delay(100); digitalWrite(13, LOW); delay(100); }
    """
    _, hw = run(src, 0.45)
    writes = [(t, v) for t, p, k, v in hw.events if k == "digital"]
    assert [v for _, v in writes[:5]] == [1.0, 0.0, 1.0, 0.0, 1.0]
    assert writes[1][0] == pytest.approx(0.1, abs=2e-4)
    assert writes[2][0] == pytest.approx(0.2, abs=4e-4)


def test_analog_read_quantises_and_pwm_scales():
    src = """
    int v; void setup() { Serial.begin(9600); }
    void loop() { v = analogRead(A0); analogWrite(9, v / 4); Serial.println(v); delay(10); }
    """
    rt, hw = run(src, 0.005, volts={14: 2.5})
    assert rt.globals["v"].value == 512  # round(2.5/5 * 1023)
    pwm = [v for _, p, k, v in hw.events if k == "pwm"]
    assert pwm[0] == pytest.approx(128 / 255)
    assert hw.lines[0][1] == "512"


def test_int_is_16_bits_on_the_uno_and_32_on_the_esp32():
    src = (
        "int x = 32767; long y; void setup() { x = x + 1; y = 70000; } void loop() { delay(1000); }"
    )
    rt, _ = run(src, 0.001)
    assert rt.globals["x"].value == -32768 and rt.globals["y"].value == 70000
    rt, _ = run(src, 0.001, board="esp32_devkitc")
    assert rt.globals["x"].value == 32768


def test_integer_division_floats_and_print_format():
    src = r"""
    void setup() {
      int a = 7 / 2; float b = 7 / 2.0; int r = -7 % 3;
      Serial.print(a); Serial.print(" "); Serial.print(b); Serial.print(" ");
      Serial.print(b, 3); Serial.print(" "); Serial.println(r);
      Serial.println(255, HEX);
      Serial.printf("t=%d ms v=%.1f\n", 12, 3.14159);
    }
    void loop() { delay(1000); }
    """
    _, hw = run(src, 0.001)
    assert [line for _, line in hw.lines] == ["3 3.50 3.500 -1", "FF", "t=12 ms v=3.1"]


def test_control_flow_functions_arrays_and_switch():
    src = """
    const int N = 5; int v[N] = {3, 1, 4, 1, 5}; int total; int state = 0; int hits;
    int sum(int n) { int s = 0; for (int i = 0; i < n; i++) { if (v[i] == 1) continue; s += v[i]; } return s; }
    void step() {
      switch (state) { case 0: hits++; state = 1; break; case 1: hits += 10; state = 2; break;
                       default: state = 0; }
    }
    void setup() { total = sum(N); int k = 0; while (true) { k++; if (k > 3) break; } do { k--; } while (k > 0); }
    void loop() { step(); delay(10); }
    """
    rt, _ = run(src, 0.045)
    assert rt.globals["total"].value == 12
    # loop() at ~0, 10, 20, 30 and 40 ms: state 0 → 1 (+1), 1 → 2 (+10), 2 → 0, 0 → 1 (+1), 1 → 2 (+10)
    assert rt.globals["hits"].value == 22


def test_user_function_with_delay_hands_time_to_the_circuit():
    src = """
    void pulse(int ms) { digitalWrite(5, HIGH); delay(ms); digitalWrite(5, LOW); }
    void setup() { pinMode(5, OUTPUT); }
    void loop() { pulse(20); delay(80); }
    """
    _, hw = run(src, 0.25)
    times = [t for t, p, k, v in hw.events if p == 5]
    assert times[1] - times[0] == pytest.approx(0.02, abs=2e-4)
    assert times[2] - times[0] == pytest.approx(0.1, abs=5e-4)


def test_millis_counts_simulated_time():
    src = """
    unsigned long t0; unsigned long dt;
    void setup() { t0 = millis(); delay(250); dt = millis() - t0; }
    void loop() { delay(1000); }
    """
    rt, _ = run(src, 0.3)
    assert 249 <= rt.globals["dt"].value <= 251


def test_digital_read_has_hysteresis():
    seq = iter([4.0, 2.0, 1.0, 2.0, 4.0])
    src = """
    int r[5]; void setup() { for (int i = 0; i < 5; i++) { r[i] = digitalRead(7); delay(1); } }
    void loop() { delay(1000); }
    """
    rt, _ = run(src, 0.01, volts={7: lambda t: next(seq)})
    assert rt.globals["r"].value == [1, 1, 0, 0, 1]  # 2 V is between 1.5 V and 3 V: keeps state


def test_esp32_dac_ledc_and_adc_range_warning():
    src = """
    void setup() { ledcAttach(18, 5000, 10); }
    void loop() { dacWrite(25, 128); ledcWrite(18, 512); int x = analogRead(34); delay(10); }
    """
    _, hw = run(src, 0.001, board="esp32_devkitc", volts={34: 3.0})
    kinds = {(p, k): v for _, p, k, v in hw.events}
    assert kinds[(25, "dac")] == pytest.approx(128 / 255 * 3.3)
    assert kinds[(18, "pwm")] == pytest.approx(512 / 1023)
    assert any("fora da faixa efetiva" in w for w in hw.warnings)


@pytest.mark.parametrize(
    ("src", "fragment"),
    [
        ("void setup() {}", "loop()"),
        ("void setup() { int *p; } void loop() {}", "ponteiros"),
        ("struct S { int a; }; void setup() {} void loop() {}", "struct"),
        ("void setup() { x = 1; } void loop() {}", "não declarada"),
        ("void setup() { pinMode(40, OUTPUT); } void loop() {}", "pino 40"),
        ("void setup() { int a = 1 }\nvoid loop() {}", "linha 1"),
    ],
)
def test_errors_are_reported_in_portuguese(src, fragment):
    with pytest.raises(CError, match=fragment):
        run(src, 0.001)
