from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.db import connection
from app.e003c_freeze import freeze_latest_completed_signal

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")


def _enabled() -> bool:
    return os.getenv("E003C_DAILY_INGEST_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _latest_feature_date() -> date | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(trade_date) AS trade_date
                FROM rd_daily_features
                WHERE timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                """
            )
            row = cur.fetchone()
        conn.rollback()
    return row["trade_date"] if row else None


def _day_is_loaded(trade_date: date) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM rd_daily_features
                    WHERE trade_date=%s
                      AND timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                ) AS loaded
                """,
                (trade_date,),
            )
            row = cur.fetchone()
        conn.rollback()
    return bool(row and row["loaded"])


def _day_has_covering_job(trade_date: date) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM rd_jobs
                    WHERE status IN ('queued','planning','running','pause_requested','paused','completed')
                      AND config->>'feed'='sip'
                      AND config->>'adjustment'='raw'
                      AND COALESCE(config->'timeframes','[]'::jsonb) ? '1Min'
                      AND COALESCE(config->'session'->>'mode','')='all'
                      AND (config->>'start_date')::date <= %s
                      AND (config->>'end_date')::date >= %s
                ) AS covered
                """,
                (trade_date, trade_date),
            )
            row = cur.fetchone()
        conn.rollback()
    return bool(row and row["covered"])


def _job_config(trade_date: date) -> dict:
    name = f"E-003C daily maintenance · {trade_date.isoformat()}"
    return {
        "name": name,
        "start_date": trade_date.isoformat(),
        "end_date": trade_date.isoformat(),
        "timeframes": ["1Min"],
        "feed": "sip",
        "adjustment": "raw",
        "asof": None,
        "universe": {
            "mode": "all_active",
            "symbols": [],
            "exchanges": ["NYSE", "NASDAQ", "AMEX", "ARCA", "BATS", "NYSEARCA"],
            "tradable_only": True,
            "fractionable_only": False,
            "marginable_only": False,
            "shortable_only": False,
            "easy_to_borrow_only": False,
            "overnight_tradable_only": False,
            "include_regex": None,
            "exclude_regex": "[/]",
            "symbol_limit": None,
        },
        "session": {
            "mode": "all",
            "custom_start": "09:30:00",
            "custom_end": "16:00:00",
            "weekdays_only": True,
        },
        "performance": {
            "symbol_batch_size": 100,
            "date_chunk_days": 1,
            "page_limit": 10000,
            "concurrency": 12,
            "target_rpm": 9000,
            "max_retries": 7,
            "retry_backoff_seconds": 1.5,
        },
        "storage": {
            "conflict_policy": "skip",
            "keep_staging_files": False,
            "generate_daily_features": True,
            "feature_session": "all",
        },
    }


def queue_daily_ingestion(trade_date: date) -> bool:
    if trade_date.weekday() >= 5 or _day_is_loaded(trade_date) or _day_has_covering_job(trade_date):
        return False
    config = _job_config(trade_date)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rd_jobs(name,status,config) VALUES (%s,'queued',%s) RETURNING id",
                (config["name"], Jsonb(config)),
            )
            job_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO rd_job_events(job_id,event_type,message,details)
                VALUES (%s,'job_created','Automatic E-003C daily maintenance job queued.',%s)
                """,
                (job_id, Jsonb({"trade_date": trade_date.isoformat(), "purpose": "E-003C live evidence inputs"})),
            )
        conn.commit()
    logger.info("Queued E-003C daily ingestion for %s", trade_date)
    return True


def queue_safe_missing_days(now_et: datetime) -> list[str]:
    # The all-session signal uses the full 04:00-20:00 ET US equity day. The current
    # date is only safe to ingest after 20:15 ET; before then, stop at yesterday.
    safe_date = now_et.date() if now_et.timetz().replace(tzinfo=None) >= time(20, 15) else now_et.date() - timedelta(days=1)
    latest = _latest_feature_date()
    start = (latest + timedelta(days=1)) if latest else safe_date
    queued: list[str] = []
    cursor = start
    # Bound automatic repair so an accidental empty database cannot enqueue years.
    earliest = safe_date - timedelta(days=14)
    if cursor < earliest:
        cursor = earliest
    while cursor <= safe_date:
        if cursor.weekday() < 5 and queue_daily_ingestion(cursor):
            queued.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return queued


async def run_daily_maintenance_scheduler(stop_event: asyncio.Event) -> None:
    if not _enabled():
        return
    logger.info("E-003C daily data maintenance scheduler enabled")
    while not stop_event.is_set():
        try:
            now_et = datetime.now(tz=NY)
            queued = queue_safe_missing_days(now_et)
            if queued:
                logger.info("E-003C maintenance queued missing dates: %s", queued)

            freeze_result = freeze_latest_completed_signal()
            if freeze_result.get("frozen"):
                logger.info("E-003C signal freeze created: %s", freeze_result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("E-003C daily data maintenance scheduler error")
        try:
            poll_seconds = max(300.0, float(os.getenv("E003C_MAINTENANCE_POLL_SECONDS", "900")))
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
