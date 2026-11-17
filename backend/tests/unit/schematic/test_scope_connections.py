import pytest
from pydantic import ValidationError

from circuitos.schematic.model import Schematic


def test_scope_connections_accept_real_holes_and_preserve_disconnected_terminals():
    circuit = Schematic(
        bench_scope_channels=2, bench_scope_connections={"1": {"positive": " 2:A12 "}}
    )
    assert circuit.bench_scope_connections["1"].positive == "2:a12"
    assert circuit.bench_scope_connections["1"].negative is None


@pytest.mark.parametrize("connections", [{"1": {"positive": "a99"}}, {"5": {"positive": "a1"}}])
def test_scope_connections_reject_invalid_holes_or_channels(connections):
    with pytest.raises(ValidationError):
        Schematic(bench_scope_connections=connections)
