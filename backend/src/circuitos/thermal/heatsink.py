"""Heat sink choice from the extrusion catalogue (steady state, natural convection).

The catalogue gives Rθsa for a reference length and a reference sink-to-ambient rise ΔT_ref
(HS Dissipadores: 4" = 101,6 mm, ΔT = 75 °C). At a smaller rise, convection is less effective
and Rθsa grows by the manufacturer's correction factor, so the actual rise is found by a fixed
point:

    ΔT = P·Rθsa,cat·k(ΔT)
    Tj = TA + P·(Rθjc + Rθcs) + ΔT

Correction factor: HS Dissipadores, Catálogo 2026-27, rev. S, p. 10 ("Correção da
temperatura"), table ΔT → factor. Only the catalogued length is used: the catalogue states that
Rθsa does not scale linearly with length.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

import pint

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcStep, record
from circuitos.core.units import Q_, parse_unit

HS_REF = BibRef(
    book="HS Dissipadores, Catálogo 2026-27 (rev. S)", chapter="Correção da temperatura, p. 10"
)

# (ΔT in K, factor) from the catalogue table; outside the table the end values are kept.
DT_FACTOR: tuple[tuple[float, float], ...] = (
    (30.0, 1.257),
    (40.0, 1.170),
    (50.0, 1.106),
    (60.0, 1.057),
    (70.0, 1.017),
    (75.0, 1.000),
)


def dt_factor(dT: float, ref: float = 75.0) -> float:
    """Rθsa multiplier at a sink-to-ambient rise dT, relative to the rise ref of the catalogue."""

    def raw(x: float) -> float:
        pts = DT_FACTOR
        if x <= pts[0][0]:
            return pts[0][1]
        if x >= pts[-1][0]:
            return pts[-1][1]
        for (x0, y0), (x1, y1) in itertools.pairwise(pts):
            if x0 <= x <= x1:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return 1.0  # pragma: no cover - the table covers [30, 75]

    return raw(dT) / raw(ref)


@dataclass(frozen=True)
class SinkFit:
    record: ComponentRecord
    rsa_catalogue: float  # K/W at the catalogue condition
    rsa_effective: float  # K/W at the actual rise
    dT: float  # K, sink above ambient
    Tj: float  # °C


def _value(rec: ComponentRecord, key: str) -> pint.Quantity | None:
    p = rec.parameters.get(key)
    if p is None:
        return None
    v = p.typ if p.typ is not None else p.max if p.max is not None else p.min
    return None if v is None else Q_(v, parse_unit(p.unit))


def fit(rec: ComponentRecord, P: float, TA: float, rth_jc: float, rth_cs: float) -> SinkFit | None:
    """Junction temperature with this sink (all in W, °C, K/W); None without Rθsa."""
    rsa = _value(rec, "Rth_sa")
    if rsa is None:
        return None
    ref_q = _value(rec, "dT_ref")
    ref = ref_q.m_as("K") if ref_q is not None else 75.0
    rsa_cat = rsa.m_as("K/W")
    dT = P * rsa_cat
    for _ in range(100):
        new = P * rsa_cat * dt_factor(dT, ref)
        if abs(new - dT) < 1e-9:
            break
        dT = new
    rsa_eff = dT / P if P > 0 else rsa_cat
    return SinkFit(rec, rsa_cat, rsa_eff, dT, TA + P * (rth_jc + rth_cs) + dT)


def choose(
    sinks: Sequence[ComponentRecord],
    P: float,
    TA: float,
    tj_limit: float,
    rth_jc: float,
    rth_cs: float,
) -> SinkFit | None:
    """Smallest released sink (largest Rθsa) keeping Tj ≤ tj_limit; in-stock profiles first."""
    fits = [
        f
        for s in sinks
        if s.selectable
        for f in [fit(s, P, TA, rth_jc, rth_cs)]
        if f is not None and f.Tj <= tj_limit
    ]
    if not fits:
        return None
    fits.sort(key=lambda f: (f.record.lifecycle == "nrnd", -f.rsa_effective, f.record.part_number))
    return fits[0]


def step(
    designator: str,
    f: SinkFit,
    P: pint.Quantity,
    TA: pint.Quantity,
    rth_jc: pint.Quantity,
    rth_cs: pint.Quantity,
) -> CalcStep:
    return record(
        f"Tj_hs_{designator}",
        f"Temperatura de junção de {designator} com o dissipador {f.record.part_number}",
        r"\Delta T_{sa} = P\,R_{\theta sa,cat}\,k(\Delta T_{sa});\quad "
        r"T_j = T_A + P\,(R_{\theta jc} + R_{\theta cs}) + \Delta T_{sa}",
        output=Q_(f.Tj, "degC"),
        inputs={
            "P": P,
            "T_A": TA.to("degC"),
            r"R_{\theta jc}": rth_jc,
            r"R_{\theta cs}": rth_cs,
            r"R_{\theta sa,cat}": Q_(f.rsa_catalogue, "K/W"),
            r"R_{\theta sa}": Q_(f.rsa_effective, "K/W"),
            r"\Delta T_{sa}": Q_(f.dT, "K"),
        },
        assumptions=[
            "um dissipador por dispositivo, no comprimento do catálogo",
            "convecção natural, aletas na vertical",
            "k(ΔT): correção do fabricante para elevação menor que a do catálogo",
            "valores do fabricante são indicativos; confirmar em protótipo",
        ],
        reference=HS_REF,
    ).step
