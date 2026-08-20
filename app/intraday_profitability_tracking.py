from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.alpaca import AlpacaClient
from app.db import connection

logger = logging.getLogger(__name__)
TRACKING_POLL_SECONDS = 30.0
IDLE_POLL_SECONDS = 120.0
CLOSE_SETTLE_SECONDS = 180.0


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _load_active_selections() -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM ip_selected_candidates
                WHERE status='tracking'
                ORDER BY market_close_at, selected_at
                LIMIT 500
                """
            )
            rows = cur.fetchall()
        conn.rollback()
    return [dict(row) for row in rows]


def _mark_refresh_error(selection_id: UUID, message: str) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ip_selected_candidates
                SET refresh_error=%s,
                    last_refreshed_at=now(),
                    metadata=metadata || jsonb_build_object('last_refresh_failed_at', now())
                WHERE id=%s
                """,
                (message[:2_000], selection_id),
            )
        conn.commit()


def _persist_outcome(
    selection: dict[str, Any],
    *,
    favourable_price: float | None,
    favourable_at: datetime | None,
    close_price: float | None,
    close_at: datetime | None,
    closed: bool,
    bars_used: int,
) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ip_selected_candidates
                SET favourable_extreme_price=%s,
                    favourable_extreme_at=%s,
                    close_price=COALESCE(%s, close_price),
                    close_at=COALESCE(%s, close_at),
                    status=CASE WHEN %s THEN 'closed' ELSE 'tracking' END,
                    last_refreshed_at=now(),
                    refresh_error=NULL,
                    metadata=metadata || jsonb_build_object(
                        'last_bar_count', %s,
                        'tracking_method', 'full-minute SIP bars strictly after scan cutoff',
                        'close_definition', 'last regular-session one-minute close at or before market close'
                    )
                WHERE id=%s
                """,
                (favourable_price, favourable_at, close_price, close_at, closed, bars_used, selection["id"]),
            )
        conn.commit()


async def _fetch_bars(
    client: AlpacaClient,
    *,
    symbols: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, list[dict[str, Any]]]:
    collected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    page_token: str | None = None
    while True:
        result = await client.fetch_bars_page(
            symbols=symbols,
            timeframe="1Min",
            start=start.isoformat().replace("+00:00", "Z"),
            end=end.isoformat().replace("+00:00", "Z"),
            feed="sip",
            adjustment="raw",
            asof=None,
            limit=10_000,
            page_token=page_token,
        )
        payload = result.data if isinstance(result.data, dict) else {}
        raw = payload.get("bars") or {}
        if isinstance(raw, dict):
            for symbol, rows in raw.items():
                if isinstance(rows, list):
                    collected[str(symbol).upper()].extend(row for row in rows if isinstance(row, dict))
        page_token = payload.get("next_page_token") or payload.get("nextPageToken")
        if not page_token:
            break
    return dict(collected)


def _selection_outcome(
    selection: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    now: datetime,
) -> tuple[float | None, datetime | None, float | None, datetime | None, bool, int]:
    scan_at = _as_utc(selection.get("scan_at"))
    market_close = _as_utc(selection.get("market_close_at"))
    if scan_at is None or market_close is None:
        raise ValueError("Selection is missing scan or market-close timestamps")

    first_full_minute = scan_at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    clean: list[tuple[datetime, dict[str, Any]]] = []
    for bar in bars:
        timestamp = _as_utc(bar.get("t"))
        if timestamp is None or timestamp < first_full_minute or timestamp >= market_close:
            continue
        try:
            high = float(bar.get("h"))
            low = float(bar.get("l"))
            close = float(bar.get("c"))
        except (TypeError, ValueError):
            continue
        if high <= 0 or low <= 0 or close <= 0 or high < low:
            continue
        clean.append((timestamp, {"h": high, "l": low, "c": close}))
    clean.sort(key=lambda item: item[0])

    direction = str(selection.get("direction") or "").upper()
    favourable_price: float | None = None
    favourable_at: datetime | None = None
    if clean:
        if direction == "LONG":
            favourable_at, favourable_bar = max(clean, key=lambda item: item[1]["h"])
            favourable_price = favourable_bar["h"]
        elif direction == "SHORT":
            favourable_at, favourable_bar = min(clean, key=lambda item: item[1]["l"])
            favourable_price = favourable_bar["l"]
        else:
            raise ValueError(f"Unsupported direction {direction!r}")

    market_has_closed = now >= market_close + timedelta(seconds=CLOSE_SETTLE_SECONDS)
    close_price: float | None = None
    close_at: datetime | None = None
    closed = False
    if market_has_closed and clean:
        close_at, close_bar = clean[-1]
        close_price = close_bar["c"]
        closed = True
    return favourable_price, favourable_at, close_price, close_at, closed, len(clean)


async def refresh_selected_candidate_outcomes() -> int:
    selections = await asyncio.to_thread(_load_active_selections)
    if not selections:
        return 0

    now = datetime.now(tz=UTC)
    refreshed = 0
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for selection in selections:
        scan_at = _as_utc(selection.get("scan_at"))
        market_close = _as_utc(selection.get("market_close_at"))
        if scan_at is None or market_close is None:
            await asyncio.to_thread(_mark_refresh_error, selection["id"], "Invalid scan/close timestamp")
            continue
        groups[(scan_at.date().isoformat(), market_close.isoformat())].append(selection)

    async with AlpacaClient(target_rpm=900, max_retries=4, backoff_seconds=1.0) as client:
        for group in groups.values():
            symbols = sorted({str(row["symbol"]).upper() for row in group})
            starts = [_as_utc(row["scan_at"]) for row in group]
            closes = [_as_utc(row["market_close_at"]) for row in group]
            group_start = min(value for value in starts if value is not None)
            group_close = max(value for value in closes if value is not None)
            request_end = min(now, group_close + timedelta(minutes=1))
            if request_end <= group_start:
                continue
            try:
                bars_by_symbol = await _fetch_bars(client, symbols=symbols, start=group_start, end=request_end)
            except Exception as exc:
                logger.exception("Selected-candidate SIP bar refresh failed for %s", symbols)
                for selection in group:
                    await asyncio.to_thread(_mark_refresh_error, selection["id"], str(exc))
                continue

            for selection in group:
                try:
                    outcome = _selection_outcome(selection, bars_by_symbol.get(str(selection["symbol"]).upper(), []), now=now)
                    await asyncio.to_thread(
                        _persist_outcome,
                        selection,
                        favourable_price=outcome[0],
                        favourable_at=outcome[1],
                        close_price=outcome[2],
                        close_at=outcome[3],
                        closed=outcome[4],
                        bars_used=outcome[5],
                    )
                    refreshed += 1
                except Exception as exc:
                    logger.exception("Selected-candidate outcome processing failed for %s", selection.get("symbol"))
                    await asyncio.to_thread(_mark_refresh_error, selection["id"], str(exc))
    return refreshed


async def run_selected_candidate_tracker(stop_event: asyncio.Event) -> None:
    logger.info("Intraday selected-candidate outcome tracker started")
    while not stop_event.is_set():
        active_count = 0
        try:
            active_count = await refresh_selected_candidate_outcomes()
            if active_count:
                logger.info("Refreshed %s selected intraday candidate outcome(s)", active_count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Intraday selected-candidate tracker loop error")
        timeout = TRACKING_POLL_SECONDS if active_count else IDLE_POLL_SECONDS
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        except TimeoutError:
            pass
