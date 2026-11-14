"""Abrupt PN junction physics for the device bench (BD-PN).

    ni(T)  = B·T^(3/2)·exp(−Eg / (2kT))                    intrinsic carrier concentration
    V0     = VT·ln(NA·ND / ni²)                            built-in voltage
    W      = sqrt(2·εs/q·(1/NA + 1/ND)·(V0 + VR))          depletion width (reverse bias VR)
    xn     = W·NA/(NA + ND),  xp = W·ND/(NA + ND)          extension into each side
    Emax   = 2·(V0 + VR)/W                                 peak electric field
    Cj     = εs·A/W = Cj0/sqrt(1 + VR/V0)                  depletion capacitance
    IS     = A·q·ni²·(Dp/(Lp·ND) + Dn/(Ln·NA))             saturation current (long diode)
    I      = IS·(exp(V/VT) − 1)                            Shockley equation

The depletion capacitance is the SPICE junction capacitance with CJO = Cj0, VJ = V0, M = 0.5, so
the bench is verified against ngspice (small-signal AC) in tests/analytic_vs_sim.

Material constants (B, Eg, εr of silicon) are defaults that the bench lets the user change. The
values and equations follow Sedra & Smith, *Microelectronic Circuits*, semiconductor chapter
(B = 7.3·10¹⁵ cm⁻³·K⁻³ᐟ², Eg = 1.12 eV, εr = 11.7); chapter and equation numbers still to be
checked against the printed book (BibRef.verified = False).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pint

from circuitos.core.calc import BibRef, Calculated, record
from circuitos.core.units import Q_, require

PN_REF = BibRef(book="Sedra & Smith, Microelectronic Circuits", chapter="Semiconductors")

Q_E = 1.602176634e-19  # C (exact, SI 2019)
K_B = 1.380649e-23  # J/K (exact, SI 2019)
EPS0 = 8.8541878128e-12  # F/m (CODATA 2018)


@dataclass(frozen=True)
class Material:
    B: pint.Quantity  # cm^-3 K^-3/2
    Eg: pint.Quantity  # eV
    eps_r: float

    def __post_init__(self) -> None:
        require(self.B, "1/cm**3/K**1.5", "B")
        require(self.Eg, "eV", "Eg")
        if not (self.B.magnitude > 0 and self.Eg.magnitude > 0 and self.eps_r > 0):
            raise ValueError("B, Eg e εr devem ser positivos")

    @property
    def eps(self) -> float:
        return self.eps_r * EPS0


SILICON = Material(B=Q_(7.3e15, "1/cm**3/K**1.5"), Eg=Q_(1.12, "eV"), eps_r=11.7)


@dataclass(frozen=True)
class Junction:
    NA: pint.Quantity  # acceptors (p side)
    ND: pint.Quantity  # donors (n side)
    area: pint.Quantity
    Dn: pint.Quantity  # electron diffusion constant (in p side)
    Dp: pint.Quantity  # hole diffusion constant (in n side)
    Ln: pint.Quantity  # electron diffusion length
    Lp: pint.Quantity  # hole diffusion length
    material: Material = SILICON

    def __post_init__(self) -> None:
        for value, unit, name in (
            (self.NA, "1/cm**3", "NA"),
            (self.ND, "1/cm**3", "ND"),
            (self.area, "cm**2", "A"),
            (self.Dn, "cm**2/s", "Dn"),
            (self.Dp, "cm**2/s", "Dp"),
            (self.Ln, "um", "Ln"),
            (self.Lp, "um", "Lp"),
        ):
            require(value, unit, name)
            if not value.magnitude > 0:
                raise ValueError(f"{name} deve ser positivo")


def _kelvin(T: pint.Quantity) -> float:
    return float(T.to("K").magnitude)


def thermal_voltage_si(T: pint.Quantity) -> float:
    return K_B * _kelvin(T) / Q_E


def ni_m3(mat: Material, T: pint.Quantity | np.ndarray) -> np.ndarray:
    """ni in m⁻³ (vectorised over T in K when T is a quantity array)."""
    t = np.asarray(T.to("K").magnitude if isinstance(T, pint.Quantity) else T, dtype=float)
    b = mat.B.m_as("1/m**3/K**1.5")
    eg = mat.Eg.m_as("eV") * Q_E
    return np.asarray(b * t**1.5 * np.exp(-eg / (2 * K_B * t)))


def intrinsic_concentration(mat: Material, T: pint.Quantity) -> Calculated[pint.Quantity]:
    return record(
        "ni",
        "Concentração intrínseca de portadores",
        r"n_i = B\,T^{3/2}\,e^{-E_g/(2kT)}",
        output=Q_(float(ni_m3(mat, T)), "1/m**3").to("1/cm**3"),
        inputs={"B": mat.B, "T": T.to("K"), "E_g": mat.Eg},
        assumptions=["B e Eg constantes com a temperatura"],
        reference=PN_REF,
    )


def built_in_voltage(j: Junction, T: pint.Quantity) -> Calculated[pint.Quantity]:
    ni = float(ni_m3(j.material, T))
    na = j.NA.m_as("1/m**3")
    nd = j.ND.m_as("1/m**3")
    v0 = thermal_voltage_si(T) * math.log(na * nd / ni**2)
    if v0 <= 0:
        raise ValueError("Dopagens menores que ni: não há junção (V0 ≤ 0)")
    return record(
        "V0",
        "Tensão de barreira (potencial interno)",
        r"V_0 = V_T \ln\frac{N_A N_D}{n_i^2}",
        output=Q_(v0, "V"),
        inputs={
            "N_A": j.NA,
            "N_D": j.ND,
            "n_i": Q_(ni, "1/m**3").to("1/cm**3"),
            "V_T": Q_(thermal_voltage_si(T), "V").to("mV"),
        },
        assumptions=["junção abrupta", "ionização completa dos dopantes"],
        reference=PN_REF,
    )


def _v0(j: Junction, T: pint.Quantity) -> float:
    return float(built_in_voltage(j, T).value.m_as("V"))


def _w(j: Junction, v0: float, vr: np.ndarray) -> np.ndarray:
    na = j.NA.m_as("1/m**3")
    nd = j.ND.m_as("1/m**3")
    total = v0 + vr
    if np.any(total <= 0):
        raise ValueError("V0 + VR deve ser positivo (polarização direta acima de V0)")
    return np.asarray(np.sqrt(2 * j.material.eps / Q_E * (1 / na + 1 / nd) * total))


def depletion_width(
    j: Junction, vr: pint.Quantity, T: pint.Quantity
) -> tuple[pint.Quantity, pint.Quantity, pint.Quantity]:
    """W, xn and xp for a reverse voltage VR (scalar or array)."""
    require(vr, "V", "VR")
    v = np.asarray(vr.m_as("V"), dtype=float)
    w = _w(j, _v0(j, T), v)
    na = j.NA.m_as("1/m**3")
    nd = j.ND.m_as("1/m**3")
    w_q = Q_(w if w.ndim else float(w), "m").to("um")
    return w_q, w_q * na / (na + nd), w_q * nd / (na + nd)


def capacitance(j: Junction, vr: pint.Quantity, T: pint.Quantity) -> pint.Quantity:
    w = depletion_width(j, vr, T)[0].m_as("m")
    c = j.material.eps * j.area.m_as("m**2") / w
    return Q_(c, "F").to("pF")


def peak_field(j: Junction, vr: pint.Quantity, T: pint.Quantity) -> pint.Quantity:
    v = np.asarray(vr.m_as("V"), dtype=float)
    v0 = _v0(j, T)
    e = 2 * (v0 + v) / _w(j, v0, v)
    return Q_(e if e.ndim else float(e), "V/m").to("kV/cm")


def saturation_current_si(j: Junction, T: pint.Quantity) -> float:
    ni = float(ni_m3(j.material, T))
    a = j.area.m_as("m**2")
    term_p = j.Dp.m_as("m**2/s") / (j.Lp.m_as("m") * j.ND.m_as("1/m**3"))
    term_n = j.Dn.m_as("m**2/s") / (j.Ln.m_as("m") * j.NA.m_as("1/m**3"))
    return float(a * Q_E * ni**2 * (term_p + term_n))


def current(j: Junction, v: pint.Quantity, T: pint.Quantity) -> pint.Quantity:
    require(v, "V", "V")
    vv = np.asarray(v.m_as("V"), dtype=float)
    i = saturation_current_si(j, T) * np.expm1(np.minimum(vv / thermal_voltage_si(T), 200))
    return Q_(i if np.ndim(i) else float(i), "A")


# ---------------------------------------------------------------- steps at an operating point


def depletion_steps(
    j: Junction, vr: pint.Quantity, T: pint.Quantity
) -> list[Calculated[pint.Quantity]]:
    v0 = Q_(_v0(j, T), "V")
    w, xn, _ = depletion_width(j, vr, T)
    eps = Q_(j.material.eps, "F/m")
    base = {"V_0": v0, "V_R": vr}
    return [
        record(
            "W",
            "Largura da região de depleção",
            r"W = \sqrt{\frac{2\varepsilon_s}{q}\left(\frac{1}{N_A} + \frac{1}{N_D}\right)"
            r"(V_0 + V_R)}",
            output=w,
            inputs={r"\varepsilon_s": eps.to("pF/cm"), "N_A": j.NA, "N_D": j.ND, **base},
            assumptions=["junção abrupta", "aproximação de depleção total"],
            reference=PN_REF,
        ),
        record(
            "xn",
            "Extensão da depleção no lado n",
            r"x_n = W\,\frac{N_A}{N_A + N_D}",
            output=xn,
            inputs={"W": w, "N_A": j.NA, "N_D": j.ND},
            assumptions=["neutralidade de carga: x_n·N_D = x_p·N_A"],
            reference=PN_REF,
        ),
        record(
            "Emax",
            "Campo elétrico máximo na junção",
            r"E_{max} = \frac{2(V_0 + V_R)}{W}",
            output=peak_field(j, vr, T),
            inputs={**base, "W": w},
            assumptions=["perfil de campo triangular (junção abrupta)"],
            reference=PN_REF,
        ),
        record(
            "Cj",
            "Capacitância de depleção",
            r"C_j = \frac{\varepsilon_s A}{W} = \frac{C_{j0}}{\sqrt{1 + V_R/V_0}}",
            output=capacitance(j, vr, T),
            inputs={r"\varepsilon_s": eps.to("pF/cm"), "A": j.area, "W": w},
            assumptions=["capacitor de placas paralelas separadas por W"],
            reference=PN_REF,
        ),
    ]


def saturation_current_step(j: Junction, T: pint.Quantity) -> Calculated[pint.Quantity]:
    ni = Q_(float(ni_m3(j.material, T)), "1/m**3").to("1/cm**3")
    return record(
        "IS",
        "Corrente de saturação (diodo longo)",
        r"I_S = A\,q\,n_i^2\left(\frac{D_p}{L_p N_D} + \frac{D_n}{L_n N_A}\right)",
        output=Q_(saturation_current_si(j, T), "A").to("fA"),
        inputs={
            "A": j.area,
            "n_i": ni,
            "D_p": j.Dp,
            "L_p": j.Lp,
            "N_D": j.ND,
            "D_n": j.Dn,
            "L_n": j.Ln,
            "N_A": j.NA,
        },
        assumptions=["regiões neutras longas (W_n ≫ L_p, W_p ≫ L_n)", "baixa injeção"],
        reference=PN_REF,
    )


def spice(j: Junction, T: pint.Quantity, name: str = "DPN") -> str:
    """Equivalent SPICE diode (IS and the depletion capacitance) at temperature T."""
    v0 = _v0(j, T)
    cj0 = capacitance(j, Q_(0.0, "V"), T).m_as("F")
    return (
        f".model {name} D(IS={saturation_current_si(j, T):.6g} N=1 CJO={cj0:.6g} VJ={v0:.6g} M=0.5)"
    )
