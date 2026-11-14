"""Two-step design engine shared by every topology module.

1. Ideal pass: the module computes the stresses with ideal devices.
2. Selection: for each role, the released catalogue parts that meet the derating policy are
   ranked (``selection/``); a part locked by the user always wins.
3. Real pass: the module recomputes with the forward drop of the chosen parts, iterating until
   the headline results change less than the convergence criterion (default 0,1 %, at most 50
   iterations). Not converging is an explicit error, never a silent result.
4. Margins and junction temperatures of the chosen parts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import pint
from pydantic import BaseModel

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.core.calc import CalcLog, CalcStep, record
from circuitos.core.errors import CircuitosError
from circuitos.core.units import Q_, QuantityModel, parse_unit
from circuitos.selection.derating import DeratingPolicy
from circuitos.selection.select import check, rank
from circuitos.thermal.steady import junction_temperature, required_heatsink

from .base import (
    Choice,
    Circuit,
    DesignResult,
    DesignWarning,
    MarginCheck,
    Role,
    Stress,
    ThermalResult,
)


class ConvergenceError(CircuitosError):
    pass


@dataclass(frozen=True)
class Device:
    """What the analytic model uses from a chosen part."""

    record: ComponentRecord | None
    drop: pint.Quantity  # forward / on-state voltage used as a constant drop


@dataclass
class Analysis:
    log: CalcLog
    stresses: list[Stress]
    summary: dict[str, pint.Quantity]
    losses: dict[str, pint.Quantity]  # designator → power of ONE device of the role
    warnings: list[DesignWarning] = field(default_factory=list)
    convergence_keys: Sequence[str] = ()


class TopologyModule(Protocol):
    id: str
    family: str
    title: str
    spec_schema: type[BaseModel]

    def roles(self, spec: BaseModel) -> list[Role]: ...

    def required_ratings(self, role: Role) -> list[str]: ...

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis: ...

    def build_circuit(
        self,
        spec: BaseModel,
        devices: Mapping[str, Device],
        summary: Mapping[str, QuantityModel],
    ) -> Circuit: ...

    def ambient(self, spec: BaseModel) -> pint.Quantity: ...

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity: ...


Catalogue = Callable[[str], list[ComponentRecord]]
Lookup = Callable[[UUID], ComponentRecord]

DROP_KEYS = {"diode": "VF", "bridge": "VF", "thyristor": "VTM"}


def _value(p: Parameter) -> float:
    for v in (p.max, p.typ, p.min):
        if v is not None:
            return v
    raise ValueError(p.symbol)


def device_for(role: Role, rec: ComponentRecord | None, log: CalcLog | None) -> Device:
    if rec is None:
        return Device(record=None, drop=Q_(0.0, "V"))
    key = DROP_KEYS.get(rec.category.split(".", 1)[0])
    p = rec.parameters.get(key) if key else None
    if p is None or not p.has_value:
        return Device(record=rec, drop=Q_(0.0, "V"))
    drop = Q_(_value(p), parse_unit(p.unit)).to("V")
    if log is not None:
        log.add(
            record(
                f"drop_{role.designator}",
                f"Queda em condução de {role.designator} ({rec.part_number})",
                r"V_F = V_{F,ds}" if key == "VF" else r"V_T = V_{TM,ds}",
                output=drop,
                inputs={k: c.to_pint() for k, c in p.conditions.items()},
                assumptions=[
                    "queda constante igual ao valor máximo do datasheet no ponto de ensaio "
                    "(conservador abaixo dessa corrente)"
                ],
            )
        )
    return Device(record=rec, drop=drop)


def _role_stresses(stresses: Sequence[Stress], role: Role) -> list[Stress]:
    return [s for s in stresses if s.designator == role.designator]


def run(
    module: TopologyModule,
    spec: BaseModel,
    catalogue: Catalogue,
    lookup: Lookup,
    policy: DeratingPolicy,
    locks: Mapping[str, UUID] | None = None,
    tolerance: float = 1e-3,
    max_iterations: int = 50,
) -> tuple[DesignResult, dict[str, Device]]:
    locks = dict(locks or {})
    roles = module.roles(spec)
    ideal = module.analyse(spec, {r.designator: device_for(r, None, None) for r in roles})
    choices: dict[str, Choice] = {}
    chosen: dict[str, ComponentRecord | None] = {}
    candidates: dict[str, list[str]] = {}
    lock_warnings: list[DesignWarning] = []
    for role in roles:
        if role.designator not in locks:
            continue
        rec = lookup(locks[role.designator])
        if not rec.category.startswith(role.category.split(".", 1)[0]):
            raise CircuitosError(
                f"{rec.part_number} ({rec.category}) não serve para {role.designator}"
            )
        chosen[role.designator] = rec
        choices[role.designator] = _choice(role, rec, locked=True)
        if not rec.selectable:
            lock_warnings.append(
                DesignWarning(
                    code="nao_revisado",
                    message=f"{role.designator}: {rec.part_number} foi travado à mão, mas "
                    "ainda não foi liberado na revisão; os valores do datasheet não foram "
                    "conferidos.",
                )
            )

    # Selection uses the ideal stresses first. The real pass can raise them (the forward drop
    # of the chosen part asks for a higher secondary voltage); a part that then misses its
    # margin is reselected with the larger stresses, a few rounds at most.
    basis: dict[str, list[Stress]] = {
        r.designator: _role_stresses(ideal.stresses, r) for r in roles
    }
    analysis = ideal
    devices: dict[str, Device] = {}
    iteration = 0
    for _round in range(5):
        select_warnings: list[DesignWarning] = []
        for role in roles:
            if role.designator in locks:
                continue
            ranked = rank(
                catalogue(role.category),
                basis[role.designator],
                policy,
                module.required_ratings(role),
            )
            candidates[role.designator] = [r.record.part_number for r in ranked[:10]]
            if ranked:
                chosen[role.designator] = ranked[0].record
                choices[role.designator] = _choice(role, ranked[0].record, locked=False)
            else:
                chosen[role.designator] = None
                choices.pop(role.designator, None)
                select_warnings.append(
                    DesignWarning(
                        code="sem_candidato",
                        message=f"{role.designator}: nenhum componente liberado de {role.category} "
                        "atende às margens. Libere componentes na tela Componentes ou trave um "
                        "componente à mão. O cálculo seguiu com dispositivo ideal.",
                    )
                )
        analysis, devices, iteration = _real_pass(
            module, spec, roles, chosen, tolerance, max_iterations
        )
        reselect = False
        for role in roles:
            part = chosen[role.designator]
            if role.designator in locks or part is None:
                continue
            real = _role_stresses(analysis.stresses, role)
            if any(c.status != "ok" for c in check(part, real, policy)):
                basis[role.designator] = _envelope(basis[role.designator], real)
                reselect = True
        if not reselect:
            break
    warnings = lock_warnings + select_warnings

    margins: list[MarginCheck] = []
    thermal: list[ThermalResult] = []
    TA = module.ambient(spec)
    for role in roles:
        part = chosen[role.designator]
        if part is None:
            continue
        role_margins = check(part, _role_stresses(analysis.stresses, role), policy)
        margins += role_margins
        if any(m.status == "violado" for m in role_margins):
            warnings.append(
                DesignWarning(
                    code="margem_violada",
                    message=f"{role.designator}: {part.part_number} não suporta os esforços "
                    "calculados.",
                )
            )
        power = analysis.losses.get(role.designator)
        if power is not None:
            result = _thermal(role, part, power, TA, policy, module.interface_resistance(spec))
            if result is not None:
                thermal_result, steps = result
                thermal.append(thermal_result)
                for s in steps:
                    analysis.log.add_step(s)
            else:
                warnings.append(
                    DesignWarning(
                        code="sem_dados_termicos",
                        message=f"{role.designator}: o datasheet de {part.part_number} não tem "
                        "Rθja nem Tj máx.; a temperatura de junção não foi calculada.",
                    )
                )

    return (
        DesignResult(
            module_id=module.id,
            steps=list(analysis.log),
            stresses=analysis.stresses,
            roles=roles,
            selection=list(choices.values()),
            candidates=candidates,
            margins=margins,
            thermal=thermal,
            summary={k: QuantityModel.from_pint(v) for k, v in analysis.summary.items()},
            iterations=iteration,
            converged=True,
            warnings=warnings + analysis.warnings,
        ),
        devices,
    )


def _envelope(a: Sequence[Stress], b: Sequence[Stress]) -> list[Stress]:
    """Per rating key, the larger of two stress lists."""
    out: dict[str, Stress] = {st.key: st for st in a}
    for st in b:
        cur = out.get(st.key)
        if cur is None or abs(st.value.to_pint().m_as(cur.value.unit)) > abs(cur.value.value):
            out[st.key] = st
    return list(out.values())


def _real_pass(
    module: TopologyModule,
    spec: BaseModel,
    roles: Sequence[Role],
    chosen: Mapping[str, ComponentRecord | None],
    tolerance: float,
    max_iterations: int,
) -> tuple[Analysis, dict[str, Device], int]:
    """Recompute with the chosen parts until the convergence keys settle."""
    previous: dict[str, float] | None = None
    for iteration in range(1, max_iterations + 1):
        log = CalcLog()
        devices = {r.designator: device_for(r, chosen[r.designator], log) for r in roles}
        analysis = module.analyse(spec, devices)
        for step in analysis.log:
            log.add_step(step)
        analysis.log = log
        current = {k: float(analysis.summary[k].magnitude) for k in analysis.convergence_keys}
        if previous is not None and all(
            abs(current[k] - previous[k]) <= tolerance * max(abs(previous[k]), 1e-30)
            for k in current
        ):
            return analysis, devices, iteration
        previous = current
    raise ConvergenceError(
        f"O cálculo não convergiu em {max_iterations} iterações (critério {tolerance:.1%})"
    )


def _choice(role: Role, part: ComponentRecord, locked: bool) -> Choice:
    return Choice(
        designator=role.designator,
        component_id=part.id,
        part_number=part.part_number,
        manufacturer=part.manufacturer,
        locked=locked,
        released=part.selectable,
    )


def _thermal(
    role: Role,
    part: ComponentRecord,
    power: pint.Quantity,
    TA: pint.Quantity,
    policy: DeratingPolicy,
    rth_cs: pint.Quantity,
) -> tuple[ThermalResult, list[CalcStep]] | None:
    p_ja = part.parameters.get("Rth_ja")
    p_tj = part.parameters.get("Tj_max")
    if p_ja is None or not p_ja.has_value or p_tj is None or not p_tj.has_value:
        return None
    rth_ja = Q_(_value(p_ja), parse_unit(p_ja.unit)).to("K/W")
    tj_max = Q_(_value(p_tj), parse_unit(p_tj.unit))
    tj = junction_temperature(role.designator, power, TA, rth_ja)
    steps = [tj.step]
    headroom = tj_max.to("degC").magnitude - tj.value.to("degC").magnitude
    status = "ok" if headroom >= policy.tj_margin_K else "atencao" if headroom >= 0 else "violado"
    required = None
    p_jc = part.parameters.get("Rth_jc")
    if status != "ok" and p_jc is not None and p_jc.has_value:
        rsa = required_heatsink(
            role.designator,
            power,
            TA,
            tj_max,
            policy.tj_margin_K,
            Q_(_value(p_jc), parse_unit(p_jc.unit)).to("K/W"),
            rth_cs,
        )
        steps.append(rsa.step)
        required = QuantityModel.from_pint(rsa.value)
    return (
        ThermalResult(
            designator=role.designator,
            power=QuantityModel.from_pint(power.to("W")),
            Tj=QuantityModel.from_pint(tj.value),
            Tj_max=QuantityModel.from_pint(tj_max.to("degC")),
            path="sem dissipador (Rθja do datasheet)",
            required_Rsa=required,
            status=status,
        ),
        steps,
    )
