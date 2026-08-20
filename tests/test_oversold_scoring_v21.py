from __future__ import annotations

from app.oversold_score_catalyst import classify_news_for_candidate, structured_catalyst_analysis
from app.oversold_score_fundamental import resilience_score
from app.oversold_score_technical import setup_score
from app.oversold_scoring import score_candidate


def _bars(values: list[float]) -> list[dict]:
    return [
        {"t": f"2026-06-{(index % 28) + 1:02d}T04:00:00Z", "c": value, "v": 1_000_000}
        for index, value in enumerate(values)
    ]


def _candidate(symbol="TEST", name="Test Corp", *, last=8.0, prev=10.0, history=None, fundamentals=None):
    return {
        "symbol": symbol,
        "name": name,
        "drop_pct": ((last / prev) - 1.0) * 100.0,
        "prev_close": prev,
        "last_price": last,
        "prev_dollar_volume": 20_000_000,
        "spread_pct": 0.5,
        "latest_trade_ts": "2026-08-19T20:00:00Z",
        "raw_snapshot": {
            "dailyBar": {"o": last * 1.03, "h": last * 1.08, "l": last * 0.93, "c": last, "v": 3_000_000, "vw": last * 0.98},
            "prevDailyBar": {"c": prev, "v": 1_000_000},
            "historicalDailyBars": history if history is not None else _bars([prev] * 30),
            "fundamentals": fundamentals or {"available": False, "provider": "massive"},
        },
    }


def _article(symbol, headline, summary="", *, symbols=None, source="benzinga"):
    return {
        "id": headline,
        "headline": headline,
        "summary": summary,
        "symbols": symbols or [symbol],
        "source": source,
        "created_at": "2026-08-19T19:00:00Z",
        "url": "https://example.test/article",
    }


def _score(candidate, articles):
    catalyst_class, _, flags = classify_news_for_candidate(candidate, articles)
    return score_candidate(candidate, articles, catalyst_class, flags)


def test_generic_multi_ticker_movers_article_cannot_invent_company_catalyst():
    candidate = _candidate("TOYO", "TOYO Co")
    article = _article(
        "TOYO",
        "20 Stocks Moving In Wednesday Session",
        "Apple earnings missed estimates badly.",
        symbols=["TOYO", "AAPL", "XYZ", "ABC", "DEF"],
    )
    catalyst_class, _, flags = classify_news_for_candidate(candidate, [article])
    assert catalyst_class == "U"
    assert "earnings_guidance" not in flags


def test_large_revenue_miss_is_more_damaging_than_mild_miss():
    toyo = _candidate("TOYO", "TOYO Co")
    lzb = _candidate("LZB", "La-Z-Boy Incorporated")
    toyo_score = _score(toyo, [_article("TOYO", "TOYO Reports H1 Results", "Sales $118.185M Miss $192.573M Estimate")])
    lzb_score = _score(lzb, [_article("LZB", "La-Z-Boy Reports Q1 Results", "Sales $475.689M Miss $501.340M Estimate; Sees Q2 Sales $500M-$520M vs $536.792M Estimate")])
    assert toyo_score["catalyst_analysis"]["event_category"] == "earnings_deterioration"
    assert lzb_score["catalyst_analysis"]["event_category"] == "earnings_deterioration"
    assert toyo_score["damage_risk"] >= lzb_score["damage_risk"] + 10
    assert toyo_score["catalyst_score"] < lzb_score["catalyst_score"]


def test_large_yoy_revenue_collapse_gets_high_damage():
    candidate = _candidate("ONFO", "Onfolio Holdings")
    score = _score(candidate, [_article("ONFO", "Onfolio Q2 Results", "Sales $1.498M down from $3.148M; EPS loss $35.57 vs loss $6.49")])
    assert score["catalyst_analysis"]["event_category"] == "earnings_deterioration"
    assert score["damage_risk"] >= 75


def test_recent_pump_unwind_is_not_rewarded_as_extreme_oversold():
    history = _bars([10.0] * 24 + [12.0, 18.0, 30.0, 45.0, 50.0])
    candidate = _candidate("PUMP", "Pump Corp", last=25.0, prev=50.0, history=history)
    setup, trace = setup_score(candidate)
    assert setup <= 30
    assert trace["caps_applied"]
    assert trace["history"]["post_spike_risk"] is True


def test_genuine_temporary_disruption_keeps_low_damage_and_high_catalyst():
    candidate = _candidate("TEMP", "Temporary Inc", last=6.0, prev=10.0, history=_bars([10.0] * 30))
    article = _article(
        "TEMP",
        "Temporary Inc says production outage is temporary",
        "Operations resume next week after short-term disruption.",
        source="businesswire",
    )
    score = _score(candidate, [article])
    assert score["setup_score"] >= 80
    assert score["catalyst_score"] >= 80
    assert score["damage_risk"] <= 25


def test_duplicate_single_source_news_does_not_create_artificial_high_evidence_confidence():
    candidate = _candidate("TEMP", "Temporary Inc", last=6.0, prev=10.0)
    articles = [
        _article("TEMP", f"Temporary Inc production outage update {index}", "Temporary outage; operations resume next week.")
        for index in range(10)
    ]
    catalyst_class, _, flags = classify_news_for_candidate(candidate, articles)
    analysis = structured_catalyst_analysis(candidate, articles, catalyst_class, flags)
    assert analysis["news_relevance"]["independent_source_count"] == 1
    assert analysis["evidence_confidence"] <= 72


def test_balance_sheet_resilience_distinguishes_strong_from_weak_company():
    strong = {
        "available": True,
        "provider": "massive",
        "ticker_details": {"market_cap": 1_000_000_000},
        "balance_sheet": {
            "cash_and_equivalents": 500_000_000,
            "total_current_liabilities": 100_000_000,
            "debt_current": 20_000_000,
            "long_term_debt_and_capital_lease_obligations": 20_000_000,
            "total_equity": 700_000_000,
        },
        "cash_flow": {"net_cash_from_operating_activities": 30_000_000},
    }
    weak = {
        "available": True,
        "provider": "massive",
        "ticker_details": {"market_cap": 1_000_000_000},
        "balance_sheet": {
            "cash_and_equivalents": 10_000_000,
            "total_current_liabilities": 200_000_000,
            "debt_current": 50_000_000,
            "long_term_debt_and_capital_lease_obligations": 100_000_000,
            "total_equity": -20_000_000,
        },
        "cash_flow": {"net_cash_from_operating_activities": -20_000_000},
    }
    strong_score, _, _ = resilience_score(_candidate(fundamentals=strong), [])
    weak_score, _, _ = resilience_score(_candidate(fundamentals=weak), [])
    assert strong_score >= 70
    assert weak_score <= 25
    assert strong_score >= weak_score + 40


def test_missing_fundamentals_are_uncertainty_not_favourable_resilience():
    score, _, missing = resilience_score(_candidate(), [])
    assert score == 45.0
    assert "fundamental_balance_sheet" in missing


def test_financing_damage_scales_with_financing_size_relative_to_market_cap():
    article = _article("FIN", "FIN Announces $5.5M Private Placement", "Private placement of common shares and warrants for $5.5M.")
    small_fraction = _candidate("FIN", "Finance Test", fundamentals={"available": True, "provider": "massive", "ticker_details": {"market_cap": 100_000_000}, "balance_sheet": {}, "cash_flow": {}})
    huge_fraction = _candidate("FIN", "Finance Test", fundamentals={"available": True, "provider": "massive", "ticker_details": {"market_cap": 8_000_000}, "balance_sheet": {}, "cash_flow": {}})
    small = _score(small_fraction, [article])
    huge = _score(huge_fraction, [article])
    assert small["catalyst_analysis"]["event_category"] == "financing_dilution"
    assert huge["damage_risk"] >= 75
    assert huge["damage_risk"] >= small["damage_risk"] + 30


def test_failed_pivotal_trial_hard_vetoes_even_extreme_setup():
    candidate = _candidate("BIO", "Bio Test", last=3.0, prev=10.0, history=_bars([10.0] * 30))
    article = _article("BIO", "Bio Test Phase 3 failed primary endpoint", "The pivotal Phase 3 trial did not meet the primary endpoint.", source="businesswire")
    score = _score(candidate, [article])
    assert score["hard_veto"] is True
    assert score["damage_risk"] >= 88
    assert score["final_score"] <= 20


def test_positive_news_that_does_not_explain_selloff_stays_cause_unverified():
    candidate = _candidate("SNSC", "Sensus Healthcare", last=6.0, prev=10.0)
    article = _article("SNSC", "Sensus Healthcare Starts Shipment Of New System", "Company starts shipment after successful launch.", source="businesswire")
    score = _score(candidate, [article])
    assert score["catalyst_analysis"]["event_category"] == "positive_news_selloff"
    assert score["catalyst_analysis"]["cause_verified"] is False
    assert score["final_score"] <= 60


def test_analyst_only_selloff_can_be_reversible_but_is_not_structural():
    candidate = _candidate("RATE", "Rating Test")
    article = _article("RATE", "Rating Test Downgraded To Hold", "Analyst lowers rating and price target; no new company operating update.")
    score = _score(candidate, [article])
    assert score["catalyst_analysis"]["event_category"] == "analyst_action"
    assert score["catalyst_score"] >= 75
    assert score["damage_risk"] <= 25


def test_score_is_reproducible_for_same_point_in_time_inputs():
    candidate = _candidate("TEMP", "Temporary Inc", last=6.0, prev=10.0)
    articles = [_article("TEMP", "Temporary Inc reports temporary outage", "Operations resume next week.", source="businesswire")]
    first = _score(candidate, articles)
    second = _score(candidate, articles)
    assert first["final_score"] == second["final_score"]
    assert first["calculation_trace"] == second["calculation_trace"]
