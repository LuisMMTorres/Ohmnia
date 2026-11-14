import numpy as np
import pytest

from circuitos.core.errors import UnitError
from circuitos.core.units import (
    Q_,
    QuantityModel,
    VectorModel,
    format_eng,
    magnitudes,
    parse_quantity,
    parse_unit,
    q,
    require,
)


def test_q_accepts_brazilian_symbols():
    assert q(4.7, "kΩ").m_as("ohm") == pytest.approx(4700)
    assert q(10, "µF").m_as("F") == pytest.approx(10e-6)


def test_q_vector():
    v = q([1, 2, 3], "V")
    assert isinstance(v.magnitude, np.ndarray)


def test_parse_unit_rejects_unknown():
    with pytest.raises(UnitError):
        parse_unit("banana")


def test_parse_unit_dimensionless():
    assert parse_unit("") == parse_unit("1")


@pytest.mark.parametrize(
    ("text", "unit", "value"),
    [
        ("4,7 kΩ", "ohm", 4700),
        ("2.2uF", "F", 2.2e-6),
        ("60 Hz", "Hz", 60),
        ("25 degC", "K", 298.15),
    ],
)
def test_parse_quantity(text, unit, value):
    assert parse_quantity(text).m_as(unit) == pytest.approx(value)


def test_parse_quantity_invalid():
    with pytest.raises(UnitError):
        parse_quantity("4,7 parsecs por banana")


def test_require_checks_dimension():
    require(q(1, "mA"), "A")
    with pytest.raises(UnitError):
        require(q(1, "V"), "A")
    with pytest.raises(UnitError):
        require(3.0, "A")


def test_magnitudes_decorator_converts_and_wraps():
    @magnitudes(inputs={"v": "V", "r": "ohm"}, output="A")
    def ohm(v: float, r: float) -> float:
        return v / r

    assert ohm(q(5, "V"), q(1, "kohm")).m_as("mA") == pytest.approx(5)
    with pytest.raises(UnitError):
        ohm(5.0, q(1, "kohm"))


def test_magnitudes_tuple_output():
    @magnitudes(inputs={"x": "V"}, output=("V", "A"))
    def pair(x: float) -> tuple[float, float]:
        return x, x / 2

    v, i = pair(q(2, "V"))
    assert v.m_as("V") == 2 and i.m_as("A") == 1


def test_magnitudes_tuple_output_wrong_arity():
    @magnitudes(inputs={"x": "V"}, output=("V", "A"))
    def bad(x: float) -> float:
        return x

    with pytest.raises(TypeError):
        bad(q(1, "V"))


def test_magnitudes_unknown_parameter():
    with pytest.raises(TypeError):

        @magnitudes(inputs={"nope": "V"})
        def f(x: float) -> float:
            return x


def test_magnitudes_without_output():
    @magnitudes(inputs={"x": "V"})
    def f(x: float) -> float:
        return x * 2

    assert f(q(1, "kV")) == 2000


def test_quantity_model_roundtrip():
    m = QuantityModel.from_pint(q(1.5, "mA"))
    assert m.to_pint().m_as("A") == pytest.approx(1.5e-3)
    m2 = QuantityModel.from_pint(q(1.5, "mA"), unit="A")
    assert m2.value == pytest.approx(1.5e-3) and m2.unit == "A"


def test_quantity_model_rejects_vector_and_bad_unit():
    with pytest.raises(UnitError):
        QuantityModel.from_pint(q([1, 2], "V"))
    with pytest.raises(ValueError):
        QuantityModel(value=1, unit="banana")


def test_vector_model_roundtrip():
    v = VectorModel.from_pint(q([1, 2], "V"), unit="mV")
    assert v.values == [1000, 2000]
    assert v.to_pint().m_as("V").tolist() == [1, 2]
    with pytest.raises(ValueError):
        VectorModel(values=[1], unit="banana")


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (q(4700, "ohm"), "4,7 kΩ"),
        (q(0.0022, "F"), "2,2 mF"),
        (q(1e-7, "F"), "100 nF"),
        (q(12, "V"), "12 V"),
        (q(-0.015, "A"), "-15 mA"),
        (q(60, "Hz"), "60 Hz"),
        (q(1.5, "kW"), "1,5 kW"),
        (q(2.5, "kVA"), "2,5 kVA"),
        (q(999.96, "ohm"), "1 kΩ"),
        (q(0, "V"), "0 V"),
        (q(33e-6, "s"), "33 µs"),
    ],
)
def test_format_eng(quantity, expected):
    assert format_eng(quantity) == expected


def test_format_eng_non_prefixable_unit():
    assert format_eng(q(1.25, "K/W")) == "1,25 K/W"


def test_format_eng_rejects_vector():
    with pytest.raises(UnitError):
        format_eng(Q_(np.array([1.0, 2.0]), "V"))
