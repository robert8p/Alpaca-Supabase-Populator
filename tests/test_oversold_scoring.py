from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.oversold_outcomes import calculate_outcome_metrics, refine_intraday_events
from app.oversold_scoring import evidence_snapshot_hash, final_score, score_candidate


SIGNAL = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)


def _history(base: float = 15.0) -> list[dict]:
    rows: list[dict] = []
    for index in range(60):
        ts = SIGNAL - timedelta(days=60 - index)
        close = base + ((index % 7) - 3) * 0.018
        rows.append(
            {
                "t": ts.isoformat().replace("+00:00", "Z"),
                "o": close - 0.03,
                "h": close + 0.12,
                "l": close - 0.12,
                "c": close,
                "v": 5_000_000 + (index % 5) * 60_000,
                "vw": close,
            }
        )
    rows[-1]["c"] = base
    return rows


def _healthy_fundamentals() -> dict:
    return {
        "source": "research_pid_fundamental.filing_events_v1",
        "accession_number": "000-test",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 49,
        "metric_coverage_count": 8,
        "revenue_yoy": 0.08,
        "net_margin": 0.08,
        "net_margin_yoy_delta": 0.01,
        "operating_margin": 0.10,
        "gross_margin": 0.48,
        "eps_change_symmetric": 0.12,
        "net_income_change_symmetric": 0.10,
        "diluted_shares_yoy": 0.02,
        "cash_to_assets": 0.24,
        "liabilities_to_assets": 0.52,
        "equity_to_assets": 0.48,
        "source_definition_hash": "test",
        "point_in_time_rule": "available_from_strictly_before_signal_date",
    }


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
        "evidence_cutoff": "2026-08-19T20:00:00Z",
        "raw_snapshot": {
            "prevDailyBar": {"o": 14.5, "h": 15.4, "l": 14.1, "c": prev, "v": 5_000_000},
            "dailyBar": {"o": 9.5, "h": 12.0, "l": 8.8, "c": last, "v": 12_000_000, "vw": 10.6},
        },
        "history_bars": _history(prev),
        "fundamentals": _healthy_fundamentals(),
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


def test_high_quality_temporary_rebound_candidate_retains_strong_economics_but_requires_source_independence():
    c = candidate()
    news = [article("Temporary production outage", "Operations resume tomorrow after a short-term technical issue.")]
    result = score_candidate(c, news, "B", [])
    reliability = result["catalyst_analysis"]["reliability_assessment"]
    assert result["setup_score"] >= 70
    assert result["catalyst_score"] >= 70
    assert result["damage_risk"] < 30
    assert result["confirmation_score"] >= 65
    assert reliability["base_v33_score"] >= result["final_score"]
    assert result["final_score"] >= 55
    assert result["catalyst_analysis"]["eligibility_gates"]["causal_evidence_independence"] is False
    assert result["verdict"] != "INVESTIGATE"
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


def test_secondary_biotech_miss_is_less_damaging_than_pivotal_failure():
    c = candidate(drop=-32.0, last=10.2)
    news = [article("Phase 2 study misses secondary endpoint", "Primary endpoint was achieved; one secondary endpoint was not met.")]
    result = score_candidate(c, news, "C", ["clinical_regulatory"])
    assert result["hard_veto"] is False
    assert 50 <= result["damage_risk"] < 90


def test_analyst_downgrade_without_operating_failure_can_be_reversible():
    c = candidate(drop=-22.0)
    news = [article("Broker downgrade cuts price target", "Analyst rating changed; no new company operating announcement cited.", "Broker note")]
    result = score_candidate(c, news, "A", ["analyst_only"])
    assert result["catalyst_score"] >= 65
    # A target cut is a small piece of negative valuation evidence even when no
    # new operating impairment is identified, so v3 does not force Damage near zero.
    assert result["damage_risk"] <= 30
    assert result["catalyst_analysis"]["analyst_reaction"]["coverage_available"] is True


def test_broad_sector_selloff_can_be_reversible_without_company_impairment():
    c = candidate(drop=-21.0)
    news = [article("Broad sector sell-off pressures shares", "Industry-wide risk-off move; no company-specific operating announcement.")]
    result = score_candidate(c, news, "B", [])
    assert result["catalyst_score"] >= 65
    assert result["hard_veto"] is False


def test_missing_news_never_gets_favourable_neutral_treatment():
    result = score_candidate(candidate(), [], "U", ["no_news"])
    assert result["catalyst_score"] <= 35
    assert result["evidence_confidence"] < 50
    assert result["final_score"] <= 60
    assert result["verdict"] != "INVESTIGATE"
    assert "company_specific_news" in result["missing_inputs"]


def test_conflicting_evidence_is_preserved():
    c = candidate(drop=-28.0)
    news = [article("Temporary outage but permanent closure under review", "Operations are temporarily halted while management considers permanent closure.")]
    result = score_candidate(c, news, "D", [])
    analysis = result["catalyst_analysis"]
    assert analysis["supporting_evidence"]
    assert analysis["contradictory_evidence"]
    assert result["damage_risk"] >= 70


def test_damage_gate_overrides_perfect_other_components():
    result = final_score(setup=100, catalyst=100, resilience=100, confirmation=100, confidence=100, damage_risk=90, cause_verified=True)
    assert result["final_score"] <= 20
    assert result["verdict"] == "PASS"


def test_low_confidence_shrinks_extreme_core_toward_neutral():
    result = final_score(setup=90, catalyst=90, resilience=90, confirmation=90, confidence=20, damage_risk=0, cause_verified=True)
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
        {"t": "2026-08-19T13:30:00Z", "o": 9, "h": 20, "l": 8, "c": 15},
        {"t": "2026-08-20T13:30:00Z", "o": 10, "h": 10.4, "l": 9.8, "c": 10.2},
        {"t": "2026-08-21T13:30:00Z", "o": 10.2, "h": 10.6, "l": 10.0, "c": 10.5},
        {"t": (deadline + timedelta(days=1)).isoformat(), "o": 10, "h": 30, "l": 9, "c": 25},
    ]
    metrics = calculate_outcome_metrics(row, bars, now=deadline + timedelta(days=1))
    assert metrics["return_1d"] == pytest.approx(2.0)
    assert metrics["hit_plus_5pct_within_6_weeks"] is True
    assert metrics["trading_days_to_plus_5"] == 2
    assert metrics["mfe_6w"] == pytest.approx(6.0)
    assert metrics["first_plus_5_ts"] is None
    assert metrics["intraday_refinement"] == "required"


def test_target_is_not_final_label_before_six_week_maturity():
    signal = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)
    row = {"signal_timestamp": signal, "horizon_deadline": signal + timedelta(weeks=6), "signal_price": 10.0}
    bars = [{"t": "2026-08-20T13:30:00Z", "o": 10, "h": 10.7, "l": 9.9, "c": 10.5}]
    metrics = calculate_outcome_metrics(row, bars, now=signal + timedelta(weeks=1))
    assert metrics["target_touch_day"] is not None
    assert metrics["hit_plus_5pct_within_6_weeks"] is None
    assert metrics["status"] == "pending"


def test_intraday_refinement_resolves_downside_before_target():
    signal = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)
    deadline = signal + timedelta(weeks=6)
    row = {"signal_timestamp": signal, "horizon_deadline": deadline, "signal_price": 10.0}
    daily = [{"t": "2026-08-20T04:00:00Z", "o": 10.0, "h": 10.7, "l": 9.4, "c": 10.5}]
    metrics = calculate_outcome_metrics(row, daily, now=deadline + timedelta(days=1))
    assert metrics["minus_5_before_plus_5"] is None
    minute = [
        {"t": "2026-08-20T13:31:00Z", "h": 10.1, "l": 9.4},
        {"t": "2026-08-20T13:32:00Z", "h": 10.6, "l": 9.8},
    ]
    refined = refine_intraday_events(row, metrics, minute)
    assert refined["first_plus_5_ts"] == datetime(2026, 8, 20, 13, 32, tzinfo=UTC)
    assert refined["minus_5_before_plus_5"] is True
    assert refined["intraday_refinement"] == "sip_1min"


def test_intraday_same_minute_order_remains_unknown():
    signal = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)
    deadline = signal + timedelta(weeks=6)
    row = {"signal_timestamp": signal, "horizon_deadline": deadline, "signal_price": 10.0}
    daily = [{"t": "2026-08-20T04:00:00Z", "o": 10.0, "h": 10.7, "l": 9.4, "c": 10.3}]
    metrics = calculate_outcome_metrics(row, daily, now=deadline + timedelta(days=1))
    minute = [{"t": "2026-08-20T13:31:00Z", "h": 10.6, "l": 9.4}]
    refined = refine_intraday_events(row, metrics, minute)
    assert refined["minus_5_before_plus_5"] is None
