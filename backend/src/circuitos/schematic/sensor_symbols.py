"""Sensors of the catalogue that had no simulation model (2026-11-20).

Behavioural SPICE models in the style of :mod:`circuitos.schematic.cosim_symbols`. Every default
value is the one of a catalogue part, cited in the parameter help with the page of its
datasheet; a part placed from the catalogue brings its own values (``SENSOR_CATALOGUE``). Where
the datasheet gives only a guaranteed range (minimum and maximum), the model takes the centre of
the range and says so.

* ``ntc``: NTC thermistor, β model R(T) = R25 exp(β (1/T − 1/T25)), with self-heating through
  the dissipation constant δ and the thermal time constant τ (C_th = δ τ).
* ``ldr``: light-dependent resistor, R(E) = R10 (E/10 lx)^(−γ), limited to the dark resistance.
* ``hall_linear``: ratiometric-free linear Hall sensor, V = V_q + S B within ±B_range.
* ``hall_switch``: Hall switch with open-collector output, operate and release points.
* ``pressure``: integrated pressure sensor with analogue output, linear from V_off to V_FS.
* ``ultrasonic``: ultrasonic range finder (TRIG/ECHO): ECHO stays high for the round trip
  2 d / c after the trigger pulse, with c = 331,3 √(1 + T/273,15) m/s.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from circuitos.components.models import ComponentRecord
from circuitos.core.units import Q_, parse_unit
from circuitos.schematic.model import Component
from circuitos.schematic.symbols_base import ParamDef, PinDef, Symbol
from circuitos.schematic.values import parse_value

Value = Callable[[str], str]
Stimulus = Callable[[str], str]

T25 = 298.15  # K


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


def _box(left: list[str], right: list[str], half: int = 3) -> tuple[PinDef, ...]:
    n = max(len(left), len(right))
    top = -(n - 1)
    pins = [PinDef(p, -half, top + 2 * i) for i, p in enumerate(left)]
    pins += [PinDef(p, half, top + 2 * i) for i, p in enumerate(right)]
    return tuple(pins)


_NTC = "Vishay NTCLE100E3103JB0"
_LDR = "Token GL5528"

SENSOR_SYMBOLS: list[Symbol] = [
    Symbol(
        "ntc",
        "Termistor NTC",
        "Sensores",
        "X",
        (PinDef("1", -2, 0), PinDef("2", 2, 0)),
        (
            ParamDef("r25", "R a 25 °C", "Ω", "10k", help=f"{_NTC}, p. 2: R25 = 10 kΩ."),
            ParamDef("beta", "Constante β (25/85 °C)", "K", "3977", help=f"{_NTC}, p. 2."),
            ParamDef(
                "delta",
                "Constante de dissipação δ",
                "W/K",
                "7m",
                help=f"{_NTC}, p. 1: 7 mW/K. Use 0 para desligar o autoaquecimento.",
            ),
            ParamDef("tau", "Constante de tempo térmica", "s", "15", help=f"{_NTC}, p. 1: 15 s."),
            _stim("temp", "Temperatura ambiente", "°C", "25"),
        ),
        description="R(T) = R25 exp[β (1/T − 1/298,15 K)] na temperatura do corpo, que segue o "
        "ambiente com a constante τ e sobe P/δ com a potência dissipada (autoaquecimento). Nó "
        "<ref>_t: temperatura do corpo (°C).",
        ref_prefix="RT",
    ),
    Symbol(
        "ldr",
        "Fotorresistor (LDR)",
        "Sensores",
        "X",
        (PinDef("1", -2, 0), PinDef("2", 2, 0)),
        (
            ParamDef(
                "r10",
                "R com 10 lux",
                "Ω",
                "15k",
                help=f"{_LDR}: 10 a 20 kΩ a 10 lux; o padrão é o centro da faixa.",
            ),
            ParamDef("gamma", "Coeficiente γ", "", "0.6", help=f"{_LDR}: γ = 0,6 (10 a 100 lux)."),
            ParamDef("rdark", "Resistência no escuro", "Ω", "1meg", help=f"{_LDR}: 1 MΩ."),
            _stim("lux", "Iluminância", "lx", "100"),
        ),
        description="R(E) = R10 (E/10 lx)^(−γ), limitada à resistência no escuro. Resposta "
        "instantânea (o tempo de resposta de dezenas de ms não é simulado).",
        ref_prefix="LDR",
    ),
    Symbol(
        "hall_linear",
        "Sensor Hall linear",
        "Sensores",
        "X",
        _box(["VS", "GND"], ["OUT"]),
        (
            ParamDef(
                "sens",
                "Sensibilidade",
                "V/mT",
                "14m",
                help="Honeywell SS49E, p. 3: 14 mV/mT típico (10 a 17,5) com VS = 5 V.",
            ),
            ParamDef("vq", "Saída sem campo", "V", "2.5", help="SS49E, p. 3: 2,5 V com VS = 5 V."),
            ParamDef(
                "brange", "Faixa linear (±)", "mT", "100", help="SS49E, p. 3: ±100 mT típico."
            ),
            _stim("b", "Densidade de fluxo", "mT", "0", "Positivo: polo sul na face marcada."),
        ),
        description="Saída = V_q + S·B, saturando em ±B_range e limitada a 0..VS. Valores na "
        "alimentação de 5 V do datasheet (a saída não acompanha VS).",
        ref_prefix="S",
    ),
    Symbol(
        "hall_switch",
        "Chave Hall (coletor aberto)",
        "Sensores",
        "X",
        _box(["VS", "GND"], ["OUT"]),
        (
            ParamDef(
                "bop",
                "Ponto de operação",
                "mT",
                "21",
                help="Allegro A3144, p. 3: 7 a 35 mT; o padrão é o centro da faixa.",
            ),
            ParamDef(
                "brel",
                "Ponto de liberação",
                "mT",
                "19",
                help="A3144, p. 3: 5 a 33 mT; o padrão é o centro da faixa.",
            ),
            ParamDef(
                "vdrop",
                "Tensão de saturação da saída",
                "V",
                "0.175",
                help="A3144, p. 3: 175 mV típico com 20 mA.",
            ),
            _stim("b", "Densidade de fluxo", "mT", "0", "Positivo: polo sul na face marcada."),
        ),
        description="Saída em coletor aberto (precisa de resistor de pull-up): conduz para GND "
        "quando B ≥ B_op e abre quando B ≤ B_rel. Ligada, a saída tem a resistência que dá a "
        "tensão de saturação com 20 mA.",
        ref_prefix="S",
    ),
    Symbol(
        "pressure",
        "Sensor de pressão integrado",
        "Sensores",
        "X",
        _box(["VS", "GND"], ["OUT"]),
        (
            ParamDef(
                "pmax", "Fundo de escala", "kPa", "700", help="NXP MPX5700DP, p. 2: 0 a 700 kPa."
            ),
            ParamDef("voff", "Saída em 0 kPa", "V", "0.2", help="MPX5700DP, p. 1: 0,2 V."),
            ParamDef("vfs", "Saída no fundo de escala", "V", "4.7", help="MPX5700DP, p. 1: 4,7 V."),
            _stim("p", "Pressão diferencial", "kPa", "0"),
        ),
        description="Saída linear de V_off (0 kPa) a V_FS (fundo de escala), limitada a essa "
        "faixa. Valores na alimentação de 5 V do datasheet.",
        ref_prefix="PT",
    ),
    Symbol(
        "ultrasonic",
        "Sensor ultrassônico (HC-SR04)",
        "Sensores",
        "X",
        _box(["VCC", "GND"], ["TRIG", "ECHO"]),
        (
            _stim("dist", "Distância do obstáculo", "m", "1"),
            _stim("temp", "Temperatura do ar", "°C", "20"),
            ParamDef("dmin", "Alcance mínimo", "m", "0.02", help="SparkFun HC-SR04, p. 1: 2 cm."),
            ParamDef("dmax", "Alcance máximo", "m", "4", help="HC-SR04, p. 1: 4 m."),
        ),
        description="Um pulso em TRIG (nível alto) dispara a medida: quando TRIG desce, ECHO fica "
        "em nível alto (tensão de VCC) pelo tempo de ida e volta do som, 2d/c, com "
        "c = 331,3 √(1 + T/273,15) m/s. Fora do alcance não há eco. O atraso da rajada de 40 kHz "
        "antes do eco não é simulado. Passo de simulação limitado a 2 µs.",
        ref_prefix="US",
    ),
]

SENSOR_KINDS = {s.kind for s in SENSOR_SYMBOLS}

# catalogue parts: symbol parameter <- (record parameter, unit)
SENSOR_CATALOGUE: dict[str, tuple[tuple[str, ...], dict[str, tuple[str, str]]]] = {
    "ntc": (
        ("thermistor.ntc",),
        {
            "r25": ("R25", "ohm"),
            "beta": ("B", "K"),
            "delta": ("dissipation", "W/K"),
            "tau": ("tau", "s"),
        },
    ),
    "ldr": (("sensor.optical",), {"gamma": ("gamma", ""), "rdark": ("R_dark", "ohm")}),
    "hall_linear": (
        ("sensor.magnetic",),
        {"sens": ("sensitivity", "V/mT"), "vq": ("V_q", "V"), "brange": ("B_range", "mT")},
    ),
    "hall_switch": (("sensor.magnetic",), {"vdrop": ("Vdrop", "V")}),
    "pressure": (("sensor.pressure",), {"pmax": ("range_bar", "kPa")}),
    "ultrasonic": (("sensor.proximity",), {}),
}

# record parameters a part must have to be offered with the symbol
SENSOR_REQUIRED: dict[str, set[str]] = {
    "ntc": {"R25", "B"},
    "ldr": {"R_light", "gamma"},
    "hall_linear": {"sensitivity", "V_q"},
    "hall_switch": {"B_op", "B_rel"},
    "pressure": {"V_out", "range_bar"},
    "ultrasonic": {"sr"},
}


def _bounds(record: ComponentRecord, name: str, unit: str) -> tuple[float, float] | None:
    p = record.parameters.get(name)
    if p is None or p.min is None or p.max is None:
        return None
    k = Q_(1.0, parse_unit(p.unit)).to(parse_unit(unit)).magnitude
    return p.min * k, p.max * k


def special_value(kind: str, record: ComponentRecord, name: str) -> str | None:
    """Values that come from a datasheet range rather than a single number."""
    pick: dict[tuple[str, str], tuple[str, str, str]] = {
        ("ldr", "r10"): ("R_light", "ohm", "mid"),
        ("hall_switch", "bop"): ("B_op", "mT", "mid"),
        ("hall_switch", "brel"): ("B_rel", "mT", "mid"),
        ("pressure", "voff"): ("V_out", "V", "min"),
        ("pressure", "vfs"): ("V_out", "V", "max"),
        ("ultrasonic", "dmin"): ("sr", "m", "min"),
        ("ultrasonic", "dmax"): ("sr", "m", "max"),
    }
    key = pick.get((kind, name))
    if key is None:
        return None
    b = _bounds(record, key[0], key[1])
    if b is None:
        return None
    value = {"mid": (b[0] + b[1]) / 2, "min": b[0], "max": b[1]}[key[2]]
    return f"{value:.6g}"


def part_applies(kind: str, record: ComponentRecord) -> bool:
    need = SENSOR_REQUIRED.get(kind, set())
    if not all(record.parameters.get(n) is not None for n in need):
        return False
    if kind == "ultrasonic":
        # only TRIG/ECHO range finders; industrial ultrasonic sensors have switching outputs
        out = record.attributes.get("saida")
        return out is not None and "echo" in str(out.value).lower()
    return True


def max_step(components: list[Component]) -> float | None:
    """The ultrasonic sensor needs a 2 µs step to time its echo (0,3 mm of distance)."""
    return 2e-6 if any(c.kind == "ultrasonic" for c in components) else None


def sound_speed(temp_c: float) -> float:
    """Speed of sound in dry air, m/s (ideal gas, 331,3 m/s at 0 °C)."""
    return 331.3 * math.sqrt(1 + temp_c / 273.15)


# ------------------------------------------------------------------------- device models


def emit_sensor(comp: Component, n: dict[str, str], v: Value, stim: Stimulus) -> list[str]:
    x = comp.ref.lower()
    k = comp.kind
    if k == "ntc":
        t = f"{x}_t"
        delta = parse_value(v("delta"))
        r = f"(({v('r25')})*exp(({v('beta')})*(1/(V({t})+273.15) - 1/{T25})))"
        lines = [
            f"* {x}: termistor NTC (modelo β)",
            f"B{x} {n['1']} {n['2']} I = V({n['1']},{n['2']}) / {r}",
            f"B{x}_amb {x}_amb 0 V = {stim(v('temp'))}",
        ]
        if delta > 0:
            # thermal RC: C_th = δ τ, R_th = 1/δ; the dissipated power heats the body
            lines += [
                f"B{x}_p 0 {t} I = V({n['1']},{n['2']})*V({n['1']},{n['2']}) / {r}",
                f"R{x}_th {t} {x}_amb {{1/({v('delta')})}}",
                f"C{x}_th {t} 0 {{({v('delta')})*({v('tau')})}}",
            ]
        else:
            lines.append(f"R{x}_th {t} {x}_amb 1m")
        return lines
    if k == "ldr":
        e = f"max({stim(v('lux'))}, 1e-6)"
        r = f"min(({v('r10')})*pow({e}/10, -({v('gamma')})), {v('rdark')})"
        return [f"B{x} {n['1']} {n['2']} I = V({n['1']},{n['2']}) / ({r})"]
    if k == "hall_linear":
        b = f"min(max({stim(v('b'))}, -({v('brange')})), {v('brange')})"
        return [
            f"B{x}_out {n['OUT']} {n['GND']} V = min(max(({v('vq')}) + ({v('sens')})*({b}), 0), "
            f"max(V({n['VS']},{n['GND']}), 0))",
            f"R{x}_q {n['VS']} {n['GND']} 833",  # about 6 mA at 5 V (SS49E, p. 3)
        ]
    if k == "hall_switch":
        bop, brel = parse_value(v("bop")), parse_value(v("brel"))
        vt, vh = (bop + brel) / 2, max((bop - brel) / 2, 1e-6)
        ron = max(parse_value(v("vdrop")), 1e-6) / 20e-3
        return [
            f"B{x}_b {x}_b 0 V = {stim(v('b'))}",
            f"S{x} {n['OUT']} {n['GND']} {x}_b 0 sw_{x}",
            f".model sw_{x} sw vt={vt:.6g} vh={vh:.6g} ron={ron:.6g} roff=1e9",
            f"R{x}_q {n['VS']} {n['GND']} 1.1k",  # about 4,4 mA at 5 V (A3144, p. 3)
        ]
    if k == "pressure":
        p = f"min(max({stim(v('p'))}, 0), {v('pmax')})"
        return [
            f"B{x}_out {n['OUT']} {n['GND']} V = ({v('voff')}) + (({v('vfs')}) - ({v('voff')}))"
            f"*({p})/({v('pmax')})",
            f"R{x}_q {n['VS']} {n['GND']} 714",  # about 7 mA at 5 V (MPX5700, p. 2)
        ]
    if k == "ultrasonic":
        trig = f"V({n['TRIG']},{n['GND']})"
        h = f"{x}_h"
        d = stim(v("dist"))
        c = f"(331.3*sqrt(1 + ({stim(v('temp'))})/273.15))"
        dt = f"(time - V({h}))"
        valid = f"(({d}) >= ({v('dmin')}) && ({d}) <= ({v('dmax')}))"
        return [
            f"* {x}: ultrassônico (tempo de voo)",
            # V(h) follows the time while TRIG is high and holds it afterwards: the end of the
            # trigger pulse
            f"B{x}_h 0 {h} I = ({trig} > 2 ? 1e8*(time - V({h})) : 0)",
            f"C{x}_h {h} 0 1",
            f"R{x}_h {h} 0 1e15",
            f"B{x}_echo {n['ECHO']} {n['GND']} V = ({trig} < 2 && V({h}) > 0 && {valid} && "
            f"{dt} > 0 && {dt} < 2*({d})/{c}) ? max(V({n['VCC']},{n['GND']}), 0) : 0",
            f"R{x}_q {n['VCC']} {n['GND']} 333",  # about 15 mA at 5 V (HC-SR04, p. 1)
            f".ic v({h})=-1",
        ]
    raise ValueError(f"tipo {k} sem modelo")
