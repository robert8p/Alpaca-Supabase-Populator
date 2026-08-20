from __future__ import annotations

from datetime import UTC, datetime

from app.oversold_outcomes_v33 import calculate_three_session_path


def parse(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def test_three_session_path_uses_only_first_three_future_sessions() -> None:
    row = {
        "signal_timestamp": datetime(2026, 8, 17, 20, 0, tzinfo=UTC),
        "signal_price": 10.0,
    }
    bars = [
        {"t": "2026-08-18T13:30:00Z", "h": 10.5, "l": 9.0, "c": 9.8},
        {"t": "2026-08-19T13:30:00Z", "h": 11.2, "l": 9.5, "c": 10.7},
        {"t": "2026-08-20T13:30:00Z", "h": 10.9, "l": 8.8, "c": 9.1},
        {"t": "2026-08-21T13:30:00Z", "h": 15.0, "l": 7.0, "c": 14.0},
    ]
    result = calculate_three_session_path(row, bars, parse_ts=parse)
    assert result["matured"] is True
    assert result["bar_count"] == 3
    assert round(result["mfe_3d"], 4) == 12.0
    assert round(result["mae_3d"], 4) == -12.0
    assert result["time_to_mfe_3d_sessions"] == 2
    assert result["time_to_mae_3d_sessions"] == 3


def test_three_session_path_ignores_bars_at_or_before_signal() -> None:
    row = {
        "signal_timestamp": datetime(2026, 8, 18, 15, 0, tzinfo=UTC),
        "signal_price": 10.0,
    }
    bars = [
        {"t": "2026-08-18T13:30:00Z", "h": 20.0, "l": 5.0, "c": 15.0},
        {"t": "2026-08-19T13:30:00Z", "h": 10.2, "l": 9.8, "c": 10.0},
    ]
    result = calculate_three_session_path(row, bars, parse_ts=parse)
    assert result["bar_count"] == 1
    assert result["matured"] is False
    assert round(result["mfe_3d"], 4) == 2.0
