from __future__ import annotations

import logging
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
from app.oversold_tracking import (
    capture_due_checkpoints,
    list_tracked,
    sync_candidate_tracking,
)

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
PUBLIC_MANUAL_COOLDOWN_SECONDS = 300
CURRENT_DECISIONS = ("investigate", "watch", "pass", "reject")
TRACKED_DECISIONS = ("investigate", "pass")


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


def _latest_decision_rows(limit: int = 500) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (c.symbol)
                        c.id,c.scan_id,c.rank,c.symbol,c.name,c.exchange,
                        c.prev_close,c.last_price,c.drop_pct,c.prev_dollar_volume,c.spread_pct,
                        c.catalyst_class,c.catalyst_summary,c.risk_flags,c.headline_count,
                        c.heuristic_score,c.triage_label,c.decision,c.review_notes,c.reviewed_at,
                        s.started_at AS scan_started_at,s.trigger_source
                    FROM or_candidates c
                    JOIN or_scans s ON s.id=c.scan_id
                    WHERE c.decision <> 'unreviewed'
                    ORDER BY c.symbol,c.reviewed_at DESC NULLS LAST,c.id DESC
                )
                SELECT *
                FROM latest
                WHERE decision = ANY(%s)
                ORDER BY reviewed_at DESC NULLS LAST,id DESC
                LIMIT %s
                """,
                (list(CURRENT_DECISIONS), limit),
            )
            rows = cur.fetchall()
        conn.rollback()
    return rows


async def _ensure_current_tracks(limit: int = 100) -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (c.symbol)
                        c.id,c.symbol,c.decision,c.reviewed_at
                    FROM or_candidates c
                    WHERE c.decision <> 'unreviewed'
                    ORDER BY c.symbol,c.reviewed_at DESC NULLS LAST,c.id DESC
                )
                SELECT l.id,l.decision
                FROM latest l
                WHERE l.decision = ANY(%s)
                  AND NOT EXISTS (
                    SELECT 1
                    FROM or_decision_tracks t
                    WHERE t.candidate_id=l.id
                      AND t.decision=l.decision
                      AND t.active=true
                  )
                ORDER BY l.reviewed_at DESC NULLS LAST,l.id DESC
                LIMIT %s
                """,
                (list(TRACKED_DECISIONS), limit),
            )
            rows = cur.fetchall()
        conn.rollback()

    created = 0
    for row in rows:
        try:
            await sync_candidate_tracking(row["id"], row["decision"])
            created += 1
        except Exception:
            logger.exception("Failed to initialise current track for candidate %s", row["id"])
    return created


@router.get("/oversold", response_class=HTMLResponse)
def oversold_page(request: Request):
    html = templates.get_template("oversold.html").render(request=request)
    html = html.replace(
        '<a href="/" style="margin-left:8px;color:var(--muted)">Rapid Discovery</a>',
        "",
    )
    html = html.replace(
        "</body>",
        '<script src="/static/oversold_tracking_v3.js?v=1"></script>\n'
        '<script src="/static/oversold_top5.js?v=3"></script>\n'
        '<script src="/static/oversold_chatgpt_score.js?v=1"></script>\n</body>',
    )
    return HTMLResponse(content=html)


@router.get("/api/oversold/latest")
def latest_scan() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM or_scans ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
        conn.rollback()
    return {"scan": None, "candidates": []} if not row else _scan_detail(row["id"])


@router.get("/api/oversold/scans")
def scan_history(limit: int = Query(30, ge=1, le=100)) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.id,s.status,s.trigger_source,s.scan_date,s.min_drop_pct,s.candidate_limit,
                    s.asset_count,s.snapshot_count,s.candidate_count,s.started_at,s.completed_at,s.error,
                    count(c.id) FILTER (WHERE c.decision='unreviewed') AS unreviewed_count,
                    count(c.id) FILTER (WHERE c.decision='investigate') AS investigate_count,
                    count(c.id) FILTER (WHERE c.decision='watch') AS watch_count,
                    count(c.id) FILTER (WHERE c.decision='pass') AS pass_count,
                    count(c.id) FILTER (WHERE c.decision='reject') AS reject_count,
                    count(c.id) FILTER (WHERE c.decision='traded') AS traded_count
                FROM or_scans s
                LEFT JOIN or_candidates c ON c.scan_id=s.id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.rollback()
    return rows


@router.get("/api/oversold/scans/{scan_id}")
def scan_detail(scan_id: UUID) -> dict[str, Any]:
    return _scan_detail(scan_id)


@router.get("/api/oversold/decision-board")
def decision_board() -> dict[str, Any]:
    rows = _latest_decision_rows()
    history = list_tracked()
    active_by_candidate: dict[int, dict[str, Any]] = {}
    for decision in TRACKED_DECISIONS:
        for track in history.get(decision, []):
            if track.get("active"):
                active_by_candidate[int(track["candidate_id"])] = track

    board = {decision: [] for decision in CURRENT_DECISIONS}
    for row in rows:
        row["tracking"] = active_by_candidate.get(int(row["id"]))
        board[row["decision"]].append(row)
    return board


@router.get("/api/oversold/tracked")
async def tracked_outcomes() -> dict[str, Any]:
    await _ensure_current_tracks()
    return list_tracked()


@router.post("/api/oversold/outcomes/run")
async def run_outcome_capture(request: Request) -> dict[str, int]:
    _require_scheduled_token(request)
    return await capture_due_checkpoints()


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
async def update_candidate(candidate_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision") or "").lower()
    if decision not in {"unreviewed", "watch", "investigate", "pass", "reject", "traded"}:
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
            if decision not in TRACKED_DECISIONS:
                cur.execute(
                    """
                    UPDATE or_decision_tracks
                    SET active=false,ended_at=COALESCE(ended_at,now()),updated_at=now()
                    WHERE active=true
                      AND symbol=(SELECT symbol FROM or_candidates WHERE id=%s)
                    """,
                    (candidate_id,),
                )
        conn.commit()

    try:
        track = await sync_candidate_tracking(candidate_id, decision)
        row["tracking"] = {
            "active": bool(track and track.get("active")),
            "decision": track.get("decision") if track else None,
            "track_id": track.get("id") if track else None,
        }
    except Exception as exc:
        logger.exception("Decision saved but tracking sync failed for candidate %s", candidate_id)
        row["tracking_error"] = str(exc)[:1000]
    return row
