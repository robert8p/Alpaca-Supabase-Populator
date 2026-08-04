from datetime import UTC, date, datetime, time

import pytest

from app.core import classify_session, estimate_for, filter_assets, in_selected_session
from app.models import JobConfig


def base_config(**overrides):
    data = {
        "name": "Test load",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "timeframes": ["5Min"],
        "universe": {"mode": "explicit", "symbols": ["AAPL"]},
    }
    data.update(overrides)
    return JobConfig.model_validate(data)


def test_custom_minute_timeframes_are_supported():
    cfg = base_config(timeframes=["1Min", "7Min", "59Min", "1Hour", "1Day"])
    assert cfg.timeframes == ["1Min", "7Min", "59Min", "1Hour", "1Day"]


def test_invalid_timeframe_is_rejected():
    with pytest.raises(ValueError):
        base_config(timeframes=["60Min"])


def test_regular_session_filter_uses_new_york_time():
    cfg = base_config(session={"mode": "regular", "weekdays_only": True})
    # 14:30 UTC is 09:30 ET in January.
    assert in_selected_session(datetime(2026, 1, 5, 14, 30, tzinfo=UTC), cfg)
    assert not in_selected_session(datetime(2026, 1, 5, 13, 0, tzinfo=UTC), cfg)


def test_custom_session_can_cross_midnight():
    cfg = base_config(session={"mode": "custom", "custom_start": "20:00", "custom_end": "04:00", "weekdays_only": True})
    assert in_selected_session(datetime(2026, 1, 6, 2, 0, tzinfo=UTC), cfg)  # 21:00 ET prior day


def test_session_classification():
    assert classify_session(datetime(2026, 1, 5, 15, 0, tzinfo=UTC)) == "regular"
    assert classify_session(datetime(2026, 1, 5, 12, 0, tzinfo=UTC)) == "premarket"


def test_asset_filters_and_limit():
    cfg = JobConfig.model_validate({
        "name": "Asset test", "start_date": "2026-01-01", "end_date": "2026-01-02",
        "timeframes": ["5Min"],
        "universe": {"mode": "all_active", "exchanges": ["NASDAQ"], "tradable_only": True, "symbol_limit": 1},
    })
    assets = [
        {"symbol": "AAPL", "exchange": "NASDAQ", "tradable": True},
        {"symbol": "MSFT", "exchange": "NASDAQ", "tradable": True},
        {"symbol": "IBM", "exchange": "NYSE", "tradable": True},
    ]
    selected = filter_assets(assets, cfg)
    assert [x["symbol"] for x in selected] == ["AAPL"]


def test_estimate_scales_with_symbols():
    cfg = base_config()
    one = estimate_for(cfg, 1)
    ten = estimate_for(cfg, 10)
    assert ten["estimated_rows"] == one["estimated_rows"] * 10
