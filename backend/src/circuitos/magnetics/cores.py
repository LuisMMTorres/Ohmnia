"""Core geometry and losses from the catalogue (cores, bobbins, materials).

The winding window always comes from the drawing dimensions of the core datasheet, so every core
is compared on the same basis (the window utilisation factor Ku covers bobbin, insulation and
gaps). The mean turn length comes from the bobbin when the catalogue has one for the core size,
else from the same dimensions:

- E core (Ferroxcube drawing: B inner width, C centre-leg width, E inner height of a half, F
  depth): Wa = E·(B − C) for the pair (two half windows of height E side by side, one per side
  of the centre leg); MLT = 2(C + F) + π(B − C)/2, a turn at the middle of the window.
- ETD core (D2 inner width, D3 round centre-leg diameter, F inner height of a half):
  Wa = F·(D2 − D3); MLT = π(D2 + D3)/2.

Core loss uses the Steinmetz form Pv = k·f^α·B̂^β fitted exactly to the material's tabulated
points (three points: k, α, β; two points at one frequency: β only), anchored on the core's own
maximum loss at the datasheet point (Ferroxcube gives W per set at 100 kHz, 200 mT, 100 °C).
Steinmetz form: Erickson & Maksimović, *Fundamentals of Power Electronics*, 2nd ed., ch. 13
(core loss). The anchor makes the estimate a maximum, like the datasheet value it scales.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from circuitos.components.models import ComponentRecord, Parameter
from circuitos.core.units import Q_, parse_unit


def _v(p: Parameter | None, prefer: tuple[str, ...] = ("typ", "max", "min")) -> float | None:
    if p is None:
        return None
    for k in prefer:
        x = getattr(p, k)
        if x is not None:
            return float(Q_(x, parse_unit(p.unit)).to_base_units().magnitude)
    return None


def _tag(rec: ComponentRecord, key: str) -> str | None:
    return next((t.split(":", 1)[1] for t in rec.tags if t.startswith(key + ":")), None)


def _cond(p: Parameter, key: str) -> float:
    return float(p.conditions[key].to_pint().to_base_units().magnitude)


@dataclass(frozen=True)
class Steinmetz:
    """Pv = k·f^α·B^β in W/m³ (f in Hz, B in T); alpha None when the data give only β."""

    k: float
    alpha: float | None
    beta: float
    material: str


def steinmetz(rec: ComponentRecord) -> Steinmetz:
    pts = []
    for key in ("Pv_1", "Pv_2", "Pv_3"):
        p = rec.parameters.get(key)
        if p is not None and (val := _v(p)) is not None:
            pts.append((_cond(p, "f"), _cond(p, "B"), val))
    if len(pts) < 2:
        raise ValueError(f"{rec.part_number}: menos de dois pontos de perdas")
    same_f = [q for q in pts if q[0] == pts[0][0]]
    (f1, b1, p1), (_, b2, p2) = same_f[0], same_f[1]
    beta = math.log(p2 / p1) / math.log(b2 / b1)
    alpha = None
    other = [q for q in pts if q[0] != f1]
    if other:
        f3, b3, p3 = other[0]
        alpha = math.log(p3 / (p1 * (b3 / b1) ** beta)) / math.log(f3 / f1)
    k = p1 / ((f1 ** (alpha or 0.0)) * b1**beta)
    return Steinmetz(k=k, alpha=alpha, beta=beta, material=rec.part_number)


@dataclass(frozen=True)
class Core:
    record: ComponentRecord
    size: str
    shape: str
    material: str
    Ae: float  # m²
    le: float  # m
    Ve: float  # m³
    AL: float  # H/turn², ungapped
    Bsat: float  # T, minimum at 100 °C
    Wa: float  # m², winding window
    MLT: float  # m
    window_from: str  # source of the mean turn length: "carretel <pn>" or "cotas do núcleo"
    P_ref: float | None  # W per set, maximum at (f_ref, B_ref, 100 °C)
    f_ref: float | None
    B_ref: float | None
    area_surface: float  # m², outside of the assembled core (for the temperature rise)
    bobbin: ComponentRecord | None

    @property
    def Ap(self) -> float:
        return self.Wa * self.Ae

    @property
    def mu_e(self) -> float:
        """Effective permeability of the ungapped set, from its AL: μe = AL·le/(μ0·Ae)."""
        return self.AL * self.le / (4e-7 * math.pi * self.Ae)

    def core_loss(
        self, f: float, B_pk: float, st: Steinmetz | None, alpha_default: float | None
    ) -> float:
        """Maximum core loss in W at peak AC flux B_pk (sinusoidal-equivalent excitation)."""
        if self.P_ref is None or self.f_ref is None or self.B_ref is None:
            raise ValueError(f"{self.record.part_number}: sem perdas no datasheet")
        if st is None:
            raise ValueError(f"{self.record.part_number}: material sem pontos de perdas")
        alpha = st.alpha if st.alpha is not None else alpha_default
        if alpha is None:
            raise ValueError(f"{self.record.part_number}: sem expoente de frequência")
        return float(self.P_ref * (f / self.f_ref) ** alpha * (B_pk / self.B_ref) ** st.beta)


def _dim(rec: ComponentRecord, key: str) -> float | None:
    return _v(rec.parameters.get(f"dim_{key}"), ("typ", "max", "min"))


def core_from(rec: ComponentRecord, bobbins: Sequence[ComponentRecord] = ()) -> Core:
    p = rec.parameters
    size = _tag(rec, "size") or rec.part_number
    shape = _tag(rec, "shape") or "E"
    if shape == "ETD":
        f, d2, d3, a, e, b = (_dim(rec, k) for k in ("F", "D2", "D3", "A", "E", "B"))
        assert f and d2 and d3 and a and e and b
        wa, mlt = f * (d2 - d3), math.pi * (d2 + d3) / 2
        w, h, dep = a, 2 * e, b
    else:
        b, c, e, f, a, d = (_dim(rec, k) for k in ("B", "C", "E", "F", "A", "D"))
        assert b and c and e and f and a and d
        wa, mlt = e * (b - c), 2 * (c + f) + math.pi * (b - c) / 2
        w, h, dep = a, 2 * d, f
    src = "cotas do núcleo"
    bob = next((x for x in bobbins if _tag(x, "size") == size), None)
    if bob is not None:
        mlt = _v(bob.parameters.get("lw")) or mlt
        src = f"carretel {bob.part_number}"
    pc = p.get("Pcore")
    return Core(
        record=rec,
        size=size,
        shape=shape,
        material=_tag(rec, "material") or "",
        Ae=_v(p["Ae"]) or 0.0,
        le=_v(p["le"]) or 0.0,
        Ve=_v(p["Ve"]) or 0.0,
        AL=_v(p["AL"]) or 0.0,
        Bsat=_v(p["Bsat"], ("min", "typ")) or 0.0,
        Wa=wa,
        MLT=mlt,
        window_from=src,
        P_ref=_v(pc, ("max", "typ")) if pc else None,
        f_ref=_cond(pc, "f") if pc else None,
        B_ref=_cond(pc, "B") if pc else None,
        area_surface=2 * (w * h + h * dep + w * dep),
        bobbin=bob,
    )
