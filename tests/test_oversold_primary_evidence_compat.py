from __future__ import annotations

from datetime import UTC, datetime

from app import oversold_primary_evidence as evidence


def test_legacy_sec_acceptance_timestamp_is_eastern_not_utc() -> None:
    parsed = evidence._parse_ts("20260820160000")
    assert parsed == datetime(2026, 8, 20, 20, 0, tzinfo=UTC)


def test_main_filing_document_is_preferred_before_exhibits() -> None:
    rows = [
        {
            "sequence": "2",
            "description": "Material agreement",
            "document": "ex10-1.htm",
            "href": "ex10-1.htm",
            "type": "EX-10.1",
        },
        {
            "sequence": "1",
            "description": "Quarterly report",
            "document": "issuer-10q.xhtml",
            "href": "issuer-10q.xhtml",
            "type": "10-Q",
        },
        {
            "sequence": "3",
            "description": "Certification",
            "document": "ex31-1.htm",
            "href": "ex31-1.htm",
            "type": "EX-31.1",
        },
    ]
    selected = evidence._select_documents(
        rows,
        primary_document="different-filename.htm",
        form="10-Q",
    )
    assert [row["document"] for row in selected] == ["issuer-10q.xhtml", "ex10-1.htm"]


def test_fda_summary_uses_only_cutoff_dated_submission_history() -> None:
    payload = {
        "results": [
            {
                "application_number": "NDA215432",
                "sponsor_name": "Current Sponsor That May Have Changed",
                "products": [{"brand_name": "Current Product Metadata"}],
                "submissions": [
                    {
                        "submission_status_date": "2026-08-19",
                        "submission_status": "AP",
                        "submission_type": "ORIG",
                        "submission_public_notes": "Approved before cutoff",
                    }
                ],
            }
        ]
    }
    article = evidence._fda_article_from_payload(
        symbol="BIO",
        application="NDA215432",
        payload=payload,
        cutoff=datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
    )
    assert article is not None
    summary = article["summary"]
    metadata = article["primary_evidence"]["metadata"]
    assert "2026-08-19" in summary
    assert "Current Sponsor" not in summary
    assert "Current Product" not in summary
    assert metadata["current_application_metadata_excluded"] is True
    assert metadata["point_in_time_scope"] == "dated submission history only"
    assert "sponsor_name" not in metadata
    assert "products" not in metadata
