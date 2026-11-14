"""Traceability rules of the component database.

The part below is FICTITIOUS (manufacturer "Fabricante Fictício"): tests must never carry real
datasheet values typed from memory (rule 1).
"""

import pytest
from pydantic import ValidationError

from circuitos.components import (
    ComponentRecord,
    Parameter,
    available_categories,
    load_schema,
    release,
    release_blockers,
    validate_against_schema,
)
from circuitos.core.errors import DataIntegrityError

DS = {"id": "ds1", "manufacturer": "Fabricante Fictício", "document_number": "FAKE-001"}


def src(page=1):
    return {"datasheet_id": "ds1", "page": page, "location": "Tabela 1"}


def p(symbol, unit, status="revisado", conditions=None, **values):
    return Parameter(
        symbol=symbol,
        unit=unit,
        status=status,
        source=src() if status != "a_verificar" else None,
        conditions=conditions or {},
        **values,
    )


def full_record(**overrides):
    params = {
        "VRRM": p("VRRM", "V", max=100),
        "IF(AV)": p("IF(AV)", "A", max=1, conditions={"TA": {"value": 75, "unit": "degC"}}),
        "IFSM": p("IFSM", "A", max=10, conditions={"t_pulse": {"value": 8.3, "unit": "ms"}}),
        "VF": p(
            "VF",
            "V",
            max=1,
            conditions={"IF": {"value": 1, "unit": "A"}, "Tj": {"value": 25, "unit": "degC"}},
        ),
        "IR": p(
            "IR",
            "uA",
            max=5,
            conditions={"VR": {"value": 100, "unit": "V"}, "Tj": {"value": 25, "unit": "degC"}},
        ),
        "Tj_max": p("Tj_max", "degC", max=150),
    }
    data = {
        "category": "diode.rectifier",
        "schema_version": "1.0",
        "manufacturer": "Fabricante Fictício",
        "part_number": "XD-0001",
        "parameters": params,
        "datasheets": [DS],
    }
    data.update(overrides)
    return ComponentRecord.model_validate(data)


def test_schema_loads():
    schema = load_schema("diode.rectifier")
    assert "VRRM" in schema.required
    assert "diode.rectifier" in available_categories()


def test_unknown_category():
    with pytest.raises(DataIntegrityError):
        load_schema("nao.existe")


def test_full_record_releases():
    rec = full_record()
    assert validate_against_schema(rec) == []
    assert not rec.selectable
    released = release(rec, reviewer="Lauro")
    assert released.selectable and released.review.reviewed_by == "Lauro"


def test_reviewed_parameter_requires_page():
    with pytest.raises(ValidationError, match="página"):
        Parameter(
            symbol="VRRM", unit="V", max=100, status="revisado", source={"datasheet_id": "ds1"}
        )


def test_extracted_parameter_requires_source():
    with pytest.raises(ValidationError, match="fonte"):
        Parameter(symbol="VRRM", unit="V", max=100, status="extraido")


def test_parameter_without_value_must_be_a_verificar():
    Parameter(symbol="VRRM", unit="V")  # empty and flagged: allowed
    with pytest.raises(ValidationError, match="sem valor"):
        Parameter(symbol="VRRM", unit="V", status="extraido", source=src())


@pytest.mark.parametrize(
    "values", [{"min": 2, "max": 1}, {"min": 2, "typ": 1}, {"typ": 3, "max": 2}]
)
def test_min_typ_max_order(values):
    with pytest.raises(ValidationError):
        Parameter(symbol="VF", unit="V", status="a_verificar", **values)


def test_unknown_unit_rejected():
    with pytest.raises(ValidationError):
        Parameter(symbol="VF", unit="parsec_banana")


def test_source_must_reference_known_datasheet():
    bad = p("VRRM", "V", max=100).model_dump()
    bad["source"]["datasheet_id"] = "x"
    with pytest.raises(ValidationError):
        ComponentRecord.model_validate(
            {
                "category": "diode.rectifier",
                "schema_version": "1.0",
                "manufacturer": "F",
                "part_number": "P",
                "parameters": {"VRRM": bad},
                "datasheets": [DS],
            }
        )


def test_key_must_match_symbol():
    with pytest.raises(ValidationError, match="difere"):
        full_record(parameters={"VRSM": p("VRRM", "V", max=1)})


def test_unverified_required_parameter_blocks_release():
    rec = full_record()
    params = dict(rec.parameters)
    params["VRRM"] = Parameter(symbol="VRRM", unit="V", status="a_verificar")
    rec = rec.model_copy(update={"parameters": params})
    assert any("VRRM" in b for b in release_blockers(rec))
    with pytest.raises(DataIntegrityError):
        release(rec, reviewer="Lauro")


def test_missing_conditions_and_wrong_unit_reported():
    rec = full_record()
    params = dict(rec.parameters)
    params["VF"] = p("VF", "A", max=1)
    rec = rec.model_copy(update={"parameters": params, "schema_version": "0.9"})
    problems = validate_against_schema(rec)
    assert any("incompatível" in x for x in problems)
    assert any("condição de teste IF" in x for x in problems)
    assert any("versão" in x for x in problems)


def test_unexpected_parameter_reported():
    rec = full_record()
    params = dict(rec.parameters)
    params["hFE"] = p("hFE", "", typ=100)
    rec = rec.model_copy(update={"parameters": params})
    assert any("não previsto" in x for x in validate_against_schema(rec))


def test_same_symbol_at_other_conditions():
    rec = full_record()
    params = dict(rec.parameters)
    params["IR@125C"] = p(
        "IR",
        "uA",
        max=50,
        conditions={"VR": {"value": 100, "unit": "V"}, "TA": {"value": 125, "unit": "degC"}},
    )
    rec = rec.model_copy(update={"parameters": params})
    assert validate_against_schema(rec) == []
