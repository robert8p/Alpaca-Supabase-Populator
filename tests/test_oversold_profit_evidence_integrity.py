from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app import oversold_calibration as calibration
from app.oversold_calibration_runtime import calibration_sample_hash
from app.oversold_calibration_v35 import calibration_robustness_checks, patch_module
from app.oversold_evaluation_v34 import profit_proxy_metrics
from app.oversold_outcomes import _parse_ts, calculate_outcome_metrics, refine_intraday_events
from app.oversold_outcomes_v33 import calculate_three_session_path

SIGNAL = datetime(2026, 8, 17, 20, tzinfo=UTC)
ROW = {"signal_timestamp": SIGNAL, "signal_price": 10.0, "horizon_deadline": SIGNAL + timedelta(weeks=6)}
CALENDAR = [{"date": f"2026-08-{day}", "open": "09:30", "close": "16:00"} for day in (18, 19, 20, 21)]
BARS = [{"t": f"2026-08-{day}T04:00:00Z", "o": 11.0, "h": 11.5, "l": 9.5, "c": 10.0} for day in (18, 19, 20, 21)]


def path(bars=BARS, now=datetime(2026, 8, 22, tzinfo=UTC), calendar=CALENDAR):
    return calculate_three_session_path(ROW, bars, parse_ts=_parse_ts, now=now, calendar=calendar)


def test_partial_third_session_cannot_mature_target():
    result = path(now=datetime(2026, 8, 20, 19, tzinfo=UTC))
    assert result["bar_count"] == 2
    assert result["matured"] is False
    assert result["profit_proxy"]["status"] == "unavailable"


def test_missing_middle_session_cannot_be_replaced_with_fourth():
    result = path([BARS[0], BARS[2], BARS[3]])
    assert result["bar_count"] == 2
    assert result["matured"] is False


def test_duplicate_bars_do_not_count_as_three_sessions():
    result = path([BARS[0]] * 3)
    assert result["bar_count"] == 1
    assert result["matured"] is False


def test_conflicting_duplicate_invalidates_session():
    result = path(BARS[:3] + [{**BARS[1], "h": 12.0}])
    assert result["matured"] is False


def test_target_touch_can_coexist_with_negative_entry_to_exit_return():
    result = path()
    assert result["mfe_3d"] > 5  # +15% from the old signal reference price.
    proxy = result["profit_proxy"]
    assert proxy["net_return_pct"] == pytest.approx((10 / 11 - 1) * 100 - 0.3)
    assert proxy["stress_net_return_pct"] == pytest.approx(proxy["net_return_pct"] - 0.3)
    assert proxy["actual_fills_verified"] is False
    report = profit_proxy_metrics([{"target": True, "profit_proxy": proxy}])
    assert report["positive_net_exit_rate"] == 0.0
    assert report["profitable_strategy_validated"] is False


def test_missing_open_does_not_invent_executable_entry():
    bars = [{key: val for key, val in bar.items() if key != "o"} for bar in BARS]
    assert path(bars)["profit_proxy"]["status"] == "unavailable"


def test_early_close_uses_real_exchange_calendar():
    calendar = [*CALENDAR[:2], {**CALENDAR[2], "close": "13:00"}]
    result = path(now=datetime(2026, 8, 20, 17, 2, tzinfo=UTC), calendar=calendar)
    assert result["matured"] is True
    assert result["window_end_ts"] == datetime(2026, 8, 20, 17, tzinfo=UTC)


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf")])
def test_invalid_signal_price_rejected(price):
    with pytest.raises(ValueError):
        calculate_three_session_path({**ROW, "signal_price": price}, BARS, parse_ts=_parse_ts)


def test_no_daily_evidence_never_becomes_a_failed_target():
    result = calculate_outcome_metrics(ROW, [], now=ROW["horizon_deadline"] + timedelta(days=1))
    assert result["hit_plus_5pct_within_6_weeks"] is None
    assert result["status"] != "matured"


def test_daily_outcomes_reject_future_and_unfinished_bars():
    result = calculate_outcome_metrics(ROW, BARS, now=datetime(2026, 8, 18, 15, tzinfo=UTC))
    assert result["bar_count"] == 0
    assert result["target_touch_day"] is None


def test_missing_minute_downside_evidence_preserves_unknown_order():
    daily = [{**BARS[0], "l": 9.0}]
    metrics = calculate_outcome_metrics(ROW, daily, now=ROW["horizon_deadline"])
    minute = [{"t": "2026-08-18T13:31:00Z", "h": 11.0, "l": 10.0}]
    refined = refine_intraday_events(ROW, metrics, minute)
    assert refined["minus_5_before_plus_5"] is None
    assert refined["minus_10_before_plus_5"] is None


def sample(index, *, symbol=None, duration=3):
    ts = SIGNAL + timedelta(days=index)
    return {"score": 80 if index % 2 else 20, "target": bool(index % 2),
            "signal_timestamp": ts, "outcome_end": ts + timedelta(days=duration),
            "sector": "test", "symbol": symbol or f"S{index}", "run_kind": "original"}


def test_training_labels_finish_before_whole_day_holdout():
    rows = [sample(index) for index in range(20)]
    rows.extend([{**sample(16), "symbol": "OTHER", "signal_timestamp": sample(16)["signal_timestamp"] + timedelta(hours=1)}])
    training, holdout = calibration.purged_temporal_split(list(reversed(rows)), 5)
    assert all(row["outcome_end"] < holdout[0]["signal_timestamp"] for row in training)
    assert {row["signal_timestamp"].date() for row in training}.isdisjoint({row["signal_timestamp"].date() for row in holdout})
    assert len(training) < len(rows) - len(holdout)


def test_rescores_and_overlapping_same_stock_are_not_independent_samples():
    rows = [sample(0, symbol="ABC"), sample(1, symbol="ABC"), sample(5, symbol="ABC"), {**sample(9), "run_kind": "rescore"}]
    selected = calibration.prepare_calibration_samples(rows)
    assert [row["signal_timestamp"] for row in selected] == [rows[0]["signal_timestamp"], rows[2]["signal_timestamp"]]


def test_calibration_hash_is_order_invariant_and_includes_outcome_embargo():
    rows = [sample(0), sample(1)]
    assert calibration_sample_hash(rows) == calibration_sample_hash(list(reversed(rows)))
    changed = [{**rows[0], "outcome_end": rows[0]["outcome_end"] + timedelta(days=1)}, rows[1]]
    assert calibration_sample_hash(rows) != calibration_sample_hash(changed)


def test_cross_validation_reports_purged_outcome_boundaries():
    result = calibration_robustness_checks(calibration, [sample(index) for index in range(180)])
    assert len(result["temporal_folds"]) >= 3
    assert result["bootstrap"]["resampling_unit"] == "signal_day"
    for fold in result["temporal_folds"]:
        assert _parse_ts(fold["training_latest_outcome_end"]) < _parse_ts(fold["holdout_start"])


def test_robustness_failure_reaches_insert_before_any_passed_mapping_is_published():
    calls = []
    def insert(**kwargs):
        calls.append(kwargs)
        return {"passed": bool(kwargs["robustness"]["passed"])}
    module = SimpleNamespace(run_calibration=insert, prepare_calibration_samples=calibration.prepare_calibration_samples)
    patch_module(module)
    result = module.run_calibration(samples=[sample(0)])
    assert len(calls) == 1
    assert calls[0]["robustness"]["passed"] is False
    assert result["passed"] is False


def test_nonfinite_probability_coefficients_do_not_emit_probability():
    fitted = {"passed": True, "metrics": {"coefficients": {"intercept": 0, "score_slope": float("nan")}}}
    assert calibration.calibrated_probability(75, fitted) is None
