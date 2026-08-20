from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.oversold_primary_evidence import (
    _fda_article_from_payload,
    _parse_filing_documents,
    _select_documents,
    _select_filing_rows,
    _trial_article_from_payload,
    extract_exact_identifiers,
)
from app.oversold_primary_evidence_runtime import _merge_articles
from app.oversold_primary_evidence_scoring import patch_module as patch_scoring
from app.oversold_primary_evidence_store import _records


CUTOFF = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)


def test_sec_filing_selection_is_strictly_point_in_time() -> None:
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-26-000001", "0001-26-000002", "0001-26-000003"],
                "form": ["8-K", "8-K", "10-Q"],
                "filingDate": ["2026-08-20", "2026-08-20", "2026-08-10"],
                "acceptanceDateTime": [
                    "2026-08-20T16:30:00Z",
                    "2026-08-20T19:00:00Z",
                    "2026-08-10T12:00:00Z",
                ],
                "primaryDocument": ["before.htm", "after.htm", "old.htm"],
                "items": ["2.02", "8.01", ""],
            }
        }
    }
    rows, excluded = _select_filing_rows(submissions, CUTOFF)
    assert [row["accessionNumber"] for row in rows] == ["0001-26-000001"]
    assert rows[0]["_available_at"] == datetime(2026, 8, 20, 16, 30, tzinfo=UTC)
    assert excluded == 1


def test_filing_document_parser_keeps_primary_and_company_release_exhibit() -> None:
    page = """
    <table>
      <tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
      <tr><td>1</td><td>Current report</td><td><a href="issuer-8k.htm">issuer-8k.htm</a></td><td>8-K</td><td>1000</td></tr>
      <tr><td>2</td><td>Press release</td><td><a href="ex991.htm">ex991.htm</a></td><td>EX-99.1</td><td>2000</td></tr>
      <tr><td>3</td><td>XBRL</td><td><a href="instance.xml">instance.xml</a></td><td>EX-101</td><td>3000</td></tr>
    </table>
    """
    rows = _parse_filing_documents(page)
    selected = _select_documents(rows, primary_document="issuer-8k.htm", form="8-K")
    assert [row["document"] for row in selected] == ["issuer-8k.htm", "ex991.htm"]


def test_exact_trial_and_fda_identifiers_are_required() -> None:
    identifiers = extract_exact_identifiers(
        [
            {
                "headline": "Phase 3 NCT12345678 update",
                "summary": "The filing references NDA 215432 and vague clinical commentary.",
            }
        ]
    )
    assert identifiers == {
        "nct_ids": ["NCT12345678"],
        "fda_applications": ["NDA215432"],
    }


def _trial_payload(last_update: str) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"briefTitle": "Pivotal Example Study"},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "studyLastUpdatePostDateStruct": {"date": last_update},
                "primaryCompletionDateStruct": {"date": "2026-06-30"},
            },
            "designModule": {"phases": ["PHASE3"]},
            "outcomesModule": {"primaryOutcomes": [{"measure": "Visual acuity"}]},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Sponsor"}},
        },
        "resultsSection": {"outcomeMeasuresModule": {}},
    }


def test_date_only_trial_record_must_predate_cutoff_date() -> None:
    assert _trial_article_from_payload(
        symbol="BIO",
        nct_id="NCT12345678",
        payload=_trial_payload("2026-08-20"),
        cutoff=CUTOFF,
    ) is None
    article = _trial_article_from_payload(
        symbol="BIO",
        nct_id="NCT12345678",
        payload=_trial_payload("2026-08-19"),
        cutoff=CUTOFF,
    )
    assert article is not None
    assert article["is_primary_evidence"] is True
    assert article["primary_evidence"]["available_at"] == "2026-08-19T00:00:00+00:00"


def test_fda_record_filters_post_cutoff_submission_history() -> None:
    payload = {
        "results": [
            {
                "application_number": "NDA215432",
                "sponsor_name": "Example Sponsor",
                "products": [{"brand_name": "ExampleDrug"}],
                "submissions": [
                    {"submission_status_date": "2026-08-19", "submission_status": "AP", "submission_type": "ORIG"},
                    {"submission_status_date": "2026-08-21", "submission_status": "TA", "submission_type": "SUPPL"},
                ],
            }
        ]
    }
    article = _fda_article_from_payload(
        symbol="BIO",
        application="NDA215432",
        payload=payload,
        cutoff=CUTOFF,
    )
    assert article is not None
    retained = article["primary_evidence"]["metadata"]["eligible_submissions"]
    assert [row["submission_status_date"] for row in retained] == ["2026-08-19"]


def test_primary_articles_cannot_be_crowded_out_or_duplicated() -> None:
    primary = {
        "ABC": [
            {"id": "sec:1", "headline": "SEC filing", "is_primary_evidence": True},
        ]
    }
    news = {
        "ABC": [
            {"id": "sec:1", "headline": "duplicate"},
            {"id": "news:1", "headline": "Reuters context"},
        ]
    }
    merged = _merge_articles(news, primary)["ABC"]
    assert [row["id"] for row in merged] == ["sec:1", "news:1"]
    assert merged[0]["is_primary_evidence"] is True


def test_primary_evidence_improves_confidence_not_structural_attractiveness() -> None:
    legacy = SimpleNamespace()
    legacy._source_evidence_quality = lambda candidate, articles, cause_recognised, conflicting: (
        45.0,
        {"authoritative_source_present": False},
    )
    module = SimpleNamespace(
        _legacy=legacy,
        _clamp=lambda value: max(0.0, min(100.0, float(value))),
        source_quality_hierarchy=lambda candidate, articles: [
            {"id": article.get("id"), "source_type": "ambiguous", "source_quality_score": 10}
            for article in articles
        ],
        score_candidate=lambda candidate, articles, catalyst_class, risk_flags: {
            "verdict": "PASS",
            "hard_veto": True,
            "catalyst_analysis": {},
            "calculation_trace": {},
        },
    )
    patch_scoring(module)
    article = {
        "id": "sec:0001",
        "headline": "Issuer filed Chapter 11 disclosure",
        "source": "SEC filing",
        "is_primary_evidence": True,
        "source_kind": "sec_filing",
        "source_authority": "SEC EDGAR",
        "created_at": (CUTOFF - timedelta(hours=1)).isoformat(),
        "primary_evidence": {
            "source_kind": "sec_filing",
            "source_authority": "SEC EDGAR",
            "external_id": "0001",
            "available_at": (CUTOFF - timedelta(hours=1)).isoformat(),
            "source_url": "https://sec.example/0001",
            "content_hash": "abc",
            "metadata": {"point_in_time_rule": "accepted before cutoff"},
        },
    }
    confidence, trace = module._legacy._source_evidence_quality(
        {}, [article], cause_recognised=True, conflicting=False
    )
    result = module.score_candidate({}, [article], "E", ["solvency"])
    assert confidence >= 90
    assert trace["authoritative_source_present"] is True
    assert result["verdict"] == "PASS"
    assert result["hard_veto"] is True
    assert result["catalyst_analysis"]["primary_event_evidence_count"] == 1


def test_store_extracts_one_immutable_record_per_external_id() -> None:
    article = {
        "id": "sec:0001",
        "is_primary_evidence": True,
        "primary_evidence": {"source_kind": "sec_filing", "external_id": "0001"},
    }
    records = _records({"headlines": [article, dict(article)]})
    assert records == [{"source_kind": "sec_filing", "external_id": "0001"}]


def test_schema_has_database_cutoff_guard_and_rls() -> None:
    source = Path("sql/oversold_primary_event_evidence_v1.sql").read_text(encoding="utf-8")
    assert "check (available_at <= evidence_cutoff)" in source
    assert "alter table public.or_primary_evidence enable row level security" in source
    assert "unique (evidence_snapshot_id, source_kind, external_id)" in source


def test_primary_evidence_ui_is_idempotent_and_loaded_last() -> None:
    ui = Path("app/static/oversold_primary_evidence_ui.js").read_text(encoding="utf-8")
    loader = Path("app/static/oversold_tracking_v3.js").read_text(encoding="utf-8")
    assert "window.__orPrimaryEvidenceUiInstalled" in ui
    assert "new MutationObserver(schedule).observe(rows, {childList:true, subtree:true})" in ui
    assert "Primary event evidence" in ui
    assert "oversold_primary_evidence_ui.js" in loader
    assert loader.index("oversold_v33_explainability.js") < loader.index("oversold_primary_evidence_ui.js")
