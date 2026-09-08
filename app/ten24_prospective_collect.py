from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection

logger = logging.getLogger(__name__)
SCHEMA = "research_ten24_wide_certrep_20260908"


def _claim_request() -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH picked AS (
                    SELECT request_id
                    FROM {SCHEMA}.collection_requests
                    WHERE status='queued'
                    ORDER BY requested_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE {SCHEMA}.collection_requests r
                SET status='running', claimed_at=now(), error=NULL
                FROM picked
                WHERE r.request_id=picked.request_id
                RETURNING r.*
                """
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def _population() -> tuple[list[str], dict[str, str]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT symbol,alpaca_asset_id::text AS asset_id
                FROM {SCHEMA}.population
                WHERE identity_state='PROSPECTIVE_IDENTITY_CERTIFIED'
                  AND classification_state='COMMON_STOCK_KNOWN_PRE_BOUNDARY'
                ORDER BY symbol
                """
            )
            rows = cur.fetchall()
        conn.rollback()
    symbols = [str(r["symbol"]) for r in rows]
    return symbols, {str(r["symbol"]): str(r["asset_id"]) for r in rows}


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _insert_page(bars_payload: dict[str, list[dict[str, Any]]], asset_ids: dict[str, str]) -> int:
    rows: list[tuple[Any, ...]] = []
    for symbol, bars in bars_payload.items():
        asset_id = asset_ids.get(str(symbol))
        if not asset_id:
            continue
        for b in bars:
            rows.append(
                (
                    "alpaca",
                    asset_id,
                    _parse_ts(str(b["t"])),
                    b.get("o"), b.get("h"), b.get("l"), b.get("c"),
                    float(b.get("v") or 0),
                    b.get("n"), b.get("vw"),
                    "sip", "raw",
                )
            )
    if not rows:
        return 0
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='30min'")
            cur.execute(
                """
                CREATE TEMP TABLE ten24_page(
                    provider text, instrument_id uuid, ts timestamptz,
                    open double precision, high double precision, low double precision,
                    close double precision, volume double precision,
                    trade_count bigint, vwap double precision,
                    source_feed text, adjustment text
                ) ON COMMIT DROP
                """
            )
            with cur.copy(
                "COPY ten24_page(provider,instrument_id,ts,open,high,low,close,volume,trade_count,vwap,source_feed,adjustment) FROM STDIN"
            ) as copy:
                for row in rows:
                    copy.write_row(row)
            cur.execute(
                """
                INSERT INTO prospective.alpaca_bars_1m(
                    provider,instrument_id,ts,open,high,low,close,volume,
                    trade_count,vwap,source_feed,adjustment
                )
                SELECT provider,instrument_id,ts,open,high,low,close,volume,
                       trade_count,vwap,source_feed,adjustment
                FROM ten24_page
                ON CONFLICT(provider,instrument_id,ts) DO NOTHING
                """
            )
            inserted = max(int(cur.rowcount or 0), 0)
        conn.commit()
    return inserted


def _checkpoint(request_id: str, *, rows_inserted: int, api_requests: int, details: dict[str, Any] | None = None) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {SCHEMA}.collection_requests
                SET rows_inserted=%s, api_requests=%s,
                    details=details || %s::jsonb
                WHERE request_id=%s::uuid
                """,
                (rows_inserted, api_requests, Jsonb(details or {}), request_id),
            )
        conn.commit()


def _finish(request_id: str, *, status: str, rows_inserted: int, api_requests: int, error: str | None, details: dict[str, Any]) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {SCHEMA}.collection_requests
                SET status=%s, completed_at=now(), rows_inserted=%s, api_requests=%s,
                    error=%s, details=details || %s::jsonb
                WHERE request_id=%s::uuid
                """,
                (status, rows_inserted, api_requests, error, Jsonb(details), request_id),
            )
        conn.commit()


def _store_source_audit(key: str, status: str, details: dict[str, Any]) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {SCHEMA}.source_audit(audit_key,status,details)
                VALUES (%s,%s,%s)
                ON CONFLICT(audit_key) DO UPDATE
                SET status=excluded.status,details=excluded.details,checked_at=now()
                """,
                (key, status, Jsonb(details)),
            )
        conn.commit()


def _corporate_action_summary(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    symbols: set[str] = set()
    rows = 0
    for payload in payloads:
        container = payload.get("corporate_actions") if isinstance(payload, dict) else None
        if isinstance(container, dict):
            for action_type, items in container.items():
                if not isinstance(items, list):
                    continue
                type_counts[str(action_type)] = type_counts.get(str(action_type), 0) + len(items)
                rows += len(items)
                for item in items:
                    if isinstance(item, dict):
                        symbol = item.get("symbol") or item.get("old_symbol") or item.get("new_symbol")
                        if symbol:
                            symbols.add(str(symbol))
    return {"rows": rows, "type_counts": type_counts, "symbols": sorted(symbols)}


async def run_ten24_prospective_collection_once() -> None:
    request = await asyncio.to_thread(_claim_request)
    if not request:
        return
    request_id = str(request["request_id"])
    rows_inserted = 0
    api_requests = 0
    symbols, asset_ids = await asyncio.to_thread(_population)
    if len(symbols) != int(request["symbol_count"]):
        error = f"Population mismatch: request={request['symbol_count']} frozen={len(symbols)}"
        await asyncio.to_thread(_finish, request_id, status="failed", rows_inserted=0, api_requests=0, error=error, details={})
        logger.error("TEN24 collection %s failed: %s", request_id, error)
        return

    start_date: date = request["start_date"]
    end_date: date = request["end_date"]
    calendar_rows: list[dict[str, Any]] = []
    ca_payloads: list[dict[str, Any]] = []
    try:
        async with AlpacaClient(target_rpm=1200, max_retries=7, backoff_seconds=1.5) as client:
            calendar_rows = await client.get_calendar(start=start_date.isoformat(), end=end_date.isoformat())
            api_requests += 1
            trading_dates = {
                date.fromisoformat(str(row["date"]))
                for row in calendar_rows
                if isinstance(row, dict) and row.get("date")
            }
            batches = [symbols[i:i + 100] for i in range(0, len(symbols), 100)]
            for day_offset in range((end_date - start_date).days + 1):
                day = start_date + timedelta(days=day_offset)
                if day not in trading_dates:
                    continue
                start = datetime(day.year, day.month, day.day, tzinfo=UTC)
                end = start + timedelta(days=1)
                for batch_idx, batch in enumerate(batches):
                    token: str | None = None
                    while True:
                        result = await client.fetch_bars_page(
                            symbols=batch,
                            timeframe="1Min",
                            start=start.isoformat(),
                            end=end.isoformat(),
                            feed="sip",
                            adjustment="raw",
                            asof=None,
                            limit=10000,
                            page_token=token,
                        )
                        api_requests += 1
                        payload = result.data if isinstance(result.data, dict) else {}
                        bars = payload.get("bars") or {}
                        inserted = await asyncio.to_thread(_insert_page, bars, asset_ids)
                        rows_inserted += inserted
                        token = payload.get("next_page_token")
                        if api_requests % 25 == 0:
                            await asyncio.to_thread(
                                _checkpoint,
                                request_id,
                                rows_inserted=rows_inserted,
                                api_requests=api_requests,
                                details={"last_day": day.isoformat(), "last_batch": batch_idx},
                            )
                        if not token:
                            break

            for batch in batches:
                token = None
                while True:
                    result = await client.fetch_corporate_actions_page(
                        symbols=batch,
                        start=start_date.isoformat(),
                        end=(end_date + timedelta(days=4)).isoformat(),
                        limit=1000,
                        page_token=token,
                        data_quality="complete",
                    )
                    api_requests += 1
                    payload = result.data if isinstance(result.data, dict) else {}
                    ca_payloads.append(payload)
                    token = payload.get("next_page_token")
                    if not token:
                        break

        ca_summary = _corporate_action_summary(ca_payloads)
        await asyncio.to_thread(
            _store_source_audit,
            "alpaca_prospective_corporate_actions",
            "OBSERVED",
            {"request_id": request_id, **ca_summary, "data_quality": "complete"},
        )
        details = {
            "calendar": calendar_rows,
            "corporate_actions": ca_summary,
            "symbols": len(symbols),
            "source": "Alpaca SIP 1Min raw",
        }
        await asyncio.to_thread(
            _finish,
            request_id,
            status="completed",
            rows_inserted=rows_inserted,
            api_requests=api_requests,
            error=None,
            details=details,
        )
        logger.info("TEN24 prospective collection completed request=%s rows=%s requests=%s", request_id, rows_inserted, api_requests)
    except Exception as exc:
        logger.exception("TEN24 prospective collection failed request=%s", request_id)
        await asyncio.to_thread(
            _finish,
            request_id,
            status="failed",
            rows_inserted=rows_inserted,
            api_requests=api_requests,
            error=str(exc)[:2000],
            details={"calendar": calendar_rows},
        )
