"""Assembly guide: the breadboard layout as numbered steps for the bench (practice sheet)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from circuitos.breadboard import board
from circuitos.breadboard.layout import Breadboard, PlacedPart
from circuitos.breadboard.packages import package
from circuitos.breadboard.reference import ALIM, Reference

_RAIL_NAME = {
    "tp": "barramento + de cima",
    "tn": "barramento − de cima",
    "bn": "barramento − de baixo",
    "bp": "barramento + de baixo",
}


class Step(BaseModel):
    text: str
    refs: list[str] = Field(default_factory=list)
    holes: list[str] = Field(default_factory=list)


def _where(hole: str) -> str:
    col, row = board.parse(hole)
    return f"{_RAIL_NAME[col]} (linha {row})" if col in board.RAILS else hole


def _part_step(ref: Reference, p: PlacedPart) -> Step:
    r = ref.parts.get(p.ref)
    pkg = package(p.package)
    title = (r.title if r else "") or p.ref
    head = f"{p.ref} ({title}, {pkg.label})" if pkg.style != "offboard" else f"{p.ref} ({title})"
    holes = list(p.legs.values())
    labels = r.labels if r else {}
    if pkg.style == "dip":
        text = (
            f"{head}: sobre a canaleta central, chanfro (pino 1) para a esquerda; pino 1 em "
            f"{p.legs.get('1', '?')}."
        )
    elif pkg.style == "offboard":
        terms = ", ".join(f"{labels.get(t, t)} em {_where(h)}" for t, h in p.legs.items())
        text = f"{head}, fora da placa: {terms}."
        if p.ref == ALIM:
            text += " Ajuste as tensões antes de ligar os cabos."
    elif p.package in ("do-41", "do-35", "do-201ad"):
        text = (
            f"{head}: faixa (catodo) em {_where(p.legs.get('1', '?'))}, anodo em "
            f"{_where(p.legs.get('2', '?'))}."
        )
    elif p.package == "radial-elco":
        text = (
            f"{head}: perna + (a mais longa) em {_where(p.legs.get('+', '?'))}, perna − "
            f"(faixa na lateral) em {_where(p.legs.get('-', '?'))}."
        )
    elif pkg.style == "inline":
        legs = ", ".join(
            f"pino {pin}" + (f" ({labels[pin]})" if pin in labels else "") + f" em {h}"
            for pin, h in sorted(p.legs.items())
        )
        text = f"{head}: {legs}. {pkg.note}"
    else:
        ends = " e ".join(_where(h) for h in p.legs.values())
        text = f"{head}: pernas em {ends}."
        if r and r.bands:
            text += f" Faixas: {'-'.join(r.bands)}."
    if r and r.origin == "generico" and pkg.style in ("inline", "dip"):
        text += " Peça genérica: confira a pinagem da peça real."
    return Step(text=text.strip(), refs=[p.ref], holes=holes)


def guide(ref: Reference, bb: Breadboard) -> list[Step]:
    order = {"dip": 0, "inline": 1, "axial": 2, "radial": 2, "offboard": 4}
    steps = [
        Step(
            text="Protoboard de 830 pontos: na mesma linha, os furos a–e estão ligados entre si, "
            "e também os furos f–j; os barramentos correm ao longo da placa."
        )
    ]
    for p in sorted(bb.parts, key=lambda p: (order[package(p.package).style], p.ref)):
        if package(p.package).style != "offboard":
            steps.append(_part_step(ref, p))
    for w in bb.wires:
        steps.append(
            Step(text=f"Fio {w.color} de {_where(w.a)} a {_where(w.b)}.", holes=[w.a, w.b])
        )
    for p in sorted(bb.parts, key=lambda p: p.ref):
        if package(p.package).style == "offboard":
            steps.append(_part_step(ref, p))
    steps.append(
        Step(
            text="Antes de ligar a alimentação: confira a montagem com o esquemático "
            "(botão Conferir) e a polaridade de diodos, eletrolíticos e fontes."
        )
    )
    for i, s in enumerate(steps[1:], start=1):
        s.text = f"{i}. {s.text}"
    return steps
