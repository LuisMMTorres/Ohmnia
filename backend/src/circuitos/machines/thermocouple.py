"""Thermocouple reference functions: NIST ITS-90 polynomials (IEC 60584-1 has the same ones).

E(T) in mV with the reference junction at 0 °C, T in °C (ITS-90):

    E = sum c_i T^i                      (all types and ranges here)
      + a0 exp(a1 (T - a2)^2)            (type K, 0 to 1372 °C only)

Coefficients: NIST, *Temperature-Electromotive Force Reference Functions and Tables for the
Letter-Designated Thermocouple Types Based on the ITS-90*, Monograph 175 (1993), as published
in the NIST ITS-90 Thermocouple Database (SRD 60). Taken from the data tables of the public
domain package ``thermocouples_reference`` 0.20 (module ``source_NIST``, "NIST SRD 60, type
X"), which transcribes SRD 60. Checked against the Omega Z-204 tables (NIST Monograph 175,
revised to ITS-90) of type K and E in the datasheet folder, every printed point: see
``tests/unit/machines/test_thermocouple.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class _Seg:
    lo: float  # °C
    hi: float  # °C
    c: tuple[float, ...]  # mV / °C^i, ascending powers
    gauss: tuple[float, float, float] | None = None  # a0 (mV), a1 (1/°C²), a2 (°C)


TYPES: dict[str, tuple[_Seg, ...]] = {
    "E": (
        _Seg(
            -270.0,
            0.0,
            (
                0.000000000000e00,
                0.586655087080e-01,
                0.454109771240e-04,
                -0.779980486860e-06,
                -0.258001608430e-07,
                -0.594525830570e-09,
                -0.932140586670e-11,
                -0.102876055340e-12,
                -0.803701236210e-15,
                -0.439794973910e-17,
                -0.164147763550e-19,
                -0.396736195160e-22,
                -0.558273287210e-25,
                -0.346578420130e-28,
            ),
            None,
        ),
        _Seg(
            0.0,
            1000.0,
            (
                0.000000000000e00,
                0.586655087100e-01,
                0.450322755820e-04,
                0.289084072120e-07,
                -0.330568966520e-09,
                0.650244032700e-12,
                -0.191974955040e-15,
                -0.125366004970e-17,
                0.214892175690e-20,
                -0.143880417820e-23,
                0.359608994810e-27,
            ),
            None,
        ),
    ),
    "J": (
        _Seg(
            -210.0,
            760.0,
            (
                0.000000000000e00,
                0.503811878150e-01,
                0.304758369300e-04,
                -0.856810657200e-07,
                0.132281952950e-09,
                -0.170529583370e-12,
                0.209480906970e-15,
                -0.125383953360e-18,
                0.156317256970e-22,
            ),
            None,
        ),
        _Seg(
            760.0,
            1200.0,
            (
                0.296456256810e03,
                -0.149761277860e01,
                0.317871039240e-02,
                -0.318476867010e-05,
                0.157208190040e-08,
                -0.306913690560e-12,
            ),
            None,
        ),
    ),
    "K": (
        _Seg(
            -270.0,
            0.0,
            (
                0.000000000000e00,
                0.394501280250e-01,
                0.236223735980e-04,
                -0.328589067840e-06,
                -0.499048287770e-08,
                -0.675090591730e-10,
                -0.574103274280e-12,
                -0.310888728940e-14,
                -0.104516093650e-16,
                -0.198892668780e-19,
                -0.163226974860e-22,
            ),
            None,
        ),
        _Seg(
            0.0,
            1372.0,
            (
                -0.176004136860e-01,
                0.389212049750e-01,
                0.185587700320e-04,
                -0.994575928740e-07,
                0.318409457190e-09,
                -0.560728448890e-12,
                0.560750590590e-15,
                -0.320207200030e-18,
                0.971511471520e-22,
                -0.121047212750e-25,
            ),
            (0.118597600000e00, -0.118343200000e-03, 0.126968600000e03),
        ),
    ),
    "N": (
        _Seg(
            -270.0,
            0.0,
            (
                0.000000000000e00,
                0.261591059620e-01,
                0.109574842280e-04,
                -0.938411115540e-07,
                -0.464120397590e-10,
                -0.263033577160e-11,
                -0.226534380030e-13,
                -0.760893007910e-16,
                -0.934196678350e-19,
            ),
            None,
        ),
        _Seg(
            0.0,
            1300.0,
            (
                0.000000000000e00,
                0.259293946010e-01,
                0.157101418800e-04,
                0.438256272370e-07,
                -0.252611697940e-09,
                0.643118193390e-12,
                -0.100634715190e-14,
                0.997453389920e-18,
                -0.608632456070e-21,
                0.208492293390e-24,
                -0.306821961510e-28,
            ),
            None,
        ),
    ),
    "T": (
        _Seg(
            -270.0,
            0.0,
            (
                0.000000000000e00,
                0.387481063640e-01,
                0.441944343470e-04,
                0.118443231050e-06,
                0.200329735540e-07,
                0.901380195590e-09,
                0.226511565930e-10,
                0.360711542050e-12,
                0.384939398830e-14,
                0.282135219250e-16,
                0.142515947790e-18,
                0.487686622860e-21,
                0.107955392700e-23,
                0.139450270620e-26,
                0.797951539270e-30,
            ),
            None,
        ),
        _Seg(
            0.0,
            400.0,
            (
                0.000000000000e00,
                0.387481063640e-01,
                0.332922278800e-04,
                0.206182434040e-06,
                -0.218822568460e-08,
                0.109968809280e-10,
                -0.308157587720e-13,
                0.454791352900e-16,
                -0.275129016730e-19,
            ),
            None,
        ),
    ),
}

LABELS = {
    "E": "tipo E (cromel-constantan)",
    "J": "tipo J (ferro-constantan)",
    "K": "tipo K (cromel-alumel)",
    "N": "tipo N (nicrosil-nisil)",
    "T": "tipo T (cobre-constantan)",
}


def emf_mv(kind: str, t_c: float) -> float:
    """Thermoelectric voltage in mV, reference junction at 0 °C (NIST ITS-90)."""
    segs = TYPES[kind.upper()]
    if not segs[0].lo <= t_c <= segs[-1].hi:
        raise ValueError(
            f"termopar {kind}: {t_c:g} °C fora da faixa ({segs[0].lo:g} a {segs[-1].hi:g} °C)"
        )
    seg = next(s for s in segs if t_c <= s.hi)
    e = sum(c * t_c**i for i, c in enumerate(seg.c))
    if seg.gauss is not None:
        a0, a1, a2 = seg.gauss
        e += a0 * math.exp(a1 * (t_c - a2) ** 2)
    return e


def range_c(kind: str) -> tuple[float, float]:
    segs = TYPES[kind.upper()]
    return segs[0].lo, segs[-1].hi


def spice_expr(kind: str, x: str) -> str:
    """ngspice expression of E(T) in volts; ``x`` is a simple term (a node voltage) holding
    the temperature in °C, already clamped to :func:`range_c` by the caller.

    The polynomial uses Horner's form so it stays short and exact in double precision.
    """
    segs = TYPES[kind.upper()]

    def poly(seg: _Seg, x: str) -> str:
        expr = f"{seg.c[-1]:.12e}"
        for c in reversed(seg.c[:-1]):
            expr = f"({c:.12e} + {x}*{expr})"
        if seg.gauss is not None:
            a0, a1, a2 = seg.gauss
            expr = f"({expr} + {a0:.10e}*exp({a1:.10e}*({x} - {a2:.10e})^2))"
        return expr

    expr = poly(segs[-1], x)
    for seg in reversed(segs[:-1]):
        expr = f"({x} <= {seg.hi:g} ? {poly(seg, x)} : {expr})"
    return f"(1e-3*{expr})"
