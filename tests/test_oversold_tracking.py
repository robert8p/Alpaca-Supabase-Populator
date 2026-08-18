from datetime import UTC, datetime

from app.oversold_tracking import (
    _calendar_datetime,
    _checkpoint_times,
    _last_completed_bar,
    _trade_from_payload,
)


def test_calendar_time_only_uses_new_york_timezone():
    row = {"date": "2026-08-19", "open": "09:30", "close": "16:00"}
    assert _calendar_datetime(row, "open") == datetime(2026, 8, 19, 13, 30, tzinfo=UTC)
    assert _calendar_datetime(row, "close") == datetime(2026, 8, 19, 20, 0, tzinfo=UTC)


def test_checkpoint_times_use_actual_session_length():
    open_at = datetime(2026, 11, 27, 14, 30, tzinfo=UTC)
    close_at = datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    result = _checkpoint_times(open_at, close_at)
    assert result["open_plus_1h"] == datetime(2026, 11, 27, 15, 30, tzinfo=UTC)
    assert result["mid_session"] == datetime(2026, 11, 27, 16, 15, tzinfo=UTC)
    assert result["close"] == close_at


def test_latest_trade_payload_parsing():
    payload = {"trades": {"TEST": {"p": 12.34, "t": "2026-08-18T20:55:00Z"}}}
    price, ts = _trade_from_payload(payload, "TEST")
    assert price == 12.34
    assert ts == datetime(2026, 8, 18, 20, 55, tzinfo=UTC)


def test_last_completed_bar_excludes_bar_starting_at_checkpoint():
    target = datetime(2026, 8, 19, 14, 30, tzinfo=UTC)
    bars = [
        {"t": "2026-08-19T14:28:00Z", "c": 10.0},
        {"t": "2026-08-19T14:29:00Z", "c": 10.2},
        {"t": "2026-08-19T14:30:00Z", "c": 10.4},
    ]
    selected = _last_completed_bar(bars, target)
    assert selected["c"] == 10.2
