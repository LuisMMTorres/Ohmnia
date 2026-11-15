import numpy as np
import pytest

from circuitos.simulation.post.expr import ExpressionError, evaluate

T = np.linspace(0.0, 1.0, 2001)
V = np.sin(2 * np.pi * 5 * T)
VECS = {
    "time": (T, "s"),
    "v(out)": (V, "V"),
    "v(a)": (V + 1.0, "V"),
    "i(r1)": (np.full_like(T, 2.0), "A"),
    "p(q1)": (2.0 * V, "W"),
}


def ev(expr):
    return evaluate(expr, VECS, "time")


def test_units_follow_the_algebra():
    assert ev("v(out)*i(r1)").unit == "W"
    assert ev("integ(v(a)*i(r1))").unit == "J"
    assert ev("v(out)/i(r1)").unit == "ohm"
    assert ev("deriv(v(out))").unit == "V/s"
    assert ev("v(out) + 1").unit == "V"
    assert ev("db(v(out))").unit == ""
    assert ev("ph(v(out))").unit == "deg"
    assert ev("integ(i(r1))").unit == "C"


def test_values():
    assert ev("v(a,out)").data == pytest.approx(np.ones_like(T))
    assert ev("v(out,0)").data == pytest.approx(V)
    assert ev("integ(i(r1))").data[-1] == pytest.approx(2.0)
    assert ev("rms(v(out))").data[-1] == pytest.approx(1 / np.sqrt(2), rel=1e-4)
    assert ev("avg(v(a))").data[-1] == pytest.approx(1.0, abs=1e-6)
    assert ev("mean(p(q1)) * 2").data[0] == pytest.approx(0.0, abs=1e-9)
    assert ev("movavg(v(a), 0.2)").data[-1] == pytest.approx(1.0, abs=1e-6)
    assert ev("max(v(out), 0)").data.min() == 0.0
    assert ev("deriv(v(out))").data[0] == pytest.approx(2 * np.pi * 5, rel=1e-3)
    assert ev("v(out)^2").data == pytest.approx(V**2)
    assert ev("abs(-v(out)) + sqrt(v(a)*v(a)) - exp(0) + pi*0").data == pytest.approx(
        np.abs(V) + np.abs(V + 1) - 1
    )


@pytest.mark.parametrize(
    ("expr", "msg"),
    [
        ("v(nada)", "não existe"),
        ("__import__('os')", "não permitido"),
        ("v(out).real", "não permitido"),
        ("foo(v(out))", "desconhecida"),
        ("x + 1", "desconhecido"),
        ("v(out) + i(r1)", "incompatíveis"),
        ("", "vazia"),
        ("v(out) +", "inválida"),
        ("movavg(v(out), -1)", "positiva"),
        ("min(v(out))", "dois argumentos"),
    ],
)
def test_errors(expr, msg):
    with pytest.raises(ExpressionError, match=msg):
        ev(expr)


def test_without_scale_and_complex():
    f = np.array([1.0, 10.0])
    h = np.array([1 + 0j, 1j])
    out = evaluate("db(v(out))", {"frequency": (f, "Hz"), "v(out)": (h, "V")}, "frequency")
    assert out.data == pytest.approx([0.0, 0.0])
    with pytest.raises(ExpressionError, match="eixo"):
        evaluate("integ(v(x))", {"v(x)": (np.array([1.0]), "V")})
