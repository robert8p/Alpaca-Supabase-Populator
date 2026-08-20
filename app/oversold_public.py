from __future__ import annotations

import asyncio
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
from app.oversold_calibration import active_calibration_from_cursor
from app.oversold_calibration_runtime import run_calibration_if_changed
from app.oversold_corporate_actions import review_corporate_actions
from app.oversold_outcomes import capture_signal_outcomes
from app.oversold_scoring import SCORING_CONFIG, public_scoring_contract
from app.oversold_tracking import capture_due_checkpoints, list_tracked, sync_candidate_tracking

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
                WHERE trigger_source='manual' AND started_at >= %s
                  AND status IN ('running','completed')
                ORDER BY started_at DESC LIMIT 1
                """,
                (cutoff,),
            )
            row = cur.fetchone()
        conn.rollback()
    return row


def _enrich_scan_calibration(detail: dict[str, Any]) -> dict[str, Any]:
    candidates = detail.get("candidates") or []
    model_run_ids = [int(row["model_run_id"]) for row in candidates if row.get("model_run_id") is not None]
    if not model_run_ids:
        return detail
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,model_status,calibration_model_version,calibrated_probability
                FROM or_model_runs WHERE id=ANY(%s)
                """,
                (model_run_ids,),
            )
            projections = {int(row["id"]): dict(row) for row in cur.fetchall()}
        conn.rollback()
    for row in candidates:
        projection = projections.get(int(row["model_run_id"])) if row.get("model_run_id") is not None else None
        if not projection:
            continue
        row["model_status"] = projection.get("model_status")
        row["calibration_model_version"] = projection.get("calibration_model_version")
        row["calibrated_probability"] = projection.get("calibrated_probability")
    return detail


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
                SELECT l.*,mr.final_score AS reversion_score,mr.model_status,mr.calibrated_probability,
                       mr.calibration_model_version,mr.verdict AS model_verdict,
                       mr.damage_risk,mr.evidence_confidence,mr.scoring_model_version
                FROM latest l
                LEFT JOIN LATERAL (
                    SELECT * FROM or_model_runs x WHERE x.candidate_id=l.id AND x.run_kind='original'
                    ORDER BY x.created_at ASC,x.id ASC LIMIT 1
                ) mr ON true
                WHERE l.decision = ANY(%s)
                ORDER BY l.reviewed_at DESC NULLS LAST,l.id DESC
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
                    SELECT DISTINCT ON (c.symbol) c.id,c.symbol,c.decision,c.reviewed_at
                    FROM or_candidates c WHERE c.decision <> 'unreviewed'
                    ORDER BY c.symbol,c.reviewed_at DESC NULLS LAST,c.id DESC
                )
                SELECT l.id,l.decision FROM latest l
                WHERE l.decision = ANY(%s)
                  AND NOT EXISTS (
                    SELECT 1 FROM or_decision_tracks t
                    WHERE t.candidate_id=l.id AND t.decision=l.decision AND t.active=true
                  )
                ORDER BY l.reviewed_at DESC NULLS LAST,l.id DESC LIMIT %s
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


def _model_diagnostics() -> dict[str, Any]:
    versions = SCORING_CONFIG["versions"]
    model_version = versions["scoring_model_version"]
    config_version = versions["scoring_config_version"]
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    count(*) AS scored_signals,
                    count(*) FILTER (WHERE mr.model_status='calibrated') AS calibrated_predictions,
                    count(*) FILTER (WHERE mr.missing_inputs @> '[\"company_specific_news\"]'::jsonb) AS missing_news_count,
                    count(*) FILTER (WHERE mr.missing_inputs @> '[\"point_in_time_fundamentals\"]'::jsonb) AS missing_fundamentals_count,
                    count(*) FILTER (WHERE mr.missing_inputs @> '[\"enrichment_partial_failure\"]'::jsonb) AS enrichment_failure_count,
                    count(*) FILTER (WHERE mr.hard_veto) AS hard_veto_count,
                    count(*) FILTER (WHERE (mr.catalyst_analysis->>'analysis_method') LIKE 'rules_%') AS rules_without_llm_count,
                    count(*) FILTER (WHERE so.status='matured') AS matured_outcomes,
                    count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration) AS calibration_eligible_matured,
                    count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration AND so.hit_plus_5pct_within_6_weeks=true) AS eligible_hits,
                    count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration AND so.hit_plus_5pct_within_6_weeks=false) AS eligible_misses,
                    count(*) FILTER (WHERE so.status='matured' AND so.corporate_action_status='affected') AS corporate_action_exclusions,
                    count(*) FILTER (WHERE so.status='matured' AND so.corporate_action_status='unchecked') AS corporate_action_unchecked,
                    avg(so.mfe_6w) FILTER (WHERE so.status='matured') AS average_mfe,
                    avg(so.mae_6w) FILTER (WHERE so.status='matured') AS average_mae,
                    avg(so.hours_to_plus_5) FILTER (WHERE so.first_plus_5_ts IS NOT NULL) AS average_hours_to_target
                FROM or_model_runs mr
                LEFT JOIN or_signal_outcomes so ON so.model_run_id=mr.id
                WHERE mr.run_kind='original'
                  AND mr.scoring_model_version=%s
                  AND mr.scoring_config_version=%s
                """,
                (model_version, config_version),
            )
            summary = cur.fetchone() or {}
            cur.execute(
                """
                SELECT
                    LEAST(9,FLOOR(mr.final_score/10)::int) AS bucket,
                    count(*) AS sample_count,
                    count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration) AS matured_count,
                    count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration AND so.hit_plus_5pct_within_6_weeks) AS hit_count,
                    avg(so.mfe_6w) FILTER (WHERE so.status='matured') AS average_mfe,
                    avg(so.mae_6w) FILTER (WHERE so.status='matured') AS average_mae
                FROM or_model_runs mr
                LEFT JOIN or_signal_outcomes so ON so.model_run_id=mr.id
                WHERE mr.run_kind='original'
                  AND mr.scoring_model_version=%s
                  AND mr.scoring_config_version=%s
                GROUP BY 1 ORDER BY 1
                """,
                (model_version, config_version),
            )
            buckets = cur.fetchall()
            cur.execute(
                """
                SELECT COALESCE(es.sector_hint,'unknown') AS sector,
                       count(*) AS sample_count,
                       count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration) AS matured_count,
                       count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration AND so.hit_plus_5pct_within_6_weeks) AS hit_count
                FROM or_model_runs mr
                JOIN or_evidence_snapshots es ON es.id=mr.evidence_snapshot_id
                LEFT JOIN or_signal_outcomes so ON so.model_run_id=mr.id
                WHERE mr.run_kind='original'
                  AND mr.scoring_model_version=%s
                  AND mr.scoring_config_version=%s
                GROUP BY 1 ORDER BY sample_count DESC
                """,
                (model_version, config_version),
            )
            sectors = cur.fetchall()
            cur.execute(
                """
                SELECT COALESCE(mr.catalyst_analysis->>'catalyst_type','unknown') AS catalyst_type,
                       count(*) AS sample_count,
                       count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration) AS matured_count,
                       count(*) FILTER (WHERE so.status='matured' AND so.eligible_for_calibration AND so.hit_plus_5pct_within_6_weeks) AS hit_count
                FROM or_model_runs mr
                LEFT JOIN or_signal_outcomes so ON so.model_run_id=mr.id
                WHERE mr.run_kind='original'
                  AND mr.scoring_model_version=%s
                  AND mr.scoring_config_version=%s
                GROUP BY 1 ORDER BY sample_count DESC
                """,
                (model_version, config_version),
            )
            catalysts = cur.fetchall()
            cur.execute(
                """
                SELECT * FROM or_calibration_runs
                WHERE scoring_model_version=%s AND scoring_config_version=%s
                ORDER BY created_at DESC,id DESC LIMIT 1
                """,
                (model_version, config_version),
            )
            latest_calibration = cur.fetchone()
            active_calibration = active_calibration_from_cursor(cur)
        conn.rollback()

    matured = int(summary.get("calibration_eligible_matured") or 0)
    positives = int(summary.get("eligible_hits") or 0)
    negatives = int(summary.get("eligible_misses") or 0)
    cfg = SCORING_CONFIG["calibration"]
    reasons: list[str] = []
    if matured < cfg["minimum_matured_signals"]:
        reasons.append(f"Need {cfg['minimum_matured_signals']} calibration-eligible matured signals; have {matured}.")
    if positives < cfg["minimum_positives"]:
        reasons.append(f"Need {cfg['minimum_positives']} positive outcomes; have {positives}.")
    if negatives < cfg["minimum_negatives"]:
        reasons.append(f"Need {cfg['minimum_negatives']} negative outcomes; have {negatives}.")
    if not active_calibration:
        reasons.append("No temporal calibration run has passed the configured quality checks for the current score version.")
    calibrated = bool(active_calibration)
    return {
        "model_status": "calibrated" if calibrated else "uncalibrated",
        "calibration_status": "Calibrated" if calibrated else "Uncalibrated",
        "calibration_reasons": reasons,
        "summary": summary,
        "score_buckets": [
            {
                **row,
                "range": f"{int(row['bucket']) * 10}-{int(row['bucket']) * 10 + 9}",
                "hit_rate": (float(row["hit_count"]) / float(row["matured_count"]) * 100.0) if row.get("matured_count") else None,
            }
            for row in buckets
        ],
        "by_sector": sectors,
        "by_catalyst_type": catalysts,
        "latest_calibration_run": latest_calibration,
        "active_calibration_run": active_calibration,
        "active_calibration_model_version": active_calibration.get("calibration_model_version") if active_calibration else None,
        "contract": public_scoring_contract(),
        "catalyst_backend": "rules_v3_point_in_time",
        "calibration_guard": "Diagnostics and calibration are version-scoped. Matured outcomes become eligible only after delayed corporate-action review; missing fundamentals and enrichment failures remain explicit uncertainty.",
    }


@router.get("/oversold", response_class=HTMLResponse)
def oversold_page(request: Request):
    html = templates.get_template("oversold.html").render(request=request)
    html = html.replace('<a href="/" style="margin-left:8px;color:var(--muted)">Rapid Discovery</a>', "")
    html = html.replace(
        "</body>",
        '<script src="/static/oversold_tracking_v3.js?v=1"></script>\n'
        '<script src="/static/oversold_score_ui.js?v=3"></script>\n'
        '<script src="/static/oversold_top5.js?v=4"></script>\n'
        '<script src="/static/oversold_chatgpt_score.js?v=3"></script>\n</body>',
    )
    return HTMLResponse(content=html)


@router.get("/api/oversold/latest")
def latest_scan() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM or_scans ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
        conn.rollback()
    return {"scan": None, "candidates": []} if not row else _enrich_scan_calibration(_scan_detail(row["id"]))


@router.get("/api/oversold/scoring-contract")
def scoring_contract() -> dict[str, Any]:
    return public_scoring_contract()


@router.get("/api/oversold/diagnostics")
def scoring_diagnostics() -> dict[str, Any]:
    return _model_diagnostics()


@router.get("/api/oversold/scans")
def scan_history(limit: int = Query(30, ge=1, le=100)) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id,s.status,s.trigger_source,s.scan_date,s.min_drop_pct,s.candidate_limit,
                       s.asset_count,s.snapshot_count,s.candidate_count,s.started_at,s.completed_at,s.error,
                       count(c.id) FILTER (WHERE c.decision='unreviewed') AS unreviewed_count,
                       count(c.id) FILTER (WHERE c.decision='investigate') AS investigate_count,
                       count(c.id) FILTER (WHERE c.decision='watch') AS watch_count,
                       count(c.id) FILTER (WHERE c.decision='pass') AS pass_count,
                       count(c.id) FILTER (WHERE c.decision='reject') AS reject_count,
                       count(c.id) FILTER (WHERE c.decision='traded') AS traded_count
                FROM or_scans s LEFT JOIN or_candidates c ON c.scan_id=s.id
                GROUP BY s.id ORDER BY s.started_at DESC LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.rollback()
    return rows


@router.get("/api/oversold/scans/{scan_id}")
def scan_detail(scan_id: UUID) -> dict[str, Any]:
    return _enrich_scan_calibration(_scan_detail(scan_id))


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
async def run_outcome_capture(request: Request) -> dict[str, Any]:
    _require_scheduled_token(request)
    decision_checkpoints = await capture_due_checkpoints()
    signal_outcomes = await capture_signal_outcomes()
    corporate_actions = await review_corporate_actions()
    calibration = await asyncio.to_thread(run_calibration_if_changed)
    return {
        "decision_checkpoints": decision_checkpoints,
        "signal_outcomes": signal_outcomes,
        "corporate_actions": corporate_actions,
        "calibration": calibration,
    }


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
            return {"status": recent["status"], "scan_id": recent["id"], "duplicate": True, "cooldown_seconds": PUBLIC_MANUAL_COOLDOWN_SECONDS}
        trigger_source = "manual"
    scan_id = _create_scan(trigger_source, min_drop_pct, candidate_limit)
    if background:
        background_tasks.add_task(execute_scan, scan_id, min_drop_pct=min_drop_pct, candidate_limit=candidate_limit)
        return {"status": "running", "scan_id": scan_id, "trigger_source": trigger_source}
    await execute_scan(scan_id, min_drop_pct=min_drop_pct, candidate_limit=candidate_limit)
    return _enrich_scan_calibration(_scan_detail(scan_id))


@router.patch("/api/oversold/candidates/{candidate_id}")
async def update_candidate(candidate_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision") or "").lower()
    if decision not in {"unreviewed", "watch", "investigate", "pass", "reject", "traded"}:
        raise HTTPException(400, "Invalid decision")
    review_notes = str(payload.get("review_notes") or "")[:4000]
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE or_candidates SET decision=%s,review_notes=%s,reviewed_at=now() WHERE id=%s RETURNING id,decision,review_notes,reviewed_at",
                (decision, review_notes, candidate_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Candidate not found")
            if decision not in TRACKED_DECISIONS:
                cur.execute(
                    "UPDATE or_decision_tracks SET active=false,ended_at=COALESCE(ended_at,now()),updated_at=now() WHERE active=true AND symbol=(SELECT symbol FROM or_candidates WHERE id=%s)",
                    (candidate_id,),
                )
        conn.commit()
    try:
        track = await sync_candidate_tracking(candidate_id, decision)
        row["tracking"] = {"active": bool(track and track.get("active")), "decision": track.get("decision") if track else None, "track_id": track.get("id") if track else None}
    except Exception as exc:
        logger.exception("Decision saved but tracking sync failed for candidate %s", candidate_id)
        row["tracking_error"] = str(exc)[:1000]
    return row
