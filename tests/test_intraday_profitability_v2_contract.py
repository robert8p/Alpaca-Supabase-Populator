from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.intraday_profitability_scoring import (
    SCORING_VERSION,
    TARGET_DEFINITION,
    benchmark_returns,
    build_market_features,
    rank_market_records,
    snapshot_liquidity_record,
)

NOW = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)


def _bars(prices: list[float]) -> list[dict[str, object]]:
    start = NOW - timedelta(minutes=len(prices))
    return [
        {
            "t": (start + timedelta(minutes=index)).isoformat(),
            "o": price * 0.999,
            "h": price * 1.001,
            "l": price * 0.999,
            "c": price,
            "v": 100_000 + index * 1_000,
            "vw": price,
            "n": 1_000 + index,
        }
        for index, price in enumerate(prices)
    ]


def _liquidity() -> dict[str, object]:
    snapshot = {
        "prevDailyBar": {"c": 99.0, "v": 2_000_000},
        "dailyBar": {"c": 101.0, "h": 102.0, "l": 98.5, "v": 1_000_000, "n": 50_000},
        "minuteBar": {"c": 101.0},
        "latestTrade": {"p": 101.0, "t": (NOW - timedelta(seconds=1)).isoformat()},
        "latestQuote": {"bp": 100.99, "ap": 101.01, "t": (NOW - timedelta(seconds=1)).isoformat()},
    }
    record = snapshot_liquidity_record(
        symbol="TEST",
        asset={"name": "Test Corp", "exchange": "NASDAQ"},
        snapshot=snapshot,
        evidence_cutoff=NOW,
        elapsed_minutes=150,
        min_price=5,
        min_prev_dollar_volume=50_000_000,
        min_current_dollar_volume=5_000_000,
        max_spread_bps=25,
        max_quote_age_seconds=180,
    )
    assert record is not None
    return record


def test_scanner_prefilter_contract_is_preserved() -> None:
    record = _liquidity()
    for field in (
        "coarse_liquidity_score",
        "prev_volume",
        "current_volume",
        "daily_range_pct",
        "daily_trade_count",
        "quote_timestamp",
        "latest_trade_timestamp",
    ):
        assert field in record
    assert float(record["coarse_liquidity_score"]) > 0


def test_persisted_evidence_contract_is_preserved() -> None:
    spy = benchmark_returns(_bars([500 + index * 0.002 for index in range(70)]), evidence_cutoff=NOW)
    features = build_market_features(
        liquidity_record=_liquidity(),
        raw_bars=_bars([100 + index * 0.03 for index in range(70)]),
        benchmark_returns=spy,
        evidence_cutoff=NOW,
    )
    assert features is not None
    for field in (
        "bar_start",
        "bar_end",
        "realized_vol_30m_pct",
        "realized_vol_60m_pct",
        "intraday_range_pct",
        "trend_efficiency",
        "setup_scores",
        "data_quality_score",
    ):
        assert field in features

    ranked = rank_market_records([features])
    assert len(ranked) == 1
    row = ranked[0]
    for field in (
        "edge_to_cost_ratio",
        "data_quality_score",
        "penalties",
        "scoring_version",
        "target_definition",
    ):
        assert field in row
    assert row["scoring_version"] == SCORING_VERSION
    assert row["target_definition"] == TARGET_DEFINITION
    assert float(row["edge_to_cost_ratio"]) > 0
