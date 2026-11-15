"""SPICE models fitted to datasheet data, with the error measured by ngspice.

Three device families, each from the data a datasheet normally gives:

* **Diode** (``D``): IS, N, RS from a digitised IF×VF curve; BV/IBV from V(BR) or VRRM and IR
  (Zener: VZ at IZT); CJO from Cj at a reverse voltage; TT from trr.
* **Bipolar transistor** (Gummel-Poon reduced to IS, NF, BF, IKF): IS and NF from a VBE×IC curve
  (or from VBE(on) with NF = 1); BF and IKF from an hFE×IC curve (or BF = hFE).
* **MOSFET** (level 1): VTO and KP from the transfer curve ID×VGS in saturation (or from VGS(th)
  and gfs); RD from RDS(on).

Every assumption that is not a datasheet value goes into ``FitReport.assumptions``. The final
``.model`` is then simulated by ngspice at each digitised point, and the residuals reported are
the simulated ones (rule 4: the model is judged by the simulator that will use it).

Equations: ngspice manual, chapters on the diode, BJT (Gummel-Poon) and MOSFET level 1 models;
Antognetti & Massobrio, *Semiconductor Device Modeling with SPICE*, 2nd ed., chs. 1–3. The
reverse-recovery estimate TT ≈ trr / ln(1 + IF/IR) is the charge-control approximation found in
the same book (chapter and equation numbers to be confirmed against the printed edition).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from circuitos.components.models import (
    ComponentRecord,
    Curve,
    FitReport,
    FitResidual,
    Parameter,
    SpiceModel,
)
from circuitos.core.errors import CircuitosError
from circuitos.core.units import Q_, parse_unit
from circuitos.simulation.backend import SimulatorBackend, make_backend

K_B = 1.380649e-23
Q_E = 1.602176634e-19
Floats = NDArray[np.float64]


class FitError(CircuitosError):
    """Not enough datasheet data for the requested model."""


def vt(t_celsius: float) -> float:
    return K_B * (t_celsius + 273.15) / Q_E


# ---------------------------------------------------------------------------------- helpers --


def _axis_si(curve: Curve, axis: str) -> Floats:
    spec = curve.x if axis == "x" else curve.y
    idx = 0 if axis == "x" else 1
    values = np.array([p[idx] for p in curve.points], dtype=float)
    unit = parse_unit(spec.unit)
    if unit == parse_unit("dimensionless"):
        return values
    base = Q_(values, unit).to_base_units()
    return np.asarray(base.magnitude, dtype=float)


def _dimension(curve: Curve, axis: str) -> str:
    spec = curve.x if axis == "x" else curve.y
    unit = parse_unit(spec.unit)
    if unit == parse_unit("dimensionless"):
        return "1"
    dims = Q_(1, unit).dimensionality
    for name, ref in (("A", "A"), ("V", "V")):
        if dims == Q_(1, parse_unit(ref)).dimensionality:
            return name
    return str(dims)


def _pair(curve: Curve, x_dim: str, y_dim: str) -> tuple[Floats, Floats]:
    """(x, y) in SI with the requested dimensions, whatever the figure's orientation."""
    dx, dy = _dimension(curve, "x"), _dimension(curve, "y")
    if (dx, dy) == (x_dim, y_dim):
        x, y = _axis_si(curve, "x"), _axis_si(curve, "y")
    elif (dx, dy) == (y_dim, x_dim):
        x, y = _axis_si(curve, "y"), _axis_si(curve, "x")
    else:
        raise FitError(
            f"Curva {curve.name}: eixos {curve.x.unit}×{curve.y.unit}, esperado {x_dim}×{y_dim}"
        )
    order = np.argsort(x)
    return x[order], y[order]


def _temperature(curve: Curve | None, notes: list[str]) -> float:
    if curve is not None:
        for key in ("Tj", "TA", "TC"):
            q = curve.family.get(key)
            if q is not None:
                return float(q.to_pint().m_as("degC"))
    notes.append("temperatura da curva não informada: assumida 25 °C (TNOM do modelo)")
    return 25.0


def _value(record: ComponentRecord, key: str) -> tuple[float, Parameter] | None:
    """Nominal value in SI: typical, else the guaranteed limit."""
    param = record.parameters.get(key)
    if param is None or not param.has_value:
        return None
    raw = next(v for v in (param.typ, param.max, param.min) if v is not None)
    unit = parse_unit(param.unit)
    if param.unit == "degC":
        return raw, param
    return float(Q_(raw, unit).to_base_units().magnitude), param


def _condition(param: Parameter, *names: str) -> float | None:
    for n in names:
        q = param.conditions.get(n)
        if q is not None:
            return float(q.to_pint().to_base_units().magnitude)
    return None


def _fmt(v: float) -> str:
    return f"{v:.6g}"


@dataclass
class _Fit:
    params: dict[str, float]
    origin: dict[str, str]
    assumptions: list[str] = field(default_factory=list)


def _model_text(name: str, device: str, fit: _Fit) -> str:
    body = " ".join(f"{k}={_fmt(v)}" for k, v in fit.params.items())
    return f".model {name} {device}({body})"


def _report(
    quantity: str,
    curve_ids: list[str],
    x: Floats,
    measured: Floats,
    model: Floats,
    fit: _Fit,
    simulated: bool,
) -> FitReport:
    err = 100 * (model - measured) / np.where(measured == 0, 1e-30, measured)
    fitted = sum(1 for origin in fit.origin.values() if origin.startswith("ajuste"))
    assumptions = list(fit.assumptions)
    if len(x) <= fitted + 1:
        assumptions.append(
            f"{len(x)} ponto(s) para {fitted} parâmetro(s) ajustado(s): o ajuste passa pelos "
            "pontos quase por construção e o erro não mede a qualidade do modelo; digitalize "
            "mais pontos ao longo de toda a curva"
        )
    return FitReport(
        curves=curve_ids,
        quantity=quantity,
        points=len(x),
        rms_error_pct=float(np.sqrt(np.mean(err**2))),
        max_error_pct=float(np.max(np.abs(err))),
        residuals=[
            FitResidual(x=float(a), measured=float(b), model=float(c), error_pct=float(e))
            for a, b, c, e in zip(x, measured, model, err, strict=True)
        ],
        simulated=simulated,
        assumptions=assumptions,
        params_origin=fit.origin,
    )


def _op_values(backend: SimulatorBackend, netlist: str, names: list[str]) -> Floats:
    result = backend.run(netlist)
    plot = result.plot("op")
    return np.array([float(np.real(plot[n].data[0])) for n in names])


def _default_name(record: ComponentRecord, suffix: str = "") -> str:
    return "".join(c if c.isalnum() else "_" for c in record.part_number.upper()) + suffix


# -------------------------------------------------------------------------------------- diode --


def _diode_vf(i: Floats, is_: float, n: float, rs: float, t: float) -> Floats:
    return np.asarray(n * vt(t) * np.log1p(i / is_) + i * rs, dtype=float)


def fit_diode_curve(i: Floats, v: Floats, t: float) -> tuple[float, float, float]:
    """IS, N, RS minimising the error in V(I), started from the linearised solution."""
    if len(i) < 3:
        raise FitError("A curva IF×VF precisa de pelo menos 3 pontos")
    # V ≈ a·ln I + b + RS·I for I ≫ IS, with a = N·Vt and b = −N·Vt·ln IS
    design = np.column_stack([np.log(i), np.ones_like(i), i])
    (a, b, rs0), *_ = np.linalg.lstsq(design, v, rcond=None)
    n0 = max(a / vt(t), 0.5)
    is0 = math.exp(-b / (n0 * vt(t))) if a > 0 else 1e-12
    rs0 = max(rs0, 0.0)

    def residual(p: Floats) -> Floats:
        log_is, n, rs = p
        return (_diode_vf(i, 10**log_is, n, rs, t) - v) / v

    sol = least_squares(
        residual,
        x0=[math.log10(max(is0, 1e-30)), n0, rs0],
        bounds=([-30, 0.5, 0.0], [-1, 10, 1e3]),
    )
    log_is, n, rs = sol.x
    return float(10**log_is), float(n), float(rs)


def fit_diode(
    record: ComponentRecord,
    curve: Curve,
    name: str | None = None,
    backend: SimulatorBackend | None = None,
) -> SpiceModel:
    name = name or _default_name(record)
    notes: list[str] = []
    t = _temperature(curve, notes)
    i, v = _pair(curve, "A", "V")
    is_, n, rs = fit_diode_curve(i, v, t)
    fit = _Fit(
        params={"IS": is_, "N": n, "RS": rs, "TNOM": t},
        origin={
            "IS": f"ajuste da curva {curve.name}",
            "N": f"ajuste da curva {curve.name}",
            "RS": f"ajuste da curva {curve.name}",
            "TNOM": "temperatura da curva",
        },
        assumptions=notes,
    )
    zener = record.category == "diode.zener"
    if zener and (vz := _value(record, "VZ")) and (izt := _value(record, "IZT")):
        fit.params["BV"], fit.params["IBV"] = vz[0], izt[0]
        fit.origin["BV"], fit.origin["IBV"] = "VZ do datasheet", "IZT do datasheet"
    else:
        bv = _value(record, "V(BR)") or _value(record, "VRRM")
        if bv is not None:
            fit.params["BV"] = bv[0]
            fit.origin["BV"] = f"{bv[1].symbol} do datasheet"
            ir = _value(record, "IR")
            if ir is not None:
                fit.params["IBV"] = ir[0]
                fit.origin["IBV"] = "IR do datasheet"
                fit.assumptions.append("IBV tomado igual à corrente reversa especificada (IR)")
    cj = _value(record, "Cj")
    if cj is not None:
        vr = _condition(cj[1], "VR") or 0.0
        vj, m = 1.0, 0.5
        fit.params.update({"CJO": cj[0] * (1 + vr / vj) ** m, "VJ": vj, "M": m})
        fit.origin["CJO"] = f"Cj do datasheet a VR = {vr:g} V, levado a 0 V"
        fit.assumptions.append("junção abrupta: VJ = 1 V e M = 0,5 (padrões do modelo)")
    trr = _value(record, "trr")
    if trr is not None:
        i_f = _condition(trr[1], "IF")
        i_r = _condition(trr[1], "IR", "IRR", "IR_rec", "IRM")
        if i_f is None:
            fit.assumptions.append("trr sem a condição IF: TT não estimado")
        else:
            if i_r is None:
                i_r = i_f
                fit.assumptions.append("trr sem a corrente reversa do ensaio: IR = IF assumido")
            fit.params["TT"] = trr[0] / math.log(1 + i_f / i_r)
            fit.origin["TT"] = "trr do datasheet, TT ≈ trr / ln(1 + IF/IR)"
    text = _model_text(name, "D", fit)
    model_v = _diode_vf(i, is_, n, rs, t)
    simulated = False
    if backend is not None or _simulator_available():
        sim = backend or make_backend("batch", timeout_s=60)
        lines = [f"fit {name}", text]
        for k, ik in enumerate(i):
            lines += [f"I{k} 0 a{k} DC {_fmt(ik)}", f"D{k} a{k} 0 {name}"]
        lines += [f".options temp={_fmt(t)}", ".op", ".end"]
        model_v = _op_values(sim, "\n".join(lines), [f"v(a{k})" for k in range(len(i))])
        simulated = True
    report = _report("VF(IF)", [curve.id], i, v, model_v, fit, simulated)
    return SpiceModel(
        name=name,
        kind="model",
        device="D",
        params=fit.params,
        text=text,
        origin="ajustado",
        checked=simulated,
        fit=report,
    )


# ---------------------------------------------------------------------------------------- BJT --


def _hfe_gp(ic: Floats, bf: float, ikf: float) -> Floats:
    # Gummel-Poon high injection with q1 = 1: qb = (1 + √(1 + 4·q2))/2 and q2 = IC·qb/IKF
    # (because IS·exp(VBE/NF·Vt) = IC·qb) give qb = 1 + IC/IKF, so hFE = BF / (1 + IC/IKF).
    return np.asarray(bf / (1 + ic / ikf), dtype=float)


def fit_bjt(
    record: ComponentRecord,
    hfe_curve: Curve | None = None,
    vbe_curve: Curve | None = None,
    name: str | None = None,
    backend: SimulatorBackend | None = None,
) -> SpiceModel:
    pnp = record.category == "bjt.pnp"
    device = "PNP" if pnp else "NPN"
    name = name or _default_name(record)
    notes: list[str] = []
    t = _temperature(hfe_curve or vbe_curve, notes)
    fit = _Fit(params={}, origin={}, assumptions=notes)
    if vbe_curve is not None:
        ic, vbe = _pair(vbe_curve, "A", "V")
        keep = ic <= np.quantile(ic, 0.7) if len(ic) > 4 else np.ones_like(ic, dtype=bool)
        slope, intercept = np.polyfit(vbe[keep], np.log(ic[keep]), 1)
        fit.params["IS"] = float(math.exp(intercept))
        fit.params["NF"] = float(1 / (slope * vt(t)))
        fit.origin["IS"] = fit.origin["NF"] = f"ajuste da curva {vbe_curve.name}"
        fit.assumptions.append("IS e NF ajustados na parte baixa da curva (sem RB e RE)")
    else:
        vbe_on = _value(record, "VBE(on)") or _value(record, "VBE(sat)")
        if vbe_on is None:
            raise FitError("Falta a curva VBE×IC ou o parâmetro VBE(on) para estimar IS")
        ic_at = _condition(vbe_on[1], "IC")
        if ic_at is None:
            raise FitError(f"{vbe_on[1].symbol} sem a condição IC")
        fit.params["NF"] = 1.0
        fit.params["IS"] = ic_at / math.exp(vbe_on[0] / vt(t))
        fit.origin["IS"] = f"{vbe_on[1].symbol} a IC = {ic_at:g} A"
        fit.origin["NF"] = "valor ideal"
        fit.assumptions.append("NF = 1 (junção ideal); IS de um só ponto VBE×IC")
    vce = 5.0
    if hfe_curve is not None:
        ic, hfe = _pair(hfe_curve, "A", "1")
        peak = int(np.argmax(hfe))
        sel = slice(peak, None) if len(ic) - peak >= 3 else slice(None)

        def residual(p: Floats) -> Floats:
            return (_hfe_gp(ic[sel], p[0], 10 ** p[1]) - hfe[sel]) / hfe[sel]

        sol = least_squares(
            residual,
            x0=[float(hfe[peak]), math.log10(max(ic) * 2)],
            bounds=([1, -6], [1e5, 4]),
        )
        fit.params["BF"], fit.params["IKF"] = float(sol.x[0]), float(10 ** sol.x[1])
        fit.origin["BF"] = fit.origin["IKF"] = f"ajuste da curva {hfe_curve.name}"
        fit.assumptions.append(
            "queda do hFE em correntes baixas (ISE, NE) não modelada: o ajuste usa o pico em diante"
        )
        if (q := hfe_curve.family.get("VCE")) is not None:
            vce = abs(float(q.to_pint().m_as("V")))
        else:
            fit.assumptions.append("VCE da curva não informado: 5 V na simulação de conferência")
    else:
        hfe_p = _value(record, "hFE")
        if hfe_p is None:
            raise FitError("Falta a curva hFE×IC ou o parâmetro hFE")
        fit.params["BF"] = hfe_p[0]
        fit.origin["BF"] = "hFE do datasheet"
        fit.assumptions.append("sem curva hFE×IC: BF = hFE, sem queda em alta corrente (IKF)")
    fit.params["TNOM"] = t
    fit.origin["TNOM"] = "temperatura da curva"
    fit.assumptions.append("VAF não informado no datasheet: efeito Early desprezado")
    text = _model_text(name, device, fit)
    if hfe_curve is None:
        report = FitReport(
            quantity="hFE",
            points=0,
            rms_error_pct=0.0,
            max_error_pct=0.0,
            assumptions=fit.assumptions,
            params_origin=fit.origin,
        )
        return SpiceModel(
            name=name,
            kind="model",
            device=device,
            params=fit.params,
            text=text,
            origin="ajustado",
            fit=report,
        )
    ic, hfe = _pair(hfe_curve, "A", "1")
    model_hfe = _hfe_gp(ic, fit.params["BF"], fit.params.get("IKF", 1e30))
    simulated = False
    if backend is not None or _simulator_available():
        sim = backend or make_backend("batch", timeout_s=60)
        s = -1 if pnp else 1
        lines = [f"fit {name}", text]
        for k, (ick, hk) in enumerate(zip(ic, hfe, strict=True)):
            ie = ick * (1 + 1 / hk)
            lines += [
                f"VC{k} c{k} 0 DC {_fmt(s * vce)}",
                f"VB{k} b{k} 0 DC 0",
                f"Q{k} c{k} b{k} e{k} {name}",
                # NPN: draw IE out of the emitter; PNP: push it in
                f"IE{k} e{k} 0 DC {_fmt(s * ie)}",
            ]
        lines += [f".options temp={_fmt(t)}", ".op", ".end"]
        names = [f"i(vc{k})" for k in range(len(ic))] + [f"i(vb{k})" for k in range(len(ic))]
        values = _op_values(sim, "\n".join(lines), names)
        model_hfe = values[: len(ic)] / values[len(ic) :]
        simulated = True
    report = _report("hFE(IC)", [hfe_curve.id], ic, hfe, model_hfe, fit, simulated)
    return SpiceModel(
        name=name,
        kind="model",
        device=device,
        params=fit.params,
        text=text,
        origin="ajustado",
        checked=simulated,
        fit=report,
    )


# ------------------------------------------------------------------------------------ MOSFET --


def fit_mosfet(
    record: ComponentRecord,
    transfer: Curve | None = None,
    name: str | None = None,
    backend: SimulatorBackend | None = None,
) -> SpiceModel:
    name = name or _default_name(record)
    notes: list[str] = []
    t = _temperature(transfer, notes)
    fit = _Fit(
        params={"LEVEL": 1.0},
        origin={"LEVEL": "modelo nível 1 (lei quadrática)"},
        assumptions=notes,
    )
    vds = 10.0
    if transfer is not None:
        vgs, i_d = _pair(transfer, "V", "A")
        keep = i_d >= 0.05 * np.max(i_d)
        if keep.sum() < 3:
            raise FitError("A curva de transferência precisa de 3 pontos acima do limiar")
        slope, intercept = np.polyfit(vgs[keep], np.sqrt(i_d[keep]), 1)
        if slope <= 0:
            raise FitError("Curva de transferência sem crescimento de ID com VGS")
        fit.params["VTO"] = float(-intercept / slope)
        fit.params["KP"] = float(2 * slope**2)
        fit.origin["VTO"] = fit.origin["KP"] = f"ajuste de √ID×VGS na curva {transfer.name}"
        fit.assumptions.append("pontos com ID < 5 % do máximo (sublimiar) fora do ajuste")
        if (q := transfer.family.get("VDS")) is not None:
            vds = float(q.to_pint().m_as("V"))
        else:
            fit.assumptions.append("VDS da curva não informado: 10 V na simulação de conferência")
    else:
        vth = _value(record, "VGS(th)")
        gfs = _value(record, "gfs")
        if vth is None or gfs is None:
            raise FitError("Falta a curva de transferência, ou VGS(th) e gfs")
        id_at = _condition(gfs[1], "ID")
        if id_at is None:
            raise FitError("gfs sem a condição ID")
        fit.params["VTO"] = vth[0]
        fit.params["KP"] = gfs[0] ** 2 / (2 * id_at)
        fit.origin["VTO"] = "VGS(th) do datasheet"
        fit.origin["KP"] = f"gfs a ID = {id_at:g} A, KP = gfs²/(2·ID)"
        fit.assumptions.append("VTO tomado igual a VGS(th) (definição de limiar do datasheet)")
    rds = _value(record, "RDS(on)")
    if rds is not None:
        vgs_on = _condition(rds[1], "VGS") or 10.0
        r_channel = 1 / (fit.params["KP"] * max(vgs_on - fit.params["VTO"], 1e-3))
        fit.params["RD"] = max(rds[0] - r_channel, 0.0)
        fit.origin["RD"] = "RDS(on) do datasheet menos a resistência do canal do modelo"
        fit.assumptions.append("RS = 0: toda a resistência série no dreno")
    fit.params["LAMBDA"] = 0.0
    fit.origin["LAMBDA"] = "modulação do canal desprezada"
    fit.params["TNOM"] = t
    fit.origin["TNOM"] = "temperatura da curva"
    fit.assumptions.append("W = L (padrão do simulador): KP já inclui a geometria")
    text = _model_text(name, "NMOS", fit)
    if transfer is None:
        report = FitReport(
            quantity="ID(VGS)",
            points=0,
            rms_error_pct=0.0,
            max_error_pct=0.0,
            assumptions=fit.assumptions,
            params_origin=fit.origin,
        )
        return SpiceModel(
            name=name,
            kind="model",
            device="NMOS",
            params=fit.params,
            text=text,
            origin="ajustado",
            fit=report,
        )
    vgs, i_d = _pair(transfer, "V", "A")
    kp, vto = fit.params["KP"], fit.params["VTO"]
    model_id = np.where(vgs > vto, kp / 2 * (vgs - vto) ** 2, 0.0)
    simulated = False
    if backend is not None or _simulator_available():
        sim = backend or make_backend("batch", timeout_s=60)
        lines = [f"fit {name}", text]
        for k, vg in enumerate(vgs):
            lines += [
                f"VD{k} d{k} 0 DC {_fmt(vds)}",
                f"VG{k} g{k} 0 DC {_fmt(vg)}",
                f"M{k} d{k} g{k} 0 0 {name}",
            ]
        lines += [f".options temp={_fmt(t)}", ".op", ".end"]
        model_id = -_op_values(sim, "\n".join(lines), [f"i(vd{k})" for k in range(len(vgs))])
        simulated = True
    report = _report("ID(VGS)", [transfer.id], vgs, i_d, model_id, fit, simulated)
    return SpiceModel(
        name=name,
        kind="model",
        device="NMOS",
        params=fit.params,
        text=text,
        origin="ajustado",
        checked=simulated,
        fit=report,
    )


# ---------------------------------------------------------------------------------- dispatch --


def _simulator_available() -> bool:
    try:
        make_backend("batch")
    except CircuitosError:
        return False
    return True


def fit_for(
    record: ComponentRecord,
    curve_ids: list[str],
    name: str | None = None,
    backend: SimulatorBackend | None = None,
) -> SpiceModel:
    """Pick the fitting procedure from the category and the curves' axes."""
    curves = [c for c in record.curves if c.id in curve_ids]
    if len(curves) != len(curve_ids):
        raise FitError("Curva não encontrada no componente")
    cat = record.category
    if cat.startswith("diode."):
        if not curves:
            raise FitError("Selecione a curva IF×VF")
        return fit_diode(record, curves[0], name, backend)
    if cat.startswith("bjt."):
        hfe = next((c for c in curves if "1" in (_dimension(c, "x"), _dimension(c, "y"))), None)
        vbe = next((c for c in curves if c is not hfe), None)
        return fit_bjt(record, hfe, vbe, name, backend)
    if cat.startswith("mosfet."):
        return fit_mosfet(record, curves[0] if curves else None, name, backend)
    raise FitError(f"Ajuste de modelo ainda não disponível para {cat}")


__all__ = ["FitError", "fit_bjt", "fit_diode", "fit_diode_curve", "fit_for", "fit_mosfet", "vt"]
