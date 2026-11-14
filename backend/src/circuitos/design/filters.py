"""Filter approximation and decomposition into first- and second-order sections.

Normalised low-pass prototypes (Butterworth, Chebyshev type I, Bessel normalised to −3 dB at
ω = 1, Cauer/elliptic) come from SciPy's ``buttap``/``cheb1ap``/``besselap``/``ellipap``; the
frequency transformations LP→LP, LP→HP, LP→BP and LP→BS are the classical substitutions
s → s/ωc, ωc/s, (s² + ω0²)/(Bs) and Bs/(s² + ω0²) (Williams & Taylor, *Electronic Filter
Design Handbook*, 4th ed., ch. 2; Pertence, cap. de filtros ativos). The transformed filter is
split into sections: each complex pole pair with up to two zeros, each real pole with up to one.
Each section is normalised to unit gain where it passes (DC for LP, ∞ for HP, ω0 for BP).

Doubly terminated LC ladders use the closed-form element values g_k (Matthaei, Young & Jones,
*Microwave Filters, Impedance-Matching Networks, and Coupling Structures*, 1964, ch. 4):
Butterworth g_k = 2 sin((2k − 1)π/2n); Chebyshev from β = ln coth(Ar/17,37), γ = sinh(β/2n).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import scipy.signal as sg
from numpy.typing import NDArray

CArr = NDArray[np.complex128]

Approx = Literal["butterworth", "chebyshev", "bessel", "eliptico"]
Kind = Literal["passa_baixas", "passa_altas", "passa_faixa", "rejeita_faixa"]


@dataclass(frozen=True)
class Section:
    """H(s) = (n2 s² + n1 s + n0)/(s² + (w0/Q) s + w0²) or (n1 s + n0)/(s + w0) (order 1)."""

    order: int
    w0: float  # rad/s
    Q: float  # 0 for first order
    n2: float
    n1: float
    n0: float

    @property
    def kind(self) -> str:
        if self.order == 1:
            return "lp1" if self.n1 == 0 else "hp1"
        if self.n2 == 0 and self.n1 == 0:
            return "lp"
        if self.n1 == 0 and self.n0 == 0:
            return "hp"
        if self.n2 == 0 and self.n0 == 0:
            return "bp"
        return "notch"

    @property
    def wz(self) -> float:
        """Zero frequency of a notch section, rad/s."""
        return math.sqrt(self.n0 / self.n2) if self.n2 else math.inf

    def h(self, s: complex) -> complex:
        if self.order == 1:
            return (self.n1 * s + self.n0) / (s + self.w0)
        return (self.n2 * s * s + self.n1 * s + self.n0) / (
            s * s + self.w0 / self.Q * s + self.w0**2
        )


def prototype(approx: Approx, n: int, rp: float, rs: float) -> tuple[CArr, CArr]:
    """Zeros and poles of the normalised low-pass prototype."""
    if approx == "butterworth":
        z, p, _ = sg.buttap(n)
    elif approx == "chebyshev":
        z, p, _ = sg.cheb1ap(n, rp)
    elif approx == "bessel":
        z, p, _ = sg.besselap(n, norm="mag")
    else:
        z, p, _ = sg.ellipap(n, rp, rs)
    return np.asarray(z, dtype=np.complex128), np.asarray(p, dtype=np.complex128)


def min_order(approx: Approx, ws_over_wp: float, rp: float, rs: float) -> int:
    """Smallest order with attenuation ≥ rs at the normalised stop frequency (LP prototype)."""
    if ws_over_wp <= 1:
        raise ValueError("A frequência de rejeição deve ficar fora da banda passante")
    if approx == "butterworth":
        # the −3 dB prototype: passband edge = 1
        n = math.ceil(math.log10(10 ** (rs / 10) - 1) / (2 * math.log10(ws_over_wp)))
        return max(1, n)
    if approx == "chebyshev":
        return max(1, int(sg.cheb1ord(1, ws_over_wp, rp, rs, analog=True)[0]))
    if approx == "eliptico":
        return max(2, int(sg.ellipord(1, ws_over_wp, rp, rs, analog=True)[0]))
    for n in range(1, 16):
        z, p = prototype("bessel", n, rp, rs)
        if attenuation_db(z, p, ws_over_wp) >= rs:
            return n
    raise ValueError("Bessel: mais de 15 polos para essa especificação")


def attenuation_db(z: CArr, p: CArr, w: float) -> float:
    """Attenuation of a low-pass prototype at ω relative to its DC gain, dB."""

    def h(s: complex) -> complex:
        return complex(np.prod(s - z) / np.prod(s - p))

    return float(-20 * math.log10(abs(h(1j * w)) / abs(h(0j))))


def transform(z: CArr, p: CArr, kind: Kind, w1: float, w2: float = 0.0) -> tuple[CArr, CArr]:
    """Prototype → actual zeros/poles. LP/HP: w1 = edge. BP/BS: w1 = centre, w2 = bandwidth."""
    if kind == "passa_baixas":
        z2, p2, _ = sg.lp2lp_zpk(z, p, 1.0, w1)
    elif kind == "passa_altas":
        z2, p2, _ = sg.lp2hp_zpk(z, p, 1.0, w1)
    elif kind == "passa_faixa":
        z2, p2, _ = sg.lp2bp_zpk(z, p, 1.0, w1, w2)
    else:
        z2, p2, _ = sg.lp2bs_zpk(z, p, 1.0, w1, w2)
    return np.asarray(z2, dtype=np.complex128), np.asarray(p2, dtype=np.complex128)


def sections(z: CArr, p: CArr, kind: Kind) -> list[Section]:
    """Split into sections, each with unit gain where it passes."""
    tol = 1e-9 * max(1.0, float(np.max(np.abs(p))))
    pairs = sorted([x for x in p if x.imag > tol], key=lambda x: -abs(x) / (2 * -x.real))
    reals = [x.real for x in p if abs(x.imag) <= tol]
    zj = sorted([x for x in z if x.imag > tol], key=lambda x: x.imag)  # finite jω zeros
    n_origin = sum(1 for x in z if abs(x) <= tol)
    out: list[Section] = []
    # zeros pairs go to the highest-Q pole pairs, nearest frequency first
    zj_left = list(zj)
    for pp in pairs:
        w0 = abs(pp)
        q = w0 / (-2 * pp.real)
        if zj_left:
            zz = min(zj_left, key=lambda x: abs(abs(x) - w0))
            zj_left.remove(zz)
            wz2 = abs(zz) ** 2
            # LP: unit gain at DC; HP and band-stop: unit gain far above the zero
            k = w0**2 / wz2 if kind == "passa_baixas" else 1.0
            out.append(Section(2, w0, q, k, 0.0, k * wz2))
        elif n_origin >= 2 and kind == "passa_altas":
            n_origin -= 2
            out.append(Section(2, w0, q, 1.0, 0.0, 0.0))
        elif n_origin >= 1 and kind == "passa_faixa":
            n_origin -= 1
            out.append(Section(2, w0, q, 0.0, w0 / q, 0.0))
        else:
            out.append(Section(2, w0, q, 0.0, 0.0, w0**2))
    for r in reals:
        w0 = -r
        if n_origin >= 1 and kind in ("passa_altas", "passa_faixa"):
            n_origin -= 1
            out.append(Section(1, w0, 0.0, 0.0, 1.0, 0.0))
        else:
            out.append(Section(1, w0, 0.0, 0.0, 0.0, w0))
    return out


def normalise(secs: list[Section], kind: Kind, w_center: float) -> list[Section]:
    """Scale the first section so the band-pass gain at the centre is 1 (others already are)."""
    if kind != "passa_faixa" or not secs:
        return secs
    g = abs(np.prod([sec.h(1j * w_center) for sec in secs]))
    first = secs[0]
    scaled = Section(first.order, first.w0, first.Q, first.n2 / g, first.n1 / g, first.n0 / g)
    return [scaled, *secs[1:]]


def response(secs: list[Section], f: NDArray[np.float64]) -> NDArray[np.complex128]:
    s = 2j * np.pi * f
    h = np.ones(f.size, dtype=np.complex128)
    for sec in secs:
        h *= np.array([sec.h(x) for x in s])
    return h


def ladder_g(approx: Approx, n: int, rp: float) -> list[float]:
    """g_1..g_n of the doubly terminated (equal terminations) LC ladder prototype."""
    if approx == "butterworth":
        return [2 * math.sin((2 * k - 1) * math.pi / (2 * n)) for k in range(1, n + 1)]
    if approx != "chebyshev":
        raise ValueError("Escada LC tabelada só para Butterworth e Chebyshev")
    if n % 2 == 0:
        raise ValueError("Escada Chebyshev com terminações iguais exige ordem ímpar")
    beta = math.log(1 / math.tanh(rp * math.log(10) / 40))  # Ar/17,37 with 17,37 = 40/ln 10
    gam = math.sinh(beta / (2 * n))
    a = [math.sin((2 * k - 1) * math.pi / (2 * n)) for k in range(1, n + 1)]
    b = [gam**2 + math.sin(k * math.pi / n) ** 2 for k in range(1, n + 1)]
    g = [2 * a[0] / gam]
    for k in range(2, n + 1):
        g.append(4 * a[k - 2] * a[k - 1] / (b[k - 2] * g[-1]))
    return g
