from __future__ import annotations

import logging
import os
from datetime import datetime

from app.alpaca import AlpacaClient
from app.db import connection

logger = logging.getLogger(__name__)

AUDIT_SYMBOLS = ["DIA", "GLD", "HYG", "QQQ", "SPY", "TLT", "USO"]
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _enabled() -> bool:
    return os.getenv("BLANKCANVAS_ADJUSTED_DAILY_AUDIT", "").strip().lower() in _TRUE_VALUES


def _bar_date(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _normalise_rows(payload: dict, adjustment: str) -> list[tuple]:
    rows: list[tuple] = []
    bars = payload.get("bars") or {}
    if not isinstance(bars, dict):
        raise RuntimeError("Unexpected Alpaca multi-symbol bars payload")
    for symbol, symbol_bars in bars.items():
        if symbol not in AUDIT_SYMBOLS or not isinstance(symbol_bars, list):
            continue
        for bar in symbol_bars:
            rows.append(
                (
                    symbol,
                    _bar_date(str(bar["t"])),
                    adjustment,
                    bar.get("o"),
                    bar.get("h"),
                    bar.get("l"),
                    bar.get("c"),
                    int(bar["v"]) if bar.get("v") is not None else None,
                    int(bar["n"]) if bar.get("n") is not None else None,
                    bar.get("vw"),
                    "alpaca_sip",
                )
            )
    return rows


def _upsert_rows(rows: list[tuple]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO public.blankcanvas_adjusted_daily_bars_v1(
            symbol,bar_date,adjustment,open,high,low,close,volume,trade_count,vwap,source,fetched_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT(symbol,bar_date,adjustment) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume,
            trade_count=excluded.trade_count,
            vwap=excluded.vwap,
            source=excluded.source,
            fetched_at=now()
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    return len(rows)


async def run_adjusted_daily_audit_once() -> int:
    """Fetch raw and fully adjusted Alpaca daily bars for the fixed seven-ETF audit universe.

    The routine is inert unless BLANKCANVAS_ADJUSTED_DAILY_AUDIT is enabled and writes only
    to public.blankcanvas_adjusted_daily_bars_v1. It never modifies rd_bars or production
    research features.
    """
    if not _enabled():
        return 0

    start_date = os.getenv("BLANKCANVAS_ADJUSTED_DAILY_START", "2004-01-01")
    end_date = os.getenv("BLANKCANVAS_ADJUSTED_DAILY_END", "2026-08-12")
    start = f"{start_date}T00:00:00Z"
    end = f"{end_date}T00:00:00Z"
    total = 0

    logger.warning(
        "Starting one-off adjusted daily audit for %s from %s to %s",
        ",".join(AUDIT_SYMBOLS),
        start_date,
        end_date,
    )

    async with AlpacaClient(target_rpm=600, max_retries=7, backoff_seconds=1.0) as client:
        for adjustment in ("raw", "all"):
            page_token: str | None = None
            while True:
                result = await client.fetch_bars_page(
                    symbols=AUDIT_SYMBOLS,
                    timeframe="1Day",
                    start=start,
                    end=end,
                    feed="sip",
                    adjustment=adjustment,
                    asof=None,
                    limit=10000,
                    page_token=page_token,
                )
                payload = result.data
                if not isinstance(payload, dict):
                    raise RuntimeError("Unexpected Alpaca bars response type")
                rows = _normalise_rows(payload, adjustment)
                total += _upsert_rows(rows)
                page_token = payload.get("next_page_token")
                if not page_token:
                    break

    logger.warning("Adjusted daily audit completed with %s row upserts", total)
    return total
