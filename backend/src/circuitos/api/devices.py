"""Device bench endpoints (BD-DIODO, BD-ZENER, BD-TBJ, BD-FET)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

import numpy as np
import pint
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.components.repository import ComponentRepository
from circuitos.core.calc import BibRef, CalcStep, record
from circuitos.core.errors import CircuitosError
from circuitos.core.units import Q_, QuantityModel, VectorModel, parse_unit
from circuitos.devices import bjt, diode, mosfet, zener

router = APIRouter(prefix="/api/v1/devices")


def formatq(q: pint.Quantity) -> str:
    """Short text for a quantity in a curve label: "10 µA", "4,5 V"."""
    text = f"{q.to_compact():~.3g}".replace("u", "µ").replace(".", ",")
    return text.replace("µs", "µs")


def record_step(
    id_: str,
    description: str,
    latex: str,
    output: pint.Quantity,
    inputs: Mapping[str, pint.Quantity | None],
    assumptions: list[str],
    reference: BibRef,
) -> CalcStep:
    clean = {k: v for k, v in inputs.items() if v is not None}
    return record(
        id_,
        description,
        latex,
        output=output,
        inputs=clean,
        assumptions=assumptions,
        reference=reference,
    ).step


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


# ---------------------------------------------------------------- BD-TBJ and BD-FET


class CurvesOut(BaseModel):
    x: VectorModel
    curves: dict[str, VectorModel]
    markers: list[Marker]
    steps: list[CalcStep]
    model: dict[str, QuantityModel | float]
    spice_model: str
    warnings: list[str]


def _record_for(request: Request, component_id: uuid.UUID, prefix: str) -> ComponentRecord:
    repo: ComponentRepository = request.app.state.components
    try:
        record = repo.get(component_id)
    except CircuitosError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not record.category.startswith(prefix):
        raise HTTPException(422, f"{record.part_number} não pertence à categoria {prefix}")
    return record


def _q(p: Parameter, attr: str) -> pint.Quantity | None:
    value = getattr(p, attr)
    return None if value is None else Q_(value, parse_unit(p.unit))


def _unreviewed(params: list[Parameter | None]) -> list[str]:
    if any(p is not None and p.status != "revisado" for p in params):
        return ["O ajuste usa valores do datasheet ainda não conferidos na revisão."]
    return []


class BjtModelIn(BaseModel):
    IS: QuantityModel = QuantityModel(value=1e-14, unit="A")
    BF: float = Field(default=200, gt=1, le=1e5)
    BR: float = Field(default=2, gt=0, le=1e3)
    VAF: QuantityModel = QuantityModel(value=80, unit="V")


class BjtBenchIn(BaseModel):
    model: BjtModelIn = BjtModelIn()
    ib: list[QuantityModel] = Field(
        default_factory=lambda: [QuantityModel(value=v, unit="uA") for v in (10, 20, 30, 40, 50)],
        min_length=1,
        max_length=10,
    )
    vce_max: QuantityModel = QuantityModel(value=10, unit="V")
    temperature: QuantityModel = QuantityModel(value=27, unit="degC")
    points: int = Field(default=400, ge=20, le=5000)
    component_id: uuid.UUID | None = None
    fit: bool = False


def _fit_bf(record: ComponentRecord) -> tuple[float, CalcStep, list[str]]:
    p = record.parameters.get("hFE")
    if p is None or not p.has_value:
        raise HTTPException(422, "O componente não tem hFE")
    warnings: list[str] = []
    if p.typ is not None:
        value, formula, how = p.typ, r"\beta_F = h_{FE,typ}", "valor típico do datasheet"
    elif p.min is not None and p.max is not None:
        value = float(np.sqrt(p.min * p.max))
        formula, how = r"\beta_F = \sqrt{h_{FE,min}\,h_{FE,max}}", "média geométrica de mín. e máx."
        warnings.append("O datasheet não dá hFE típico; BF = média geométrica de mín. e máx.")
    else:
        value = float(p.min if p.min is not None else p.max)  # type: ignore[arg-type]
        formula, how = r"\beta_F = h_{FE,lim}", "único limite disponível"
        warnings.append("O datasheet só dá um limite de hFE; BF foi tomado igual a esse limite.")
    inputs = {
        k: v
        for k, v in (
            ("h_{FE,min}", _q(p, "min")),
            ("h_{FE,typ}", _q(p, "typ")),
            ("h_{FE,max}", _q(p, "max")),
        )
        if v is not None
    }
    inputs |= {k: c.to_pint() for k, c in p.conditions.items() if k in ("IC", "VCE")}
    step = record_step(
        "BF_fit",
        "Ganho direto do modelo a partir do hFE do datasheet",
        formula,
        Q_(value, "dimensionless"),
        inputs,
        [how, "BF constante (sem queda de ganho em alta corrente)"],
        bjt.BJT_REF,
    )
    return value, step, warnings + _unreviewed([p])


@router.post("/bjt/output")
def bjt_output(request: Request, body: BjtBenchIn) -> CurvesOut:
    try:
        model = bjt.BjtModel(
            IS=body.model.IS.to_pint(),
            BF=body.model.BF,
            BR=body.model.BR,
            VAF=body.model.VAF.to_pint(),
        )
        vmax = body.vce_max.to_pint().m_as("V")
        temp = body.temperature.to_pint()
    except (CircuitosError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if vmax <= 0:
        raise HTTPException(422, "vce_max deve ser positivo")
    steps: list[CalcStep] = []
    warnings: list[str] = []
    markers: list[Marker] = []
    if body.component_id is not None:
        record = _record_for(request, body.component_id, "bjt")
        if body.fit:
            bf, step, w = _fit_bf(record)
            model = bjt.BjtModel(IS=model.IS, BF=bf, BR=model.BR, VAF=model.VAF)
            steps.append(step)
            warnings += w
        for key, p in record.parameters.items():
            if p.symbol == "VCE(sat)" and p.max is not None and "IC" in p.conditions:
                ic = p.conditions["IC"].to_pint()
                ibc = p.conditions.get("IB")
                markers.append(
                    Marker(
                        key=key,
                        label=f"{record.part_number}: VCE(sat) máx. @ IC = {formatq(ic)}"
                        + (f", IB = {formatq(ibc.to_pint())}" if ibc else ""),
                        v=QuantityModel(value=Q_(p.max, parse_unit(p.unit)).m_as("V"), unit="V"),
                        i=QuantityModel(value=ic.m_as("A"), unit="A"),
                        temperature=None,
                        reviewed=p.status == "revisado",
                    )
                )
        if record.category == "bjt.pnp":
            warnings.append("Transistor PNP: curvas e valores em módulo.")
    grid = np.linspace(0, vmax, body.points)
    grid = np.unique(np.concatenate([grid, [m.v.value for m in markers if m.v.value < vmax]]))
    curves: dict[str, VectorModel] = {}
    for ibq in body.ib:
        ib = ibq.to_pint()
        ic, _ = bjt.output_characteristic(model, ib, Q_(grid, "V"), temp)
        curves[f"IB = {formatq(ib)}"] = VectorModel.from_pint(ic, "A")
    mid_ib = body.ib[len(body.ib) // 2].to_pint()
    vce_op = Q_(vmax / 2, "V")
    ic_op, _ = bjt.output_characteristic(model, mid_ib, vce_op, temp)
    steps.append(bjt.forward_gain(model, ic_op, mid_ib).step)
    steps.append(bjt.output_resistance(model, ic_op, vce_op).step)
    return CurvesOut(
        x=VectorModel(values=grid.tolist(), unit="V"),
        curves=curves,
        markers=markers,
        steps=steps,
        model={
            "IS": QuantityModel(value=model.IS.m_as("A"), unit="A"),
            "BF": model.BF,
            "BR": model.BR,
            "VAF": QuantityModel(value=model.VAF.m_as("V"), unit="V"),
        },
        spice_model=model.spice(),
        warnings=warnings,
    )


class MosfetModelIn(BaseModel):
    VTO: QuantityModel = QuantityModel(value=3.0, unit="V")
    KP: QuantityModel = QuantityModel(value=2.0, unit="A/V**2")
    LAMBDA: QuantityModel = QuantityModel(value=0.01, unit="1/V")


class MosfetBenchIn(BaseModel):
    model: MosfetModelIn = MosfetModelIn()
    vgs: list[QuantityModel] = Field(
        default_factory=lambda: [QuantityModel(value=v, unit="V") for v in (4, 4.5, 5, 5.5, 6)],
        min_length=1,
        max_length=10,
    )
    vds_max: QuantityModel = QuantityModel(value=10, unit="V")
    points: int = Field(default=400, ge=20, le=5000)
    component_id: uuid.UUID | None = None
    fit: bool = False


@router.post("/mosfet/output")
def mosfet_output(request: Request, body: MosfetBenchIn) -> CurvesOut:
    try:
        model = mosfet.MosfetModel(
            VTO=body.model.VTO.to_pint(),
            KP=body.model.KP.to_pint(),
            LAMBDA=body.model.LAMBDA.to_pint(),
        )
        vmax = body.vds_max.to_pint().m_as("V")
    except (CircuitosError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if vmax <= 0:
        raise HTTPException(422, "vds_max deve ser positivo")
    steps: list[CalcStep] = []
    warnings: list[str] = []
    markers: list[Marker] = []
    if body.component_id is not None:
        record = _record_for(request, body.component_id, "mosfet")
        rds = record.parameters.get("RDS(on)")
        vth = record.parameters.get("VGS(th)")
        if rds is not None and rds.max is not None and "ID" in rds.conditions:
            idq = rds.conditions["ID"].to_pint()
            vds_pt = Q_(Q_(rds.max, parse_unit(rds.unit)).m_as("ohm") * idq.m_as("A"), "V")
            vgs_txt = formatq(rds.conditions["VGS"].to_pint()) if "VGS" in rds.conditions else "?"
            markers.append(
                Marker(
                    key="RDS(on)",
                    label=f"{record.part_number}: RDS(on) máx. @ VGS = {vgs_txt}, "
                    f"ID = {formatq(idq)}",
                    v=QuantityModel(value=vds_pt.m_as("V"), unit="V"),
                    i=QuantityModel(value=idq.m_as("A"), unit="A"),
                    temperature=None,
                    reviewed=rds.status == "revisado",
                )
            )
        if body.fit:
            if rds is None or rds.max is None or "VGS" not in rds.conditions:
                raise HTTPException(422, "O componente não tem RDS(on) com VGS de ensaio")
            if vth is None or vth.min is None or vth.max is None:
                raise HTTPException(422, "O componente não tem VGS(th) mín. e máx.")
            vt = Q_((vth.min + vth.max) / 2, parse_unit(vth.unit))
            vt_step = record_step(
                "VT_fit",
                "Tensão de limiar do modelo",
                r"V_T = \frac{V_{GS(th),min} + V_{GS(th),max}}{2}",
                vt.to("V"),
                {"V_{GS(th),min}": _q(vth, "min"), "V_{GS(th),max}": _q(vth, "max")},
                ["ponto médio da faixa do datasheet (não há valor típico)"],
                mosfet.MOS_REF,
            )
            try:
                model, fit_steps = mosfet.fit_to_datasheet(
                    vt,
                    Q_(rds.max, parse_unit(rds.unit)),
                    rds.conditions["VGS"].to_pint(),
                    model.LAMBDA,
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            steps += [vt_step] + [s.step for s in fit_steps]
            warnings.append(
                "RDS(on) do datasheet é máximo: o KP ajustado é conservador (corrente menor que a "
                "típica). O modelo quadrático não representa bem um MOSFET de potência em alta "
                "corrente; use-o para entender as regiões de operação."
            )
            warnings += _unreviewed([rds, vth])
    grid = np.linspace(0, vmax, body.points)
    grid = np.unique(np.concatenate([grid, [m.v.value for m in markers if m.v.value < vmax]]))
    curves: dict[str, VectorModel] = {}
    for vq in body.vgs:
        vgs = vq.to_pint()
        curves[f"VGS = {formatq(vgs)}"] = VectorModel.from_pint(
            mosfet.drain_current(model, vgs, Q_(grid, "V")), "A"
        )
    top = body.vgs[-1].to_pint()
    steps.append(mosfet.saturation_current(model, top, Q_(vmax, "V")).step)
    return CurvesOut(
        x=VectorModel(values=grid.tolist(), unit="V"),
        curves=curves,
        markers=markers,
        steps=steps,
        model={
            "VTO": QuantityModel(value=model.VTO.m_as("V"), unit="V"),
            "KP": QuantityModel(value=model.KP.m_as("A/V**2"), unit="A/V**2"),
            "LAMBDA": QuantityModel(value=model.LAMBDA.m_as("1/V"), unit="1/V"),
        },
        spice_model=model.spice(),
        warnings=warnings,
    )
