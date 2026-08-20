from pathlib import Path

from app.oversold_scoring import SCORING_CONFIG, SCORING_CONFIG_VERSION, TARGET_DEFINITION
from app.oversold_three_session_target import TARGET_TRADING_SESSIONS


def test_calibration_contract_is_three_trading_sessions() -> None:
    assert TARGET_DEFINITION == "hit_reversion_within_3_trading_sessions"
    assert SCORING_CONFIG_VERSION == "or_score_config_2026_08_20_v4"
    assert SCORING_CONFIG["target"]["horizon_trading_sessions"] == 3
    assert SCORING_CONFIG["calibration"]["target_horizon_trading_sessions"] == 3


def test_calibration_runtime_uses_three_session_metadata_not_six_week_maturity() -> None:
    source = Path("app/oversold_three_session_target.py").read_text(encoding="utf-8")
    assert "hit_reversion_within_3_sessions" in source
    assert "calibration_target_matured" in source
    assert "trading_days_to_plus_5 BETWEEN 1 AND %s" in source
    assert "so.eligible_for_calibration=true" in source


def test_ui_describes_horizon_without_exposing_target_threshold() -> None:
    source = Path("app/static/oversold_top5.js").read_text(encoding="utf-8")
    assert "Calibration horizon: reversion must occur within 3 trading sessions." in source
    assert "evidence for/against a reversion within 3 trading sessions" in source
    assert "Rank by 3-trading-session reversion quality" in source or "rank by 3-trading-session reversion quality" in source


def test_prompt_sanitizer_handles_legacy_target_copy() -> None:
    source = Path("app/static/oversold_top5.js").read_text(encoding="utf-8")
    assert "sanitizeTargetCopy" in source
    assert "legacy_reversion_target" in source
    assert "window.buildChatGPTPrompt = wrapped" in source
