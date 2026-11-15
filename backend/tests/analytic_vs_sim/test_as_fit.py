"""AS-FIT: model fitting recovers known parameters and ngspice reproduces the curve.

The "datasheet" curves are produced by ngspice from fictitious models with known parameters
(TRUE_*), so the fit can be judged against the truth. Tolerances: parameters within the limits
below; simulated error of the fitted model at the curve points ≤ 1 % (diode VF, MOSFET ID) and
≤ 3 % (hFE, two-parameter roll-off).
"""

from __future__ import annotations

import numpy as np
import pytest

from circuitos.components.models import (
    AxisSpec,
    ComponentRecord,
    Curve,
    DatasheetRef,
    SourceRef,
)
from circuitos.core.units import QuantityModel
from circuitos.datasheets.fit import fit_bjt, fit_diode, fit_for, fit_mosfet
from circuitos.simulation.backend import make_backend

pytestmark = pytest.mark.ngspice

SRC = SourceRef(datasheet_id="ds", page=3, location="Fig. 1")


def _record(category: str, **kw: object) -> ComponentRecord:
    return ComponentRecord(
        category=category,
        schema_version="1.0",
        manufacturer="Teste",
        part_number="TESTE-1",
        datasheets=[DatasheetRef(id="ds", manufacturer="Teste")],
        **kw,  # type: ignore[arg-type]
    )


def _op(netlist: str, names: list[str]) -> np.ndarray:
    plot = make_backend("batch").run(netlist).plot("op")
    return np.array([float(np.real(plot[n].data[0])) for n in names])


def _curve(
    name: str, x: AxisSpec, y: AxisSpec, pts: list[tuple[float, float]], **fam: QuantityModel
) -> Curve:
    return Curve(name=name, x=x, y=y, points=pts, source=SRC, digitized_by="teste", family=fam)


T25 = QuantityModel(value=25, unit="degC")


def test_as_fit_diode() -> None:
    true = ".model DTRUE D(IS=5n N=1.9 RS=0.03 TNOM=25)"
    i = np.logspace(-2, 1, 12)
    lines = ["d", true] + [f"I{k} 0 a{k} DC {v:.6g}\nD{k} a{k} 0 DTRUE" for k, v in enumerate(i)]
    v = _op("\n".join([*lines, ".options temp=25", ".op"]), [f"v(a{k})" for k in range(len(i))])
    # figure as datasheets draw it: VF on x (V), IF on y (A, log)
    curve = _curve(
        "IF×VF",
        AxisSpec(quantity="VF", unit="V"),
        AxisSpec(quantity="IF", unit="A", scale="log"),
        list(zip(v.tolist(), i.tolist(), strict=True)),
        Tj=T25,
    )
    model = fit_diode(_record("diode.rectifier", curves=[curve]), curve)
    assert model.params["IS"] == pytest.approx(5e-9, rel=0.15)
    assert model.params["N"] == pytest.approx(1.9, rel=0.02)
    assert model.params["RS"] == pytest.approx(0.03, rel=0.05)
    assert model.fit is not None and model.fit.simulated
    assert model.fit.max_error_pct < 1.0
    assert model.checked


def test_as_fit_bjt_hfe_rolloff() -> None:
    true = ".model QTRUE NPN(IS=2e-14 BF=180 IKF=0.4 TNOM=25)"
    ic = np.logspace(-3, 0, 10)
    lines = ["q", true]
    for k, c in enumerate(ic):
        lines += [
            f"VC{k} c{k} 0 DC 5",
            f"VB{k} b{k} 0 DC 0",
            f"Q{k} c{k} b{k} e{k} QTRUE",
            f"IE{k} e{k} 0 DC {c:.6g}",
        ]
    names = [f"i(vc{k})" for k in range(len(ic))] + [f"i(vb{k})" for k in range(len(ic))]
    vals = _op("\n".join([*lines, ".options temp=25", ".op"]), names)
    ic_sim = -vals[: len(ic)]
    hfe = vals[: len(ic)] / vals[len(ic) :]
    curve = _curve(
        "hFE×IC",
        AxisSpec(quantity="IC", unit="A", scale="log"),
        AxisSpec(quantity="hFE", unit="dimensionless"),
        list(zip(ic_sim.tolist(), hfe.tolist(), strict=True)),
        Tj=T25,
        VCE=QuantityModel(value=5, unit="V"),
    )
    vbe_on = {
        "VBE(on)": {
            "symbol": "VBE(on)",
            "typ": 0.65,
            "unit": "V",
            "status": "extraido",
            "conditions": {"IC": {"value": 10, "unit": "mA"}},
            "source": {"datasheet_id": "ds", "page": 2},
        }
    }
    rec = _record("bjt.npn", curves=[curve], parameters=vbe_on)
    model = fit_bjt(rec, hfe_curve=curve)
    assert model.params["BF"] == pytest.approx(180, rel=0.05)
    assert model.params["IKF"] == pytest.approx(0.4, rel=0.15)
    assert model.fit is not None and model.fit.simulated
    assert model.fit.max_error_pct < 3.0


def test_as_fit_mosfet_transfer() -> None:
    true = ".model MTRUE NMOS(LEVEL=1 VTO=3.5 KP=2 LAMBDA=0 TNOM=25)"
    vgs = np.linspace(4.0, 7.0, 8)
    lines = ["m", true]
    for k, vg in enumerate(vgs):
        lines += [f"VD{k} d{k} 0 DC 10", f"VG{k} g{k} 0 DC {vg:.6g}", f"M{k} d{k} g{k} 0 0 MTRUE"]
    i_d = -_op(
        "\n".join([*lines, ".options temp=25", ".op"]), [f"i(vd{k})" for k in range(len(vgs))]
    )
    curve = _curve(
        "ID×VGS",
        AxisSpec(quantity="VGS", unit="V"),
        AxisSpec(quantity="ID", unit="A"),
        list(zip(vgs.tolist(), i_d.tolist(), strict=True)),
        Tj=T25,
        VDS=QuantityModel(value=10, unit="V"),
    )
    rec = _record("mosfet.n", curves=[curve])
    model = fit_for(rec, [curve.id])
    assert model.params["VTO"] == pytest.approx(3.5, rel=0.01)
    assert model.params["KP"] == pytest.approx(2.0, rel=0.02)
    assert model.fit is not None and model.fit.max_error_pct < 1.0
    # the same through the explicit entry point
    assert fit_mosfet(rec, curve).params["VTO"] == pytest.approx(model.params["VTO"])
