from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app.reversion_guard_engine import (
    DEFAULT_SETTINGS,
    GUARD_VERSION,
    assess_candidate,
    compact_candidate_packet,
    portfolio_summary,
    review_position,
)

VERSION = "1.1.0"
logger = logging.getLogger(__name__)
SOURCE_BASE_URL = os.getenv("OVERSOLD_SOURCE_BASE_URL", "https://alpaca-rapid-discovery-web.onrender.com").rstrip("/")
CACHE_SECONDS = max(5, int(os.getenv("REVERSION_GUARD_CACHE_SECONDS", "20")))
REQUEST_TIMEOUT_SECONDS = max(15.0, float(os.getenv("REVERSION_GUARD_REQUEST_TIMEOUT_SECONDS", "75")))


class RiskSettings(BaseModel):
    account_value_gbp: float = Field(default=float(DEFAULT_SETTINGS["account_value_gbp"]), gt=0, le=100_000_000)
    risk_budget_gbp: float = Field(default=float(DEFAULT_SETTINGS["risk_budget_gbp"]), gt=0, le=1_000_000)
    max_position_gbp: float = Field(default=float(DEFAULT_SETTINGS["max_position_gbp"]), gt=0, le=10_000_000)
    usd_per_gbp: float = Field(default=float(DEFAULT_SETTINGS["usd_per_gbp"]), gt=0.1, le=10)
    max_theme_positions: int = Field(default=int(DEFAULT_SETTINGS["max_theme_positions"]), ge=1, le=20)
    max_open_risk_pct: float = Field(default=float(DEFAULT_SETTINGS["max_open_risk_pct"]), gt=0, le=100)


class PositionInput(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    entry_price_usd: float = Field(gt=0, le=1_000_000)
    current_price_usd: float | None = Field(default=None, gt=0, le=1_000_000)
    quantity: float = Field(gt=0, le=100_000_000)
    entry_timestamp: str | None = None
    theme: str | None = Field(default=None, max_length=100)
    planned_risk_gbp: float | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("symbol")
    @classmethod
    def normalise_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol.replace(".", "").replace("-", "").isalnum():
            raise ValueError("symbol contains unsupported characters")
        return symbol


class PositionReviewRequest(BaseModel):
    position: PositionInput
    settings: RiskSettings = Field(default_factory=RiskSettings)


class PortfolioReviewRequest(BaseModel):
    positions: list[PositionInput] = Field(default_factory=list, max_length=100)
    settings: RiskSettings = Field(default_factory=RiskSettings)


class DecisionUpdate(BaseModel):
    decision: str
    review_notes: str = Field(default="", max_length=4000)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        decision = value.strip().lower()
        if decision not in {"unreviewed", "investigate", "watch", "pass", "reject", "traded"}:
            raise ValueError("invalid decision")
        return decision


_cache_lock = asyncio.Lock()
_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting Oversold Reversion Guard %s using upstream %s", VERSION, SOURCE_BASE_URL)
    yield


app = FastAPI(
    title="Oversold Reversion Guard",
    description="Strict catalyst, confirmation, sizing and portfolio-risk overlay for Oversold Reversion.",
    version=VERSION,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _settings_dict(settings: RiskSettings | None = None) -> dict[str, Any]:
    return (settings or RiskSettings()).model_dump()


async def _request_upstream(method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None, timeout: float | None = None) -> Any:
    url = f"{SOURCE_BASE_URL}{path}"
    request_timeout = timeout or REQUEST_TIMEOUT_SECONDS
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(request_timeout, connect=20.0), follow_redirects=True) as client:
            response = await client.request(method, url, params=params, json=json, headers={"User-Agent": f"oversold-reversion-guard/{VERSION}"})
    except httpx.TimeoutException as exc:
        raise HTTPException(504, f"The upstream scanner timed out while waking or processing: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Could not reach the upstream scanner: {exc}") from exc
    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:1000]
        raise HTTPException(response.status_code, detail=detail)
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, "Upstream scanner returned a non-JSON response") from exc


async def _cached_get(path: str, *, force: bool = False) -> dict[str, Any]:
    now = datetime.now(UTC)
    if not force:
        cached = _cache.get(path)
        if cached and now - cached[0] < timedelta(seconds=CACHE_SECONDS):
            return cached[1]
    async with _cache_lock:
        if not force:
            cached = _cache.get(path)
            if cached and now - cached[0] < timedelta(seconds=CACHE_SECONDS):
                return cached[1]
        payload = await _request_upstream("GET", path)
        if not isinstance(payload, dict):
            raise HTTPException(502, "Upstream scanner returned an invalid payload")
        _cache[path] = (datetime.now(UTC), payload)
        return payload


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, float, float, int]:
    assessment = row.get("guard_assessment") or {}
    action_order = {"INVESTIGATE": 0, "WAIT": 1, "PASS": 2, "REJECT": 3}
    return (
        action_order.get(str(assessment.get("recommended_action")), 9),
        -float(assessment.get("guard_score") or 0),
        -float(row.get("evidence_confidence") or 0),
        int(row.get("rank") or 9999),
    )


def _enrich(payload: dict[str, Any], settings: dict[str, Any], positions: list[dict[str, Any]] | None = None, *, historical: bool = False) -> dict[str, Any]:
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        assessment = assess_candidate(candidate, settings, historical=historical)
        row = {**candidate, "guard_assessment": assessment}
        enriched.append(row)
    enriched.sort(key=_candidate_sort_key)
    assessments = [row["guard_assessment"] for row in enriched]
    scan = payload.get("scan")
    return {
        "scan": scan,
        "candidates": enriched,
        "portfolio": portfolio_summary(assessments, positions=positions or [], settings=settings),
        "guard": {
            "version": GUARD_VERSION,
            "app_version": VERSION,
            "source_base_url": SOURCE_BASE_URL,
            "assessment_count": len(enriched),
            "model_status": "UNCALIBRATED_HEURISTIC",
            "profit_probability": None,
            "historical_only": historical,
            "generated_at": datetime.now(UTC).isoformat(),
            "purpose": "Find verified, survivable overreactions that are tradable only after regular-session confirmation; reject structural damage and size every trade by invalidation risk.",
        },
    }


async def _latest_candidate(symbol: str, settings: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    payload = await _cached_get("/api/oversold/latest")
    for candidate in payload.get("candidates") or []:
        if str(candidate.get("symbol") or "").upper() == symbol.upper():
            return candidate, assess_candidate(candidate, settings)
    return None, None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "reversion_guard.html",
        {
            "request": request,
            "version": VERSION,
            "guard_version": GUARD_VERSION,
            "source_base_url": SOURCE_BASE_URL,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health")
async def health() -> JSONResponse:
    try:
        upstream = await _request_upstream("GET", "/health", timeout=30.0)
        status_code = 200
        status = "ok"
    except HTTPException as exc:
        upstream = {"ok": False, "error": str(exc.detail)}
        status_code = 503
        status = "degraded"
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "version": VERSION,
            "guard_version": GUARD_VERSION,
            "upstream": upstream,
            "source_base_url": SOURCE_BASE_URL,
        },
    )


@app.get("/api/reversion-guard/latest")
async def latest(
    account_value_gbp: float = Query(float(DEFAULT_SETTINGS["account_value_gbp"]), gt=0),
    risk_budget_gbp: float = Query(float(DEFAULT_SETTINGS["risk_budget_gbp"]), gt=0),
    max_position_gbp: float = Query(float(DEFAULT_SETTINGS["max_position_gbp"]), gt=0),
    usd_per_gbp: float = Query(float(DEFAULT_SETTINGS["usd_per_gbp"]), gt=0.1, le=10),
    max_theme_positions: int = Query(int(DEFAULT_SETTINGS["max_theme_positions"]), ge=1, le=20),
    max_open_risk_pct: float = Query(float(DEFAULT_SETTINGS["max_open_risk_pct"]), gt=0, le=100),
    force: bool = Query(False),
) -> dict[str, Any]:
    settings = RiskSettings(
        account_value_gbp=account_value_gbp,
        risk_budget_gbp=risk_budget_gbp,
        max_position_gbp=max_position_gbp,
        usd_per_gbp=usd_per_gbp,
        max_theme_positions=max_theme_positions,
        max_open_risk_pct=max_open_risk_pct,
    ).model_dump()
    payload = await _cached_get("/api/oversold/latest", force=force)
    return _enrich(payload, settings)


@app.get("/api/reversion-guard/scans")
async def scans(limit: int = Query(30, ge=1, le=100)) -> Any:
    return await _request_upstream("GET", "/api/oversold/scans", params={"limit": limit})


@app.get("/api/reversion-guard/scans/{scan_id}")
async def scan_detail(
    scan_id: UUID,
    account_value_gbp: float = Query(float(DEFAULT_SETTINGS["account_value_gbp"]), gt=0),
    risk_budget_gbp: float = Query(float(DEFAULT_SETTINGS["risk_budget_gbp"]), gt=0),
    max_position_gbp: float = Query(float(DEFAULT_SETTINGS["max_position_gbp"]), gt=0),
    usd_per_gbp: float = Query(float(DEFAULT_SETTINGS["usd_per_gbp"]), gt=0.1, le=10),
    max_theme_positions: int = Query(int(DEFAULT_SETTINGS["max_theme_positions"]), ge=1, le=20),
    max_open_risk_pct: float = Query(float(DEFAULT_SETTINGS["max_open_risk_pct"]), gt=0, le=100),
) -> dict[str, Any]:
    settings = RiskSettings(
        account_value_gbp=account_value_gbp,
        risk_budget_gbp=risk_budget_gbp,
        max_position_gbp=max_position_gbp,
        usd_per_gbp=usd_per_gbp,
        max_theme_positions=max_theme_positions,
        max_open_risk_pct=max_open_risk_pct,
    ).model_dump()
    payload = await _cached_get(f"/api/oversold/scans/{scan_id}", force=True)
    return _enrich(payload, settings, historical=True)


@app.post("/api/reversion-guard/run", status_code=202)
async def run_scan(
    min_drop_pct: float = Query(15.0, ge=5, le=90),
    candidate_limit: int = Query(50, ge=1, le=100),
) -> Any:
    result = await _request_upstream(
        "POST",
        "/api/oversold/run",
        params={"background": "true", "min_drop_pct": min_drop_pct, "candidate_limit": candidate_limit},
        timeout=45.0,
    )
    _cache.clear()
    return result


@app.patch("/api/reversion-guard/candidates/{candidate_id}")
async def update_candidate(candidate_id: int, payload: DecisionUpdate) -> Any:
    result = await _request_upstream(
        "PATCH",
        f"/api/oversold/candidates/{candidate_id}",
        json=payload.model_dump(),
        timeout=45.0,
    )
    _cache.clear()
    return result


@app.post("/api/reversion-guard/positions/review")
async def position_review(payload: PositionReviewRequest) -> dict[str, Any]:
    settings = payload.settings.model_dump()
    position = payload.position.model_dump()
    candidate, assessment = await _latest_candidate(payload.position.symbol, settings)
    if position.get("current_price_usd") is None:
        if candidate and candidate.get("last_price") is not None:
            position["current_price_usd"] = candidate["last_price"]
            position["current_price_source"] = "stored_scan"
        else:
            raise HTTPException(400, "Current price was not supplied and the symbol is not in the latest scan")
    try:
        review = review_position(position, candidate=candidate, settings=settings)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if position.get("theme"):
        review["theme"] = position["theme"]
    elif assessment:
        review["theme"] = assessment.get("theme")
    else:
        review["theme"] = "Other / unknown"
    review["source_candidate_found"] = candidate is not None
    review["reviewed_at"] = datetime.now(UTC).isoformat()
    return review


@app.post("/api/reversion-guard/portfolio/review")
async def portfolio_review(payload: PortfolioReviewRequest) -> dict[str, Any]:
    settings = payload.settings.model_dump()
    latest_payload = await _cached_get("/api/oversold/latest")
    by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in latest_payload.get("candidates") or []
        if isinstance(row, dict)
    }
    reviews: list[dict[str, Any]] = []
    for item in payload.positions:
        position = item.model_dump()
        candidate = by_symbol.get(item.symbol)
        if position.get("current_price_usd") is None:
            if candidate and candidate.get("last_price") is not None:
                position["current_price_usd"] = candidate["last_price"]
                position["current_price_source"] = "stored_scan"
            else:
                reviews.append({"symbol": item.symbol, "error": "Current price missing and symbol is not in latest scan"})
                continue
        try:
            review = review_position(position, candidate=candidate, settings=settings)
        except ValueError as exc:
            reviews.append({"symbol": item.symbol, "error": str(exc)})
            continue
        review["theme"] = item.theme or (review.get("candidate_assessment") or {}).get("theme") or "Other / unknown"
        review["planned_risk_gbp"] = item.planned_risk_gbp
        reviews.append(review)

    valid_reviews = [row for row in reviews if not row.get("error")]
    candidate_assessments = [
        assess_candidate(row, settings)
        for row in latest_payload.get("candidates") or []
        if isinstance(row, dict)
    ]
    return {
        "positions": reviews,
        "summary": portfolio_summary(candidate_assessments, positions=valid_reviews, settings=settings),
        "reviewed_at": datetime.now(UTC).isoformat(),
    }


@app.get("/api/reversion-guard/candidates/{candidate_id}/packet")
async def candidate_packet(candidate_id: int) -> dict[str, Any]:
    payload = await _cached_get("/api/oversold/latest")
    for candidate in payload.get("candidates") or []:
        if int(candidate.get("id") or -1) == candidate_id:
            assessment = assess_candidate(candidate, _settings_dict())
            return compact_candidate_packet(candidate, assessment)
    raise HTTPException(404, "Candidate not found in the latest scan")


@app.get("/api/reversion-guard/policy")
def policy() -> dict[str, Any]:
    return {
        "version": GUARD_VERSION,
        "purpose": "Prioritise verified, survivable overreactions and block entries until regular-session price confirmation exists.",
        "hard_exclusions": [
            "bankruptcy, solvency, fraud, restatement or permanent structural impairment",
            "convertible debt, share issuance, registered offerings or material dilution",
            "failed pivotal clinical/regulatory events",
            "dominant post-spike or parabolic momentum unwinds",
        ],
        "conditional_exclusions": [
            "reduced guidance or earnings-quality resets until fair value is rebuilt",
            "open legal, export-control or compliance risk",
            "unknown or weakly verified catalysts",
        ],
        "entry_rule": "No extended-hours entry. Wait until at least 10:00 ET and require a higher low plus VWAP or intraday-pivot reclaim.",
        "sizing_rule": "Sizing previews use your saved GBP risk budget and maximum-position settings. Stops can slip or gap beyond planned loss.",
        "portfolio_rule": "No more than three positions driven by the same theme by default.",
        "time_stop": "Exit by the close of the second full regular session if confirmation does not develop.",
        "profit_rule": "+1R and +4–6% are illustrative planning levels, not forecasts or evidence of favourable net risk/reward.",
        "averaging_rule": "Never average down into a falling price.",
        "research_status": "Research prioritisation only; it does not place orders or provide personalised financial advice.",
        "score_status": "Uncalibrated heuristic. Profit probability and expected net return are unavailable until independently validated after costs.",
        "evidence_rule": "A VERIFIED label or high confidence score needs cutoff-valid, issuer-linked source content; a filing header alone cannot establish a cause.",
        "execution_evidence_rule": "A current non-crossed bid/ask and trade are required. Missing or stale inputs cannot be offset by high liquidity or upstream scores.",
    }


@app.post("/api/reversion-guard/echo-settings")
def echo_settings(payload: RiskSettings = Body(default_factory=RiskSettings)) -> dict[str, Any]:
    """Small validation endpoint used by the UI before storing settings locally."""
    return payload.model_dump()
