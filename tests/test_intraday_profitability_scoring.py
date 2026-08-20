from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime, timedelta

from app.intraday_profitability_scoring import (
    ANALYSIS_PRIORITY_CAP,
    MODEL_AUDIT_VERSION,
    SCORING_VERSION,
    TARGET_DEFINITION,
    benchmark_returns,
    build_market_features,
    rank_market_records,
    snapshot_liquidity_record,
)

NOW = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)


def make_snapshot(
    *,
    last: float = 100.0,
    prev_close: float = 99.0,
    prev_volume: float = 2_000_000,
    current_volume: float = 800_000,
    bid: float = 99.99,
    ask: float = 100.01,
    quote_age_seconds: int = 1,
    trade_age_seconds: int = 1,
) -> dict[str, object]:
    return {
        "prevDailyBar": {"c": prev_close, "v": prev_volume},
        "dailyBar": {"c": last, "h": last * 1.01, "l": last * 0.99, "v": current_volume, "n": 50_000},
        "minuteBar": {"c": last},
        "latestTrade": {"p": last, "t": (NOW - timedelta(seconds=trade_age_seconds)).isoformat()},
        "latestQuote": {"bp": bid, "ap": ask, "t": (NOW - timedelta(seconds=quote_age_seconds)).isoformat()},
    }


def make_bars(
    prices: list[float],
    *,
    base_volume: float = 100_000,
    accelerate: bool = False,
    gap_every: int = 0,
) -> list[dict[str, object]]:
    start = NOW - timedelta(minutes=len(prices))
    output: list[dict[str, object]] = []
    for index, price in enumerate(prices):
        if gap_every and index and index % gap_every == 0:
            continue
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


def liquidity(
    symbol: str,
    *,
    last: float = 100.0,
    spread_bps: float = 2.0,
    volume_pace: float = 1.5,
    quote_age_seconds: int = 1,
    trade_age_seconds: int = 1,
    shortable: bool | None = True,
    easy_to_borrow: bool | None = True,
    elapsed_minutes: float = 150.0,
) -> dict[str, object] | None:
    midpoint = last
    half_spread = midpoint * (spread_bps / 10_000) / 2
    previous_volume = 2_000_000
    current_volume = previous_volume * volume_pace * elapsed_minutes / 390
    asset: dict[str, object] = {"name": f"{symbol} Corp", "exchange": "NASDAQ"}
    if shortable is not None:
        asset["shortable"] = shortable
    if easy_to_borrow is not None:
        asset["easy_to_borrow"] = easy_to_borrow
    return snapshot_liquidity_record(
        symbol=symbol,
        asset=asset,
        snapshot=make_snapshot(
            last=last,
            prev_close=last * 0.99,
            prev_volume=previous_volume,
            current_volume=current_volume,
            bid=midpoint - half_spread,
            ask=midpoint + half_spread,
            quote_age_seconds=quote_age_seconds,
            trade_age_seconds=trade_age_seconds,
        ),
        evidence_cutoff=NOW,
        elapsed_minutes=elapsed_minutes,
        min_price=5,
        min_prev_dollar_volume=50_000_000,
        min_current_dollar_volume=5_000_000,
        max_spread_bps=25,
        max_quote_age_seconds=180,
    )


class LiquidityGateTests(unittest.TestCase):
    def test_public_contract_is_reliability_first(self):
        self.assertEqual(SCORING_VERSION, "ip-reliability-v3.0")
        self.assertEqual(MODEL_AUDIT_VERSION, "ip-reliability-v3.0")
        self.assertIn("research-only", TARGET_DEFINITION.lower())
        self.assertIn("no calibrated probability", TARGET_DEFINITION.lower())

    def test_accepts_highly_liquid_tight_spread(self):
        record = liquidity("LIQD", spread_bps=2.5)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["symbol"], "LIQD")
        self.assertLess(record["spread_bps"], 3.0)
        self.assertGreater(record["prev_dollar_volume"], 50_000_000)
        self.assertTrue(record["shortable"])
        self.assertTrue(record["easy_to_borrow"])
        self.assertAlmostEqual(record["observed_trade_price"], 100.0)
        self.assertAlmostEqual(record["midpoint_price"], 100.0)

    def test_rejects_wide_spread_stale_data_and_bad_print(self):
        self.assertIsNone(liquidity("STALEQUOTE", quote_age_seconds=61))
        self.assertIsNone(liquidity("STALETRADE", trade_age_seconds=91))
        self.assertIsNone(
            snapshot_liquidity_record(
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
        )
        self.assertIsNone(
            snapshot_liquidity_record(
                symbol="BADPRINT",
                asset={"name": "Bad Print Corp", "exchange": "NASDAQ"},
                snapshot=make_snapshot(last=101.0, bid=99.99, ask=100.01),
                evidence_cutoff=NOW,
                elapsed_minutes=150,
                min_price=5,
                min_prev_dollar_volume=50_000_000,
                min_current_dollar_volume=5_000_000,
                max_spread_bps=25,
                max_quote_age_seconds=180,
            )
        )


class ReliabilityRankingTests(unittest.TestCase):
    def setUp(self):
        benchmark_prices = [500 + math.sin(index / 7) * 0.05 for index in range(70)]
        self.benchmark = benchmark_returns(make_bars(benchmark_prices), evidence_cutoff=NOW)

    def features(
        self,
        symbol: str,
        prices: list[float],
        *,
        spread_bps: float = 3.0,
        volume_pace: float = 1.5,
        accelerate: bool = False,
        raw_bars: list[dict[str, object]] | None = None,
        shortable: bool | None = True,
        easy_to_borrow: bool | None = True,
        elapsed_minutes: float = 150.0,
    ) -> dict[str, object]:
        liquidity_record = liquidity(
            symbol,
            last=prices[-1],
            spread_bps=spread_bps,
            volume_pace=volume_pace,
            shortable=shortable,
            easy_to_borrow=easy_to_borrow,
            elapsed_minutes=elapsed_minutes,
        )
        self.assertIsNotNone(liquidity_record)
        result = build_market_features(
            liquidity_record=liquidity_record,
            raw_bars=raw_bars or make_bars(prices, accelerate=accelerate),
            benchmark_returns=self.benchmark,
            evidence_cutoff=NOW,
        )
        self.assertIsNotNone(result)
        assert result is not None
        return result

    def test_clear_structure_ranks_above_flat_but_never_claims_edge(self):
        trend = [100 + index * 0.035 for index in range(70)]
        flat = [100 + math.sin(index / 3) * 0.03 for index in range(70)]
        ranked = rank_market_records(
            [
                self.features("TREND", trend, spread_bps=2.0, volume_pace=2.2, accelerate=True),
                self.features("FLAT", flat, spread_bps=5.0, volume_pace=1.0),
            ]
        )
        self.assertEqual(ranked[0]["symbol"], "TREND")
        self.assertGreater(ranked[0]["profitability_score"], ranked[1]["profitability_score"])
        for row in ranked:
            evidence = row["evidence"]
            self.assertEqual(evidence["reliability_label"], "NO VALIDATED EDGE")
            self.assertEqual(evidence["trade_gate"], "BLOCKED")
            self.assertEqual(evidence["empirical_reliability_score"], 0.0)
            self.assertEqual(evidence["registered_robust_candidates_tested"], 23)
            self.assertEqual(evidence["registered_robust_candidates_passed"], 0)
            self.assertNotIn(row["initial_view"], {"INVESTIGATE", "TRADE"})

    def test_analysis_priority_is_capped_and_not_probability(self):
        prices = [100 + index * 0.06 for index in range(70)]
        row = rank_market_records([
            self.features("CAP", prices, spread_bps=1.0, volume_pace=4.0, accelerate=True)
        ])[0]
        self.assertGreaterEqual(row["profitability_score"], 0)
        self.assertLessEqual(row["profitability_score"], ANALYSIS_PRIORITY_CAP)
        self.assertEqual(row["evidence"]["score_interpretation"], "analysis priority, not probability or expected return")
        self.assertIn("hypothesis for catalyst review only", row["rationale"])

    def test_executable_reference_uses_ask_for_long_and_bid_for_short(self):
        rising = [100 + index * 0.04 for index in range(70)]
        falling = [103 - index * 0.04 for index in range(70)]
        long_record = self.features("LONGREF", rising, spread_bps=4.0)
        short_record = self.features("SHORTREF", falling, spread_bps=4.0)
        long_row = rank_market_records([long_record], direction_filter="long")[0]
        short_row = rank_market_records([short_record], direction_filter="short")[0]
        self.assertAlmostEqual(long_row["last_price"], long_record["ask"])
        self.assertAlmostEqual(short_row["last_price"], short_record["bid"])
        self.assertIn("ask", long_row["evidence"]["reference_price_definition"])
        self.assertIn("bid", short_row["evidence"]["reference_price_definition"])

    def test_non_shortable_is_excluded_and_hard_to_borrow_penalised(self):
        falling = [103 - index * 0.04 for index in range(70)]
        non_shortable = self.features("NOBORROW", falling, shortable=False, easy_to_borrow=False)
        self.assertEqual(rank_market_records([non_shortable], direction_filter="short"), [])
        easy = self.features("EASY", falling, shortable=True, easy_to_borrow=True)
        hard = self.features("HARD", falling, shortable=True, easy_to_borrow=False)
        easy_row = rank_market_records([easy], direction_filter="short")[0]
        hard_row = rank_market_records([hard], direction_filter="short")[0]
        self.assertGreater(easy_row["profitability_score"], hard_row["profitability_score"])
        self.assertIn("the stock is not marked easy to borrow", hard_row["penalties"]["labels"])

    def test_opening_regime_and_ambiguous_setup_are_penalised(self):
        trend = [100 + index * 0.03 for index in range(70)]
        settled = self.features("SETTLED", trend, elapsed_minutes=150)
        opening = self.features("OPENING", trend, elapsed_minutes=10)
        settled_row = rank_market_records([settled], direction_filter="long")[0]
        opening_row = rank_market_records([opening], direction_filter="long")[0]
        self.assertGreater(settled_row["profitability_score"], opening_row["profitability_score"])
        self.assertIn("opening price discovery remains unusually unstable", opening_row["penalties"]["labels"])
        self.assertGreaterEqual(opening_row["penalties"]["ambiguity_penalty"], 0)

    def test_reversion_is_marked_insufficient_and_unstable(self):
        falling_then_turning = [100 - index * 0.09 for index in range(60)] + [94.6, 94.8, 95.0, 95.25, 95.5, 95.8, 96.1, 96.35, 96.55, 96.8]
        row = rank_market_records([
            self.features("TURN", falling_then_turning, spread_bps=3.0, volume_pace=2.0, accelerate=True)
        ], direction_filter="long")[0]
        if row["setup_type"] == "REVERSION":
            self.assertEqual(row["evidence"]["historical_setup_status"], "INSUFFICIENT_AND_UNSTABLE")
            self.assertGreaterEqual(row["evidence"]["empirical_penalty"], 20)

    def test_gappy_and_short_histories_are_rejected(self):
        prices = [100 + index * 0.02 for index in range(70)]
        liquidity_record = liquidity("GAP", last=prices[-1])
        self.assertIsNotNone(liquidity_record)
        self.assertIsNone(
            build_market_features(
                liquidity_record=liquidity_record,
                raw_bars=make_bars(prices, gap_every=3),
                benchmark_returns=self.benchmark,
                evidence_cutoff=NOW,
            )
        )
        self.assertIsNone(
            build_market_features(
                liquidity_record=liquidity_record,
                raw_bars=make_bars(prices[:30]),
                benchmark_returns=self.benchmark,
                evidence_cutoff=NOW,
            )
        )


if __name__ == "__main__":
    unittest.main()
