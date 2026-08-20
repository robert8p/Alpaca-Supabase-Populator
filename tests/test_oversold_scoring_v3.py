from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.oversold_features import technical_features
from app.oversold_scoring import score_candidate


SIGNAL_TS = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)


def history_bars(*, base=15.0, days=60, volume=5_000_000):
    rows = []
    for index in range(days):
        ts = SIGNAL_TS - timedelta(days=days - index)
        cycle = ((index % 7) - 3) * 0.018
        close = base + cycle
        rows.append(
            {
                "t": ts.isoformat().replace("+00:00", "Z"),
                "o": close - 0.03,
                "h": close + 0.12,
                "l": close - 0.12,
                "c": close,
                "v": volume + (index % 5) * 60_000,
                "vw": close,
            }
        )
    rows[-1]["c"] = base
    rows[-1]["o"] = base - 0.02
    rows[-1]["h"] = base + 0.10
    rows[-1]["l"] = base - 0.10
    return rows


def benchmark_snapshot(prev_close, last):
    return {
        "prevDailyBar": {"c": prev_close, "o": prev_close * 0.998, "h": prev_close * 1.003, "l": prev_close * 0.995, "v": 10_000_000},
        "dailyBar": {"o": prev_close * 0.997, "h": prev_close * 1.001, "l": last * 0.998, "c": last, "v": 8_000_000},
        "latestTrade": {"p": last, "t": SIGNAL_TS.isoformat().replace("+00:00", "Z")},
    }


def strong_fundamentals():
    return {
        "source": "research_pid_fundamental.filing_events_v1",
        "accession_number": "000-test-strong",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 49,
        "metric_coverage_count": 8,
        "revenue_yoy": 0.08,
        "net_margin": 0.08,
        "net_margin_yoy_delta": 0.01,
        "operating_margin": 0.10,
        "gross_margin": 0.48,
        "eps_change_symmetric": 0.12,
        "net_income_change_symmetric": 0.10,
        "diluted_shares_yoy": 0.02,
        "cash_to_assets": 0.24,
        "liabilities_to_assets": 0.52,
        "equity_to_assets": 0.48,
        "source_definition_hash": "strong",
        "point_in_time_rule": "available_from_strictly_before_signal_date",
    }


def weak_fundamentals():
    return {
        "source": "research_pid_fundamental.filing_events_v1",
        "accession_number": "000-test-weak",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 49,
        "metric_coverage_count": 8,
        "revenue_yoy": -0.40,
        "net_margin": -0.30,
        "net_margin_yoy_delta": -0.18,
        "operating_margin": -0.32,
        "gross_margin": 0.08,
        "eps_change_symmetric": -0.70,
        "net_income_change_symmetric": -0.75,
        "diluted_shares_yoy": 0.65,
        "cash_to_assets": 0.02,
        "liabilities_to_assets": 0.95,
        "equity_to_assets": 0.02,
        "source_definition_hash": "weak",
        "point_in_time_rule": "available_from_strictly_before_signal_date",
    }


def candidate(*, drop=-25.0, last=11.25, fundamentals=None, include_fundamentals=True):
    previous = 15.0
    output = {
        "symbol": "TEST",
        "name": "Test Industrial Company",
        "drop_pct": drop,
        "last_price": last,
        "prev_close": previous,
        "prev_volume": 5_000_000,
        "prev_dollar_volume": 75_000_000,
        "spread_pct": 0.35,
        "latest_trade_ts": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "evidence_cutoff": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "raw_snapshot": {
            "prevDailyBar": {"o": 14.9, "h": 15.15, "l": 14.8, "c": previous, "v": 5_000_000},
            "dailyBar": {"o": 9.70, "h": 11.55, "l": 9.20, "c": last, "v": 14_000_000, "vw": 10.65},
        },
        "history_bars": history_bars(base=previous),
        "benchmark_context": {
            "SPY": {"snapshot": benchmark_snapshot(600.0, 595.0), "history_bars": history_bars(base=600.0, volume=20_000_000)},
            "XLI": {"snapshot": benchmark_snapshot(150.0, 148.8), "history_bars": history_bars(base=150.0, volume=8_000_000)},
        },
    }
    if include_fundamentals:
        output["fundamentals"] = fundamentals if fundamentals is not None else strong_fundamentals()
    return output


def article(headline, summary="", source="Company IR", hours_before=2):
    published = SIGNAL_TS - timedelta(hours=hours_before)
    return {
        "id": f"{source}:{headline}:{hours_before}",
        "headline": headline,
        "summary": summary,
        "source": source,
        "created_at": published.isoformat().replace("+00:00", "Z"),
        "url": "https://example.test/item",
    }


def test_v3_uses_volatility_and_history_not_drop_magnitude_alone():
    c = candidate()
    tech = technical_features(c, "industrials")
    assert tech["history_count"] >= 50
    assert tech["shock_z"] is not None and tech["shock_z"] > 3
    assert tech["rsi14"] is not None and tech["rsi14"] < 30
    assert tech["sma20_distance_pct"] is not None and tech["sma20_distance_pct"] < -20
    assert tech["relative_volume20"] is not None and tech["relative_volume20"] > 2
    assert tech["market_relative_move_pct"] is not None and tech["market_relative_move_pct"] < -20
    result = score_candidate(c, [article("Temporary production outage", "Operations resume tomorrow after a short-term technical issue.")], "C", [])
    assert result["setup_score"] >= 75
    assert result["calculation_trace"]["setup"]["technical_features"]["shock_z"] > 3


def test_same_scanner_class_no_longer_collapses_different_catalysts():
    c = candidate()
    temporary = score_candidate(
        c,
        [article("Temporary production outage", "Operations resume tomorrow after a short-term technical issue.")],
        "C",
        [],
    )
    guidance = score_candidate(
        c,
        [article("Company lowers full-year guidance", "Management cuts guidance after weaker core demand and a revenue miss.")],
        "C",
        ["earnings_guidance"],
    )
    assert temporary["catalyst_analysis"]["event_profile"] != guidance["catalyst_analysis"]["event_profile"]
    assert temporary["catalyst_score"] >= guidance["catalyst_score"] + 25
    assert guidance["damage_risk"] >= temporary["damage_risk"] + 30
    assert temporary["final_score"] > guidance["final_score"]


def test_independent_sources_raise_confidence_but_duplicate_source_count_does_not():
    c = candidate()
    repeated = [article("Temporary production outage", "Operations resume tomorrow.", "Reuters", hours_before=2 + index / 10) for index in range(8)]
    independent = [
        article("Temporary production outage", "Operations resume tomorrow.", "Reuters", 2),
        article("Company confirms temporary production outage", "Operations resume tomorrow.", "Company IR", 2.5),
        article("Plant restart expected tomorrow", "The outage was described as temporary.", "Dow Jones", 3),
    ]
    repeated_result = score_candidate(c, repeated, "C", [])
    independent_result = score_candidate(c, independent, "C", [])
    repeated_trace = repeated_result["catalyst_analysis"]["evidence_quality_trace"]
    independent_trace = independent_result["catalyst_analysis"]["evidence_quality_trace"]
    assert repeated_trace["independent_source_count"] == 1
    assert independent_trace["independent_source_count"] == 3
    assert independent_result["evidence_confidence"] > repeated_result["evidence_confidence"]


def test_point_in_time_fundamentals_materially_discriminate_resilience():
    news = [article("Temporary production outage", "Operations resume tomorrow after a technical issue.")]
    strong = score_candidate(candidate(fundamentals=strong_fundamentals()), news, "C", [])
    weak = score_candidate(candidate(fundamentals=weak_fundamentals()), news, "C", [])
    assert strong["resilience_score"] >= weak["resilience_score"] + 45
    assert strong["catalyst_analysis"]["fundamental_trace"]["available"] is True
    assert weak["catalyst_analysis"]["fundamental_trace"]["contributions"]["diluted_shares_yoy"] <= -15
    assert strong["final_score"] > weak["final_score"]


def test_missing_fundamentals_are_uncertainty_not_favourable_evidence():
    news = [article("Temporary production outage", "Operations resume tomorrow after a technical issue.")]
    known = score_candidate(candidate(fundamentals=strong_fundamentals()), news, "C", [])
    missing = score_candidate(candidate(include_fundamentals=False), news, "C", [])
    assert missing["resilience_score"] < known["resilience_score"]
    assert missing["evidence_confidence"] < known["evidence_confidence"]
    assert "point_in_time_fundamentals" in missing["missing_inputs"]
    assert missing["catalyst_analysis"]["fundamental_trace"]["available"] is False


def test_primary_endpoint_failure_is_much_worse_than_secondary_miss_with_primary_intact():
    c = candidate()
    failed = score_candidate(
        c,
        [article("Phase 3 study failed primary endpoint", "The pivotal trial did not meet the primary endpoint.")],
        "C",
        ["clinical_regulatory"],
    )
    secondary = score_candidate(
        c,
        [article("Phase 2 study misses secondary endpoint", "The study met the primary endpoint but one secondary endpoint was not met.")],
        "C",
        ["clinical_regulatory"],
    )
    assert failed["hard_veto"] is True
    assert failed["damage_risk"] >= 90
    assert secondary["hard_veto"] is False
    assert secondary["damage_risk"] <= 60
    assert secondary["catalyst_score"] > failed["catalyst_score"]


def test_signal_day_bar_is_excluded_from_historical_technicals():
    c = candidate()
    normal = technical_features(c, "industrials")
    c["history_bars"] = list(c["history_bars"]) + [
        {
            "t": "2026-08-19T14:00:00Z",
            "o": 1000,
            "h": 1200,
            "l": 1,
            "c": 1000,
            "v": 999_999_999,
        }
    ]
    contaminated = technical_features(c, "industrials")
    assert contaminated["history_count"] == normal["history_count"]
    assert contaminated["sma20"] == normal["sma20"]
    assert contaminated["shock_z"] == normal["shock_z"]
