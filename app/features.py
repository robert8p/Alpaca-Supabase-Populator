from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.db import connection
from app.models import JobConfig


def refresh_daily_features(task: dict[str, Any], config: JobConfig) -> int:
    feature_session = config.storage.feature_session
    session_sql = "TRUE" if feature_session == "all" else "session_label = %s"
    params: list[Any] = [
        task["symbols"],
        task["timeframe"],
        task["feed"],
        task["adjustment"],
        task["window_start"] - timedelta(days=1),
        task["window_end"] + timedelta(days=1),
    ]
    if feature_session != "all":
        params.append(feature_session)

    query = f"""
        WITH base AS (
            SELECT
                symbol, bar_ts, timeframe, feed, adjustment, session_label,
                open, high, low, close, volume, trade_count, vwap,
                (bar_ts AT TIME ZONE 'America/New_York')::date AS trade_date,
                lag(close) OVER (
                    PARTITION BY symbol, timeframe, feed, adjustment, session_label,
                                 (bar_ts AT TIME ZONE 'America/New_York')::date
                    ORDER BY bar_ts
                ) AS previous_close
            FROM rd_bars
            WHERE symbol = ANY(%s)
              AND timeframe = %s
              AND feed = %s
              AND adjustment = %s
              AND bar_ts >= %s
              AND bar_ts < %s
              AND {session_sql}
        ), aggregated AS (
            SELECT
                symbol, trade_date, timeframe, feed, adjustment,
                CASE WHEN %s = 'all' THEN 'all' ELSE min(session_label) END AS feature_session,
                min(bar_ts) AS first_bar_ts,
                max(bar_ts) AS last_bar_ts,
                (array_agg(open ORDER BY bar_ts))[1] AS day_open,
                max(high) AS day_high,
                min(low) AS day_low,
                (array_agg(close ORDER BY bar_ts DESC))[1] AS day_close,
                sum(volume)::bigint AS day_volume,
                sum(COALESCE(trade_count,0))::bigint AS day_trade_count,
                count(*)::integer AS bar_count,
                sum(COALESCE(vwap, close) * volume) / NULLIF(sum(volume), 0) AS day_vwap,
                stddev_samp(ln(close / NULLIF(previous_close, 0))) AS realised_volatility
            FROM base
            GROUP BY symbol, trade_date, timeframe, feed, adjustment
        )
        INSERT INTO rd_daily_features(
            symbol, trade_date, timeframe, feed, adjustment, session_label,
            first_bar_ts, last_bar_ts, open, high, low, close, volume, trade_count,
            bar_count, vwap, return_pct, range_pct, realised_volatility, refreshed_at
        )
        SELECT
            symbol, trade_date, timeframe, feed, adjustment, feature_session,
            first_bar_ts, last_bar_ts, day_open, day_high, day_low, day_close,
            day_volume, day_trade_count, bar_count, day_vwap,
            CASE WHEN day_open <> 0 THEN (day_close / day_open - 1) * 100 END,
            CASE WHEN day_open <> 0 THEN (day_high - day_low) / day_open * 100 END,
            realised_volatility, now()
        FROM aggregated
        ON CONFLICT(symbol, trade_date, timeframe, feed, adjustment, session_label)
        DO UPDATE SET
            first_bar_ts=excluded.first_bar_ts, last_bar_ts=excluded.last_bar_ts,
            open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
            volume=excluded.volume, trade_count=excluded.trade_count,
            bar_count=excluded.bar_count, vwap=excluded.vwap,
            return_pct=excluded.return_pct, range_pct=excluded.range_pct,
            realised_volatility=excluded.realised_volatility, refreshed_at=now()
    """
    params.append(feature_session)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '15min'")
            cur.execute(query, params)
            affected = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()
    return affected
