from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

# app.oversold reads required runtime settings at import time. These tests only
# exercise pure scoring/universe helpers, so provide inert values before import.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from app.oversold import _is_operating_company_asset
from app.oversold_scoring import SCORING_MODEL_VERSION, score_candidate, setup_score
from app.oversold_v3_hardening import classify_news_for_candidate, filter_causal_articles

SIGNAL_TS = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)


def history_bars(base: float = 10.0, days: int = 60) -> list[dict]:
    rows = []
    for index in range(days):
        ts = SIGNAL_TS - timedelta(days=days - index)
        close = base * (1.0 + ((index % 5) - 2) * 0.002)
        rows.append({"t": ts.isoformat().replace("+00:00", "Z"), "o": close, "h": close * 1.01, "l": close * 0.99, "c": close, "v": 1_000_000, "vw": close})
    return rows


def candidate(symbol="TEST", name="Test Company", last=8.0, prev=10.0, *, history=None) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "drop_pct": ((last / prev) - 1.0) * 100.0,
        "last_price": last,
        "prev_close": prev,
        "prev_volume": 1_000_000,
        "prev_dollar_volume": 10_000_000,
        "spread_pct": 0.4,
        "latest_trade_ts": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "evidence_cutoff": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "raw_snapshot": {
            "prevDailyBar": {"o": prev, "h": prev * 1.01, "l": prev * 0.99, "c": prev, "v": 1_000_000},
            "dailyBar": {"o": last * 1.02, "h": last * 1.05, "l": last * 0.95, "c": last, "v": 2_000_000, "vw": last * 0.99},
        },
        "history_bars": history if history is not None else history_bars(prev),
        "benchmark_context": {},
        "fundamentals": None,
        "enrichment_meta": {"mode": "provided", "errors": []},
    }


def article(symbol: str, headline: str, summary: str = "", *, symbols=None, source="benzinga") -> dict:
    return {
        "id": headline,
        "headline": headline,
        "summary": summary,
        "source": source,
        "symbols": symbols if symbols is not None else [symbol],
        "created_at": (SIGNAL_TS - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        "url": "https://example.test/item",
    }


def test_hardening_uses_new_model_lineage():
    assert SCORING_MODEL_VERSION == "oversold_reversion_score_v3_2"


def test_leveraged_inverse_etn_is_not_operating_company():
    assert _is_operating_company_asset({"name": "MicroSectors Gold Miners -3x Inverse Leveraged ETN"}) is False
    assert _is_operating_company_asset({"name": "La-Z-Boy Incorporated"}) is True


def test_aggregate_movers_article_is_ambient_and_cannot_invent_earnings_catalyst():
    c = candidate("TOYO", "TOYO Co., Ltd")
    aggregate = article(
        "TOYO",
        "12 Information Technology Stocks Moving In Wednesday's Intraday Session",
        "PowerCompute rose after earnings; several other stocks moved.",
        symbols=["TOYO", "PWCM", "WYFI", "ABC", "DEF", "GHI", "JKL"],
    )
    causal, trace = filter_causal_articles(c, [aggregate])
    assert causal == []
    assert trace["ambient_article_count"] == 1
    catalyst_class, _, flags = classify_news_for_candidate(c, [aggregate])
    assert catalyst_class == "U"
    assert "earnings_guidance" not in flags


def test_single_ticker_earnings_article_remains_causal():
    c = candidate("TOYO", "TOYO Co., Ltd")
    direct = article("TOYO", "Toyo Co H1 EPS $0.45 Misses $0.52 Estimate, Sales $118.185M Miss $192.573M Estimate")
    causal, _ = filter_causal_articles(c, [direct])
    assert len(causal) == 1
    catalyst_class, _, flags = classify_news_for_candidate(c, [direct])
    assert catalyst_class == "C"
    assert "earnings_guidance" in flags


def test_large_sales_miss_scores_materially_worse_than_mild_miss():
    toyo = candidate("TOYO", "TOYO Co., Ltd")
    lzb = candidate("LZB", "La-Z-Boy Incorporated")
    toyo_news = [article("TOYO", "Toyo Co H1 EPS $0.45 Misses $0.52 Estimate, Sales $118.185M Miss $192.573M Estimate")]
    lzb_news = [
        article("LZB", "La-Z-Boy Q1 Adj. EPS $0.43 Misses $0.49 Estimate, Sales $475.689M Miss $501.340M Estimate"),
        article("LZB", "La-Z-Boy Sees Q2 Sales $500.000M-$520.000M vs $536.792M Est"),
    ]
    toyo_result = score_candidate(toyo, toyo_news, "C", ["earnings_guidance"])
    lzb_result = score_candidate(lzb, lzb_news, "C", ["earnings_guidance"])
    assert toyo_result["catalyst_analysis"]["event_profile"] == "quantified_earnings_deterioration"
    assert lzb_result["catalyst_analysis"]["event_profile"] == "quantified_earnings_deterioration"
    assert toyo_result["damage_risk"] >= lzb_result["damage_risk"] + 10
    assert toyo_result["catalyst_score"] < lzb_result["catalyst_score"]


def test_yoy_revenue_collapse_is_high_damage():
    c = candidate("ONFO", "Onfolio Holdings Inc.")
    news = [article("ONFO", "Onfolio Holdings Q2 EPS $(35.57) Down From $(6.49) YoY, Sales $1.498M Down From $3.148M YoY")]
    result = score_candidate(c, news, "U", [])
    assert result["catalyst_analysis"]["event_profile"] == "quantified_earnings_deterioration"
    assert result["damage_risk"] >= 75
    assert result["catalyst_analysis"]["cause_verified"] is True


def test_controlling_stake_transaction_is_not_unknown():
    c = candidate("SLE", "Super League Enterprise, Inc.")
    news = [article("SLE", "Metaplanet Takes 95.7% Stake in Super League", "Definitive agreement gives Metaplanet about a 95.7% stake in Super League.", symbols=["SLE", "MTPLF", "BTCUSD"])]
    result = score_candidate(c, news, "U", [])
    assert result["catalyst_analysis"]["event_profile"] == "control_transaction"
    assert result["damage_risk"] >= 70
    assert result["catalyst_analysis"]["cause_verified"] is True


def test_post_spike_price_still_far_above_baseline_caps_setup():
    c = candidate("PFSA", "Profusa, Inc.")
    tech = {
        "shock_z": 0.7,
        "drawdown_from_60d_high_pct": -66.0,
        "sma20_distance_pct": 132.0,
        "sma50_distance_pct": 110.0,
        "rsi14": 58.0,
        "relative_volume20": 3.0,
        "market_relative_move_pct": -52.0,
        "sector_relative_move_pct": None,
        "technical_history_completeness": 95.0,
    }
    score, trace = setup_score(c, tech)
    assert score <= 30.0
    assert trace["setup_cap"] == 30.0
    assert trace["setup_cap_reasons"]


def test_post_spike_direct_article_is_recognised_as_unwind_not_generic_unknown():
    c = candidate("PFSA", "Profusa, Inc.")
    c["history_bars"] = history_bars(10.0)
    news = [article("PFSA", "Profusa Stock Dips After Hours As Whopping 506% Rally Cools", "Profusa shares fell after a 506.62% intraday surge.")]
    result = score_candidate(c, news, "C", ["earnings_guidance"])
    assert result["catalyst_analysis"]["event_profile"] == "post_spike_unwind"
    assert result["catalyst_analysis"]["cause_verified"] is True
    assert "earnings_guidance" not in result["catalyst_analysis"]["red_flags"]


def test_ambient_articles_do_not_inflate_independent_source_confidence():
    c = candidate("TEMP", "Temporary Company")
    direct = article("TEMP", "Temporary Company Reports Temporary Production Outage", "Operations resume tomorrow.", source="Company IR")
    ambient = [
        article("TEMP", f"12 Industrials Stocks Moving Session {index}", "Another company missed earnings.", symbols=["TEMP", "AAA", "BBB", "CCC", "DDD"], source=f"source-{index}")
        for index in range(5)
    ]
    result = score_candidate(c, [direct, *ambient], "B", [])
    trace = result["catalyst_analysis"]["evidence_quality_trace"]
    assert trace["independent_source_count"] == 1
    assert result["catalyst_analysis"]["news_relevance_trace"]["ambient_article_count"] == 5
