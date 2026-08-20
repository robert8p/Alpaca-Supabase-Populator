from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.intraday_profitability_tracking import _tracking_outcome

SCAN = datetime(2026, 8, 20, 17, 41, 57, tzinfo=UTC)
HORIZON = datetime(2026, 8, 20, 19, 41, 57, tzinfo=UTC)
CLOSE = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)


def bar(timestamp: datetime, open_price: float, high: float, low: float, close: float) -> dict[str, object]:
    return {"t": timestamp.isoformat(), "o": open_price, "h": high, "l": low, "c": close}


class CandidateOutcomeTests(unittest.TestCase):
    def test_long_tracks_next_minute_entry_favourable_adverse_horizon_and_close(self):
        tracking = {
            "direction": "LONG",
            "scan_at": SCAN,
            "horizon_end_at": HORIZON,
            "market_close_at": CLOSE,
        }
        bars = [
            bar(SCAN.replace(second=0), 100, 150, 80, 100),  # partial scan minute: must be ignored
            bar(SCAN.replace(second=0) + timedelta(minutes=1), 101, 102, 99, 101.5),
            bar(HORIZON - timedelta(minutes=1), 102, 106, 98, 105),
            bar(CLOSE - timedelta(minutes=1), 104, 105, 100, 103),
        ]
        result = _tracking_outcome(tracking, bars, now=CLOSE + timedelta(minutes=5))
        self.assertEqual(result["entry_price"], 101)
        self.assertEqual(result["favourable_price"], 106)
        self.assertEqual(result["adverse_price"], 98)
        self.assertEqual(result["horizon_price"], 105)
        self.assertEqual(result["close_price"], 103)
        self.assertTrue(result["horizon_matured"])
        self.assertTrue(result["closed"])
        self.assertEqual(result["bars_used"], 3)

    def test_short_reverses_favourable_and_adverse_extremes(self):
        tracking = {
            "direction": "SHORT",
            "scan_at": SCAN,
            "horizon_end_at": HORIZON,
            "market_close_at": CLOSE,
        }
        bars = [
            bar(SCAN.replace(second=0) + timedelta(minutes=1), 100, 102, 98, 99),
            bar(SCAN.replace(second=0) + timedelta(minutes=2), 99, 104, 95, 96),
        ]
        result = _tracking_outcome(tracking, bars, now=SCAN + timedelta(minutes=10))
        self.assertEqual(result["entry_price"], 100)
        self.assertEqual(result["favourable_price"], 95)
        self.assertEqual(result["adverse_price"], 104)
        self.assertFalse(result["horizon_matured"])
        self.assertFalse(result["closed"])

    def test_horizon_uses_last_complete_bar_before_fixed_deadline(self):
        tracking = {
            "direction": "LONG",
            "scan_at": SCAN,
            "horizon_end_at": HORIZON,
            "market_close_at": CLOSE,
        }
        bars = [
            bar(HORIZON - timedelta(minutes=2), 100, 101, 99, 100.5),
            bar(HORIZON - timedelta(minutes=1), 100.5, 102, 100, 101.75),
            bar(HORIZON, 101.75, 120, 90, 110),  # starts at deadline: excluded
        ]
        result = _tracking_outcome(tracking, bars, now=HORIZON + timedelta(minutes=5))
        self.assertEqual(result["horizon_price"], 101.75)
        self.assertEqual(result["horizon_at"], HORIZON - timedelta(minutes=1))
        self.assertTrue(result["horizon_matured"])

    def test_partial_scan_minute_is_excluded_from_entry_and_excursions(self):
        tracking = {
            "direction": "LONG",
            "scan_at": SCAN,
            "horizon_end_at": HORIZON,
            "market_close_at": CLOSE,
        }
        bars = [
            bar(SCAN.replace(second=0), 100, 150, 80, 100),
            bar(SCAN.replace(second=0) + timedelta(minutes=1), 101, 102, 99, 100),
        ]
        result = _tracking_outcome(tracking, bars, now=SCAN + timedelta(minutes=10))
        self.assertEqual(result["entry_price"], 101)
        self.assertEqual(result["favourable_price"], 102)
        self.assertEqual(result["adverse_price"], 99)


if __name__ == "__main__":
    unittest.main()
