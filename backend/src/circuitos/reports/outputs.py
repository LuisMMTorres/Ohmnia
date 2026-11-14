"""Outputs of a design module, whatever its family: schematic, BOM, labels, lab guide.

The rectifier modules of phase 3 keep their outputs in :mod:`rectifiers` and the labels in
:mod:`report`; newer modules carry them as attributes (``labels``, ``spec_labels``,
``enum_labels``, ``lab``, ``questions``, ``safety``) and methods (``schematic``, ``bom_extra``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from circuitos.design.base import DesignResult

from . import rectifiers
from .common import BENCH_SAFETY, BomRow, LabItem, role_rows
from .labels import ENUM_LABELS, LABELS, SPEC_LABELS

RECTIFIERS = {"DM-RET1", "DM-RETC1", "DM-RET3"}


def schematic_svg(module: Any, spec: BaseModel, result: DesignResult, title: str) -> str:
    if module.id in RECTIFIERS:
        return rectifiers.schematic_svg(spec, result, title)
    svg: str = module.schematic(spec, result, title)
    return svg


def bom(module: Any, spec: BaseModel, result: DesignResult) -> list[BomRow]:
    if module.id in RECTIFIERS:
        return rectifiers.bom(spec, result)
    rows: list[BomRow] = role_rows(result) + list(module.bom_extra(spec, result))
    return rows


def labels(module: Any) -> dict[str, str]:
    return {**LABELS, **getattr(module, "labels", {})}


def spec_labels(module: Any) -> dict[str, str]:
    return {**SPEC_LABELS, **getattr(module, "spec_labels", {})}


def enum_labels(module: Any) -> dict[str, str]:
    return {**ENUM_LABELS, **getattr(module, "enum_labels", {})}


def lab(module: Any) -> list[LabItem]:
    if module.id in RECTIFIERS:
        return rectifiers.LAB.get(module.id, [])
    items: list[LabItem] = getattr(module, "lab", [])
    return items


def safety(module: Any) -> list[str]:
    if module.id in RECTIFIERS:
        return rectifiers.SAFETY
    items: list[str] = getattr(module, "safety", BENCH_SAFETY)
    return items


def questions(module: Any) -> list[str]:
    items: list[str] = getattr(module, "questions", [])
    return items
