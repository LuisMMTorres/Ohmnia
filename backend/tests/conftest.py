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
    """Repository with the reviewed part of the catalogue, every value marked reviewed and released.

    The files are listed in ``fixtures/catalogo-revisado.txt``: records transcribed later stay out
    until the user reviews them, so the design tests keep a stable, reviewed catalogue.

    Only for tests of the design flow: it simulates the user's review (rule 5 still applies,
    the records go through the normal release path). The values are the datasheet ones.
    """
    from pathlib import Path

    from circuitos.components.repository import ComponentRepository

    # a file, not :memory:, so the API test client (another thread) sees the same database
    repo = ComponentRepository(f"sqlite:///{tempfile.mkdtemp(prefix='circuitos-rev-')}/c.db")
    from circuitos.components.repository import load_records_file

    root = Path(__file__).resolve().parents[2] / "data" / "components"
    listed = Path(__file__).with_name("fixtures") / "catalogo-revisado.txt"
    files = [ln for ln in listed.read_text(encoding="utf-8").splitlines() if ln and ln[0] != "#"]
    repo.import_records([r for f in files for r in load_records_file(root / f)])
    for record in repo.search():
        for key, param in record.parameters.items():
            if param.status == "extraido":
                repo.set_parameter_status(record.id, key, "revisado")
        # missing required values stay unreleased, as in real use
        with contextlib.suppress(Exception):
            repo.release(record.id, "teste")
    return repo


@pytest.fixture(scope="session")
def firing_catalogue(reviewed_catalogue):
    """Reviewed catalogue plus the parts of the DM-RETC1 firing circuit (LM393, BC337, MOC3021,
    the zero-crossing MOC3041 that must be refused, and the BT151-500R of the user's design),
    released as in :func:`reviewed_catalogue`. A separate database, so other tests keep theirs."""
    from pathlib import Path

    from circuitos.components.repository import ComponentRepository, load_records_file

    repo = ComponentRepository(f"sqlite:///{tempfile.mkdtemp(prefix='circuitos-fd-')}/c.db")
    root = Path(__file__).resolve().parents[2] / "data" / "components"
    listed = Path(__file__).with_name("fixtures") / "catalogo-revisado.txt"
    files = [ln for ln in listed.read_text(encoding="utf-8").splitlines() if ln and ln[0] != "#"]
    files += [
        "comparator/ti-lm393.yaml",
        "bjt/onsemi-bc337.yaml",
        "optocoupler/onsemi-moc3021.yaml",
        "optocoupler/onsemi-moc3041.yaml",
        "thyristor/ween-bt151-500r.yaml",
    ]
    repo.import_records([r for f in dict.fromkeys(files) for r in load_records_file(root / f)])
    for record in repo.search():
        for key, param in record.parameters.items():
            if param.status == "extraido":
                repo.set_parameter_status(record.id, key, "revisado")
        with contextlib.suppress(Exception):
            repo.release(record.id, "teste")
    return repo
