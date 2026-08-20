from pathlib import Path

from app.oversold_scoring import _damage_class


def test_damage_class_matches_audit_economic_bands() -> None:
    assert _damage_class(29) == "LOW"
    assert _damage_class(30) == "MODERATE"
    assert _damage_class(58) == "MODERATE"
    assert _damage_class(64) == "MODERATE"
    assert _damage_class(65) == "HIGH"
    assert _damage_class(79) == "HIGH"
    assert _damage_class(80) == "STRUCTURAL_OR_EXISTENTIAL"


def test_historical_rescore_skips_signals_already_originally_scored_by_current_model() -> None:
    source = Path("app/oversold_evaluation.py").read_text(encoding="utf-8")
    assert "NOT (original.scoring_model_version=%s AND original.scoring_config_version=%s)" in source
    assert "NOT (old.scoring_model_version=%s AND old.scoring_config_version=%s)" in source
