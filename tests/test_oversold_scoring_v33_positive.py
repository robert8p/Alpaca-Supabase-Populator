from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from app.oversold_scoring import score_candidate

SIGNAL_TS = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)


def _history(base: float = 10.0, days: int = 70) -> list[dict]:
    return [
        {
            "t": (SIGNAL_TS - timedelta(days=days-index)).isoformat().replace("+00:00", "Z"),
            "o": base,
            "h": base * 1.01,
            "l": base * 0.99,
            "c": base,
            "v": 4_000_000,
            "vw": base,
        }
        for index in range(days)
    ]


def _fundamentals() -> dict:
    return {
        "source": "sec_companyfacts_point_in_time_v1",
        "accession_number": "000-positive-control",
        "form": "10-Q",
        "available_from": "2026-07-01",
        "report_period_end": "2026-06-30",
        "age_calendar_days": 50,
        "metric_coverage_count": 18,
        "revenue_yoy": 0.12,
        "net_margin": 0.14,
        "net_margin_yoy_delta": 0.02,
        "operating_margin": 0.16,
        "gross_margin": 0.48,
        "eps_change_symmetric": 0.10,
        "net_income_change_symmetric": 0.10,
        "diluted_shares_yoy": 0.01,
        "cash_to_assets": 0.34,
        "liabilities_to_assets": 0.30,
        "equity_to_assets": 0.70,
        "debt_to_assets": 0.08,
        "current_ratio": 2.4,
        "cash_runway_months": 42.0,
        "market_cap": 1_200_000_000.0,
        "price_to_sales": 1.8,
        "source_definition_hash": "positive-control",
        "point_in_time_rule": "filed_before_cutoff",
    }


def _article(headline: str, summary: str, source: str, hours_before: float) -> dict:
    created_at = (SIGNAL_TS - timedelta(hours=hours_before)).isoformat().replace("+00:00", "Z")
    row = {
        "id": f"{source}:{headline}",
        "headline": headline,
        "summary": summary,
        "source": source,
        "symbols": ["TEMP"],
        "created_at": created_at,
        "url": "https://example.test/evidence",
    }
    if source == "SEC filing":
        row.update(
            {
                "is_primary_evidence": True,
                "source_kind": "sec_filing",
                "source_authority": "SEC EDGAR",
                "primary_evidence": {
                    "source_kind": "sec_filing",
                    "source_authority": "SEC EDGAR",
                    "external_id": "000-positive-control-8k",
                    "available_at": created_at,
                    "source_url": row["url"],
                    "summary": summary,
                    "content_excerpt": summary,
                    "content_hash": "a" * 64,
                    "metadata": {
                        "context_only": False,
                        "point_in_time_rule": "accepted before signal cutoff",
                    },
                },
            }
        )
    return row


def test_verified_transient_event_with_strong_finances_can_reach_investigate() -> None:
    previous = 10.0
    last = 7.2
    candidate = {
        "symbol": "TEMP",
        "name": "Temporary Event Corporation",
        "drop_pct": ((last / previous) - 1.0) * 100.0,
        "last_price": last,
        "prev_close": previous,
        "prev_volume": 5_000_000,
        "prev_dollar_volume": 50_000_000,
        "spread_pct": 0.25,
        "latest_trade_ts": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "evidence_cutoff": SIGNAL_TS.isoformat().replace("+00:00", "Z"),
        "raw_snapshot": {
            "prevDailyBar": {"o": previous, "h": 10.1, "l": 9.9, "c": previous, "v": 5_000_000},
            "dailyBar": {"o": 6.1, "h": 7.45, "l": 5.9, "c": last, "v": 15_000_000, "vw": 6.75},
        },
        "history_bars": _history(previous),
        "benchmark_context": {},
        "fundamentals": _fundamentals(),
        "price_session_context": {
            "price_session": "regular",
            "current_move_pct": -28.0,
            "regular_session_move_pct": -28.0,
            "extended_hours_only": False,
        },
        "_sec_prefetch_complete": True,
    }
    evidence = [
        _article(
            "Temporary Event reports short production outage; operations expected to resume tomorrow",
            "A localized equipment fault caused the interruption. Management expects delayed units to ship within the week and kept guidance unchanged.",
            "Company IR",
            3.0,
        ),
        _article(
            "Temporary Event files Form 8-K on temporary outage with no material financial impact",
            "The filing confirms the affected line is insured, customer contracts remain in force and no financing is required.",
            "SEC filing",
            2.5,
        ),
        _article(
            "Temporary Event says operations resumed after brief equipment fault",
            "Operations resumed, guidance remains unchanged and management reported no customer loss.",
            "Reuters",
            1.0,
        ),
    ]

    result = score_candidate(candidate, evidence, "B", [])
    analysis = result["catalyst_analysis"]

    assert analysis["cause_verification_status"] == "VERIFIED"
    assert analysis["fundamental_evidence_state"] == "VERIFIED_PRIMARY"
    assert analysis["overreaction_quality_score"] >= 60.0
    assert analysis["survivability_score"] >= 55.0
    assert analysis["three_session_fit_score"] >= 55.0
    assert analysis["tail_risk_score"] <= 60.0
    assert analysis["primary_causal_evidence_count"] >= 1
    assert analysis["independent_causal_source_count"] >= 2
    assert result["final_score"] >= 72.0
    assert result["verdict"] == "INVESTIGATE"
    assert all(analysis["eligibility_gates"].values())
