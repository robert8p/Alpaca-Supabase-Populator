from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection

logger = logging.getLogger(__name__)
OUTCOME_BATCH_SIZE = 20
TARGET_RETURN = 0.05


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
    return ((p / signal_price) - 1.0) * 100.0 if signal_price > 0 else None


def calculate_outcome_metrics(row: dict[str, Any], bars: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    """Calculate target/outcome metrics without using bars from before the signal.

    Alpaca 1Day bars are timestamped at the session start. Signals may occur intraday,
    so any bar whose timestamp is <= the signal timestamp is excluded. The scheduled
    production scan is after the US close, making the next retained bar the next session.
    """
    signal_ts = _parse_ts(row.get("signal_timestamp"))
    deadline = _parse_ts(row.get("horizon_deadline"))
    if signal_ts is None or deadline is None:
        raise ValueError("Outcome row has invalid signal/deadline timestamp")
    signal_price = float(row["signal_price"])
    eligible: list[tuple[datetime, dict[str, Any]]] = []
    for bar in bars:
        ts = _parse_ts(bar.get("t"))
        if ts is None or ts <= signal_ts or ts > deadline:
            continue
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

    first_hit_index: int | None = None
    first_hit_ts: datetime | None = None
    target_price = signal_price * (1.0 + TARGET_RETURN)
    for idx, (ts, bar) in enumerate(eligible):
        try:
            high = float(bar.get("h"))
        except (TypeError, ValueError):
            continue
        if high >= target_price:
            first_hit_index, first_hit_ts = idx, ts
            break

    def downside_before(threshold: float) -> bool | None:
        if not clean:
            return None
        stop = first_hit_index if first_hit_index is not None else len(clean) - 1
        floor = signal_price * (1.0 - threshold)
        for bar in clean[: stop + 1]:
            try:
                if float(bar.get("l")) <= floor:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    matured = now >= deadline
    last_close_return = _return_pct(closes[-1], signal_price) if closes else None
    hours_to_target = ((first_hit_ts - signal_ts).total_seconds() / 3600.0) if first_hit_ts else None
    return {
        "return_1d": close_at(0),
        "return_3d": close_at(2),
        "return_1w": close_at(4),
        "return_2w": close_at(9),
        "return_4w": close_at(19),
        "return_6w": last_close_return if matured else None,
        "mfe_6w": mfe,
        "mae_6w": mae,
        "hit_plus_5pct_within_6_weeks": first_hit_index is not None if matured else None,
        "first_plus_5_ts": first_hit_ts,
        "trading_days_to_plus_5": first_hit_index + 1 if first_hit_index is not None else None,
        "hours_to_plus_5": hours_to_target,
        "minus_5_before_plus_5": downside_before(0.05),
        "minus_10_before_plus_5": downside_before(0.10),
        "minus_20_before_plus_5": downside_before(0.20),
        "status": "matured" if matured else "pending",
        "bar_count": len(clean),
        "first_bar_ts": timestamps[0] if timestamps else None,
        "last_bar_ts": timestamps[-1] if timestamps else None,
    }


def _load_due(limit: int = 500) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,candidate_id,symbol,signal_timestamp,signal_price,horizon_deadline,status,
                       corporate_action_status,eligible_for_calibration
                FROM or_signal_outcomes
                WHERE status IN ('pending','error')
                ORDER BY signal_timestamp,id
                LIMIT %s
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
        result = await client.fetch_bars_page(
            symbols=symbols,
            timeframe="1Day",
            start=(earliest - timedelta(days=1)).isoformat(),
            end=end_at.isoformat(),
            feed="sip",
            adjustment="raw",
            asof=None,
            limit=10000,
            page_token=page_token,
        )
        payload = result.data if isinstance(result.data, dict) else {}
        for symbol, bars in _bars_by_symbol(payload).items():
            merged.setdefault(symbol, []).extend(bars)
        page_token = payload.get("next_page_token")
        if not page_token:
            break
    return merged


async def capture_signal_outcomes(limit: int = 500) -> dict[str, int]:
    rows = _load_due(limit=limit)
    if not rows:
        return {"due": 0, "updated": 0, "matured": 0, "errors": 0}
    now = datetime.now(UTC)
    updated = matured = errors = 0
    async with AlpacaClient(target_rpm=1000, max_retries=3, backoff_seconds=0.5) as client:
        for group in _chunks(rows, OUTCOME_BATCH_SIZE):
            try:
                bars_by_symbol = await _fetch_daily_bars(client, group, now)
            except Exception as exc:
                logger.exception("Six-week outcome bars request failed")
                with connection() as conn:
                    with conn.cursor() as cur:
                        for row in group:
                            cur.execute(
                                "UPDATE or_signal_outcomes SET status='error',error=%s,last_evaluated_at=now(),updated_at=now() WHERE id=%s",
                                (str(exc)[:1000], row["id"]),
                            )
                    conn.commit()
                errors += len(group)
                continue

            with connection() as conn:
                with conn.cursor() as cur:
                    for row in group:
                        try:
                            metrics = calculate_outcome_metrics(row, bars_by_symbol.get(str(row["symbol"]).upper(), []), now=now)
                            cur.execute(
                                """
                                UPDATE or_signal_outcomes SET
                                    return_1d=%s,return_3d=%s,return_1w=%s,return_2w=%s,return_4w=%s,return_6w=%s,
                                    mfe_6w=%s,mae_6w=%s,hit_plus_5pct_within_6_weeks=%s,first_plus_5_ts=%s,
                                    trading_days_to_plus_5=%s,hours_to_plus_5=%s,minus_5_before_plus_5=%s,
                                    minus_10_before_plus_5=%s,minus_20_before_plus_5=%s,status=%s,error=NULL,
                                    last_evaluated_at=now(),updated_at=now(),metadata=metadata || %s
                                WHERE id=%s
                                """,
                                (
                                    metrics["return_1d"], metrics["return_3d"], metrics["return_1w"], metrics["return_2w"],
                                    metrics["return_4w"], metrics["return_6w"], metrics["mfe_6w"], metrics["mae_6w"],
                                    metrics["hit_plus_5pct_within_6_weeks"], metrics["first_plus_5_ts"], metrics["trading_days_to_plus_5"],
                                    metrics["hours_to_plus_5"], metrics["minus_5_before_plus_5"], metrics["minus_10_before_plus_5"],
                                    metrics["minus_20_before_plus_5"], metrics["status"],
                                    Jsonb({"bar_count": metrics["bar_count"], "first_bar_ts": metrics["first_bar_ts"], "last_bar_ts": metrics["last_bar_ts"], "daily_bar_adjustment": "raw", "corporate_action_guard": "not calibration eligible until separately verified"}),
                                    row["id"],
                                ),
                            )
                            updated += 1
                            matured += 1 if metrics["status"] == "matured" else 0
                        except Exception as exc:
                            logger.exception("Outcome calculation failed for %s", row.get("symbol"))
                            cur.execute(
                                "UPDATE or_signal_outcomes SET status='error',error=%s,last_evaluated_at=now(),updated_at=now() WHERE id=%s",
                                (str(exc)[:1000], row["id"]),
                            )
                            errors += 1
                conn.commit()
    return {"due": len(rows), "updated": updated, "matured": matured, "errors": errors}
