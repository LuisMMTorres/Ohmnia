import pytest

from circuitos.core.eseries import TOLERANCE, series, snap
from circuitos.core.errors import UnitError
from circuitos.core.units import q

# Independent transcription of IEC 60063 E48, used to cross-check the geometric construction.
E48_IEC = (
    1.00, 1.05, 1.10, 1.15, 1.21, 1.27, 1.33, 1.40, 1.47, 1.54, 1.62, 1.69,
    1.78, 1.87, 1.96, 2.05, 2.15, 2.26, 2.37, 2.49, 2.61, 2.74, 2.87, 3.01,
    3.16, 3.32, 3.48, 3.65, 3.83, 4.02, 4.22, 4.42, 4.64, 4.87, 5.11, 5.36,
    5.62, 5.90, 6.19, 6.49, 6.81, 7.15, 7.50, 7.87, 8.25, 8.66, 9.09, 9.53,
)  # fmt: skip


@pytest.mark.parametrize(("name", "n"), [("E3", 3), ("E6", 6), ("E12", 12), ("E24", 24),
                                         ("E48", 48), ("E96", 96), ("E192", 192)])
def test_series_length_and_order(name, n):
    s = series(name)
    assert len(s) == n
    assert list(s) == sorted(s)
    assert s[0] == 1.0 and s[-1] < 10


def test_e12_e6_subsets_of_e24():
    assert series("E12") == (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2)
    assert series("E6") == (1.0, 1.5, 2.2, 3.3, 4.7, 6.8)


def test_e48_matches_iec_table():
    assert series("E48") == E48_IEC


def test_e96_contains_e48_and_e192_exception():
    assert set(series("E48")) <= set(series("E96")) <= set(series("E192"))
    assert 9.20 in series("E192") and 9.19 not in series("E192")


def test_unknown_series():
    with pytest.raises(ValueError):
        series("E7")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "name", "mode", "expected"),
    [
        (4600, "E24", "nearest", 4700),
        (4600, "E24", "down", 4300),
        (4700, "E24", "up", 4700),
        (4701, "E24", "up", 5100),
        (9.5, "E12", "up", 10),
        (0.95, "E12", "down", 0.82),
        (1234, "E96", "nearest", 1240),
        (3.0e-6, "E6", "nearest", 3.3e-6),
    ],
)
def test_snap(value, name, mode, expected):
    result = snap(q(value, "ohm"), name, mode)
    assert result.m_as("ohm") == pytest.approx(expected)


def test_snap_keeps_unit():
    assert str(snap(q(2.1, "uF"), "E12").units) == "microfarad"


def test_snap_rejects_bad_values():
    with pytest.raises(ValueError):
        snap(q(-1, "ohm"))
    with pytest.raises(UnitError):
        snap(100)  # type: ignore[arg-type]


def test_tolerances_defined_for_all_series():
    assert set(TOLERANCE) == {"E3", "E6", "E12", "E24", "E48", "E96", "E192"}
