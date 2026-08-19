from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.oversold_outcomes import calculate_outcome_metrics
from app.oversold_scoring import evidence_snapshot_hash, final_score, score_candidate


def candidate(*, drop=-25.0, last=11.5, prev=15.0, spread=0.35, dollar_volume=80_000_000):
    return {
        "symbol": "TEST",
        "name": "Test Company",
        "drop_pct": drop,
        "last_price": last,
        "prev_close": prev,
        "prev_volume": 5_000_000,
        "prev_dollar_volume": dollar_volume,
        "spread_pct": spread,
        "latest_trade_ts": "2026-08-19T20:00:00Z",
        "raw_snapshot": {
            "prevDailyBar": {"o": 14.5, "h": 15.4, "l": 14.1, "c": prev, "v": 5_000_000},
            "dailyBar": {"o": 9.5, "h": 12.0, "l": 8.8, "c": last, "v": 12_000_000},
        },
    }


def article(headline, summary="", source="Company IR"):
    return {
        "id": headline,
        "headline": headline,
        "summary": summary,
        "source": source,
        "created_at": "2026-08-19T18:00:00Z",
        "url": "https://example.test/item",
    }


def test_high_quality_temporary_rebound_candidate_scores_high():
    c = candidate()
    news = [article("Temporary production outage", "Operations resume tomorrow after a short-term technical issue.")]
    result = score_candidate(c, news, "B", [])
    assert result["setup_score"] >= 70
    assert result["catalyst_score"] >= 70
    assert result["damage_risk"] < 30
    assert result["confirmation_score"] >= 65
    assert result["final_score"] >= 70
    assert result["hard_veto"] is False


def test_value_trap_damage_caps_extreme_setup():
    c = candidate(drop=-45.0, last=8.25)
    news = [article("Company permanently closes core business", "Permanent closure follows collapse in core demand.")]
    result = score_candidate(c, news, "D", ["earnings_guidance"])
    assert result["setup_score"] >= 70
    assert result["damage_risk"] >= 70
    assert result["final_score"] <= 40
    assert result["verdict"] == "PASS"


def test_biotech_pivotal_failure_hard_vetoes():
    c = candidate(drop=-60.0, last=6.0)
    news = [article("Phase 3 study failed primary endpoint", "The pivotal clinical trial did not meet the primary endpoint.")]
    result = score_candidate(c, news, "C", ["clinical_regulatory"])
    assert result["damage_risk"] >= 90
    assert result["hard_veto"] is True
    assert result["final_score"] <= 20
    assert result["verdict"] == "PASS"


def test_analyst_downgrade_without_operating_failure_can_be_reversible():
    c = candidate(drop=-22.0)
    news = [article("Broker downgrade cuts price target", "Analyst rating changed; no new company operating announcement cited.", "Broker note")]
    result = score_candidate(c, news, "A", ["analyst_only"])
    assert result["catalyst_score"] >= 65
    assert result["damage_risk"] <= 25
    assert result["catalyst_analysis"]["analyst_reaction"]["coverage_available"] is True


def test_missing_news_never_gets_favourable_neutral_treatment():
    result = score_candidate(candidate(), [], "U", ["no_news"])
    assert result["catalyst_score"] <= 35
    assert result["evidence_confidence"] < 50
    assert result["final_score"] <= 60
    assert result["verdict"] != "INVESTIGATE"
    assert "company_specific_news" in result["missing_inputs"]


def test_damage_gate_overrides_perfect_other_components():
    result = final_score(
        setup=100, catalyst=100, resilience=100, confirmation=100,
        confidence=100, damage_risk=90, cause_verified=True,
    )
    assert result["final_score"] <= 20
    assert result["verdict"] == "PASS"


def test_low_confidence_shrinks_extreme_core_toward_neutral():
    result = final_score(
        setup=90, catalyst=90, resilience=90, confirmation=90,
        confidence=20, damage_risk=0, cause_verified=True,
    )
    assert result["core_score"] == pytest.approx(90.0)
    assert result["confidence_adjusted_score"] == pytest.approx(58.0)
    assert result["final_score"] == pytest.approx(58.0)


def test_score_is_reproducible_for_identical_snapshot():
    c = candidate()
    news = [article("Temporary production outage", "Operations resume tomorrow.")]
    first = score_candidate(c, news, "B", [])
    second = score_candidate(c, news, "B", [])
    assert first["final_score"] == second["final_score"]
    assert first["calculation_trace"] == second["calculation_trace"]
    payload = {"candidate": c, "news": news}
    assert evidence_snapshot_hash(payload) == evidence_snapshot_hash(payload)


def test_outcome_tracker_excludes_signal_day_bar_and_future_beyond_cutoff():
    signal = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)
    deadline = signal + timedelta(weeks=6)
    row = {"signal_timestamp": signal, "horizon_deadline": deadline, "signal_price": 10.0}
    bars = [
        {"t": "2026-08-19T13:30:00Z", "o": 9, "h": 20, "l": 8, "c": 15},  # before signal: must not count
        {"t": "2026-08-20T13:30:00Z", "o": 10, "h": 10.4, "l": 9.8, "c": 10.2},
        {"t": "2026-08-21T13:30:00Z", "o": 10.2, "h": 10.6, "l": 10.0, "c": 10.5},
        {"t": (deadline + timedelta(days=1)).isoformat(), "o": 10, "h": 30, "l": 9, "c": 25},  # after horizon
    ]
    metrics = calculate_outcome_metrics(row, bars, now=deadline + timedelta(days=1))
    assert metrics["return_1d"] == pytest.approx(2.0)
    assert metrics["hit_plus_5pct_within_6_weeks"] is True
    assert metrics["trading_days_to_plus_5"] == 2
    assert metrics["mfe_6w"] == pytest.approx(6.0)


def test_outcome_target_not_labelled_before_six_week_maturity():
    signal = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)
    row = {"signal_timestamp": signal, "horizon_deadline": signal + timedelta(weeks=6), "signal_price": 10.0}
    bars = [{"t": "2026-08-20T13:30:00Z", "o": 10, "h": 10.7, "l": 9.9, "c": 10.5}]
    metrics = calculate_outcome_metrics(row, bars, now=signal + timedelta(weeks=1))
    assert metrics["first_plus_5_ts"] is not None
    assert metrics["hit_plus_5pct_within_6_weeks"] is None
    assert metrics["status"] == "pending"
