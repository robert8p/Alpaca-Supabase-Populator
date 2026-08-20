from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from app.oversold_scoring import (
    SCORING_CONFIG_VERSION,
    SCORING_MODEL_VERSION,
    public_scoring_contract,
    score_candidate,
)

SIGNAL_TS = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)


def bars(base: float = 10.0, days: int = 70) -> list[dict]:
    return [
        {
            "t": (SIGNAL_TS - timedelta(days=days-index)).isoformat().replace("+00:00", "Z"),
            "o": base,
            "h": base * 1.01,
            "l": base * 0.99,
            "c": base,
            "v": 2_000_000,
            "vw": base,
        }
        for index in range(days)
    ]


def fundamentals(**overrides) -> dict:
    data = {
        "source": "sec_companyfacts_point_in_time_v1",
        "accession_number": "000-test",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 50,
        "metric_coverage_count": 14,
        "revenue_yoy": 0.08,
        "net_margin": 0.10,
        "net_margin_yoy_delta": 0.01,
        "operating_margin": 0.12,
        "gross_margin": 0.45,
        "eps_change_symmetric": 0.05,
        "net_income_change_symmetric": 0.05,
        "diluted_shares_yoy": 0.02,
        "cash_to_assets": 0.30,
        "liabilities_to_assets": 0.35,
        "equity_to_assets": 0.65,
        "debt_to_assets": 0.10,
        "current_ratio": 2.0,
        "cash_runway_months": 36.0,
        "market_cap": 1_000_000_000.0,
        "price_to_sales": 2.0,
        "source_definition_hash": "test",
        "point_in_time_rule": "filed_before_cutoff",
    }
    data.update(overrides)
    return data


def candidate(
    *,
    symbol: str = "TEST",
    prev: float = 10.0,
    last: float = 7.5,
    fundamental: dict | None = None,
    session: dict | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} Corporation",
        "drop_pct": ((last / prev) - 1.0) * 100.0,
        "last_price": last,
        "prev_close": prev,
        "prev_volume": 2_000_000,
        "prev_dollar_volume": prev * 2_000_000,
        "spread_pct": 0.40,
        "latest_trade_ts": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "evidence_cutoff": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "raw_snapshot": {
            "prevDailyBar": {"o": prev, "h": prev * 1.01, "l": prev * 0.99, "c": prev, "v": 2_000_000},
            "dailyBar": {"o": last * 0.95, "h": last * 1.03, "l": last * 0.93, "c": last, "v": 6_000_000, "vw": last * 0.98},
        },
        "history_bars": bars(prev),
        "benchmark_context": {},
        "fundamentals": fundamentals() if fundamental is None else fundamental,
        "price_session_context": session or {
            "price_session": "regular",
            "current_move_pct": ((last / prev) - 1.0) * 100.0,
            "regular_session_move_pct": ((last / prev) - 1.0) * 100.0,
            "extended_hours_only": False,
        },
        "_sec_prefetch_complete": True,
    }


def article(symbol: str, headline: str, summary: str, source: str = "Company IR") -> dict:
    return {
        "id": headline,
        "headline": headline,
        "summary": summary,
        "source": source,
        "symbols": [symbol],
        "created_at": (SIGNAL_TS - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        "url": "https://example.test/item",
    }


def test_v36_contract_is_purpose_aligned_and_versioned() -> None:
    assert SCORING_MODEL_VERSION == "oversold_reversion_score_v3_6"
    assert SCORING_CONFIG_VERSION == "or_score_config_2026_08_20_v8"
    contract = public_scoring_contract()
    assert "verified price damage" in contract["purpose"]
    assert contract["opportunity_architecture"]["aggregation"] == "weighted_geometric_mean"
    assert contract["score_semantics"]["name"] == "Robust Opportunity Score"
    assert contract["reliability_architecture"]["minimum_stability_score"] == 70.0
    assert contract["robustness_architecture"]["minimum_robust_score"] == 72.0
    assert contract["robustness_architecture"]["minimum_causal_clusters"] == 2
    assert contract["subject_attribution"]["version"] == "subject_attribution_v1"


def test_confidence_and_reliability_can_only_reduce_raw_opportunity() -> None:
    c = candidate()
    result = score_candidate(
        c,
        [article("TEST", "Test Corporation reports temporary production outage", "Operations are expected to resume tomorrow.")],
        "B",
        [],
    )
    assert result["confidence_adjusted_score"] <= result["core_score"]
    assert result["calculation_trace"]["v3_3"]["confidence_multiplier"] <= 1.0
    assert result["final_score"] <= result["calculation_trace"]["v3_4_reliability"]["base_v33_score"]
    assert result["final_score"] <= result["calculation_trace"]["v3_5_robustness"]["ensemble"]["ensemble_median"]


def test_catastrophic_capital_distress_cannot_rank_high() -> None:
    c = candidate(
        symbol="DIST",
        fundamental=fundamentals(
            cash_runway_months=2.0,
            cash_to_assets=0.01,
            liabilities_to_assets=1.10,
            equity_to_assets=-0.10,
            debt_to_assets=0.90,
            current_ratio=0.35,
            diluted_shares_yoy=0.80,
        ),
    )
    result = score_candidate(
        c,
        [article("DIST", "DIST files discounted offering amid going concern and Nasdaq deficiency", "The financing includes warrants and convertible securities after a debt default.")],
        "E",
        ["solvency", "dilution", "delisting"],
    )
    assert result["verdict"] == "PASS"
    assert result["final_score"] <= 20.0
    assert result["catalyst_analysis"]["tail_risk_score"] >= 90.0
    assert result["catalyst_analysis"]["eligibility_gates"]["no_capital_distress"] is False


def test_extreme_technical_oversold_does_not_override_bad_fundamentals() -> None:
    c = candidate(
        symbol="TRAP",
        prev=10.0,
        last=4.0,
        fundamental=fundamentals(
            cash_runway_months=4.0,
            current_ratio=0.50,
            debt_to_assets=0.85,
            liabilities_to_assets=0.98,
            cash_to_assets=0.01,
            net_margin=-0.80,
        ),
    )
    result = score_candidate(
        c,
        [article("TRAP", "TRAP reports temporary operational delay", "Management expects the site to reopen next week.")],
        "B",
        [],
    )
    assert result["setup_score"] >= 50.0
    assert result["catalyst_analysis"]["survivability_score"] < 55.0
    assert result["verdict"] != "INVESTIGATE"


def test_unknown_cause_is_uncertainty_not_bullishness() -> None:
    result = score_candidate(candidate(symbol="UNKN"), [], "U", [])
    assert result["catalyst_analysis"]["assessment_confidence_state"] == "UNKNOWN"
    assert result["final_score"] <= 45.0
    assert result["catalyst_analysis"]["eligibility_gates"]["cause_verified_or_strong_partial"] is False
    assert result["catalyst_analysis"]["eligibility_gates"]["causal_evidence_independence"] is False
    assert result["catalyst_analysis"]["eligibility_gates"]["causal_provenance_independence"] is False


def test_critical_event_without_fundamentals_fails_gate() -> None:
    c = candidate(symbol="MISS", fundamental={})
    result = score_candidate(
        c,
        [article("MISS", "MISS quarterly revenue misses estimates and lowers guidance", "Revenue and outlook fell below expectations.")],
        "C",
        ["earnings_guidance"],
    )
    assert result["catalyst_analysis"]["critical_fundamentals_required"] is True
    assert result["catalyst_analysis"]["eligibility_gates"]["critical_fundamentals_available"] is False
    assert result["catalyst_analysis"]["eligibility_gates"]["critical_fundamental_data_quality"] is False
    assert result["final_score"] <= 55.0


def test_extended_hours_only_shock_requires_regular_session_confirmation() -> None:
    c = candidate(
        symbol="AHRS",
        session={
            "price_session": "after_hours",
            "current_move_pct": -25.0,
            "regular_session_move_pct": -4.0,
            "extended_hours_only": True,
        },
    )
    result = score_candidate(
        c,
        [article("AHRS", "AHRS reports a temporary shipment delay", "Delayed orders are expected to ship next week.")],
        "B",
        [],
    )
    assert result["catalyst_analysis"]["eligibility_gates"]["regular_session_confirmation"] is False
    assert result["final_score"] <= 50.0
