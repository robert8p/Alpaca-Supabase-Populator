from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.db import connection

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 4
BATCH_SIZE = 25


def _quote_time(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    if "." in text:
        head, tail = text.split(".", 1)
        positions = [p for p in (tail.find("+"), tail.find("-")) if p >= 0]
        sign_pos = min(positions) if positions else -1
        if sign_pos >= 0:
            fraction, offset = tail[:sign_pos], tail[sign_pos:]
        else:
            fraction, offset = tail, ""
        text = f"{head}.{fraction[:6]}{offset}"
    return datetime.fromisoformat(text)


def _iter_quotes(data: Any):
    if not isinstance(data, dict):
        return
    payload = data.get("quotes")
    if isinstance(payload, dict):
        rows = payload.get("SPY") or []
        for row in rows:
            if isinstance(row, dict):
                yield row
    elif isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and (row.get("S") == "SPY" or row.get("symbol") == "SPY"):
                yield row


def _claim_groups(limit: int = BATCH_SIZE) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,signal_date,trade_date,position,leg,target_ts,request_start,request_end,attempts
                FROM blankcanvas_spy_ms001_quote_audit_groups
                WHERE status='pending' OR (status='failed' AND attempts < %s)
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (MAX_ATTEMPTS, limit),
            )
            rows = cur.fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                cur.execute(
                    """
                    UPDATE blankcanvas_spy_ms001_quote_audit_groups
                    SET status='running',attempts=attempts+1,claimed_at=now(),error=NULL
                    WHERE id=ANY(%s)
                    """,
                    (ids,),
                )
        conn.commit()
    return [dict(r) for r in rows]


async def _process_group(client: AlpacaClient, group: dict[str, Any]) -> None:
    page_token: str | None = None
    api_requests = 0
    snap: dict[str, Any] | None = None
    try:
        while True:
            result = await client.fetch_quotes_page(
                symbols=["SPY"],
                start=group["request_start"].isoformat(),
                end=group["request_end"].isoformat(),
                feed="sip",
                limit=1000,
                page_token=page_token,
            )
            api_requests += 1
            for row in _iter_quotes(result.data):
                ts_raw = row.get("t") or row.get("timestamp")
                if not ts_raw:
                    continue
                try:
                    quote_ts = _quote_time(str(ts_raw))
                    bid = float(row.get("bp") if row.get("bp") is not None else row.get("bid_price"))
                    ask = float(row.get("ap") if row.get("ap") is not None else row.get("ask_price"))
                except (TypeError, ValueError):
                    continue
                if quote_ts < group["request_start"] or bid <= 0 or ask < bid:
                    continue
                bs = row.get("bs") if row.get("bs") is not None else row.get("bid_size")
                asks = row.get("as") if row.get("as") is not None else row.get("ask_size")
                snap = {
                    "quote_ts": quote_ts,
                    "bid": bid,
                    "ask": ask,
                    "bid_size": float(bs) if bs is not None else None,
                    "ask_size": float(asks) if asks is not None else None,
                    "latency_ms": (quote_ts - group["target_ts"]).total_seconds() * 1000.0,
                }
                break
            if snap is not None:
                break
            data = result.data if isinstance(result.data, dict) else {}
            token = data.get("next_page_token")
            if not token:
                break
            page_token = str(token)

        with connection() as conn:
            with conn.cursor() as cur:
                if snap is not None:
                    cur.execute(
                        """
                        INSERT INTO blankcanvas_spy_ms001_quote_audit_snapshots(
                          group_id,signal_date,trade_date,position,leg,target_ts,quote_ts,
                          bid_price,ask_price,bid_size,ask_size,latency_ms,source_feed
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sip')
                        ON CONFLICT(group_id) DO UPDATE SET
                          quote_ts=excluded.quote_ts,bid_price=excluded.bid_price,ask_price=excluded.ask_price,
                          bid_size=excluded.bid_size,ask_size=excluded.ask_size,latency_ms=excluded.latency_ms
                        """,
                        (group["id"],group["signal_date"],group["trade_date"],group["position"],group["leg"],
                         group["target_ts"],snap["quote_ts"],snap["bid"],snap["ask"],snap["bid_size"],snap["ask_size"],snap["latency_ms"]),
                    )
                    cur.execute(
                        """
                        UPDATE blankcanvas_spy_ms001_quote_audit_groups
                        SET status='completed',api_requests=api_requests+%s,completed_at=now(),error=NULL
                        WHERE id=%s
                        """,
                        (api_requests,group["id"]),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE blankcanvas_spy_ms001_quote_audit_groups
                        SET status='failed',api_requests=api_requests+%s,error='No valid SPY SIP quote in frozen 1s-6s window'
                        WHERE id=%s
                        """,
                        (api_requests,group["id"]),
                    )
            conn.commit()
    except Exception as exc:
        logger.exception("SPY-MS-001 quote audit group %s failed", group["id"])
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE blankcanvas_spy_ms001_quote_audit_groups SET status='failed',api_requests=api_requests+%s,error=%s WHERE id=%s",
                    (api_requests,str(exc)[:2000],group["id"]),
                )
            conn.commit()


async def run_spy_ms001_quote_audit_batch() -> int:
    groups = _claim_groups()
    if not groups:
        return 0
    settings = get_settings()
    async with AlpacaClient(target_rpm=min(settings.default_target_rpm,600),max_retries=5,backoff_seconds=1.0) as client:
        for group in groups:
            await _process_group(client,group)
    logger.info("Processed %s SPY-MS-001 SPY quote-audit groups", len(groups))
    return len(groups)
