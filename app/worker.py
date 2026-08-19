from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import time
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from app.adjusted_daily_audit import run_adjusted_daily_audit_once
from app.alpaca import AlpacaClient
from app.blankcanvas_net5_postprocess import run_net5_postprocess_async
from app.config import get_settings
from app.db import assert_database_writable, close_pool, connection, execute_schema
from app.e003c_live import run_e003c_scheduler
from app.intraday_snapshot_compactor import run_intraday_snapshot_compactor
from app.live_maintenance import run_daily_maintenance_scheduler
from app.loader import process_task
from app.models import JobConfig
from app.oversold_outcome_scheduler import run_oversold_outcome_scheduler
from app.planner import add_event, claim_job_for_planning, plan_job
from app.rv30_quote_audit import run_rv30_quote_audit_batch

VERSION = "1.0.14"
logger = logging.getLogger(__name__)
stop_event = asyncio.Event()


def worker_id() -> str:
    return os.getenv("WORKER_ID") or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def heartbeat(worker: str, status: str, job_id: str | None = None, task_ids: list[int] | None = None, details: dict | None = None) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rd_workers(worker_id,status,current_job_id,current_task_ids,version,details,heartbeat_at)
                VALUES (%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT(worker_id) DO UPDATE SET
                    status=excluded.status,current_job_id=excluded.current_job_id,
                    current_task_ids=excluded.current_task_ids,version=excluded.version,
                    details=excluded.details,heartbeat_at=now()
                """,
                (worker, status, job_id, task_ids or [], VERSION, Jsonb(details or {})),
            )
            if job_id:
                cur.execute("UPDATE rd_jobs SET heartbeat_at=now(), claimed_by=%s WHERE id=%s", (worker, job_id))
        conn.commit()


def recover_stale_tasks() -> None:
    stale_seconds = get_settings().worker_stale_seconds
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rd_tasks SET
                    claimed_by=NULL,
                    error=COALESCE(error,'Recovered orphaned staged task after stale worker heartbeat')
                WHERE status='staged'
                  AND claimed_by IS NOT NULL
                  AND (heartbeat_at IS NULL OR heartbeat_at < now() - (%s * interval '1 second'))
                """,
                (stale_seconds,),
            )
            released_staged = cur.rowcount or 0
            cur.execute(
                """
                UPDATE rd_tasks SET
                    status=CASE WHEN status='loading' THEN 'staged' ELSE 'pending' END,
                    claimed_by=NULL,
                    error=COALESCE(error,'Recovered after stale worker heartbeat')
                WHERE status IN ('running','loading')
                  AND (heartbeat_at IS NULL OR heartbeat_at < now() - (%s * interval '1 second'))
                """,
                (stale_seconds,),
            )
            recovered = cur.rowcount or 0
            cur.execute(
                """
                UPDATE rd_jobs SET status='running', claimed_by=NULL
                WHERE status='planning'
                  AND heartbeat_at < now() - (%s * interval '1 second')
                  AND EXISTS (SELECT 1 FROM rd_tasks WHERE job_id=rd_jobs.id)
                """,
                (stale_seconds,),
            )
            cur.execute(
                """
                UPDATE rd_jobs SET status='queued', claimed_by=NULL, error=NULL
                WHERE status='planning'
                  AND heartbeat_at < now() - (%s * interval '1 second')
                  AND NOT EXISTS (SELECT 1 FROM rd_tasks WHERE job_id=rd_jobs.id)
                """,
                (stale_seconds,),
            )
        conn.commit()
    if released_staged:
        logger.warning("Released %s orphaned staged tasks", released_staged)
    if recovered:
        logger.warning("Recovered %s stale running/loading tasks", recovered)


def apply_job_controls() -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rd_jobs SET status='paused'
                WHERE status='pause_requested'
                  AND NOT EXISTS (
                      SELECT 1 FROM rd_tasks
                      WHERE job_id=rd_jobs.id
                        AND (status IN ('running','loading') OR (status='staged' AND claimed_by IS NOT NULL))
                  )
                """
            )
            cur.execute(
                """
                UPDATE rd_tasks SET status='cancelled', completed_at=now()
                WHERE job_id IN (SELECT id FROM rd_jobs WHERE status='cancel_requested')
                  AND (status IN ('pending','failed') OR (status='staged' AND claimed_by IS NULL))
                """
            )
            cur.execute(
                """
                UPDATE rd_jobs SET status='cancelled', completed_at=now()
                WHERE status='cancel_requested'
                  AND NOT EXISTS (
                      SELECT 1 FROM rd_tasks
                      WHERE job_id=rd_jobs.id
                        AND (status IN ('running','loading') OR (status='staged' AND claimed_by IS NOT NULL))
                  )
                """
            )
        conn.commit()


def next_running_job() -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, config FROM rd_jobs
                WHERE status='running'
                  AND EXISTS (
                      SELECT 1 FROM rd_tasks
                      WHERE job_id=rd_jobs.id
                        AND (status IN ('pending','failed') OR (status='staged' AND claimed_by IS NULL))
                  )
                ORDER BY created_at
                LIMIT 1
                """
            )
            row = cur.fetchone()
        conn.rollback()
    if not row:
        return None
    return {"id": str(row["id"]), "config": row["config"]}


def claim_tasks(job_id: str, worker: str, limit: int, max_retries: int) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM rd_tasks
                WHERE job_id=%s
                  AND (status='pending' OR (status='staged' AND claimed_by IS NULL)
                       OR (status='failed' AND attempts < %s))
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (job_id, max_retries, limit),
            )
            tasks = cur.fetchall()
            if tasks:
                ids = [task["id"] for task in tasks]
                cur.execute(
                    """
                    UPDATE rd_tasks SET status='running', claimed_by=%s, heartbeat_at=now(),
                        started_at=COALESCE(started_at,now()), attempts=attempts+1, error=NULL
                    WHERE id=ANY(%s)
                    """,
                    (worker, ids),
                )
        conn.commit()
    return [dict(task) for task in tasks]


def refresh_job_stats(job_id: str) -> dict[str, int]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH stats AS (
                    SELECT
                        count(*) FILTER (WHERE status='completed') AS completed,
                        count(*) FILTER (WHERE status='failed') AS failed,
                        COALESCE(sum(rows_staged),0) AS rows_staged,
                        COALESCE(sum(rows_loaded),0) AS rows_loaded,
                        COALESCE(sum(api_requests),0) AS api_requests,
                        COALESCE(sum(bytes_staged),0) AS bytes_staged
                    FROM rd_tasks WHERE job_id=%s
                )
                UPDATE rd_jobs SET
                    completed_tasks=stats.completed, failed_tasks=stats.failed,
                    rows_staged=stats.rows_staged, rows_loaded=stats.rows_loaded,
                    api_requests=stats.api_requests, bytes_staged=stats.bytes_staged,
                    heartbeat_at=now()
                FROM stats WHERE rd_jobs.id=%s
                RETURNING completed_tasks,failed_tasks,total_tasks
                """,
                (job_id, job_id),
            )
            result = cur.fetchone()
        conn.commit()
    return dict(result or {})


def finalise_if_done(job_id: str, max_retries: int) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status IN ('pending','running','staged','loading')) AS active,
                    count(*) FILTER (WHERE status='failed' AND attempts < %s) AS retryable,
                    count(*) FILTER (WHERE status='failed' AND attempts >= %s) AS exhausted
                FROM rd_tasks WHERE job_id=%s
                """,
                (max_retries, max_retries, job_id),
            )
            state = cur.fetchone()
            if state and state["active"] == 0 and state["retryable"] == 0:
                if state["exhausted"]:
                    cur.execute(
                        "UPDATE rd_jobs SET status='failed', error=%s, completed_at=now() WHERE id=%s AND status='running'",
                        (f"{state['exhausted']} task(s) exhausted their retry limit", job_id),
                    )
                    outcome = "failed"
                else:
                    cur.execute(
                        "UPDATE rd_jobs SET status='completed', completed_at=now(), error=NULL WHERE id=%s AND status='running'",
                        (job_id,),
                    )
                    outcome = "completed"
            else:
                outcome = None
        conn.commit()
    if outcome:
        add_event(job_id, f"job_{outcome}", f"Job {outcome}.", level="error" if outcome == "failed" else "info")


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    if settings.auto_migrate:
        execute_schema()
    else:
        assert_database_writable()
    wid = worker_id()
    recover_stale_tasks()
    last_recovery = time.monotonic()
    heartbeat(wid, "idle", details={"max_global_concurrency": settings.max_global_concurrency})
    logger.info("Worker %s started", wid)

    audit_rows = await run_adjusted_daily_audit_once()
    if audit_rows:
        heartbeat(wid, "adjusted_daily_audit", details={"rows_upserted": audit_rows})
        logger.warning("One-off adjusted daily audit wrote %s rows", audit_rows)

    compactor_task = asyncio.create_task(run_intraday_snapshot_compactor(stop_event), name="blankcanvas-intraday-compactor")
    net5_task = asyncio.create_task(run_net5_postprocess_async(), name="blankcanvas-net5-postprocess")
    await asyncio.sleep(0)
    capture_task = asyncio.create_task(run_e003c_scheduler(stop_event), name="e003c-live-evidence")
    maintenance_task = asyncio.create_task(run_daily_maintenance_scheduler(stop_event), name="e003c-daily-maintenance")
    oversold_outcome_task = asyncio.create_task(
        run_oversold_outcome_scheduler(stop_event),
        name="oversold-reversion-outcomes",
    )

    while not stop_event.is_set():
        try:
            if time.monotonic() - last_recovery >= 60.0:
                recover_stale_tasks()
                last_recovery = time.monotonic()
            apply_job_controls()
            planning_job = claim_job_for_planning(wid)
            if planning_job:
                heartbeat(wid, "planning", planning_job["id"])
                await plan_job(planning_job, wid)
                continue

            job = next_running_job()
            if not job:
                audited = await run_rv30_quote_audit_batch()
                if audited:
                    heartbeat(wid, "rv30_quote_audit", details={"groups_processed": audited})
                    continue
                heartbeat(wid, "idle")
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.worker_poll_seconds)
                except TimeoutError:
                    pass
                continue

            config = JobConfig.model_validate(job["config"])
            concurrency = min(config.performance.concurrency, settings.max_global_concurrency)
            tasks = claim_tasks(job["id"], wid, concurrency, config.performance.max_retries)
            if not tasks:
                refresh_job_stats(job["id"])
                finalise_if_done(job["id"], config.performance.max_retries)
                await asyncio.sleep(0.5)
                continue

            task_ids = [task["id"] for task in tasks]
            heartbeat(wid, "running", job["id"], task_ids)
            async with AlpacaClient(
                target_rpm=config.performance.target_rpm,
                max_retries=config.performance.max_retries,
                backoff_seconds=config.performance.retry_backoff_seconds,
            ) as client:
                await asyncio.gather(
                    *(process_task(task, config, wid, client) for task in tasks),
                    return_exceptions=False,
                )
            refresh_job_stats(job["id"])
            finalise_if_done(job["id"], config.performance.max_retries)
        except Exception:
            logger.exception("Worker loop error")
            heartbeat(wid, "error")
            await asyncio.sleep(max(2, settings.worker_poll_seconds))

    capture_task.cancel()
    maintenance_task.cancel()
    oversold_outcome_task.cancel()
    compactor_task.cancel()
    net5_task.cancel()
    await asyncio.gather(
        capture_task,
        maintenance_task,
        oversold_outcome_task,
        compactor_task,
        net5_task,
        return_exceptions=True,
    )
    heartbeat(wid, "stopped")
    close_pool()


def _signal_handler(*_: Any) -> None:
    stop_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    asyncio.run(run_worker())
