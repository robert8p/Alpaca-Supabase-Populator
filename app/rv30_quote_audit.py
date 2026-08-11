from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.db import connection

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BATCH_SIZE = 20


def _claim_groups(limit: int = BATCH_SIZE) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,trade_date,minute_of_day,leg,target_ts,request_start,request_end,symbols,attempts
                FROM blankcanvas_rv30_quote_audit_groups
                WHERE (status='pending' OR (status='failed' AND attempts < %s))
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (MAX_ATTEMPTS, limit),
            )
            groups = cur.fetchall()
            if groups:
                ids = [row["id"] for row in groups]
                cur.execute(
                    """
                    UPDATE blankcanvas_rv30_quote_audit_groups
                    SET status='running',attempts=attempts+1,claimed_at=now(),error=NULL
                    WHERE id=ANY(%s)
                    """,
                    (ids,),
                )
        conn.commit()
    return [dict(row) for row in groups]


def _quote_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iter_quotes(data: Any):
    if not isinstance(data, dict):
        return
    payload = data.get("quotes")
    if isinstance(payload, dict):
        for symbol, rows in payload.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    yield str(symbol), row
    elif isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            symbol = row.get("S") or row.get("symbol")
            if symbol:
                yield str(symbol), row


def _valid_snapshot(symbol: str, row: dict[str, Any], target_ts: datetime) -> dict[str, Any] | None:
    ts_raw = row.get("t") or row.get("timestamp")
    if not ts_raw:
        return None
    try:
        quote_ts = _quote_time(str(ts_raw))
        bid = float(row.get("bp") if row.get("bp") is not None else row.get("bid_price"))
        ask = float(row.get("ap") if row.get("ap") is not None else row.get("ask_price"))
    except (TypeError, ValueError):
        return None
    if bid <= 0 or ask < bid or quote_ts < target_ts:
        return None
    bid_size_raw = row.get("bs") if row.get("bs") is not None else row.get("bid_size")
    ask_size_raw = row.get("as") if row.get("as") is not None else row.get("ask_size")
    return {
        "symbol": symbol,
        "quote_ts": quote_ts,
        "bid_price": bid,
        "ask_price": ask,
        "bid_size": float(bid_size_raw) if bid_size_raw is not None else None,
        "ask_size": float(ask_size_raw) if ask_size_raw is not None else None,
        "latency_ms": (quote_ts - target_ts).total_seconds() * 1000.0,
    }


async def _process_group(client: AlpacaClient, group: dict[str, Any]) -> None:
    symbols = [str(symbol) for symbol in group["symbols"]]
    first: dict[str, dict[str, Any]] = {}
    page_token: str | None = None
    api_requests = 0
    try:
        while True:
            result = await client.fetch_quotes_page(
                symbols=symbols,
                start=group["request_start"].isoformat(),
                end=group["request_end"].isoformat(),
                feed="sip",
                limit=10000,
                page_token=page_token,
            )
            api_requests += 1
            for symbol, row in _iter_quotes(result.data):
                if symbol in first:
                    continue
                snap = _valid_snapshot(symbol, row, group["request_start"])
                if snap is not None:
                    first[symbol] = snap
            if len(first) == len(symbols):
                break
            data = result.data if isinstance(result.data, dict) else {}
            next_token = data.get("next_page_token")
            if not next_token:
                break
            page_token = str(next_token)

        rows = [
            (
                group["id"],
                snap["symbol"],
                group["trade_date"],
                group["minute_of_day"],
                group["leg"],
                group["target_ts"],
                snap["quote_ts"],
                snap["bid_price"],
                snap["ask_price"],
                snap["bid_size"],
                snap["ask_size"],
                snap["latency_ms"],
            )
            for snap in first.values()
        ]
        missing = sorted(set(symbols) - set(first))
        with connection() as conn:
            with conn.cursor() as cur:
                if rows:
                    cur.executemany(
                        """
                        INSERT INTO blankcanvas_rv30_quote_audit_snapshots(
                            group_id,symbol,trade_date,minute_of_day,leg,target_ts,quote_ts,
                            bid_price,ask_price,bid_size,ask_size,latency_ms,source_feed
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sip')
                        ON CONFLICT(group_id,symbol) DO UPDATE SET
                            quote_ts=excluded.quote_ts,bid_price=excluded.bid_price,ask_price=excluded.ask_price,
                            bid_size=excluded.bid_size,ask_size=excluded.ask_size,latency_ms=excluded.latency_ms
                        """,
                        rows,
                    )
                if first:
                    cur.execute(
                        """
                        UPDATE blankcanvas_rv30_quote_audit_groups
                        SET status='completed',api_requests=api_requests+%s,quotes_found=%s,
                            error=%s,completed_at=now()
                        WHERE id=%s
                        """,
                        (
                            api_requests,
                            len(first),
                            f"Missing {len(missing)} of {len(symbols)} symbols within frozen 1s-6s quote window" if missing else None,
                            group["id"],
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE blankcanvas_rv30_quote_audit_groups
                        SET status='failed',api_requests=api_requests+%s,quotes_found=0,
                            error='No valid SIP NBBO quote found in frozen 1s-6s execution window'
                        WHERE id=%s
                        """,
                        (api_requests, group["id"]),
                    )
            conn.commit()
    except Exception as exc:
        logger.exception("RV30 quote audit group %s failed", group["id"])
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE blankcanvas_rv30_quote_audit_groups
                    SET status='failed',api_requests=api_requests+%s,error=%s
                    WHERE id=%s
                    """,
                    (api_requests, str(exc)[:2000], group["id"]),
                )
            conn.commit()


async def run_rv30_quote_audit_batch() -> int:
    groups = _claim_groups()
    if not groups:
        return 0
    settings = get_settings()
    async with AlpacaClient(target_rpm=min(settings.default_target_rpm, 600), max_retries=5, backoff_seconds=1.0) as client:
        for group in groups:
            await _process_group(client, group)
    logger.info("Processed %s frozen RV30 quote-audit groups", len(groups))
    return len(groups)
