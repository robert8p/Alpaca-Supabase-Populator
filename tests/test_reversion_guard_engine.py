from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from app.reversion_guard_engine import (
    assess_candidate as _assess_candidate,
    break_even_recovery_pct,
    classify_event,
    infer_theme,
    portfolio_summary,
    review_position,
)

AS_OF = datetime(2026, 8, 19, 15, 30, tzinfo=UTC)


def assess_candidate(row, settings=None):
    return _assess_candidate(row, settings, as_of=AS_OF)


def candidate(**overrides):
    row = {
        "id": 1,
        "scan_id": "00000000-0000-0000-0000-000000000001",
        "rank": 1,
        "symbol": "TEST",
        "name": "Test Semiconductor Systems",
        "prev_close": 20.0,
        "last_price": 16.0,
        "drop_pct": -20.0,
        "prev_dollar_volume": 35_000_000,
        "spread_pct": 0.35,
        "evidence_cutoff": "2026-08-19T15:30:00Z",  # 11:30 ET in August
        "latest_trade_ts": "2026-08-19T15:30:00Z",
        "catalyst_summary": "A temporary shipment delay affected one quarter; demand and guidance remain intact.",
        "risk_flags": [],
        "headlines": [
            {
                "headline": "Test says temporary shipment delay will clear next month",
                "summary": "The company reaffirmed guidance.",
                "source": "Company IR",
                "symbols": ["TEST"],
                "url": "https://example.com/test-quarterly-results",
                "created_at": "2026-08-19T13:00:00Z",
            }
        ],
        "headline_count": 1,
        "reversion_score": 82.0,
        "model_verdict": "INVESTIGATE",
        "resilience_score": 82.0,
        "confirmation_score": 78.0,
        "damage_risk": 24.0,
        "evidence_confidence": 84.0,
        "hard_veto": False,
        "hard_veto_reason": None,
        "sector_hint": "technology",
        "catalyst_analysis": {"catalyst_type": "temporary_operational", "verification_status": "VERIFIED"},
        "technical_inputs": {
            "session_range_position": 82.0,
            "gap_reclaim_pct": 48.0,
            "low_reclaim_pct": 72.0,
            "vwap_distance_pct": 2.0,
            "return_from_open_pct": 5.0,
            "atr20": 0.9,
            "drawdown_from_60d_high_pct": -30.0,
            "current_return_pct": -20.0,
            "vwap": 15.7,
        },
        "raw_snapshot": {
            "dailyBar": {"o": 15.2, "h": 16.3, "l": 14.8, "c": 16.0, "vw": 15.7},
            "latestQuote": {"bp": 15.98, "ap": 16.02, "t": "2026-08-19T15:30:00Z"},
        },
        "intraday_bars": [
            {"t": f"2026-08-19T15:{minute}:00Z", "l": low, "h": 16.3}
            for minute, low in [(25, 15.5), (26, 14.8), (27, 15.5), (28, 15.2), (29, 15.8)]
        ],
    }
    row.update(overrides)
    if "catalyst_summary" in overrides and "headlines" not in overrides:
        row["headlines"][0]["headline"] = overrides["catalyst_summary"]
        row["headlines"][0]["summary"] = ""
    return row


def test_temporary_verified_regular_session_candidate_can_be_investigated():
    assessment = assess_candidate(candidate())
    assert assessment["event"]["bucket"] == "temporary_operational_issue"
    assert assessment["confirmation"]["status"] == "confirmed"
    assert assessment["gate_code"] == "INVESTIGATE_CONFIRMED"
    assert assessment["risk_plan"]["recommended_shares_now"] > 0


def test_after_hours_signal_is_forced_to_wait_even_when_other_inputs_are_strong():
    assessment = assess_candidate(candidate(evidence_cutoff="2026-08-19T22:15:00Z"))
    assert assessment["session"]["label"] == "after-hours"
    assert assessment["gate_code"] == "WAIT_FOR_REGULAR_SESSION"
    assert assessment["risk_plan"]["recommended_shares_now"] == 0
    assert assessment["risk_plan"]["preview_shares_after_confirmation"] > 0


@pytest.mark.parametrize(
    ("summary", "risk_flags", "expected"),
    [
        ("The company announced a $150m convertible senior notes offering and share issuance.", ["dilution"], "financing_or_dilution"),
        ("The pivotal Phase 3 study failed its primary endpoint.", ["clinical_regulatory"], "failed_clinical_or_regulatory_event"),
        ("The company warned it may be unable to continue as a going concern.", ["solvency"], "existential_or_structural_damage"),
        ("The move appears to be a post_spike_unwind after a parabolic rally.", [], "parabolic_momentum_unwind"),
    ],
)
def test_destructive_or_unanchored_events_are_hard_rejected(summary, risk_flags, expected):
    row = candidate(catalyst_summary=summary, risk_flags=risk_flags, catalyst_analysis={})
    event = classify_event(row)
    assessment = assess_candidate(row)
    assert event["bucket"] == expected
    assert event["hard_reject_new_entry"] is True
    assert assessment["gate_code"] == "REJECT_NEW_ENTRY"
    assert assessment["guard_score"] <= 20


def test_guidance_cut_requires_new_fair_value_not_an_automatic_bounce_trade():
    row = candidate(
        catalyst_summary="Management lowered full-year revenue guidance and reduced its outlook.",
        catalyst_analysis={"catalyst_type": "earnings"},
    )
    assessment = assess_candidate(row)
    assert assessment["event"]["bucket"] == "guidance_or_earnings_quality_reset"
    assert assessment["gate_code"] == "WAIT_FOR_NEW_FAIR_VALUE"
    assert assessment["guard_score"] <= 48


def test_break_even_recovery_exposes_asymmetric_loss_math():
    assert break_even_recovery_pct(100.0, 75.0) == pytest.approx(33.3333333)
    assert break_even_recovery_pct(100.0, 80.0) == pytest.approx(25.0)
    assert break_even_recovery_pct(100.0, 110.0) == 0.0


def test_position_review_exits_dilution_and_does_not_anchor_to_cost_basis():
    row = candidate(
        catalyst_summary="The company priced a dilutive registered direct offering with warrants.",
        risk_flags=["dilution"],
        catalyst_analysis={"catalyst_type": "financing"},
    )
    review = review_position(
        {"symbol": "TEST", "entry_price_usd": 100.0, "current_price_usd": 75.0, "quantity": 10},
        candidate=row,
    )
    assert review["action"] == "EXIT"
    assert review["recovery_to_break_even_pct"] == pytest.approx(33.33)
    assert "Do not average down" in review["sizing_guidance"]


def test_position_review_takes_profit_in_planned_zone():
    review = review_position(
        {"symbol": "TEST", "entry_price_usd": 100.0, "current_price_usd": 105.0, "quantity": 10},
        candidate=candidate(last_price=105.0),
    )
    assert review["action"] == "TRIM_WINNER"


def test_theme_inference_and_portfolio_concentration_limit():
    assessment = assess_candidate(candidate())
    assert infer_theme(candidate()) == "AI / semiconductors"
    positions = [
        {"theme": "AI / semiconductors", "planned_risk_gbp": 30},
        {"theme": "AI / semiconductors", "planned_risk_gbp": 30},
        {"theme": "AI / semiconductors", "planned_risk_gbp": 30},
        {"theme": "AI / semiconductors", "planned_risk_gbp": 30},
    ]
    summary = portfolio_summary([assessment], positions=positions, settings={"max_theme_positions": 3, "account_value_gbp": 10_000})
    assert summary["overexposed_themes"] == [{"theme": "AI / semiconductors", "count": 4, "limit": 3}]
    assert summary["planned_open_risk_gbp"] == 120


def test_risk_sizing_is_bound_by_both_risk_budget_and_maximum_position():
    assessment = assess_candidate(
        candidate(),
        settings={"risk_budget_gbp": 50, "max_position_gbp": 200, "usd_per_gbp": 1.25, "account_value_gbp": 10_000},
    )
    plan = assessment["risk_plan"]
    assert plan["preview_position_gbp"] <= 200.01
    assert plan["preview_risk_gbp"] <= 50.01
    assert math.isclose(plan["recommended_shares_now"], plan["preview_shares_after_confirmation"])


def test_missing_spread_and_quote_cannot_be_rescued_by_large_dollar_volume():
    row = candidate(prev_dollar_volume=1_000_000_000, spread_pct=None)
    row["raw_snapshot"].pop("latestQuote")
    assessment = assess_candidate(row)
    assert assessment["gate_code"] == "WAIT_FOR_CURRENT_MARKET_DATA"
    assert assessment["execution"]["ready"] is False
    assert assessment["execution"]["score"] < 55
    assert assessment["risk_plan"]["recommended_shares_now"] == 0
    assert assessment["research_action"] == "INVESTIGATE"


@pytest.mark.parametrize("quote", [
    {"bp": 16.1, "ap": 16.0, "t": "2026-08-19T15:30:00Z"},
    {"bp": 0, "ap": 16.0, "t": "2026-08-19T15:30:00Z"},
    {"bp": 15.98, "ap": 16.02},
    {"bp": 15.98, "ap": 16.02, "t": "2026-08-19T15:00:00Z"},
    {"bp": 15.98, "ap": 16.02, "t": "2026-08-19T15:31:00Z"},
])
def test_invalid_stale_or_future_quotes_never_open_an_entry_gate(quote):
    row = candidate()
    row["raw_snapshot"]["latestQuote"] = quote
    assessment = assess_candidate(row)
    assert assessment["gate_code"] == "WAIT_FOR_CURRENT_MARKET_DATA"
    assert assessment["risk_plan"]["recommended_shares_now"] == 0


@pytest.mark.parametrize("trade_ts", [None, "2026-08-19T15:00:00Z", "2026-08-19T15:31:00Z"])
def test_trade_timestamp_is_checked_even_when_quote_is_good(trade_ts):
    assessment = assess_candidate(candidate(latest_trade_ts=trade_ts))
    assert assessment["gate_code"] == "WAIT_FOR_CURRENT_MARKET_DATA"


def test_latest_view_does_not_recycle_an_old_regular_session_as_a_current_entry():
    assessment = _assess_candidate(candidate(), as_of=datetime(2026, 8, 20, 15, 30, tzinfo=UTC))
    assert assessment["gate_code"] == "WAIT_FOR_CURRENT_MARKET_DATA"
    assert assessment["risk_plan"]["recommended_shares_now"] == 0
    assert assessment["execution"]["evidence"]["quote_age_seconds"] == 86400


def test_historical_assessment_preserves_cutoff_evidence_but_never_recommends_shares_now():
    assessment = _assess_candidate(candidate(), historical=True)
    assert assessment["gate_code"] == "INVESTIGATE_CONFIRMED"
    assert assessment["assessment_context"] == "historical_at_cutoff"
    assert assessment["risk_plan"]["recommended_shares_now"] == 0
    assert assessment["risk_plan"]["historical_only"] is True


@pytest.mark.parametrize("source_change", [
    {"created_at": "2026-08-19T15:31:00Z"},
    {"created_at": None},
    {"url": "javascript:alert(1)"},
    {"symbols": ["OTHER"]},
    {"primary_evidence": {"metadata": {"context_only": True}}},
    {"updated_at": "2026-08-19T15:31:00Z"},
    {"primary_evidence": {"available_at": "2026-08-19T15:31:00Z"}},
    {"primary_evidence": {"available_at": "2026-08-19T12:00:00Z"}, "created_at": "2026-08-19T15:31:00Z"},
    {"created_at": "2026-08-19"},
    {"updated_at": "unknown"},
])
def test_ineligible_sources_cannot_be_promoted_by_upstream_verified_label(source_change):
    row = candidate(evidence_confidence=99, reversion_score=99)
    row["headlines"][0].update(source_change)
    assessment = assess_candidate(row)
    assert assessment["gate_code"] == "WAIT_FOR_EVIDENCE"
    assert assessment["evidence"]["cause_verified"] is False
    assert assessment["evidence"]["excluded_articles"]


def test_generic_form_8k_is_not_a_verified_analyst_downgrade_or_regulatory_event():
    row = candidate(
        catalyst_summary="TEST filed Form 8-K — Items 2.02,9.01",
        catalyst_analysis={"catalyst_type": "analyst_only", "cause_verified": True, "cause_verification_status": "VERIFIED"},
    )
    assessment = assess_candidate(row)
    assert assessment["event"]["bucket"] == "unknown_or_unverified"
    assert assessment["gate_code"] == "WAIT_FOR_EVIDENCE"


def test_high_confidence_cannot_override_explicitly_unverified_cause():
    row = candidate(catalyst_analysis={"catalyst_type": "temporary_operational", "cause_verified": False, "cause_verification_status": "VERIFIED"})
    assert assess_candidate(row)["gate_code"] == "WAIT_FOR_EVIDENCE"


def test_aggregate_recovery_measures_cannot_prove_a_higher_low():
    row = candidate(intraday_bars=[], confirmation_score=100)
    row["technical_inputs"]["higher_low_confirmed"] = True  # unsupported boolean is not evidence
    assessment = assess_candidate(row)
    assert assessment["confirmation"]["status"] == "pattern_evidence_missing"
    assert assessment["gate_code"] == "WAIT_FOR_CONFIRMATION"
    assert assessment["research_action"] == "INVESTIGATE"
    assert assessment["risk_plan"]["recommended_shares_now"] == 0


def test_future_intraday_bars_cannot_complete_a_higher_low():
    row = candidate()
    row["intraday_bars"][-1]["t"] = "2026-08-19T15:31:00Z"
    assert assess_candidate(row)["confirmation"]["status"] == "pattern_evidence_missing"


def test_partial_minute_and_gapped_minute_paths_do_not_confirm_a_higher_low():
    row = candidate()
    row["intraday_bars"][-1]["t"] = "2026-08-19T15:30:00Z"
    assert assess_candidate(row)["confirmation"]["status"] == "pattern_evidence_missing"
    row = candidate()
    row["intraday_bars"][0]["t"] = "2026-08-19T15:20:00Z"
    assert assess_candidate(row)["confirmation"]["higher_low_evidence"]["reason"] == "Intraday minute path is not contiguous"


def test_confirmed_pattern_also_requires_an_observed_reclaim():
    row = candidate()
    row["technical_inputs"].pop("vwap_distance_pct")
    assert assess_candidate(row)["confirmation"]["status"] == "waiting_for_reclaim"


def test_scores_and_planning_targets_do_not_claim_calibrated_profitability():
    assessment = assess_candidate(candidate())
    assert assessment["model_status"] == "UNCALIBRATED_HEURISTIC"
    assert assessment["profit_probability"] is None
    assert assessment["expected_net_return_pct"] is None
    assert assessment["risk_plan"]["profit_probability"] is None
    assert assessment["risk_plan"]["stop_loss_is_guaranteed"] is False
    assert assessment["risk_plan"]["target_basis"].startswith("Illustrative")


def test_explanation_cautions_are_not_misclassified_as_primary_economic_damage():
    row = candidate(explanation={"risk_reminder": "Check bankruptcy, dilution and lawsuits; no evidence supplied here."})
    assert assess_candidate(row)["event"]["bucket"] == "temporary_operational_issue"


def test_structural_damage_takes_precedence_over_a_winning_position():
    row = candidate(catalyst_summary="Dilutive registered direct offering", risk_flags=["dilution"])
    review = review_position({"symbol": "TEST", "entry_price_usd": 100, "current_price_usd": 105, "quantity": 10}, candidate=row)
    assert review["action"] == "EXIT"


@pytest.mark.parametrize("raw_flags", [[], ["solvency"]])
def test_vendor_bankruptcy_does_not_become_issuer_insolvency_after_v38_repair(raw_flags):
    row = candidate(
        name="Test Issuer", risk_flags=raw_flags, hard_veto=False,
        catalyst_summary="A vendor filed for Chapter 11 bankruptcy protection. Test Issuer recorded a receivable loss.",
        catalyst_analysis={
            "cause_verified": False,
            "evidence_integrity": {"version": "evidence_integrity_v1"},
            "event_signals": {"existential_or_solvency": False},
            "red_flags": [],
        },
    )
    assessment = assess_candidate(row)
    assert assessment["event"]["bucket"] != "existential_or_structural_damage"
    assert assessment["event"]["hard_reject_new_entry"] is False
    assert assessment["gate_code"] == "WAIT_FOR_EVIDENCE"


def test_legacy_vendor_bankruptcy_text_also_requires_a_local_issuer_assertion():
    row = candidate(
        risk_flags=["solvency"], catalyst_analysis={},
        catalyst_summary="A vendor filed for Chapter 11 bankruptcy protection. Test Semiconductor Systems recorded a receivable loss.",
    )
    assert assess_candidate(row)["event"]["hard_reject_new_entry"] is False


def test_v38_actual_issuer_bankruptcy_remains_rejected():
    row = candidate(
        risk_flags=["solvency"], hard_veto=True,
        catalyst_summary="The company filed for Chapter 11 bankruptcy protection today.",
        catalyst_analysis={
            "cause_verified": True,
            "evidence_integrity": {"version": "evidence_integrity_v1"},
            "event_signals": {"existential_or_solvency": True},
            "red_flags": ["solvency"],
        },
    )
    assert assess_candidate(row)["gate_code"] == "REJECT_NEW_ENTRY"
