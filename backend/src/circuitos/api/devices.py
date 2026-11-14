"""Device bench endpoints (BD-DIODO, BD-ZENER)."""

from __future__ import annotations

import uuid

import numpy as np
import pint
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.components.repository import ComponentRepository
from circuitos.core.calc import CalcStep
from circuitos.core.errors import CircuitosError
from circuitos.core.units import Q_, QuantityModel, VectorModel, parse_unit
from circuitos.devices import diode, zener

router = APIRouter(prefix="/api/v1/devices")


class DiodeModelIn(BaseModel):
    Is: QuantityModel = QuantityModel(value=10, unit="nA")
    n: float = Field(default=1.8, gt=0.5, le=5)
    Rs: QuantityModel = QuantityModel(value=0.05, unit="ohm")


class DiodeBenchIn(BaseModel):
    model: DiodeModelIn = DiodeModelIn()
    temperatures: list[QuantityModel] = Field(
        default_factory=lambda: [
            QuantityModel(value=25, unit="degC"),
            QuantityModel(value=100, unit="degC"),
        ],
        min_length=1,
        max_length=6,
    )
    v_min: QuantityModel = QuantityModel(value=0, unit="V")
    v_max: QuantityModel = QuantityModel(value=1.2, unit="V")
    points: int = Field(default=400, ge=20, le=5000)
    component_id: uuid.UUID | None = None


class Marker(BaseModel):
    key: str
    label: str
    v: QuantityModel
    i: QuantityModel
    temperature: QuantityModel | None
    reviewed: bool


class DiodeBenchOut(BaseModel):
    v: VectorModel
    curves: dict[str, VectorModel]
    markers: list[Marker]
    steps: list[CalcStep]
    spice_model: str
    warnings: list[str]


def _datasheet_markers(repo: ComponentRepository, component_id: uuid.UUID) -> list[Marker]:
    record = repo.get(component_id)
    markers = []
    for key, p in record.parameters.items():
        if p.symbol != "VF" or p.max is None or "IF" not in p.conditions:
            continue
        temp = p.conditions.get("Tj") or p.conditions.get("TA")
        markers.append(
            Marker(
                key=key,
                label=f"{record.part_number}: VF máx. @ {p.conditions['IF'].value:g} "
                f"{p.conditions['IF'].unit}" + (f", {temp.value:g} °C" if temp else ""),
                v=QuantityModel(value=Q_(p.max, p.unit).m_as("V"), unit="V"),
                i=QuantityModel(value=p.conditions["IF"].to_pint().m_as("A"), unit="A"),
                temperature=temp,
                reviewed=p.status == "revisado",
            )
        )
    return markers


@router.post("/diode/iv")
def diode_iv(request: Request, body: DiodeBenchIn) -> DiodeBenchOut:
    try:
        model = diode.DiodeModel(
            Is=body.model.Is.to_pint(), n=body.model.n, Rs=body.model.Rs.to_pint()
        )
        v_lo, v_hi = body.v_min.to_pint().m_as("V"), body.v_max.to_pint().m_as("V")
    except (CircuitosError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if v_hi <= v_lo:
        raise HTTPException(422, "v_max deve ser maior que v_min")
    markers: list[Marker] = []
    if body.component_id is not None:
        repo: ComponentRepository = request.app.state.components
        try:
            markers = _datasheet_markers(repo, body.component_id)
        except CircuitosError as exc:
            raise HTTPException(404, str(exc)) from exc
    grid = np.linspace(v_lo, v_hi, body.points)
    grid = np.unique(np.concatenate([grid, [m.v.value for m in markers]]))
    curves: dict[str, VectorModel] = {}
    steps: list[CalcStep] = []
    for idx, t in enumerate(body.temperatures):
        temp = t.to_pint()
        label = f"{temp.m_as('degC'):g} °C"
        current = diode.current(model, Q_(grid, "V"), temp)
        curves[label] = VectorModel.from_pint(current, "A")
        is_step = diode.saturation_current(model, temp).step
        coeff_step = diode.vf_temperature_coefficient(model, Q_(10, "mA"), temp).step
        for step, sid in ((is_step, "Is_T"), (coeff_step, "dVF_dT")):
            steps.append(
                step.model_copy(
                    update={"id": f"{sid}_{idx}", "description": f"{step.description} ({label})"}
                )
            )
    warnings = []
    if markers:
        warnings.append(
            "Os pontos do datasheet são valores MÁXIMOS garantidos; a curva é de um modelo "
            "didático ajustável, não do componente. O ajuste do modelo ao datasheet virá com a "
            "digitalização de curvas (Fase 8)."
        )
    return DiodeBenchOut(
        v=VectorModel(values=grid.tolist(), unit="V"),
        curves=curves,
        markers=markers,
        steps=steps,
        spice_model=model.spice(),
        warnings=warnings,
    )


# ---------------------------------------------------------------- BD-ZENER


class ZenerModelIn(BaseModel):
    VZ0: QuantityModel = QuantityModel(value=5.0, unit="V")
    Rz: QuantityModel = QuantityModel(value=2.0, unit="ohm")
    Is_r: QuantityModel = QuantityModel(value=1, unit="uA")
    n_r: float = Field(default=1.5, gt=0.2, le=10)
    TC: QuantityModel = QuantityModel(value=0.03, unit="percent/K")
    forward: DiodeModelIn = DiodeModelIn()


class ZenerBenchIn(BaseModel):
    model: ZenerModelIn = ZenerModelIn()
    temperatures: list[QuantityModel] = Field(
        default_factory=lambda: [
            QuantityModel(value=25, unit="degC"),
            QuantityModel(value=100, unit="degC"),
        ],
        min_length=1,
        max_length=6,
    )
    v_max: QuantityModel | None = None
    points: int = Field(default=600, ge=20, le=5000)
    component_id: uuid.UUID | None = None
    fit: bool = False
    iz_op: QuantityModel | None = None


class ZenerBenchOut(BaseModel):
    v: VectorModel
    curves: dict[str, VectorModel]
    markers: list[Marker]
    steps: list[CalcStep]
    model: ZenerModelIn
    spice_model: str
    warnings: list[str]


def _cond_temperature(p: Parameter) -> pint.Quantity:
    for name in ("Tj", "TL", "TA"):
        if name in p.conditions:
            return p.conditions[name].to_pint()
    return Q_(25, "degC")


def _zener_markers(record: ComponentRecord) -> list[Marker]:
    p = record.parameters.get("VZ")
    if p is None or "IZ" not in p.conditions:
        return []
    temp = _cond_temperature(p)
    iz = p.conditions["IZ"].to_pint().m_as("A")
    out = []
    for kind, label in (("min", "mín."), ("typ", "nom."), ("max", "máx.")):
        value = getattr(p, kind)
        if value is None:
            continue
        out.append(
            Marker(
                key=f"VZ_{kind}",
                label=f"{record.part_number}: VZ {label} @ {p.conditions['IZ'].value:g} "
                f"{p.conditions['IZ'].unit}",
                v=QuantityModel(value=Q_(value, p.unit).m_as("V"), unit="V"),
                i=QuantityModel(value=iz, unit="A"),
                temperature=QuantityModel(value=temp.m_as("degC"), unit="degC"),
                reviewed=p.status == "revisado",
            )
        )
    return out


def _fit_zener(
    record: ComponentRecord, model: zener.ZenerModel
) -> tuple[zener.ZenerModel, list[CalcStep], list[str]]:
    vz = record.parameters.get("VZ")
    zzt = record.parameters.get("ZZT")
    if vz is None or vz.typ is None or "IZ" not in vz.conditions:
        raise HTTPException(422, "O componente não tem VZ nominal com corrente de teste")
    if zzt is None or (zzt.typ is None and zzt.max is None):
        raise HTTPException(422, "O componente não tem ZZT")
    warnings: list[str] = []
    zzt_value = zzt.typ if zzt.typ is not None else zzt.max
    if zzt.typ is None:
        warnings.append(
            "ZZT do datasheet é limite máximo; o ajuste usa esse valor como se fosse típico."
        )
    tc = model.TC
    tc_param = record.parameters.get("TC_VZ")
    if tc_param is not None and tc_param.typ is not None:
        tc = Q_(tc_param.typ, parse_unit(tc_param.unit))
    else:
        warnings.append(
            "O datasheet não dá o coeficiente de temperatura típico de VZ; o ajuste mantém o TC "
            "informado no modelo."
        )
    fit = zener.fit_to_datasheet(
        Q_(vz.typ, parse_unit(vz.unit)),
        vz.conditions["IZ"].to_pint(),
        Q_(zzt_value, parse_unit(zzt.unit)),
        _cond_temperature(vz),
        n_r=model.n_r,
        Is_r=model.Is_r,
        TC=tc,
        forward=model.forward,
    )
    if any(p.status != "revisado" for p in (vz, zzt)):
        warnings.append("O ajuste usa valores do datasheet ainda não conferidos na revisão.")
    return fit.model, [s.step for s in fit.steps], warnings + fit.warnings


def _model_out(m: zener.ZenerModel) -> ZenerModelIn:
    f = m.forward
    return ZenerModelIn(
        VZ0=QuantityModel(value=m.VZ0.m_as("V"), unit="V"),
        Rz=QuantityModel(value=m.Rz.m_as("ohm"), unit="ohm"),
        Is_r=QuantityModel(value=m.Is_r.m_as("A"), unit="A"),
        n_r=m.n_r,
        TC=QuantityModel(value=m.TC.m_as("percent/K"), unit="percent/K"),
        forward=DiodeModelIn(
            Is=QuantityModel(value=f.Is.m_as("A"), unit="A"),
            n=f.n,
            Rs=QuantityModel(value=f.Rs.m_as("ohm"), unit="ohm"),
        ),
    )


@router.post("/zener/iv")
def zener_iv(request: Request, body: ZenerBenchIn) -> ZenerBenchOut:
    try:
        fm = body.model.forward
        model = zener.ZenerModel(
            VZ0=body.model.VZ0.to_pint(),
            Rz=body.model.Rz.to_pint(),
            Is_r=body.model.Is_r.to_pint(),
            n_r=body.model.n_r,
            TC=body.model.TC.to_pint(),
            forward=diode.DiodeModel(Is=fm.Is.to_pint(), n=fm.n, Rs=fm.Rs.to_pint()),
        )
    except (CircuitosError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    steps: list[CalcStep] = []
    warnings: list[str] = []
    markers: list[Marker] = []
    iz_op = body.iz_op.to_pint() if body.iz_op else Q_(10, "mA")
    if body.component_id is not None:
        repo: ComponentRepository = request.app.state.components
        try:
            record = repo.get(body.component_id)
        except CircuitosError as exc:
            raise HTTPException(404, str(exc)) from exc
        if record.category != "diode.zener":
            raise HTTPException(422, f"{record.part_number} não é um diodo Zener")
        markers = _zener_markers(record)
        vz = record.parameters.get("VZ")
        if body.iz_op is None and vz is not None and "IZ" in vz.conditions:
            iz_op = vz.conditions["IZ"].to_pint()
        if body.fit:
            model, fit_steps, fit_warnings = _fit_zener(record, model)
            steps += fit_steps
            warnings += fit_warnings
        else:
            warnings.append(
                "Os pontos do datasheet mostram VZ na corrente de teste; a curva é do modelo "
                "ajustável. Use 'Ajustar ao datasheet' para calibrar VZ0 e Rz."
            )
    temps = [t.to_pint() for t in body.temperatures]
    if body.v_max is not None:
        v_hi = body.v_max.to_pint().m_as("V")
    else:
        v_hi = max(model.vz0_at(t).m_as("V") for t in temps) * 1.15 + 0.5
    if v_hi <= 0:
        raise HTTPException(422, "v_max deve ser positivo")
    grid = np.linspace(0, v_hi, body.points)
    grid = np.unique(np.concatenate([grid, [m.v.value for m in markers if m.v.value < v_hi]]))
    curves: dict[str, VectorModel] = {}
    for idx, temp in enumerate(temps):
        label = f"{temp.m_as('degC'):g} °C"
        curves[label] = VectorModel.from_pint(
            zener.reverse_current(model, Q_(grid, "V"), temp), "A"
        )
        for step, sid in (
            (zener.zener_voltage_step(model, iz_op, temp).step, "VZ"),
            (zener.dynamic_resistance(model, iz_op, temp).step, "rz"),
        ):
            steps.append(
                step.model_copy(
                    update={"id": f"{sid}_{idx}", "description": f"{step.description} ({label})"}
                )
            )
    return ZenerBenchOut(
        v=VectorModel(values=grid.tolist(), unit="V"),
        curves=curves,
        markers=markers,
        steps=steps,
        model=_model_out(model),
        spice_model=model.spice(),
        warnings=warnings,
    )
