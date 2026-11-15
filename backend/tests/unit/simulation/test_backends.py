import numpy as np
import pytest

from circuitos.core.errors import SimulationError, SimulatorUnavailableError
from circuitos.simulation.backend import (
    BatchNgspiceBackend,
    SharedNgspiceBackend,
    make_backend,
    normalise_netlist,
)

RC = """rc
V1 in 0 PULSE(0 1 0 1n 1n 5m 10m) AC 1
R1 in out 1k
C1 out 0 1u
.op
.tran 10u 5m
.ac dec 5 10 100k
"""

pytestmark = pytest.mark.ngspice


def test_normalise_netlist():
    assert normalise_netlist("t\nR1 a 0 1")[-1] == ".end"
    with pytest.raises(SimulationError):
        normalise_netlist("   ")


@pytest.fixture(scope="module")
def shared():
    if not SharedNgspiceBackend.available():
        pytest.skip("libngspice indisponível")
    return SharedNgspiceBackend()


def test_shared_and_batch_agree(shared):
    progress = []
    a = shared.run(RC, lambda f, m: progress.append(f))
    b = BatchNgspiceBackend().run(RC)
    assert progress[-1] == 1.0
    for kind in ("op", "tran", "ac"):
        pa, pb = a.plot(kind), b.plot(kind)
        assert pa.name == pb.name and pa.scale == pb.scale
        assert set(pa.vectors) == set(pb.vectors)
        for name, vec in pa.vectors.items():
            assert vec.unit == pb[name].unit
            np.testing.assert_allclose(vec.data, pb[name].data, rtol=1e-9, atol=1e-15)


def test_shared_reports_syntax_error(shared):
    with pytest.raises(SimulationError):
        shared.run("t\nR1 a 0\n.op\n")


def test_shared_can_run_twice(shared):
    shared.run(RC)
    r = shared.run("div\nV1 a 0 10\nR1 a b 1k\nR2 b 0 1k\n.op\n")
    assert r.plot("op")["v(b)"].data[0] == pytest.approx(5.0)


def test_batch_reports_errors():
    with pytest.raises(SimulationError):
        BatchNgspiceBackend().run("t\nQ1 a b c nomodel\n.op\n")


def test_batch_missing_executable():
    with pytest.raises(SimulatorUnavailableError):
        BatchNgspiceBackend(executable="nao-existe-ngspice").run(RC)


def test_batch_timeout():
    long = "t\nV1 a 0 SIN(0 1 1k)\nR1 a 0 1k\n.tran 1m 10 0 1n\n"
    with pytest.raises(SimulationError, match="Tempo limite"):
        BatchNgspiceBackend(timeout_s=0.5).run(long)


def test_make_backend_preferences(monkeypatch):
    assert make_backend("batch").name == "ngspice-batch"
    monkeypatch.setattr(SharedNgspiceBackend, "available", classmethod(lambda cls: False))
    monkeypatch.setattr(BatchNgspiceBackend, "available", classmethod(lambda cls: False))
    with pytest.raises(SimulatorUnavailableError):
        make_backend()


def test_shared_missing_library():
    with pytest.raises(SimulatorUnavailableError):
        SharedNgspiceBackend(library="/nao/existe/libngspice.so")


def test_dc_sweep_scale_is_the_same_in_both_backends(shared):
    net = "t\nI1 0 a DC 1m\nR1 a 0 1k\n.dc I1 0 1m 0.5m\n"
    a, b = shared.run(net).plot("dc"), BatchNgspiceBackend().run(net).plot("dc")
    assert a.scale == b.scale == "i-sweep"
    np.testing.assert_allclose(a["v(a)"].data, b["v(a)"].data)
