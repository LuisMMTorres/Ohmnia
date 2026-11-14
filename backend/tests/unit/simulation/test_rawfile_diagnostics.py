import numpy as np
import pytest

from circuitos.core.errors import ConvergenceError, SimulationError
from circuitos.simulation.diagnostics import raise_for_log
from circuitos.simulation.rawfile import parse_rawfile
from circuitos.simulation.results import SimulationResult, canonical_name, kind_for, unit_for

ASCII_RAW = b"""Title: teste
Date: hoje
Plotname: Transient Analysis
Flags: real
No. Variables: 3
No. Points: 2
Variables:
\t0\ttime\ttime
\t1\tv(out)\tvoltage
\t2\ti(v1)\tcurrent
Values:
 0\t0.0
\t1.0
\t-1e-3
 1\t1e-3
\t2.0
\t-2e-3

Plotname: AC Analysis
Flags: complex
No. Variables: 2
No. Points: 1
Variables:
\t0\tfrequency\tfrequency grid=3
\t1\tv(out)\tvoltage
Values:
 0\t1.0e3,0.0
\t0.5,-0.5
"""


def test_parse_ascii_rawfile():
    plots = parse_rawfile(ASCII_RAW)
    tran, ac = plots
    assert (tran.name, tran.kind, tran.scale, tran.title) == (
        "tran1",
        "tran",
        "time",
        "Transient Analysis",
    )
    assert tran["v(out)"].data.tolist() == [1.0, 2.0]
    assert tran["i(v1)"].unit == "A"
    assert tran["time"].quantity().m_as("ms").tolist() == [0, 1]
    assert ac.kind == "ac" and ac["frequency"].data.dtype == float
    assert ac["v(out)"].is_complex and ac["v(out)"].data[0] == 0.5 - 0.5j
    with pytest.raises(KeyError, match="não existe"):
        tran["v(nada)"]


def test_parse_binary_rawfile():
    header = (
        b"Title: t\nPlotname: Operating Point\nFlags: real\nNo. Variables: 2\nNo. Points: 1\n"
        b"Variables:\n\t0\tv(a)\tvoltage\n\t1\ti(v1)\tcurrent\nBinary:\n"
    )
    raw = header + np.array([5.0, -0.01], dtype="<f8").tobytes()
    (op,) = parse_rawfile(raw)
    assert op.kind == "op" and op.scale is None
    assert op["v(a)"].data[0] == 5.0


def test_naming_helpers():
    assert canonical_name("V1#branch", "current") == "i(v1)"
    assert canonical_name("out", "voltage") == "v(out)"
    assert canonical_name("v(out)", "voltage") == "v(out)"
    assert unit_for("", "i(r1)") == "A" and unit_for("", "v(x)") == "V"
    assert unit_for("", "@q1[ic]") == ""
    assert kind_for("dc1") == "dc" and kind_for("sens") == "other"


def test_result_plot_lookup():
    result = SimulationResult(backend="x", plots=parse_rawfile(ASCII_RAW))
    assert result.plot("ac").name == "ac1"
    with pytest.raises(KeyError):
        result.plot("op")


@pytest.mark.parametrize(
    ("log", "cls", "text"),
    [
        ("Error: timestep too small; time = 1e-3", ConvergenceError, "Passo de tempo"),
        ("singular matrix: check node out", ConvergenceError, "singular"),
        ("Warning: gmin stepping failed", ConvergenceError, "ponto de operação"),
        ("Error: unknown model d1n4007", SimulationError, "Modelo"),
        ("Error on line 3 : xyz", SimulationError, "sintaxe"),
    ],
)
def test_classified_errors(log, cls, text):
    with pytest.raises(cls, match=text) as info:
        raise_for_log(log, no_output=False)
    assert info.value.log == log


def test_generic_failure_only_when_no_output():
    raise_for_log("tudo certo", no_output=False)
    with pytest.raises(SimulationError, match="nenhum vetor"):
        raise_for_log("tudo certo", no_output=True)
    with pytest.raises(SimulationError, match="fatal"):
        raise_for_log("fatal: algo", no_output=True)
