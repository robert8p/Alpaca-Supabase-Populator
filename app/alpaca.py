from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class AlpacaError(RuntimeError):
    pass


@dataclass
class RequestResult:
    data: Any
    request_id: str | None
    headers: dict[str, str]


class AsyncRateLimiter:
    """Spaces requests so aggregate traffic stays close to the selected RPM."""

    def __init__(self, requests_per_minute: int):
        self.interval = 60.0 / max(1, requests_per_minute)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                await asyncio.sleep(self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.interval


class AlpacaClient:
    def __init__(self, target_rpm: int, max_retries: int = 7, backoff_seconds: float = 1.5):
        settings = get_settings()
        self.settings = settings
        self.limiter = AsyncRateLimiter(target_rpm)
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.client = httpx.AsyncClient(
            headers=settings.alpaca_headers,
            timeout=httpx.Timeout(60.0, connect=20.0),
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "AlpacaClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> RequestResult:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            await self.limiter.wait()
            try:
                response = await self.client.get(url, params=params)
                request_id = response.headers.get("x-request-id")
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    reset = response.headers.get("x-ratelimit-reset")
                    delay = self.backoff_seconds * (2 ** min(attempt, 6))
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    elif reset:
                        try:
                            delay = max(delay, float(reset) - time.time())
                        except ValueError:
                            pass
                    await asyncio.sleep(max(0.5, delay) + random.random())
                    continue
                if response.status_code in {500, 502, 503, 504}:
                    await asyncio.sleep(self.backoff_seconds * (2 ** min(attempt, 6)) + random.random())
                    continue
                if response.status_code >= 400:
                    detail = response.text[:1000]
                    raise AlpacaError(f"Alpaca returned HTTP {response.status_code}: {detail}")
                return RequestResult(
                    data=response.json(),
                    request_id=request_id,
                    headers={k.lower(): v for k, v in response.headers.items()},
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(self.backoff_seconds * (2 ** min(attempt, 6)) + random.random())
        raise AlpacaError(f"Alpaca request failed after retries: {last_error}")

    async def list_assets(self) -> list[dict[str, Any]]:
        url = f"{self.settings.alpaca_trading_base_url.rstrip('/')}/v2/assets"
        result = await self._get(url, {"status": "active", "asset_class": "us_equity"})
        if not isinstance(result.data, list):
            raise AlpacaError("Unexpected assets response")
        return result.data

    async def get_clock(self) -> dict[str, Any]:
        url = f"{self.settings.alpaca_trading_base_url.rstrip('/')}/v2/clock"
        result = await self._get(url)
        if not isinstance(result.data, dict):
            raise AlpacaError("Unexpected clock response")
        return result.data

    async def fetch_latest_quotes(self, *, symbols: list[str], feed: str = "sip") -> RequestResult:
        url = f"{self.settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/quotes/latest"
        return await self._get(url, {"symbols": ",".join(symbols), "feed": feed})

    async def fetch_bars_page(
        self,
        *,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str,
        feed: str,
        adjustment: str,
        asof: str | None,
        limit: int,
        page_token: str | None,
    ) -> RequestResult:
        url = f"{self.settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/bars"
        params: dict[str, Any] = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "feed": feed,
            "adjustment": adjustment,
            "limit": limit,
            "sort": "asc",
        }
        if asof:
            params["asof"] = asof
        if page_token:
            params["page_token"] = page_token
        return await self._get(url, params)

    async def health(self) -> dict[str, Any]:
        assets = await self.list_assets()
        return {"ok": True, "asset_count": len(assets)}
