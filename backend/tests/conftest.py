import pytest

from circuitos.simulation.backend import BatchNgspiceBackend, SharedNgspiceBackend


def pytest_collection_modifyitems(config, items):
    if SharedNgspiceBackend.available() or BatchNgspiceBackend.available():
        return
    skip = pytest.mark.skip(reason="ngspice não instalado")
    for item in items:
        if "ngspice" in item.keywords:
            item.add_marker(skip)
