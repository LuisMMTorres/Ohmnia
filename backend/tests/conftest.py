import os
import tempfile

import pytest

# Never touch the user's real catalogue/datasheet folder from tests.
os.environ.setdefault("CIRCUITOS_DATA_DIR", tempfile.mkdtemp(prefix="circuitos-test-"))

from circuitos.simulation.backend import BatchNgspiceBackend, SharedNgspiceBackend


def pytest_collection_modifyitems(config, items):
    if SharedNgspiceBackend.available() or BatchNgspiceBackend.available():
        return
    skip = pytest.mark.skip(reason="ngspice não instalado")
    for item in items:
        if "ngspice" in item.keywords:
            item.add_marker(skip)
