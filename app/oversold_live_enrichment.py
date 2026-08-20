from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings
from app.oversold_features import MARKET_BENCHMARK, SECTOR_BENCHMARKS
from app.oversold_fundamentals import load_point_in_time_fundamentals

NY = ZoneInfo("America/New_York")
HISTORY_CALENDAR_DAYS = 125
BENCHMARK_CACHE_SECONDS = 90.0

_benchmark_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _runtime_fetch_enabled() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    raw = os.getenv("OVERSOLD_LIVE_ENRICHMENT_ENABLED", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _candidate_cutoff(candidate: dict[str, Any]) -> datetime:
    return (
        _parse_ts(candidate.get("evidence_cutoff"))
        or _parse_ts(candidate.get("latest_trade_ts"))
        or datetime.now(UTC)
    )


def _headers() -> dict[str, str]:
    return get_settings().alpaca_headers


def _fetch_history(symbols: list[str], cutoff: datetime) -> tuple[dict[str, list[dict[str, Any]]], int]:
    settings = get_settings()
    local_date = cutoff.astimezone(NY).date()
    start_date = local_date - timedelta(days=HISTORY_CALENDAR_DAYS)
    url = f"{settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/bars"
    params: dict[str, Any] = {
        "symbols": ",".join(symbols),
        "timeframe": "1Day",
        "start": start_date.isoformat(),
        "end": local_date.isoformat(),
        "feed": "sip",
        "adjustment": "split",
        "limit": 10000,
        "sort": "asc",
    }
    merged: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    requests = 0
    token: str | None = None
    with httpx.Client(headers=_headers(), timeout=httpx.Timeout(20.0, connect=8.0)) as client:
        for _ in range(3):
            if token:
                params["page_token"] = token
            response = client.get(url, params=params)
            requests += 1
            response.raise_for_status()
            payload = response.json() if response.content else {}
            bars = payload.get("bars") if isinstance(payload, dict) else None
            if isinstance(bars, dict):
                for symbol, rows in bars.items():
                    if symbol in merged and isinstance(rows, list):
                        merged[symbol].extend(row for row in rows if isinstance(row, dict))
            token = payload.get("next_page_token") if isinstance(payload, dict) else None
            if not token:
                break
    return merged, requests


def _fetch_benchmark_snapshots(symbols: list[str]) -> tuple[dict[str, dict[str, Any]], int]:
    now = time.monotonic()
    output: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for symbol in symbols:
        cached = _benchmark_cache.get(symbol)
        if cached and now - cached[0] <= BENCHMARK_CACHE_SECONDS:
            output[symbol] = cached[1]
        else:
            missing.append(symbol)
    if not missing:
        return output, 0

    settings = get_settings()
    url = f"{settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/snapshots"
    with httpx.Client(headers=_headers(), timeout=httpx.Timeout(12.0, connect=6.0)) as client:
        response = client.get(url, params={"symbols": ",".join(missing), "feed": "sip"})
        response.raise_for_status()
        payload = response.json() if response.content else {}
    snapshots = payload.get("snapshots") if isinstance(payload, dict) and isinstance(payload.get("snapshots"), dict) else payload
    if not isinstance(snapshots, dict):
        snapshots = {}
    for symbol in missing:
        snapshot = snapshots.get(symbol)
        if isinstance(snapshot, dict):
            _benchmark_cache[symbol] = (now, snapshot)
            output[symbol] = snapshot
    return output, 1


def load_runtime_enrichment(candidate: dict[str, Any], sector_hint: str | None) -> dict[str, Any]:
    cutoff = _candidate_cutoff(candidate)
    symbol = str(candidate.get("symbol") or "").upper()
    sector_benchmark = SECTOR_BENCHMARKS.get(str(sector_hint or ""))
    benchmark_symbols = [MARKET_BENCHMARK] + ([sector_benchmark] if sector_benchmark and sector_benchmark != MARKET_BENCHMARK else [])

    provided_history = candidate.get("history_bars")
    provided_context = candidate.get("benchmark_context")
    provided_fundamentals = candidate.get("fundamentals")
    if isinstance(provided_history, list) or isinstance(provided_context, dict) or isinstance(provided_fundamentals, dict):
        return {
            "cutoff": cutoff,
            "history_bars": provided_history if isinstance(provided_history, list) else [],
            "benchmark_context": provided_context if isinstance(provided_context, dict) else {},
            "fundamentals": provided_fundamentals if isinstance(provided_fundamentals, dict) else None,
            "history_requests": 0,
            "benchmark_requests": 0,
            "errors": [],
            "mode": "provided",
        }

    if not _runtime_fetch_enabled() or not symbol:
        return {
            "cutoff": cutoff,
            "history_bars": [],
            "benchmark_context": {},
            "fundamentals": None,
            "history_requests": 0,
            "benchmark_requests": 0,
            "errors": ["live_enrichment_disabled_or_symbol_missing"],
            "mode": "disabled",
        }

    errors: list[str] = []
    history_map: dict[str, list[dict[str, Any]]] = {}
    history_requests = 0
    try:
        history_symbols = [symbol] + [item for item in benchmark_symbols if item != symbol]
        history_map, history_requests = _fetch_history(history_symbols, cutoff)
    except Exception as exc:
        errors.append(f"history:{type(exc).__name__}:{str(exc)[:240]}")

    snapshots: dict[str, dict[str, Any]] = {}
    benchmark_requests = 0
    try:
        snapshots, benchmark_requests = _fetch_benchmark_snapshots(benchmark_symbols)
    except Exception as exc:
        errors.append(f"benchmarks:{type(exc).__name__}:{str(exc)[:240]}")

    benchmark_context: dict[str, dict[str, Any]] = {}
    for benchmark in benchmark_symbols:
        benchmark_context[benchmark] = {
            "snapshot": snapshots.get(benchmark) or {},
            "history_bars": history_map.get(benchmark) or [],
        }

    fundamentals: dict[str, Any] | None = None
    try:
        fundamentals = load_point_in_time_fundamentals([symbol], cutoff).get(symbol)
    except Exception as exc:
        errors.append(f"fundamentals:{type(exc).__name__}:{str(exc)[:240]}")

    return {
        "cutoff": cutoff,
        "history_bars": history_map.get(symbol) or [],
        "benchmark_context": benchmark_context,
        "fundamentals": fundamentals,
        "history_requests": history_requests,
        "benchmark_requests": benchmark_requests,
        "errors": errors,
        "mode": "live",
    }
