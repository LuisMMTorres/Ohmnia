from pathlib import Path

import pytest

from circuitos.components.models import Parameter
from circuitos.components.repository import (
    ComponentRepository,
    ParamFilter,
    component_id,
    dump_record,
    guaranteed_value,
    load_record_file,
    load_records_file,
)
from circuitos.core.errors import DataIntegrityError
from circuitos.datasheets.queue import load_queue

CATALOG = Path(__file__).parents[4] / "data" / "components"

FAMILY = """
family: XF1–XF2
category: diode.rectifier
schema_version: "1.0"
manufacturer: Fabricante Fictício
datasheets: [{id: ds, manufacturer: F}]
parameters:
  IF(AV): {max: 1, unit: A, status: extraido, conditions: {TA: 75 degC}, source: {page: 1}}
  IFSM: {max: 30, unit: A, status: extraido, conditions: {t_pulse: 8.3 ms}, source: {page: 1}}
  Tj_max: {max: 150, unit: degC, status: extraido, source: {page: 1}}
  VF: {max: 1.1, unit: V, status: extraido, conditions: {IF: 1 A, TA: 25 degC}, source: {page: 2}}
per_part:
  VRRM: {unit: V, status: extraido, source: {page: 1}}
  VDC: {unit: V, status: extraido, source: {page: 1}}
  IR: {max: 5, unit: uA, status: extraido, conditions: {VR: "=VDC", TA: 25 degC}, source: {page: 2}}
parts:
  XF1: {VRRM: 50, VDC: 50, IR: {}}
  XF2: {VRRM: 100, VDC: 100, IR: {}}
"""


@pytest.fixture
def family_file(tmp_path):
    path = tmp_path / "fam.yaml"
    path.write_text(FAMILY, encoding="utf-8")
    return path


def test_family_file_expands_parts(family_file):
    records = load_records_file(family_file)
    assert [r.part_number for r in records] == ["XF1", "XF2"]
    xf2 = records[1]
    assert xf2.parameters["VRRM"].max == 100
    assert xf2.parameters["IR"].conditions["VR"].value == 100  # "=VDC" resolved per part
    assert xf2.parameters["VF"].source.datasheet_id == "ds"  # default datasheet
    assert xf2.id == component_id("Fabricante Fictício", "XF2")
    with pytest.raises(DataIntegrityError):
        load_record_file(family_file)


def test_bad_reference_in_condition(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(FAMILY.replace('"=VDC"', '"=NADA"'), encoding="utf-8")
    with pytest.raises(DataIntegrityError, match="NADA"):
        load_records_file(path)


def test_import_keeps_reviews_until_revision_bump(family_file):
    repo = ComponentRepository()
    report = repo.import_directory(family_file.parent)
    assert len(report.added) == 2 and not report.errors
    rid = component_id("Fabricante Fictício", "XF1")
    repo.set_parameter_status(rid, "VRRM", "revisado")
    assert repo.import_directory(family_file.parent).unchanged
    assert repo.get(rid).parameters["VRRM"].status == "revisado"
    family_file.write_text(FAMILY + "catalog_revision: 2\n", encoding="utf-8")
    assert len(repo.import_directory(family_file.parent).updated) == 2
    assert repo.get(rid).parameters["VRRM"].status == "extraido"


def test_import_reports_invalid_files(tmp_path):
    (tmp_path / "x.yaml").write_text("- not a mapping", encoding="utf-8")
    (tmp_path / "y.yaml").write_text(
        FAMILY.replace("unit: V,", "unit: banana,", 1), encoding="utf-8"
    )
    report = ComponentRepository().import_directory(tmp_path)
    assert set(report.errors) == {"x.yaml", "y.yaml"}


def test_review_flow_and_release(family_file):
    repo = ComponentRepository()
    repo.import_directory(family_file.parent)
    rid = component_id("Fabricante Fictício", "XF1")
    with pytest.raises(DataIntegrityError):
        repo.release(rid, "Lauro")
    for key in repo.get(rid).parameters:
        repo.set_parameter_status(rid, key, "revisado")
    assert repo.get(rid).review.status == "em_revisao"
    released = repo.release(rid, "Lauro")
    assert released.selectable
    # Un-reviewing a parameter takes the part out of automatic selection again.
    assert repo.set_parameter_status(rid, "VF", "a_verificar", note="conferir").review.status == (
        "em_revisao"
    )
    with pytest.raises(DataIntegrityError):
        repo.set_parameter_status(rid, "NADA", "revisado")


def test_search_and_filters(family_file):
    repo = ComponentRepository()
    repo.import_directory(family_file.parent)
    v = {"value": 80, "unit": "V"}
    assert [
        r.part_number for r in repo.search(filters=[ParamFilter(symbol="VRRM", op=">=", value=v)])
    ] == ["XF2"]
    assert [
        r.part_number for r in repo.search(filters=[ParamFilter(symbol="VRRM", op="<=", value=v)])
    ] == ["XF1"]
    mv = {"value": 1200, "unit": "mV"}
    assert len(repo.search(filters=[ParamFilter(symbol="VF", op="<=", value=mv)])) == 2
    assert repo.search(filters=[ParamFilter(symbol="trr", op="<=", value=v)]) == []
    wrong_unit = {"value": 1, "unit": "A"}
    assert repo.search(filters=[ParamFilter(symbol="VRRM", op=">=", value=wrong_unit)]) == []
    assert len(repo.search(category="diode")) == 2
    assert len(repo.search(text="xf2")) == 2  # the family name "XF1–XF2" matches too
    assert repo.search(text="nada") == []
    assert len(repo.search(review_status="liberado")) == 0
    assert repo.categories() == {"diode.rectifier": 2}


def test_guaranteed_value_semantics():
    rating = Parameter(symbol="VRRM", unit="V", max=600)
    assert guaranteed_value(rating, ">=", is_rating=True) == 600
    assert guaranteed_value(rating, ">=", is_rating=False) is None
    hfe = Parameter(symbol="hFE", unit="", min=110, max=800)
    assert guaranteed_value(hfe, ">=", is_rating=False) == 110
    assert guaranteed_value(hfe, "<=", is_rating=False) == 800
    typ = Parameter(symbol="Cj", unit="pF", typ=15)
    assert guaranteed_value(typ, "<=", is_rating=False) == 15


def test_dump_roundtrip(family_file, tmp_path):
    record = load_records_file(family_file)[0]
    out = tmp_path / "out" / "x.yaml"
    out.parent.mkdir()
    out.write_text(dump_record(record), encoding="utf-8")
    again = load_record_file(out)
    assert again.parameters == record.parameters and again.id == record.id


# ---------------------------------------------------------------------------- catalogue --


def test_catalogue_files_are_valid_and_traceable():
    """Every catalogue file loads, conforms to its schema, and every value cites a page."""
    repo = ComponentRepository()
    report = repo.import_directory(CATALOG)
    assert not report.errors, report.errors
    records = repo.search()
    assert len(records) >= 28 + 107
    # a datasheet without URL must be a PDF the user keeps locally (listed in the queue by hash)
    local = {
        i.local.sha256 for i in load_queue() if i.local is not None and i.local.situacao == "ok"
    }
    for record in records:
        assert record.datasheets and all(d.sha256 for d in record.datasheets)
        for d in record.datasheets:
            assert d.url or d.sha256 in local, (
                record.part_number,
                "datasheet sem link nem cópia local",
            )
        for key, param in record.parameters.items():
            if param.has_value:
                assert param.source is not None and param.source.page, (record.part_number, key)
                assert param.status in ("extraido", "revisado", "a_verificar"), (
                    record.part_number,
                    key,
                )
                if param.status == "a_verificar":
                    # a doubtful value must say why
                    assert param.note, (record.part_number, key)
