from datetime import UTC, datetime, timedelta

import pytest

from app.oversold_calibration_runtime import calibration_sample_hash
from app.oversold_corporate_actions import classify_corporate_actions
from app.oversold_score_store import apply_active_calibration


def outcome_row(symbol="TEST", signal_price=10.0):
    signal = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)
    return {
        "symbol": symbol,
        "signal_timestamp": signal,
        "horizon_deadline": signal + timedelta(weeks=6),
        "signal_price": signal_price,
    }


def test_split_inside_horizon_excludes_outcome_from_calibration():
    result = classify_corporate_actions(
        outcome_row(),
        {
            "forward_splits": [
                {"symbol": "TEST", "process_date": "2026-01-10", "ex_date": "2026-01-20", "old_rate": "1", "new_rate": "4"}
            ]
        },
    )
    assert result["corporate_action_status"] == "affected"
    assert result["eligible_for_calibration"] is False
    assert result["material_events"][0]["type"] == "forward_splits"


def test_ordinary_cash_dividend_remains_eligible():
    result = classify_corporate_actions(
        outcome_row(signal_price=100.0),
        {
            "cash_dividends": [
                {"symbol": "TEST", "process_date": "2026-01-10", "ex_date": "2026-01-20", "rate": "0.25", "special": False}
            ]
        },
    )
    assert result["corporate_action_status"] == "clear"
    assert result["eligible_for_calibration"] is True
    assert len(result["benign_events"]) == 1


def test_special_or_large_cash_dividend_is_material():
    special = classify_corporate_actions(
        outcome_row(signal_price=100.0),
        {"cash_dividends": [{"symbol": "TEST", "ex_date": "2026-01-20", "rate": "1", "special": True}]},
    )
    large = classify_corporate_actions(
        outcome_row(signal_price=10.0),
        {"cash_dividends": [{"symbol": "TEST", "ex_date": "2026-01-20", "rate": "0.60", "special": False}]},
    )
    assert special["eligible_for_calibration"] is False
    assert large["eligible_for_calibration"] is False


def test_being_merger_acquirer_does_not_mechanically_contaminate_target():
    result = classify_corporate_actions(
        outcome_row(symbol="BUYER"),
        {
            "cash_mergers": [
                {
                    "acquirer_symbol": "BUYER",
                    "acquiree_symbol": "TARGET",
                    "effective_date": "2026-01-20",
                    "process_date": "2026-01-15",
                    "rate": "20",
                }
            ]
        },
    )
    assert result["corporate_action_status"] == "clear"
    assert result["eligible_for_calibration"] is True


def test_action_outside_six_week_target_window_is_ignored():
    result = classify_corporate_actions(
        outcome_row(),
        {"reverse_splits": [{"symbol": "TEST", "ex_date": "2026-03-15", "process_date": "2026-03-10"}]},
    )
    assert result["corporate_action_status"] == "clear"


def test_calibration_sample_hash_is_deterministic_and_changes_with_sample():
    rows = [
        {"score": 70.0, "target": True, "signal_timestamp": "2026-01-01T00:00:00+00:00", "sector": "software"},
        {"score": 40.0, "target": False, "signal_timestamp": "2026-01-02T00:00:00+00:00", "sector": "consumer"},
    ]
    assert calibration_sample_hash(rows) == calibration_sample_hash(rows)
    changed = [dict(row) for row in rows]
    changed[1]["target"] = True
    assert calibration_sample_hash(rows) != calibration_sample_hash(changed)


def test_passed_calibration_is_attached_without_changing_raw_score():
    score = {
        "final_score": 70.0,
        "model_status": "uncalibrated",
        "calibration_model_version": None,
        "calculation_trace": {},
    }
    calibration = {
        "passed": True,
        "calibration_model_version": "cal-v1",
        "metrics": {"coefficients": {"intercept": 0.0, "score_slope": 0.5}},
    }
    result = apply_active_calibration(score, calibration)
    assert result["final_score"] == 70.0
    assert result["model_status"] == "calibrated"
    assert result["calibration_model_version"] == "cal-v1"
    assert result["calibrated_probability"] == pytest.approx(0.7310585786)
    assert result["calculation_trace"]["calibration"]["raw_reversion_score"] == 70.0


def test_missing_calibration_leaves_score_uncalibrated():
    score = {"final_score": 70.0, "model_status": "uncalibrated", "calculation_trace": {}}
    result = apply_active_calibration(score, None)
    assert result["model_status"] == "uncalibrated"
    assert "calibrated_probability" not in result
