from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.db import close_pool, connection, execute_schema
from app.core import estimate_for, filter_assets
from app.models import EstimateRequest, JobCreateRequest
from app.oversold_public import router as oversold_public_router
from app.oversold import router as oversold_router
from app.oversold_v2 import router as oversold_v2_router
from app.intraday_profitability import router as intraday_profitability_router
from app.runtime_scope import request_is_in_scope, root_redirect_for, runtime_mode

VERSION = "1.2.0"
logger = logging.getLogger(__name__)
settings = get_settings()
deployment_mode = runtime_mode()
security = HTTPBasic()
templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if settings.auto_migrate:
        execute_schema()
    yield
    close_pool()


app = FastAPI(title="Alpaca Rapid Discovery Loader", version=VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(oversold_public_router)
app.include_router(oversold_router)
app.include_router(oversold_v2_router)
app.include_router(intraday_profitability_router)


@app.middleware("http")
async def enforce_runtime_scope(request: Request, call_next):
    if request.url.path == "/":
        redirect = root_redirect_for(deployment_mode)
        if redirect:
            return RedirectResponse(redirect, status_code=307)
    if not request_is_in_scope(deployment_mode, request.url.path):
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            content={
                "detail": "This legacy endpoint is retired on this deployment.",
                "runtime_mode": deployment_mode,
            },
        )
    return await call_next(request)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    username_ok = secrets.compare_digest(credentials.username.encode(), settings.app_username.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), settings.app_password.encode())
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(400, "Invalid job ID") from exc


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT now() AS db_time")
                db_time = cur.fetchone()["db_time"]
            conn.rollback()
        return {
            "status": "ok",
            "version": VERSION,
            "runtime_mode": deployment_mode,
            "database": "ok",
            "db_time": db_time,
        }
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "degraded",
                    "version": VERSION,
                    "runtime_mode": deployment_mode,
                    "database": "error",
                    "error": str(exc),
                }
            ),
        )


@app.get("/", response_class=HTMLResponse)
def index(request: Request, _: str = Depends(require_auth)):
    return templates.TemplateResponse("index.html", {"request": request, "version": VERSION})


@app.get("/api/dashboard")
def dashboard(_: str = Depends(require_auth)) -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status IN ('queued','planning','running','pause_requested')) AS active_jobs,
                    count(*) FILTER (WHERE status='completed') AS completed_jobs,
                    COALESCE(sum(rows_loaded),0) AS total_rows_loaded,
                    COALESCE(sum(api_requests),0) AS total_api_requests
                FROM rd_jobs
                """
            )
            metrics = cur.fetchone()
            cur.execute(
                """
                SELECT worker_id,status,current_job_id,current_task_ids,version,details,
                    heartbeat_at,started_at,
                    EXTRACT(EPOCH FROM (now()-heartbeat_at))::integer AS heartbeat_age_seconds
                FROM rd_workers ORDER BY heartbeat_at DESC LIMIT 5
                """
            )
            workers = cur.fetchall()
            cur.execute(
                """
                SELECT id,name,status,symbol_count,total_tasks,completed_tasks,failed_tasks,
                    rows_staged,rows_loaded,api_requests,bytes_staged,feature_rows,error,
                    created_at,started_at,completed_at,heartbeat_at,
                    CASE WHEN total_tasks > 0 THEN round(completed_tasks::numeric/total_tasks*100,1) ELSE 0 END AS progress_pct
                FROM rd_jobs ORDER BY created_at DESC LIMIT 100
                """
            )
            jobs = cur.fetchall()
            cur.execute("SELECT * FROM rd_inventory ORDER BY timeframe,feed,adjustment")
            inventory = cur.fetchall()
        conn.rollback()
    return {"metrics": metrics, "workers": workers, "jobs": jobs, "inventory": inventory, "server_time": datetime.now(UTC)}


@app.get("/api/jobs")
def list_jobs(limit: int = 100, _: str = Depends(require_auth)) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 500)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,name,status,symbol_count,total_tasks,completed_tasks,failed_tasks,
                    rows_staged,rows_loaded,api_requests,bytes_staged,feature_rows,error,
                    created_at,started_at,completed_at,heartbeat_at,
                    CASE WHEN total_tasks > 0 THEN round(completed_tasks::numeric/total_tasks*100,1) ELSE 0 END AS progress_pct
                FROM rd_jobs ORDER BY created_at DESC LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.rollback()
    return rows


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str, _: str = Depends(require_auth)) -> dict[str, Any]:
    jid = _uuid(job_id)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM rd_jobs WHERE id=%s", (jid,))
            job = cur.fetchone()
            if not job:
                raise HTTPException(404, "Job not found")
            cur.execute(
                """
                SELECT status,count(*) AS tasks,COALESCE(sum(rows_staged),0) AS rows_staged,
                    COALESCE(sum(rows_loaded),0) AS rows_loaded,COALESCE(sum(api_requests),0) AS api_requests
                FROM rd_tasks WHERE job_id=%s GROUP BY status ORDER BY status
                """,
                (jid,),
            )
            task_summary = cur.fetchall()
            cur.execute(
                """
                SELECT id,timeframe,feed,window_start,window_end,symbols,status,pages_completed,
                    rows_staged,rows_loaded,api_requests,attempts,error,claimed_by,heartbeat_at,completed_at,
                    EXTRACT(EPOCH FROM (now()-heartbeat_at))::integer AS heartbeat_age_seconds
                FROM rd_tasks WHERE job_id=%s ORDER BY id DESC LIMIT 100
                """,
                (jid,),
            )
            tasks = cur.fetchall()
            cur.execute(
                """
                SELECT id,task_id,level,event_type,message,details,created_at
                FROM rd_job_events WHERE job_id=%s ORDER BY created_at DESC LIMIT 100
                """,
                (jid,),
            )
            events = cur.fetchall()
        conn.rollback()
    return {"job": job, "task_summary": task_summary, "tasks": tasks, "events": events}


@app.post("/api/estimate")
async def estimate(payload: EstimateRequest, _: str = Depends(require_auth)) -> dict[str, Any]:
    config = payload.config
    async with AlpacaClient(
        target_rpm=min(config.performance.target_rpm, 1000),
        max_retries=config.performance.max_retries,
        backoff_seconds=config.performance.retry_backoff_seconds,
    ) as client:
        assets = await client.list_assets()
    selected = filter_assets(assets, config)
    estimate_data = estimate_for(config, len(selected))
    estimate_data["sample_symbols"] = [str(a.get("symbol")) for a in selected[:20]]
    return estimate_data


@app.post("/api/jobs", status_code=201)
def create_job(payload: JobCreateRequest, _: str = Depends(require_auth)) -> dict[str, Any]:
    config = payload.config
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rd_jobs(name,status,config) VALUES (%s,'queued',%s) RETURNING id,created_at",
                (config.name, Jsonb(config.model_dump(mode="json"))),
            )
            row = cur.fetchone()
            cur.execute(
                """
                INSERT INTO rd_job_events(job_id,event_type,message,details)
                VALUES (%s,'job_created','Job queued for planning.',%s)
                """,
                (row["id"], Jsonb({"timeframes": config.timeframes, "feed": config.feed})),
            )
        conn.commit()
    return {"id": row["id"], "status": "queued", "created_at": row["created_at"]}


@app.post("/api/jobs/{job_id}/actions/{action}")
def job_action(job_id: str, action: str, _: str = Depends(require_auth)) -> dict[str, Any]:
    jid = _uuid(job_id)
    action = action.lower()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status,total_tasks FROM rd_jobs WHERE id=%s FOR UPDATE", (jid,))
            job = cur.fetchone()
            if not job:
                raise HTTPException(404, "Job not found")
            current = job["status"]
            if action == "pause":
                if current not in {"running", "planning"}:
                    raise HTTPException(409, f"Cannot pause a {current} job")
                new_status = "pause_requested"
                cur.execute("UPDATE rd_jobs SET status=%s WHERE id=%s", (new_status, jid))
            elif action == "resume":
                if current != "paused":
                    raise HTTPException(409, f"Cannot resume a {current} job")
                new_status = "running" if job["total_tasks"] else "queued"
                cur.execute("UPDATE rd_jobs SET status=%s,error=NULL,completed_at=NULL WHERE id=%s", (new_status, jid))
            elif action == "cancel":
                if current in {"completed", "cancelled"}:
                    raise HTTPException(409, f"Job is already {current}")
                new_status = "cancel_requested"
                cur.execute("UPDATE rd_jobs SET status=%s WHERE id=%s", (new_status, jid))
            elif action == "recover":
                if current not in {"running", "pause_requested", "paused"}:
                    raise HTTPException(409, f"Cannot recover tasks for a {current} job")
                stale_seconds = settings.worker_stale_seconds
                cur.execute(
                    """
                    UPDATE rd_tasks SET claimed_by=NULL,
                        error=COALESCE(error,'Released by manual stalled-task recovery')
                    WHERE job_id=%s AND status='staged' AND claimed_by IS NOT NULL
                      AND (heartbeat_at IS NULL OR heartbeat_at < now() - (%s * interval '1 second'))
                    """,
                    (jid, stale_seconds),
                )
                staged_released = cur.rowcount or 0
                cur.execute(
                    """
                    UPDATE rd_tasks SET
                        status=CASE WHEN status='loading' THEN 'staged' ELSE 'pending' END,
                        claimed_by=NULL,
                        error=COALESCE(error,'Released by manual stalled-task recovery')
                    WHERE job_id=%s AND status IN ('running','loading')
                      AND (heartbeat_at IS NULL OR heartbeat_at < now() - (%s * interval '1 second'))
                    """,
                    (jid, stale_seconds),
                )
                active_recovered = cur.rowcount or 0
                new_status = "running"
                cur.execute(
                    "UPDATE rd_jobs SET status='running',error=NULL,completed_at=NULL WHERE id=%s",
                    (jid,),
                )
                cur.execute(
                    """
                    INSERT INTO rd_job_events(job_id,event_type,message,details)
                    VALUES (%s,'manual_recovery',%s,%s)
                    """,
                    (jid, f"Released {staged_released} staged and recovered {active_recovered} running/loading task(s).",
                     Jsonb({"staged_released": staged_released, "active_recovered": active_recovered})),
                )
            elif action == "retry":
                if current not in {"failed", "cancelled"}:
                    raise HTTPException(409, f"Cannot retry a {current} job")
                if job["total_tasks"]:
                    cur.execute(
                        """
                        UPDATE rd_tasks SET status='pending',attempts=0,error=NULL,claimed_by=NULL,
                            completed_at=NULL WHERE job_id=%s AND status IN ('failed','cancelled')
                        """,
                        (jid,),
                    )
                    new_status = "running"
                else:
                    new_status = "queued"
                cur.execute("UPDATE rd_jobs SET status=%s,error=NULL,completed_at=NULL WHERE id=%s", (new_status, jid))
            elif action == "delete":
                if current not in {"completed", "failed", "cancelled"}:
                    raise HTTPException(409, "Only terminal jobs can be deleted")
                cur.execute("DELETE FROM rd_jobs WHERE id=%s", (jid,))
                conn.commit()
                return {"ok": True, "status": "deleted"}
            else:
                raise HTTPException(400, "Unsupported action")
            if action != "recover":
                cur.execute(
                    "INSERT INTO rd_job_events(job_id,event_type,message) VALUES (%s,%s,%s)",
                    (jid, f"action_{action}", f"Action requested: {action}."),
                )
        conn.commit()
    return {"ok": True, "status": new_status}


@app.get("/api/inventory")
def inventory(_: str = Depends(require_auth)) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM rd_inventory ORDER BY timeframe,feed,adjustment")
            rows = cur.fetchall()
        conn.rollback()
    return rows


@app.get("/api/dependencies")
async def dependencies(_: str = Depends(require_auth)) -> dict[str, Any]:
    output: dict[str, Any] = {"database": {"ok": False}, "alpaca": {"ok": False}}
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database() AS database, current_user AS user, now() AS checked_at")
                output["database"] = {"ok": True, **cur.fetchone()}
            conn.rollback()
    except Exception as exc:
        output["database"] = {"ok": False, "error": str(exc)}
    try:
        async with AlpacaClient(target_rpm=200, max_retries=2) as client:
            output["alpaca"] = await client.health()
    except Exception as exc:
        output["alpaca"] = {"ok": False, "error": str(exc)}
    output["auth_warning"] = settings.app_password == "change-me"
    return output
