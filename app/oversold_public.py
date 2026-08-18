from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connection
from app.oversold import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_MIN_DROP_PCT,
    LONDON,
    MAX_CANDIDATE_LIMIT,
    _create_scan,
    _existing_scheduled_scan,
    _scan_detail,
    execute_scan,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
PUBLIC_MANUAL_COOLDOWN_SECONDS = 300


def _require_scheduled_token(request: Request) -> None:
    expected = os.getenv("OVERSOLD_TRIGGER_TOKEN", "")
    supplied = request.headers.get("X-Oversold-Token", "")
    if not expected or not supplied or not secrets.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(status_code=401, detail="Scheduled trigger authentication required")


def _recent_manual_scan() -> dict[str, Any] | None:
    cutoff = datetime.now(LONDON).astimezone() - timedelta(seconds=PUBLIC_MANUAL_COOLDOWN_SECONDS)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,status,started_at,completed_at
                FROM or_scans
                WHERE trigger_source='manual'
                  AND started_at >= %s
                  AND status IN ('running','completed')
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (cutoff,),
            )
            row = cur.fetchone()
        conn.rollback()
    return row


@router.get("/oversold", response_class=HTMLResponse)
def oversold_page(request: Request):
    return templates.TemplateResponse("oversold.html", {"request": request})


@router.get("/api/oversold/latest")
def latest_scan() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM or_scans ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
        conn.rollback()
    return {"scan": None, "candidates": []} if not row else _scan_detail(row["id"])


@router.get("/api/oversold/scans/{scan_id}")
def scan_detail(scan_id: UUID) -> dict[str, Any]:
    return _scan_detail(scan_id)


@router.post("/api/oversold/run", status_code=202)
async def run_scan(
    background_tasks: BackgroundTasks,
    request: Request,
    scheduled: bool = Query(False),
    background: bool = Query(True),
    min_drop_pct: float = Query(DEFAULT_MIN_DROP_PCT, ge=5, le=90),
    candidate_limit: int = Query(DEFAULT_CANDIDATE_LIMIT, ge=1, le=MAX_CANDIDATE_LIMIT),
) -> dict[str, Any]:
    if scheduled:
        _require_scheduled_token(request)
        local_now = datetime.now(LONDON)
        if not (local_now.weekday() < 5 and local_now.hour == 22 and 45 <= local_now.minute <= 59):
            return {"status": "skipped", "reason": "outside_london_scan_window", "local_time": local_now.isoformat()}
        existing = _existing_scheduled_scan()
        if existing:
            return {"status": existing["status"], "scan_id": existing["id"], "duplicate": True}
        trigger_source = "scheduled"
    else:
        recent = _recent_manual_scan()
        if recent:
            return {
                "status": recent["status"],
                "scan_id": recent["id"],
                "duplicate": True,
                "cooldown_seconds": PUBLIC_MANUAL_COOLDOWN_SECONDS,
            }
        trigger_source = "manual"

    scan_id = _create_scan(trigger_source, min_drop_pct, candidate_limit)
    if background:
        background_tasks.add_task(
            execute_scan,
            scan_id,
            min_drop_pct=min_drop_pct,
            candidate_limit=candidate_limit,
        )
        return {"status": "running", "scan_id": scan_id, "trigger_source": trigger_source}

    await execute_scan(scan_id, min_drop_pct=min_drop_pct, candidate_limit=candidate_limit)
    return _scan_detail(scan_id)


@router.patch("/api/oversold/candidates/{candidate_id}")
def update_candidate(candidate_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision") or "").lower()
    if decision not in {"unreviewed", "watch", "investigate", "pass", "traded"}:
        raise HTTPException(400, "Invalid decision")
    review_notes = str(payload.get("review_notes") or "")[:4000]
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE or_candidates
                SET decision=%s,review_notes=%s,reviewed_at=now()
                WHERE id=%s
                RETURNING id,decision,review_notes,reviewed_at
                """,
                (decision, review_notes, candidate_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Candidate not found")
        conn.commit()
    return row
