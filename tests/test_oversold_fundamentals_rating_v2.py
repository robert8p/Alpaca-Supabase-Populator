from pathlib import Path


SCRIPT = Path("app/static/oversold_fundamentals_rating_v2.js")
LOADER = Path("app/static/oversold_tracking_v3.js")


def test_rating_blends_resilience_damage_and_structural_signals() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "0.65 * resilience + 0.35 * (100 - damage)" in source
    assert "capital_distress" in source
    assert "primary_endpoint_failure" in source
    assert "material_dilution" in source


def test_missing_filing_data_is_limited_not_unavailable() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "limited data" in source
    assert "event/scanner data only" in source


def test_loader_applies_rating_after_day3_ui() -> None:
    source = LOADER.read_text(encoding="utf-8")
    assert "oversold_day3_ui.js" in source
    assert "oversold_fundamentals_rating_v2.js" in source
