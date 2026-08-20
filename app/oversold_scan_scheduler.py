from __future__ import annotations

"""Worker-owned Oversold Reversion scan scheduling.

This removes the web service from the critical path for the nightly scan.  The
worker uses the same canonical scanner and duplicate guards, so primary event
evidence is collected even during a web-service deployment delay.
"""

import asyncio
import logging
import os
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.db import connection
from app.oversold_primary_evidence import PRIMARY_EVIDENCE_VERSION

logger = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")
SCAN_WINDOW_START = time(22, 45)
SCAN_WINDOW_END = time(23, 5)
DEFAULT_POLL_SECONDS = 300.0


def scheduled_scan_due(now_london: datetime, last_run_date: date | None) -> bool:
    local = now_london.astimezone(LONDON) if now_london.tzinfo else now_london.replace(tzinfo=LONDON)
    clock = local.timetz().replace(tzinfo=None)
    return (
        local.weekday() < 5
        and SCAN_WINDOW_START <= clock <= SCAN_WINDOW_END
        and last_run_date != local.date()
    )


def _scan_state() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,status,trigger_source,scan_date,started_at,completed_at,
                       metadata->>'primary_event_evidence_version' AS primary_version,
                       metadata->>'primary_event_evidence_items' AS primary_items
                FROM or_scans
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            latest = cur.fetchone()
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM or_scans
                    WHERE status='running'
                      AND started_at >= now() - interval '30 minutes'
                ) AS scan_running
                """
            )
            running = cur.fetchone()
        conn.rollback()
    return {
        "latest": dict(latest) if latest else None,
        "scan_running": bool(running and running.get("scan_running")),
    }


def bootstrap_scan_required(*, enabled: bool) -> bool:
    if not enabled:
        return False
    state = _scan_state()
    if state["scan_running"]:
        return False
    latest = state["latest"] or {}
    return latest.get("status") != "completed" or latest.get("primary_version") != PRIMARY_EVIDENCE_VERSION


async def _run_scan(trigger_source: str) -> dict[str, Any]:
    # Import after app bootstrap has installed all scanner/evidence patches.
    from app import oversold

    scan_id = oversold._create_scan(
        trigger_source,
        oversold.DEFAULT_MIN_DROP_PCT,
        oversold.DEFAULT_CANDIDATE_LIMIT,
    )
    await oversold.execute_scan(
        scan_id,
        min_drop_pct=oversold.DEFAULT_MIN_DROP_PCT,
        candidate_limit=oversold.DEFAULT_CANDIDATE_LIMIT,
    )
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,status,candidate_count,error,metadata
                FROM or_scans WHERE id=%s
                """,
                (scan_id,),
            )
            row = cur.fetchone()
        conn.rollback()
    return dict(row or {"id": str(scan_id), "status": "unknown"})


async def run_oversold_scan_scheduler(stop_event: asyncio.Event) -> None:
    enabled = os.getenv("OVERSOLD_WORKER_SCAN_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("Oversold Reversion worker scan scheduler disabled")
        return

    poll_seconds = max(60.0, float(os.getenv("OVERSOLD_WORKER_SCAN_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))))
    bootstrap_enabled = os.getenv("OVERSOLD_PRIMARY_BOOTSTRAP_ON_START", "false").strip().lower() in {"1", "true", "yes", "on"}
    last_run_date: date | None = None
    logger.info(
        "Oversold Reversion worker scan scheduler enabled; London window=%s-%s bootstrap=%s",
        SCAN_WINDOW_START.isoformat(timespec="minutes"),
        SCAN_WINDOW_END.isoformat(timespec="minutes"),
        bootstrap_enabled,
    )

    if bootstrap_scan_required(enabled=bootstrap_enabled):
        try:
            result = await _run_scan("manual")
            logger.info("Oversold Reversion primary-evidence bootstrap scan: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Oversold Reversion primary-evidence bootstrap scan failed")

    while not stop_event.is_set():
        try:
            now_london = datetime.now(tz=LONDON)
            if scheduled_scan_due(now_london, last_run_date):
                state = _scan_state()
                if not state["scan_running"]:
                    latest = state["latest"] or {}
                    if not (
                        latest.get("status") == "completed"
                        and latest.get("trigger_source") == "scheduled"
                        and latest.get("scan_date") == now_london.date()
                        and latest.get("primary_version") == PRIMARY_EVIDENCE_VERSION
                    ):
                        result = await _run_scan("scheduled")
                        logger.info("Oversold Reversion worker scheduled scan: %s", result)
                    last_run_date = now_london.date()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Oversold Reversion worker scan scheduler error")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
