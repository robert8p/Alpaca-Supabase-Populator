from __future__ import annotations

import os
from datetime import UTC, datetime

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from app import oversold_scan_v33 as scan


def candidate(
    symbol: str,
    *,
    drop: float,
    dollar_volume: float,
    spread: float,
    catalyst_class: str = "U",
    flags: list[str] | None = None,
    headlines: int = 0,
) -> dict:
    return {
        "symbol": symbol,
        "drop_pct": drop,
        "prev_dollar_volume": dollar_volume,
        "spread_pct": spread,
        "prev_volume": 1_000_000,
        "raw_snapshot": {"dailyBar": {"v": 2_000_000}},
        "price_session_context": {"extended_hours_only": False},
        "catalyst_class": catalyst_class,
        "risk_flags": flags or [],
        "headline_count": headlines,
    }


def test_moderate_liquid_transient_candidate_outranks_extreme_illiquid_unknown() -> None:
    moderate = candidate(
        "GOOD",
        drop=-18.0,
        dollar_volume=25_000_000,
        spread=0.35,
        catalyst_class="B",
        headlines=2,
    )
    extreme = candidate(
        "BAD",
        drop=-58.0,
        dollar_volume=600_000,
        spread=4.5,
        catalyst_class="U",
        headlines=0,
    )
    assert scan._discovery_priority(moderate) > scan._discovery_priority(extreme)


def test_structural_risk_lowers_discovery_priority() -> None:
    neutral = candidate(
        "NEUT",
        drop=-20.0,
        dollar_volume=10_000_000,
        spread=0.5,
        catalyst_class="B",
        headlines=1,
    )
    structural = candidate(
        "STRU",
        drop=-30.0,
        dollar_volume=10_000_000,
        spread=0.5,
        catalyst_class="E",
        flags=["solvency", "delisting"],
        headlines=3,
    )
    assert scan._discovery_priority(neutral) > scan._discovery_priority(structural)


def test_price_session_classification() -> None:
    assert scan._price_session(datetime(2026, 8, 20, 12, 0, tzinfo=UTC)) == "pre_market"
    assert scan._price_session(datetime(2026, 8, 20, 15, 0, tzinfo=UTC)) == "regular"
    assert scan._price_session(datetime(2026, 8, 20, 21, 0, tzinfo=UTC)) == "after_hours"
