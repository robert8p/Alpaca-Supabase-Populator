from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.db import connection

logger = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")
RULE_VERSION = "E003C_v1"
MIN_BASKET_NAMES = 6
RANGE_LOG_CHANGE_MIN = 0.785659891999253
DOLLAR_VOLUME_LOG_CHANGE_MIN = 0.652913500220726
BAR_COUNT_LOG_CHANGE_MIN = 0.23375466939777


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quote_metrics(quote: dict[str, Any] | None) -> dict[str, Any]:
    quote = quote or {}
    bid = _safe_float(quote.get("bp"))
    ask = _safe_float(quote.get("ap"))
    observed_at = quote.get("t")
    mid = None
    spread_bp = None
    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2.0
        if mid > 0:
            spread_bp = (ask - bid) / mid * 10000.0
    return {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_bp": spread_bp,
        "observed_at": observed_at,
    }


def _within(now_et: datetime, start: time, end: time) -> bool:
    current = now_et.timetz().replace(tzinfo=None)
    return start <= current <= end


def _latest_signal_date(trade_date: date) -> date | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(trade_date) AS signal_date
                FROM rd_daily_features
                WHERE trade_date < %s
                  AND timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                """,
                (trade_date,),
            )
            row = cur.fetchone()
        conn.rollback()
    return row["signal_date"] if row else None


def _previous_trade_date(signal_date: date) -> date | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(trade_date) AS previous_date
                FROM rd_daily_features
                WHERE trade_date < %s
                  AND timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                """,
                (signal_date,),
            )
            row = cur.fetchone()
        conn.rollback()
    return row["previous_date"] if row else None


def _signal_candidates(signal_date: date) -> list[dict[str, Any]]:
    previous_date = _previous_trade_date(signal_date)
    if previous_date is None:
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH s AS (
                    SELECT symbol, open, high, low, close, volume, bar_count, vwap,
                           return_pct, range_pct,
                           COALESCE(vwap, close) * volume::double precision AS dollar_volume
                    FROM rd_daily_features
                    WHERE trade_date=%s
                      AND timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                ), p AS (
                    SELECT symbol, range_pct,
                           COALESCE(vwap, close) * volume::double precision AS dollar_volume,
                           bar_count
                    FROM rd_daily_features
                    WHERE trade_date=%s
                      AND timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                )
                SELECT s.symbol,
                       s.open AS signal_open, s.high AS signal_high, s.low AS signal_low,
                       s.close AS signal_close, s.return_pct AS signal_return_pct,
                       s.range_pct AS signal_range_pct, s.dollar_volume AS signal_dollar_volume,
                       s.bar_count AS signal_bar_count,
                       p.range_pct AS prior_range_pct, p.dollar_volume AS prior_dollar_volume,
                       p.bar_count AS prior_bar_count,
                       ln(s.range_pct / p.range_pct) AS range_log_change,
                       ln(s.dollar_volume / p.dollar_volume) AS dollar_volume_log_change,
                       ln(s.bar_count::double precision / p.bar_count::double precision) AS bar_count_log_change
                FROM s JOIN p USING(symbol)
                WHERE s.open >= 5
                  AND s.close >= 5
                  AND s.return_pct >= 2
                  AND s.dollar_volume >= 1000000
                  AND s.bar_count >= 200
                  AND s.range_pct > 0 AND p.range_pct > 0
                  AND s.dollar_volume > 0 AND p.dollar_volume > 0
                  AND p.bar_count > 0
                  AND ln(s.range_pct / p.range_pct) >= %s
                  AND ln(s.dollar_volume / p.dollar_volume) >= %s
                  AND ln(s.bar_count::double precision / p.bar_count::double precision) >= %s
                ORDER BY s.symbol
                """,
                (
                    signal_date,
                    previous_date,
                    RANGE_LOG_CHANGE_MIN,
                    DOLLAR_VOLUME_LOG_CHANGE_MIN,
                    BAR_COUNT_LOG_CHANGE_MIN,
                ),
            )
            rows = cur.fetchall()
        conn.rollback()
    return [dict(row) for row in rows]


async def _latest_quotes(client: AlpacaClient, symbols: list[str], chunk_size: int = 150) -> dict[str, dict[str, Any]]:
    quotes: dict[str, dict[str, Any]] = {}
    for index in range(0, len(symbols), chunk_size):
        chunk = symbols[index:index + chunk_size]
        result = await client.fetch_latest_quotes(symbols=chunk, feed="sip")
        payload = result.data.get("quotes", {}) if isinstance(result.data, dict) else {}
        if isinstance(payload, dict):
            quotes.update({str(symbol): quote for symbol, quote in payload.items() if isinstance(quote, dict)})
    return quotes


async def capture_entry(trade_date: date, client: AlpacaClient) -> dict[str, Any]:
    signal_date = _latest_signal_date(trade_date)
    if signal_date is None or signal_date < trade_date - timedelta(days=5):
        logger.warning("E-003C entry skipped: no recent signal date for %s", trade_date)
        return {"ok": False, "reason": "signal_date_missing"}

    candidates = _signal_candidates(signal_date)
    symbols = [row["symbol"] for row in candidates]
    assets = {str(asset.get("symbol")): asset for asset in await client.list_assets()}
    quotes = await _latest_quotes(client, symbols) if symbols else {}

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        symbol = candidate["symbol"]
        asset = assets.get(symbol, {})
        quote = quotes.get(symbol, {})
        qm = _quote_metrics(quote)
        shortable = bool(asset.get("shortable"))
        easy_to_borrow = bool(asset.get("easy_to_borrow"))
        entry_ge_5 = bool(qm["mid"] is not None and qm["mid"] >= 5)
        quote_ok = bool(qm["bid"] and qm["ask"] and qm["mid"])
        executable = bool(shortable and easy_to_borrow and entry_ge_5 and quote_ok)
        if not shortable:
            reason = "not_shortable"
        elif not easy_to_borrow:
            reason = "hard_to_borrow"
        elif not quote_ok:
            reason = "quote_missing_or_invalid"
        elif not entry_ge_5:
            reason = "entry_below_5"
        else:
            reason = None
        rows.append(
            {
                **candidate,
                "shortable": shortable,
                "easy_to_borrow": easy_to_borrow,
                "borrow_status": "easy_to_borrow" if easy_to_borrow else "hard_to_borrow",
                "borrow_observed_at": datetime.now(tz=NY),
                "entry_observed_at": qm["observed_at"] or datetime.now(tz=NY),
                "entry_bid": qm["bid"],
                "entry_ask": qm["ask"],
                "entry_mid": qm["mid"],
                "entry_spread_bp": qm["spread_bp"],
                "entry_proxy_price": qm["bid"],
                "entry_price_ge_5": entry_ge_5,
                "executable": executable,
                "exclusion_reason": reason,
                "raw_borrow": asset,
                "raw_entry_quote": quote,
            }
        )

    executable_count = sum(1 for row in rows if row["executable"])
    basket_eligible = executable_count >= MIN_BASKET_NAMES

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ra_e003c_live_days(
                    trade_date, signal_date, rule_version, signal_count, executable_count, etb_count,
                    basket_eligible, min_required_names, assumed_cost_budget_bp, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,25,now())
                ON CONFLICT(trade_date) DO UPDATE SET
                    signal_date=excluded.signal_date, rule_version=excluded.rule_version,
                    signal_count=excluded.signal_count, executable_count=excluded.executable_count,
                    etb_count=excluded.etb_count, basket_eligible=excluded.basket_eligible,
                    min_required_names=excluded.min_required_names, updated_at=now()
                """,
                (
                    trade_date,
                    signal_date,
                    RULE_VERSION,
                    len(rows),
                    executable_count,
                    sum(1 for row in rows if row["easy_to_borrow"]),
                    basket_eligible,
                    MIN_BASKET_NAMES,
                ),
            )
            for row in rows:
                included = bool(basket_eligible and row["executable"])
                reason = row["exclusion_reason"]
                if row["executable"] and not basket_eligible:
                    reason = "insufficient_basket_names"
                cur.execute(
                    """
                    INSERT INTO ra_e003c_live_candidates(
                        signal_date, trade_date, symbol, rule_version,
                        signal_open, signal_close, signal_return_pct, signal_high, signal_low,
                        signal_range_pct, signal_dollar_volume, signal_bar_count,
                        prior_range_pct, prior_dollar_volume, prior_bar_count,
                        range_log_change, dollar_volume_log_change, bar_count_log_change,
                        borrow_observed_at, shortable, easy_to_borrow, borrow_status,
                        entry_observed_at, entry_bid, entry_ask, entry_mid, entry_spread_bp,
                        entry_proxy_price, entry_price_ge_5, executable, included_in_basket,
                        exclusion_reason, raw_borrow, raw_entry_quote, updated_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()
                    )
                    ON CONFLICT(signal_date, trade_date, symbol, rule_version) DO UPDATE SET
                        borrow_observed_at=excluded.borrow_observed_at,
                        shortable=excluded.shortable, easy_to_borrow=excluded.easy_to_borrow,
                        borrow_status=excluded.borrow_status,
                        entry_observed_at=excluded.entry_observed_at,
                        entry_bid=excluded.entry_bid, entry_ask=excluded.entry_ask,
                        entry_mid=excluded.entry_mid, entry_spread_bp=excluded.entry_spread_bp,
                        entry_proxy_price=excluded.entry_proxy_price,
                        entry_price_ge_5=excluded.entry_price_ge_5,
                        executable=excluded.executable, included_in_basket=excluded.included_in_basket,
                        exclusion_reason=excluded.exclusion_reason,
                        raw_borrow=excluded.raw_borrow, raw_entry_quote=excluded.raw_entry_quote,
                        updated_at=now()
                    """,
                    (
                        signal_date,
                        trade_date,
                        row["symbol"],
                        RULE_VERSION,
                        row["signal_open"],
                        row["signal_close"],
                        row["signal_return_pct"],
                        row["signal_high"],
                        row["signal_low"],
                        row["signal_range_pct"],
                        row["signal_dollar_volume"],
                        row["signal_bar_count"],
                        row["prior_range_pct"],
                        row["prior_dollar_volume"],
                        row["prior_bar_count"],
                        row["range_log_change"],
                        row["dollar_volume_log_change"],
                        row["bar_count_log_change"],
                        row["borrow_observed_at"],
                        row["shortable"],
                        row["easy_to_borrow"],
                        row["borrow_status"],
                        row["entry_observed_at"],
                        row["entry_bid"],
                        row["entry_ask"],
                        row["entry_mid"],
                        row["entry_spread_bp"],
                        row["entry_proxy_price"],
                        row["entry_price_ge_5"],
                        row["executable"],
                        included,
                        reason,
                        Jsonb(row["raw_borrow"]),
                        Jsonb(row["raw_entry_quote"]),
                    ),
                )
        conn.commit()

    logger.info(
        "E-003C entry captured trade_date=%s signal_date=%s signals=%s executable=%s basket=%s",
        trade_date,
        signal_date,
        len(rows),
        executable_count,
        basket_eligible,
    )
    return {
        "ok": True,
        "trade_date": str(trade_date),
        "signal_date": str(signal_date),
        "signal_count": len(rows),
        "executable_count": executable_count,
        "basket_eligible": basket_eligible,
    }


async def capture_exit(trade_date: date, client: AlpacaClient) -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, symbol, entry_bid, entry_ask, entry_mid, entry_spread_bp
                FROM ra_e003c_live_candidates
                WHERE trade_date=%s AND rule_version=%s
                  AND included_in_basket=true AND exit_observed_at IS NULL
                ORDER BY symbol
                """,
                (trade_date, RULE_VERSION),
            )
            candidates = [dict(row) for row in cur.fetchall()]
        conn.rollback()

    if not candidates:
        return {"ok": False, "reason": "no_open_observations"}

    quotes = await _latest_quotes(client, [row["symbol"] for row in candidates])
    updated = 0
    with connection() as conn:
        with conn.cursor() as cur:
            for row in candidates:
                quote = quotes.get(row["symbol"], {})
                qm = _quote_metrics(quote)
                if not qm["bid"] or not qm["ask"] or not qm["mid"]:
                    continue
                entry_bid = _safe_float(row["entry_bid"])
                entry_mid = _safe_float(row["entry_mid"])
                entry_spread_bp = _safe_float(row["entry_spread_bp"]) or 0.0
                if not entry_bid or not entry_mid:
                    continue
                gross = (entry_mid - qm["mid"]) / entry_mid * 100.0
                quote_cost_bp = entry_spread_bp / 2.0 + (qm["spread_bp"] or 0.0) / 2.0
                net_proxy = (entry_bid - qm["ask"]) / entry_bid * 100.0
                cur.execute(
                    """
                    UPDATE ra_e003c_live_candidates SET
                        exit_observed_at=%s, exit_bid=%s, exit_ask=%s, exit_mid=%s,
                        exit_spread_bp=%s, exit_proxy_price=%s,
                        gross_short_return_pct=%s,
                        quoted_round_trip_spread_bp=%s,
                        estimated_slippage_bp=0,
                        total_cost_bp=%s,
                        net_short_return_pct=%s,
                        raw_exit_quote=%s,
                        updated_at=now()
                    WHERE id=%s
                    """,
                    (
                        qm["observed_at"] or datetime.now(tz=NY),
                        qm["bid"],
                        qm["ask"],
                        qm["mid"],
                        qm["spread_bp"],
                        qm["ask"],
                        gross,
                        quote_cost_bp,
                        quote_cost_bp,
                        net_proxy,
                        Jsonb(quote),
                        row["id"],
                    ),
                )
                updated += 1
        conn.commit()

    logger.info("E-003C exit captured trade_date=%s names=%s", trade_date, updated)
    return {"ok": True, "trade_date": str(trade_date), "updated": updated}


async def run_e003c_scheduler(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    enabled = os.getenv("E003C_LIVE_CAPTURE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return
    logger.info("E-003C live evidence scheduler enabled")
    while not stop_event.is_set():
        try:
            now_et = datetime.now(tz=NY)
            if now_et.weekday() < 5:
                async with AlpacaClient(
                    target_rpm=min(300, settings.default_target_rpm),
                    max_retries=3,
                    backoff_seconds=1.0,
                ) as client:
                    clock = await client.get_clock()
                    is_open = bool(clock.get("is_open")) if isinstance(clock, dict) else False
                    if is_open and _within(now_et, time(9, 30), time(9, 40)):
                        await capture_entry(now_et.date(), client)
                    if is_open and _within(now_et, time(15, 50), time(15, 59, 59)):
                        await capture_exit(now_et.date(), client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("E-003C live evidence scheduler error")

        try:
            poll_seconds = max(10.0, float(os.getenv("E003C_CAPTURE_POLL_SECONDS", "30")))
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
