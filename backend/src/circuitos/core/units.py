"""Physical quantities with units.

Rule 2 of the project: every physical quantity carries a unit. Inside the domain core values are
``pint.Quantity`` objects created from the single registry ``ureg``. At the API boundary they are
serialised as :class:`QuantityModel` / :class:`VectorModel`. Numeric hot loops may work on bare
magnitudes only inside functions decorated with :func:`magnitudes`.
"""

from __future__ import annotations

import functools
import inspect
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, cast

import numpy as np
import pint
from pydantic import BaseModel, ConfigDict, field_validator

from circuitos.core.errors import UnitError

ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
ureg.define("var = volt * ampere = VAr")  # reactive power, same dimension as VA and W
Q_ = ureg.Quantity
Quantity = pint.Quantity

F = TypeVar("F", bound=Callable[..., Any])


def parse_unit(unit: str) -> pint.Unit:
    """Parse a unit string, accepting the symbols used in Brazilian engineering texts."""
    normalized = unit.strip().replace("Ω", "ohm").replace("µ", "u").replace("μ", "u")
    if normalized in ("", "1", "-"):
        return ureg.dimensionless
    try:
        return ureg.Unit(normalized)
    except (pint.UndefinedUnitError, pint.DefinitionSyntaxError, AttributeError, ValueError) as exc:
        raise UnitError(f"Unidade desconhecida: {unit!r}") from exc


def q(value: float | Sequence[float] | np.ndarray[Any, Any], unit: str) -> pint.Quantity:
    """Create a quantity. ``q(4.7, "kohm")``."""
    if isinstance(value, Sequence) and not isinstance(value, str):
        value = np.asarray(value, dtype=float)
    return Q_(value, parse_unit(unit))


def parse_quantity(text: str) -> pint.Quantity:
    """Parse ``"4,7 kΩ"`` or ``"2.2uF"`` into a quantity (decimal comma accepted)."""
    cleaned = text.strip().replace(",", ".").replace("Ω", "ohm").replace("µ", "u")
    try:
        result = ureg.Quantity(cleaned)
    except Exception as exc:
        raise UnitError(f"Grandeza inválida: {text!r}") from exc
    if not isinstance(result, pint.Quantity):  # pragma: no cover - pint returns numbers for "3"
        return Q_(float(result), ureg.dimensionless)
    return result


def require(value: object, dimension: str, name: str = "valor") -> pint.Quantity:
    """Ensure ``value`` is a quantity compatible with the unit ``dimension`` (e.g. ``"V"``)."""
    if not isinstance(value, pint.Quantity):
        raise UnitError(f"{name} deve ter unidade compatível com {dimension}; recebido {value!r}")
    target = parse_unit(dimension)
    if value.dimensionality != Q_(1, target).dimensionality:
        raise UnitError(f"{name} deve ser compatível com {dimension}; recebido {value.units:~P}")
    return value


def magnitudes(
    inputs: Mapping[str, str], output: str | Sequence[str] | None = None
) -> Callable[[F], F]:
    """Unit-safe boundary for numeric kernels.

    Arguments listed in ``inputs`` must be quantities; they are converted to the given unit and
    passed as bare magnitudes. The return value (bare magnitude, or a tuple of them) is wrapped with
    ``output`` unit(s).
    """

    def decorator(func: F) -> F:
        sig = inspect.signature(func)
        unknown = set(inputs) - set(sig.parameters)
        if unknown:
            raise TypeError(f"{func.__name__}: parâmetros inexistentes em inputs: {unknown}")

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for name, unit in inputs.items():
                bound.arguments[name] = require(bound.arguments[name], unit, name).m_as(
                    parse_unit(unit)
                )
            result = func(*bound.args, **bound.kwargs)
            if output is None:
                return result
            if isinstance(output, str):
                return Q_(result, parse_unit(output))
            if not isinstance(result, tuple) or len(result) != len(output):
                raise TypeError(f"{func.__name__} deve retornar {len(output)} valores")
            return tuple(Q_(r, parse_unit(u)) for r, u in zip(result, output, strict=True))

        return cast(F, wrapper)

    return decorator


# ---------------------------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------------------------


class QuantityModel(BaseModel):
    """Scalar quantity as exchanged over the API: ``{"value": 1.2e-3, "unit": "A"}``."""

    model_config = ConfigDict(frozen=True)

    value: float
    unit: str

    @field_validator("unit")
    @classmethod
    def _valid_unit(cls, unit: str) -> str:
        parse_unit(unit)
        return unit

    def to_pint(self) -> pint.Quantity:
        return Q_(self.value, parse_unit(self.unit))

    @classmethod
    def from_pint(cls, quantity: pint.Quantity, unit: str | None = None) -> QuantityModel:
        if unit is not None:
            quantity = quantity.to(parse_unit(unit))
        magnitude = quantity.magnitude
        if np.ndim(magnitude) != 0:
            raise UnitError("QuantityModel aceita apenas escalares; use VectorModel")
        return cls(value=float(magnitude), unit=unit or f"{quantity.units:~C}")


class VectorModel(BaseModel):
    """Vector quantity: ``{"values": [...], "unit": "V"}``."""

    model_config = ConfigDict(frozen=True)

    values: list[float]
    unit: str

    @field_validator("unit")
    @classmethod
    def _valid_unit(cls, unit: str) -> str:
        parse_unit(unit)
        return unit

    def to_pint(self) -> pint.Quantity:
        return Q_(np.asarray(self.values, dtype=float), parse_unit(self.unit))

    @classmethod
    def from_pint(cls, quantity: pint.Quantity, unit: str | None = None) -> VectorModel:
        if unit is not None:
            quantity = quantity.to(parse_unit(unit))
        values = np.atleast_1d(np.asarray(quantity.magnitude, dtype=float))
        return cls(values=values.tolist(), unit=unit or f"{quantity.units:~C}")


# ---------------------------------------------------------------------------------------------
# Engineering notation (pt-BR)
# ---------------------------------------------------------------------------------------------

_PREFIXES = {-15: "f", -12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T"}

# Units that take SI prefixes in engineering notation, in order of preference for each dimension.
_PREFIXABLE = [
    ("volt", "V"),
    ("ampere", "A"),
    ("watt", "W"),
    ("volt_ampere", "VA"),
    ("var", "var"),
    ("ohm", "Ω"),
    ("siemens", "S"),
    ("farad", "F"),
    ("henry", "H"),
    ("hertz", "Hz"),
    ("second", "s"),
    ("joule", "J"),
    ("coulomb", "C"),
    ("tesla", "T"),
    ("weber", "Wb"),
    ("meter", "m"),
]


def _base_unit_for(quantity: pint.Quantity) -> tuple[str, str] | None:
    unit_name = str(quantity.units)
    compatible = [
        (name, sym)
        for name, sym in _PREFIXABLE
        if quantity.dimensionality == Q_(1, ureg.Unit(name)).dimensionality
    ]
    for name, sym in compatible:
        if unit_name.endswith(name):
            return name, sym
    return compatible[0] if compatible else None


def format_eng(quantity: pint.Quantity, digits: int = 3) -> str:
    """Format a scalar quantity in engineering notation with decimal comma: ``"4,7 kΩ"``."""
    if np.ndim(quantity.magnitude) != 0:
        raise UnitError("format_eng aceita apenas escalares")
    base = _base_unit_for(quantity)
    if base is None:
        text = f"{float(quantity.magnitude):.{digits}g} {quantity.units:~P}"
        return text.replace(".", ",").strip()
    name, symbol = base
    value = float(quantity.m_as(ureg.Unit(name)))
    if value == 0 or not math.isfinite(value):
        return f"{value:g} {symbol}".replace(".", ",")
    exponent = int(math.floor(math.log10(abs(value)) / 3) * 3)
    exponent = max(min(exponent, 12), -15)
    mantissa = value / 10**exponent
    # Rounding may push 999.6 to 1000: move to the next prefix.
    if float(f"{abs(mantissa):.{digits}g}") >= 1000 and exponent < 12:
        exponent += 3
        mantissa = value / 10**exponent
    text = f"{mantissa:.{digits}g}"
    if "e" in text:  # pragma: no cover - guarded by the range clamp above
        text = f"{mantissa:.{digits}f}"
    return f"{text.replace('.', ',')} {_PREFIXES[exponent]}{symbol}"
