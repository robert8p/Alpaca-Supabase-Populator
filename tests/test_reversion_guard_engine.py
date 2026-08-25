from __future__ import annotations

import math

import pytest

from app.reversion_guard_engine import (
    assess_candidate,
    break_even_recovery_pct,
    classify_event,
    infer_theme,
    portfolio_summary,
    review_position,
)


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
        "raw_snapshot": {"dailyBar": {"o": 15.2, "h": 16.3, "l": 14.8, "c": 16.0, "vw": 15.7}},
    }
    row.update(overrides)
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
