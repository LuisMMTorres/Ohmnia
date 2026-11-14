"""Small-signal (AC) analysis of linear equivalent circuits by nodal analysis.

The amplifier modules build the hybrid-π equivalent at the Q-point (gm, rπ, Cπ, Cμ; Sedra &
Smith, *Microelectronic Circuits*, 7th ed., ch. 7 "Transistor amplifiers" and ch. 10
"Frequency response") and solve it exactly at every frequency, so the gain, the cut-off
frequencies and the Bode plot are the closed solution of the model, with no dominant-pole
approximation. The same linearised model is what SPICE uses in ``.ac``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

ComplexArray = NDArray[np.complex128]


@dataclass
class Network:
    """Admittance network with one ideal input source ``vin`` (1 V) at node ``src``."""

    elements: list[tuple[str, str, str, float, str | None, str | None]] = field(
        default_factory=list
    )
    nodes: list[str] = field(default_factory=list)

    def _node(self, n: str) -> None:
        if n != "0" and n not in self.nodes:
            self.nodes.append(n)

    def R(self, a: str, b: str, r: float) -> None:
        if np.isfinite(r) and r > 0:
            self._add("G", a, b, 1 / r)

    def C(self, a: str, b: str, c: float) -> None:
        if c > 0:
            self._add("C", a, b, c)

    def gm(self, out_p: str, out_n: str, gm: float, ctrl_p: str, ctrl_n: str) -> None:
        """Current gm·v(ctrl_p, ctrl_n) flowing from out_p to out_n through the source."""
        self._node(ctrl_p)
        self._node(ctrl_n)
        self.elements.append(("gm", out_p, out_n, gm, ctrl_p, ctrl_n))
        self._node(out_p)
        self._node(out_n)

    def _add(self, kind: str, a: str, b: str, v: float) -> None:
        self._node(a)
        self._node(b)
        self.elements.append((kind, a, b, v, None, None))

    def solve(
        self, f: NDArray[np.float64], src: str, outputs: list[str]
    ) -> dict[str, ComplexArray]:
        """Node voltages at ``outputs`` for 1 V at ``src`` (ideal source to ground)."""
        unknown = [n for n in self.nodes if n != src]
        idx = {n: i for i, n in enumerate(unknown)}
        out = {o: np.zeros(f.size, dtype=np.complex128) for o in outputs}
        for k, fk in enumerate(f):
            s = 2j * np.pi * fk
            n = len(unknown)
            Y = np.zeros((n, n), dtype=np.complex128)
            rhs = np.zeros(n, dtype=np.complex128)

            def stamp(
                a: str,
                b: str,
                y: complex,
                Y: NDArray[np.complex128] = Y,
                rhs: NDArray[np.complex128] = rhs,
            ) -> None:
                for p, q, sign in ((a, a, 1), (b, b, 1), (a, b, -1), (b, a, -1)):
                    if p in idx:
                        if q in idx:
                            Y[idx[p], idx[q]] += sign * y
                        elif q == src:
                            rhs[idx[p]] -= sign * y  # v(src) = 1

            for kind, a, b, v, cp, cn in self.elements:
                if kind == "G":
                    stamp(a, b, v)
                elif kind == "C":
                    stamp(a, b, s * v)
                else:
                    assert cp is not None and cn is not None
                    for node, sgn in ((a, 1), (b, -1)):
                        if node not in idx:
                            continue
                        for c, csg in ((cp, 1), (cn, -1)):
                            if c in idx:
                                Y[idx[node], idx[c]] += sgn * csg * v
                            elif c == src:
                                rhs[idx[node]] -= sgn * csg * v
            x = np.linalg.solve(Y, rhs)
            for o in outputs:
                out[o][k] = 1.0 if o == src else (0.0 if o == "0" else x[idx[o]])
        return out


def corner(f: NDArray[np.float64], mag: NDArray[np.float64], side: str) -> float | None:
    """−3 dB frequency below ("fl") or above ("fh") the maximum, interpolated in log f / dB."""
    k = int(np.argmax(mag))
    level = 20 * np.log10(mag[k] / np.sqrt(2))
    db = 20 * np.log10(np.maximum(mag, 1e-300))
    lf = np.log10(f)
    if side == "fl":
        idx = np.nonzero(db[: k + 1] < level)[0]
        if idx.size == 0:
            return None
        i = int(idx[-1])
        j = i + 1
    else:
        idx = np.nonzero(db[k:] < level)[0]
        if idx.size == 0:
            return None
        j = k + int(idx[0])
        i = j - 1
    x = lf[i] + (level - db[i]) * (lf[j] - lf[i]) / (db[j] - db[i])
    return float(10**x)


def log_grid(f1: float, f2: float, per_decade: int = 40) -> NDArray[np.float64]:
    """Same points as ``.ac dec per_decade f1 f2`` of SPICE."""
    n = int(np.floor(per_decade * np.log10(f2 / f1) + 1e-9)) + 1
    return np.asarray(f1 * 10 ** (np.arange(n) / per_decade), dtype=np.float64)
