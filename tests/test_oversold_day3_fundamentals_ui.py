from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "static" / "oversold_day3_ui.js"
LOADER = ROOT / "app" / "static" / "oversold_tracking_v3.js"
MIGRATION = ROOT / "sql" / "oversold_reversion_tracking_v5_day3.sql"
TRACKING_PATCH = ROOT / "app" / "oversold_tracking_day3.py"


def test_tracking_schema_supports_third_session() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "session3_date" in source
    assert "session3_open" in source
    assert "session3_close" in source
    assert "session_no IN (1,2,3)" in source


def test_tracking_backend_backfills_day3_from_market_calendar() -> None:
    source = TRACKING_PATCH.read_text(encoding="utf-8")
    assert "client.get_calendar" in source
    assert "session_no,checkpoint_kind,scheduled_at" in source
    assert "VALUES (%s,3,%s,%s)" in source
    assert "completed_at=NULL" in source


def test_tabs_render_day3_without_guidance_blocks() -> None:
    source = UI.read_text(encoding="utf-8")
    assert "Day 3 · +1h" in source
    assert "Day 3 · midpoint" in source
    assert "Day 3 · close" in source
    assert ".or-note,.or-early { display:none !important; }" in source


def test_scanner_has_point_in_time_fundamentals_rating() -> None:
    source = UI.read_text(encoding="utf-8")
    assert "th.textContent = 'Fundamentals'" in source
    assert "analysis.fundamental_trace" in source
    assert "candidate?.resilience_score" in source
    assert "Revenue YoY" in source
    assert "Diluted shares YoY" in source


def test_tracking_loader_preserves_base_then_loads_extension() -> None:
    source = LOADER.read_text(encoding="utf-8")
    assert "oversold_tracking_v3_base.js" in source
    assert "oversold_day3_ui.js" in source
