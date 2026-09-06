from __future__ import annotations

from app.reversion_guard_engine import DEFAULT_SETTINGS, GUARD_VERSION
from app.reversion_guard_main import app


def test_guard_service_identity_is_stable() -> None:
    assert app.title == "Oversold Reversion Guard"
    assert GUARD_VERSION == "oversold_reversion_guard_v1_1"


def test_guard_default_risk_controls_are_non_zero_and_constrained() -> None:
    assert DEFAULT_SETTINGS["risk_budget_gbp"] > 0
    assert DEFAULT_SETTINGS["max_position_gbp"] > DEFAULT_SETTINGS["risk_budget_gbp"]
    assert DEFAULT_SETTINGS["max_theme_positions"] == 3
    assert DEFAULT_SETTINGS["max_open_risk_pct"] > 0
