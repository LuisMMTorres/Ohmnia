"""Which package each schematic component takes on the breadboard, and what each leg is.

Three origins, shown to the user:

* ``datasheet``: a catalogue part with a pinout transcribed from its datasheet (with page). The
  check compares its legs; the status (``extraido``/``revisado``) says whether it was reviewed.
* ``generico``: a generic part of the simulator (no catalogue part). The system draws a didactic
  package with each leg labelled (C, B, E...). This is not a real part's pinout: the check works
  on those labels and the user is told to confirm the real part's pinout.
* ``sem_pinagem``: a catalogue part whose pinout is not in the catalogue yet. Rule 1: no guessed
  pinout. It is drawn with unlabelled legs, with a warning, and left out of the check.

Ideal elements with no physical counterpart (controlled sources, behavioural sources, the
voltage-controlled switch, subcircuits) are ``sem_montagem``: not placed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from circuitos.breadboard.packages import PACKAGES, package
from circuitos.components.models import ComponentRecord, DatasheetRef, SourceRef
from circuitos.schematic.cosim_symbols import POT_REFERENCE, TRIMPOT_REFERENCE
from circuitos.schematic.library import param, symbol
from circuitos.schematic.model import Component
from circuitos.schematic.values import format_value, try_parse

Origin = Literal["datasheet", "generico", "sem_pinagem", "sem_montagem", "implicito"]


@dataclass
class Resolved:
    ref: str
    kind: str
    package: str | None
    origin: Origin
    pinmap: dict[str, str] = field(default_factory=dict)  # package pin -> symbol pin / vcc / vee
    labels: dict[str, str] = field(default_factory=dict)  # package pin -> label on the drawing
    title: str = ""  # text on the body: part number, value, instrument name
    part_number: str | None = None
    source: SourceRef | None = None
    datasheet: DatasheetRef | None = None
    status: str | None = None  # pinout review status (datasheet origin)
    notes: list[str] = field(default_factory=list)
    bands: list[str] = field(default_factory=list)  # resistor colour code
    supplies: dict[str, float] = field(default_factory=dict)  # "vcc"/"vee" -> volts (ICs)

    @property
    def checkable(self) -> bool:
        return self.origin in ("datasheet", "generico", "implicito") and self.package is not None


# ------------------------------------------------------------------------- colour code

COLOURS = (
    "preto",
    "marrom",
    "vermelho",
    "laranja",
    "amarelo",
    "verde",
    "azul",
    "violeta",
    "cinza",
    "branco",
)
_MULT = {-2: "prata", -1: "ouro"}
_TOL = {
    1.0: "marrom",
    2.0: "vermelho",
    0.5: "verde",
    0.25: "azul",
    0.1: "violeta",
    0.05: "cinza",
    5.0: "ouro",
    10.0: "prata",
}


def colour_code(ohms: float, tol: str | None = None) -> list[str]:
    """IEC 60062 colour bands: two significant digits when exact, otherwise three.

    The tolerance band is drawn only when the tolerance is known (parameter ``tol``).
    """
    if not math.isfinite(ohms) or ohms <= 0:
        return []
    for digits in (2, 3):
        exp = math.floor(math.log10(ohms)) - (digits - 1)
        mant = round(ohms / 10**exp)
        if mant >= 10**digits:
            mant //= 10
            exp += 1
        if abs(mant * 10**exp - ohms) <= ohms * 1e-6 or digits == 3:
            if not -2 <= exp <= 9:
                return []
            bands = [COLOURS[int(d)] for d in f"{mant:0{digits}d}"]
            bands.append(_MULT[exp] if exp < 0 else COLOURS[exp])
            t = try_parse((tol or "").strip().rstrip("%").replace(",", "."))
            if t is not None and t in _TOL:
                bands.append(_TOL[t])
            return bands
    return []


# ------------------------------------------------------------------------- generic defaults

_INSTRUMENT = {
    "vdc": ("fonte-cc", "Fonte CC"),
    "vsin": ("gerador", "Gerador de funções"),
    "vpulse": ("gerador", "Gerador de funções (pulso)"),
    "vpwl": ("gerador", "Gerador arbitrário"),
    "idc": ("fonte-i", "Fonte de corrente CC"),
    "isin": ("fonte-i", "Fonte de corrente senoidal"),
    "ipulse": ("fonte-i", "Fonte de corrente (pulso)"),
    "ipwl": ("fonte-i", "Fonte de corrente arbitrária"),
    "v3ph": ("trifasica", "Fonte trifásica"),
    "transformer": ("trafo", "Transformador"),
    "transformer_1ph": ("trafo", "Transformador monofásico"),
    "transformer_3ph": ("trafo-3f", "Transformador trifásico"),
    "autotransformer": ("autotrafo", "Autotransformador"),
    "transformer_1ph_4": ("trafo-4b", "Transformador de 4 bobinas"),
    "transformer_3ph_open": ("trafo-3f-12", "Transformador trifásico de bobinas acessíveis"),
    "rl_load": ("carga", "Carga RL"),
}
_BOARDS = {"arduino_uno": "board-uno", "esp32_devkitc": "board-esp32"}
_IDEAL = {"bsource", "vcvs", "vccs", "cccs", "ccvs", "switch", "subckt"}
# generic three-leg parts: leg order and labels (didactic, not a real part's pinout)
_GENERIC_3 = {
    "npn": ("to-92", ("e", "b", "c"), "Transistor NPN"),
    "pnp": ("to-92", ("e", "b", "c"), "Transistor PNP"),
    "njf": ("to-92", ("d", "s", "g"), "JFET canal N"),
    "pjf": ("to-92", ("d", "s", "g"), "JFET canal P"),
    "nmos": ("to-220", ("g", "d", "s"), "MOSFET canal N"),
    "pmos": ("to-220", ("g", "d", "s"), "MOSFET canal P"),
    "igbt": ("to-220", ("g", "c", "e"), "IGBT"),
    "scr": ("to-220", ("k", "a", "g"), "SCR"),
    "triac": ("to-220", ("mt1", "mt2", "g"), "TRIAC"),
}
_LABEL = {
    "c": "C",
    "b": "B",
    "e": "E",
    "d": "D",
    "g": "G",
    "s": "S",
    "a": "A",
    "k": "K",
    "mt1": "MT1",
    "mt2": "MT2",
    "inn": "IN−",
    "inp": "IN+",
    "out": "OUT",
    "vcc": "V+",
    "vee": "V−",
}
GENERIC_NOTE = (
    "Peça genérica: as pernas estão rotuladas pela função, não pela pinagem de uma peça real. "
    "Escolha a peça do catálogo ou confira a pinagem no datasheet antes de montar."
)


def _value_label(comp: Component, name: str, unit: str) -> str:
    v = try_parse(param(comp, name))
    return f"{format_value(v, 3)}{unit}" if v is not None else param(comp, name)


def _generic(comp: Component) -> Resolved:
    kind = comp.kind
    r = Resolved(comp.ref, kind, None, "generico")
    if kind == "lm35":
        r.package = "to-92"
        r.pinmap = {"1": "VS", "2": "OUT", "3": "GND"}
        r.labels = {"1": "+VS", "2": "VOUT", "3": "GND"}
        r.title = "LM35"
        r.notes.append(GENERIC_NOTE)
        return r
    if kind in ("potentiometer", "trimpot"):
        # drawn as a real reference part (rule 1: its pinout is the one of that datasheet)
        pot = kind == "potentiometer"
        r.package = "pot-9mm" if pot else "trimpot-3386p"
        r.pinmap = {"1": "a", "2": "w", "3": "b"}
        r.labels = {"1": "CCW", "2": "WIPER", "3": "CW"}
        r.title = f"{_value_label(comp, 'r', 'Ω')}"
        ref = POT_REFERENCE if pot else TRIMPOT_REFERENCE
        r.notes.append(
            f"Peça genérica desenhada como a de referência {ref}: pino 1 = anti-horário (CCW, "
            "posição 0), 2 = cursor, 3 = horário (CW). Escolha a peça do catálogo para usar a "
            "sua."
        )
        return r
    if kind == "timer555":
        r.package = "dip-8"
        names = ("GND", "TRIG", "OUT", "RESET", "CONT", "THRES", "DISCH", "VCC")
        r.labels = {str(i + 1): name for i, name in enumerate(names)}
        r.pinmap = dict(r.labels)
        r.title = "555"
        r.notes.append(
            "Pinagem do 555 em DIP-8, igual em todos os fabricantes (TI NE555, SLFS022K, "
            "tabela 4-1); escolha o NE555P do catálogo para conferir com o datasheet."
        )
        return r
    if kind in _BOARDS:
        pkg = package(_BOARDS[kind])
        model = {pin.name for pin in symbol(kind).pins}
        r.package = pkg.id
        r.labels = dict(zip(pkg.pins, pkg.silk, strict=True))
        r.pinmap = {pin: name for pin, name in r.labels.items() if name in model}
        r.title = symbol(kind).label
        loose = sorted({n for n in pkg.silk if n not in model}, key=pkg.silk.index)
        r.notes.append(
            "Pinos na ordem das barras da placa real (vista de cima). Os pinos GND são ligados "
            "entre si na placa. Sem modelo na simulação (ficam fora da conferência): "
            + ", ".join(loose)
            + "."
        )
        r.notes.append(pkg.note)
        return r
    if kind in ("tact_switch", "push_nc"):
        r.package = "tact-2"
        r.pinmap = {"1": "1", "2": "2"}
        r.labels = {"1": "1", "2": "2"}
        r.title = "Botão NA" if kind == "tact_switch" else "Botão NF"
        return r
    if kind == "tact_switch4":
        # legs facing each other across the channel (same row) are the joined pairs
        r.package = "tact-6x6"
        r.pinmap = {"1": "1", "4": "2", "2": "3", "3": "4"}
        r.labels = {"1": "1", "4": "2", "2": "3", "3": "4"}
        r.title = "Chave táctil"
        r.notes.append(GENERIC_NOTE)
        return r
    if f"mod-{kind}" in PACKAGES:
        pkg = package(f"mod-{kind}")
        r.package = pkg.id
        r.pinmap = {pin: pin for pin in pkg.pins}
        r.labels = {pin: pin for pin in pkg.pins}
        r.title = pkg.label
        return r
    if kind in _IDEAL:
        r.origin = "sem_montagem"
        r.notes.append("Elemento ideal da simulação, sem equivalente físico: não vai à protoboard.")
        return r
    if kind in _INSTRUMENT:
        pid, title = _INSTRUMENT[kind]
        r.package = pid
        r.title = title
        r.pinmap = {t: t for t in package(pid).pins}
        r.labels = {t: t.upper() if len(t) <= 2 else t for t in package(pid).pins}
        if kind == "vdc":
            dc = try_parse(param(comp, "dc"))
            r.supplies["dc"] = dc if dc is not None else 0.0
            r.title = f"{title} {_value_label(comp, 'dc', 'V')}"
        return r
    if kind == "resistor":
        ohms = try_parse(param(comp, "value"))
        r.package = "axial-r"
        r.pinmap = {"1": "1", "2": "2"}
        r.title = _value_label(comp, "value", "Ω")
        r.bands = colour_code(ohms, comp.params.get("tol")) if ohms else []
        return r
    if kind == "capacitor":
        farads = try_parse(param(comp, "value")) or 0.0
        r.title = _value_label(comp, "value", "F")
        if farads >= 1e-6:
            r.package = "radial-elco"
            vr = try_parse(param(comp, "v_rated"))
            if vr is not None:
                # printed on the can next to the capacitance, as on a real part
                r.title = f"{r.title} {format_value(vr, 3)}V"
            r.pinmap = {"+": "1", "-": "2"}
            r.labels = {"+": "+", "-": "−"}
            r.notes.append(
                "Capacitor ≥ 1 µF desenhado como eletrolítico: a perna + corresponde ao pino 1 do "
                "símbolo. Confira se o pino 1 está no nó de maior tensão."
            )
        else:
            r.package = "radial-cer"
            r.pinmap = {"1": "1", "2": "2"}
        return r
    if kind == "inductor":
        r.package = "axial-l"
        r.pinmap = {"1": "1", "2": "2"}
        r.title = _value_label(comp, "value", "H")
        return r
    if kind in ("diode", "zener"):
        r.package = "do-41" if kind == "diode" else "do-35"
        r.pinmap = {"1": "k", "2": "a"}
        r.labels = {"1": "K", "2": "A"}
        r.title = "Diodo" if kind == "diode" else "Zener"
        r.notes.append("Faixa pintada = catodo (K).")
        return r
    if kind == "led":
        r.package = "led-5mm"
        r.pinmap = {"1": "a", "2": "k"}
        r.labels = {"1": "A", "2": "K"}
        r.title = "LED"
        r.notes.append("Perna longa = anodo (A).")
        return r
    if kind == "lamp":
        r.package = "lampada"
        r.pinmap = {"1": "1", "2": "2"}
        r.labels = {"1": "1", "2": "2"}
        r.title = f"Lâmpada {_value_label(comp, 'vn', 'V')} {_value_label(comp, 'pn', 'W')}"
        return r
    if kind in _GENERIC_3:
        pid, roles, title = _GENERIC_3[kind]
        r.package = pid
        r.pinmap = {str(i + 1): role for i, role in enumerate(roles)}
        r.labels = {str(i + 1): _LABEL[role] for i, role in enumerate(roles)}
        r.title = title
        r.notes.append(GENERIC_NOTE)
        return r
    if kind == "opamp":
        r.package = "dip-8"
        r.pinmap = {"2": "inn", "3": "inp", "6": "out", "7": "vcc", "4": "vee"}
        r.labels = {
            "1": "—",
            "2": "IN−",
            "3": "IN+",
            "4": "V−",
            "5": "—",
            "6": "OUT",
            "7": "V+",
            "8": "—",
        }
        r.title = "AMPOP"
        r.notes.append(GENERIC_NOTE)
        _supplies(comp, r)
        return r
    r.origin = "sem_montagem"
    r.notes.append(f"Sem encapsulamento definido para {kind}.")
    return r


def _supplies(comp: Component, r: Resolved) -> None:
    for name in ("vcc", "vee"):
        if name in r.pinmap.values():
            v = try_parse(param(comp, name))
            r.supplies[name] = v if v is not None else 0.0


def resolve(comp: Component, record: ComponentRecord | None) -> Resolved:
    if comp.kind == "ground":
        return Resolved(comp.ref, comp.kind, None, "sem_montagem")
    if record is None:
        return _generic(comp)
    r = Resolved(comp.ref, comp.kind, None, "sem_pinagem", part_number=record.part_number)
    r.title = record.part_number
    po = record.pinout
    if po is not None and po.status == "a_verificar":
        r.package = po.package if po.package in PACKAGES else _generic(comp).package
        r.status = po.status
        r.notes.append(
            f"{record.part_number}: pinagem marcada como a verificar. "
            "As pernas ficam sem ligação automática e fora da conferência; "
            "confirme a pinagem no datasheet antes de montar."
        )
        return r
    if po is None or po.package not in PACKAGES:
        base = _generic(comp)
        r.package = base.package
        r.notes.append(
            f"{record.part_number}: pinagem ainda não transcrita do datasheet. A peça aparece na "
            "protoboard sem rótulos nas pernas e fica fora da conferência (regra 1: não se supõe "
            "pinagem)."
            if po is None
            else f"{record.part_number}: encapsulamento {po.package!r} não desenhado ainda."
        )
        return r
    r.origin = "datasheet"
    r.package = po.package
    r.source = po.source
    r.datasheet = next((d for d in record.datasheets if d.id == po.source.datasheet_id), None)
    r.status = po.status
    used_unit = next((p.unit for p in po.pins if p.unit), None)
    for p in po.pins:
        r.labels[p.pin] = p.name
        if p.role and (p.unit is None or p.unit == used_unit):
            r.pinmap[p.pin] = p.role
    if po.note:
        r.notes.append(po.note)
    if used_unit and any(p.unit and p.unit != used_unit for p in po.pins):
        r.notes.append(
            f"Integrado com mais de uma unidade: este componente usa a unidade {used_unit}; as "
            "demais ficam livres (boa prática: entrada não inversora no terra e saída ligada à "
            "entrada inversora)."
        )
    if po.status != "revisado":
        r.notes.append("Pinagem transcrita do datasheet, ainda não revisada por você.")
    _supplies(comp, r)
    return r
