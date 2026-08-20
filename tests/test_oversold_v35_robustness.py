from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from app.oversold_scoring import (
    SCORING_CONFIG_VERSION,
    SCORING_MODEL_VERSION,
    score_candidate,
)
from app.oversold_scoring_v35 import (
    ROBUSTNESS_VERSION,
    event_alignment_quality,
    evidence_provenance_clusters,
    fundamental_data_quality,
)

SIGNAL = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)


def article(
    identifier: str,
    headline: str,
    summary: str,
    *,
    source: str,
    hours_before: float,
    primary: bool = False,
    external_id: str | None = None,
) -> dict:
    created = (SIGNAL - timedelta(hours=hours_before)).isoformat()
    row = {
        "id": identifier,
        "headline": headline,
        "summary": summary,
        "source": source,
        "symbols": ["TEMP"],
        "created_at": created,
        "url": f"https://{source.lower().replace(' ','')}.example/{identifier}",
    }
    if primary:
        row.update(
            {
                "is_primary_evidence": True,
                "source_kind": "sec_filing",
                "source_authority": "SEC EDGAR",
                "primary_evidence": {
                    "source_kind": "sec_filing",
                    "source_authority": "SEC EDGAR",
                    "external_id": external_id or identifier,
                    "accession_number": external_id or identifier,
                    "available_at": created,
                    "source_url": row["url"],
                    "summary": summary,
                    "content_excerpt": summary,
                    "content_hash": (identifier.replace("-", "a") + "a" * 64)[:64],
                    "metadata": {"context_only": False},
                },
            }
        )
    return row


def relevance_for(rows: list[dict]) -> dict:
    return {
        "event_family": "operations",
        "items": [
            {
                "id": row["id"],
                "relevance": "causal",
                "age_hours": (SIGNAL - datetime.fromisoformat(row["created_at"])).total_seconds() / 3600,
            }
            for row in rows
        ],
    }


def fundamentals() -> dict:
    return {
        "source": "sec_companyfacts_point_in_time_v1",
        "accession_number": "000-v35-positive",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 50,
        "metric_coverage_count": 19,
        "revenue_yoy": 0.12,
        "net_margin": 0.14,
        "net_margin_yoy_delta": 0.02,
        "operating_margin": 0.16,
        "gross_margin": 0.48,
        "eps_change_symmetric": 0.10,
        "net_income_change_symmetric": 0.10,
        "diluted_shares_yoy": 0.01,
        "cash_to_assets": 0.34,
        "liabilities_to_assets": 0.30,
        "equity_to_assets": 0.70,
        "debt_to_assets": 0.08,
        "current_ratio": 2.4,
        "cash_runway_months": 42.0,
        "operating_cash_flow": 120_000_000,
        "assets": 1_000_000_000,
        "liabilities": 300_000_000,
        "equity": 700_000_000,
        "market_cap": 1_200_000_000,
        "price_to_sales": 1.8,
        "source_definition_hash": "v35-positive",
        "point_in_time_rule": "filed_before_cutoff",
    }


def candidate() -> dict:
    previous = 10.0
    last = 7.2
    history = [
        {
            "t": (SIGNAL - timedelta(days=80-index)).isoformat(),
            "o": previous,
            "h": previous * 1.01,
            "l": previous * 0.99,
            "c": previous,
            "v": 5_000_000,
            "vw": previous,
        }
        for index in range(70)
    ]
    return {
        "symbol": "TEMP",
        "name": "Temporary Event Corporation",
        "drop_pct": -28.0,
        "last_price": last,
        "prev_close": previous,
        "prev_volume": 5_000_000,
        "prev_dollar_volume": 50_000_000,
        "spread_pct": 0.20,
        "latest_trade_ts": SIGNAL.isoformat(),
        "evidence_cutoff": SIGNAL.isoformat(),
        "raw_snapshot": {
            "prevDailyBar": {"o": previous, "h": 10.1, "l": 9.9, "c": previous, "v": 5_000_000},
            "dailyBar": {"o": 6.1, "h": 7.45, "l": 5.9, "c": last, "v": 15_000_000, "vw": 6.75},
        },
        "history_bars": history,
        "benchmark_context": {},
        "fundamentals": fundamentals(),
        "price_session_context": {
            "price_session": "regular",
            "current_move_pct": -28.0,
            "regular_session_move_pct": -28.0,
            "extended_hours_only": False,
        },
        "_sec_prefetch_complete": True,
    }


def strong_evidence() -> list[dict]:
    return [
        article(
            "ir-outage",
            "Temporary Event reports short production outage",
            "A localized equipment fault interrupted production. Guidance remains unchanged and delayed units will ship this week.",
            source="Company IR",
            hours_before=3.0,
        ),
        article(
            "sec-outage",
            "Temporary Event files Form 8-K on temporary outage",
            "The filing confirms no material financial impact, no customer loss, no financing need and insured equipment.",
            source="SEC filing",
            hours_before=2.5,
            primary=True,
            external_id="000-v35-8k",
        ),
        article(
            "reuters-resumed",
            "Temporary Event says production resumed",
            "Reuters reports operations resumed, guidance stayed unchanged and customer contracts remain in force.",
            source="Reuters",
            hours_before=1.0,
        ),
    ]


def test_provenance_clusters_collapse_syndicated_copies() -> None:
    rows = [
        article(
            "wire-1",
            "Issuer announces temporary production outage",
            "Issuer announces a temporary production outage caused by an equipment fault and expects operations to resume tomorrow.",
            source="Business Wire",
            hours_before=3,
        ),
        article(
            "ir-1",
            "Issuer announces temporary production outage",
            "Issuer announces a temporary production outage caused by an equipment fault and expects operations to resume tomorrow.",
            source="Company IR",
            hours_before=3,
        ),
        article(
            "reuters-1",
            "Factory fault briefly interrupts issuer output",
            "Reuters independently reports a localized equipment fault and management's next-day restart timetable.",
            source="Reuters",
            hours_before=2,
        ),
    ]
    clusters = evidence_provenance_clusters(rows, relevance_for(rows))
    assert clusters["causal_cluster_count"] == 2
    assert sorted(cluster["article_count"] for cluster in clusters["clusters"]) == [1, 2]
    assert clusters["leave_one_cluster_out_minimum"] == 1


def test_common_sec_accession_is_one_provenance_root() -> None:
    rows = [
        article(
            "sec-main",
            "Issuer files Form 8-K",
            "Form 8-K describes the temporary production interruption and expected restart.",
            source="SEC filing",
            hours_before=2,
            primary=True,
            external_id="000-shared-accession",
        ),
        article(
            "sec-exhibit",
            "Issuer press release exhibit",
            "The press release exhibit describes the temporary production interruption and expected restart.",
            source="Company IR",
            hours_before=2,
            primary=True,
            external_id="000-shared-accession",
        ),
    ]
    clusters = evidence_provenance_clusters(rows, relevance_for(rows))
    assert clusters["causal_cluster_count"] == 1
    assert clusters["primary_causal_cluster_count"] == 1
    assert clusters["single_cluster_dependency_risk"] >= 80


def test_event_alignment_penalises_stale_context() -> None:
    recent = event_alignment_quality(
        {
            "clusters": [
                {"minimum_age_hours": 3.0, "is_primary": True},
                {"minimum_age_hours": 6.0, "is_primary": False},
            ]
        }
    )
    stale = event_alignment_quality(
        {"clusters": [{"minimum_age_hours": 90.0, "is_primary": True}]}
    )
    assert recent["score"] >= 90
    assert stale["score"] < 60


def test_fundamental_quality_is_event_specific_and_checks_consistency() -> None:
    analysis = {
        "fundamental_trace": {
            "available": True,
            "source": "sec_companyfacts_point_in_time_v1",
            "age_calendar_days": 60,
            "metric_coverage_count": 18,
            "raw_metrics": fundamentals(),
        }
    }
    strong = fundamental_data_quality(analysis, "financing")
    missing = fundamental_data_quality(
        {"fundamental_trace": {"available": False, "raw_metrics": {}}},
        "financing",
    )
    assert strong["score"] >= 80
    assert strong["required_coverage_ratio"] >= 0.85
    assert strong["accounting_consistency"] == 0.0
    assert missing["score"] == 0


def test_v35_positive_control_survives_robust_ensemble() -> None:
    result = score_candidate(candidate(), strong_evidence(), "B", [])
    analysis = result["catalyst_analysis"]
    robustness = analysis["robustness_assessment"]
    assert SCORING_MODEL_VERSION == "oversold_reversion_score_v3_5"
    assert SCORING_CONFIG_VERSION == "or_score_config_2026_08_20_v7"
    assert analysis["causal_provenance_cluster_count"] >= 2
    assert analysis["event_alignment_score"] >= 60
    assert analysis["fundamental_data_quality_score"] >= 60
    assert analysis["weight_stability_score"] >= 70
    assert robustness["ensemble"]["ensemble_member_count"] >= 30
    assert result["final_score"] >= 72
    assert result["verdict"] == "INVESTIGATE"
    assert all(analysis["eligibility_gates"].values())


def test_single_source_dependency_cannot_reach_investigate() -> None:
    evidence = [strong_evidence()[1]]
    result = score_candidate(candidate(), evidence, "B", [])
    analysis = result["catalyst_analysis"]
    assert analysis["causal_provenance_cluster_count"] <= 1
    assert analysis["eligibility_gates"]["causal_provenance_independence"] is False
    assert result["verdict"] != "INVESTIGATE"
    assert result["final_score"] <= 60


def test_robust_ensemble_is_deterministic() -> None:
    first = score_candidate(candidate(), strong_evidence(), "B", [])
    second = score_candidate(candidate(), strong_evidence(), "B", [])
    assert first["final_score"] == second["final_score"]
    assert first["catalyst_analysis"]["robustness_assessment"] == second["catalyst_analysis"]["robustness_assessment"]
    assert first["catalyst_analysis"]["robustness_version"] == ROBUSTNESS_VERSION
