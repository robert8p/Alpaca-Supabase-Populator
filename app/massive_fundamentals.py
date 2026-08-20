from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

import httpx

MASSIVE_BASE_URL = os.getenv("MASSIVE_BASE_URL", "https://api.massive.com").rstrip("/")
MASSIVE_API_KEY = (
    os.getenv("MASSIVE_API_KEY")
    or os.getenv("POLYGON_API_KEY")
    or os.getenv("MASSIVE_API_TOKEN")
)
MAX_CONCURRENCY = 8
TIMEOUT_SECONDS = 15.0


def configured() -> bool:
    return bool(MASSIVE_API_KEY)


def _first_result(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if isinstance(results, dict):
        return dict(results)
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return dict(results[0])
    return None


async def fetch_massive_fundamentals(
    symbols: list[str],
    *,
    cutoff: datetime,
) -> tuple[dict[str, dict[str, Any]], int]:
    """Fetch point-in-time reference and filed fundamental data when Massive is configured.

    Failure is deliberately non-fatal. Each symbol receives explicit availability/error
    metadata so the scorer can reduce confidence instead of treating missing fundamentals
    as favourable evidence.
    """
    unique_symbols = sorted({str(symbol).upper() for symbol in symbols if symbol})
    if not unique_symbols:
        return {}, 0
    if not MASSIVE_API_KEY:
        return {
            symbol: {
                "available": False,
                "provider": "massive",
                "reason": "api_key_unconfigured",
                "cutoff": cutoff.astimezone(UTC).isoformat(),
            }
            for symbol in unique_symbols
        }, 0

    cutoff_utc = cutoff.astimezone(UTC)
    cutoff_date = cutoff_utc.date().isoformat()
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    request_count = 0
    request_lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=8.0)) as client:
        async def get_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
            nonlocal request_count
            async with semaphore:
                query = dict(params)
                query["apiKey"] = MASSIVE_API_KEY
                async with request_lock:
                    request_count += 1
                response = await client.get(f"{MASSIVE_BASE_URL}{path}", params=query)
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}

        async def one(symbol: str) -> tuple[str, dict[str, Any]]:
            errors: list[str] = []
            detail: dict[str, Any] | None = None
            balance: dict[str, Any] | None = None
            cash_flow: dict[str, Any] | None = None

            async def detail_call() -> dict[str, Any] | None:
                payload = await get_json(
                    f"/v3/reference/tickers/{symbol}",
                    {"date": cutoff_date},
                )
                return _first_result(payload)

            async def balance_call() -> dict[str, Any] | None:
                payload = await get_json(
                    "/stocks/financials/v1/balance-sheets",
                    {
                        "tickers": symbol,
                        "timeframe": "quarterly",
                        "filing_date.lte": cutoff_date,
                        "sort": "filing_date.desc",
                        "limit": 1,
                    },
                )
                return _first_result(payload)

            async def cash_flow_call() -> dict[str, Any] | None:
                payload = await get_json(
                    "/stocks/financials/v1/cash-flow-statements",
                    {
                        "tickers": symbol,
                        "timeframe": "quarterly",
                        "filing_date.lte": cutoff_date,
                        "sort": "filing_date.desc",
                        "limit": 1,
                    },
                )
                return _first_result(payload)

            results = await asyncio.gather(
                detail_call(), balance_call(), cash_flow_call(), return_exceptions=True
            )
            names = ("ticker_details", "balance_sheet", "cash_flow")
            clean: list[dict[str, Any] | None] = []
            for name, result in zip(names, results, strict=True):
                if isinstance(result, Exception):
                    errors.append(f"{name}:{type(result).__name__}:{str(result)[:180]}")
                    clean.append(None)
                else:
                    clean.append(result)
            detail, balance, cash_flow = clean
            available = bool(detail or balance or cash_flow)
            return symbol, {
                "available": available,
                "provider": "massive",
                "cutoff": cutoff_utc.isoformat(),
                "ticker_details": detail or {},
                "balance_sheet": balance or {},
                "cash_flow": cash_flow or {},
                "errors": errors,
            }

        pairs = await asyncio.gather(*(one(symbol) for symbol in unique_symbols))
    return dict(pairs), request_count
