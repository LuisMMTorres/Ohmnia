"""Round magnet wire: AWG geometry, copper resistance and skin depth.

AWG diameters follow the definition of the gauge, d(n) = 0,127 mm · 92^((36 − n)/39)
(ASTM B258, "Standard Specification for Standard Nominal Diameters and Cross-Sectional Areas of
AWG Sizes of Solid Round Wires"). Copper resistivity is the International Annealed Copper
Standard, 1/58 Ω·mm²/m at 20 °C with temperature coefficient 0,00393 /K (IEC 60028). Skin depth
δ = √(ρ/(π f μ0)) (Erickson & Maksimović, *Fundamentals of Power Electronics*, 2nd ed., ch. 13,
"Basic magnetics theory", skin effect). Enamel thickness is not modelled: the window fill factor
Ku covers insulation, bobbin and winding gaps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

RHO_CU_20 = 1 / 58e6  # Ω·m, IACS (IEC 60028)
ALPHA_CU = 0.00393  # 1/K
MU0 = 4e-7 * math.pi  # H/m (classical value; the 2019 SI value differs by < 1e-9)
GAUGES = tuple(range(10, 41))


def awg_diameter(n: int) -> float:
    """Bare copper diameter in m."""
    return float(0.127e-3 * 92 ** ((36 - n) / 39))


def awg_area(n: int) -> float:
    """Bare copper cross-section in m²."""
    return math.pi * awg_diameter(n) ** 2 / 4


def rho_cu(T: float) -> float:
    """Copper resistivity in Ω·m at T in °C."""
    return RHO_CU_20 * (1 + ALPHA_CU * (T - 20.0))


def skin_depth(f: float, T: float = 20.0) -> float:
    """Skin depth in m at frequency f (Hz)."""
    return math.sqrt(rho_cu(T) / (math.pi * f * MU0))


@dataclass(frozen=True)
class Strand:
    awg: int
    n: int  # parallel strands
    area: float  # m², total copper

    @property
    def d(self) -> float:
        return awg_diameter(self.awg)

    def r_per_m(self, T: float) -> float:
        return rho_cu(T) / self.area


def choose_strand(i_rms: float, J: float, f: float, T: float) -> Strand:
    """Copper for i_rms at density J (A/m²) with every strand thinner than 2δ at f.

    One wire when a gauge with enough area still fits 2δ (the thinnest such gauge); otherwise
    parallel strands of the thickest gauge within 2δ.
    """
    need = i_rms / J
    d_max = 2 * skin_depth(f, T) if f > 0 else math.inf
    fit = [g for g in GAUGES if awg_diameter(g) <= d_max]
    gauge_max = fit[0] if fit else GAUGES[-1]
    single = [g for g in fit if awg_area(g) >= need]
    if single:
        g = single[-1]
        return Strand(awg=g, n=1, area=awg_area(g))
    n = max(1, math.ceil(need / awg_area(gauge_max) - 1e-9))
    return Strand(awg=gauge_max, n=n, area=n * awg_area(gauge_max))
