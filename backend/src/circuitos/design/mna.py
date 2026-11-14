"""Modified nodal analysis (MNA) of linear circuits: DC operating point and AC sweep.

The op-amp modules build the same linear circuit the simulator receives (resistors,
capacitors, inductors, independent sources, VCVS and VCCS, and the op-amp macromodel expanded
into those elements) and solve it here exactly: DC with capacitors open and inductors shorted,
AC at each frequency with s = j2πf. This is the MNA formulation SPICE itself uses for ``.op``
and ``.ac`` (Sedra & Smith, *Microelectronic Circuits*, 7th ed., appendix on SPICE; Nagel's
SPICE2 MNA), so the analytic result and the simulation agree to rounding.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

ComplexArray = NDArray[np.complex128]


@dataclass
class Element:
    kind: str  # R C L V I E G
    name: str
    a: str
    b: str
    value: float = 0.0
    ac: complex = 0.0
    cp: str | None = None
    cn: str | None = None


@dataclass
class Circuit:
    """Linear circuit; node "0" is ground. Names follow SPICE (the netlist uses the same)."""

    elements: list[Element] = field(default_factory=list)

    def R(self, name: str, a: str, b: str, r: float) -> None:
        self.elements.append(Element("R", name, a, b, r))

    def C(self, name: str, a: str, b: str, c: float) -> None:
        self.elements.append(Element("C", name, a, b, c))

    def L(self, name: str, a: str, b: str, h: float) -> None:
        self.elements.append(Element("L", name, a, b, h))

    def V(self, name: str, a: str, b: str, dc: float = 0.0, ac: complex = 0.0) -> None:
        """Voltage source, v(a) − v(b) = dc (+ ac in the AC analysis)."""
        self.elements.append(Element("V", name, a, b, dc, ac))

    def I(self, name: str, a: str, b: str, dc: float = 0.0, ac: complex = 0.0) -> None:  # noqa: E743
        """Current source pushing current from a through the source into b (SPICE sign)."""
        self.elements.append(Element("I", name, a, b, dc, ac))

    def E(self, name: str, a: str, b: str, cp: str, cn: str, gain: float) -> None:
        self.elements.append(Element("E", name, a, b, gain, 0.0, cp, cn))

    def G(self, name: str, a: str, b: str, cp: str, cn: str, gm: float) -> None:
        """Current gm·v(cp, cn) from a through the source into b (SPICE sign)."""
        self.elements.append(Element("G", name, a, b, gm, 0.0, cp, cn))

    # ------------------------------------------------------------------ solve
    def _nodes(self) -> list[str]:
        out: list[str] = []
        for e in self.elements:
            for n in (e.a, e.b, e.cp, e.cn):
                if n is not None and n != "0" and n not in out:
                    out.append(n)
        return out

    def _solve(self, s: complex, dc: bool) -> tuple[dict[str, complex], dict[str, complex]]:
        nodes = self._nodes()
        idx = {n: i for i, n in enumerate(nodes)}
        branches = [e for e in self.elements if e.kind in ("V", "E") or (e.kind == "L")]
        bidx = {e.name: len(nodes) + k for k, e in enumerate(branches)}
        size = len(nodes) + len(branches)
        A = np.zeros((size, size), dtype=np.complex128)
        z = np.zeros(size, dtype=np.complex128)

        def y(a: str, b: str, val: complex) -> None:
            for p, q, sg in ((a, a, 1), (b, b, 1), (a, b, -1), (b, a, -1)):
                if p in idx and q in idx:
                    A[idx[p], idx[q]] += sg * val

        for e in self.elements:
            if e.kind == "R":
                y(e.a, e.b, 1 / e.value)
            elif e.kind == "C":
                if not dc:
                    y(e.a, e.b, s * e.value)
            elif e.kind == "G":
                for node, sg in ((e.a, 1), (e.b, -1)):
                    if node in idx:
                        for c, cs in ((e.cp, 1), (e.cn, -1)):
                            if c is not None and c in idx:
                                A[idx[node], idx[c]] += sg * cs * e.value
            elif e.kind == "I":
                val = e.value if dc else e.ac
                if e.a in idx:
                    z[idx[e.a]] -= val
                if e.b in idx:
                    z[idx[e.b]] += val
            else:  # V, E, L: branch current k flows from a through the element to b
                k = bidx[e.name]
                for node, sg in ((e.a, 1), (e.b, -1)):
                    if node in idx:
                        A[idx[node], k] += sg
                        A[k, idx[node]] += sg
                if e.kind == "V":
                    z[k] = e.value if dc else e.ac
                elif e.kind == "E":
                    for c, cs in ((e.cp, 1), (e.cn, -1)):
                        if c is not None and c in idx:
                            A[k, idx[c]] -= cs * e.value
                elif not dc:  # inductor: v = sL·i
                    A[k, k] -= s * e.value
        x = np.linalg.solve(A, z)
        volts = {n: complex(x[i]) for n, i in idx.items()}
        volts["0"] = 0j
        currents = {name: complex(x[k]) for name, k in bidx.items()}
        return volts, currents

    def op(self) -> tuple[dict[str, float], dict[str, float]]:
        """DC operating point: node voltages and branch currents of V/E/L elements.

        A branch current is SPICE's ``i(vname)``: positive into the + terminal.
        """
        v, i = self._solve(0j, dc=True)
        return {k: x.real for k, x in v.items()}, {k: x.real for k, x in i.items()}

    def ac(self, f: NDArray[np.float64], outputs: list[str]) -> dict[str, ComplexArray]:
        """Node voltages at ``outputs`` for the AC values of the sources, at each frequency."""
        out = {o: np.zeros(f.size, dtype=np.complex128) for o in outputs}
        for k, fk in enumerate(f):
            v, _ = self._solve(2j * np.pi * fk, dc=False)
            for o in outputs:
                out[o][k] = v[o]
        return out

    def netlist(self) -> list[str]:
        """The same circuit as SPICE element lines."""
        lines = []
        for e in self.elements:
            if e.kind in ("R", "C", "L"):
                lines.append(f"{e.kind}{e.name} {e.a} {e.b} {e.value:.12g}")
            elif e.kind in ("V", "I"):
                ac = f" AC {abs(e.ac):.12g} {np.degrees(np.angle(e.ac)):.12g}" if e.ac else ""
                lines.append(f"{e.kind}{e.name} {e.a} {e.b} DC {e.value:.12g}{ac}")
            else:
                lines.append(f"{e.kind}{e.name} {e.a} {e.b} {e.cp} {e.cn} {e.value:.12g}")
        return lines
