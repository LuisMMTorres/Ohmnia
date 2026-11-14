"""Building blocks shared by the outputs of every design module (BOM rows, lab items)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from circuitos.core.units import Q_, format_eng
from circuitos.design.base import DesignResult


@dataclass
class BomRow:
    designator: str
    quantity: int
    description: str
    part_number: str
    manufacturer: str
    value: str
    note: str


@dataclass
class LabItem:
    quantity: str
    instrument: str
    summary_key: str


def eng(v: float, unit: str) -> str:
    try:
        return format_eng(Q_(v, unit.replace("µ", "u").replace("VA", "V*A")))
    except Exception:  # units pint does not parse as written: plain text
        return f"{v:.3g} {unit}".replace(".", ",")


def role_rows(result: DesignResult) -> list[BomRow]:
    """One row per catalogue role, plus the heat sink of each role that needs one."""
    rows: list[BomRow] = []
    chosen = {c.designator: c for c in result.selection}
    for role in result.roles:
        c = chosen.get(role.designator)
        rows.append(
            BomRow(
                designator=role.designator,
                quantity=role.count,
                description=role.description,
                part_number=c.part_number if c else "(sem candidato liberado)",
                manufacturer=c.manufacturer if c else "",
                value="",
                note=("travado à mão" if c and c.locked else "seleção automática")
                + ("" if not c or c.released else "; NÃO REVISADO"),
            )
        )
    th = {t.designator: t for t in result.thermal}
    for role in result.roles:
        t = th.get(role.designator)
        if t and t.heatsink is not None:
            rows.append(
                BomRow(
                    designator=f"HS ({role.designator})",
                    quantity=role.count,
                    description="Dissipador, perfil extrudado, 101,6 mm (um por dispositivo)",
                    part_number=t.heatsink,
                    manufacturer=t.heatsink_manufacturer or "",
                    value=f"Rθsa ≈ {eng(t.heatsink_Rsa.value, 'K/W')}" if t.heatsink_Rsa else "",
                    note=f"exigido Rθsa ≤ {eng(t.required_Rsa.value, 'K/W')}"
                    if t.required_Rsa
                    else "",
                )
            )
        elif t and t.required_Rsa is not None and t.status != "ok":
            rows.append(
                BomRow(
                    designator=f"HS ({role.designator})",
                    quantity=role.count,
                    description="Dissipador",
                    part_number="(a escolher)",
                    manufacturer="",
                    value=f"Rθsa ≤ {eng(t.required_Rsa.value, 'K/W')}",
                    note="nenhum dissipador liberado do catálogo atende",
                )
            )
    return rows


def passive(
    designator: str, description: str, value: str, note: str = "", quantity: int = 1
) -> BomRow:
    return BomRow(designator, quantity, description, "(a escolher)", "", value, note)


def resistor_row(
    result: DesignResult, designator: str, key: str, power_key: str | None = None
) -> BomRow | None:
    """Resistor row from summary values (E-series value and dissipated power)."""
    s = result.summary
    if key not in s:
        return None
    note = ""
    if power_key and power_key in s:
        p = s[power_key].to_pint().m_as("W")
        rating = next((r for r in (0.125, 0.25, 0.5, 1, 2, 3, 5, 10) if r >= 2 * p), None)
        note = (
            f"P = {eng(p, 'W')}; use ≥ {eng(rating, 'W')} (2 × P)"
            if rating
            else (f"P = {eng(p, 'W')}: resistor de fio com dissipação adequada")
        )
    return passive(designator, "Resistor", format_eng(s[key].to_pint()), note)


def capacitor_row(
    result: DesignResult, designator: str, key: str, description: str, note: str = ""
) -> BomRow | None:
    s = result.summary
    if key not in s:
        return None
    return passive(designator, description, format_eng(s[key].to_pint()), note)


def bom_csv(rows: list[BomRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Designador", "Qtd", "Descrição", "Código", "Fabricante", "Valor", "Observação"])
    for r in rows:
        w.writerow(
            [
                r.designator,
                r.quantity,
                r.description,
                r.part_number,
                r.manufacturer,
                r.value,
                r.note,
            ]
        )
    return buf.getvalue()


BENCH_SAFETY = [
    "Ligue a fonte de bancada com limite de corrente ajustado pouco acima do valor de projeto.",
    "Confira a polaridade de capacitores eletrolíticos e a pinagem dos transistores no "
    "datasheet antes de energizar.",
    "Dispositivos e dissipadores aquecem: confira a temperatura antes de manusear.",
]
