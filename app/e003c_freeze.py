from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.db import connection
from app.e003c_live import RULE_VERSION, _signal_candidates

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
SAFE_ALL_SESSION_TIME = time(20, 15)


def _safe_signal_date_ceiling(now_et: datetime | None = None) -> date:
    """Latest date that can possibly contain a complete 04:00-20:00 ET all-session signal."""
    current = now_et or datetime.now(tz=NY)
    current_et = current.astimezone(NY)
    if current_et.timetz().replace(tzinfo=None) >= SAFE_ALL_SESSION_TIME:
        return current_et.date()
    return current_et.date() - timedelta(days=1)


def _latest_completed_feature_date() -> date | None:
    """Return the latest complete all-session feature date that is not still being loaded."""
    safe_ceiling = _safe_signal_date_ceiling()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(f.trade_date) AS trade_date
                FROM (
                    SELECT DISTINCT trade_date
                    FROM rd_daily_features
                    WHERE timeframe='1Min'
                      AND feed='sip'
                      AND adjustment='raw'
                      AND session_label='all'
                      AND trade_date <= %s
                ) f
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM rd_jobs j
                    WHERE j.status IN ('queued','planning','running','pause_requested','paused')
                      AND j.config->>'feed'='sip'
                      AND j.config->>'adjustment'='raw'
                      AND COALESCE(j.config->'timeframes','[]'::jsonb) ? '1Min'
                      AND COALESCE(j.config->'session'->>'mode','')='all'
                      AND (j.config->>'start_date')::date <= f.trade_date
                      AND (j.config->>'end_date')::date >= f.trade_date
                )
                """,
                (safe_ceiling,),
            )
            row = cur.fetchone()
        conn.rollback()
    return row["trade_date"] if row else None


def _already_frozen(signal_date: date) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM ra_e003c_signal_freeze_days
                    WHERE signal_date=%s AND rule_version=%s
                ) AS frozen
                """,
                (signal_date, RULE_VERSION),
            )
            row = cur.fetchone()
        conn.rollback()
    return bool(row and row["frozen"])


def freeze_signal_date(signal_date: date) -> dict[str, Any]:
    """Persist the frozen E-003C candidate list for a completed signal date."""
    safe_ceiling = _safe_signal_date_ceiling()
    if signal_date > safe_ceiling:
        return {
            "signal_date": str(signal_date),
            "frozen": False,
            "reason": "all_session_not_yet_complete",
            "safe_ceiling": str(safe_ceiling),
        }

    if _already_frozen(signal_date):
        return {"signal_date": str(signal_date), "frozen": False, "reason": "already_frozen"}

    candidates = _signal_candidates(signal_date)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(refreshed_at) AS source_feature_max_refreshed_at
                FROM rd_daily_features
                WHERE trade_date=%s
                  AND timeframe='1Min'
                  AND feed='sip'
                  AND adjustment='raw'
                  AND session_label='all'
                """,
                (signal_date,),
            )
            source_row = cur.fetchone()
            source_refreshed_at = source_row["source_feature_max_refreshed_at"] if source_row else None

            cur.execute(
                """
                INSERT INTO ra_e003c_signal_freeze_days(
                    signal_date, rule_version, frozen_at, candidate_count,
                    source_feature_max_refreshed_at
                ) VALUES (%s,%s,now(),%s,%s)
                ON CONFLICT(signal_date,rule_version) DO NOTHING
                """,
                (signal_date, RULE_VERSION, len(candidates), source_refreshed_at),
            )

            for row in candidates:
                cur.execute(
                    """
                    INSERT INTO ra_e003c_signal_freeze_candidates(
                        signal_date, symbol, rule_version, frozen_at,
                        signal_open, signal_high, signal_low, signal_close,
                        signal_return_pct, signal_range_pct, signal_dollar_volume,
                        signal_bar_count, prior_range_pct, prior_dollar_volume,
                        prior_bar_count, range_log_change, dollar_volume_log_change,
                        bar_count_log_change
                    ) VALUES (
                        %s,%s,%s,now(),
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT(signal_date,symbol,rule_version) DO NOTHING
                    """,
                    (
                        signal_date,
                        row["symbol"],
                        RULE_VERSION,
                        row["signal_open"],
                        row["signal_high"],
                        row["signal_low"],
                        row["signal_close"],
                        row["signal_return_pct"],
                        row["signal_range_pct"],
                        row["signal_dollar_volume"],
                        row["signal_bar_count"],
                        row["prior_range_pct"],
                        row["prior_dollar_volume"],
                        row["prior_bar_count"],
                        row["range_log_change"],
                        row["dollar_volume_log_change"],
                        row["bar_count_log_change"],
                    ),
                )
        conn.commit()

    logger.info("Frozen E-003C signal date=%s candidates=%s", signal_date, len(candidates))
    return {"signal_date": str(signal_date), "frozen": True, "candidate_count": len(candidates)}


def freeze_latest_completed_signal() -> dict[str, Any]:
    signal_date = _latest_completed_feature_date()
    if signal_date is None:
        return {"frozen": False, "reason": "no_completed_feature_date"}
    return freeze_signal_date(signal_date)
