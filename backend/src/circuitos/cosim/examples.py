"""Integrated examples: microcontrollers, PLC, sensors, actuators and the circuit (Fase 11, D12).

Each example is a complete schematic (parts tied by node labels) with its program, ready to
co-simulate. The tests run every one of them and check the physical result.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from circuitos.schematic.library import pin_defs, pin_positions
from circuitos.schematic.model import Analysis, Component, NetLabel, NetRef, Probe, Schematic


class _Layout:
    def __init__(self, title: str):
        self.sch = Schematic(title=title)
        self._n = 0
        # ids unique per example, so the editor sees a new document and frames it
        self._id = "x" + hashlib.sha1(title.encode()).hexdigest()[:6]

    def add(self, kind: str, ref: str, at: tuple[int, int], nodes: dict[str, str],
            **params: str) -> Component:  # fmt: skip
        self._n += 1
        comp = Component(
            id=f"{self._id}c{self._n}", kind=kind, ref=ref, x=at[0], y=at[1], params=params
        )
        pos = pin_positions(comp)
        self.sch.components.append(comp)
        for p in pin_defs(comp):
            node = nodes.get(p.name)
            if node is None:
                continue  # unconnected pin: its own node
            x, y = pos[p.name]
            self.sch.labels.append(
                NetLabel(id=f"{self._id}l{len(self.sch.labels)}", name=node, x=x, y=y)
            )
        return comp

    def ground(self, at: tuple[int, int]) -> None:
        self._n += 1
        self.sch.components.append(
            Component(
                id=f"{self._id}c{self._n}", kind="ground", ref=f"GND{self._n}", x=at[0], y=at[1]
            )
        )
        self.sch.labels.append(
            NetLabel(id=f"{self._id}l{len(self.sch.labels)}", name="0", x=at[0], y=at[1])
        )

    def probe(self, *nets: str) -> None:
        """Voltage probes on labelled nets: the oscilloscope opens on them."""
        for net in nets:
            self.sch.probes.append(
                Probe(id=f"{self._id}p{len(self.sch.probes)}", kind="v", target=NetRef(net=net))
            )

    def tran(self, tstop: str) -> Schematic:
        self.sch.analyses = [Analysis(kind="tran", params={"tstop": tstop})]
        return self.sch


# ------------------------------------------------------------------------------------- E1

PWM_TEMPERATURE = """// Controle PI de temperatura: LM35 em A0, MOSFET no pino 9.
// PWM lento (proporcional no tempo, janela de 1 s), como se faz com aquecedores e relés de
// estado sólido: o MOSFET chaveia totalmente e a potência média é a razão cíclica vezes
// a potência plena. (analogWrite a 490 Hz também funciona, com "PWM = chaveado" na placa,
// mas exige passo de ~50 µs e uma simulação 40 vezes mais longa.)
const float SETPOINT = 60.0;          // °C
const float KP = 20.0;                // passos (0-255) por °C
const float KI = 2.0;                 // passos por °C·s
const unsigned long JANELA = 1000;    // ms
float integral = 0;
float temperatura;
int pwm = 0;
unsigned long inicio = 0, ultimoSerial = 0;

void setup() {
  pinMode(9, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  unsigned long agora = millis();
  if (agora - inicio >= JANELA || agora == 0) {           // PI uma vez por janela
    inicio = agora;
    temperatura = analogRead(A0) * 5.0 / 1023.0 * 100.0;  // LM35: 10 mV/°C
    float erro = SETPOINT - temperatura;
    integral = constrain(integral + KI * erro * JANELA / 1000.0, 0, 255);
    pwm = constrain(KP * erro + integral, 0, 255);
  }
  digitalWrite(9, agora - inicio < (unsigned long)pwm * JANELA / 255 ? HIGH : LOW);
  if (agora - ultimoSerial >= 5000) {
    ultimoSerial = agora;
    Serial.print("T = "); Serial.print(temperatura, 1);
    Serial.print(" °C  PWM = "); Serial.println(pwm);
  }
  delay(10);
}
"""


def arduino_pwm_temperature() -> Schematic:
    s = _Layout("Arduino: controle PI de temperatura (LM35, MOSFET, aquecedor)")
    s.probe("t_sig", "gate")
    s.add("arduino_uno", "U1", (0, 0), {"GND": "0", "5V": "v5", "A0": "t_sig", "D9": "d9"},
          program=PWM_TEMPERATURE)  # fmt: skip
    s.add("lm35", "S1", (-22, -6), {"VS": "v5", "GND": "0", "OUT": "t_sig"}, temp="v(h1_temp)")
    s.add("resistor", "RG", (14, 4), {"1": "d9", "2": "gate"}, value="100")
    # generic MOSFET with a power-device transconductance (the default is a small-signal one)
    s.add("nmos", "Q1", (24, 4), {"d": "hd", "g": "gate", "s": "0"}, vto="2", kp="5")
    s.add("heater", "H1", (24, -6), {"1": "v12", "2": "hd"}, r="10", rth="5", cth="2", tamb="25")
    s.add("vdc", "V1", (36, -2), {"p": "v12", "n": "0"}, dc="12")
    s.ground((36, 4))
    return s.tran("60")


# ------------------------------------------------------------------------------------- E2

ENERGY_METER = """// Medidor de energia: tensão em IO34 (divisor com polarização de 1,25 V),
// corrente em IO35 (ACS712 de 185 mV/A, saída reduzida a 2/3 por divisor)
const float VBIAS = 1.25;          // V
const float KV = 221.0;            // (220k + 1k) / 1k
const float SENS = 0.185;          // V/A
const int N = 400;                 // amostras por janela (200 ms a 2 kHz)
float sv, si, sv2, si2, svi;
int n = 0;
float vrms, irms, p, fp;

void setup() { Serial.begin(115200); }

void loop() {
  float v = (analogReadMilliVolts(34) / 1000.0 - VBIAS) * KV;
  float i = (analogReadMilliVolts(35) / 1000.0 * 1.5 - 2.5) / SENS;
  sv += v; si += i; sv2 += v * v; si2 += i * i; svi += v * i;
  n++;
  if (n == N) {
    float mv = sv / N, mi = si / N;
    vrms = sqrt(sv2 / N - mv * mv);
    irms = sqrt(si2 / N - mi * mi);
    p = svi / N - mv * mi;
    fp = p / (vrms * irms);
    Serial.printf("Vrms=%.1f V  Irms=%.2f A  P=%.0f W  FP=%.2f\\n", vrms, irms, p, fp);
    sv = si = sv2 = si2 = svi = 0;
    n = 0;
  }
  delayMicroseconds(500);
}
"""


def esp32_energy_meter() -> Schematic:
    s = _Layout("ESP32: medidor de energia (ACS712 e divisor de tensão)")
    s.probe("vm", "im")
    s.add("vsin", "V1", (-40, 0), {"p": "fase", "n": "0"}, amplitude="179.6", freq="60")
    s.add("acs712", "S1", (-24, 0), {"IP+": "fase", "IP-": "carga", "VCC": "v5", "GND": "0",
                                     "OUT": "acs"})  # fmt: skip
    s.add("rl_load", "Z1", (-24, 12), {"1": "carga", "2": "0"}, r="50", l="0.1")
    s.add("vdc", "V2", (-8, -12), {"p": "v5", "n": "0"}, dc="5")
    s.add("resistor", "R3", (-8, 0), {"1": "acs", "2": "im"}, value="10k")
    s.add("resistor", "R4", (-8, 8), {"1": "im", "2": "0"}, value="20k")
    s.add("resistor", "R1", (-40, -14), {"1": "fase", "2": "vm"}, value="220k")
    s.add("resistor", "R2", (-26, -14), {"1": "vm", "2": "bias"}, value="1k")
    s.add("vdc", "V3", (-14, -20), {"p": "bias", "n": "0"}, dc="1.25")
    s.add("esp32_devkitc", "U1", (12, 0), {"GND": "0", "IO34": "vm", "IO35": "im"},
          program=ENERGY_METER)  # fmt: skip
    s.ground((0, 14))
    return s.tran("0.5")


# ------------------------------------------------------------------------------------- E3

LOOP_LADDER = """{
  "rungs": [
    {"comment": "Liga (I0) e desliga (I1) o controle, com selo",
     "branches": [[{"type": "NO", "var": "I0"}, {"type": "NC", "var": "I1"}],
                  [{"type": "NO", "var": "M0"}, {"type": "NC", "var": "I1"}]],
     "coils": [{"type": "coil", "var": "M0"}]},
    {"comment": "Abaixo de 58 °C (10,19 mA) liga o aquecedor",
     "branches": [[{"type": "NO", "var": "M0"}, {"type": "CMP", "expr": "AI0 < 10.19"}]],
     "coils": [{"type": "set", "var": "Q0"}]},
    {"comment": "Acima de 62 °C (10,61 mA) ou controle desligado: desliga",
     "branches": [[{"type": "CMP", "expr": "AI0 > 10.61"}], [{"type": "NC", "var": "M0"}]],
     "coils": [{"type": "reset", "var": "Q0"}]}
  ]
}"""


def plc_4_20ma_loop() -> Schematic:
    s = _Layout("CLP: laço 4-20 mA de temperatura com histerese em ladder")
    s.probe("ai0", "i0", "h_a")
    s.add("vdc", "V1", (-36, 0), {"p": "p24", "n": "0"}, dc="24")
    s.add("tx420", "TT1", (-22, 6), {"+": "p24", "-": "ai0"}, x="v(h1_temp)", lo="0", hi="150")
    s.add("plc", "CLP1", (0, 0),
          {"L+": "p24", "M": "0", "I0": "i0", "I1": "i1", "AI0": "ai0", "Q0a": "p24",
           "Q0b": "h_a"},
          language="ladder", ladder=LOOP_LADDER)  # fmt: skip
    s.add("switch_manual", "B1", (-22, -8), {"1": "p24", "2": "i0"}, state="0 0 1 0 1.001 1")
    s.add("switch_manual", "B2", (-22, -14), {"1": "p24", "2": "i1"},
          state="0 0 40 0 40.001 1")  # fmt: skip
    s.add("heater", "H1", (20, 8), {"1": "h_a", "2": "0"}, r="12", rth="1.5", cth="3", tamb="25")
    s.ground((-36, 8))
    return s.tran("60")


# ------------------------------------------------------------------------------------- E4

ESP_CONDITIONER = """// ESP32 lê o LM35 (IO34) e entrega 0 a 3,3 V no DAC (IO25) para 0 a 100 °C;
// o amp-op amplifica para 0 a 10 V, a faixa da entrada AI1 do CLP
float temperatura;
void setup() { Serial.begin(115200); }
void loop() {
  temperatura = analogReadMilliVolts(34) / 10.0;          // LM35: 10 mV/°C
  int codigo = constrain(temperatura / 100.0 * 255.0, 0, 255);
  dacWrite(25, codigo);
  delay(50);
}
"""
FAN_ST = """(* CLP: AI1 em 0-10 V = 0-100 °C; ventilador (Q0) liga acima de 70 °C e desliga abaixo
   de 65 °C *)
VAR temperatura : REAL; END_VAR
temperatura := AI1 * 10.0;
IF temperatura > 70.0 THEN
  Q0 := TRUE;
ELSIF temperatura < 65.0 THEN
  Q0 := FALSE;
END_IF;
"""


def esp32_plc_conditioner() -> Schematic:
    s = _Layout("ESP32 + CLP: o ESP32 condiciona o sensor e entrega 0-10 V ao CLP")
    s.probe("lm", "dac", "ai", "fan")
    s.add("vdc", "V5", (-44, -10), {"p": "v5", "n": "0"}, dc="5")
    s.add("lm35", "S1", (-32, -4), {"VS": "v5", "GND": "0", "OUT": "lm"}, temp="0 20 20 90")
    s.add("esp32_devkitc", "U1", (-14, 0), {"GND": "0", "IO34": "lm", "IO25": "dac"},
          program=ESP_CONDITIONER)  # fmt: skip
    s.add("opamp", "A1", (8, 0), {"inp": "dac", "inn": "fb", "out": "ai"}, vcc="15", vee="-15")
    s.add("resistor", "RF", (8, -8), {"1": "fb", "2": "ai"}, value="20.3k")
    s.add("resistor", "RG", (0, -8), {"1": "fb", "2": "0"}, value="10k")
    s.add("vdc", "V24", (20, -14), {"p": "p24", "n": "0"}, dc="24")
    s.add("plc", "CLP1", (30, 0),
          {"L+": "p24", "M": "0", "AI1": "ai", "Q0a": "p24", "Q0b": "fan"},
          language="st", st=FAN_ST, ai1="0-10V")  # fmt: skip
    s.add("dc_motor", "M1", (48, 6), {"+": "fan", "-": "0"}, r="20", ke="0.02", kt="0.02")
    s.ground((-44, -2))
    return s.tran("20")


# ------------------------------------------------------------------------------------- E5

PUMP_ST = """(* Pressão constante: PID no CLP comanda o inversor (AQ0, 0-10 V = 0-60 Hz);
   transmissor de pressão 0-10 bar em AI0 (4-20 mA); I0 liga, I1 desliga *)
VAR
  rodando : BOOL;
  pressao : REAL;
  pid1 : PID;
END_VAR
rodando := (I0 OR rodando) AND NOT I1;
Q0 := rodando;                              (* habilita o inversor (RUN) *)
pressao := (AI0 - 4.0) / 16.0 * 10.0;       (* bar *)
pid1(SP := 3.0, PV := pressao, KP := 1.5, TI := 2.0, TD := 0.0,
     OUT_MIN := 0.0, OUT_MAX := 10.0, ENABLE := rodando);
AQ0 := pid1.OUT;
"""
PUMP_SUPERVISOR = """// ESP32 supervisório: lê a referência do inversor (AQ0 do CLP, divisor 1/4)
float hz;
unsigned long ultimo = 0;
void setup() { Serial.begin(115200); }
void loop() {
  hz = analogReadMilliVolts(34) / 1000.0 * 4.0 * 6.0;     // 0-10 V -> 0-60 Hz
  if (millis() - ultimo >= 5000) {
    ultimo = millis();
    Serial.printf("referência do inversor: %.1f Hz\\n", hz);
  }
  delay(100);
}
"""


def pump_constant_pressure() -> Schematic:
    s = _Layout("Bombeamento com pressão constante: CLP (PID), inversor, bomba e ESP32")
    s.probe("ref", "ai0", "run")
    s.add("vdc", "V24", (-40, 0), {"p": "p24", "n": "0"}, dc="24")
    s.add("switch_manual", "B1", (-26, -8), {"1": "p24", "2": "i0"}, state="0 0 1 0 1.001 1")
    s.add("plc", "CLP1", (0, 0),
          {"L+": "p24", "M": "0", "I0": "i0", "AI0": "ai0", "Q0a": "p24", "Q0b": "run",
           "AQ0": "ref"},
          language="st", st=PUMP_ST)  # fmt: skip
    s.add("pump_plant", "PL1", (26, 0),
          {"AI": "ref", "GND": "0", "RUN": "run", "COM": "0", "PT+": "p24", "PT-": "ai0"},
          pmax="5", accel="5", demand="0 0.3 30 0.3 31 0.6")  # fmt: skip
    s.add("resistor", "R1", (26, 14), {"1": "ref", "2": "esp"}, value="30k")
    s.add("resistor", "R2", (36, 14), {"1": "esp", "2": "0"}, value="10k")
    s.add("esp32_devkitc", "U1", (54, 6), {"GND": "0", "IO34": "esp"},
          program=PUMP_SUPERVISOR)  # fmt: skip
    s.ground((-40, 8))
    return s.tran("60")


# ------------------------------------------------------------------------------------- E6

START_LADDER = """{
  "rungs": [
    {"comment": "Liga (I0) e desliga (I1) com selo",
     "branches": [[{"type": "NO", "var": "I0"}, {"type": "NC", "var": "I1"}],
                  [{"type": "NO", "var": "M0"}, {"type": "NC", "var": "I1"}]],
     "coils": [{"type": "coil", "var": "M0"}]},
    {"comment": "Partida direta: bobina do contator K1",
     "branches": [[{"type": "NO", "var": "M0"}]],
     "coils": [{"type": "coil", "var": "Q0"}]},
    {"comment": "Partida suave: RUN do soft-starter",
     "branches": [[{"type": "NO", "var": "M0"}]],
     "coils": [{"type": "coil", "var": "Q1"}]}
  ]
}"""


def motor_start_comparison() -> Schematic:
    s = _Layout("Partida de motor: direta com contator × soft-starter, comandadas pelo CLP")
    s.probe("m1_i", "m2_i", "m1_rpm", "m2_rpm")
    s.add("v3ph", "V1", (-44, 20), {"a": "l1", "b": "l2", "c": "l3", "n": "0"},
          vrms="219.393")  # fmt: skip
    s.add("vdc", "V24", (-44, -10), {"p": "p24", "n": "0"}, dc="24")
    s.add("switch_manual", "B1", (-30, -16), {"1": "p24", "2": "i0"}, state="0 0 1 0 1.05 1")
    s.add("switch_manual", "B2", (-30, -22), {"1": "p24", "2": "i1"},
          state="0 0 9 0 9.05 1")  # fmt: skip
    s.add("plc", "CLP1", (-10, -12),
          {"L+": "p24", "M": "0", "I0": "i0", "I1": "i1", "Q0a": "p24", "Q0b": "k1",
           "Q1a": "p24", "Q1b": "ss_run"},
          language="ladder", ladder=START_LADDER)  # fmt: skip
    s.add("contactor", "K1", (14, 4),
          {"A1": "k1", "A2": "0", "L1": "l1", "T1": "u1", "L2": "l2", "T2": "v1", "L3": "l3",
           "T3": "w1"})  # fmt: skip
    s.add("induction_motor", "M1", (32, 4), {"A": "u1", "B": "v1", "C": "w1"},
          tl="20", load="quadrática")  # fmt: skip
    s.add("soft_starter", "SS1", (14, 24),
          {"L1": "l1", "L2": "l2", "L3": "l3", "RUN": "ss_run", "COM": "0", "T1": "u2",
           "T2": "v2", "T3": "w2"},
          control="limitação de corrente", ilim="15", tacc="10", tdec="2")  # fmt: skip
    s.add("induction_motor", "M2", (32, 24), {"A": "u2", "B": "v2", "C": "w2"},
          tl="20", load="quadrática")  # fmt: skip
    s.ground((-44, -2))
    s.ground((-44, 28))
    return s.tran("12")


# ------------------------------------------------------------------------------------- E7

STEPPER_PROGRAM = """// Posicionamento com motor de passo: driver em 1/4 de passo (0,45° por pulso).
// D2 = STEP, D3 = DIR. Vai a 180°, volta a 90° e retorna à origem, com rampa de
// aceleração (intervalo entre pulsos de 4 ms caindo para 1,5 ms).
const int STEP = 2;
const int DIR = 3;
const float GRAUS_POR_PULSO = 0.45;
long posicao = 0;   // pulsos desde a origem
float angulo = 0;   // graus (variável vista no osciloscópio)

void pulso(int intervalo_us) {
  digitalWrite(STEP, HIGH);
  delayMicroseconds(intervalo_us / 2);
  digitalWrite(STEP, LOW);
  delayMicroseconds(intervalo_us / 2);
}

void mover(long alvo) {
  int sentido = alvo > posicao ? 1 : -1;
  digitalWrite(DIR, sentido > 0 ? HIGH : LOW);
  delay(1);
  long total = alvo > posicao ? alvo - posicao : posicao - alvo;
  for (long i = 0; i < total; i++) {
    long resta = total - i;
    long rampa = i < resta ? i : resta;            // acelera e desacelera
    int intervalo = 4000 - rampa * 50;
    if (intervalo < 1500) intervalo = 1500;
    pulso(intervalo);
    posicao += sentido;
    angulo = posicao * GRAUS_POR_PULSO;
  }
  Serial.print("posição: ");
  Serial.print(angulo);
  Serial.println(" graus");
}

void setup() {
  pinMode(STEP, OUTPUT);
  pinMode(DIR, OUTPUT);
  Serial.begin(9600);
  delay(100);
  mover(400);    // 180°
  delay(300);
  mover(200);    // 90°
  delay(300);
  mover(0);      // origem
}

void loop() {
  delay(1000);
}
"""


def stepper_positioning() -> Schematic:
    s = _Layout("Posicionamento: Arduino, driver STEP/DIR e motor de passo 17HS19")
    s.probe("m1_deg", "step")
    s.add("vdc", "V12", (-30, 16), {"p": "vm", "n": "0"}, dc="12")
    s.add("arduino_uno", "U1", (-20, 0), {"GND": "0", "D2": "step", "D3": "dir"},
          program=STEPPER_PROGRAM)  # fmt: skip
    s.add("stepper_driver", "DRV1", (4, 0),
          {"STEP": "step", "DIR": "dir", "GND": "0", "VM": "vm", "A+": "a1", "A-": "a2",
           "B+": "b1", "B-": "b2"},
          ifull="1.5", micro="4")  # fmt: skip
    s.add("stepper_motor", "M1", (22, 0), {"A+": "a1", "A-": "a2", "B+": "b1", "B-": "b2"},
          b="2e-3", jl="2e-5")  # fmt: skip
    s.ground((-30, 24))
    return s.tran("2.6")


EXAMPLES: dict[str, tuple[str, Callable[[], Schematic]]] = {
    "Arduino: controle PI de temperatura (PWM)": (
        "Arduino lê o LM35 e comanda o aquecedor por MOSFET em PWM; alvo de 60 °C.",
        arduino_pwm_temperature,
    ),
    "ESP32: medidor de energia": (
        "ACS712 e divisor de tensão no ESP32: tensão e corrente RMS, potência e fator de "
        "potência de uma carga RL em 127 V (divisor resistivo só na simulação: na bancada, use "
        "transformador ou sensor isolado).",
        esp32_energy_meter,
    ),
    "CLP: laço 4-20 mA com histerese (ladder)": (
        "Transmissor de temperatura 4-20 mA na AI0, ladder liga o aquecedor pelo relé Q0 entre "
        "58 e 62 °C; botões de liga e desliga em I0 e I1.",
        plc_4_20ma_loop,
    ),
    "ESP32 + CLP: condicionamento 0-10 V": (
        "ESP32 lê o LM35 e gera 0-3,3 V no DAC; o amp-op leva a 0-10 V para a AI1 do CLP, que "
        "liga o ventilador acima de 70 °C.",
        esp32_plc_conditioner,
    ),
    "Bombeamento: CLP com PID, inversor e bomba": (
        "PID no CLP mantém 3 bar com o inversor e a bomba; o consumo sobe em 30 s e o PID "
        "compensa; o ESP32 mostra a referência do inversor.",
        pump_constant_pressure,
    ),
    "Partida de motor: direta × soft-starter (CLP)": (
        "O CLP liga, ao mesmo tempo, um motor de indução por contator (partida direta) e outro "
        "por soft-starter com limitação de corrente em 15 A; compare as correntes de partida.",
        motor_start_comparison,
    ),
    "Arduino: posicionamento com motor de passo": (
        "O Arduino gera pulsos STEP/DIR com rampa para um driver em 1/4 de passo e leva o "
        "motor a 180°, 90° e à origem; a posição real aparece em v(m1_deg).",
        stepper_positioning,
    ),
}
