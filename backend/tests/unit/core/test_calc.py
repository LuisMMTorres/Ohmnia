import pytest

from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.errors import UnitError
from circuitos.core.units import q


def test_record_builds_step():
    c = record(
        "vo_med",
        "Tensão média na carga",
        r"V_{o} = \frac{2 V_m}{\pi}",
        output=q(108, "V"),
        inputs={"V_m": q(169.7, "V")},
        assumptions=["diodos ideais"],
        reference=BibRef(book="Hart, Eletrônica de Potência"),
    )
    assert c.value.m_as("V") == 108
    assert c.step.inputs["V_m"].unit == "V"
    assert c.step.reference is not None and c.step.reference.verified is False


def test_record_requires_units():
    with pytest.raises(UnitError):
        record("x", "x", "x", output=1.0)  # type: ignore[arg-type]
    with pytest.raises(UnitError):
        record("x", "x", "x", output=q(1, "V"), inputs={"a": 2.0})  # type: ignore[dict-item]


def test_calc_log_order_and_duplicates():
    log = CalcLog()
    a = log.add(record("a", "a", "a", output=q(1, "V")))
    log.add(record("b", "b", "b", output=q(2, "A")))
    assert a.m_as("V") == 1
    assert [s.id for s in log] == ["a", "b"]
    assert len(log) == 2 and log["b"].output.unit == "A"
    with pytest.raises(ValueError):
        log.add(record("a", "a", "a", output=q(1, "V")))
