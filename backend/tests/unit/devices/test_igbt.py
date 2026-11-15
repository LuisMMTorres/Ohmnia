import pytest

from circuitos.core.units import Q_
from circuitos.devices import igbt


def model() -> igbt.IgbtModel:
    return igbt.IgbtModel(
        VT=Q_(5, "V"), V0=Q_(0.7, "V"), R_on=Q_(0.05, "ohm"), K=Q_(2, "A/V**2")
    )


def test_regions():
    m = model()
    # below the threshold: off
    assert igbt.collector_current(m, Q_(4, "V"), Q_(3, "V")).m_as("A") == 0
    # below the knee: off
    assert igbt.collector_current(m, Q_(15, "V"), Q_(0.5, "V")).m_as("A") == 0
    # linear region above the knee
    assert igbt.collector_current(m, Q_(15, "V"), Q_(1.7, "V")).m_as("A") == pytest.approx(20)
    # gate-limited: K/2·(VGE − VT)² = 1·(7 − 5)² = 4 A
    assert igbt.collector_current(m, Q_(7, "V"), Q_(5, "V")).m_as("A") == pytest.approx(4)


def test_fit_and_losses():
    r = igbt.fit_r_on(Q_(1.9, "V"), Q_(40, "A"), Q_(0.7, "V"))
    assert r.value.m_as("ohm") == pytest.approx(0.03)
    with pytest.raises(ValueError):
        igbt.fit_r_on(Q_(0.5, "V"), Q_(40, "A"), Q_(0.7, "V"))
    cond, sw = igbt.chopper_losses(
        model(),
        Q_(200, "V"),
        Q_(10, "A"),
        Q_(10, "kHz"),
        0.4,
        Q_(1, "mJ"),
        Q_(0.5, "mJ"),
        Q_(400, "V"),
        Q_(40, "A"),
    )
    assert cond.value.m_as("W") == pytest.approx(0.4 * (0.7 * 10 + 0.05 * 100))
    assert sw.value.m_as("W") == pytest.approx(1.5e-3 * 0.5 * 0.25 * 1e4)
