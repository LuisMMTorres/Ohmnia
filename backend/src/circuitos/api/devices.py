"""Device bench endpoints (BD-DIODO)."""

from __future__ import annotations

import uuid

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from circuitos.components.repository import ComponentRepository
from circuitos.core.calc import CalcStep
from circuitos.core.errors import CircuitosError
from circuitos.core.units import Q_, QuantityModel, VectorModel
from circuitos.devices import diode

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
        steps.append(is_step.model_copy(update={"id": f"Is_T_{idx}"}))
        steps.append(coeff_step.model_copy(update={"id": f"dVF_dT_{idx}"}))
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
