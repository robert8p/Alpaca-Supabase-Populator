from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.intraday_profitability_tracking import _selection_outcome

SCAN = datetime(2026, 8, 20, 17, 41, 57, tzinfo=UTC)
CLOSE = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)


def bar(timestamp: datetime, high: float, low: float, close: float) -> dict[str, object]:
    return {"t": timestamp.isoformat(), "h": high, "l": low, "c": close}


class SelectionOutcomeTests(unittest.TestCase):
    def test_long_uses_highest_post_scan_high_and_last_close(self):
        selection = {"direction": "LONG", "scan_at": SCAN, "market_close_at": CLOSE}
        bars = [
            bar(SCAN.replace(second=0), 110, 90, 100),
            bar(SCAN.replace(second=0) + timedelta(minutes=1), 102, 99, 101),
            bar(CLOSE - timedelta(minutes=1), 104, 100, 103),
        ]
        best, _, close, _, closed, count = _selection_outcome(
            selection,
            bars,
            now=CLOSE + timedelta(minutes=5),
        )
        self.assertEqual(best, 104)
        self.assertEqual(close, 103)
        self.assertTrue(closed)
        self.assertEqual(count, 2)

    def test_short_uses_lowest_post_scan_low(self):
        selection = {"direction": "SHORT", "scan_at": SCAN, "market_close_at": CLOSE}
        bars = [
            bar(SCAN.replace(second=0) + timedelta(minutes=1), 102, 98, 99),
            bar(SCAN.replace(second=0) + timedelta(minutes=2), 101, 95, 96),
        ]
        best, _, _, _, closed, _ = _selection_outcome(
            selection,
            bars,
            now=SCAN + timedelta(minutes=10),
        )
        self.assertEqual(best, 95)
        self.assertFalse(closed)

    def test_partially_observed_scan_minute_is_excluded(self):
        selection = {"direction": "LONG", "scan_at": SCAN, "market_close_at": CLOSE}
        bars = [
            bar(SCAN.replace(second=0), 150, 80, 100),
            bar(SCAN.replace(second=0) + timedelta(minutes=1), 101, 99, 100),
        ]
        best, *_ = _selection_outcome(selection, bars, now=SCAN + timedelta(minutes=10))
        self.assertEqual(best, 101)


if __name__ == "__main__":
    unittest.main()
