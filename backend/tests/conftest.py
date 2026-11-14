import contextlib
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


@pytest.fixture(scope="session")
def reviewed_catalogue():
    """Repository with the real catalogue, every extracted value marked as reviewed and released.

    Only for tests of the design flow: it simulates the user's review (rule 5 still applies,
    the records go through the normal release path). The values are the datasheet ones.
    """
    from pathlib import Path

    from circuitos.components.repository import ComponentRepository

    # a file, not :memory:, so the API test client (another thread) sees the same database
    repo = ComponentRepository(f"sqlite:///{tempfile.mkdtemp(prefix='circuitos-rev-')}/c.db")
    repo.import_directory(Path(__file__).resolve().parents[2] / "data" / "components")
    for record in repo.search():
        for key, param in record.parameters.items():
            if param.status == "extraido":
                repo.set_parameter_status(record.id, key, "revisado")
        # missing required values stay unreleased, as in real use
        with contextlib.suppress(Exception):
            repo.release(record.id, "teste")
    return repo
