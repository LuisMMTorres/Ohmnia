"""Derived waveforms: arithmetic expressions on simulation vectors, with unit inference.

Syntax (case-insensitive, like ngspice): vectors ``v(out)``, ``v(a,b)`` (difference),
``i(r1)``, any vector name of the plot (``time``, ``frequency``, ``onoise_spectrum``); operators
``+ - * / **`` (or ``^``); constants ``pi`` and ``e``; functions:

* elementwise: ``abs sqrt exp ln log log10 sin cos tan atan min max real imag mag db ph``;
* along the scale (time or frequency): ``integ`` (cumulative trapezoidal integral), ``deriv``,
  ``avg`` (running mean since the start), ``rms`` (running RMS), ``movavg(x, window)`` (moving
  average over ``window`` in scale units), ``mean`` (scalar mean over the record).

The expression is parsed into a Python AST and only the nodes above are evaluated (no names,
attributes or calls outside the table). Units are carried by evaluating the same tree on
:mod:`pint` quantities, so ``v(out)*i(r1)`` is in W and ``integ(p(q1))`` in J.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pint
from numpy.typing import NDArray

from circuitos.core.units import Q_, parse_unit, ureg

Array = NDArray[Any]


class ExpressionError(ValueError):
    """Invalid expression (message in Portuguese)."""


_VEC = re.compile(r"\b([vi])\(\s*([^()]+?)\s*\)", re.IGNORECASE)
_PREFERRED = ("V", "A", "W", "ohm", "S", "J", "C", "Wb", "s", "Hz", "V/s", "A/s", "F", "H")


@dataclass(frozen=True)
class Evaluated:
    data: Array
    unit: str


def _prepare(expr: str, names: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """Replace vector references by identifiers; ``names`` maps vector name → unit."""
    lookup = {k.lower(): k for k in names}
    mapping: dict[str, str] = {}

    def ident(vec: str) -> str:
        key = vec.lower()
        if key not in lookup:
            raise ExpressionError(f"Vetor {vec!r} não existe nesta análise")
        for k, v in mapping.items():
            if v == lookup[key]:
                return k
        k = f"_v{len(mapping)}"
        mapping[k] = lookup[key]
        return k

    def repl(m: re.Match[str]) -> str:
        kind, args = m.group(1).lower(), m.group(2)
        parts = [a.strip() for a in args.split(",")]
        if kind == "v" and len(parts) == 2:
            a = "0" if parts[0] == "0" else ident(f"v({parts[0]})")
            b = "0" if parts[1] == "0" else ident(f"v({parts[1]})")
            return f"({a}-{b})"
        if len(parts) != 1:
            raise ExpressionError(f"Referência inválida: {m.group(0)}")
        if kind == "v" and parts[0] == "0":
            return "0"
        return ident(f"{kind}({parts[0]})")

    text = _VEC.sub(repl, expr.replace("^", "**"))
    # bare vector names (time, frequency, onoise_spectrum, p(q1)...) longest first
    for key in sorted(lookup, key=len, reverse=True):
        if "(" in key:
            while key in text.lower():
                idx = text.lower().index(key)
                text = text[:idx] + ident(key) + text[idx + len(key) :]
            continue
        pattern = re.compile(rf"(?<![\w.]){re.escape(key)}(?![\w(])", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(ident(key), text)
    return text, mapping


class _Wild:
    """Unit of a bare constant: adopts the unit of the other operand of + and −."""


_WILD = _Wild()
UnitVal = pint.Quantity | _Wild


def _unit_of(x: UnitVal) -> pint.Quantity:
    return Q_(1.0, "") if isinstance(x, _Wild) else x


def _addsub(a: UnitVal, b: UnitVal, op: str) -> UnitVal:
    if isinstance(a, _Wild):
        return b
    if isinstance(b, _Wild):
        return a
    try:
        return a + b if op == "+" else a - b
    except pint.DimensionalityError as exc:
        raise ExpressionError(f"Unidades incompatíveis: {a.units:~} e {b.units:~}") from exc


class _Evaluator:
    def __init__(
        self, env: Mapping[str, Array], units: Mapping[str, str], scale: Array | None, sunit: str
    ):
        self.env = env
        self.units = units
        self.scale = scale
        self.sunit = sunit

    # numeric -------------------------------------------------------------------------------
    def _need_scale(self, fn: str) -> Array:
        if self.scale is None:
            raise ExpressionError(f"{fn}() precisa de uma análise com eixo (tempo ou frequência)")
        return self.scale

    def _integ(self, y: Array) -> Array:
        x = self._need_scale("integ")
        steps = np.diff(x) * (y[1:] + y[:-1]) / 2
        return np.concatenate(([0.0], np.cumsum(steps)))

    def _num_call(self, fn: str, args: list[Any]) -> Any:
        def one() -> Any:
            if len(args) != 1:
                raise ExpressionError(f"{fn}() recebe um argumento")
            return args[0]

        simple: dict[str, Callable[[Any], Any]] = {
            "abs": np.abs,
            "mag": np.abs,
            "sqrt": np.sqrt,
            "exp": np.exp,
            "ln": np.log,
            "log": np.log,
            "log10": np.log10,
            "sin": np.sin,
            "cos": np.cos,
            "tan": np.tan,
            "atan": np.arctan,
            "real": np.real,
            "imag": np.imag,
        }
        if fn in simple:
            return simple[fn](one())
        if fn == "db":
            with np.errstate(divide="ignore"):
                return 20 * np.log10(np.abs(one()))
        if fn == "ph":
            return np.degrees(np.unwrap(np.angle(one())))
        if fn in ("min", "max"):
            if len(args) != 2:
                raise ExpressionError(f"{fn}() recebe dois argumentos")
            return (np.minimum if fn == "min" else np.maximum)(args[0], args[1])
        if fn == "integ":
            return self._integ(np.broadcast_to(one(), self._need_scale(fn).shape).astype(float))
        if fn == "deriv":
            x = self._need_scale(fn)
            return np.gradient(np.broadcast_to(one(), x.shape), x)
        if fn in ("avg", "rms", "mean"):
            x = self._need_scale(fn)
            y = np.broadcast_to(one(), x.shape)
            y2 = np.abs(y) ** 2 if fn == "rms" else y
            cum = self._integ(np.asarray(y2))
            span = x - x[0]
            if fn == "mean":
                return np.full(x.shape, cum[-1] / span[-1]) if span[-1] > 0 else y
            with np.errstate(invalid="ignore", divide="ignore"):
                out = np.where(span > 0, cum / np.where(span > 0, span, 1), y2)
            return np.sqrt(out) if fn == "rms" else out
        if fn == "movavg":
            if len(args) != 2:
                raise ExpressionError("movavg(x, janela) recebe dois argumentos")
            x = self._need_scale(fn)
            width = float(np.asarray(args[1]).flat[0])
            if not width > 0:
                raise ExpressionError("A janela de movavg deve ser positiva")
            y = np.broadcast_to(args[0], x.shape).astype(float)
            cum = self._integ(y)
            lo = np.maximum(x - width, x[0])
            span = x - lo
            with np.errstate(invalid="ignore", divide="ignore"):
                return np.where(span > 0, (cum - np.interp(lo, x, cum)) / span, y)
        raise ExpressionError(f"Função desconhecida: {fn}()")

    # unit ----------------------------------------------------------------------------------
    def _unit_call(self, fn: str, args: list[UnitVal]) -> UnitVal:
        if all(isinstance(x, _Wild) for x in args):
            return _WILD  # a function of constants is a constant
        a = args[0] if args else _WILD
        same = ("abs", "mag", "real", "imag", "min", "max", "avg", "rms", "movavg", "mean")
        if fn in same:
            return a
        if fn == "sqrt":
            return _unit_of(a) ** 0.5
        if fn == "integ":
            return _unit_of(a) * Q_(1.0, self.sunit)
        if fn == "deriv":
            return _unit_of(a) / Q_(1.0, self.sunit)
        if fn == "ph":
            return Q_(1.0, "deg")
        return Q_(1.0, "")  # db, exp, log, trig: dimensionless

    # tree walk -----------------------------------------------------------------------------
    def eval(self, node: ast.AST, units: bool) -> Any:
        if isinstance(node, ast.Expression):
            return self.eval(node.body, units)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return _WILD if units else float(node.value)
        if isinstance(node, ast.Name):
            name = node.id
            if name in self.env:
                if units:
                    return Q_(1.0, parse_unit(self.units.get(name, "")))
                return self.env[name]
            if name.lower() in ("pi", "e"):
                return _WILD if units else (np.pi if name.lower() == "pi" else np.e)
            raise ExpressionError(f"Nome desconhecido: {name}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            v = self.eval(node.operand, units)
            if units:
                return v
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            a, b = self.eval(node.left, units), self.eval(node.right, units)
            op = node.op
            if units:
                if isinstance(a, _Wild) and isinstance(b, _Wild):
                    return _WILD
                if isinstance(op, ast.Add | ast.Sub):
                    return _addsub(a, b, "+" if isinstance(op, ast.Add) else "-")
                if isinstance(op, ast.Mult):
                    return _unit_of(a) * _unit_of(b)
                if isinstance(op, ast.Div):
                    return _unit_of(a) / _unit_of(b)
                if isinstance(op, ast.Pow):
                    exp = self.eval(node.right, units=False)
                    return _unit_of(a) ** float(np.asarray(exp).flat[0])
            else:
                with np.errstate(divide="ignore", invalid="ignore"):
                    if isinstance(op, ast.Add):
                        return a + b
                    if isinstance(op, ast.Sub):
                        return a - b
                    if isinstance(op, ast.Mult):
                        return a * b
                    if isinstance(op, ast.Div):
                        return a / b
                    if isinstance(op, ast.Pow):
                        return a**b
            raise ExpressionError("Operador não permitido")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = node.func.id.lower()
            args = [self.eval(a, units) for a in node.args]
            return self._unit_call(fn, args) if units else self._num_call(fn, args)
        raise ExpressionError(f"Elemento não permitido na expressão: {ast.dump(node)[:40]}")


def _unit_text(q: UnitVal) -> str:
    if isinstance(q, _Wild):
        return ""
    if q.dimensionless:
        return "deg" if q.units == ureg.deg else ""
    for u in _PREFERRED:
        if q.dimensionality == ureg(u).dimensionality:
            return u
    return f"{q.units:~}"


def evaluate(
    expr: str,
    vectors: Mapping[str, tuple[Array, str]],
    scale: str | None = None,
) -> Evaluated:
    """Evaluate ``expr`` on ``vectors`` (name → (data, unit)); ``scale`` names the x vector."""
    if not expr.strip():
        raise ExpressionError("Expressão vazia")
    if len(expr) > 2000:
        raise ExpressionError("Expressão longa demais")
    text, mapping = _prepare(expr, {k: v[1] for k, v in vectors.items()})
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Expressão inválida: {expr}") from exc
    env = {k: vectors[v][0] for k, v in mapping.items()}
    units = {k: vectors[v][1] for k, v in mapping.items()}
    x = None
    sunit = ""
    if scale is not None and scale in vectors:
        x = np.asarray(vectors[scale][0]).real.astype(float)
        sunit = vectors[scale][1]
    ev = _Evaluator(env, units, x, sunit)
    unit = _unit_text(ev.eval(tree, units=True))
    data = np.asarray(ev.eval(tree, units=False))
    if x is not None and data.ndim == 0:
        data = np.full(x.shape, data)
    return Evaluated(data, unit)
