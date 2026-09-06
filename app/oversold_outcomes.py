from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection

logger = logging.getLogger(__name__)
OUTCOME_BATCH_SIZE = 20
TARGET_RETURN = 0.05
NEW_YORK = ZoneInfo("America/New_York")


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


def _bars_by_symbol(payload: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        return {}
    bars = payload.get("bars")
    if not isinstance(bars, dict):
        return {}
    return {
        str(symbol).upper(): [bar for bar in values if isinstance(bar, dict)]
        for symbol, values in bars.items()
        if isinstance(values, list)
    }


def _chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def _return_pct(price: Any, signal_price: float) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    return ((p / signal_price) - 1.0) * 100.0 if signal_price > 0 and p > 0 and math.isfinite(p) else None


def _first_daily_touch(eligible: list[tuple[datetime, dict[str, Any]]], *, field: str, threshold: float, comparator: str) -> tuple[int | None, datetime | None]:
    for idx, (ts, bar) in enumerate(eligible):
        try:
            value = float(bar.get(field))
        except (TypeError, ValueError):
            continue
        if (comparator == "gte" and value >= threshold) or (comparator == "lte" and value <= threshold):
            return idx, ts
    return None, None


def calculate_outcome_metrics(row: dict[str, Any], bars: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    """Calculate point-in-time-safe daily outcome metrics.

    Daily bars identify the first session that touched the target and downside
    thresholds. Exact ordering when target and downside touch in the same session
    is intentionally left unknown here and is resolved separately with SIP 1-minute
    bars. Bars at/before the signal timestamp and after the six-week deadline are
    excluded.
    """
    signal_ts = _parse_ts(row.get("signal_timestamp"))
    deadline = _parse_ts(row.get("horizon_deadline"))
    if signal_ts is None or deadline is None:
        raise ValueError("Outcome row has invalid signal/deadline timestamp")
    signal_price = float(row["signal_price"])
    if not math.isfinite(signal_price) or signal_price <= 0:
        raise ValueError("invalid signal price")
    eligible: list[tuple[datetime, dict[str, Any]]] = []
    seen_sessions = set()
    for bar in sorted(bars, key=lambda bar: str(bar.get("t") or "")):
        ts = _parse_ts(bar.get("t"))
        if ts is None or ts <= signal_ts or ts > deadline or ts > now:
            continue
        day = ts.astimezone(NEW_YORK).date()
        close_at = datetime.combine(day, time(16), tzinfo=NEW_YORK)
        if day <= signal_ts.astimezone(NEW_YORK).date() or close_at + timedelta(minutes=1) > min(now, deadline):
            continue
        if day in seen_sessions:
            continue
        try:
            high, low, close = (float(bar[field]) for field in ("h", "l", "c"))
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(value) and value > 0 for value in (high, low, close)) or not low <= close <= high:
            continue
        seen_sessions.add(day)
        eligible.append((ts, bar))
    eligible.sort(key=lambda item: item[0])
    clean = [bar for _, bar in eligible]
    timestamps = [ts for ts, _ in eligible]

    def close_at(index: int) -> float | None:
        if len(clean) <= index:
            return None
        return _return_pct(clean[index].get("c"), signal_price)

    closes = [float(bar["c"]) for bar in clean if bar.get("c") is not None]
    highs = [float(bar["h"]) for bar in clean if bar.get("h") is not None]
    lows = [float(bar["l"]) for bar in clean if bar.get("l") is not None]
    mfe = max((_return_pct(p, signal_price) for p in highs), default=None)
    mae = min((_return_pct(p, signal_price) for p in lows), default=None)

    target_idx, target_day = _first_daily_touch(
        eligible, field="h", threshold=signal_price * (1.0 + TARGET_RETURN), comparator="gte"
    )
    downside_days: dict[str, datetime | None] = {}
    downside_flags: dict[str, bool | None] = {}
    for label, threshold in (("5", 0.05), ("10", 0.10), ("20", 0.20)):
        _, downside_day = _first_daily_touch(
            eligible, field="l", threshold=signal_price * (1.0 - threshold), comparator="lte"
        )
        downside_days[label] = downside_day
        if target_day is None:
            downside_flags[label] = downside_day is not None
        elif downside_day is None or downside_day > target_day:
            downside_flags[label] = False
        elif downside_day < target_day:
            downside_flags[label] = True
        else:
            downside_flags[label] = None

    matured = now >= deadline and bool(clean)
    terminal_bar_observed = bool(timestamps and (deadline - timestamps[-1]).total_seconds() <= 4 * 86400)
    last_close_return = _return_pct(closes[-1], signal_price) if closes and terminal_bar_observed else None
    existing_first_hit = _parse_ts(row.get("first_plus_5_ts"))
    existing_hours = row.get("hours_to_plus_5")
    if existing_first_hit:
        first_hit_ts = existing_first_hit
        hours_to_target = float(existing_hours) if existing_hours is not None else (existing_first_hit - signal_ts).total_seconds() / 3600.0
        for label, field in (("5", "minus_5_before_plus_5"), ("10", "minus_10_before_plus_5"), ("20", "minus_20_before_plus_5")):
            if row.get(field) is not None:
                downside_flags[label] = bool(row[field])
    else:
        first_hit_ts = None
        hours_to_target = None

    return {
        "return_1d": close_at(0), "return_3d": close_at(2), "return_1w": close_at(4),
        "return_2w": close_at(9), "return_4w": close_at(19), "return_6w": last_close_return if matured else None,
        "mfe_6w": mfe, "mae_6w": mae,
        "hit_plus_5pct_within_6_weeks": (True if target_idx is not None else (False if timestamps and (deadline - timestamps[-1]).total_seconds() <= 4 * 86400 else None)) if matured else None,
        "first_plus_5_ts": first_hit_ts,
        "trading_days_to_plus_5": target_idx + 1 if target_idx is not None else None,
        "hours_to_plus_5": hours_to_target,
        "minus_5_before_plus_5": downside_flags["5"], "minus_10_before_plus_5": downside_flags["10"], "minus_20_before_plus_5": downside_flags["20"],
        "status": "matured" if matured else "pending",
        "bar_count": len(clean), "first_bar_ts": timestamps[0] if timestamps else None, "last_bar_ts": timestamps[-1] if timestamps else None,
        "target_touch_day": target_day, "downside_touch_days": downside_days,
        "intraday_refinement": "already_stored" if existing_first_hit else "required" if target_day is not None else "not_applicable",
    }


def refine_intraday_events(row: dict[str, Any], metrics: dict[str, Any], minute_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve first target touch and same-session event order to minute resolution.

    If a target and downside threshold first occur in the same minute bar, their
    within-minute order is unknowable from OHLC and the corresponding before-target
    flag remains NULL rather than asserting false precision.
    """
    signal_ts = _parse_ts(row.get("signal_timestamp"))
    deadline = _parse_ts(row.get("horizon_deadline"))
    target_day = _parse_ts(metrics.get("target_touch_day"))
    if signal_ts is None or deadline is None or target_day is None:
        return metrics
    signal_price = float(row["signal_price"])
    if not math.isfinite(signal_price) or signal_price <= 0:
        raise ValueError("invalid signal price")
    target_price = signal_price * 1.05
    bars: list[tuple[datetime, dict[str, Any]]] = []
    for bar in minute_bars:
        ts = _parse_ts(bar.get("t"))
        if ts is None or ts <= signal_ts or ts + timedelta(minutes=1) > deadline:
            continue
        if ts.astimezone(NEW_YORK).date() != target_day.astimezone(NEW_YORK).date():
            continue
        bars.append((ts, bar))
    bars.sort(key=lambda item: item[0])

    first_target_ts: datetime | None = None
    for ts, bar in bars:
        try:
            if float(bar.get("h")) >= target_price:
                first_target_ts = ts
                break
        except (TypeError, ValueError):
            continue
    if first_target_ts is None:
        metrics["intraday_refinement"] = "target_not_confirmed_in_minute_bars"
        return metrics

    metrics["first_plus_5_ts"] = first_target_ts
    metrics["hours_to_plus_5"] = (first_target_ts - signal_ts).total_seconds() / 3600.0
    for label, threshold, field in (
        ("5", 0.05, "minus_5_before_plus_5"), ("10", 0.10, "minus_10_before_plus_5"), ("20", 0.20, "minus_20_before_plus_5")
    ):
        downside_day = _parse_ts((metrics.get("downside_touch_days") or {}).get(label))
        if downside_day is None or downside_day > target_day:
            metrics[field] = False
            continue
        if downside_day < target_day:
            metrics[field] = True
            continue
        first_down_ts: datetime | None = None
        floor = signal_price * (1.0 - threshold)
        for ts, bar in bars:
            try:
                if float(bar.get("l")) <= floor:
                    first_down_ts = ts
                    break
            except (TypeError, ValueError):
                continue
        if first_down_ts is None:
            # The daily low proves a touch; missing minute evidence cannot disprove it.
            metrics[field] = None
        elif first_down_ts < first_target_ts:
            metrics[field] = True
        elif first_down_ts > first_target_ts:
            metrics[field] = False
        else:
            metrics[field] = None
    metrics["intraday_refinement"] = "sip_1min"
    return metrics


def _load_due(limit: int = 500) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,candidate_id,symbol,signal_timestamp,signal_price,horizon_deadline,status,
                       corporate_action_status,eligible_for_calibration,first_plus_5_ts,hours_to_plus_5,
                       minus_5_before_plus_5,minus_10_before_plus_5,minus_20_before_plus_5
                FROM or_signal_outcomes
                WHERE status IN ('pending','error') ORDER BY signal_timestamp,id LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.rollback()
    return rows


async def _fetch_daily_bars(client: AlpacaClient, rows: list[dict[str, Any]], now: datetime) -> dict[str, list[dict[str, Any]]]:
    if not rows:
        return {}
    symbols = sorted({str(row["symbol"]).upper() for row in rows})
    earliest = min(_parse_ts(row["signal_timestamp"]) for row in rows)
    latest_deadline = max(_parse_ts(row["horizon_deadline"]) for row in rows)
    if earliest is None or latest_deadline is None:
        raise ValueError("Invalid outcome timestamps")
    end_at = min(now, latest_deadline + timedelta(days=1))
    page_token: str | None = None
    merged: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    while True:
        result = await client.fetch_bars_page(symbols=symbols, timeframe="1Day", start=(earliest - timedelta(days=1)).isoformat(), end=end_at.isoformat(), feed="sip", adjustment="raw", asof=None, limit=10000, page_token=page_token)
        payload = result.data if isinstance(result.data, dict) else {}
        for symbol, bars in _bars_by_symbol(payload).items():
            merged.setdefault(symbol, []).extend(bars)
        page_token = payload.get("next_page_token")
        if not page_token:
            break
    return merged


async def _fetch_minute_bars_for_session(client: AlpacaClient, symbol: str, daily_touch_ts: datetime) -> list[dict[str, Any]]:
    session_date = daily_touch_ts.astimezone(NEW_YORK).date()
    start_local = datetime.combine(session_date, datetime.min.time(), tzinfo=NEW_YORK)
    end_local = start_local + timedelta(days=1)
    page_token: str | None = None
    bars: list[dict[str, Any]] = []
    while True:
        result = await client.fetch_bars_page(symbols=[symbol], timeframe="1Min", start=start_local.astimezone(UTC).isoformat(), end=end_local.astimezone(UTC).isoformat(), feed="sip", adjustment="raw", asof=None, limit=10000, page_token=page_token)
        payload = result.data if isinstance(result.data, dict) else {}
        bars.extend(_bars_by_symbol(payload).get(symbol.upper(), []))
        page_token = payload.get("next_page_token")
        if not page_token:
            break
    return bars


async def capture_signal_outcomes(limit: int = 500) -> dict[str, int]:
    rows = _load_due(limit=limit)
    if not rows:
        return {"due": 0, "updated": 0, "matured": 0, "errors": 0, "minute_refinements": 0}
    now = datetime.now(UTC)
    updated = matured = errors = minute_refinements = 0
    minute_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    async with AlpacaClient(target_rpm=1000, max_retries=3, backoff_seconds=0.5) as client:
        for group in _chunks(rows, OUTCOME_BATCH_SIZE):
            try:
                bars_by_symbol = await _fetch_daily_bars(client, group, now)
            except Exception as exc:
                logger.exception("Six-week outcome bars request failed")
                with connection() as conn:
                    with conn.cursor() as cur:
                        for row in group:
                            cur.execute("UPDATE or_signal_outcomes SET status='error',error=%s,last_evaluated_at=now(),updated_at=now() WHERE id=%s", (str(exc)[:1000], row["id"]))
                    conn.commit()
                errors += len(group)
                continue

            with connection() as conn:
                with conn.cursor() as cur:
                    for row in group:
                        try:
                            metrics = calculate_outcome_metrics(row, bars_by_symbol.get(str(row["symbol"]).upper(), []), now=now)
                            target_day = _parse_ts(metrics.get("target_touch_day"))
                            if target_day is not None and row.get("first_plus_5_ts") is None:
                                cache_key = (str(row["symbol"]).upper(), target_day.astimezone(NEW_YORK).date().isoformat())
                                if cache_key not in minute_cache:
                                    minute_cache[cache_key] = await _fetch_minute_bars_for_session(client, cache_key[0], target_day)
                                metrics = refine_intraday_events(row, metrics, minute_cache[cache_key])
                                if metrics.get("intraday_refinement") == "sip_1min":
                                    minute_refinements += 1
                            cur.execute(
                                """
                                UPDATE or_signal_outcomes SET
                                    return_1d=%s,return_3d=%s,return_1w=%s,return_2w=%s,return_4w=%s,return_6w=%s,
                                    mfe_6w=%s,mae_6w=%s,hit_plus_5pct_within_6_weeks=%s,first_plus_5_ts=%s,
                                    trading_days_to_plus_5=%s,hours_to_plus_5=%s,minus_5_before_plus_5=%s,
                                    minus_10_before_plus_5=%s,minus_20_before_plus_5=%s,status=%s,error=NULL,
                                    last_evaluated_at=now(),updated_at=now(),metadata=metadata || %s WHERE id=%s
                                """,
                                (
                                    metrics["return_1d"], metrics["return_3d"], metrics["return_1w"], metrics["return_2w"], metrics["return_4w"], metrics["return_6w"], metrics["mfe_6w"], metrics["mae_6w"], metrics["hit_plus_5pct_within_6_weeks"], metrics["first_plus_5_ts"], metrics["trading_days_to_plus_5"], metrics["hours_to_plus_5"], metrics["minus_5_before_plus_5"], metrics["minus_10_before_plus_5"], metrics["minus_20_before_plus_5"], metrics["status"],
                                    Jsonb({"bar_count": metrics["bar_count"], "first_bar_ts": metrics["first_bar_ts"], "last_bar_ts": metrics["last_bar_ts"], "daily_bar_adjustment": "raw", "target_event_resolution": metrics.get("intraday_refinement"), "same_minute_event_order": "NULL means unknowable within a 1-minute OHLC bar", "corporate_action_guard": "not calibration eligible until separately verified"}), row["id"],
                                ),
                            )
                            updated += 1
                            matured += 1 if metrics["status"] == "matured" else 0
                        except Exception as exc:
                            logger.exception("Outcome calculation failed for %s", row.get("symbol"))
                            cur.execute("UPDATE or_signal_outcomes SET status='error',error=%s,last_evaluated_at=now(),updated_at=now() WHERE id=%s", (str(exc)[:1000], row["id"]))
                            errors += 1
                conn.commit()
    return {"due": len(rows), "updated": updated, "matured": matured, "errors": errors, "minute_refinements": minute_refinements}
