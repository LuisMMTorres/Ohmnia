"""SV-MAG: wire tables, core geometry, loss model and the Ap design loop."""

import math

import pytest

from circuitos.core.calc import CalcLog
from circuitos.magnetics.cores import _cond, _v, core_from, steinmetz
from circuitos.magnetics.design import MagSpec, Winding, _at_turns, _materials, design
from circuitos.magnetics.wire import MU0, awg_area, awg_diameter, choose_strand, rho_cu, skin_depth


def test_awg_definition_points():
    # ASTM B258: AWG 36 = 0,127 mm and AWG 0000 = 0,46 in; 39 steps between them
    assert awg_diameter(36) == pytest.approx(0.127e-3)
    assert awg_diameter(-3) == pytest.approx(0.46 * 25.4e-3, rel=1e-3)
    assert awg_area(10) == pytest.approx(math.pi / 4 * awg_diameter(10) ** 2)


def test_copper_resistivity_and_skin_depth():
    assert rho_cu(20) == pytest.approx(1 / 58e6)
    assert rho_cu(100) == pytest.approx(1 / 58e6 * (1 + 0.00393 * 80))
    # δ = √(ρ/(π f μ0)) ≈ 0,21 mm at 100 kHz and 100 °C
    assert skin_depth(100e3, 100) == pytest.approx(math.sqrt(rho_cu(100) / (math.pi * 100e3 * MU0)))
    assert 0.2e-3 < skin_depth(100e3, 100) < 0.25e-3


def test_strand_is_thinner_than_two_skin_depths_and_has_the_area():
    s = choose_strand(8.0, 4e6, 100e3, 100)
    assert awg_diameter(s.awg) <= 2 * skin_depth(100e3, 100)
    assert s.area >= 8.0 / 4e6
    low = choose_strand(1.0, 4e6, 50.0, 100)  # mains frequency: one solid wire
    assert low.n == 1


def _cat(repo):
    return (
        repo.search(category="magnetic.core"),
        repo.search(category="magnetic.material"),
        repo.search(category="magnetic.bobbin"),
    )


def test_steinmetz_fit_reproduces_material_points(reviewed_catalogue):
    _, mats, _ = _cat(reviewed_catalogue)
    m96 = next(m for m in mats if m.part_number == "3C96")
    st = steinmetz(m96)
    assert st.alpha is not None
    for key in ("Pv_1", "Pv_2", "Pv_3"):
        p = m96.parameters[key]
        f, b = _cond(p, "f"), _cond(p, "B")
        assert f and b
        assert st.k * f**st.alpha * b**st.beta == pytest.approx(_v(p), rel=1e-6)


def test_core_geometry_e30(reviewed_catalogue):
    cores, _, bob = _cat(reviewed_catalogue)
    c = core_from(next(x for x in cores if "E30/15/7" in x.tags[0] or "E30" in x.part_number), bob)
    assert c.Ae == pytest.approx(60e-6)
    assert c.window_from.startswith("carretel")
    assert c.Wa > 100e-6 and c.mu_e > 1000


def test_inductor_design_is_consistent(reviewed_catalogue):
    cores, mats, bob = _cat(reviewed_catalogue)
    s = MagSpec(
        kind="indutor", f=100e3, windings=(Winding("L", 1, 3.0),), L=22e-6, I_pk=3.45, dI_pp=0.9
    )
    log = CalcLog()
    r = design(s, cores, mats, bob, log)
    n = r.windings[0].N
    c = r.core
    assert r.B_pk == pytest.approx(s.L * s.I_pk / (n * c.Ae))
    assert r.B_pk <= min(s.B_max, 0.9 * c.Bsat) + 1e-12
    # L = μ0 N² Ae / (lg + le/μe)
    assert MU0 * n**2 * c.Ae / (r.gap + c.le / c.mu_e) == pytest.approx(s.L, rel=1e-9)
    assert r.fill <= s.Ku and r.dT <= s.dT_max
    ids = {st.id for st in log}
    assert {"mag_N1_min", "mag_N1", "mag_gap", "mag_R_L", "mag_Pcore", "mag_dT"} <= ids
    # nothing smaller in the catalogue fits
    st = _materials(mats)
    smaller = [core_from(x, bob) for x in cores if core_from(x, bob).Ap < c.Ap]
    for k in smaller:
        best = min(
            (
                res
                for n_ in range(1, 200)
                if (res := _at_turns(s, k, n_, st.get(k.material), 2.39)[0])
            ),
            key=lambda x: x.P_total,
            default=None,
        )
        assert best is None or best.B_pk > min(s.B_max, 0.9 * k.Bsat) or best.dT > s.dT_max


def test_transformer_turns_minimise_loss(reviewed_catalogue):
    cores, mats, bob = _cat(reviewed_catalogue)
    s = MagSpec(
        kind="transformador",
        f=100e3,
        windings=(Winding("P", 1, 2.0), Winding("S", 0.25, 8.0)),
        lam=48 * 4.5e-6,
        bipolar=True,
    )
    r = design(s, cores, mats, bob, CalcLog())
    n1, n2 = (w.N for w in r.windings)
    assert n2 == round(n1 * 0.25)
    assert r.B_ac == pytest.approx(s.lam / (2 * n1 * r.core.Ae))
    assert 2 * r.B_ac <= 2 * min(s.B_max, 0.9 * r.core.Bsat) + 1e-12
    st = _materials(mats)
    for nn in (n1 - 1, n1 + 1):
        other, _ = _at_turns(s, r.core, nn, st.get(r.core.material), None)
        if other is not None and other.B_ac <= min(s.B_max, 0.9 * r.core.Bsat):
            assert other.P_total >= r.P_total - 1e-12


def test_unreleased_cores_are_not_chosen(reviewed_catalogue):
    from pathlib import Path

    from circuitos.components.repository import ComponentRepository

    repo = ComponentRepository()
    repo.import_directory(Path(__file__).resolve().parents[4] / "data" / "components" / "magnetic")
    cores, mats, bob = _cat(repo)
    s = MagSpec(kind="indutor", f=100e3, windings=(Winding("L", 1, 3.0),), L=22e-6, I_pk=3.45)
    with pytest.raises(ValueError, match="liberado"):
        design(s, cores, mats, bob, CalcLog())


def test_impossible_spec_reports_reasons(reviewed_catalogue):
    cores, mats, bob = _cat(reviewed_catalogue)
    s = MagSpec(kind="indutor", f=100e3, windings=(Winding("L", 1, 300.0),), L=1e-3, I_pk=300)
    with pytest.raises(ValueError, match="Nenhum núcleo"):
        design(s, cores, mats, bob, CalcLog())
