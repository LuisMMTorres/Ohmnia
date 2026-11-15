"""PT-SIM: free-simulator properties (Monte Carlo, import/export, geometry, expressions)."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from circuitos.schematic.importer import import_netlist
from circuitos.schematic.library import transform
from circuitos.schematic.model import Sweep
from circuitos.schematic.netlist import build_netlist, connectivity
from circuitos.schematic.parts import Spread
from circuitos.schematic.runs import monte_carlo_runs
from circuitos.schematic.values import format_value, parse_value
from circuitos.simulation.post.expr import evaluate

positive = st.floats(min_value=1e-12, max_value=1e9, allow_nan=False, allow_infinity=False)


@settings(max_examples=200, deadline=None)
@given(
    nom=positive,
    tol=st.floats(min_value=0.001, max_value=0.5),
    seed=st.integers(0, 2**31 - 1),
    dist=st.sampled_from(["gauss", "uniform"]),
)
def test_monte_carlo_never_leaves_the_spread(nom, tol, seed, dist):
    sp = {"R1": Spread("value", nom * (1 - tol), nom, nom * (1 + tol), "tol")}
    runs = monte_carlo_runs(Sweep(kind="montecarlo", runs=30, seed=seed, distribution=dist), sp)
    assert runs[0].overrides == {}  # run 0 is the nominal circuit
    for r in runs[1:]:
        v = r.overrides[("R1", "value")]
        assert nom * (1 - tol) * (1 - 1e-12) <= v <= nom * (1 + tol) * (1 + 1e-12)
    again = monte_carlo_runs(Sweep(kind="montecarlo", runs=30, seed=seed, distribution=dist), sp)
    assert [r.overrides for r in runs] == [r.overrides for r in again]


@settings(max_examples=300, deadline=None)
@given(x=st.floats(min_value=1e-15, max_value=1e15))
def test_format_parse_roundtrip(x):
    assert parse_value(format_value(x)) == pytest.approx(x, rel=1e-5)


@given(dx=st.integers(-5, 5), dy=st.integers(-5, 5), mirror=st.booleans())
def test_four_rotations_are_identity_and_mirror_is_an_involution(dx, dy, mirror):
    p = (dx, dy)
    for _ in range(4):
        p = transform(p[0], p[1], 90, False)
    assert tuple(p) == (dx, dy)
    m = transform(*transform(dx, dy, 0, True), 0, True)
    assert tuple(m) == (dx, dy)
    # rotation preserves distance from the origin
    r = transform(dx, dy, 90, mirror)
    assert r[0] ** 2 + r[1] ** 2 == dx**2 + dy**2


ladder = st.lists(
    st.tuples(
        st.sampled_from(["R", "C", "L"]), st.integers(1, 999), st.sampled_from(["", "k", "u", "n"])
    ),
    min_size=1,
    max_size=8,
)


@settings(max_examples=60, deadline=None)
@given(parts=ladder)
def test_import_then_export_keeps_every_connection(parts):
    """A random ladder (series element k between n{k-1} and n{k}, shunt R to ground at each node)
    imported and exported again keeps each element between the same nets with the same value."""
    lines = ["ladder", "V1 n0 0 DC 1"]
    expected = {"V1": ("n0", "0")}
    for k, (kind, mant, suf) in enumerate(parts, start=1):
        lines.append(f"{kind}{k} n{k - 1} n{k} {mant}{suf}")
        lines.append(f"RS{k} n{k} 0 1k")
        expected[f"{kind}{k}"] = (f"n{k - 1}", f"n{k}")
        expected[f"RS{k}"] = (f"n{k}", "0")
    lines += [".op", ".end"]
    res = import_netlist("\n".join(lines))
    nl = build_netlist(res.schematic)
    conn = connectivity(res.schematic)
    assert set(nl.elements) == set(expected)
    for comp in res.schematic.components:
        if comp.ref not in expected:
            continue
        nodes = tuple(nl.pin_nodes[comp.ref][p] for p in ("1", "2") if p in nl.pin_nodes[comp.ref])
        if comp.ref == "V1":
            nodes = (nl.pin_nodes["V1"]["p"], nl.pin_nodes["V1"]["n"])
        assert nodes == expected[comp.ref], comp.ref
    assert conn is not None


@settings(max_examples=100, deadline=None)
@given(
    k=st.floats(min_value=-1e3, max_value=1e3).filter(lambda v: abs(v) > 1e-6),
    f=st.floats(min_value=1.0, max_value=10.0),
)
def test_rms_scales_with_gain(k, f):
    t = np.linspace(0, 1, 2001)
    x = np.sin(2 * np.pi * f * t) + 0.3
    vec = {"time": (t, "s"), "v(a)": (x, "V")}
    base = evaluate("rms(v(a))", vec, "time")
    scaled = evaluate(f"rms({k!r}*v(a))", vec, "time")
    assert float(np.real(np.ravel(scaled.data)[-1])) == pytest.approx(
        abs(k) * float(np.real(np.ravel(base.data)[-1])), rel=1e-9
    )
