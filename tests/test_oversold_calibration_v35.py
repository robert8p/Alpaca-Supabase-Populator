from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app import oversold_calibration as calibration
from app.oversold_calibration_v35 import calibration_robustness_checks


def samples(*, reversed_signal: bool = False) -> list[dict]:
    rows: list[dict] = []
    start = datetime(2025, 1, 2, tzinfo=UTC)
    for index in range(360):
        score = float((index * 17) % 101)
        target = score >= 52
        if index % 11 == 0:
            target = not target
        if reversed_signal:
            target = not target
        rows.append(
            {
                "score": score,
                "target": target,
                "signal_timestamp": start + timedelta(days=index),
                "sector": ["Technology", "Healthcare", "Industrials", "Consumer"][index % 4],
            }
        )
    return rows


def test_robust_calibration_checks_pass_for_stable_predictive_score() -> None:
    result = calibration_robustness_checks(calibration, samples())
    assert result["bootstrap"]["positive_direction_rate"] >= 0.80
    assert result["quartile_separation"]["separation"] >= 0.05
    assert len(result["temporal_folds"]) >= 3
    assert result["median_temporal_auc"] >= 0.55
    assert result["passed"] is True


def test_robust_calibration_checks_reject_inverted_score() -> None:
    result = calibration_robustness_checks(calibration, samples(reversed_signal=True))
    assert result["bootstrap"]["positive_direction_rate"] < 0.20
    assert result["quartile_separation"]["separation"] < 0
    assert result["passed"] is False


def test_robust_calibration_checks_are_deterministic() -> None:
    first = calibration_robustness_checks(calibration, samples())
    second = calibration_robustness_checks(calibration, samples())
    assert first == second
