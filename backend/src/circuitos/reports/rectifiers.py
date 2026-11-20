"""Outputs of the rectifier modules: schematic, bill of materials, lab guide items."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from circuitos.design.base import DesignResult
from circuitos.design.plugins.ret1 import Ret1Spec
from circuitos.design.plugins.ret3 import Ret3Spec
from circuitos.design.plugins.retc1 import Retc1Spec

from . import schematic
from .common import BomRow, LabItem, bom_csv, eng, role_rows

__all__ = ["LAB", "SAFETY", "BomRow", "bom", "bom_csv", "schematic_svg"]


def _summary(result: DesignResult, spec: BaseModel) -> dict[str, tuple[float, str]]:
    out = {k: (q.value, q.unit) for k, q in result.summary.items()}
    for key in ("Vin", "R", "E", "Ls"):
        v = getattr(spec, key, None)
        if v is not None:
            out.setdefault(key, (v.value, v.unit))
    if isinstance(spec, Retc1Spec):
        out["L_load"] = (spec.L.to_pint().m_as("mH"), "mH")
    if isinstance(spec, Ret1Spec | Retc1Spec) and "R_load" in result.summary:
        q = result.summary["R_load"]
        out["R"] = (q.value, q.unit)
    return out


def _parts(result: DesignResult) -> dict[str, str]:
    return {c.designator: c.part_number for c in result.selection}


def schematic_svg(spec: BaseModel, result: DesignResult, title: str) -> str:
    summ = _summary(result, spec)
    parts = _parts(result)
    if isinstance(spec, Ret3Spec):
        role = result.roles[0]
        return schematic.three_phase(
            spec.pulses,
            "scr" if spec.controlled else "diode",
            role.designator,
            parts.get(role.designator, ""),
            summ,
            title,
        )
    if isinstance(spec, Ret1Spec):
        role = result.roles[0]
        part = parts.get(role.designator, "")
        n = role.count
        devs = {f"D{i}": ("diode", f"D{i}", part if i == 1 else "") for i in range(1, n + 1)}
        return schematic.single_phase(spec.topology, devs, spec.filter, "R", summ, title)
    if isinstance(spec, Retc1Spec):
        t_role = result.roles[0]
        t_part = parts.get(t_role.designator, "")
        d_role = result.roles[1] if len(result.roles) > 1 else None
        d_part = parts.get(d_role.designator, "") if d_role else ""
        if spec.topology == "ponte":
            # drawing positions: leg a = D1 (a→P) and D3 (N→a); leg b = D2 (b→P) and D4 (N→b)
            devs = {
                "D1": ("scr", "T1", t_part),
                "D3": ("scr", "T4", ""),
                "D2": ("scr", "T3", ""),
                "D4": ("scr", "T2", ""),
            }
        elif spec.topology == "semicontrolada":
            devs = {
                "D1": ("scr", "T1", t_part),
                "D2": ("scr", "T2", ""),
                "D3": ("diode", "D1", d_part),
                "D4": ("diode", "D2", ""),
            }
        else:
            devs = {"D1": ("scr", "T1", t_part), "DRL": ("diode", "D1", d_part)}
        load = "RLE" if spec.E.value > 0 else ("RL" if spec.L.value > 0 else "R")
        topo = "meia_onda" if spec.topology == "meia_onda" else "ponte"
        return schematic.single_phase(
            topo, devs, "nenhum", load, summ, title, freewheel=spec.freewheel
        )
    raise TypeError("Sem esquemático para esta especificação")


_eng = eng


def bom(spec: BaseModel, result: DesignResult) -> list[BomRow]:
    rows = role_rows(result)
    s = result.summary
    vc = s.get("VC_max")
    if "C" in s:
        rows.append(
            BomRow(
                "C1",
                1,
                "Capacitor eletrolítico de filtro",
                "(a escolher)",
                "",
                _eng(s["C"].value, "µF"),
                f"tensão ≥ {_eng(vc.value * 1.25, 'V')} (25 % acima do pico); "
                f"ondulação ≥ {_eng(s['IC_rms'].value, 'A')} ef."
                if vc and "IC_rms" in s
                else "",
            )
        )
    if "C2" in s:
        rows.append(
            BomRow(
                "C2",
                1,
                "Capacitor eletrolítico de filtro",
                "(a escolher)",
                "",
                _eng(s["C2"].value, "µF"),
                "",
            )
        )
    if "L" in s:
        rows.append(
            BomRow(
                "L1",
                1,
                "Indutor de filtro",
                "(a projetar)",
                "",
                _eng(s["L"].value, "mH"),
                f"corrente média {_eng(s['Io'].value, 'A')}",
            )
        )
    va = s.get("VA_sec") or s.get("VA_pri")
    if va is not None:
        if isinstance(spec, Ret3Spec):
            desc = "Transformador trifásico" + (" Δ/Y-Δ" if spec.pulses == 12 else "")
            val = f"{_eng(spec.Vin.value, 'V')} / {_eng(s['Vll_sec'].value, 'V')} de linha"
        else:
            vsec = s["Vsec"].value
            assert isinstance(spec, Ret1Spec | Retc1Spec)
            ct = isinstance(spec, Ret1Spec) and spec.topology == "center_tap"
            desc = "Transformador" + (" com derivação central" if ct else "")
            val = f"{_eng(spec.Vin.value, 'V')} / {_eng(vsec, 'V')}" + (
                " + " + _eng(vsec, "V") if ct else ""
            )
        rows.append(
            BomRow("TR1", 1, desc, "(a especificar)", "", val, f"S ≥ {_eng(va.value, 'VA')}")
        )
    return rows


LAB: Mapping[str, list[LabItem]] = {
    "DM-RET1": [
        LabItem("Tensão média na carga", "multímetro em CC", "Vo"),
        LabItem("Ondulação de pico a pico", "osciloscópio, acoplamento CA", "dVo"),
        LabItem("Tensão eficaz do secundário", "multímetro true RMS", "Vsec"),
        LabItem("Corrente de pico no diodo", "osciloscópio com ponteira de corrente", "ID_pk"),
        LabItem("Fator de potência na entrada", "analisador de energia", "PF"),
    ],
    "DM-RETC1": [
        LabItem("Tensão média na carga", "multímetro em CC", "Vo"),
        LabItem("Corrente média na carga", "alicate CC ou shunt", "Io"),
        LabItem("Ângulo de extinção β", "osciloscópio (corrente na carga)", "beta"),
        LabItem("Corrente eficaz do secundário", "alicate true RMS", "Isec"),
        LabItem("Fator de potência na entrada", "analisador de energia", "PF"),
    ],
    "DM-RET3": [
        LabItem("Tensão média na saída", "multímetro em CC", "Vo"),
        LabItem("Ângulo de comutação μ", "osciloscópio (tensão de saída, entalhes)", "mu"),
        LabItem("Corrente de linha eficaz", "alicate true RMS", "I_line"),
        LabItem("THD da corrente de linha", "analisador de energia", "THD_i"),
        LabItem("Fator de potência", "analisador de energia", "PF"),
    ],
}

SAFETY = [
    "Montagem ligada à rede: use transformador isolador e bancada com disjuntor e DR.",
    "A referência do osciloscópio é o terra da rede: meça tensões flutuantes com ponteira "
    "diferencial, nunca com a garra de terra em um nó do circuito.",
    "Capacitores de filtro mantêm carga após desligar: descarregue por resistor antes de tocar.",
    "Dispositivos e dissipadores aquecem: confira a temperatura antes de manusear.",
]
