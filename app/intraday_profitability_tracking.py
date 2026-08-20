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
SETTLE_SECONDS = 180.0
TRACKING_VERSION = "ip-tracking-v3"


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


def _load_active_tracking_rows() -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM ip_selected_candidates
                WHERE status='tracking'
                   OR horizon_status='pending'
                ORDER BY market_close_at, selected_at
                LIMIT 2000
                """
            )
            rows = cur.fetchall()
        conn.rollback()
    return [dict(row) for row in rows]


def _mark_refresh_error(tracking_id: UUID, message: str) -> None:
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
                (message[:2_000], tracking_id),
            )
        conn.commit()


def _persist_outcome(
    tracking: dict[str, Any],
    *,
    entry_price: float | None,
    entry_at: datetime | None,
    favourable_price: float | None,
    favourable_at: datetime | None,
    adverse_price: float | None,
    adverse_at: datetime | None,
    horizon_price: float | None,
    horizon_at: datetime | None,
    horizon_matured: bool,
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
                SET entry_price=COALESCE(entry_price,%s),
                    entry_at=COALESCE(entry_at,%s),
                    favourable_extreme_price=%s,
                    favourable_extreme_at=%s,
                    adverse_extreme_price=%s,
                    adverse_extreme_at=%s,
                    horizon_price=COALESCE(%s,horizon_price),
                    horizon_at=COALESCE(%s,horizon_at),
                    horizon_status=CASE WHEN %s THEN 'matured' ELSE horizon_status END,
                    close_price=COALESCE(%s,close_price),
                    close_at=COALESCE(%s,close_at),
                    status=CASE WHEN %s THEN 'closed' ELSE 'tracking' END,
                    tracking_version=%s,
                    last_refreshed_at=now(),
                    refresh_error=NULL,
                    metadata=metadata || jsonb_build_object(
                        'last_bar_count', %s,
                        'tracking_method', 'all ranked candidates; full SIP minutes strictly after evidence cutoff',
                        'entry_definition', 'open of first complete regular-session minute after the evidence cutoff',
                        'horizon_definition', 'last complete one-minute close at or before the fixed 120-minute horizon',
                        'close_definition', 'last regular-session one-minute close before the recorded market close'
                    )
                WHERE id=%s
                """,
                (
                    entry_price,
                    entry_at,
                    favourable_price,
                    favourable_at,
                    adverse_price,
                    adverse_at,
                    horizon_price,
                    horizon_at,
                    horizon_matured,
                    close_price,
                    close_at,
                    closed,
                    TRACKING_VERSION,
                    bars_used,
                    tracking["id"],
                ),
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


def _tracking_outcome(
    tracking: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, Any]:
    scan_at = _as_utc(tracking.get("scan_at"))
    market_close = _as_utc(tracking.get("market_close_at"))
    horizon_end = _as_utc(tracking.get("horizon_end_at"))
    if scan_at is None or market_close is None:
        raise ValueError("Tracking row is missing scan or market-close timestamps")
    if horizon_end is None:
        horizon_end = min(scan_at + timedelta(minutes=120), market_close)

    first_full_minute = scan_at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    clean: list[tuple[datetime, dict[str, float]]] = []
    for bar in bars:
        timestamp = _as_utc(bar.get("t"))
        if timestamp is None or timestamp < first_full_minute or timestamp >= market_close:
            continue
        try:
            open_price = float(bar.get("o"))
            high = float(bar.get("h"))
            low = float(bar.get("l"))
            close = float(bar.get("c"))
        except (TypeError, ValueError):
            continue
        if min(open_price, high, low, close) <= 0 or high < low:
            continue
        clean.append((timestamp, {"o": open_price, "h": high, "l": low, "c": close}))
    clean.sort(key=lambda item: item[0])

    entry_price: float | None = None
    entry_at: datetime | None = None
    favourable_price: float | None = None
    favourable_at: datetime | None = None
    adverse_price: float | None = None
    adverse_at: datetime | None = None
    direction = str(tracking.get("direction") or "").upper()
    if clean:
        entry_at, entry_bar = clean[0]
        entry_price = entry_bar["o"]
        if direction == "LONG":
            favourable_at, favourable_bar = max(clean, key=lambda item: item[1]["h"])
            adverse_at, adverse_bar = min(clean, key=lambda item: item[1]["l"])
            favourable_price = favourable_bar["h"]
            adverse_price = adverse_bar["l"]
        elif direction == "SHORT":
            favourable_at, favourable_bar = min(clean, key=lambda item: item[1]["l"])
            adverse_at, adverse_bar = max(clean, key=lambda item: item[1]["h"])
            favourable_price = favourable_bar["l"]
            adverse_price = adverse_bar["h"]
        else:
            raise ValueError(f"Unsupported direction {direction!r}")

    horizon_rows = [item for item in clean if item[0] < horizon_end]
    horizon_has_matured = now >= horizon_end + timedelta(seconds=SETTLE_SECONDS)
    horizon_price: float | None = None
    horizon_at: datetime | None = None
    if horizon_has_matured and horizon_rows:
        horizon_at, horizon_bar = horizon_rows[-1]
        horizon_price = horizon_bar["c"]

    market_has_closed = now >= market_close + timedelta(seconds=SETTLE_SECONDS)
    close_price: float | None = None
    close_at: datetime | None = None
    closed = False
    if market_has_closed and clean:
        close_at, close_bar = clean[-1]
        close_price = close_bar["c"]
        closed = True

    return {
        "entry_price": entry_price,
        "entry_at": entry_at,
        "favourable_price": favourable_price,
        "favourable_at": favourable_at,
        "adverse_price": adverse_price,
        "adverse_at": adverse_at,
        "horizon_price": horizon_price,
        "horizon_at": horizon_at,
        "horizon_matured": horizon_has_matured and horizon_price is not None,
        "close_price": close_price,
        "close_at": close_at,
        "closed": closed,
        "bars_used": len(clean),
    }


async def refresh_candidate_outcomes() -> int:
    tracking_rows = await asyncio.to_thread(_load_active_tracking_rows)
    if not tracking_rows:
        return 0

    now = datetime.now(tz=UTC)
    refreshed = 0
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for tracking in tracking_rows:
        scan_at = _as_utc(tracking.get("scan_at"))
        market_close = _as_utc(tracking.get("market_close_at"))
        if scan_at is None or market_close is None:
            await asyncio.to_thread(_mark_refresh_error, tracking["id"], "Invalid scan/close timestamp")
            continue
        groups[(scan_at.date().isoformat(), market_close.isoformat())].append(tracking)

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
                logger.exception("Candidate SIP outcome refresh failed for %s", symbols)
                for tracking in group:
                    await asyncio.to_thread(_mark_refresh_error, tracking["id"], str(exc))
                continue

            for tracking in group:
                try:
                    outcome = _tracking_outcome(
                        tracking,
                        bars_by_symbol.get(str(tracking["symbol"]).upper(), []),
                        now=now,
                    )
                    await asyncio.to_thread(
                        _persist_outcome,
                        tracking,
                        entry_price=outcome["entry_price"],
                        entry_at=outcome["entry_at"],
                        favourable_price=outcome["favourable_price"],
                        favourable_at=outcome["favourable_at"],
                        adverse_price=outcome["adverse_price"],
                        adverse_at=outcome["adverse_at"],
                        horizon_price=outcome["horizon_price"],
                        horizon_at=outcome["horizon_at"],
                        horizon_matured=outcome["horizon_matured"],
                        close_price=outcome["close_price"],
                        close_at=outcome["close_at"],
                        closed=outcome["closed"],
                        bars_used=outcome["bars_used"],
                    )
                    refreshed += 1
                except Exception as exc:
                    logger.exception("Candidate outcome processing failed for %s", tracking.get("symbol"))
                    await asyncio.to_thread(_mark_refresh_error, tracking["id"], str(exc))
    return refreshed


# Backwards-compatible names used by earlier tests and runtime imports.
_selection_outcome = _tracking_outcome
refresh_selected_candidate_outcomes = refresh_candidate_outcomes


async def run_selected_candidate_tracker(stop_event: asyncio.Event) -> None:
    logger.info("Intraday all-candidate outcome tracker started (%s)", TRACKING_VERSION)
    while not stop_event.is_set():
        active_count = 0
        try:
            active_count = await refresh_candidate_outcomes()
            if active_count:
                logger.info("Refreshed %s intraday candidate outcome row(s)", active_count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Intraday candidate outcome tracker loop error")
        timeout = TRACKING_POLL_SECONDS if active_count else IDLE_POLL_SECONDS
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        except TimeoutError:
            pass
