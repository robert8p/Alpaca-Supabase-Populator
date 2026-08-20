from __future__ import annotations

from pathlib import Path

from app.oversold_scoring import public_scoring_contract
from app.oversold_v33_diagnostics import decorate_diagnostics


ROOT = Path("app/static")


def test_public_contract_exposes_current_v33_semantics_only() -> None:
    contract = public_scoring_contract()
    assert contract["score_semantics"]["name"] == "Opportunity Score"
    assert contract["weights"] == contract["opportunity_architecture"]["weights"]
    assert "overreaction" in contract["weights"]
    assert "setup" not in contract["weights"]
    assert contract["investigate_gates"]["minimum_opportunity_score"] == 72.0
    assert contract["investigate_gates"]["minimum_previous_dollar_volume"] == 2_000_000.0
    assert contract["investigate_gates"]["maximum_spread_pct"] == 3.0
    assert contract["confidence"]["minimum_multiplier"] == 0.35
    assert "legacy_feature_context" in contract
    assert "cause_unknown" not in contract


def test_diagnostics_decorator_labels_v33_and_retains_analytics() -> None:
    result = decorate_diagnostics(
        {"summary": {"scored_signals": 10}, "catalyst_backend": "stale"},
        coverage={"primary_fundamentals_available": 8, "verified_causes": 5},
        sectors=[{"sector": "Industrials", "sample_count": 4}],
        catalysts=[{"catalyst_type": "temporary_operational_issue", "sample_count": 2}],
    )
    assert result["catalyst_backend"] == "rules_v3_3_point_in_time"
    assert result["summary"]["scored_signals"] == 10
    assert result["summary"]["primary_fundamentals_available"] == 8
    assert result["by_sector"][0]["sector"] == "Industrials"
    assert result["by_catalyst_type"][0]["catalyst_type"] == "temporary_operational_issue"


def test_v33_ui_uses_current_formula_and_six_decision_metrics() -> None:
    source = (ROOT / "oversold_v33_explainability.js").read_text(encoding="utf-8")
    for label in (
        "Overreaction",
        "Reversibility",
        "Survivability",
        "3-session fit",
        "Tail risk",
        "Evidence",
    ):
        assert label in source
    assert "Weighted geometric opportunity" in source
    assert "Evidence-confidence multiplier" in source
    assert "Tail-risk penalty" in source
    assert "Current v3.3 calculation" in source
    assert "new MutationObserver(schedule).observe(rows, {childList:true, subtree:true})" in source


def test_loader_includes_v33_explainability_after_current_bundles() -> None:
    source = (ROOT / "oversold_tracking_v3.js").read_text(encoding="utf-8")
    assert "oversold_v33_ui.js" in source
    assert "oversold_chatgpt_v33.js" in source
    assert "oversold_v33_explainability.js" in source
    assert source.index("oversold_v33_ui.js") < source.index("oversold_chatgpt_v33.js") < source.index("oversold_v33_explainability.js")
