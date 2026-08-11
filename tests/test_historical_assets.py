from __future__ import annotations

import asyncio
from datetime import date

from app.alpaca import AlpacaClient
from app.models import JobConfig
from app.planner import resolve_universe


class FakeAlpacaClient(AlpacaClient):
    def __init__(self):
        pass

    async def list_assets(self, *, status: str = "active"):
        if status == "inactive":
            return [
                {"symbol": "OLD", "status": "inactive", "class": "us_equity", "exchange": "NYSE", "tradable": False},
                {"symbol": "SAME", "status": "inactive", "class": "us_equity", "exchange": "NASDAQ", "tradable": False},
            ]
        return [
            {"symbol": "AAPL", "status": "active", "class": "us_equity", "exchange": "NASDAQ", "tradable": True},
            {"symbol": "SAME", "status": "active", "class": "us_equity", "exchange": "NASDAQ", "tradable": True},
        ]


def _config(mode: str, *, tradable_only: bool) -> JobConfig:
    return JobConfig.model_validate({
        "name": "Historical asset test",
        "start_date": date(2025, 4, 11),
        "end_date": date(2025, 5, 2),
        "timeframes": ["1Min"],
        "feed": "sip",
        "adjustment": "raw",
        "asof": date(2025, 5, 4),
        "universe": {
            "mode": mode,
            "symbols": [],
            "exchanges": ["NYSE", "NASDAQ"],
            "tradable_only": tradable_only,
            "exclude_regex": "[/]",
        },
        "session": {"mode": "regular", "weekdays_only": True},
        "storage": {"conflict_policy": "skip", "generate_daily_features": False, "feature_session": "regular"},
    })


def test_all_known_union_retains_inactive_symbols_and_prefers_active_duplicate():
    client = FakeAlpacaClient()
    assets = asyncio.run(client.list_known_assets())
    by_symbol = {row["symbol"]: row for row in assets}
    assert set(by_symbol) == {"AAPL", "OLD", "SAME"}
    assert by_symbol["OLD"]["status"] == "inactive"
    assert by_symbol["SAME"]["status"] == "active"


def test_resolve_all_known_can_source_inactive_history_without_current_tradable_filter():
    client = FakeAlpacaClient()
    symbols, assets = asyncio.run(resolve_universe(_config("all_known", tradable_only=False), client))
    assert symbols == ["AAPL", "OLD", "SAME"]
    assert any(row["status"] == "inactive" for row in assets)


def test_inactive_known_sources_only_inactive_assets():
    client = FakeAlpacaClient()
    symbols, assets = asyncio.run(resolve_universe(_config("inactive_known", tradable_only=False), client))
    assert symbols == ["OLD", "SAME"]
    assert all(row["status"] == "inactive" for row in assets)


def test_all_active_behavior_is_unchanged():
    client = FakeAlpacaClient()
    symbols, _ = asyncio.run(resolve_universe(_config("all_active", tradable_only=True), client))
    assert symbols == ["AAPL", "SAME"]
