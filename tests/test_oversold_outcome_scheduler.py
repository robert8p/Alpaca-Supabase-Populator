from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.oversold_outcome_scheduler import outcome_capture_due

NY = ZoneInfo("America/New_York")


def et(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=NY)


def test_outcome_capture_runs_once_after_daily_cutoff():
    now = et("2026-08-20T18:31:00")
    assert outcome_capture_due(now, None) is True
    assert outcome_capture_due(now, date(2026, 8, 20)) is False


def test_outcome_capture_does_not_run_before_cutoff():
    assert outcome_capture_due(et("2026-08-20T18:29:59"), None) is False


def test_outcome_capture_skips_weekends():
    assert outcome_capture_due(et("2026-08-22T19:00:00"), None) is False
