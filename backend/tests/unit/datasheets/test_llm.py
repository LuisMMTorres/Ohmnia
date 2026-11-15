"""LLM-assisted mapping: only proposals whose quote and numbers are on the page survive.

No network: the Anthropic client is replaced by a stub returning a fixed JSON answer.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pymupdf

from circuitos.datasheets.extract import extract_document
from circuitos.datasheets.llm import MODEL, LlmParameter, Rejected, propose, verify
from circuitos.datasheets.mapping import Candidate

from .synthetic import rectifier_pdf


def _doc():
    with pymupdf.open(stream=rectifier_pdf(), filetype="pdf") as pdf:
        return extract_document(pdf)


def _p(**kw: Any) -> LlmParameter:
    base = {
        "key": "VRRM",
        "max": 800,
        "unit": "V",
        "page": 1,
        "excerpt": "Peak repetitive reverse voltage V RRM 800 V",
    }
    return LlmParameter.model_validate(base | kw)


def test_verified_proposal_becomes_candidate() -> None:
    out = verify(_p(), _doc(), "diode.rectifier")
    assert isinstance(out, Candidate)
    assert out.method == "llm" and out.max == 800 and out.bbox is not None


def test_number_not_in_quote_is_rejected() -> None:
    out = verify(_p(max=1000), _doc(), "diode.rectifier")
    assert isinstance(out, Rejected) and "1000" in out.reason


def test_invented_quote_is_rejected() -> None:
    out = verify(_p(excerpt="VRRM 1000 V"), _doc(), "diode.rectifier")
    assert isinstance(out, Rejected) and "trecho" in out.reason


def test_wrong_page_and_unit_are_rejected() -> None:
    assert isinstance(verify(_p(page=7), _doc(), "diode.rectifier"), Rejected)
    assert isinstance(verify(_p(unit="A"), _doc(), "diode.rectifier"), Rejected)


class _Stub:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.kwargs: dict[str, Any] = {}
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            stop_reason="end_turn",
            model=MODEL,
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
        )


def test_propose_splits_verified_and_rejected() -> None:
    stub = _Stub(
        {
            "parameters": [
                {
                    "key": "VRRM",
                    "min": None,
                    "typ": None,
                    "max": 800,
                    "unit": "V",
                    "conditions": [],
                    "page": 1,
                    "excerpt": "Peak repetitive reverse voltage V RRM 800 V",
                },
                {
                    "key": "IFSM",
                    "min": None,
                    "typ": None,
                    "max": 30,
                    "unit": "A",
                    "conditions": [],
                    "page": 1,
                    "excerpt": "IFSM 30 A",
                },
            ]
        }
    )
    result = propose(rectifier_pdf(), _doc(), "diode.rectifier", client=stub)
    assert [c.key for c in result.candidates] == ["VRRM"]
    assert [r.proposal.key for r in result.rejected] == ["IFSM"]
    assert stub.kwargs["model"] == MODEL
    assert stub.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert stub.kwargs["messages"][0]["content"][0]["type"] == "document"
