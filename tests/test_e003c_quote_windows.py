from datetime import date, time

from app.e003c_live import _parse_quote_datetime, _quote_in_window


def test_quote_timestamp_parses_utc_and_converts_to_new_york():
    observed = _parse_quote_datetime("2026-08-11T13:30:02.123456Z")
    assert observed is not None
    assert observed.date() == date(2026, 8, 11)
    assert observed.hour == 9
    assert observed.minute == 30


def test_entry_quote_must_be_inside_frozen_window():
    trade_date = date(2026, 8, 11)
    assert _quote_in_window(
        "2026-08-11T13:30:01Z",
        trade_date,
        time(9, 30),
        time(9, 35, 59),
    )
    assert not _quote_in_window(
        "2026-08-11T13:29:59Z",
        trade_date,
        time(9, 30),
        time(9, 35, 59),
    )
    assert not _quote_in_window(
        "2026-08-11T13:36:00Z",
        trade_date,
        time(9, 30),
        time(9, 35, 59),
    )


def test_exit_quote_must_be_inside_frozen_window():
    trade_date = date(2026, 8, 11)
    assert _quote_in_window(
        "2026-08-11T19:59:58Z",
        trade_date,
        time(15, 54),
        time(15, 59, 59),
    )
    assert not _quote_in_window(
        "2026-08-11T20:00:00Z",
        trade_date,
        time(15, 54),
        time(15, 59, 59),
    )
