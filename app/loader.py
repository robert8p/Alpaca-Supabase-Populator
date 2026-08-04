from __future__ import annotations

import asyncio
import csv
import gzip
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg import sql

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.core import classify_session, in_selected_session
from app.db import connection
from app.features import refresh_daily_features
from app.models import JobConfig
from app.planner import add_event

logger = logging.getLogger(__name__)
CSV_FIELDS = [
    "symbol", "bar_ts", "timeframe", "feed", "adjustment", "session_label",
    "open", "high", "low", "close", "volume", "trade_count", "vwap", "loaded_by_job_id",
]


class TaskControl(RuntimeError):
    def __init__(self, action: str):
        super().__init__(action)
        self.action = action


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _job_control(job_id: str) -> str:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM rd_jobs WHERE id=%s", (job_id,))
            row = cur.fetchone()
        conn.rollback()
    return row["status"] if row else "cancel_requested"




def _is_cancel(control: str) -> bool:
    return control in {"cancel_requested", "cancelled"}


def _is_pause(control: str) -> bool:
    return control in {"pause_requested", "paused"}

def _task_path(job_id: str, task_id: int) -> Path:
    base = get_settings().staging_dir / job_id
    base.mkdir(parents=True, exist_ok=True)
    return base / f"task_{task_id}.csv.gz"


def _checkpoint(task_id: int, *, page_token: str | None, pages: int, rows: int, requests: int, path: Path) -> str:
    size = path.stat().st_size if path.exists() else 0
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH updated AS (
                    UPDATE rd_tasks SET page_token=%s, pages_completed=%s, rows_staged=%s,
                        api_requests=%s, bytes_staged=%s, staging_path=%s, heartbeat_at=now(),
                        status=CASE WHEN %s::text IS NULL THEN 'staged' ELSE 'running' END
                    WHERE id=%s
                    RETURNING job_id
                )
                SELECT j.status FROM rd_jobs j JOIN updated u ON u.job_id=j.id
                """,
                (page_token, pages, rows, requests, size, str(path), page_token, task_id),
            )
            row = cur.fetchone()
        conn.commit()
    return row["status"] if row else "cancel_requested"


def _write_page(writer: csv.DictWriter, bars_payload: dict[str, list[dict[str, Any]]], task: dict[str, Any], config: JobConfig) -> int:
    written = 0
    for symbol, bars in bars_payload.items():
        for bar in bars:
            ts = parse_timestamp(bar["t"])
            if not in_selected_session(ts, config):
                continue
            writer.writerow(
                {
                    "symbol": symbol,
                    "bar_ts": ts.isoformat(),
                    "timeframe": task["timeframe"],
                    "feed": task["feed"],
                    "adjustment": task["adjustment"],
                    "session_label": classify_session(ts),
                    "open": bar["o"],
                    "high": bar["h"],
                    "low": bar["l"],
                    "close": bar["c"],
                    "volume": int(bar.get("v") or 0),
                    "trade_count": bar.get("n"),
                    "vwap": bar.get("vw"),
                    "loaded_by_job_id": str(task["job_id"]),
                }
            )
            written += 1
    return written


def ensure_monthly_partitions(cur, start: datetime, end: datetime) -> None:
    cursor = datetime(start.year, start.month, 1, tzinfo=UTC)
    while cursor < end:
        if cursor.month == 12:
            nxt = datetime(cursor.year + 1, 1, 1, tzinfo=UTC)
        else:
            nxt = datetime(cursor.year, cursor.month + 1, 1, tzinfo=UTC)
        partition_name = f"rd_bars_{cursor:%Y%m}"
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (partition_name,))
        cur.execute(
            sql.SQL("CREATE TABLE IF NOT EXISTS {} PARTITION OF rd_bars FOR VALUES FROM ({}) TO ({})").format(
                sql.Identifier(partition_name), sql.Literal(cursor), sql.Literal(nxt)
            )
        )
        cursor = nxt


def bulk_load(task: dict[str, Any], config: JobConfig, path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Staging file is missing: {path}")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '30min'")
            ensure_monthly_partitions(cur, task["window_start"], task["window_end"] + timedelta(seconds=1))
            cur.execute(
                """
                CREATE TEMP TABLE temp_rd_bars (
                    symbol text NOT NULL,
                    bar_ts timestamptz NOT NULL,
                    timeframe text NOT NULL,
                    feed text NOT NULL,
                    adjustment text NOT NULL,
                    session_label text NOT NULL,
                    open double precision NOT NULL,
                    high double precision NOT NULL,
                    low double precision NOT NULL,
                    close double precision NOT NULL,
                    volume bigint NOT NULL,
                    trade_count bigint,
                    vwap double precision,
                    loaded_by_job_id uuid
                ) ON COMMIT DROP
                """
            )
            with gzip.open(path, "rb") as handle:
                with cur.copy(
                    """
                    COPY temp_rd_bars(
                        symbol,bar_ts,timeframe,feed,adjustment,session_label,
                        open,high,low,close,volume,trade_count,vwap,loaded_by_job_id
                    ) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)
                    """
                ) as copy:
                    while chunk := handle.read(1024 * 1024):
                        copy.write(chunk)

            cur.execute("SELECT min(bar_ts) AS min_ts, max(bar_ts) AS max_ts FROM temp_rd_bars")
            staged_bounds = cur.fetchone()

            if config.storage.conflict_policy == "update":
                conflict_sql = """
                    DO UPDATE SET
                        session_label=excluded.session_label, open=excluded.open,
                        high=excluded.high, low=excluded.low, close=excluded.close,
                        volume=excluded.volume, trade_count=excluded.trade_count,
                        vwap=excluded.vwap, loaded_by_job_id=excluded.loaded_by_job_id,
                        loaded_at=now()
                """
            else:
                conflict_sql = "DO NOTHING"
            cur.execute(
                f"""
                INSERT INTO rd_bars(
                    symbol,bar_ts,timeframe,feed,adjustment,session_label,
                    open,high,low,close,volume,trade_count,vwap,loaded_by_job_id
                )
                SELECT DISTINCT ON (symbol,timeframe,feed,adjustment,bar_ts)
                    symbol,bar_ts,timeframe,feed,adjustment,session_label,
                    open,high,low,close,volume,trade_count,vwap,loaded_by_job_id
                FROM temp_rd_bars
                ORDER BY symbol,timeframe,feed,adjustment,bar_ts
                ON CONFLICT(symbol,timeframe,feed,adjustment,bar_ts) {conflict_sql}
                """
            )
            loaded = max(cur.rowcount or 0, 0)
            cur.execute(
                """
                INSERT INTO rd_inventory(
                    timeframe,feed,adjustment,min_bar_ts,max_bar_ts,rows_loaded,
                    loads_completed,last_job_id,last_loaded_at
                ) VALUES (%s,%s,%s,%s,%s,%s,1,%s,now())
                ON CONFLICT(timeframe,feed,adjustment) DO UPDATE SET
                    min_bar_ts=LEAST(rd_inventory.min_bar_ts,excluded.min_bar_ts),
                    max_bar_ts=GREATEST(rd_inventory.max_bar_ts,excluded.max_bar_ts),
                    rows_loaded=rd_inventory.rows_loaded+excluded.rows_loaded,
                    loads_completed=rd_inventory.loads_completed+1,
                    last_job_id=excluded.last_job_id,last_loaded_at=now()
                """,
                (
                    task["timeframe"], task["feed"], task["adjustment"],
                    staged_bounds["min_ts"], staged_bounds["max_ts"], loaded, task["job_id"],
                ),
            )
        conn.commit()
    return loaded


async def process_task(task: dict[str, Any], config: JobConfig, worker_id: str, client: AlpacaClient) -> None:
    task_id = task["id"]
    job_id = str(task["job_id"])
    path = Path(task["staging_path"]) if task.get("staging_path") else _task_path(job_id, task_id)
    original_status = task.get("status")
    download_complete = original_status == "staged"
    page_token = task.get("page_token")
    pages = int(task.get("pages_completed") or 0)
    rows_staged = int(task.get("rows_staged") or 0)
    requests = int(task.get("api_requests") or 0)

    if (page_token or download_complete) and not path.exists():
        download_complete = False
        page_token = None
        pages = rows_staged = requests = 0
        add_event(job_id, "checkpoint_reset", "Staging file was absent, so this task restarted safely from page one.", task_id=task_id, level="warning")

    try:
        control = await asyncio.to_thread(_job_control, job_id)
        while not download_complete:
            if _is_cancel(control):
                raise TaskControl("cancel")
            if _is_pause(control):
                raise TaskControl("pause")

            result = await client.fetch_bars_page(
                symbols=task["symbols"],
                timeframe=task["timeframe"],
                start=task["window_start"].isoformat(),
                end=task["window_end"].isoformat(),
                feed=task["feed"],
                adjustment=task["adjustment"],
                asof=config.asof.isoformat() if config.asof else None,
                limit=config.performance.page_limit,
                page_token=page_token,
            )
            payload = result.data
            bars_payload = payload.get("bars") or {}
            new_file = not path.exists() or path.stat().st_size == 0
            # Close after every page. Each append is a complete gzip member, so a hard
            # process stop cannot leave all previously checkpointed pages unreadable.
            with gzip.open(path, "at", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
                if new_file:
                    writer.writeheader()
                rows_staged += _write_page(writer, bars_payload, task, config)
            page_token = payload.get("next_page_token")
            pages += 1
            requests += 1
            control = await asyncio.to_thread(
                _checkpoint, task_id, page_token=page_token, pages=pages,
                rows=rows_staged, requests=requests, path=path
            )
            if _is_cancel(control):
                raise TaskControl("cancel")
            if _is_pause(control):
                raise TaskControl("pause_staged" if not page_token else "pause")
            if not page_token:
                download_complete = True
                break

        control = await asyncio.to_thread(_job_control, job_id)
        if _is_cancel(control):
            raise TaskControl("cancel")
        if _is_pause(control):
            raise TaskControl("pause_staged")

        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE rd_tasks SET status='loading', heartbeat_at=now() WHERE id=%s", (task_id,))
            conn.commit()

        loaded = await asyncio.to_thread(bulk_load, task, config, path)
        feature_rows = 0
        if config.storage.generate_daily_features and rows_staged:
            feature_rows = await asyncio.to_thread(refresh_daily_features, task, config)

        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE rd_tasks SET status='completed', rows_loaded=%s,
                        page_token=NULL, completed_at=now(), heartbeat_at=now(), error=NULL
                    WHERE id=%s
                    """,
                    (loaded, task_id),
                )
                cur.execute("UPDATE rd_jobs SET feature_rows=feature_rows+%s WHERE id=%s", (feature_rows, job_id))
            conn.commit()
        if not config.storage.keep_staging_files:
            path.unlink(missing_ok=True)
    except TaskControl as control:
        new_status = {
            "cancel": "cancelled",
            "pause_staged": "staged",
        }.get(control.action, "pending")
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE rd_tasks SET status=%s, claimed_by=NULL, heartbeat_at=now() WHERE id=%s",
                    (new_status, task_id),
                )
            conn.commit()
        if control.action == "cancel" and not config.storage.keep_staging_files:
            path.unlink(missing_ok=True)
    except Exception as exc:
        # Alpaca pagination tokens can become invalid after a long pause or provider-side expiry.
        # Restarting the task from page one is safe because the destination key deduplicates bars.
        if page_token and "HTTP 400" in str(exc):
            path.unlink(missing_ok=True)
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE rd_tasks SET status='pending', page_token=NULL, pages_completed=0,
                            rows_staged=0, api_requests=0, bytes_staged=0, staging_path=NULL,
                            claimed_by=NULL, error='Pagination checkpoint expired; restarting task'
                        WHERE id=%s
                        """,
                        (task_id,),
                    )
                conn.commit()
            add_event(job_id, "checkpoint_expired", "Alpaca rejected the saved page token; the task will restart safely from page one.", task_id=task_id, level="warning")
            return
        logger.exception("Task %s failed", task_id)
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE rd_tasks SET status='failed', error=%s, heartbeat_at=now(),
                        staging_path=%s WHERE id=%s
                    """,
                    (str(exc), str(path), task_id),
                )
            conn.commit()
        add_event(job_id, "task_failed", str(exc), task_id=task_id, level="error")
