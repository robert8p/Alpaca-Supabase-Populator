from __future__ import annotations

from pathlib import Path

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


def test_guard_loads_all_requested_research_metric_columns() -> None:
    root = Path(__file__).resolve().parents[1]
    template = (root / "app/templates/reversion_guard.html").read_text(encoding="utf-8")
    script = (root / "app/static/reversion_guard_fundamental_columns.js").read_text(encoding="utf-8")
    assert "reversion_guard_fundamental_columns.js" in template
    for label in ["PEG", "Forward P/E", "FCF yield", "ROIC", "Balance sheet", "EPS growth"]:
        assert label in script
    assert "technical_inputs?.fundamentals" in script
    assert "data-candidate-id" in script
    assert "Never borrow current metrics for an unmatched/historical signal" in script
