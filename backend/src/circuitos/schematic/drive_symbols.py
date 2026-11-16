"""Drives, machines and the thermocouple for the co-simulation (Fase 11 leftovers, D12).

Behavioural SPICE models, in the same style as :mod:`circuitos.schematic.cosim_symbols`:

* ``induction_motor``: squirrel-cage motor, dynamic model in the stationary αβ frame; steady
  state equals the equivalent circuit of :mod:`circuitos.machines.induction`.
* ``vfd``: frequency inverter with V/f control, acceleration and deceleration ramps, voltage
  boost; output as the fundamental (average model) or SPWM with third-harmonic injection.
* ``soft_starter``: voltage ramp or current limit, kick start and soft stop, as the
  fundamental of the thyristor output (average model), bypass at the end of the ramp.
* ``contactor``: three-pole contactor with AC or DC coil.
* ``stepper_motor``: two-phase hybrid stepper (:mod:`circuitos.machines.stepper`).
* ``stepper_driver``: STEP/DIR driver with microstepping and current regulation; the step
  counter runs in the co-simulation (:mod:`circuitos.cosim.engine`), the current loop in SPICE.
* ``thermocouple``: NIST ITS-90 reference functions with the cold junction temperature.

Default values without a datasheet are didactic and the parameter help says so.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from circuitos.machines import thermocouple as tc
from circuitos.schematic.model import Component
from circuitos.schematic.symbols_base import ParamDef, PinDef, Symbol

Value = Callable[[str], str]
Stimulus = Callable[[str], str]

_SQ3 = math.sqrt(3)


def _box(left: list[str], right: list[str], half: int = 4) -> tuple[PinDef, ...]:
    n = max(len(left), len(right))
    top = -(n - 1)
    pins = [PinDef(p, -half, top + 2 * i) for i, p in enumerate(left)]
    pins += [PinDef(p, half, top + 2 * i) for i, p in enumerate(right)]
    return tuple(pins)


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


_DIDACTIC = "Valor didático; troque pelo do seu motor."

DRIVE_SYMBOLS: list[Symbol] = [
    Symbol(
        "induction_motor",
        "Motor de indução trifásico",
        "Atuadores",
        "X",
        (PinDef("A", -3, -2), PinDef("B", -3, 0), PinDef("C", -3, 2)),
        (
            ParamDef("poles", "Número de polos", "", "4"),
            ParamDef("fnom", "Frequência das reatâncias", "Hz", "60"),
            ParamDef("rs", "R1 (estator, por fase em Y)", "Ω", "1.5", help=_DIDACTIC),
            ParamDef("rr", "R2 (rotor referido ao estator)", "Ω", "1.2", help=_DIDACTIC),
            ParamDef("xls", "X1 (dispersão do estator)", "Ω", "2.5", help=_DIDACTIC),
            ParamDef("xlr", "X2 (dispersão do rotor)", "Ω", "2.5", help=_DIDACTIC),
            ParamDef("xm", "Xm (magnetização)", "Ω", "60", help=_DIDACTIC),
            ParamDef("j", "Inércia (rotor + carga)", "kg·m²", "0.02", help=_DIDACTIC),
            ParamDef("b", "Atrito viscoso", "N·m·s/rad", "0.005", help=_DIDACTIC),
            _stim("tl", "Torque de carga", "N·m", "0"),
            ParamDef(
                "load",
                "Tipo de carga",
                "",
                "constante",
                type="choice",
                choices=("constante", "quadrática"),
                help="quadrática (ventilador, bomba centrífuga): o torque de carga vale o "
                "informado na velocidade síncrona de fnom e cai com o quadrado da velocidade.",
            ),
        ),
        description="Gaiola de esquilo, modelo dinâmico em αβ (Krause, cap. 4); em regime, "
        "igual ao circuito equivalente por fase. Os parâmetros padrão são de um motor didático "
        "de 4 polos, 380 V em Y, cerca de 3,7 kW (20 N·m a 1732 rpm). Nós: <ref>_rpm, "
        "<ref>_te (torque, N·m), <ref>_i (corrente de linha eficaz, A), <ref>_w (rad/s).",
        ref_prefix="M",
    ),
    Symbol(
        "vfd",
        "Inversor de frequência (V/f)",
        "Atuadores",
        "X",
        _box(["AI", "GND", "RUN", "COM"], ["U", "V", "W"], 4),
        (
            ParamDef("vnom", "Tensão de linha nominal (eficaz)", "V", "380"),
            ParamDef("fnom", "Frequência nominal", "Hz", "60"),
            ParamDef(
                "accel",
                "Tempo de aceleração (0 a fnom)",
                "s",
                "5",
                help="Como o P0100 do CFW500 (WEG, manual, p. 38).",
            ),
            ParamDef("decel", "Tempo de desaceleração (fnom a 0)", "s", "5", help="P0101."),
            ParamDef("fmin", "Frequência mínima com RUN", "Hz", "0", help="P0133."),
            ParamDef(
                "boost",
                "Boost de tensão a 0 Hz (fração de vnom)",
                "",
                "0.03",
                help="Compensa a queda em R1 em baixa frequência (P0136 do CFW500). Didático.",
            ),
            ParamDef(
                "mode",
                "Saída",
                "",
                "senoidal",
                type="choice",
                choices=("senoidal", "SPWM"),
                help="senoidal: só a fundamental (modelo médio, rápido). SPWM: chaveamento com "
                "injeção de 3ª harmônica (equivalente ao SVPWM) a partir do barramento CC; passo "
                "de simulação de 1/40 da portadora.",
            ),
            ParamDef(
                "fsw",
                "Frequência de chaveamento",
                "Hz",
                "5k",
                help="CFW500: portadora nominal de 5 kHz (manual, Tabela B.4, p. 153).",
            ),
            ParamDef(
                "vdc", "Barramento CC (SPWM)", "V", "537", help="√2 × 380 V: retificador a diodos."
            ),
        ),
        description="Referência 0-10 V em AI-GND = 0 a fnom; RUN-COM ≥ 11 V liga (rampa de "
        "aceleração), abaixo desliga (rampa de desaceleração até 0). Lei V/f linear com boost, "
        "tensão limitada a vnom. Saídas U, V e W em relação a GND. Nós: <ref>_f (Hz), <ref>_v "
        "(tensão de linha comandada, V eficaz).",
        ref_prefix="INV",
    ),
    Symbol(
        "soft_starter",
        "Soft-starter",
        "Atuadores",
        "X",
        _box(["L1", "L2", "L3", "RUN", "COM"], ["T1", "T2", "T3"], 4),
        (
            ParamDef(
                "control",
                "Tipo de controle",
                "",
                "rampa de tensão",
                type="choice",
                choices=("rampa de tensão", "limitação de corrente"),
                help="Os dois controles do SSW-07 (WEG, manual, p. 31 e p. 57: Voltage ramp; "
                "Current limitation).",
            ),
            ParamDef("vinit", "Tensão inicial (fração da linha)", "", "0.35", help="Didático."),
            ParamDef(
                "tacc",
                "Tempo da rampa de aceleração",
                "s",
                "5",
                help="Na limitação de corrente, é o tempo máximo de partida (SSW-07, p. 33).",
            ),
            ParamDef("ilim", "Limite de corrente (eficaz)", "A", "20"),
            ParamDef(
                "tdec",
                "Rampa de desaceleração (0 = parada livre)",
                "s",
                "0",
                help="Para bombas, reduz o golpe de aríete (SSW-07, p. 33).",
            ),
            ParamDef(
                "kick",
                "Kick start (duração, 0 = desligado)",
                "s",
                "0",
                help="Pulso de 80 % da tensão de linha no início (SSW-07, p. 31).",
            ),
        ),
        description="Modelo da fundamental: a tensão nos terminais T é a fração k da linha "
        "(o disparo dos tiristores reduz a fundamental; harmônicas não são simuladas). RUN-COM "
        "≥ 11 V parte; ao fim da rampa, k = 1 (bypass). Nós: <ref>_k (fração da tensão), "
        "<ref>_i (corrente de linha eficaz, A).",
        ref_prefix="SS",
    ),
    Symbol(
        "contactor",
        "Contator tripolar",
        "Atuadores",
        "X",
        _box(["A1", "A2"], ["L1", "T1", "L2", "T2", "L3", "T3"], 3),
        (
            ParamDef("vnom", "Tensão da bobina (eficaz se CA)", "V", "24"),
            ParamDef("coil", "Bobina", "", "CC", type="choice", choices=("CC", "CA")),
            ParamDef("pcoil", "Potência da bobina", "W", "5", help="Didático."),
            ParamDef("ron", "Resistência de cada contato", "Ω", "0.005"),
        ),
        description="Fecha L1-T1, L2-T2 e L3-T3 com a bobina acima de 75 % da nominal (abre "
        "abaixo de 40 %). Bobina CA: valor médio retificado com 10 ms de constante.",
        ref_prefix="K",
    ),
    Symbol(
        "stepper_motor",
        "Motor de passo híbrido (bipolar)",
        "Atuadores",
        "X",
        _box(["A+", "A-", "B+", "B-"], [], 3),
        (
            ParamDef("step", "Ângulo de passo", "°", "1.8"),
            ParamDef("r", "Resistência por fase", "Ω", "1.4"),
            ParamDef("l", "Indutância por fase", "H", "3m"),
            ParamDef(
                "km",
                "Constante de torque (= FCEM)",
                "N·m/A",
                "0.2086",
                help="T_hold/(√2 I) com as duas fases na corrente nominal; padrão do "
                "17HS19-2004S1 (0,59 N·m, 2,0 A). Com a peça do catálogo, vem dela.",
            ),
            ParamDef("jr", "Inércia do rotor", "kg·m²", "8.2e-6", help="17HS19-2004S1: 82 g·cm²."),
            ParamDef("jl", "Inércia da carga", "kg·m²", "0"),
            ParamDef("b", "Atrito viscoso", "N·m·s/rad", "2e-4", help="Didático."),
            ParamDef("tdet", "Torque de retenção sem corrente (detent)", "N·m", "0"),
            _stim(
                "tl",
                "Torque de carga (constante)",
                "N·m",
                "0",
                "Torque com sentido fixo, como um peso pendurado: positivo se opõe ao giro no "
                "sentido positivo.",
            ),
            ParamDef(
                "tf",
                "Atrito seco (Coulomb)",
                "N·m",
                "0",
                help="Sempre contra o movimento; suavizado em ±1 rad/s.",
            ),
        ),
        description="Duas fases, A e B (Kenjo, cap. 4): torque = K (−i_a sen Nθ + i_b cos Nθ). "
        "Padrão: StepperOnline 17HS19-2004S1 (1,4 Ω, 3 mH, 0,59 N·m a 2 A). Nós: <ref>_deg "
        "(posição em graus), <ref>_w (rad/s), <ref>_te (torque).",
        ref_prefix="M",
    ),
    Symbol(
        "stepper_driver",
        "Driver de motor de passo (STEP/DIR)",
        "Controladores",
        "X",
        _box(["STEP", "DIR", "EN", "GND", "VM"], ["A+", "A-", "B+", "B-"], 4),
        (
            ParamDef("ifull", "Corrente por fase (pico do vetor)", "A", "1.5"),
            ParamDef(
                "micro",
                "Micropasso",
                "",
                "1",
                type="choice",
                choices=("1", "2", "4", "8", "16"),
                help="1 = passo inteiro com as duas fases a 70,7 % (vetor a 45°).",
            ),
            ParamDef("vth", "Limiar das entradas lógicas", "V", "1.65", help="Didático."),
        ),
        description="Driver genérico (didático, no estilo dos módulos de protoboard): conta as "
        "bordas de subida em STEP (DIR alto = sentido positivo), EN baixo ou solto habilita. "
        "Ponte H por fase com regulação de corrente limitada a VM; corrente senoidal por "
        "micropasso. Variáveis: <ref>.steps, <ref>.ia_ref, <ref>.ib_ref.",
        ref_prefix="DRV",
    ),
    Symbol(
        "thermocouple",
        "Termopar",
        "Sensores",
        "X",
        (PinDef("+", -2, -1), PinDef("-", -2, 1)),
        (
            ParamDef("type", "Tipo", "", "K", type="choice", choices=("J", "K", "T", "E", "N")),
            _stim("temp", "Temperatura da junta quente", "°C", "25"),
            _stim(
                "tref",
                "Temperatura da junta fria (terminais)",
                "°C",
                "25",
                "É a temperatura onde o termopar encontra o cobre (borneira, entrada do "
                "instrumento).",
            ),
            ParamDef("r", "Resistência do laço", "Ω", "10", help="Didático (fio e conexões)."),
        ),
        description="Tensão = E(T) − E(T_ref), funções de referência NIST ITS-90 (iguais às da "
        "IEC 60584-1); conferidas nas tabelas Omega Z-204 (tipo K) e Z-206 (tipo E). Nós: "
        "<ref>_t (temperatura da junta quente).",
        ref_prefix="TC",
    ),
]

DRIVE_KINDS = {s.kind for s in DRIVE_SYMBOLS}
DRIVER_KINDS = {"stepper_driver"}  # driven by the co-simulation (step counter)

# catalogue parts: symbol parameter <- (record parameter, unit); see cosim_symbols
DRIVE_CATALOGUE: dict[str, tuple[tuple[str, ...], dict[str, tuple[str, str]]]] = {
    "stepper_motor": (
        ("motor.stepper",),
        {
            "step": ("step_angle", "deg"),
            "r": ("R_phase", "ohm"),
            "l": ("L_phase", "H"),
            "jr": ("J_rotor", "kg*m^2"),
        },
    ),
}


def max_step(components: list[Component]) -> float | None:
    """Largest time step the drives need: 1/40 of the SPWM carrier; 1/80 of a 60 Hz cycle
    (about 200 µs) with AC machines and drives, whose sinusoids the default step would skip.
    """
    from circuitos.schematic.library import param

    cap: float | None = None
    for c in components:
        if c.kind not in DRIVE_KINDS or c.kind in ("thermocouple", "stepper_motor", "contactor"):
            continue
        step = 1 / (80 * 60)
        if c.kind == "vfd" and param(c, "mode") == "SPWM":
            fsw = _f(param(c, "fsw"))
            step = min(step, 1 / (40 * fsw))
        cap = step if cap is None else min(cap, step)
    return cap


_STATES = {  # integrator nodes (C = 1 analogues), held at zero for the operating point
    "induction_motor": ("psa", "psb", "pra", "prb", "w"),
    "vfd": ("f", "th"),
    "soft_starter": ("k", "t0"),
    "contactor": ("ctl",),
    "stepper_motor": ("w", "th"),
}


def emit_drive(comp: Component, n: dict[str, str], v: Value, stim: Stimulus) -> list[str]:
    x = comp.ref.lower()
    k = comp.kind
    if k == "induction_motor":
        lines = _induction(x, n, v, stim)
    elif k == "vfd":
        lines = _vfd(x, n, v)
    elif k == "soft_starter":
        lines = _soft_starter(x, n, v)
    elif k == "contactor":
        lines = _contactor(x, n, v)
    elif k == "stepper_motor":
        lines = _stepper(x, n, v, stim)
    elif k == "thermocouple":
        return _thermocouple(x, n, v, stim)
    else:
        raise ValueError(f"tipo {k} sem modelo")
    # without this the operating point is the DC steady state of each integrator (a motor
    # "running" at t = 0 with DC fluxes); the machines start at rest, unmagnetised
    states = " ".join(f"v({x}_{s})=0" for s in _STATES[k])
    return [*lines, f".ic {states}"]


def _f(text: str) -> float:
    from circuitos.schematic.values import try_parse

    value = try_parse(text)
    if value is None:
        raise ValueError(f"valor inválido: {text!r}")
    return value


# ------------------------------------------------------------------------ induction motor


def _induction(x: str, n: dict[str, str], v: Value, stim: Stimulus) -> list[str]:
    poles = round(_f(v("poles")))
    if poles < 2 or poles % 2:
        raise ValueError("número de polos deve ser par (2, 4, 6...)")
    p = poles // 2
    w0 = 2 * math.pi * _f(v("fnom"))
    rs, rr = _f(v("rs")), _f(v("rr"))
    lm = _f(v("xm")) / w0
    ls, lr = _f(v("xls")) / w0 + lm, _f(v("xlr")) / w0 + lm
    d = ls * lr - lm * lm
    a, b, c = n["A"], n["B"], n["C"]
    psa, psb, pra, prb, w = (f"{x}_{s}" for s in ("psa", "psb", "pra", "prb", "w"))
    isa = f"(({lr:.9g}*V({psa}) - {lm:.9g}*V({pra}))/{d:.9g})"
    isb = f"(({lr:.9g}*V({psb}) - {lm:.9g}*V({prb}))/{d:.9g})"
    ira = f"(({ls:.9g}*V({pra}) - {lm:.9g}*V({psa}))/{d:.9g})"
    irb = f"(({ls:.9g}*V({prb}) - {lm:.9g}*V({psb}))/{d:.9g})"
    wr = f"({p}*V({w}))"
    ws_nom = w0 / p
    tl = stim(v("tl"))
    if v("load") == "quadrática":
        tl = f"({tl})*V({w})*abs(V({w}))/{ws_nom * ws_nom:.9g}"
    # Krause, 2nd ed., ch. 4: stator and rotor flux linkages in the stationary frame
    return [
        f"* {x}: motor de indução (αβ)",
        f"B{x}_psa 0 {psa} I = (2*V({a},{b}) + V({b},{c}))/3 - {rs:.9g}*{isa}",
        f"B{x}_psb 0 {psb} I = V({b},{c})/{_SQ3:.12g} - {rs:.9g}*{isb}",
        f"B{x}_pra 0 {pra} I = -{rr:.9g}*{ira} - {wr}*V({prb})",
        f"B{x}_prb 0 {prb} I = -{rr:.9g}*{irb} + {wr}*V({pra})",
        *(f"C{x}_{s} {x}_{s} 0 1" for s in ("psa", "psb", "pra", "prb")),
        *(f"R{x}_{s} {x}_{s} 0 1e12" for s in ("psa", "psb", "pra", "prb")),
        # terminal currents (inverse Clarke); they add up to zero
        f"B{x}_ia {a} 0 I = {isa}",
        f"B{x}_ib {b} 0 I = -0.5*{isa} + {_SQ3 / 2:.12g}*{isb}",
        f"B{x}_ic {c} 0 I = -0.5*{isa} - {_SQ3 / 2:.12g}*{isb}",
        *(f"R{x}_g{i} {node} 0 10meg" for i, node in enumerate((a, b, c))),
        # torque: Te = 3/2 p (ψsα isβ − ψsβ isα); mechanics as an RC analogue (J = C)
        f"B{x}_te {x}_te 0 V = {1.5 * p:.9g}*(V({psa})*{isb} - V({psb})*{isa})",
        f"B{x}_mech 0 {w} I = V({x}_te) - ({tl}) - {_f(v('b')):.9g}*V({w})",
        f"C{x}_j {w} 0 {_f(v('j')):.9g}",
        f"R{x}_w {w} 0 1e12",
        f"B{x}_rpm {x}_rpm 0 V = V({w})*{60 / (2 * math.pi):.12g}",
        f"B{x}_i {x}_i 0 V = sqrt(({isa})^2 + ({isb})^2)/{math.sqrt(2):.12g}",
    ]


# ------------------------------------------------------------------------------- inverter


def _vfd(x: str, n: dict[str, str], v: Value) -> list[str]:
    fnom, vnom = _f(v("fnom")), _f(v("vnom"))
    acc, dec = max(_f(v("accel")), 1e-3), max(_f(v("decel")), 1e-3)
    fmin, boost = _f(v("fmin")), _f(v("boost"))
    f, th, vc = f"{x}_f", f"{x}_th", f"{x}_v"
    run = f"(V({n['RUN']},{n['COM']}) > 11 ? 1 : 0)"
    fref = f"({run}*max({fnom:.9g}*min(max(V({n['AI']},{n['GND']})/10, 0), 1), {fmin:.9g}))"
    rate = f"min(max(({fref} - V({f}))/0.01, {-fnom / dec:.9g}), {fnom / acc:.9g})"
    gnd = n["GND"]
    lines = [
        f"* {x}: inversor V/f",
        f"R{x}_ai {n['AI']} {gnd} 10k",
        f"R{x}_run {n['RUN']} {n['COM']} 4.7k",
        f"B{x}_f 0 {f} I = {rate}",
        f"C{x}_f {f} 0 1",
        f"R{x}_f {f} 0 1e12",
        f"B{x}_th 0 {th} I = {2 * math.pi:.12g}*V({f})",
        f"C{x}_th {th} 0 1",
        f"R{x}_th {th} 0 1e12",
        # V/f with boost, fading in over the first hertz so 0 Hz is not a DC voltage
        f"B{x}_vcmd {vc} 0 V = {vnom:.9g}*min(1, {boost:.9g} + {1 - boost:.9g}*V({f})/{fnom:.9g})"
        f"*min(1, max(V({f}), 0))",
    ]
    vpk = f"(V({vc})*{math.sqrt(2) / _SQ3:.12g})"  # phase peak
    shifts = (0.0, -2 * math.pi / 3, 2 * math.pi / 3)
    if v("mode") == "SPWM":
        vdc, fsw = _f(v("vdc")), _f(v("fsw"))
        # triangle carrier in [-1, 1]; references with 1/6 third harmonic (linear up to
        # Vll = Vdc/√2, the same reach as SVPWM; Holmes and Lipo, ch. 6)
        tri = f"({2 / math.pi:.12g}*asin(sin({2 * math.pi * fsw:.9g}*time)))"
        for pin, sh in zip(("U", "V", "W"), shifts, strict=True):
            ref = f"({vpk}*(sin(V({th}) + {sh:.12g}) + sin(3*V({th}))/6)/{vdc / 2:.9g})"
            lines.append(
                f"B{x}_{pin.lower()} {x}_{pin.lower()}s {gnd} V = "
                f"({ref} > {tri} ? {vdc / 2:.9g} : {-vdc / 2:.9g})"
            )
    else:
        for pin, sh in zip(("U", "V", "W"), shifts, strict=True):
            lines.append(
                f"B{x}_{pin.lower()} {x}_{pin.lower()}s {gnd} V = {vpk}*sin(V({th}) + {sh:.12g})"
            )
    for pin in ("U", "V", "W"):
        lines.append(f"R{x}_{pin.lower()}o {x}_{pin.lower()}s {n[pin]} 0.01")
    return lines


# --------------------------------------------------------------------------- soft-starter


def _soft_starter(x: str, n: dict[str, str], v: Value) -> list[str]:
    vinit = min(max(_f(v("vinit")), 0.0), 1.0)
    tacc = max(_f(v("tacc")), 1e-3)
    tdec = _f(v("tdec"))
    kick = _f(v("kick"))
    ilim = _f(v("ilim"))
    k, i, on, t0 = f"{x}_k", f"{x}_i", f"{x}_on", f"{x}_t0"
    ls, ts = (n["L1"], n["L2"], n["L3"]), (n["T1"], n["T2"], n["T3"])
    sense = [f"V{x}_s{j}" for j in range(3)]
    run = f"(V({n['RUN']},{n['COM']}) > 11 ? 1 : 0)"
    # line current: magnitude of the αβ vector (rms for a balanced, sinusoidal set)
    ia, ib = f"I({sense[0]})", f"(I({sense[1]}) - I({sense[2]}))/{_SQ3:.12g}"
    if v("control") == "limitação de corrente":
        # SSW-07, p. 32: the current is held at the limit until the motor reaches speed; the
        # initial voltage does not apply. k rises at most at 1/(tacc/4) while the current is
        # below the limit and falls above it (a fast integral regulator).
        climb = f"min({4 / tacc:.9g}, 20*({ilim:.9g} - V({i}))/{ilim:.9g})"
    else:
        # voltage ramp: jump to the initial voltage, then rise to 1 in tacc
        up = (1 - vinit) / tacc
        climb = f"(V({k}) < {vinit:.9g} ? 1000*({vinit:.9g} - V({k})) + {up:.9g} : {up:.9g})"
    down = f"{-1 / tdec:.9g}" if tdec > 0 else "-1000"
    # k ramps to 1 (bypass) with RUN, ramps or drops to 0 without it
    dk = f"(V({on}) > 0.5 ? (V({k}) >= 1 ? min({climb}, 0) : {climb}) : (V({k}) <= 0 ? 0 : {down}))"
    kv = f"min(max(V({k}), 0), 1)"
    if kick > 0:
        kv = f"((V({on}) > 0.5 && V({t0}) < {kick:.9g}) ? max({kv}, 0.8) : {kv})"
    vn = f"((V({ls[0]}) + V({ls[1]}) + V({ls[2]}))/3)"
    lines = [
        f"* {x}: soft-starter (fundamental)",
        f"R{x}_run {n['RUN']} {n['COM']} 4.7k",
        f"B{x}_on {on} 0 V = {run}",
        # time since the start command (for the kick start): resets when RUN drops
        f"B{x}_t0 0 {t0} I = V({on}) > 0.5 ? 1 : -1000*V({t0})",
        f"C{x}_t0 {t0} 0 1",
        f"R{x}_t0 {t0} 0 1e12",
        f"B{x}_k 0 {k} I = {dk}",
        f"C{x}_k {k} 0 1",
        f"R{x}_k {k} 0 1e12",
        f"B{x}_kv {x}_kv 0 V = {kv}",
        f"B{x}_i {i} 0 V = sqrt({ia}^2 + ({ib})^2)/{math.sqrt(2):.12g}",
    ]
    for j in range(3):
        lines += [
            f"B{x}_o{j} {x}_o{j} 0 V = {vn} + V({x}_kv)*(V({ls[j]}) - {vn})",
            f"{sense[j]} {x}_o{j} {ts[j]} DC 0",
            f"B{x}_in{j} {ls[j]} 0 I = V({x}_kv)*I({sense[j]})",
        ]
    return lines


# ------------------------------------------------------------------------------ contactor


def _contactor(x: str, n: dict[str, str], v: Value) -> list[str]:
    vnom = _f(v("vnom"))
    rcoil = vnom * vnom / max(_f(v("pcoil")), 1e-3)
    ac = v("coil") == "CA"
    level = f"abs(V({n['A1']},{n['A2']}))" + (f"/{0.9:.9g}" if ac else "")  # mean |v| = 0.9 Vrms
    ctl = f"{x}_ctl"
    lines = [
        f"R{x}_coil {n['A1']} {n['A2']} {rcoil:.9g}",
        f"B{x}_lv 0 {ctl} I = ({level}/{vnom:.9g} - V({ctl}))/{0.01 if ac else 0.001:g}",
        f"C{x}_ctl {ctl} 0 1",
        f"R{x}_ctl {ctl} 0 1e12",
        # closes at 75 %, opens at 40 % of the rated coil voltage
        f".model sw_{x} sw vt=0.575 vh=0.175 ron={v('ron')} roff=1e9",
    ]
    for j in (1, 2, 3):
        lines.append(f"S{x}_{j} {n[f'L{j}']} {n[f'T{j}']} {ctl} 0 sw_{x}")
    return lines


# --------------------------------------------------------------------------------- stepper


def _stepper(x: str, n: dict[str, str], v: Value, stim: Stimulus) -> list[str]:
    nr = 90.0 / _f(v("step"))
    km = _f(v("km"))
    w, th = f"{x}_w", f"{x}_th"
    j = _f(v("jr")) + _f(v("jl"))
    tdet = _f(v("tdet"))
    ang = f"({nr:.9g}*V({th}))"
    lines = [f"* {x}: motor de passo híbrido"]
    r, ind = _f(v("r")), _f(v("l"))
    for ph, (p, m) in (("a", ("A+", "A-")), ("b", ("B+", "B-"))):
        emf = f"-{km:.9g}*V({w})*sin({ang})" if ph == "a" else f"{km:.9g}*V({w})*cos({ang})"
        i = f"{x}_i{ph}"
        # winding current as a state (L di/dt = v − R i − e), drawn from the terminals by a
        # current source: an L element between voltage sources stalls the time step
        lines += [
            f"B{x}_l{ph} 0 {i} I = (V({n[p]},{n[m]}) - {r:.9g}*V({i}) - ({emf}))/{ind:.9g}",
            f"C{x}_l{ph} {i} 0 1",
            f"R{x}_l{ph} {i} 0 1e12",
            f"B{x}_{ph} {n[p]} {n[m]} I = V({i})",
            f"R{x}_p{ph} {n[p]} {n[m]} 10k",
        ]
    te = f"{km:.9g}*(-V({x}_ia)*sin({ang}) + V({x}_ib)*cos({ang}))"
    if tdet:
        te += f" - {tdet:.9g}*sin(4*{ang})"
    tl = stim(v("tl"))
    # Coulomb friction, smoothed over ±1 rad/s (a hard sign() stalls the solver at rest)
    tf = f"({_f(v('tf')):.9g}*tanh(V({w})))"
    tl_eff = f"(({tl}) + {tf})"
    lines += [
        f"B{x}_te {x}_te 0 V = {te}",
        f"B{x}_mech 0 {w} I = V({x}_te) - {tl_eff} - {_f(v('b')):.9g}*V({w})",
        f"C{x}_j {w} 0 {j:.9g}",
        f"R{x}_w {w} 0 1e12",
        f"B{x}_th 0 {th} I = V({w})",
        f"C{x}_th {th} 0 1",
        f"R{x}_th {th} 0 1e12",
        f"B{x}_deg {x}_deg 0 V = V({th})*{180 / math.pi:.12g}",
    ]
    return lines


def stepper_driver_lines(x: str, n: dict[str, str], params: dict[str, str]) -> list[str]:
    """SPICE part of the driver: H-bridges with current loops; references are EXTERNAL."""
    gnd, vm = n["GND"], n["VM"]
    vmx = f"max(V({vm},{gnd}), 0.1)"
    lines = [
        f"* {x}: driver de motor de passo (co-simulação)",
        f"R{x}_step {n['STEP']} {gnd} 100k",
        f"R{x}_dir {n['DIR']} {gnd} 100k",
        f"R{x}_en {n['EN']} {gnd} 100k",  # pull-down: EN left open = enabled
        f"V{x}_tick {x}_tick 0 DC 0 EXTERNAL",
        f"R{x}_tick {x}_tick 0 1meg",
    ]
    for ph, (p, m) in (("a", ("A+", "A-")), ("b", ("B+", "B-"))):
        lines += [
            f"V{x}_ref{ph} {x}_ref{ph} 0 DC 0 EXTERNAL",
            f"R{x}_ref{ph} {x}_ref{ph} 0 1meg",
            f"V{x}_s{ph} {x}_{ph}o {n[p]} DC 0",
            f"R{x}_g{ph} {n[m]} {gnd} 1meg",  # the bridge output is referred to GND
            # PI current loop (20 V/A, zero at 1000 rad/s), output limited by the motor supply
            # through tanh (a hard min/max clamp makes the operating point fail its gmin
            # stepping, and a pure high gain loop stalls the time step)
            f"B{x}_{ph}i 0 {x}_{ph}i I = (abs(V({x}_{ph}i)) > {vmx} && "
            f"V({x}_{ph}i)*(V({x}_ref{ph}) - I(V{x}_s{ph})) > 0) ? 0 : "
            f"2e4*(V({x}_ref{ph}) - I(V{x}_s{ph}))",
            f"C{x}_{ph}i {x}_{ph}i 0 1",
            f"R{x}_{ph}i {x}_{ph}i 0 1e12",
            f"B{x}_{ph} {x}_{ph}o {n[m]} V = {vmx}*tanh((20*(V({x}_ref{ph}) - I(V{x}_s{ph}))"
            f" + V({x}_{ph}i))/{vmx})",
        ]
    # power drawn from VM (ideal bridge): P = sum v·i
    lines.append(
        f"B{x}_vm {vm} {gnd} I = (V({x}_ao,{n['A-']})*I(V{x}_sa) + V({x}_bo,{n['B-']})*I(V{x}_sb))"
        f"/max(V({vm},{gnd}), 1)"
    )
    return lines


# ---------------------------------------------------------------------------- thermocouple


def _thermocouple(x: str, n: dict[str, str], v: Value, stim: Stimulus) -> list[str]:
    kind = v("type").upper()
    if kind not in tc.TYPES:
        raise ValueError(f"tipo de termopar desconhecido: {kind}")
    lo, hi = tc.range_c(kind)
    t, tr = f"{x}_t", f"{x}_tr"
    return [
        f"* {x}: termopar {kind} (NIST ITS-90)",
        f"B{x}_t {t} 0 V = min(max({stim(v('temp'))}, {lo:g}), {hi:g})",
        f"B{x}_tr {tr} 0 V = min(max({stim(v('tref'))}, {lo:g}), {hi:g})",
        f"B{x}_e {x}_e {n['-']} V = {tc.spice_expr(kind, f'V({t})')} - "
        f"{tc.spice_expr(kind, f'V({tr})')}",
        f"R{x} {x}_e {n['+']} {v('r')}",
    ]
