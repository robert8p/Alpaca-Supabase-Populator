from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime, timedelta

from app.intraday_profitability_scoring import (
    benchmark_returns,
    build_market_features,
    rank_market_records,
    snapshot_liquidity_record,
)


NOW = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)


def make_snapshot(*, last=100.0, prev_close=99.0, prev_volume=2_000_000, current_volume=800_000, bid=99.99, ask=100.01):
    return {
        "prevDailyBar": {"c": prev_close, "v": prev_volume},
        "dailyBar": {"c": last, "h": last * 1.01, "l": last * 0.99, "v": current_volume, "n": 50_000},
        "minuteBar": {"c": last},
        "latestTrade": {"p": last, "t": (NOW - timedelta(seconds=1)).isoformat()},
        "latestQuote": {"bp": bid, "ap": ask, "t": (NOW - timedelta(seconds=1)).isoformat()},
    }


def make_bars(prices: list[float], *, base_volume: float = 100_000, accelerate: bool = False):
    start = NOW - timedelta(minutes=len(prices))
    output = []
    for index, price in enumerate(prices):
        volume = base_volume * (1 + (index / max(1, len(prices) - 1)) * 1.5) if accelerate else base_volume
        output.append(
            {
                "t": (start + timedelta(minutes=index)).isoformat(),
                "o": price * 0.9995,
                "h": price * 1.001,
                "l": price * 0.999,
                "c": price,
                "v": volume,
                "vw": price,
                "n": int(volume / 100),
            }
        )
    return output


def liquidity(symbol: str, *, last=100.0, spread_bps=2.0, volume_pace=1.5):
    midpoint = last
    half_spread = midpoint * (spread_bps / 10_000) / 2
    previous_volume = 2_000_000
    elapsed = 150
    current_volume = previous_volume * volume_pace * elapsed / 390
    record = snapshot_liquidity_record(
        symbol=symbol,
        asset={"name": f"{symbol} Corp", "exchange": "NASDAQ"},
        snapshot=make_snapshot(
            last=last,
            prev_close=last * 0.99,
            prev_volume=previous_volume,
            current_volume=current_volume,
            bid=midpoint - half_spread,
            ask=midpoint + half_spread,
        ),
        evidence_cutoff=NOW,
        elapsed_minutes=elapsed,
        min_price=5,
        min_prev_dollar_volume=50_000_000,
        min_current_dollar_volume=5_000_000,
        max_spread_bps=25,
        max_quote_age_seconds=180,
    )
    assert record is not None
    return record


class LiquidityGateTests(unittest.TestCase):
    def test_accepts_highly_liquid_tight_spread(self):
        record = liquidity("LIQD", spread_bps=2.5)
        self.assertEqual(record["symbol"], "LIQD")
        self.assertLess(record["spread_bps"], 3.0)
        self.assertGreater(record["prev_dollar_volume"], 50_000_000)

    def test_rejects_wide_spread(self):
        record = snapshot_liquidity_record(
            symbol="WIDE",
            asset={"name": "Wide Corp", "exchange": "NASDAQ"},
            snapshot=make_snapshot(bid=99.5, ask=100.5),
            evidence_cutoff=NOW,
            elapsed_minutes=150,
            min_price=5,
            min_prev_dollar_volume=50_000_000,
            min_current_dollar_volume=5_000_000,
            max_spread_bps=25,
            max_quote_age_seconds=180,
        )
        self.assertIsNone(record)


class RankingTests(unittest.TestCase):
    def setUp(self):
        benchmark_prices = [500 + math.sin(index / 7) * 0.05 for index in range(70)]
        self.benchmark_bars = make_bars(benchmark_prices)
        self.benchmark = benchmark_returns(self.benchmark_bars, evidence_cutoff=NOW)

    def features(self, symbol: str, prices: list[float], *, spread_bps=3.0, volume_pace=1.5, accelerate=False):
        result = build_market_features(
            liquidity_record=liquidity(symbol, last=prices[-1], spread_bps=spread_bps, volume_pace=volume_pace),
            raw_bars=make_bars(prices, accelerate=accelerate),
            benchmark_returns=self.benchmark,
            evidence_cutoff=NOW,
        )
        self.assertIsNotNone(result)
        return result

    def test_clear_long_continuation_ranks_above_flat_setup(self):
        trend = [100 + index * 0.035 for index in range(70)]
        flat = [100 + math.sin(index / 3) * 0.03 for index in range(70)]
        ranked = rank_market_records(
            [
                self.features("TREND", trend, spread_bps=2.0, volume_pace=2.2, accelerate=True),
                self.features("FLAT", flat, spread_bps=5.0, volume_pace=1.0),
            ]
        )
        self.assertEqual(ranked[0]["symbol"], "TREND")
        self.assertEqual(ranked[0]["direction"], "LONG")
        self.assertEqual(ranked[0]["setup_type"], "CONTINUATION")
        self.assertGreater(ranked[0]["profitability_score"], ranked[1]["profitability_score"])

    def test_reversion_requires_a_real_short_horizon_turn(self):
        falling_then_turning = [100 - index * 0.09 for index in range(60)] + [94.6, 94.8, 95.0, 95.25, 95.5, 95.8, 96.1, 96.35, 96.55, 96.8]
        record = self.features("TURN", falling_then_turning, spread_bps=3.0, volume_pace=2.0, accelerate=True)
        ranked = rank_market_records([record])
        self.assertEqual(ranked[0]["direction"], "LONG")
        self.assertIn(ranked[0]["setup_type"], {"REVERSION", "CONTINUATION"})
        # The key safety requirement: the chosen long setup has a positive five-minute turn.
        self.assertGreater(ranked[0]["return_5m_pct"], 0)

    def test_short_filter_never_returns_long(self):
        rising = [100 + index * 0.04 for index in range(70)]
        falling = [103 - index * 0.04 for index in range(70)]
        ranked = rank_market_records(
            [self.features("UP", rising), self.features("DOWN", falling)],
            direction_filter="short",
        )
        self.assertTrue(all(row["direction"] == "SHORT" for row in ranked))

    def test_score_is_bounded_and_contains_execution_cost(self):
        prices = [100 + index * 0.02 for index in range(70)]
        ranked = rank_market_records([self.features("BOUND", prices)])
        row = ranked[0]
        self.assertGreaterEqual(row["profitability_score"], 0)
        self.assertLessEqual(row["profitability_score"], 100)
        self.assertGreater(row["cost_estimate_bps"], row["spread_bps"])
        self.assertIn("estimated round-trip cost", row["rationale"])


if __name__ == "__main__":
    unittest.main()
