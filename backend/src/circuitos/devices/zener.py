"""Zener diode model for the device bench (BD-ZENER).

Didactic model built from two junction diodes, so the bench and ngspice share the same equations
(verified in tests/analytic_vs_sim):

    forward branch:  ordinary junction diode (Shockley + Rs, SPICE temperature law)
    reverse branch:  ideal source VZ0(T) in series with a diode (Is_r, n_r) and Rz

    IZ(VR) = I_r(VR − VZ0(T)) − I_f(−VR)
    VZ0(T) = VZ0·[1 + TC·(T − T0)]

Small-signal (dynamic) resistance of the reverse branch at IZ:

    rz = n_r·Vt / (IZ + Is_r) + Rz

This is the piecewise-linear Zener equivalent (VZ0 in series with rz) found in Boylestad &
Nashelsky, *Electronic Devices and Circuit Theory* (Zener diode section), with an exponential knee
added so the curve is continuous. Section and equation numbers still to be checked against the
printed book (BibRef.verified = False).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pint

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, require
from circuitos.devices.diode import DiodeModel, current, thermal_voltage

T0_C = 27.0  # °C: reference temperature of VZ0 and TC (SPICE TNOM)

ZENER_REF = BibRef(
    book="Boylestad & Nashelsky, Electronic Devices and Circuit Theory", chapter="Zener diodes"
)


@dataclass(frozen=True)
class ZenerModel:
    """Model parameters. They are *model* values, not datasheet ratings."""

    VZ0: pint.Quantity  # breakdown source voltage at T0
    Rz: pint.Quantity  # ohmic part of the dynamic resistance
    Is_r: pint.Quantity  # saturation current of the reverse (breakdown) branch
    n_r: float  # emission coefficient of the reverse branch (sets the knee sharpness)
    TC: pint.Quantity  # temperature coefficient of VZ0, in %/K
    forward: DiodeModel

    def __post_init__(self) -> None:
        require(self.VZ0, "V", "VZ0")
        require(self.Rz, "ohm", "Rz")
        require(self.Is_r, "A", "Is_r")
        require(self.TC, "1/K", "TC")
        if not self.VZ0.magnitude > 0 or self.Rz.magnitude < 0 or not self.Is_r.magnitude > 0:
            raise ValueError("VZ0 e Is_r devem ser positivos e Rz não negativo")
        if not self.n_r > 0:
            raise ValueError("n_r deve ser positivo")

    @property
    def reverse_branch(self) -> DiodeModel:
        # EG = XTI = 0: the branch saturation current does not vary with temperature; the
        # Zener temperature drift is carried by VZ0(T).
        return DiodeModel(Is=self.Is_r, n=self.n_r, Rs=self.Rz, Eg=Q_(0, "eV"), XTI=0.0)

    def vz0_at(self, T: pint.Quantity) -> pint.Quantity:
        dt = T.to("degC").magnitude - T0_C
        tc = self.TC.m_as("1/K")
        return Q_(self.VZ0.m_as("V") * (1 + tc * dt), "V")

    def spice(self, name: str = "DZENER") -> str:
        """Subcircuit with pins (anode, cathode)."""
        tc = self.TC.m_as("1/K")
        vz0 = self.VZ0.m_as("V")
        return "\n".join(
            [
                f".subckt {name} a k",
                "D1 a k DZF",
                "DR k n1 DZR",
                f"BZ n1 a V={vz0:.9g}*(1+{tc:.9g}*(temper-{T0_C:g}))",
                self.forward.spice("DZF"),
                self.reverse_branch.spice("DZR"),
                ".ends",
            ]
        )


def reverse_current(model: ZenerModel, vr: pint.Quantity, T: pint.Quantity) -> pint.Quantity:
    """IZ (cathode → anode) for a reverse voltage VR = V(k) − V(a)."""
    require(vr, "V", "VR")
    v = np.asarray(vr.m_as("V"), dtype=float)
    vz0 = model.vz0_at(T).m_as("V")
    i_rev = current(model.reverse_branch, Q_(v - vz0, "V"), T).m_as("A")
    i_fwd = current(model.forward, Q_(-v, "V"), T).m_as("A")
    out = np.asarray(i_rev, dtype=float) - np.asarray(i_fwd, dtype=float)
    return Q_(out if np.ndim(v) else float(out), "A")


def zener_voltage(model: ZenerModel, iz: pint.Quantity, T: pint.Quantity) -> pint.Quantity:
    """VZ at a given IZ (reverse branch only; the forward diode leakage is negligible)."""
    require(iz, "A", "IZ")
    i = iz.m_as("A")
    nvt = model.n_r * thermal_voltage(T).m_as("V")
    vz = (
        model.vz0_at(T).m_as("V")
        + nvt * np.log1p(i / model.Is_r.m_as("A"))
        + i * model.Rz.m_as("ohm")
    )
    return Q_(vz, "V")


def zener_voltage_step(
    model: ZenerModel, iz: pint.Quantity, T: pint.Quantity
) -> Calculated[pint.Quantity]:
    return record(
        "VZ",
        "Tensão Zener na corrente de operação",
        r"V_Z = V_{Z0}(T) + n_r V_T \ln\left(\frac{I_Z}{I_{S,r}} + 1\right) + I_Z R_z",
        output=zener_voltage(model, iz, T),
        inputs={
            r"V_{Z0}(T)": model.vz0_at(T),
            "I_Z": iz,
            r"I_{S,r}": model.Is_r,
            "R_z": model.Rz,
            "V_T": thermal_voltage(T).to("mV"),
        },
        assumptions=[f"n_r = {model.n_r:g}", "fuga do ramo direto desprezada"],
        reference=ZENER_REF,
    )


def dynamic_resistance(
    model: ZenerModel, iz: pint.Quantity, T: pint.Quantity
) -> Calculated[pint.Quantity]:
    require(iz, "A", "IZ")
    vt = thermal_voltage(T)
    rz = Q_(
        model.n_r * vt.m_as("V") / (iz.m_as("A") + model.Is_r.m_as("A")) + model.Rz.m_as("ohm"),
        "ohm",
    )
    return record(
        "rz",
        "Resistência dinâmica no ponto de operação",
        r"r_z = \frac{dV_Z}{dI_Z} = \frac{n_r V_T}{I_Z + I_{S,r}} + R_z",
        output=rz,
        inputs={"I_Z": iz, "V_T": vt.to("mV"), "R_z": model.Rz},
        assumptions=[f"n_r = {model.n_r:g}"],
        reference=ZENER_REF,
    )


@dataclass(frozen=True)
class ZenerFit:
    model: ZenerModel
    steps: list[Calculated[pint.Quantity]]
    warnings: list[str]


def fit_to_datasheet(
    vz: pint.Quantity,
    izt: pint.Quantity,
    zzt: pint.Quantity,
    T: pint.Quantity,
    *,
    n_r: float,
    Is_r: pint.Quantity,
    TC: pint.Quantity,
    forward: DiodeModel,
) -> ZenerFit:
    """Choose Rz and VZ0 so the model gives VZ and rz = ZZT at IZT (datasheet test point).

    Rz = ZZT − n_r·Vt/(IZT + Is_r); VZ0 = VZ − n_r·Vt·ln(IZT/Is_r + 1) − IZT·Rz, referred to
    T0 through TC.
    """
    require(vz, "V", "VZ")
    require(izt, "A", "IZT")
    require(zzt, "ohm", "ZZT")
    vt = thermal_voltage(T)
    warnings: list[str] = []
    knee: pint.Quantity = (n_r * vt / (izt + Is_r)).to("ohm")
    rz_val: pint.Quantity = (zzt - knee).to("ohm")
    if rz_val.magnitude < 0:
        warnings.append(
            f"ZZT ({zzt.m_as('ohm'):g} Ω) é menor que a parcela exponencial n_r·Vt/IZT "
            f"({knee.m_as('ohm'):.3g} Ω): Rz foi limitado a 0; "
            "reduza n_r para acompanhar o datasheet."
        )
        rz_val = Q_(0.0, "ohm")
    rz_step = record(
        "Rz_fit",
        "Parcela ôhmica da resistência dinâmica (ajuste a ZZT)",
        r"R_z = Z_{ZT} - \frac{n_r V_T}{I_{ZT} + I_{S,r}}",
        output=rz_val,
        inputs={"Z_{ZT}": zzt, "I_{ZT}": izt, "V_T": vt.to("mV"), r"I_{S,r}": Is_r},
        assumptions=[f"n_r = {n_r:g}", "ZZT medido em pequeno sinal no ponto IZT"],
        reference=ZENER_REF,
    )
    nvt = n_r * vt.m_as("V")
    vz0_t = (
        vz.m_as("V")
        - nvt * float(np.log1p(izt.m_as("A") / Is_r.m_as("A")))
        - izt.m_as("A") * rz_val.m_as("ohm")
    )
    dt = T.to("degC").magnitude - T0_C
    vz0 = Q_(vz0_t / (1 + TC.m_as("1/K") * dt), "V")
    vz0_step = record(
        "VZ0_fit",
        "Tensão da fonte de ruptura (ajuste a VZ em IZT)",
        r"V_{Z0}(T_0) = \frac{V_Z - n_r V_T \ln\left(\frac{I_{ZT}}{I_{S,r}}+1\right) - I_{ZT} R_z}"
        r"{1 + TC\,(T - T_0)}",
        output=vz0,
        inputs={
            "V_Z": vz,
            "I_{ZT}": izt,
            "R_z": rz_val,
            "T": T.to("degC"),
            "T_0": Q_(T0_C, "degC"),
            "TC": TC.to("percent/K"),
        },
        assumptions=[f"n_r = {n_r:g}"],
        reference=ZENER_REF,
    )
    model = ZenerModel(VZ0=vz0, Rz=rz_val, Is_r=Is_r, n_r=n_r, TC=TC, forward=forward)
    return ZenerFit(model=model, steps=[rz_step, vz0_step], warnings=warnings)
