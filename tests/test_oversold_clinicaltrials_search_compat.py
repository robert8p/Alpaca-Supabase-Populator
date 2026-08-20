from __future__ import annotations

from app.oversold_clinicaltrials_search_compat import (
    _precise_regulated_candidate,
    _request_studies,
)


def test_regulated_scope_excludes_unrelated_auto_parts_issuer() -> None:
    assert _precise_regulated_candidate(
        "AAP",
        ["ADVANCE AUTO PARTS INC"],
        [{"headline": "Advance Auto reports earnings", "summary": "Management discussed consumer demand and store operations."}],
    ) is False


def test_regulated_scope_includes_biotech_and_explicit_fda_evidence() -> None:
    assert _precise_regulated_candidate("MRNA", ["Moderna, Inc."], []) is False
    assert _precise_regulated_candidate(
        "MRNA",
        ["Moderna, Inc."],
        [{"headline": "Phase 3 clinical trial update", "summary": "The FDA reviewed the vaccine application."}],
    ) is True
    assert _precise_regulated_candidate("EDSA", ["Edesa Biotech, Inc."], []) is True


def test_search_falls_back_from_query_spons_to_fielded_query_term(monkeypatch) -> None:
    calls = []

    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params):
            calls.append(dict(params))
            if "query.spons" in params:
                return Response(403, {})
            return Response(200, {"studies": [{"protocolSection": {}}]})

    monkeypatch.setattr(
        "app.oversold_clinicaltrials_search_compat.httpx.Client",
        Client,
    )
    payload, request_count, error = _request_studies("Moderna, Inc.", 8.0)
    assert error is None
    assert request_count == 2
    assert payload == {"studies": [{"protocolSection": {}}]}
    assert calls[0]["query.spons"] == "Moderna, Inc."
    assert "AREA[LeadSponsorName]" in calls[1]["query.term"]
    assert "format" not in calls[0]
    assert "format" not in calls[1]
