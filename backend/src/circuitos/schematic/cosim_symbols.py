"""Symbols and SPICE models of controllers, sensors and actuators (Fase 11, decision D12).

Controllers (Arduino Uno, ESP32-DevKitC, PLC) become EXTERNAL sources and input loads; the
co-simulation (:mod:`circuitos.cosim.engine`) drives the sources from the running program.
Sensors and actuators are behavioural SPICE models. A *stimulus* parameter (temperature,
position, demand...) accepts a constant (``25``), a time profile as time/value pairs
(``0 25 10 80``: 25 at 0 s, 80 at 10 s) or a node voltage (``v(h1_temp)``: the temperature of a
heater, for instance).

Default values cite their datasheet in the parameter help; the rest are didactic defaults, said
so in the description.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable

from circuitos.components.models import ComponentRecord
from circuitos.core.units import Q_, parse_unit
from circuitos.machines.stepper import torque_constant
from circuitos.schematic.model import Component
from circuitos.schematic.symbols_base import ParamDef, PinDef, Symbol

Value = Callable[[str], str]  # parameter name -> text (with overrides applied)


def _stim(name: str, label: str, unit: str, default: str, help_: str = "") -> ParamDef:
    return ParamDef(
        name,
        label,
        unit,
        default,
        type="text",
        help=(help_ + " " if help_ else "")
        + "Constante (25), perfil no tempo em pares tempo/valor (0 25 10 80) ou tensão de um nó "
        "(v(h1_temp)).",
    )


def _box_pins(left: list[str], right: list[str], half: int = 4) -> tuple[PinDef, ...]:
    n = max(len(left), len(right))
    top = -(n - 1)
    pins = [PinDef(p, -half, top + 2 * i) for i, p in enumerate(left)]
    pins += [PinDef(p, half, top + 2 * i) for i, p in enumerate(right)]
    return tuple(pins)


_UNO_LEFT = [f"A{i}" for i in range(6)] + ["5V", "GND"]
_UNO_RIGHT = [f"D{i}" for i in range(2, 14)]
_NANO_LEFT = [f"A{i}" for i in range(8)] + ["5V", "GND"]
_MEGA_LEFT = [f"A{i}" for i in range(16)] + ["5V", "GND"]
_MEGA_RIGHT = [f"D{i}" for i in (*range(2, 14), 20, 21, *range(22, 30), 44, 45, 46)]
_PICO_LEFT = ["GP26", "GP27", "GP28", "3V3", "GND"]
_PICO_RIGHT = [f"GP{i}" for i in range(23)]
_ESP_LEFT = [
    "3V3",
    "GND",
    "IO36",
    "IO39",
    "IO34",
    "IO35",
    "IO32",
    "IO33",
    "IO25",
    "IO26",
    "IO27",
    "IO14",
    "IO12",
]
_ESP_RIGHT = [
    "IO23",
    "IO22",
    "IO21",
    "IO19",
    "IO18",
    "IO5",
    "IO17",
    "IO16",
    "IO4",
    "IO2",
    "IO15",
    "IO13",
]
_PLC_LEFT = ["L+", "M", "I0", "I1", "I2", "I3", "I4", "I5", "AI0", "AI1"]
_PLC_RIGHT = ["Q0a", "Q0b", "Q1a", "Q1b", "Q2a", "Q2b", "Q3a", "Q3b", "AQ0"]

UNO_DEFAULT = """// Pisca o LED da placa e lê A0
void setup() {
  pinMode(13, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  int leitura = analogRead(A0);
  Serial.println(leitura);
  digitalWrite(13, HIGH);
  delay(250);
  digitalWrite(13, LOW);
  delay(250);
}
"""
PICO_DEFAULT = """// Pisca o LED da placa (GP25) e lê GP26 (A0)
void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(100);
  digitalWrite(LED_BUILTIN, LOW);
  delay(100);
  Serial.println(analogRead(A0));
}
"""

ESP_DEFAULT = """// Lê a tensão em IO34 e escreve no DAC (IO25)
void setup() {
  Serial.begin(115200);
}

void loop() {
  int mv = analogReadMilliVolts(34);
  dacWrite(25, mv * 255 / 3300);
  Serial.printf("IO34 = %d mV\\n", mv);
  delay(100);
}
"""
PLC_LADDER_DEFAULT = (
    '{"rungs": [{"comment": "partida e parada com selo", "branches": '
    '[[{"type": "NO", "var": "I0"}, {"type": "NC", "var": "I1"}], '
    '[{"type": "NO", "var": "Q0"}, {"type": "NC", "var": "I1"}]], '
    '"coils": [{"type": "coil", "var": "Q0"}]}]}'
)
PLC_ST_DEFAULT = """(* Partida e parada com selo: I0 liga, I1 desliga, Q0 aciona *)
Q0 := (I0 OR Q0) AND NOT I1;
"""

_CONTROLLER_COMMON = (
    ParamDef(
        "instr_us",
        "Tempo por instrução",
        "µs",
        "10",
        help="Custo didático de cada comando no tempo simulado (as placas reais são "
        "mais rápidas; delay() continua exato).",
    ),
    ParamDef(
        "pwm",
        "PWM no circuito",
        "",
        "média",
        type="choice",
        choices=("média", "chaveado"),
        help="média: o pino entrega a tensão média (rápido); vale para cargas que filtram, "
        "como filtro RC, LED visto pelo olho ou motor, mas não para o gate de um MOSFET usado "
        "como chave, que ficaria na região linear. chaveado: onda quadrada na frequência da "
        "placa (passo de simulação menor, simulação mais longa).",
    ),
)

COSIM_SYMBOLS: list[Symbol] = [
    Symbol(
        "arduino_uno",
        "Arduino Uno R3",
        "Controladores",
        "X",
        _box_pins(_UNO_LEFT, _UNO_RIGHT, 5),
        (
            ParamDef("program", "Programa (estilo Arduino)", "", UNO_DEFAULT, type="code"),
            *_CONTROLLER_COMMON,
        ),
        description="Programa estilo Arduino co-simulado com o circuito: ADC de 10 bits (0 a "
        "5 V), PWM nos pinos 3, 5, 6, 9, 10 e 11, saída 5 V. O pino GND precisa estar ligado.",
        ref_prefix="U",
    ),
    Symbol(
        "arduino_nano",
        "Arduino Nano",
        "Controladores",
        "X",
        _box_pins(_NANO_LEFT, _UNO_RIGHT, 5),
        (
            ParamDef("program", "Programa (estilo Arduino)", "", UNO_DEFAULT, type="code"),
            *_CONTROLLER_COMMON,
        ),
        description="O mesmo ATmega328P do Uno em formato DIP: ADC de 10 bits (0 a 5 V) em A0 a "
        "A7 (A6 e A7 só analógicas), PWM nos pinos 3, 5, 6, 9, 10 e 11, saída 5 V. O pino GND "
        "precisa estar ligado.",
        ref_prefix="U",
    ),
    Symbol(
        "arduino_mega",
        "Arduino Mega 2560",
        "Controladores",
        "X",
        _box_pins(_MEGA_LEFT, _MEGA_RIGHT, 5),
        (
            ParamDef("program", "Programa (estilo Arduino)", "", UNO_DEFAULT, type="code"),
            *_CONTROLLER_COMMON,
        ),
        description="ATmega2560: ADC de 10 bits (0 a 5 V) em A0 a A15, PWM nos pinos 2 a 13 e "
        "44 a 46, saída 5 V, I2C em 20 (SDA) e 21 (SCL). O símbolo mostra os pinos digitais 2 a "
        "13, 20 e 21, 22 a 29 e 44 a 46.",
        ref_prefix="U",
    ),
    Symbol(
        "esp32_devkitc",
        "ESP32-DevKitC",
        "Controladores",
        "X",
        _box_pins(_ESP_LEFT, _ESP_RIGHT, 5),
        (
            ParamDef("program", "Programa (estilo Arduino)", "", ESP_DEFAULT, type="code"),
            *_CONTROLLER_COMMON,
        ),
        description="Programa estilo Arduino (núcleo ESP32) co-simulado: ADC de 12 bits nos "
        "pinos 32 a 39, DAC de 8 bits em 25 e 26, PWM (analogWrite, ledcWrite), saída 3,3 V.",
        ref_prefix="U",
    ),
    Symbol(
        "rpi_pico",
        "Raspberry Pi Pico",
        "Controladores",
        "X",
        _box_pins(_PICO_LEFT, _PICO_RIGHT, 5),
        (
            ParamDef("program", "Programa (estilo Arduino)", "", PICO_DEFAULT, type="code"),
            *_CONTROLLER_COMMON,
        ),
        description="RP2040 com programa estilo Arduino co-simulado: ADC de 12 bits (0 a 3,3 V) "
        "em GP26 a GP28 (A0 a A2), PWM (analogWrite) em qualquer GP, saída 3,3 V, LED no GP25 e "
        "I2C em GP4 (SDA) e GP5 (SCL). Limiares de entrada e resistência de saída didáticos.",
        ref_prefix="U",
    ),
    Symbol(
        "plc",
        "CLP (24 V)",
        "Controladores",
        "X",
        _box_pins(_PLC_LEFT, _PLC_RIGHT, 6),
        (
            ParamDef(
                "language", "Linguagem", "", "ladder", type="choice", choices=("ladder", "st")
            ),
            ParamDef("ladder", "Programa ladder", "", PLC_LADDER_DEFAULT, type="code"),
            ParamDef("st", "Texto estruturado (ST)", "", PLC_ST_DEFAULT, type="code"),
            ParamDef("scan_ms", "Ciclo de varredura", "ms", "10"),
            ParamDef(
                "ai0", "Entrada AI0", "", "4-20mA", type="choice", choices=("4-20mA", "0-10V")
            ),
            ParamDef("ai1", "Entrada AI1", "", "0-10V", type="choice", choices=("4-20mA", "0-10V")),
        ),
        description="CLP genérico (didático): alimentação 24 V em L+/M (desliga abaixo de "
        "19,2 V), 6 entradas digitais 24 V (liga ≥ 15 V, desliga ≤ 5 V, faixas do tipo 1 da IEC "
        "61131-2; 4,7 kΩ), 2 entradas analógicas (4-20 mA em 250 Ω ou 0-10 V em 100 kΩ), 4 saídas "
        "a relé (contatos Qna-Qnb) e 1 saída 0-10 V (AQ0). Variáveis: I0..I5, Q0..Q3, AI0, AI1 "
        "(mA ou V), AQ0 (V).",
        ref_prefix="CLP",
    ),
    Symbol(
        "lm35",
        "Sensor de temperatura LM35",
        "Sensores",
        "X",
        _box_pins(["VS", "GND"], ["OUT"], 3),
        (
            _stim("temp", "Temperatura", "°C", "25"),
            ParamDef(
                "sens",
                "Sensibilidade",
                "V/°C",
                "10m",
                help="LM35 (Texas Instruments), p. 1: +10,0 mV/°C.",
            ),
            ParamDef(
                "voff",
                "Tensão de offset (saída a 0 °C)",
                "V",
                "0",
                help="LM35: 0 V. TMP36 (Analog Devices, TMP35/TMP36/TMP37 Rev. H, Tabela 4, p. 8): "
                "0,5 V, com 750 mV a 25 °C.",
            ),
        ),
        description="Saída = offset + sensibilidade × temperatura, limitada à alimentação menos "
        "1,5 V (LM35 sem offset; TMP36 com 0,5 V).",
        ref_prefix="S",
    ),
    Symbol(
        "pt100",
        "Termorresistência Pt100",
        "Sensores",
        "X",
        (PinDef("1", -2, 0), PinDef("2", 2, 0)),
        (
            _stim("temp", "Temperatura", "°C", "25"),
            ParamDef("r0", "R a 0 °C", "Ω", "100"),
            ParamDef(
                "a", "Coeficiente A", "1/°C", "3.9083e-3", help="IEC 60751 (Callendar-Van Dusen)."
            ),
            ParamDef("b", "Coeficiente B", "1/°C²", "-5.775e-7", help="IEC 60751, para T ≥ 0 °C."),
        ),
        description="R(T) = R0 (1 + A T + B T²) da IEC 60751 (faixa de 0 a 850 °C).",
        ref_prefix="RT",
    ),
    Symbol(
        "tx420",
        "Transmissor 4-20 mA (2 fios)",
        "Sensores",
        "X",
        (PinDef("+", 0, -2), PinDef("-", 0, 2)),
        (
            _stim("x", "Grandeza medida", "", "50"),
            ParamDef("lo", "Início da faixa (4 mA)", "", "0"),
            ParamDef("hi", "Fim da faixa (20 mA)", "", "100"),
            ParamDef(
                "vmin",
                "Tensão mínima no transmissor",
                "V",
                "10",
                help="Abaixo dela a corrente cai (laço sem tensão suficiente). Valor didático.",
            ),
        ),
        description="Laço a dois fios: a corrente entra em + e sai em −, de 4 mA (início da "
        "faixa) a 20 mA (fim), alimentado pelo próprio laço (fonte de 24 V em série com a "
        "entrada do CLP).",
        ref_prefix="TT",
    ),
    Symbol(
        "tx420_rtd",
        "Transmissor 4-20 mA para RTD (3 fios)",
        "Sensores",
        "X",
        (
            PinDef("+", 3, -2),
            PinDef("-", 3, 2),
            PinDef("1", -3, -2),
            PinDef("2", -3, 0),
            PinDef("3", -3, 2),
        ),
        (
            ParamDef("r0", "R0 do sensor (a 0 °C)", "Ω", "100", help="Pt100: 100 Ω (IEC 60751)."),
            ParamDef(
                "a", "Coeficiente A", "1/°C", "3.9083e-3", help="IEC 60751 (Callendar-Van Dusen)."
            ),
            ParamDef("b", "Coeficiente B", "1/°C²", "-5.775e-7", help="IEC 60751, para T ≥ 0 °C."),
            ParamDef("lo", "Início da faixa (4 mA)", "°C", "0"),
            ParamDef("hi", "Fim da faixa (20 mA)", "°C", "100"),
            ParamDef(
                "iexc",
                "Corrente de excitação do RTD",
                "A",
                "0.5m",
                help="Valor didático (transmissores reais usam de 0,1 a 1 mA, confira o manual).",
            ),
            ParamDef(
                "vmin",
                "Tensão mínima no transmissor",
                "V",
                "10",
                help="Abaixo dela a corrente cai (laço sem tensão suficiente). Valor didático.",
            ),
        ),
        description="Transmissor de cabeçote a dois fios para termorresistência a três fios: "
        "injeta a corrente de excitação pelo terminal 1 e a recolhe pelo 2; o terminal 3 só mede "
        "(sem corrente), e R = (V13 − V32)/I desconta a resistência dos fios quando eles são "
        "iguais. A temperatura vem da inversa de R(T) = R0 (1 + A T + B T²) (IEC 60751) e a "
        "corrente do laço vai de 4 mA (início) a 20 mA (fim) entre + e −. Nó <ref>_t: "
        "temperatura medida (°C).",
        ref_prefix="TT",
    ),
    Symbol(
        "acs712",
        "Sensor de corrente ACS712",
        "Sensores",
        "X",
        _box_pins(["IP+", "IP-"], ["VCC", "OUT", "GND"], 3),
        (
            ParamDef(
                "sens",
                "Sensibilidade",
                "V/A",
                "185m",
                help="ACS712ELCTR-05B (Allegro), p. 6: 185 mV/A típico (66 a 185 mV/A, p. 1).",
            ),
            ParamDef(
                "rip", "Resistência do condutor", "Ω", "1.2m", help="Allegro ACS712, p. 1: 1,2 mΩ."
            ),
            ParamDef("bw", "Banda", "Hz", "80k", help="Allegro ACS712, p. 1: 80 kHz."),
        ),
        description="Efeito Hall: saída = VCC/2 + sensibilidade × corrente de IP+ para IP− "
        "(p. 5: saída de VCC/2 sem corrente), isolada do circuito medido.",
        ref_prefix="S",
    ),
    Symbol(
        "potentiometer",
        "Potenciômetro",
        "Sensores",
        "X",
        (PinDef("a", -2, 0), PinDef("b", 2, 0), PinDef("w", 0, 2)),
        (
            ParamDef("r", "Resistência total", "Ω", "10k"),
            _stim("pos", "Posição do cursor (0 a 1)", "", "0.5"),
        ),
        description="Cursor (w) entre a (posição 0) e b (posição 1).",
        ref_prefix="P",
    ),
    Symbol(
        "relay",
        "Relé",
        "Atuadores",
        "X",
        _box_pins(["A1", "A2"], ["COM", "NA", "NF"], 3),
        (
            ParamDef("vnom", "Tensão nominal da bobina", "V", "5"),
            ParamDef(
                "rcoil",
                "Resistência da bobina",
                "Ω",
                "70",
                help="Songle SRD-05VDC-SL-C, p. 2: 70 Ω ±10 % na bobina de 5 V.",
            ),
            ParamDef(
                "pull",
                "Operação (fração da nominal)",
                "",
                "0.75",
                help="Didático; confira a coluna Pull-In da tabela do relé.",
            ),
            ParamDef("ron", "Resistência do contato", "Ω", "0.1"),
        ),
        description="Bobina A1-A2; contato comum COM fecha com NA quando a bobina está "
        "energizada e com NF quando não está.",
        ref_prefix="K",
    ),
    Symbol(
        "dc_motor",
        "Motor CC",
        "Atuadores",
        "X",
        (PinDef("+", -2, 0), PinDef("-", 2, 0)),
        (
            ParamDef("r", "Resistência de armadura", "Ω", "2"),
            ParamDef("l", "Indutância de armadura", "H", "1m"),
            ParamDef("ke", "Constante de FCEM", "V·s/rad", "0.01"),
            ParamDef("kt", "Constante de torque", "N·m/A", "0.01"),
            ParamDef("j", "Inércia", "kg·m²", "1e-5"),
            ParamDef("b", "Atrito viscoso", "N·m·s/rad", "1e-5"),
            _stim("tl", "Torque de carga", "N·m", "0"),
        ),
        description="Motor CC de ímã permanente. Sem peça do catálogo, valores didáticos; com um "
        "motor do catálogo, R, L, kE, kM e J vêm da folha de dados e o atrito viscoso sai das "
        "perdas a vazio (b = kM·I0/ω0). Velocidade em rad/s no nó <ref>_w (ex.: v(m1_w)).",
        ref_prefix="M",
    ),
    Symbol(
        "heater",
        "Aquecedor com planta térmica",
        "Atuadores",
        "X",
        (PinDef("1", -2, 0), PinDef("2", 2, 0)),
        (
            ParamDef("r", "Resistência elétrica", "Ω", "10"),
            ParamDef("rth", "Resistência térmica para o ambiente", "°C/W", "5"),
            ParamDef("cth", "Capacidade térmica", "J/°C", "20"),
            _stim("tamb", "Temperatura ambiente", "°C", "25"),
        ),
        description="Resistor que aquece um corpo (valores didáticos): a temperatura, em °C, "
        "fica no nó <ref>_temp (ex.: v(h1_temp)) e pode alimentar um sensor.",
        ref_prefix="H",
    ),
    Symbol(
        "switch_manual",
        "Botão / chave manual",
        "Atuadores",
        "X",
        (PinDef("1", -2, 0), PinDef("2", 2, 0)),
        (
            _stim(
                "state",
                "Estado (0 aberto, 1 fechado)",
                "",
                "0 0 1 0 1.001 1",
                "Exemplo: aperta em 1 s.",
            ),
            ParamDef("ron", "Resistência fechada", "Ω", "0.01"),
        ),
        description="Contato operado pelo tempo (simula o operador apertando o botão).",
        ref_prefix="B",
    ),
    Symbol(
        "tact_switch",
        "Chave táctil 2 terminais (NA)",
        "Chaves",
        "X",
        (PinDef("1", -2, 0), PinDef("2", 2, 0)),
        (
            _stim(
                "state",
                "Apertado (0 solto, 1 apertado)",
                "",
                "0 0 0.001 0 0.00101 1",
                "Exemplo: aperta em 1 ms.",
            ),
            ParamDef("ron", "Resistência de contato", "Ω", "0.1"),
        ),
        description="Botão de contato momentâneo normalmente aberto (push-button); com a peça do "
        "catálogo, a resistência de contato vem do datasheet.",
        ref_prefix="SW",
    ),
    Symbol(
        "tact_switch4",
        "Chave táctil 4 terminais (6×6 / 12×12)",
        "Chaves",
        "X",
        (PinDef("1", -2, -1), PinDef("2", -2, 1), PinDef("3", 2, -1), PinDef("4", 2, 1)),
        (
            _stim(
                "state",
                "Apertado (0 solto, 1 apertado)",
                "",
                "0 0 0.001 0 0.00101 1",
                "Exemplo: aperta em 1 ms.",
            ),
            ParamDef("ron", "Resistência de contato", "Ω", "0.1"),
        ),
        description="Chave táctil de 4 terminais: 1-2 sempre ligados entre si, 3-4 também; "
        "apertar liga 1-2 a 3-4. Confira no datasheet quais pernas são pares.",
        ref_prefix="SW",
    ),
    Symbol(
        "push_nc",
        "Botão normalmente fechado (NF)",
        "Chaves",
        "X",
        (PinDef("1", -2, 0), PinDef("2", 2, 0)),
        (
            _stim(
                "state",
                "Apertado (0 solto, 1 apertado)",
                "",
                "0 0 0.001 0 0.00101 1",
                "Exemplo: abre em 1 ms.",
            ),
            ParamDef("ron", "Resistência de contato", "Ω", "0.1"),
        ),
        description="Botão de contato momentâneo normalmente fechado: abre enquanto apertado.",
        ref_prefix="SW",
    ),
    Symbol(
        "pump_plant",
        "Inversor + motor + bomba (planta)",
        "Atuadores",
        "X",
        _box_pins(["AI", "GND", "RUN", "COM"], ["PT+", "PT-"], 4),
        (
            ParamDef("fnom", "Frequência nominal", "Hz", "60"),
            ParamDef("accel", "Rampa de aceleração (0 a fnom)", "s", "5"),
            ParamDef("pmax", "Pressão a fnom, vazão nula", "bar", "4"),
            _stim("demand", "Consumo (0 a 1)", "", "0.5"),
            ParamDef("prange", "Fundo de escala do transmissor", "bar", "10"),
            ParamDef("vmin", "Tensão mínima do transmissor", "V", "10"),
        ),
        description="Planta didática de bombeamento: referência 0-10 V em AI-GND dá a frequência "
        "do inversor (rampa), RUN-COM ≥ 11 V habilita; pressão = pmax (f/fnom)² (1 − consumo/2); "
        "transmissor de pressão 4-20 mA entre PT+ e PT−. Nós: <ref>_f (Hz), <ref>_p (bar).",
        ref_prefix="PL",
    ),
]

# Drives, machines and the thermocouple (Fase 11 leftovers) live in their own module
from circuitos.schematic.drive_symbols import (  # noqa: E402
    DRIVE_CATALOGUE,
    DRIVE_KINDS,
    DRIVE_SYMBOLS,
    DRIVER_KINDS,
    emit_drive,
)

COSIM_SYMBOLS += DRIVE_SYMBOLS

# Sensors of the catalogue modelled later (2026-11-20)
from circuitos.schematic.sensor_symbols import (  # noqa: E402
    SENSOR_CATALOGUE,
    SENSOR_KINDS,
    SENSOR_SYMBOLS,
    emit_sensor,
    special_value,
)

COSIM_SYMBOLS += SENSOR_SYMBOLS

# Catalogue parts for the co-simulation symbols: symbol parameter <- (record symbol, unit).
# A real part placed with the symbol takes these values from its record (rule 1: the values
# come from the datasheet, with page); parameters without a value keep the symbol default.
CATALOGUE_PARAMS: dict[str, tuple[tuple[str, ...], dict[str, tuple[str, str]]]] = {
    "lm35": (
        ("sensor.temperature",),
        {"sens": ("sensitivity", "V/K"), "voff": ("V_offset", "V")},
    ),
    "pt100": (("sensor.temperature",), {"r0": ("R0", "ohm")}),
    "acs712": (
        ("sensor.current",),
        {"sens": ("sensitivity", "V/A"), "rip": ("R_primary", "ohm"), "bw": ("bandwidth", "Hz")},
    ),
    "potentiometer": (("resistor.variable",), {"r": ("R", "ohm")}),
    "relay": (
        ("relay.electromechanical",),
        {"vnom": ("V_coil", "V"), "rcoil": ("R_coil", "ohm")},
    ),
    "switch_manual": (("switch.mechanical",), {"ron": ("R_contact", "ohm")}),
    "dc_motor": (
        ("motor.dc",),
        {
            "r": ("R_a", "ohm"),
            "l": ("L_a", "H"),
            "ke": ("k_E", "V*s/rad"),
            "kt": ("k_M", "N*m/A"),
            "j": ("J", "kg*m**2"),
        },
    ),
    "tact_switch": (("switch.mechanical",), {"ron": ("R_contact", "ohm")}),
    "tact_switch4": (("switch.mechanical",), {"ron": ("R_contact", "ohm")}),
    "push_nc": (("switch.mechanical",), {"ron": ("R_contact", "ohm")}),
    "arduino_uno": (("board.mcu",), {}),
    "esp32_devkitc": (("board.mcu",), {}),
    "arduino_nano": (("board.mcu",), {}),
    "arduino_mega": (("board.mcu",), {}),
    "rpi_pico": (("board.mcu",), {}),
    "plc": (("plc",), {}),
    **DRIVE_CATALOGUE,
    **SENSOR_CATALOGUE,
}
COSIM_SYMBOLS[:] = [
    dataclasses.replace(sym, catalogue=CATALOGUE_PARAMS[sym.kind][0])
    if sym.kind in CATALOGUE_PARAMS
    else sym
    for sym in COSIM_SYMBOLS
]


def _number(param: object) -> float | None:
    return next(
        (x for x in (getattr(param, a) for a in ("typ", "max", "min")) if x is not None), None
    )


def _si(record: ComponentRecord, name: str, unit: str) -> float | None:
    param = record.parameters.get(name)
    number = _number(param) if param is not None else None
    if param is None or number is None:
        return None
    return float(Q_(number, parse_unit(param.unit)).to(parse_unit(unit)).magnitude)


def catalogue_value(kind: str, record: ComponentRecord, fallback: Value) -> Value:
    """Parameter lookup that prefers the values of the catalogue part placed with the symbol."""
    mapping = CATALOGUE_PARAMS.get(kind, ((), {}))[1]

    def value(name: str) -> str:
        special = special_value(kind, record, name) if kind in SENSOR_KINDS else None
        if special is not None:
            return special
        if kind == "stepper_motor" and name == "km":
            # torque constant from the holding torque, both phases at rated current
            t_hold, i_ph = _si(record, "T_hold", "N*m"), _si(record, "I_phase", "A")
            if t_hold and i_ph:
                return f"{torque_constant(t_hold, i_ph):.6g}"
            return fallback(name)
        if kind == "dc_motor" and name == "b":
            # no-load losses as viscous friction: kM·I0 = b·ω0
            km, i0 = _si(record, "k_M", "N*m/A"), _si(record, "I0", "A")
            w0 = _si(record, "n0", "rad/s")
            if km and i0 and w0:
                return f"{km * i0 / w0:.6g}"
            return fallback(name)
        target = mapping.get(name)
        param = record.parameters.get(target[0]) if target else None
        if target is None or param is None:
            return fallback(name)
        number = _number(param)
        if number is None:
            return fallback(name)
        si = Q_(number, parse_unit(param.unit)).to(parse_unit(target[1])).magnitude
        return f"{si:.6g}"

    return value


COSIM_KINDS = {s.kind for s in COSIM_SYMBOLS}
CONTROLLER_KINDS = {
    "arduino_uno",
    "arduino_nano",
    "arduino_mega",
    "esp32_devkitc",
    "rpi_pico",
    "plc",
    *DRIVER_KINDS,
}


# ------------------------------------------------------------------------------ stimulus


def stimulus(text: str) -> str:
    """Behavioural-source expression of a stimulus parameter."""
    t = text.strip()
    if re.fullmatch(r"[vV]\([A-Za-z0-9_+\-,]+\)", t):
        return t.lower()
    nums = t.replace(",", " ").split()
    try:
        values = [float(x) for x in nums]
    except ValueError as exc:
        raise ValueError(
            f"estímulo inválido: {text!r} (número, pares tempo/valor ou v(nó))"
        ) from exc
    if len(values) == 1:
        return f"{values[0]:.9g}"
    if len(values) % 2 or not values:
        raise ValueError(f"estímulo {text!r}: use pares tempo/valor")
    points = list(zip(values[::2], values[1::2], strict=True))
    # ngspice's pwl() keeps the last slope beyond the ends: pin both ends flat
    points = [(points[0][0] - 1e9, points[0][1]), *points, (points[-1][0] + 1e9, points[-1][1])]
    pairs = ", ".join(f"{a:.9g}, {b:.9g}" for a, b in points)
    return f"pwl(time, {pairs})"


# ------------------------------------------------------------------------- device models


def emit_device(comp: Component, n: dict[str, str], v: Value) -> list[str]:
    ref = comp.ref
    x = f"{ref}".lower()
    k = comp.kind
    if k == "lm35":
        t = stimulus(v("temp"))
        return [
            f"B{x}_out {n['OUT']} {n['GND']} V = min(max(({v('voff')}) + ({v('sens')})*({t}), 0), "
            f"max(V({n['VS']},{n['GND']}) - 1.5, 0))",
            f"R{x}_q {n['VS']} {n['GND']} 50k",  # quiescent current about 60 µA at 3 V
        ]
    if k == "pt100":
        t = stimulus(v("temp"))
        r = f"({v('r0')})*(1 + ({v('a')})*({t}) + ({v('b')})*({t})*({t}))"
        return [f"B{x} {n['1']} {n['2']} I = V({n['1']},{n['2']}) / ({r})"]
    if k == "tx420":
        xs = stimulus(v("x"))
        frac = f"min(max((({xs}) - ({v('lo')}))/(({v('hi')}) - ({v('lo')})), 0), 1)"
        return [
            f"B{x} {n['+']} {n['-']} I = (4m + 16m*{frac}) * "
            f"min(1, max(0, V({n['+']},{n['-']})/({v('vmin')})))",
        ]
    if k == "tx420_rtd":
        i = v("iexc")
        r = f"((V({n['1']},{n['3']}) - V({n['3']},{n['2']}))/({i}))"
        a, b = f"({v('a')})", f"({v('b')})"
        temp = f"((-{a} + sqrt(max({a}*{a} - 4*{b}*(1 - {r}/({v('r0')})), 0)))/(2*{b}))"
        frac = f"min(max(({x}_t - ({v('lo')}))/(({v('hi')}) - ({v('lo')})), 0), 1)"
        frac = frac.replace(f"{x}_t", f"V({x}_t)")
        return [
            f"I{x}_exc {n['2']} {n['1']} DC {i}",
            f"R{x}_s {n['3']} {n['2']} 1g",  # sense input: no current
            f"R{x}_ref {n['2']} {n['-']} 1g",  # RTD side referred to the loop (not isolated)
            f"B{x}_t {x}_t 0 V = {temp}",
            f"R{x}_t {x}_t 0 1g",
            f"B{x} {n['+']} {n['-']} I = (4m + 16m*{frac}) * "
            f"min(1, max(0, V({n['+']},{n['-']})/({v('vmin')})))",
        ]
    if k == "acs712":
        m = f"{x}_m"
        flt = f"{x}_f"
        return [
            f"V{x}_ip {n['IP+']} {m} DC 0",
            f"R{x}_ip {m} {n['IP-']} {v('rip')}",
            f"B{x}_raw {flt}_r 0 V = V({n['VCC']},{n['GND']})/2 + ({v('sens')})*I(V{x}_ip)",
            f"R{x}_flt {flt}_r {flt} 1k",
            f"C{x}_flt {flt} 0 {{1/(6.283185*1k*({v('bw')}))}}",
            f"E{x}_out {n['OUT']} {n['GND']} {flt} 0 1",
            f"R{x}_q {n['VCC']} {n['GND']} 500",  # about 10 mA supply current at 5 V
        ]
    if k == "potentiometer":
        p = f"min(max({stimulus(v('pos'))}, 0.001), 0.999)"
        r = v("r")
        return [
            f"B{x}_a {n['a']} {n['w']} I = V({n['a']},{n['w']}) / (({r})*({p}))",
            f"B{x}_b {n['w']} {n['b']} I = V({n['w']},{n['b']}) / (({r})*(1-{p}))",
        ]
    if k == "relay":
        return [
            f"R{x}_coil {n['A1']} {n['A2']} {v('rcoil')}",
            f"S{x}_na {n['COM']} {n['NA']} {n['A1']} {n['A2']} sw_{x}",
            f"S{x}_nf {n['COM']} {n['NF']} {n['A2']} {n['A1']} sw_{x}_nf",
            f".model sw_{x} sw vt={{({v('pull')})*({v('vnom')})}} vh=0.1 ron={v('ron')} roff=1e9",
            f".model sw_{x}_nf sw vt={{-({v('pull')})*({v('vnom')})}} vh=0.1 "
            f"ron={v('ron')} roff=1e9",
        ]
    if k == "dc_motor":
        w = f"{x}_w"
        return [
            f"R{x}_a {n['+']} {x}_1 {v('r')}",
            f"L{x}_a {x}_1 {x}_2 {v('l')}",
            f"V{x}_ia {x}_2 {x}_3 DC 0",
            f"B{x}_emf {x}_3 {n['-']} V = ({v('ke')})*V({w})",
            # mechanics as an electrical analogue: torque = current into node w, J = capacitance
            f"B{x}_t 0 {w} I = ({v('kt')})*I(V{x}_ia) - ({stimulus(v('tl'))})",
            f"C{x}_j {w} 0 {v('j')}",
            f"R{x}_b {w} 0 {{1/({v('b')})}}",
        ]
    if k == "heater":
        tnode = f"{x}_temp"
        return [
            f"R{x} {n['1']} {n['2']} {v('r')}",
            f"B{x}_p 0 {tnode} I = V({n['1']},{n['2']})*V({n['1']},{n['2']})/({v('r')})",
            f"C{x}_th {tnode} 0 {v('cth')}",
            f"R{x}_th {tnode} {x}_amb {v('rth')}",
            f"B{x}_amb {x}_amb 0 V = {stimulus(v('tamb'))}",
        ]
    if k == "switch_manual":
        st = stimulus(v("state"))
        return [
            f"B{x}_ctl {x}_c 0 V = {st}",
            f"S{x} {n['1']} {n['2']} {x}_c 0 sw_{x}",
            f".model sw_{x} sw vt=0.5 vh=0.1 ron={v('ron')} roff=1e9",
        ]
    if k in ("tact_switch", "push_nc"):
        st = stimulus(v("state"))
        ctl = st if k == "tact_switch" else f"1 - ({st})"
        return [
            f"B{x}_ctl {x}_c 0 V = {ctl}",
            f"S{x} {n['1']} {n['2']} {x}_c 0 sw_{x}",
            f".model sw_{x} sw vt=0.5 vh=0.1 ron={v('ron')} roff=1e9",
        ]
    if k == "tact_switch4":
        st = stimulus(v("state"))
        return [
            f"R{x}_12 {n['1']} {n['2']} 1m",
            f"R{x}_34 {n['3']} {n['4']} 1m",
            f"B{x}_ctl {x}_c 0 V = {st}",
            f"S{x} {n['1']} {n['3']} {x}_c 0 sw_{x}",
            f".model sw_{x} sw vt=0.5 vh=0.1 ron={v('ron')} roff=1e9",
        ]
    if k == "pump_plant":
        f, p = f"{x}_f", f"{x}_p"
        tau = f"(({v('accel')})/3)"
        run = f"(V({n['RUN']},{n['COM']}) > 11 ? 1 : 0)"
        fref = f"({v('fnom')})*min(max(V({n['AI']},{n['GND']})/10, 0), 1)*{run}"
        frac = f"min(max(V({p})/({v('prange')}), 0), 1)"
        return [
            f"R{x}_ai {n['AI']} {n['GND']} 10k",
            f"R{x}_run {n['RUN']} {n['COM']} 4.7k",
            f"B{x}_f 0 {f} I = ({fref} - V({f}))/{tau}",
            f"C{x}_f {f} 0 1",
            f"R{x}_f {f} 0 1g",
            f"B{x}_p {p} 0 V = ({v('pmax')})*(V({f})/({v('fnom')}))*(V({f})/({v('fnom')}))"
            f"*(1 - 0.5*min(max({stimulus(v('demand'))}, 0), 1))",
            f"B{x}_pt {n['PT+']} {n['PT-']} I = (4m + 16m*{frac})*"
            f"min(1, max(0, V({n['PT+']},{n['PT-']})/({v('vmin')})))",
        ]
    if k in DRIVE_KINDS:
        return emit_drive(comp, n, v, stimulus)
    if k in SENSOR_KINDS:
        return emit_sensor(comp, n, v, stimulus)
    raise ValueError(f"tipo {k} sem modelo")
