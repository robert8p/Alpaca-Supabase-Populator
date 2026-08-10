from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.e003c_live import _quote_metrics, _within


def test_quote_metrics():
    result = _quote_metrics({"bp": 10.0, "ap": 10.1, "t": "2026-08-10T13:32:00Z"})
    assert result["bid"] == 10.0
    assert result["ask"] == 10.1
    assert result["mid"] == 10.05
    assert result["spread_bp"] > 0


def test_within_window():
    ny = ZoneInfo("America/New_York")
    now = datetime(2026, 8, 10, 9, 35, tzinfo=ny)
    assert _within(now, time(9, 30), time(9, 40))
    assert not _within(now, time(15, 50), time(15, 59, 59))
