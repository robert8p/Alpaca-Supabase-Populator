from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.oversold_scoring import (
    SCORING_CONFIG_VERSION,
    SCORING_MODEL_VERSION,
    financing_assessment,
    price_path_assessment,
    score_candidate,
)


SIGNAL_TS = datetime(2026, 8, 20, 19, 30, tzinfo=UTC)


def history_from_closes(closes: list[float], *, volume: int = 4_000_000) -> list[dict]:
    rows = []
    start = SIGNAL_TS - timedelta(days=len(closes) + 20)
    for index, close in enumerate(closes):
        ts = start + timedelta(days=index)
        rows.append({
            "t": ts.isoformat().replace("+00:00", "Z"),
            "o": close * 0.997,
            "h": close * 1.01,
            "l": close * 0.99,
            "c": close,
            "v": volume + (index % 5) * 50_000,
            "vw": close,
        })
    return rows


def stable_history(base: float = 15.0, days: int = 65) -> list[dict]:
    closes = [base * (1 + (((idx % 7) - 3) * 0.0015)) for idx in range(days)]
    closes[-1] = base
    return history_from_closes(closes)


def benchmark_snapshot(prev: float, last: float) -> dict:
    return {
        "prevDailyBar": {"c": prev, "v": 10_000_000},
        "dailyBar": {"o": prev * 0.998, "h": prev * 1.002, "l": last * 0.998, "c": last, "v": 9_000_000},
        "latestTrade": {"p": last, "t": SIGNAL_TS.isoformat().replace("+00:00", "Z")},
    }


def fundamentals(*, shares_yoy: float = 0.02, cash: float = 0.25, liabilities: float = 0.50, equity: float = 0.50, revenue_yoy: float = 0.06, margin: float = 0.08) -> dict:
    return {
        "source": "research_pid_fundamental.filing_events_v1",
        "accession_number": "000-v32-test",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 50,
        "metric_coverage_count": 8,
        "revenue_yoy": revenue_yoy,
        "net_margin": margin,
        "net_margin_yoy_delta": 0.01,
        "operating_margin": margin,
        "gross_margin": 0.45,
        "eps_change_symmetric": 0.05,
        "net_income_change_symmetric": 0.04,
        "diluted_shares_yoy": shares_yoy,
        "cash_to_assets": cash,
        "liabilities_to_assets": liabilities,
        "equity_to_assets": equity,
        "source_definition_hash": "v32-test",
        "point_in_time_rule": "available_from_strictly_before_signal_date",
    }


def candidate(*, symbol: str = "TEST", name: str = "Test Industrial Company", prev: float = 15.0, last: float = 11.25, history: list[dict] | None = None, fundamental: dict | None = None) -> dict:
    drop = ((last / prev) - 1.0) * 100.0
    return {
        "symbol": symbol,
        "name": name,
        "drop_pct": drop,
        "last_price": last,
        "prev_close": prev,
        "prev_volume": 5_000_000,
        "prev_dollar_volume": prev * 5_000_000,
        "spread_pct": 0.35,
        "latest_trade_ts": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "evidence_cutoff": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "raw_snapshot": {
            "prevDailyBar": {"o": prev * 0.995, "h": prev * 1.01, "l": prev * 0.99, "c": prev, "v": 5_000_000},
            "dailyBar": {"o": last * 0.90, "h": last * 1.03, "l": last * 0.86, "c": last, "v": 14_000_000, "vw": last * 0.96},
        },
        "history_bars": history if history is not None else stable_history(prev),
        "benchmark_context": {
            "SPY": {"snapshot": benchmark_snapshot(600.0, 598.0), "history_bars": stable_history(600.0)},
            "XLI": {"snapshot": benchmark_snapshot(150.0, 149.2), "history_bars": stable_history(150.0)},
        },
        "fundamentals": fundamental if fundamental is not None else fundamentals(),
    }


def article(headline: str, summary: str = "", *, source: str = "Company IR", symbol: str = "TEST", hours_before: float = 2.0) -> dict:
    return {
        "id": f"{symbol}:{source}:{headline}:{hours_before}",
        "headline": headline,
        "summary": summary,
        "source": source,
        "created_at": (SIGNAL_TS - timedelta(hours=hours_before)).isoformat().replace("+00:00", "Z"),
        "url": "https://example.test/article",
        "symbols": [symbol],
    }


def test_model_is_explicitly_versioned_v32() -> None:
    result = score_candidate(
        candidate(),
        [article("Test Industrial reports temporary outage", "Operations are expected to resume tomorrow after a short-term technical issue.")],
        "B",
        [],
    )
    assert SCORING_MODEL_VERSION == "oversold_reversion_score_v3_2"
    assert SCORING_CONFIG_VERSION == "or_score_config_2026_08_20_v4"
    assert result["scoring_model_version"] == SCORING_MODEL_VERSION
    assert result["scoring_config_version"] == SCORING_CONFIG_VERSION
    assert result["catalyst_analysis"]["analysis_method"] == "rules_v3_2_point_in_time"


def test_xos_type_prior_spike_is_measured_against_real_pre_spike_baseline() -> None:
    # $5 baseline -> $11 previous close -> $7 signal: the daily fall is large,
    # but the stock is still +40% versus its pre-spike baseline.
    closes = [5.0] * 55 + [5.0, 5.2, 6.0, 8.5, 11.0]
    c = candidate(symbol="XOS", name="Xos Inc", prev=11.0, last=7.0, history=history_from_closes(closes))
    result = score_candidate(
        c,
        [article("Xos shares fall after recent rally fades", "The stock had surged more than 100% before profit-taking.", symbol="XOS")],
        "C",
        [],
    )
    spike = result["catalyst_analysis"]["spike_adjustment"]
    assert spike["post_spike_unwind"] is True
    assert spike["max_prior_runup_pct"] >= 100.0
    assert spike["current_vs_pre_spike_baseline_pct"] >= 35.0
    assert spike["penalty"] >= 25.0
    assert result["setup_score"] <= 35.0
    assert result["verdict"] != "INVESTIGATE"
    assert result["catalyst_analysis"]["eligibility_gates"]["post_spike_not_dominant"] is False


def test_wyfi_type_survivable_financing_is_not_automatically_distress() -> None:
    c = candidate(symbol="WYFI", name="WhiteFiber Inc", prev=20.0, last=15.0, fundamental=fundamentals(shares_yoy=0.08, cash=0.35, liabilities=0.35, equity=0.65))
    news = [article(
        "WhiteFiber prices strategic registered direct offering at $19.00 per share",
        "The company will issue shares to fund expansion; no warrants or convertibles were announced.",
        symbol="WYFI",
    )]
    result = score_candidate(c, news, "C", ["dilution"])
    dilution = result["catalyst_analysis"]["dilution_analysis"]
    assert dilution["is_financing_event"] is True
    assert dilution["classification"] == "financing_benign"
    assert dilution["severity_score"] < 40.0
    assert dilution["hard_veto"] is False
    assert result["catalyst_analysis"]["cause_verification_status"] in {"VERIFIED", "PARTIALLY_VERIFIED"}


def test_sgly_type_deep_discount_and_share_expansion_materially_reduce_score() -> None:
    c = candidate(symbol="SGLY", name="Singularity Future Technology Ltd", prev=10.0, last=6.5, fundamental=fundamentals(shares_yoy=0.55, cash=0.08, liabilities=0.70, equity=0.30))
    news = [article(
        "Singularity Future prices $5.50 per share registered direct offering",
        "The financing includes 8 million common shares and warrants to purchase additional shares.",
        symbol="SGLY",
    )]
    result = score_candidate(c, news, "C", ["dilution"])
    dilution = result["catalyst_analysis"]["dilution_analysis"]
    assert dilution["classification"] in {"material_dilution", "capital_distress"}
    assert dilution["severity_score"] >= 40.0
    assert dilution["penalty"] > 0
    assert result["damage_risk"] >= 60.0
    assert result["verdict"] != "INVESTIGATE"
    assert result["catalyst_analysis"]["eligibility_gates"]["dilution_not_severe"] is False


def test_pfsa_type_reverse_split_plus_listing_stress_is_capital_distress_pass() -> None:
    c = candidate(symbol="PFSA", name="Profusa Inc", prev=4.0, last=2.8, fundamental=fundamentals(shares_yoy=0.45, cash=0.02, liabilities=0.92, equity=0.04))
    news = [article(
        "Profusa announces 1-for-20 reverse split after Nasdaq listing deficiency",
        "The company also seeks additional financing and faces minimum bid price compliance pressure.",
        symbol="PFSA",
    )]
    result = score_candidate(c, news, "C", ["delisting", "dilution"])
    dilution = result["catalyst_analysis"]["dilution_analysis"]
    assert dilution["reverse_split"] is True
    assert dilution["listing_stress"] is True
    assert dilution["classification"] == "capital_distress"
    assert result["verdict"] == "PASS"
    assert result["damage_risk"] >= 80.0
    assert result["catalyst_analysis"]["eligibility_gates"]["no_capital_distress"] is False


def test_lzb_type_verified_moderate_earnings_damage_with_strong_balance_sheet_is_not_structural_veto() -> None:
    c = candidate(symbol="LZB", name="La-Z-Boy Incorporated", prev=40.0, last=33.0, fundamental=fundamentals(cash=0.30, liabilities=0.38, equity=0.62, revenue_yoy=0.03, margin=0.07))
    news = [article(
        "La-Z-Boy reports quarterly sales $520M misses $550M estimate",
        "Management cited softer near-term demand but maintained a strong balance sheet and expects sequential improvement.",
        symbol="LZB",
    )]
    result = score_candidate(c, news, "C", ["earnings_guidance"])
    assert result["catalyst_analysis"]["cause_verification_status"] == "VERIFIED"
    assert result["hard_veto"] is False
    assert result["catalyst_analysis"]["economic_damage_class"] in {"MODERATE", "HIGH"}
    assert result["catalyst_analysis"]["event_profile"] != "capital_distress"


def test_unknown_cause_never_reaches_investigate_even_with_large_drop() -> None:
    c = candidate(symbol="RTB", name="RTB Digital Inc", prev=20.0, last=10.0)
    result = score_candidate(c, [], "U", [])
    assert result["catalyst_analysis"]["cause_verification_status"] == "UNVERIFIED"
    assert result["catalyst_score"] <= 30.0
    assert result["evidence_confidence"] <= 45.0
    assert result["final_score"] <= 50.0
    assert result["verdict"] == "PASS"
    assert result["catalyst_analysis"]["eligibility_gates"]["cause_verified_or_strong_partial"] is False


def test_ipst_type_generic_movers_listing_does_not_create_causal_confidence() -> None:
    c = candidate(symbol="IPST", name="Innovative Payment Solutions Inc", prev=12.0, last=8.5)
    generic = article(
        "12 Information Technology Stocks Moving In Thursday's Intraday Session",
        "IPST shares are among several names trading lower today.",
        source="Benzinga",
        symbol="IPST",
    )
    # Explicitly represent the multi-symbol market-movers metadata seen in production.
    generic["symbols"] = ["IPST", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    result = score_candidate(c, [generic], "U", [])
    assert result["catalyst_analysis"]["cause_verification_status"] == "UNVERIFIED"
    assert result["catalyst_analysis"]["news_relevance_trace"]["causal_article_count"] == 0
    assert result["verdict"] != "INVESTIGATE"


def test_high_evidence_confidence_does_not_make_verified_severe_dilution_attractive() -> None:
    c = candidate(symbol="DILU", name="Dilution Example Corp", prev=10.0, last=5.0, fundamental=fundamentals(shares_yoy=0.80, cash=0.015, liabilities=0.94, equity=0.03))
    news = [
        article("Dilution Example prices registered direct offering at $4.00 per share", "The deal includes 20 million shares, warrants and convertible securities.", source="Company IR", symbol="DILU", hours_before=1),
        article("Dilution Example launches deeply discounted equity financing", "The company disclosed the same financing terms and liquidity need.", source="Reuters", symbol="DILU", hours_before=1.5),
        article("Dilution Example files financing terms", "A regulatory filing confirms the offering and warrant overhang.", source="SEC filing", symbol="DILU", hours_before=2),
    ]
    result = score_candidate(c, news, "C", ["dilution"])
    assert result["evidence_confidence"] >= 60.0
    assert result["catalyst_analysis"]["dilution_analysis"]["severity_score"] >= 75.0
    assert result["verdict"] == "PASS"
    assert result["damage_risk"] >= 80.0


def test_financing_assessment_exposes_offer_discount_and_announced_share_count() -> None:
    c = candidate(prev=10.0, last=7.0, fundamental=fundamentals(shares_yoy=0.30))
    news = [article("Test Industrial prices offering at $6.00 per share", "The company will issue 12 million common shares and warrants.")]
    base = score_candidate(c, [article("Temporary production outage", "Operations resume tomorrow.")], "B", [])
    assessment = financing_assessment(c, news, base)
    assert assessment["discount_to_previous_close_pct"] == -40.0
    assert assessment["announced_new_shares"] == 12_000_000.0
    assert assessment["warrants"] is True


def test_price_path_assessment_does_not_penalize_a_stock_already_below_pre_spike_baseline_heavily() -> None:
    closes = [5.0] * 55 + [5.0, 5.5, 6.0, 8.0, 10.0]
    c = candidate(prev=10.0, last=4.5, history=history_from_closes(closes))
    base = score_candidate(c, [article("Temporary disruption", "Operations resume tomorrow.")], "B", [])
    spike = price_path_assessment(c, base)
    assert spike["post_spike_unwind"] is True
    assert spike["current_vs_pre_spike_baseline_pct"] < 0
    assert spike["penalty"] <= 4.0