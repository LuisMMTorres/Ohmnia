"""Packages drawn on the breadboard: leg count, spacing on the 0.1" grid and drawing style.

A package says how its legs sit on the board, not what each leg does: the meaning of each leg
(pinout) comes from the part's datasheet (``ComponentRecord.pinout``) or, for a generic part of
the simulator, from the didactic default in :mod:`circuitos.breadboard.pinout`.

Spacing is given in breadboard holes (0.1" = 2.54 mm). Packages whose real pitch is not a
multiple of 0.1" (TO-247 at 5.45 mm, GBU at 5.0 mm) are placed with legs bent to the nearest
hole count, as is done on a real breadboard; the drawing says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Style = Literal["axial", "radial", "inline", "dip", "board", "offboard"]


@dataclass(frozen=True)
class Package:
    id: str
    label: str
    style: Style
    pins: tuple[str, ...]  # package pin numbers (or terminal names, off-board), in leg order
    pitch: int = 1  # holes between consecutive legs (inline, radial, DIP along a side)
    span: int = 0  # axial: default distance between the two legs, in holes
    min_span: int = 0  # axial: shortest bend that fits the body
    body: str = (
        ""  # drawing hint: "resistor", "diode", "glass", "ceramic", "electrolytic", "to92"...
    )
    note: str = ""
    extra: dict[str, str] = field(default_factory=dict)
    # DIP and board: (lower, upper) columns of the two rows of legs; leg 1 is in the lower one
    cols: tuple[str, str] = ("f", "e")
    offsets: tuple[tuple[int, int], ...] = ()  # board: explicit (row, column) offsets
    silk: tuple[str, ...] = ()  # board: label printed next to each leg, in leg order

    def leg_offsets(self) -> list[tuple[int, int]]:
        """Default (row, column) offsets of each leg from leg 1, before any rotation.

        Rows grow to the right; the column offset is in board columns (a→b = +1). DIP legs:
        pins 1..n/2 along the lower side (column f), the others back along the upper side
        (column e), as seen from above with the notch to the left.
        """
        n = len(self.pins)
        if self.offsets:
            return list(self.offsets)
        if self.style == "dip":
            half = n // 2
            low = [(i * self.pitch, 0) for i in range(half)]
            up = [((half - 1 - i) * self.pitch, -1) for i in range(half)]
            return low + up  # column offset -1: from f to e (across the channel)
        if self.style == "axial":
            return [(0, 0), (self.span, 0)]
        return [(i * self.pitch, 0) for i in range(n)]


def _dip(n: int) -> Package:
    return Package(
        f"dip-{n}",
        f"DIP-{n}",
        "dip",
        tuple(str(i) for i in range(1, n + 1)),
        body="dip",
        note="Encaixa sobre a canaleta central (pinos nas colunas e e f).",
    )


def _board(
    pid: str, label: str, lower: list[str | None], upper: list[str | None], start: int, note: str
) -> Package:
    """Development board with two rows of header pins, placed over the channel like a DIP.

    ``lower`` and ``upper`` are the pins of each header from left to right as seen from above
    (``None``: a gap of one hole between groups of pins). Legs are numbered as in a DIP: 1 at the
    left of the lower row, then back along the upper row; ``start`` is the row offset of the
    leftmost upper hole from leg 1.
    """
    legs: list[tuple[int, int]] = []
    silk: list[str] = []
    for i, name in enumerate(lower):
        if name is not None:
            legs.append((i, 0))
            silk.append(name)
    for i, name in reversed(list(enumerate(upper))):
        if name is not None:
            legs.append((start + i, -1))
            silk.append(name)
    return Package(
        pid,
        label,
        "board",
        tuple(str(i) for i in range(1, len(legs) + 1)),
        body=pid,
        note=note,
        cols=("h", "c"),
        offsets=tuple(legs),
        silk=tuple(silk),
    )


# Header order from the boards' published pinouts, top view (to be confirmed by the user, as
# every generic drawing: see docs/validacao/protoboard.md). The real pitch between some groups
# of the Uno headers is not a multiple of 0.1"; here each group is one hole apart.
UNO_LOWER: list[str | None] = [
    "NC", "IOREF", "RESET", "3V3", "5V", "GND", "GND", "VIN", None,
    "A0", "A1", "A2", "A3", "A4", "A5",
]  # fmt: skip
UNO_UPPER: list[str | None] = [
    "SCL", "SDA", "AREF", "GND", "D13", "D12", "D11", "D10", "D9", "D8", None,
    "D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0",
]  # fmt: skip
ESP32_LOWER: list[str | None] = [
    "3V3", "EN", "IO36", "IO39", "IO34", "IO35", "IO32", "IO33", "IO25", "IO26",
    "IO27", "IO14", "IO12", "GND", "IO13", "IO9", "IO10", "IO11", "5V",
]  # fmt: skip
ESP32_UPPER: list[str | None] = [
    "GND", "IO23", "IO22", "IO1", "IO3", "IO21", "GND", "IO19", "IO18", "IO5",
    "IO17", "IO16", "IO4", "IO0", "IO2", "IO15", "IO8", "IO7", "IO6",
]  # fmt: skip


def _offboard(pid: str, label: str, terminals: tuple[str, ...], body: str, note: str) -> Package:
    return Package(pid, label, "offboard", terminals, body=body, note=note)


PACKAGES: dict[str, Package] = {
    p.id: p
    for p in (
        Package(
            "axial-r",
            "Resistor axial (1/4 W)",
            "axial",
            ("1", "2"),
            span=4,
            min_span=3,
            body="resistor",
        ),
        Package(
            "axial-r-1w",
            "Resistor axial (1 W)",
            "axial",
            ("1", "2"),
            span=6,
            min_span=5,
            body="resistor",
        ),
        Package(
            "axial-l", "Indutor axial", "axial", ("1", "2"), span=4, min_span=3, body="inductor"
        ),
        Package(
            "do-35",
            "DO-35 (vidro)",
            "axial",
            ("1", "2"),
            span=4,
            min_span=3,
            body="glass",
            note="Faixa no catodo.",
        ),
        Package(
            "do-41",
            "DO-41",
            "axial",
            ("1", "2"),
            span=4,
            min_span=3,
            body="diode",
            note="Faixa no catodo.",
        ),
        Package(
            "do-201ad",
            "DO-201AD",
            "axial",
            ("1", "2"),
            span=6,
            min_span=5,
            body="diode",
            note="Faixa no catodo; perna grossa (1,3 mm), entra com folga apertada.",
        ),
        Package("radial-cer", "Capacitor cerâmico", "radial", ("1", "2"), pitch=1, body="ceramic"),
        Package("radial-film", "Capacitor de filme", "radial", ("1", "2"), pitch=2, body="film"),
        Package(
            "radial-elco",
            "Capacitor eletrolítico radial",
            "radial",
            ("+", "-"),
            pitch=1,
            body="electrolytic",
            note="Polarizado: a perna + vai ao nó de maior tensão.",
        ),
        Package("radial-l", "Indutor radial", "radial", ("1", "2"), pitch=2, body="inductor"),
        Package(
            "to-92",
            "TO-92",
            "inline",
            ("1", "2", "3"),
            pitch=1,
            body="to92",
            note="Face plana para a frente; pinos numerados da esquerda para a direita.",
        ),
        Package(
            "to-126",
            "TO-126 / TO-225",
            "inline",
            ("1", "2", "3"),
            pitch=1,
            body="to126",
            note="Face com a marcação para a frente.",
        ),
        Package(
            "to-220",
            "TO-220",
            "inline",
            ("1", "2", "3"),
            pitch=1,
            body="to220",
            note="Face com a marcação para a frente, aleta para trás.",
        ),
        Package(
            "to-220-2",
            "TO-220 (2 terminais)",
            "inline",
            ("1", "3"),
            pitch=2,
            body="to220",
            note="Dois terminais nas posições 1 e 3.",
        ),
        Package(
            "to-247",
            "TO-247",
            "inline",
            ("1", "2", "3"),
            pitch=2,
            body="to247",
            note="Passo real de 5,45 mm: pernas abertas para dois furos.",
        ),
        Package(
            "sip-4",
            "Ponte em linha (GBU/KBP)",
            "inline",
            ("1", "2", "3", "4"),
            pitch=2,
            body="sip",
            note="Passo real de 5 mm: pernas abertas para dois furos.",
        ),
        _dip(4),
        _dip(8),
        _dip(14),
        _dip(16),
        _offboard(
            "fonte-cc",
            "Fonte de bancada CC",
            ("p", "n"),
            "supply",
            "Fora da placa: ligue com cabos e garras jacaré.",
        ),
        _offboard(
            "gerador",
            "Gerador de funções",
            ("p", "n"),
            "generator",
            "Fora da placa: ponta (sinal) e garra (terra).",
        ),
        _offboard(
            "fonte-i",
            "Fonte de corrente",
            ("p", "n"),
            "supply",
            "Fora da placa: a corrente sai pelo terminal n (convenção SPICE).",
        ),
        _offboard(
            "trifasica",
            "Fonte trifásica",
            ("a", "b", "c", "n"),
            "supply",
            "Fora da placa. Atenção: tensão de rede só com bancada protegida.",
        ),
        _offboard(
            "trafo",
            "Transformador",
            ("p1", "p2", "s1", "s2"),
            "transformer",
            "Fora da placa: só o secundário vem para a protoboard.",
        ),
        _offboard("carga", "Carga externa", ("1", "2"), "load", "Fora da placa."),
        _offboard(
            "alim",
            "Fonte simétrica de bancada",
            ("+", "-", "0"),
            "supply",
            "Alimentação dos integrados (V+ e V-), implícita no esquemático.",
        ),
        _board(
            "board-uno",
            "Arduino Uno R3 (barras de pinos)",
            UNO_LOWER,
            UNO_UPPER,
            -3,
            "Montagem didática: a placa real não encaixa na protoboard (ligue com jumpers "
            "macho-fêmea). Pino 1 = primeiro pino da barra de alimentação (NC), na coluna h.",
        ),
        _board(
            "board-esp32",
            "ESP32-DevKitC (38 pinos)",
            ESP32_LOWER,
            ESP32_UPPER,
            0,
            "Encaixa sobre a canaleta, como um DIP largo (fileiras nas colunas c e h; confira o "
            "espaçamento da sua placa). Pino 1 = 3V3, na coluna h.",
        ),
        Package(
            "pot-3",
            "Potenciômetro (3 terminais)",
            "inline",
            ("1", "2", "3"),
            pitch=2,
            body="pot",
            note="Cursor no terminal do meio.",
        ),
    )
}
# Fase 11: boards, PLC, modules and plants stay off the board, wired by their terminals
from circuitos.schematic.cosim_symbols import COSIM_SYMBOLS  # noqa: E402

for _s in COSIM_SYMBOLS:
    if _s.kind not in ("lm35", "potentiometer"):
        PACKAGES[f"mod-{_s.kind}"] = _offboard(
            f"mod-{_s.kind}", _s.label, tuple(pin.name for pin in _s.pins), "module",
            "Fora da placa: ligue cada terminal por fio ao furo indicado.",
        )  # fmt: skip


def package(pid: str) -> Package:
    try:
        return PACKAGES[pid]
    except KeyError as exc:
        raise ValueError(f"Encapsulamento desconhecido: {pid!r}") from exc


def spec() -> list[dict[str, object]]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "style": p.style,
            "pins": list(p.pins),
            "pitch": p.pitch,
            "span": p.span,
            "min_span": p.min_span,
            "body": p.body,
            "note": p.note,
            "offsets": p.leg_offsets(),
            "cols": list(p.cols),
            "silk": list(p.silk),
        }
        for p in PACKAGES.values()
    ]
