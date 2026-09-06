from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.db import connection
from app.intraday_profitability import _create_scan, _ensure_schema, execute_scan
from app.intraday_profitability_scoring import MODEL_AUDIT_VERSION, SCORING_VERSION
from app.intraday_profitability_tracking import TRACKING_VERSION, run_selected_candidate_tracker
from app.runtime_scope import canonical_schema_managed

logger = logging.getLogger(__name__)
POLL_SECONDS = 2.0
STALE_REQUEST_MINUTES = 30
MAX_SCAN_WAIT_SECONDS = 25 * 60

REQUEST_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ip_scan_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed')),
    direction_filter text NOT NULL DEFAULT 'both' CHECK (direction_filter IN ('both','long','short')),
    min_price double precision NOT NULL DEFAULT 5.0 CHECK (min_price BETWEEN 1.0 AND 1000.0),
    min_prev_dollar_volume double precision NOT NULL DEFAULT 50000000.0 CHECK (min_prev_dollar_volume BETWEEN 1000000.0 AND 50000000000.0),
    min_current_dollar_volume double precision NOT NULL DEFAULT 5000000.0 CHECK (min_current_dollar_volume BETWEEN 100000.0 AND 10000000000.0),
    max_spread_bps double precision NOT NULL DEFAULT 25.0 CHECK (max_spread_bps BETWEEN 1.0 AND 200.0),
    prefilter_limit integer NOT NULL DEFAULT 300 CHECK (prefilter_limit BETWEEN 25 AND 500),
    candidate_limit integer NOT NULL DEFAULT 50 CHECK (candidate_limit BETWEEN 10 AND 100),
    scan_id uuid REFERENCES ip_scans(id) ON DELETE SET NULL,
    requested_by text NOT NULL DEFAULT 'static-app',
    claimed_by text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    requested_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS ip_scan_requests_requested_idx ON ip_scan_requests(requested_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ip_scan_requests_one_active_idx
    ON ip_scan_requests ((1)) WHERE status IN ('queued','running');
ALTER TABLE ip_scan_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE ip_scan_requests FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE ip_scan_requests TO service_role;
"""


def _enrol_scan_candidates(scan_id: UUID) -> int:
    """Enroll every ranked candidate so calibration is not selection-biased."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ip_selected_candidates (
                    candidate_id,scan_id,symbol,name,exchange,direction,setup_type,
                    selected_rank,profitability_score,scan_price,scan_at,market_close_at,
                    market_date,selected_at,user_selected,user_selected_at,auto_enrolled_at,
                    horizon_end_at,status,horizon_status,tracking_version,metadata
                )
                SELECT
                    c.id,c.scan_id,c.symbol,c.name,c.exchange,c.direction,c.setup_type,
                    c.rank,c.profitability_score,c.last_price,s.evidence_cutoff,s.market_close,
                    (s.evidence_cutoff AT TIME ZONE 'UTC')::date,now(),false,NULL,now(),
                    s.horizon_end,'tracking','pending',%s,
                    jsonb_build_object(
                        'source','automatic-all-candidate-calibration',
                        'model_version',s.scoring_version,
                        'original_initial_view',c.initial_view,
                        'original_rationale',c.rationale,
                        'calibration_population','all persisted ranked candidates'
                    )
                FROM ip_candidates c
                JOIN ip_scans s ON s.id=c.scan_id
                WHERE c.scan_id=%s
                  AND s.status='completed'
                ON CONFLICT (candidate_id) DO UPDATE SET
                    horizon_end_at=COALESCE(ip_selected_candidates.horizon_end_at,EXCLUDED.horizon_end_at),
                    auto_enrolled_at=COALESCE(ip_selected_candidates.auto_enrolled_at,EXCLUDED.auto_enrolled_at),
                    tracking_version=EXCLUDED.tracking_version,
                    metadata=ip_selected_candidates.metadata || jsonb_build_object(
                        'automatic_calibration_enrolment_confirmed_at',now(),
                        'calibration_population','all persisted ranked candidates'
                    )
                RETURNING id
                """,
                (TRACKING_VERSION, scan_id),
            )
            count = len(cur.fetchall())
        conn.commit()
    return count


def _backfill_completed_scans() -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id
                FROM ip_scans s
                WHERE s.status='completed'
                  AND EXISTS (SELECT 1 FROM ip_candidates c WHERE c.scan_id=s.id)
                  AND EXISTS (
                      SELECT 1 FROM ip_candidates c
                      WHERE c.scan_id=s.id
                        AND NOT EXISTS (
                            SELECT 1 FROM ip_selected_candidates t WHERE t.candidate_id=c.id
                        )
                  )
                ORDER BY s.started_at DESC
                LIMIT 50
                """
            )
            scan_ids = [row["id"] for row in cur.fetchall()]
        conn.rollback()
    return sum(_enrol_scan_candidates(scan_id) for scan_id in scan_ids)


def ensure_request_schema() -> None:
    if not canonical_schema_managed():
        _ensure_schema()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(REQUEST_SCHEMA_SQL)
            conn.commit()
    enrolled = _backfill_completed_scans()
    if enrolled:
        logger.info("Backfilled %s historical intraday candidate tracking row(s)", enrolled)


def _claim_request(worker_name: str) -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ip_scan_requests
                SET status='failed', error=COALESCE(error,'Recovered as stale after 30 minutes.'), completed_at=now()
                WHERE status='running'
                  AND claimed_at < now() - (%s * interval '1 minute')
                """,
                (STALE_REQUEST_MINUTES,),
            )
            cur.execute(
                """
                SELECT *
                FROM ip_scan_requests
                WHERE status='queued'
                ORDER BY requested_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE ip_scan_requests
                    SET status='running', claimed_by=%s, claimed_at=now(), error=NULL
                    WHERE id=%s
                    RETURNING *
                    """,
                    (worker_name, row["id"]),
                )
                row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def _request_params(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "direction_filter": str(request.get("direction_filter") or "both"),
        "min_price": float(request.get("min_price") or 5.0),
        "min_prev_dollar_volume": float(request.get("min_prev_dollar_volume") or 50_000_000.0),
        "min_current_dollar_volume": float(request.get("min_current_dollar_volume") or 5_000_000.0),
        "max_spread_bps": float(request.get("max_spread_bps") or 25.0),
        "prefilter_limit": int(request.get("prefilter_limit") or 300),
        "candidate_limit": int(request.get("candidate_limit") or 50),
    }


def _set_scan_id(request_id: UUID, scan_id: UUID, *, duplicate: bool) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ip_scan_requests
                SET scan_id=%s,
                    metadata=metadata || %s::jsonb
                WHERE id=%s
                """,
                (scan_id, Jsonb({"attached_to_existing_scan": duplicate}), request_id),
            )
        conn.commit()


def _scan_state(scan_id: UUID) -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status,error,candidate_count,completed_at FROM ip_scans WHERE id=%s", (scan_id,))
            row = cur.fetchone()
        conn.rollback()
    return dict(row) if row else None


def _mark_scan_provenance(scan_id: UUID) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ip_scans
                SET scoring_version=%s,
                    metadata=metadata || %s::jsonb
                WHERE id=%s AND status='completed'
                """,
                (
                    SCORING_VERSION,
                    Jsonb(
                        {
                            "heuristic_review": "reliability-v3",
                            "model_audit_version": MODEL_AUDIT_VERSION,
                            "score_interpretation": "analysis priority only; not probability or validated edge",
                            "trade_gate": "blocked",
                            "outcome_tracking": "all ranked candidates; next-minute entry, 120-minute horizon and close",
                        }
                    ),
                    scan_id,
                ),
            )
        conn.commit()


async def _wait_for_scan(scan_id: UUID, stop_event: asyncio.Event) -> dict[str, Any]:
    waited = 0.0
    while not stop_event.is_set() and waited < MAX_SCAN_WAIT_SECONDS:
        state = _scan_state(scan_id)
        if state and state.get("status") != "running":
            return state
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
        except TimeoutError:
            waited += POLL_SECONDS
    if stop_event.is_set():
        raise asyncio.CancelledError
    raise TimeoutError(f"Intraday profitability scan {scan_id} exceeded the worker wait limit")


def _finish_request(
    request_id: UUID,
    *,
    status: str,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ip_scan_requests
                SET status=%s,
                    error=%s,
                    metadata=metadata || %s::jsonb,
                    completed_at=now()
                WHERE id=%s
                """,
                (status, error[:4_000] if error else None, Jsonb(metadata or {}), request_id),
            )
        conn.commit()


async def _process_request(request: dict[str, Any], stop_event: asyncio.Event) -> None:
    request_id = request["id"]
    params = _request_params(request)
    scan_id: UUID | None = None
    try:
        scan_id, duplicate = _create_scan(**params)
        _set_scan_id(request_id, scan_id, duplicate=duplicate)
        logger.info("Intraday request %s attached to scan %s (duplicate=%s)", request_id, scan_id, duplicate)
        if duplicate:
            state = await _wait_for_scan(scan_id, stop_event)
        else:
            await execute_scan(scan_id, **params)
            state = _scan_state(scan_id) or {"status": "failed", "error": "Scan result was not persisted."}

        if state.get("status") == "completed":
            await asyncio.to_thread(_mark_scan_provenance, scan_id)
            enrolled = await asyncio.to_thread(_enrol_scan_candidates, scan_id)
            _finish_request(
                request_id,
                status="completed",
                metadata={
                    "candidate_count": int(state.get("candidate_count") or 0),
                    "automatic_tracking_rows": enrolled,
                    "model_audit_version": MODEL_AUDIT_VERSION,
                },
            )
            logger.info("Intraday request %s completed with scan %s; tracking rows=%s", request_id, scan_id, enrolled)
        else:
            message = str(state.get("error") or f"Scan ended with status {state.get('status')}")
            _finish_request(request_id, status="failed", error=message)
            logger.warning("Intraday request %s failed: %s", request_id, message)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Intraday request %s crashed", request_id)
        _finish_request(
            request_id,
            status="failed",
            error=str(exc),
            metadata={"scan_id": str(scan_id) if scan_id else None},
        )


async def _run_request_queue(stop_event: asyncio.Event) -> None:
    ensure_request_schema()
    worker_name = f"intraday-profitability:{socket.gethostname()}"
    logger.info("Intraday reliability-first request scheduler started as %s", worker_name)
    while not stop_event.is_set():
        try:
            request = await asyncio.to_thread(_claim_request, worker_name)
            if request:
                await _process_request(request, stop_event)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Intraday request scheduler loop error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
        except TimeoutError:
            pass


async def run_intraday_profitability_request_scheduler(stop_event: asyncio.Event) -> None:
    request_task = asyncio.create_task(_run_request_queue(stop_event), name="intraday-profitability-request-queue")
    tracker_task = asyncio.create_task(run_selected_candidate_tracker(stop_event), name="intraday-all-candidate-outcomes")
    try:
        await asyncio.gather(request_task, tracker_task)
    finally:
        request_task.cancel()
        tracker_task.cancel()
        await asyncio.gather(request_task, tracker_task, return_exceptions=True)
