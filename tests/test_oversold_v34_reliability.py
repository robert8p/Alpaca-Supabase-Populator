from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from app.oversold_regulatory_evidence_v2 import (
    _enforcement_article,
    _normalise_name,
    _trial_sponsor_article,
)
from app.oversold_scoring import score_candidate
from app.oversold_scoring_v34 import (
    classify_evidence_relevance,
    detect_claim_contradictions,
    estimate_execution_friction,
)
from app.oversold_three_session_reliability import (
    TARGET_CONTRACT_VERSION,
    TARGET_DEFINITION,
    patch_score_store,
)

SIGNAL = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)


def article(
    headline: str,
    summary: str,
    *,
    source: str = "Reuters",
    hours_before: float = 2.0,
    primary: bool = False,
    context_only: bool = False,
) -> dict:
    row = {
        "id": f"{source}:{headline}",
        "headline": headline,
        "summary": summary,
        "source": source,
        "symbols": ["TEST"],
        "created_at": (SIGNAL - timedelta(hours=hours_before)).isoformat(),
        "url": "https://example.test/evidence",
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
                    "external_id": headline,
                    "available_at": row["created_at"],
                    "source_url": row["url"],
                    "summary": summary,
                    "content_excerpt": summary,
                    "content_hash": "a" * 64,
                    "metadata": {"context_only": context_only},
                },
            }
        )
    return row


def fundamentals(**overrides) -> dict:
    result = {
        "source": "sec_companyfacts_point_in_time_v1",
        "accession_number": "000-reliability",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 50,
        "metric_coverage_count": 16,
        "revenue_yoy": 0.10,
        "net_margin": 0.12,
        "net_margin_yoy_delta": 0.02,
        "operating_margin": 0.14,
        "gross_margin": 0.50,
        "eps_change_symmetric": 0.08,
        "net_income_change_symmetric": 0.08,
        "diluted_shares_yoy": 0.01,
        "cash_to_assets": 0.32,
        "liabilities_to_assets": 0.30,
        "equity_to_assets": 0.70,
        "debt_to_assets": 0.08,
        "current_ratio": 2.2,
        "cash_runway_months": 36.0,
        "market_cap": 900_000_000.0,
        "price_to_sales": 1.7,
        "source_definition_hash": "reliability-test",
        "point_in_time_rule": "filed_before_cutoff",
    }
    result.update(overrides)
    return result


def candidate(**overrides) -> dict:
    previous = float(overrides.pop("prev_close", 10.0))
    last = float(overrides.pop("last_price", 7.0))
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
    result = {
        "symbol": "TEST",
        "name": "Test Corporation",
        "drop_pct": ((last / previous) - 1.0) * 100.0,
        "last_price": last,
        "prev_close": previous,
        "prev_volume": 5_000_000,
        "prev_dollar_volume": 50_000_000,
        "spread_pct": 0.25,
        "latest_trade_ts": SIGNAL.isoformat(),
        "evidence_cutoff": SIGNAL.isoformat(),
        "raw_snapshot": {
            "prevDailyBar": {"o": previous, "h": 10.1, "l": 9.9, "c": previous, "v": 5_000_000},
            "dailyBar": {"o": 6.0, "h": 7.4, "l": 5.8, "c": last, "v": 15_000_000, "vw": 6.7},
        },
        "history_bars": history,
        "benchmark_context": {},
        "fundamentals": fundamentals(),
        "price_session_context": {
            "price_session": "regular",
            "current_move_pct": -30.0,
            "regular_session_move_pct": -30.0,
            "extended_hours_only": False,
        },
        "_sec_prefetch_complete": True,
    }
    result.update(overrides)
    return result


def test_primary_context_record_does_not_become_causal_evidence() -> None:
    analysis = {"event_taxonomy_primary": "temporary_operational_issue"}
    evidence = [
        article(
            "Routine Form 10-Q",
            "The filing contains general operations and revenue disclosure but does not describe the outage.",
            primary=True,
            context_only=True,
        )
    ]
    relevance = classify_evidence_relevance(evidence, analysis, SIGNAL)
    assert relevance["causal_primary_count"] == 0
    assert relevance["items"][0]["relevance"] in {"supporting", "context"}


def test_recent_primary_event_record_is_causal_and_independent() -> None:
    analysis = {"event_taxonomy_primary": "material_dilution"}
    evidence = [
        article(
            "Issuer files registered direct offering",
            "The SEC filing discloses common shares, warrants and offering proceeds.",
            primary=True,
        ),
        article(
            "Issuer prices share offering",
            "Reuters reports the same registered direct financing.",
            source="Reuters",
        ),
    ]
    relevance = classify_evidence_relevance(evidence, analysis, SIGNAL)
    assert relevance["causal_primary_count"] == 1
    assert relevance["causal_independent_sources"] == 2


def test_unresolved_high_quality_claim_conflict_is_penalised() -> None:
    evidence = [
        article("Company reaffirms guidance", "Management reaffirmed full-year guidance.", source="Company IR", hours_before=3),
        article("Company cuts outlook", "A later SEC filing says guidance was reduced.", source="SEC filing", hours_before=1, primary=True),
    ]
    contradiction = detect_claim_contradictions(evidence)
    assert contradiction["unresolved_count"] == 1
    assert contradiction["severity"] >= 50.0


def test_later_operational_resolution_is_not_treated_as_unresolved_conflict() -> None:
    evidence = [
        article("Plant shutdown", "Production was halted after an equipment fault.", source="Reuters", hours_before=5),
        article("Plant resumes", "The company said production resumed and operations were restored.", source="Company IR", hours_before=1),
    ]
    contradiction = detect_claim_contradictions(evidence)
    assert contradiction["unresolved_count"] == 0
    assert contradiction["resolved_sequence_count"] == 1


def test_execution_friction_penalises_illiquid_microcap() -> None:
    liquid = estimate_execution_friction(
        candidate(),
        {"fundamental_trace": {"raw_metrics": {"market_cap": 1_000_000_000}}},
    )
    illiquid = estimate_execution_friction(
        candidate(prev_dollar_volume=300_000, spread_pct=4.0),
        {"fundamental_trace": {"raw_metrics": {"market_cap": 15_000_000}}},
    )
    assert liquid["estimated_round_trip_friction_pct"] < 1.0
    assert illiquid["estimated_round_trip_friction_pct"] > 5.0


def test_contradictory_evidence_prevents_investigate_even_with_strong_finances() -> None:
    evidence = [
        article("Test reaffirms guidance", "Management reaffirmed its full-year guidance.", source="Company IR", hours_before=4),
        article("Test lowers outlook", "The SEC filing reduced full-year guidance after a revenue miss.", source="SEC filing", hours_before=1, primary=True),
        article("Test outlook cut", "Reuters confirms guidance was cut after results.", source="Reuters", hours_before=0.5),
    ]
    result = score_candidate(candidate(), evidence, "C", ["earnings_guidance"])
    reliability = result["catalyst_analysis"]["reliability_assessment"]
    assert reliability["contradictions"]["severity"] >= 50.0
    assert result["catalyst_analysis"]["eligibility_gates"]["no_material_evidence_contradiction"] is False
    assert result["verdict"] != "INVESTIGATE"
    assert result["final_score"] <= reliability["base_v33_score"]


def test_reliability_scenarios_are_deterministic() -> None:
    evidence = [
        article("Temporary outage", "Production was disrupted but operations are expected to resume tomorrow.", source="Company IR"),
        article("Operations resume", "Reuters says production resumed with guidance unchanged.", source="Reuters", hours_before=0.5),
    ]
    first = score_candidate(candidate(), evidence, "B", [])
    second = score_candidate(candidate(), evidence, "B", [])
    assert first["final_score"] == second["final_score"]
    assert first["catalyst_analysis"]["reliability_assessment"] == second["catalyst_analysis"]["reliability_assessment"]


def test_exact_regulator_matching_and_date_cutoff() -> None:
    module = SimpleNamespace(
        _parse_date=lambda value: date.fromisoformat(str(value)[:10]) if value else None,
        _sha256=lambda value: "b" * 64,
    )
    row = {
        "recalling_firm": "Example Therapeutics, Inc.",
        "report_date": "20260819",
        "recall_number": "D-100-2026",
        "classification": "Class II",
        "status": "Ongoing",
        "reason_for_recall": "Potential contamination",
        "product_description": "Example drug",
    }
    article_row = _enforcement_article(
        module,
        symbol="EXM",
        source_kind="fda_drug_enforcement",
        authority="U.S. FDA drug enforcement",
        row=row,
        cutoff=SIGNAL,
        aliases=["Example Therapeutics Inc"],
    )
    assert article_row is not None
    assert article_row["is_primary_evidence"] is True
    assert _normalise_name("Example Therapeutics, Inc.") == _normalise_name("Example Therapeutics Inc")
    row["report_date"] = "20260820"
    assert _enforcement_article(
        module,
        symbol="EXM",
        source_kind="fda_drug_enforcement",
        authority="U.S. FDA drug enforcement",
        row=row,
        cutoff=SIGNAL,
        aliases=["Example Therapeutics Inc"],
    ) is None


def test_trial_sponsor_match_requires_exact_issuer_and_pre_cutoff_posting() -> None:
    module = SimpleNamespace(
        _parse_date=lambda value: date.fromisoformat(str(value)[:10]) if value else None,
        _sha256=lambda value: "c" * 64,
    )
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT12345678", "briefTitle": "Example pivotal study"},
            "statusModule": {
                "studyFirstPostDateStruct": {"date": "2026-01-01"},
                "studyLastUpdatePostDateStruct": {"date": "2026-08-19"},
                "overallStatus": "RECRUITING",
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Therapeutics, Inc."}},
            "designModule": {"phases": ["PHASE3"]},
        }
    }
    matched = _trial_sponsor_article(
        module,
        symbol="EXM",
        aliases=["Example Therapeutics Inc"],
        study=study,
        cutoff=SIGNAL,
    )
    assert matched is not None
    assert matched["primary_evidence"]["metadata"]["context_only"] is True
    assert _trial_sponsor_article(
        module,
        symbol="OTHER",
        aliases=["Other Company"],
        study=study,
        cutoff=SIGNAL,
    ) is None


def test_new_source_kinds_and_target_contract_are_migrated() -> None:
    migration = Path("sql/oversold_reversion_v34_reliability.sql").read_text(encoding="utf-8")
    for source_kind in (
        "clinical_trial_sponsor_match",
        "fda_drug_enforcement",
        "fda_device_enforcement",
    ):
        assert source_kind in migration
    assert TARGET_DEFINITION == "hit_reversion_within_3_trading_sessions"
    assert TARGET_CONTRACT_VERSION == "three_session_target_v3"


def test_score_store_wrapper_writes_target_metadata() -> None:
    calls: list[tuple[str, tuple]] = []

    class Cursor:
        def execute(self, sql, params=None):
            calls.append((sql, params or ()))

    module = SimpleNamespace(
        persist_original_score=lambda cur, **kwargs: (11, 22),
    )
    patch_score_store(module)
    result = module.persist_original_score(
        Cursor(),
        candidate_id=7,
        scan_id="scan",
        item={},
        score={},
        evidence_cutoff=SIGNAL,
    )
    assert result == (11, 22)
    assert any("calibration_target_definition" in str(params) for _sql, params in calls)
