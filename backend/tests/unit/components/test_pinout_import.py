"""Adding sourced pinouts must preserve the user's existing catalogue review."""

from pathlib import Path

from circuitos.components.repository import ComponentRepository, load_record_file


def test_new_pinout_preserves_parameter_review_and_identity():
    path = Path(__file__).parents[4] / "data/components/bjt/onsemi-2n3904.yaml"
    incoming = load_record_file(path)
    assert incoming.pinout is not None
    repo = ComponentRepository()
    repo.import_records([incoming.model_copy(update={"pinout": None})])
    for key in incoming.parameters:
        repo.set_parameter_status(incoming.id, key, "revisado")
    repo.release(incoming.id, "fixture")
    before = repo.get(incoming.id)
    assert before.selectable
    report = repo.import_records([incoming])
    after = repo.get(incoming.id)
    assert report.updated
    assert after.pinout == incoming.pinout
    assert after.parameters == before.parameters
    assert after.review == before.review
    assert after.id == before.id and after.catalog_revision == before.catalog_revision
    assert after.selectable == before.selectable


def test_import_does_not_overwrite_an_existing_pinout_review():
    path = Path(__file__).parents[4] / "data/components/bjt/onsemi-2n3904.yaml"
    incoming = load_record_file(path)
    assert incoming.pinout is not None
    reviewed = incoming.pinout.model_copy(update={"status": "revisado", "note": "Revisão local"})
    repo = ComponentRepository()
    repo.import_records([incoming.model_copy(update={"pinout": reviewed})])
    report = repo.import_records([incoming])
    assert not report.updated
    assert repo.get(incoming.id).pinout == reviewed
