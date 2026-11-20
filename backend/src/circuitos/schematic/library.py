"""Symbol library of the schematic editor: pins (grid offsets), parameters and catalogue links.

The pin offsets are the contract with the editor, which draws each symbol around them; the
editor reads this table from ``GET /api/v1/schematic/library``. Generic models (no catalogue
part) are didactic SPICE defaults, not data of any real component; a catalogue part replaces
them by the model built from its datasheet (:mod:`circuitos.schematic.parts`).
"""

from __future__ import annotations

import math

from circuitos.schematic.model import Component, Point
from circuitos.schematic.symbols_base import ParamDef, ParamType, PinDef, Symbol

__all__ = ["ParamDef", "ParamType", "PinDef", "Symbol"]


def _two(a: str = "1", b: str = "2") -> tuple[PinDef, ...]:
    return (PinDef(a, -2, 0), PinDef(b, 2, 0))


_SRC_PINS = (PinDef("p", 0, -2), PinDef("n", 0, 2))
_TRANSISTOR = ("c", "b", "e")


def _tol(default: str) -> ParamDef:
    return ParamDef(
        "tol",
        "Tolerância",
        "%",
        default,
        optional=True,
        help="Faixa ± usada no Monte Carlo e no pior caso (do datasheet da peça)",
    )


_AC = ParamDef("ac", "Amplitude AC", "", "0", help="Magnitude na análise AC (.ac)")
_MODEL = ParamDef(
    "model",
    "Modelo SPICE",
    "",
    "",
    type="text",
    optional=True,
    help="Nome de um .model/.subckt das diretivas; substitui os parâmetros genéricos",
)


def _sources(prefix: str, unit: str, label: str) -> list[Symbol]:
    ac = ParamDef("ac", "Amplitude AC", unit, "0", help="Magnitude na análise AC (.ac)")
    ac1 = ParamDef("ac", "Amplitude AC", unit, "1", help="Magnitude na análise AC (.ac)")
    k = prefix.lower()
    return [
        Symbol(
            f"{k}dc",
            f"{label} CC",
            "Fontes",
            prefix,
            _SRC_PINS,
            (ParamDef("dc", "Valor", unit, "5" if unit == "V" else "1m"), ac, _tol("0")),
            tolerance="dc",
        ),
        Symbol(
            f"{k}sin",
            f"{label} senoidal",
            "Fontes",
            prefix,
            _SRC_PINS,
            (
                ParamDef("offset", "Nível CC", unit, "0"),
                ParamDef("amplitude", "Amplitude (pico)", unit, "1"),
                ParamDef("freq", "Frequência", "Hz", "1k"),
                ParamDef("delay", "Atraso", "s", "0"),
                ParamDef("damping", "Amortecimento", "1/s", "0"),
                ParamDef("phase", "Fase", "°", "0"),
                ac1,
                _tol("0"),
            ),
            tolerance="amplitude",
        ),
        Symbol(
            f"{k}pulse",
            f"{label} pulso",
            "Fontes",
            prefix,
            _SRC_PINS,
            (
                ParamDef("v1", "Nível inicial", unit, "0"),
                ParamDef("v2", "Nível pulsado", unit, "5" if unit == "V" else "1m"),
                ParamDef("delay", "Atraso", "s", "0"),
                ParamDef("rise", "Subida", "s", "1n"),
                ParamDef("fall", "Descida", "s", "1n"),
                ParamDef("width", "Largura", "s", "0.5m"),
                ParamDef("period", "Período", "s", "1m"),
                ac,
            ),
        ),
        Symbol(
            f"{k}pwl",
            f"{label} PWL",
            "Fontes",
            prefix,
            _SRC_PINS,
            (
                ParamDef(
                    "points",
                    "Pontos (t v ...)",
                    "",
                    "0 0 1m 1 2m 1",
                    type="text",
                    help="Pares tempo/valor em notação SPICE, separados por espaço",
                ),
                ParamDef(
                    "repeat",
                    "Repetir",
                    "",
                    "não",
                    type="choice",
                    choices=("não", "sim"),
                ),
                ac,
            ),
        ),
    ]


SYMBOLS: dict[str, Symbol] = {
    s.kind: s
    for s in [
        # passives and loads -------------------------------------------------------------
        Symbol(
            "resistor",
            "Resistor",
            "Passivos",
            "R",
            _two(),
            (ParamDef("value", "Resistência", "Ω", "1k"), _tol("5")),
            tolerance="value",
        ),
        Symbol(
            "capacitor",
            "Capacitor",
            "Passivos",
            "C",
            _two(),
            (
                ParamDef("value", "Capacitância", "F", "1u"),
                ParamDef("ic", "Tensão inicial", "V", "", optional=True),
                _tol("10"),
            ),
            tolerance="value",
        ),
        Symbol(
            "inductor",
            "Indutor",
            "Passivos",
            "L",
            _two(),
            (
                ParamDef("value", "Indutância", "H", "1m"),
                ParamDef("ic", "Corrente inicial", "A", "", optional=True),
                _tol("10"),
            ),
            tolerance="value",
        ),
        Symbol(
            "rl_load",
            "Carga RL",
            "Passivos",
            "X",
            _two(),
            (
                ParamDef("r", "Resistência", "Ω", "10"),
                ParamDef("l", "Indutância", "H", "10m"),
                _tol("0"),
            ),
            tolerance="r",
            description="R e L em série (carga de eletrônica de potência)",
            ref_prefix="Z",
        ),
        Symbol(
            "transformer",
            "Transformador",
            "Passivos",
            "L",
            (PinDef("p1", -2, -2), PinDef("p2", -2, 2), PinDef("s1", 2, -2), PinDef("s2", 2, 2)),
            (
                ParamDef("lp", "Indutância do primário", "H", "100m"),
                ParamDef("n", "Relação Ns/Np", "", "1"),
                ParamDef("k", "Acoplamento", "", "0.999"),
                ParamDef("rp", "Resistência do primário", "Ω", "10m"),
                ParamDef("rs", "Resistência do secundário", "Ω", "10m"),
            ),
            description="Dois indutores acoplados; pontos em p1 e s1; 1 GΩ entre p2 e s2",
            ref_prefix="T",
        ),
        # transformers sized by their nameplate (Vp, Vs, S) -------------------------------
        Symbol(
            "transformer_1ph",
            "Transformador monofásico",
            "Transformadores",
            "L",
            (PinDef("p1", -2, -2), PinDef("p2", -2, 2), PinDef("s1", 2, -2), PinDef("s2", 2, 2)),
            (
                ParamDef("vp", "Tensão do primário (eficaz)", "V", "220"),
                ParamDef("vs", "Tensão do secundário (eficaz)", "V", "12"),
                ParamDef(
                    "turns",
                    "Relação de espiras Np/Ns (vazio: Vp/Vs)",
                    "",
                    "",
                ),
                ParamDef("sn", "Potência nominal", "VA", "50"),
                ParamDef("freq", "Frequência", "Hz", "60"),
                ParamDef("imag", "Corrente de magnetização (% de In)", "%", "5"),
                ParamDef("rcu", "Perdas no cobre (% de Sn)", "%", "2"),
            ),
            description="Transformador definido pelos dados de placa: a relação de espiras sai "
            "de Vp/Vs (ou é dada); a magnetização e as perdas no cobre são valores didáticos, "
            "ajuste com os ensaios a vazio e de curto-circuito. Pontos em p1 e s1.",
            ref_prefix="T",
        ),
        Symbol(
            "transformer_3ph",
            "Transformador trifásico",
            "Transformadores",
            "L",
            (
                PinDef("H1", -3, -3),
                PinDef("H2", -3, -1),
                PinDef("H3", -3, 1),
                PinDef("H0", -3, 3),
                PinDef("X1", 3, -3),
                PinDef("X2", 3, -1),
                PinDef("X3", 3, 1),
                PinDef("X0", 3, 3),
            ),
            (
                ParamDef("vp", "Tensão de linha do primário (eficaz)", "V", "380"),
                ParamDef("vs", "Tensão de linha do secundário (eficaz)", "V", "220"),
                ParamDef(
                    "conn_p",
                    "Ligação do primário",
                    "",
                    "D",
                    type="choice",
                    choices=("D", "Y"),
                ),
                ParamDef(
                    "conn_s",
                    "Ligação do secundário",
                    "",
                    "Y",
                    type="choice",
                    choices=("Y", "D"),
                ),
                ParamDef(
                    "turns",
                    "Relação de espiras por fase Np/Ns (vazio: das tensões)",
                    "",
                    "",
                ),
                ParamDef("sn", "Potência nominal (total)", "VA", "3k"),
                ParamDef("freq", "Frequência", "Hz", "60"),
                ParamDef("imag", "Corrente de magnetização (% de In)", "%", "5"),
                ParamDef("rcu", "Perdas no cobre (% de Sn)", "%", "2"),
            ),
            description="Três colunas (uma por fase), primário H1-H3 e secundário X1-X3; H0 e "
            "X0 são os neutros (só existem na ligação em estrela). D = triângulo, Y = estrela: "
            "Dy dá Dyn11, Yd dá Yd1, Yy e Dd dão 0.",
            ref_prefix="T",
        ),
        # sources -------------------------------------------------------------------------
        *_sources("V", "V", "Fonte de tensão"),
        *_sources("I", "A", "Fonte de corrente"),
        Symbol(
            "v3ph",
            "Fonte trifásica",
            "Fontes",
            "V",
            (PinDef("a", 2, -2), PinDef("b", 2, 0), PinDef("c", 2, 2), PinDef("n", -2, 0)),
            (
                ParamDef("vrms", "Tensão de fase (eficaz)", "V", "127"),
                ParamDef("freq", "Frequência", "Hz", "60"),
                ParamDef("phase", "Fase de a", "°", "0"),
                ParamDef("sequence", "Sequência", "", "abc", type="choice", choices=("abc", "acb")),
            ),
            description="Três fontes senoidais em estrela (neutro n), defasadas de 120°",
        ),
        Symbol(
            "bsource",
            "Fonte dependente",
            "Fontes",
            "B",
            _SRC_PINS,
            (
                ParamDef("type", "Tipo", "", "V", type="choice", choices=("V", "I")),
                ParamDef(
                    "expr",
                    "Expressão",
                    "",
                    "v(in)*2",
                    type="text",
                    help="Expressão do ngspice, ex.: v(a,b)*i(V1), sin(2*pi*60*time)",
                ),
            ),
            description="Fonte dependente de tensão ou corrente definida por uma expressão de "
            "tensões, correntes e tempo (elemento B do ngspice).",
        ),
        Symbol(
            "vcvs",
            "Fonte de tensão controlada por tensão (E)",
            "Fontes",
            "E",
            (PinDef("op", 2, -2), PinDef("on", 2, 2), PinDef("cp", -2, -2), PinDef("cn", -2, 2)),
            (ParamDef("gain", "Ganho", "V/V", "1"),),
        ),
        Symbol(
            "vccs",
            "Fonte de corrente controlada por tensão (G)",
            "Fontes",
            "G",
            (PinDef("op", 2, -2), PinDef("on", 2, 2), PinDef("cp", -2, -2), PinDef("cn", -2, 2)),
            (ParamDef("gm", "Transcondutância", "S", "1m"),),
        ),
        Symbol(
            "cccs",
            "Fonte de corrente controlada por corrente (F)",
            "Fontes",
            "F",
            _SRC_PINS,
            (
                ParamDef("control", "Fonte de controle", "", "V1", type="text"),
                ParamDef("gain", "Ganho", "A/A", "1"),
            ),
            description="A corrente de controle é a da fonte de tensão indicada",
        ),
        Symbol(
            "ccvs",
            "Fonte de tensão controlada por corrente (H)",
            "Fontes",
            "H",
            _SRC_PINS,
            (
                ParamDef("control", "Fonte de controle", "", "V1", type="text"),
                ParamDef("r", "Transresistência", "Ω", "1k"),
            ),
            description="A corrente de controle é a da fonte de tensão indicada",
        ),
        # semiconductors ------------------------------------------------------------------
        Symbol(
            "diode",
            "Diodo",
            "Semicondutores",
            "D",
            _two("a", "k"),
            (
                _MODEL,
                ParamDef("is", "IS", "A", "1e-14"),
                ParamDef("n", "N", "", "1"),
                ParamDef("rs", "RS", "Ω", "0"),
                ParamDef("cjo", "CJO", "F", "0"),
                ParamDef("tt", "TT", "s", "0"),
                ParamDef("bv", "BV", "V", "", optional=True),
            ),
            catalogue=("diode.rectifier", "diode.fast", "diode.schottky", "diode.signal"),
        ),
        Symbol(
            "zener",
            "Diodo Zener",
            "Semicondutores",
            "X",
            _two("a", "k"),
            (
                ParamDef("vz", "VZ", "V", "5.1"),
                ParamDef("rz", "rz", "Ω", "10"),
                ParamDef("vf", "VF direta", "V", "0.7"),
                _tol("0"),
            ),
            catalogue=("diode.zener",),
            tolerance="vz",
            description="Linear por partes: V_Z0 + r_z·I na ruptura, queda V_F constante direta",
            ref_prefix="D",
        ),
        *[
            Symbol(
                kind,
                label,
                "Semicondutores",
                "Q",
                (PinDef("c", 0, -2), PinDef("b", -2, 0), PinDef("e", 0, 2)),
                (
                    _MODEL,
                    ParamDef("bf", "BF", "", "100"),
                    ParamDef("is", "IS", "A", "1e-14"),
                    ParamDef("vaf", "VAF", "V", "", optional=True),
                    ParamDef(
                        "ic_op",
                        "IC de operação",
                        "A",
                        "1m",
                        help="Peça do catálogo: escolhe o hFE ensaiado mais perto desta corrente",
                    ),
                    _tol("0"),
                ),
                catalogue=(cat,),
                tolerance="bf",
            )
            for kind, label, cat in (
                ("npn", "Transistor NPN", "bjt.npn"),
                ("pnp", "Transistor PNP", "bjt.pnp"),
            )
        ],
        *[
            Symbol(
                kind,
                label,
                "Semicondutores",
                "M",
                (PinDef("d", 0, -2), PinDef("g", -2, 0), PinDef("s", 0, 2)),
                (
                    _MODEL,
                    ParamDef("vto", "VTO", "V", vto),
                    ParamDef("kp", "KP", "A/V²", "20m"),
                    ParamDef("lambda", "LAMBDA", "1/V", "0"),
                ),
                catalogue=cat,
                description="Nível 1 (quadrático), corpo ligado à fonte",
            )
            for kind, label, vto, cat in (
                ("nmos", "MOSFET canal N", "2", ("mosfet.n",)),
                ("pmos", "MOSFET canal P", "-2", ()),
            )
        ],
        *[
            Symbol(
                kind,
                label,
                "Semicondutores",
                "J",
                (PinDef("d", 0, -2), PinDef("g", -2, 0), PinDef("s", 0, 2)),
                (
                    _MODEL,
                    ParamDef("vto", "VTO", "V", vto),
                    ParamDef("beta", "BETA", "A/V²", "1m"),
                    ParamDef("lambda", "LAMBDA", "1/V", "0"),
                ),
                catalogue=cat,
            )
            for kind, label, vto, cat in (
                ("njf", "JFET canal N", "-2", ("jfet.n",)),
                ("pjf", "JFET canal P", "2", ()),
            )
        ],
        Symbol(
            "opamp",
            "Amplificador operacional",
            "Semicondutores",
            "X",
            (PinDef("inn", -3, -1), PinDef("inp", -3, 1), PinDef("out", 3, 0)),
            (
                ParamDef("a0", "Ganho em malha aberta", "V/V", "200k"),
                ParamDef("gbw", "GBW", "Hz", "1meg"),
                ParamDef("sr", "Taxa de subida", "V/s", "", optional=True),
                ParamDef("vcc", "Alimentação +", "V", "15"),
                ParamDef("vee", "Alimentação −", "V", "-15"),
            ),
            catalogue=("opamp",),
            description="Macromodelo de um polo com limite de taxa de subida e saturação",
            ref_prefix="U",
        ),
        Symbol(
            "switch",
            "Chave controlada por tensão",
            "Chaves",
            "S",
            (PinDef("1", -2, 0), PinDef("2", 2, 0), PinDef("cp", -1, 2), PinDef("cn", 1, 2)),
            (
                _MODEL,
                ParamDef("ron", "R ligada", "Ω", "10m"),
                ParamDef("roff", "R desligada", "Ω", "10meg"),
                ParamDef("vt", "Limiar", "V", "2.5"),
                ParamDef("vh", "Histerese", "V", "0.1"),
            ),
            description="Fecha quando v(cp) − v(cn) > limiar",
        ),
        Symbol(
            "igbt",
            "IGBT",
            "Chaves",
            "X",
            (PinDef("c", 0, -2), PinDef("g", -2, 0), PinDef("e", 0, 2)),
            (
                ParamDef("vth", "VGE de condução", "V", "5"),
                ParamDef("v0", "Joelho V0", "V", "1"),
                ParamDef("ron", "r_on", "Ω", "20m"),
                ParamDef(
                    "diode", "Diodo antiparalelo", "", "sim", type="choice", choices=("sim", "não")
                ),
                ParamDef("vf", "VF do diodo", "V", "1.5"),
            ),
            catalogue=("igbt.n",),
            description="Chave comandada por v(g,e): i_C = (v_CE − V0)/r_on, sem condução reversa",
            ref_prefix="Q",
        ),
        Symbol(
            "scr",
            "SCR",
            "Chaves",
            "X",
            (PinDef("a", 0, -2), PinDef("k", 0, 2), PinDef("g", -2, 1)),
            (
                ParamDef("vt0", "V_T0", "V", "1"),
                ParamDef("rt", "r_T", "Ω", "10m"),
                ParamDef("igt", "I_GT", "A", "10m"),
                ParamDef("ih", "I_H", "A", "20m"),
                ParamDef("il", "I_L", "A", "40m"),
            ),
            catalogue=("thyristor.scr",),
            description="Tiristor comportamental (o da bancada BD-TIR): porta referida ao catodo",
        ),
        Symbol(
            "triac",
            "TRIAC",
            "Chaves",
            "X",
            (PinDef("mt2", 0, -2), PinDef("mt1", 0, 2), PinDef("g", -2, 1)),
            (
                ParamDef("vt0", "V_T0", "V", "1"),
                ParamDef("rt", "r_T", "Ω", "10m"),
                ParamDef("igt", "I_GT", "A", "10m"),
                ParamDef("ih", "I_H", "A", "20m"),
                ParamDef("il", "I_L", "A", "40m"),
            ),
            catalogue=("thyristor.triac",),
            description="TRIAC comportamental (o da bancada BD-TIR): porta referida a MT1",
        ),
        # indicators: LEDs and incandescent lamps ------------------------------------------
        Symbol(
            "led",
            "LED",
            "LEDs e lâmpadas",
            "X",
            (PinDef("a", -2, 0), PinDef("k", 2, 0)),
            (
                ParamDef(
                    "color",
                    "Cor",
                    "",
                    "vermelho",
                    type="choice",
                    choices=("vermelho", "laranja", "amarelo", "verde", "azul", "branco"),
                    help="Só muda a cor do brilho no desenho; a peça do catálogo define a cor",
                ),
                ParamDef("vf", "Tensão direta V_F", "V", "2", help="Genérico (didático)"),
                ParamDef(
                    "if_ref",
                    "Corrente de referência do brilho",
                    "A",
                    "20m",
                    help="Corrente em que o LED brilha 100 % (a de ensaio de V_F)",
                ),
                ParamDef("if_max", "Corrente máxima", "A", "30m", help="Acima dela: queima"),
            ),
            catalogue=("optoelectronic.led",),
            description="LED de queda constante (V_F do datasheet); brilha conforme a corrente "
            "simulada e avisa acima de I_F máxima",
            ref_prefix="LED",
        ),
        Symbol(
            "lamp",
            "Lâmpada incandescente",
            "LEDs e lâmpadas",
            "R",
            _two(),
            (
                ParamDef("vn", "Tensão nominal", "V", "12", help="Valor de placa"),
                ParamDef("pn", "Potência nominal", "W", "5", help="Valor de placa"),
            ),
            catalogue=("lamp.incandescent",),
            description="Filamento como resistência a quente R = V_n²/P_n; brilha conforme a "
            "potência simulada (sem corrente de partida a frio)",
            ref_prefix="LP",
        ),
        # other ---------------------------------------------------------------------------
        Symbol(
            "subckt",
            "Subcircuito",
            "Outros",
            "X",
            (),
            (
                ParamDef("model", "Nome do .subckt", "", "", type="text"),
                ParamDef("pins", "Pinos (em ordem)", "", "1 2", type="text"),
                ParamDef("args", "Parâmetros", "", "", type="text", optional=True),
            ),
            description="Instância de um .subckt (ex.: modelo do fabricante nas diretivas)",
        ),
        Symbol("ground", "Terra", "Fontes", "", (PinDef("g", 0, 0),)),
    ]
}


def symbol(kind: str) -> Symbol:
    try:
        return SYMBOLS[kind]
    except KeyError as exc:
        raise ValueError(f"Tipo de componente desconhecido: {kind!r}") from exc


def subckt_pin_names(comp: Component) -> list[str]:
    names = comp.params.get("pins", "1 2").replace(",", " ").split()
    return names or ["1"]


def pin_defs(comp: Component) -> tuple[PinDef, ...]:
    """Pins of a component; a subcircuit has its pins on two sides of a box."""
    sym = symbol(comp.kind)
    if comp.kind != "subckt":
        return sym.pins
    names = subckt_pin_names(comp)
    left = math.ceil(len(names) / 2)
    pins = [PinDef(n, -3, 2 * i) for i, n in enumerate(names[:left])]
    pins += [PinDef(n, 3, 2 * i) for i, n in enumerate(names[left:])]
    return tuple(pins)


def transform(dx: int, dy: int, rot: int, mirror: bool) -> Point:
    """Mirror (x → −x), then rotate clockwise on screen (y downwards)."""
    if mirror:
        dx = -dx
    for _ in range((rot // 90) % 4):
        dx, dy = -dy, dx
    return dx, dy


def pin_positions(comp: Component) -> dict[str, Point]:
    out: dict[str, Point] = {}
    for p in pin_defs(comp):
        dx, dy = transform(p.dx, p.dy, comp.rot, comp.mirror)
        out[p.name] = (comp.x + dx, comp.y + dy)
    return out


def param(comp: Component, name: str) -> str:
    """Parameter value, falling back on the symbol default."""
    v = comp.params.get(name)
    if v is not None and v.strip() != "":
        return v.strip()
    return symbol(comp.kind).param(name).default


def element_name(comp: Component) -> str:
    """SPICE element name: the designator, prefixed with the element letter when needed."""
    prefix = symbol(comp.kind).prefix
    if not prefix or comp.ref[0].upper() == prefix:
        return comp.ref
    return f"{prefix}{comp.ref}"


ANALYSES: dict[str, tuple[str, tuple[ParamDef, ...]]] = {
    "op": ("Ponto de operação (.op)", ()),
    "tran": (
        "Transitória (.tran)",
        (
            ParamDef("tstop", "Tempo final", "s", "10m"),
            ParamDef("tstep", "Passo de saída", "s", "", optional=True, help="Vazio: tstop/1000"),
            ParamDef("tstart", "Início da gravação", "s", "", optional=True),
            ParamDef("tmax", "Passo máximo", "s", "", optional=True),
            ParamDef(
                "uic",
                "Condições iniciais (UIC)",
                "",
                "não",
                type="choice",
                choices=("não", "sim"),
            ),
        ),
    ),
    "ac": (
        "Resposta em frequência (.ac)",
        (
            ParamDef(
                "variation", "Escala", "", "dec", type="choice", choices=("dec", "oct", "lin")
            ),
            ParamDef("points", "Pontos (por década)", "", "50"),
            ParamDef("fstart", "Frequência inicial", "Hz", "10"),
            ParamDef("fstop", "Frequência final", "Hz", "1meg"),
        ),
    ),
    "dc": (
        "Varredura CC (.dc)",
        (
            ParamDef("source", "Fonte (ou temp)", "", "V1", type="text"),
            ParamDef("start", "Início", "", "0"),
            ParamDef("stop", "Fim", "", "10"),
            ParamDef("step", "Passo", "", "0.1"),
            ParamDef("source2", "Segunda fonte", "", "", type="text", optional=True),
            ParamDef("start2", "Início (2ª)", "", "", optional=True),
            ParamDef("stop2", "Fim (2ª)", "", "", optional=True),
            ParamDef("step2", "Passo (2ª)", "", "", optional=True),
        ),
    ),
    "noise": (
        "Ruído (.noise)",
        (
            ParamDef("output", "Nó de saída (rótulo)", "", "out", type="text"),
            ParamDef("reference", "Nó de referência", "", "", type="text", optional=True),
            ParamDef("source", "Fonte de entrada", "", "V1", type="text"),
            ParamDef(
                "variation", "Escala", "", "dec", type="choice", choices=("dec", "oct", "lin")
            ),
            ParamDef("points", "Pontos (por década)", "", "20"),
            ParamDef("fstart", "Frequência inicial", "Hz", "10"),
            ParamDef("fstop", "Frequência final", "Hz", "1meg"),
        ),
    ),
}


# controllers, sensors and actuators (Fase 11): defined in their own module, which imports the
# classes above, so the import sits at the end
from circuitos.schematic.cosim_symbols import COSIM_SYMBOLS  # noqa: E402

SYMBOLS.update({s.kind: s for s in COSIM_SYMBOLS})
