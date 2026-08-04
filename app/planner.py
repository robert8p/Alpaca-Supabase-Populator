from __future__ import annotations

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.core import estimate_for, filter_assets
from app.db import connection
from app.models import JobConfig

logger = logging.getLogger(__name__)


def add_event(job_id: str, event_type: str, message: str, *, level: str = "info", task_id: int | None = None, details: dict | None = None) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rd_job_events(job_id, task_id, level, event_type, message, details)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (job_id, task_id, level, event_type, message, Jsonb(details) if details is not None else None),
            )
        conn.commit()


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _date_windows(start_date: date, end_date: date, chunk_days: int) -> Iterable[tuple[datetime, datetime]]:
    cursor = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    exclusive_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    while cursor < exclusive_end:
        nxt = min(cursor + timedelta(days=chunk_days), exclusive_end)
        yield cursor, nxt
        cursor = nxt


def _symbol_hash(symbols: list[str]) -> str:
    return hashlib.sha256(",".join(symbols).encode("utf-8")).hexdigest()[:24]


async def resolve_universe(config: JobConfig, client: AlpacaClient) -> tuple[list[str], list[dict[str, Any]]]:
    assets = await client.list_assets()
    selected = filter_assets(assets, config)
    symbols = [str(asset["symbol"]).upper() for asset in selected]
    return symbols, selected


def save_assets(assets: list[dict[str, Any]]) -> None:
    if not assets:
        return
    rows = []
    for asset in assets:
        asset_id = asset.get("id")
        rows.append(
            (
                str(asset.get("symbol", "")).upper(),
                asset_id if asset_id else None,
                asset.get("class"),
                asset.get("exchange"),
                asset.get("name"),
                asset.get("status"),
                asset.get("tradable"),
                asset.get("marginable"),
                asset.get("shortable"),
                asset.get("easy_to_borrow"),
                asset.get("borrow_status"),
                asset.get("fractionable"),
                Jsonb(asset.get("attributes") or []),
                Jsonb(asset),
            )
        )
    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO rd_assets(
                    symbol, asset_id, asset_class, exchange, name, status, tradable,
                    marginable, shortable, easy_to_borrow, borrow_status, fractionable,
                    attributes, raw, observed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT(symbol) DO UPDATE SET
                    asset_id=excluded.asset_id, asset_class=excluded.asset_class,
                    exchange=excluded.exchange, name=excluded.name, status=excluded.status,
                    tradable=excluded.tradable, marginable=excluded.marginable,
                    shortable=excluded.shortable, easy_to_borrow=excluded.easy_to_borrow,
                    borrow_status=excluded.borrow_status, fractionable=excluded.fractionable,
                    attributes=excluded.attributes, raw=excluded.raw, observed_at=now()
                """,
                rows,
            )
        conn.commit()


def claim_job_for_planning(worker_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, config FROM rd_jobs
                WHERE status='queued'
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            job = cur.fetchone()
            if not job:
                conn.rollback()
                return None
            cur.execute(
                """
                UPDATE rd_jobs SET status='planning', claimed_by=%s, heartbeat_at=now(),
                    started_at=COALESCE(started_at, now()), error=NULL
                WHERE id=%s
                """,
                (worker_id, job["id"]),
            )
        conn.commit()
        return {"id": str(job["id"]), "config": job["config"]}


async def plan_job(job: dict[str, Any], worker_id: str) -> None:
    job_id = job["id"]
    config = JobConfig.model_validate(job["config"])
    add_event(job_id, "planning_started", "Resolving the Alpaca asset universe and creating resumable tasks.")
    try:
        async with AlpacaClient(
            target_rpm=min(config.performance.target_rpm, 1000),
            max_retries=config.performance.max_retries,
            backoff_seconds=config.performance.retry_backoff_seconds,
        ) as client:
            symbols, assets = await resolve_universe(config, client)
        if not symbols:
            raise RuntimeError("The selected universe contains no symbols")
        save_assets(assets)

        task_rows: list[tuple[Any, ...]] = []
        for timeframe in config.timeframes:
            for window_start, window_end in _date_windows(config.start_date, config.end_date, config.performance.date_chunk_days):
                for symbol_batch in _chunks(symbols, config.performance.symbol_batch_size):
                    task_rows.append(
                        (
                            job_id,
                            timeframe,
                            config.feed,
                            config.adjustment,
                            window_start,
                            window_end,
                            symbol_batch,
                            _symbol_hash(symbol_batch),
                        )
                    )

        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM rd_jobs WHERE id=%s FOR UPDATE", (job_id,))
                control = cur.fetchone()["status"]
                if control == "cancel_requested":
                    cur.execute("UPDATE rd_jobs SET status='cancelled',completed_at=now() WHERE id=%s", (job_id,))
                    conn.commit()
                    add_event(job_id, "planning_cancelled", "Job was cancelled before tasks were committed.")
                    return
                cur.executemany(
                    "INSERT INTO rd_job_symbols(job_id, symbol) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    [(job_id, symbol) for symbol in symbols],
                )
                cur.executemany(
                    """
                    INSERT INTO rd_tasks(
                        job_id, timeframe, feed, adjustment, window_start, window_end, symbols, symbols_hash
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    task_rows,
                )
                next_status = "paused" if control == "pause_requested" else "running"
                cur.execute(
                    """
                    UPDATE rd_jobs SET status=%s, symbol_count=%s,
                        total_tasks=(SELECT count(*) FROM rd_tasks WHERE job_id=%s),
                        claimed_by=%s, heartbeat_at=now(), error=NULL
                    WHERE id=%s
                    """,
                    (next_status, len(symbols), job_id, worker_id, job_id),
                )
            conn.commit()
        estimate = estimate_for(config, len(symbols))
        add_event(job_id, "planning_completed", f"Planned {len(task_rows):,} tasks across {len(symbols):,} symbols.", details=estimate)
    except Exception as exc:
        logger.exception("Planning failed for job %s", job_id)
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE rd_jobs SET status='failed', error=%s, completed_at=now() WHERE id=%s", (str(exc), job_id))
            conn.commit()
        add_event(job_id, "planning_failed", str(exc), level="error")
