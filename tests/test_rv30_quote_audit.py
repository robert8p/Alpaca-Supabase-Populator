from datetime import UTC, datetime, timedelta

from app.rv30_quote_audit import _quote_time, _valid_snapshot


def test_quote_time_accepts_nanoseconds() -> None:
    value = _quote_time("2026-08-10T14:31:01.123456789Z")
    assert value == datetime(2026, 8, 10, 14, 31, 1, 123456, tzinfo=UTC)


def test_valid_snapshot_enforces_frozen_one_second_latency() -> None:
    target = datetime(2026, 8, 10, 14, 31, 0, tzinfo=UTC)
    earliest = target + timedelta(seconds=1)

    too_early = {"t": "2026-08-10T14:31:00.999999Z", "bp": 100.0, "ap": 100.02}
    assert _valid_snapshot("ABC", too_early, earliest_ts=earliest, target_ts=target) is None

    eligible = {"t": "2026-08-10T14:31:01.250000Z", "bp": 100.0, "ap": 100.02, "bs": 10, "as": 12}
    snap = _valid_snapshot("ABC", eligible, earliest_ts=earliest, target_ts=target)
    assert snap is not None
    assert snap["bid_price"] == 100.0
    assert snap["ask_price"] == 100.02
    assert snap["latency_ms"] == 1250.0


def test_invalid_crossed_or_zero_quote_is_rejected() -> None:
    target = datetime(2026, 8, 10, 14, 31, 0, tzinfo=UTC)
    earliest = target + timedelta(seconds=1)
    assert _valid_snapshot(
        "ABC",
        {"t": "2026-08-10T14:31:01Z", "bp": 0, "ap": 100.02},
        earliest_ts=earliest,
        target_ts=target,
    ) is None
    assert _valid_snapshot(
        "ABC",
        {"t": "2026-08-10T14:31:01Z", "bp": 100.03, "ap": 100.02},
        earliest_ts=earliest,
        target_ts=target,
    ) is None
