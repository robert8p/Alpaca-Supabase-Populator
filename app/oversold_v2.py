from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection
from app.oversold import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_MIN_DROP_PCT,
    MAX_CANDIDATE_LIMIT,
    _extract_candidate,
    _fetch_news_map,
    _fetch_snapshots,
    _is_operating_company_asset,
)
from app.oversold_fundamentals import load_point_in_time_fundamentals
from app.oversold_v3_hardening import classify_news_for_candidate

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
_scan_lock = asyncio.Lock()

SCORING_VERSION = "oversold-v2-simple-1"
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS or2_scans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    min_drop_pct double precision NOT NULL,
    candidate_limit integer NOT NULL,
    asset_count integer NOT NULL DEFAULT 0,
    snapshot_count integer NOT NULL DEFAULT 0,
    candidate_count integer NOT NULL DEFAULT 0,
    evidence_cutoff timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS or2_scans_started_idx ON or2_scans(started_at DESC);

CREATE TABLE IF NOT EXISTS or2_candidates (
    id bigserial PRIMARY KEY,
    scan_id uuid NOT NULL REFERENCES or2_scans(id) ON DELETE CASCADE,
    rank integer NOT NULL,
    symbol text NOT NULL,
    name text,
    exchange text,
    prev_close double precision,
    last_price double precision,
    drop_pct double precision,
    prev_dollar_volume double precision,
    spread_pct double precision,
    dislocation_score double precision NOT NULL,
    fundamental_survivability double precision NOT NULL,
    catalyst_reversibility double precision NOT NULL,
    impairment_risk double precision NOT NULL,
    confidence double precision NOT NULL,
    oversold_score double precision NOT NULL,
    fundamental_quality text NOT NULL,
    catalyst_class text NOT NULL,
    catalyst_summary text NOT NULL,
    initial_view text NOT NULL,
    risk_flags text[] NOT NULL DEFAULT '{}',
    fundamentals jsonb,
    headlines jsonb NOT NULL DEFAULT '[]'::jsonb,
    explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
    evidence_cutoff timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(scan_id, symbol)
);
CREATE INDEX IF NOT EXISTS or2_candidates_scan_rank_idx ON or2_candidates(scan_id, rank);
"""


def _ensure_schema() -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _fundamental_assessment(fundamentals: dict[str, Any] | None) -> tuple[float, str, list[str]]:
    if not fundamentals:
        return 35.0, "Unknown", ["point_in_time_fundamentals_missing"]

    score = 50.0
    reasons: list[str] = []
    revenue_yoy = _number(fundamentals.get("revenue_yoy"))
    net_margin = _number(fundamentals.get("net_margin"))
    cash_to_assets = _number(fundamentals.get("cash_to_assets"))
    liabilities_to_assets = _number(fundamentals.get("liabilities_to_assets"))
    equity_to_assets = _number(fundamentals.get("equity_to_assets"))
    diluted_shares_yoy = _number(fundamentals.get("diluted_shares_yoy"))

    if cash_to_assets is not None:
        if cash_to_assets >= 0.20:
            score += 15
            reasons.append("strong_cash_buffer")
        elif cash_to_assets >= 0.10:
            score += 8
        elif cash_to_assets <= 0.03:
            score -= 15
            reasons.append("thin_cash_buffer")
    if liabilities_to_assets is not None:
        if liabilities_to_assets <= 0.50:
            score += 10
        elif liabilities_to_assets >= 1.00:
            score -= 20
            reasons.append("liabilities_exceed_assets")
        elif liabilities_to_assets >= 0.80:
            score -= 10
    if equity_to_assets is not None:
        if equity_to_assets >= 0.40:
            score += 10
        elif equity_to_assets <= 0.0:
            score -= 20
            reasons.append("non_positive_equity")
    if revenue_yoy is not None:
        if revenue_yoy >= 0.10:
            score += 8
        elif revenue_yoy <= -0.20:
            score -= 10
            reasons.append("sharp_revenue_contraction")
    if net_margin is not None:
        if net_margin >= 0.10:
            score += 8
        elif net_margin < 0:
            score -= 8
        if net_margin <= -0.20:
            score -= 7
            reasons.append("deep_negative_margin")
    if diluted_shares_yoy is not None and diluted_shares_yoy >= 0.20:
        score -= 15
        reasons.append("high_dilution_rate")

    score = _clamp(score)
    quality = "Strong" if score >= 70 else "Adequate" if score >= 55 else "Weak" if score >= 40 else "Fragile"
    return score, quality, reasons


def _score_candidate(item: dict[str, Any], fundamentals: dict[str, Any] | None, catalyst_class: str, risk_flags: list[str], headline_count: int) -> dict[str, Any]:
    drop = abs(min(float(item.get("drop_pct") or 0.0), 0.0))
    dislocation = _clamp(25.0 + max(0.0, drop - 15.0) * 2.0)
    survivability, fundamental_quality, fundamental_reasons = _fundamental_assessment(fundamentals)

    reversibility = {"A": 82.0, "B": 88.0, "C": 48.0, "D": 20.0, "E": 5.0, "U": 45.0}.get(catalyst_class, 45.0)
    impairment = {"A": 18.0, "B": 22.0, "C": 55.0, "D": 82.0, "E": 98.0, "U": 50.0}.get(catalyst_class, 50.0)

    flags = set(risk_flags or [])
    if "dilution" in flags:
        reversibility -= 15
        impairment += 18
    if "solvency" in flags:
        reversibility -= 35
        impairment += 35
    if "clinical_regulatory" in flags:
        reversibility -= 10
        impairment += 12
    if "legal" in flags:
        reversibility -= 10
        impairment += 12
    if "delisting" in flags:
        reversibility -= 25
        impairment += 30
    if "analyst_only" in flags:
        reversibility += 5
        impairment -= 5

    reversibility = _clamp(reversibility)
    impairment = _clamp(impairment)

    confidence = 20.0
    confidence += 35.0 if fundamentals else 0.0
    confidence += 30.0 if headline_count else 5.0
    confidence += 10.0 if item.get("prev_dollar_volume") is not None else 0.0
    confidence += 5.0 if item.get("spread_pct") is not None else 0.0
    confidence = _clamp(confidence)

    raw = (
        0.30 * dislocation
        + 0.30 * survivability
        + 0.25 * reversibility
        + 0.15 * (100.0 - impairment)
    )
    confidence_factor = 0.45 + 0.55 * (confidence / 100.0)
    final = 50.0 + (raw - 50.0) * confidence_factor

    hard_cap: float | None = None
    hard_reason: str | None = None
    if catalyst_class == "E" or "solvency" in flags or "delisting" in flags:
        hard_cap, hard_reason = 20.0, "existential_or_solvency_risk"
    elif catalyst_class == "D":
        hard_cap, hard_reason = 40.0, "structural_impairment_risk"
    elif "dilution" in flags:
        hard_cap, hard_reason = 55.0, "material_dilution_risk"
    if hard_cap is not None:
        final = min(final, hard_cap)

    final = round(_clamp(final), 1)
    if hard_cap == 20.0 or final < 45:
        view = "Pass"
    elif final >= 70:
        view = "Investigate"
    elif final >= 55:
        view = "Watch"
    else:
        view = "Pass"

    return {
        "dislocation_score": round(dislocation, 1),
        "fundamental_survivability": round(survivability, 1),
        "catalyst_reversibility": round(reversibility, 1),
        "impairment_risk": round(impairment, 1),
        "confidence": round(confidence, 1),
        "oversold_score": final,
        "fundamental_quality": fundamental_quality,
        "initial_view": view,
        "explanation": {
            "formula": "30% dislocation + 30% survivability + 25% reversibility + 15% inverse impairment, compressed toward 50 when evidence confidence is low",
            "fundamental_reasons": fundamental_reasons,
            "risk_flags": sorted(flags),
            "hard_cap": hard_cap,
            "hard_cap_reason": hard_reason,
            "scoring_version": SCORING_VERSION,
        },
    }


def _create_scan(min_drop_pct: float, candidate_limit: int) -> UUID:
    _ensure_schema()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO or2_scans(min_drop_pct,candidate_limit,status) VALUES (%s,%s,'running') RETURNING id",
                (min_drop_pct, candidate_limit),
            )
            scan_id = cur.fetchone()["id"]
        conn.commit()
    return scan_id


def _scan_detail(scan_id: UUID) -> dict[str, Any]:
    _ensure_schema()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM or2_scans WHERE id=%s", (scan_id,))
            scan = cur.fetchone()
            if not scan:
                raise HTTPException(404, "Scan not found")
            cur.execute("SELECT * FROM or2_candidates WHERE scan_id=%s ORDER BY rank", (scan_id,))
            candidates = cur.fetchall()
        conn.rollback()
    return {"scan": scan, "candidates": candidates}


async def execute_scan(scan_id: UUID, *, min_drop_pct: float, candidate_limit: int) -> None:
    async with _scan_lock:
        try:
            async with AlpacaClient(target_rpm=3000, max_retries=4, backoff_seconds=0.8) as client:
                assets = await client.list_assets(status="active")
                eligible_assets = [
                    asset for asset in assets
                    if asset.get("tradable") is True
                    and str(asset.get("asset_class") or "").lower() == "us_equity"
                    and "otc" not in str(asset.get("exchange") or "").lower()
                    and _is_operating_company_asset(asset)
                ]
                asset_by_symbol = {str(asset["symbol"]).upper(): asset for asset in eligible_assets if asset.get("symbol")}
                snapshots, snapshot_requests = await _fetch_snapshots(client, sorted(asset_by_symbol))
                evidence_cutoff = datetime.now(UTC)
                raw_candidates = [
                    candidate
                    for symbol, snapshot in snapshots.items()
                    if symbol in asset_by_symbol and isinstance(snapshot, dict)
                    if (candidate := _extract_candidate(symbol, snapshot, asset_by_symbol[symbol], min_drop_pct)) is not None
                ]
                raw_candidates.sort(key=lambda row: row["drop_pct"])
                raw_candidates = raw_candidates[:candidate_limit]
                symbols = [row["symbol"] for row in raw_candidates]
                news_map, news_requests = await _fetch_news_map(client, symbols, end_at=evidence_cutoff)

            fundamentals_map = await asyncio.to_thread(load_point_in_time_fundamentals, symbols, evidence_cutoff)
            enriched: list[dict[str, Any]] = []
            for item in raw_candidates:
                symbol = item["symbol"]
                articles = news_map.get(symbol, [])
                catalyst_class, catalyst_summary, risk_flags = classify_news_for_candidate(item, articles)
                fundamentals = fundamentals_map.get(symbol)
                if fundamentals:
                    risk_flags = sorted(set(risk_flags or []).union(fundamentals.get("derived_risk_flags") or []))
                model = _score_candidate(item, fundamentals, catalyst_class, risk_flags, len(articles))
                enriched.append({
                    **item,
                    **model,
                    "catalyst_class": catalyst_class,
                    "catalyst_summary": catalyst_summary,
                    "risk_flags": risk_flags,
                    "fundamentals": fundamentals,
                    "headlines": articles,
                })

            enriched.sort(key=lambda row: (-row["oversold_score"], -row["confidence"], row["drop_pct"]))
            with connection() as conn:
                with conn.cursor() as cur:
                    for rank, item in enumerate(enriched, 1):
                        cur.execute(
                            """
                            INSERT INTO or2_candidates(
                                scan_id,rank,symbol,name,exchange,prev_close,last_price,drop_pct,prev_dollar_volume,spread_pct,
                                dislocation_score,fundamental_survivability,catalyst_reversibility,impairment_risk,confidence,
                                oversold_score,fundamental_quality,catalyst_class,catalyst_summary,initial_view,risk_flags,
                                fundamentals,headlines,explanation,evidence_cutoff
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (
                                scan_id, rank, item["symbol"], item.get("name"), item.get("exchange"), item.get("prev_close"),
                                item.get("last_price"), item.get("drop_pct"), item.get("prev_dollar_volume"), item.get("spread_pct"),
                                item["dislocation_score"], item["fundamental_survivability"], item["catalyst_reversibility"],
                                item["impairment_risk"], item["confidence"], item["oversold_score"], item["fundamental_quality"],
                                item["catalyst_class"], item["catalyst_summary"], item["initial_view"], item["risk_flags"],
                                Jsonb(item["fundamentals"]) if item["fundamentals"] else None, Jsonb(item["headlines"]),
                                Jsonb(item["explanation"]), evidence_cutoff,
                            ),
                        )
                    cur.execute(
                        """
                        UPDATE or2_scans SET status='completed',asset_count=%s,snapshot_count=%s,candidate_count=%s,
                            evidence_cutoff=%s,metadata=%s,completed_at=now() WHERE id=%s
                        """,
                        (
                            len(eligible_assets), len(snapshots), len(enriched), evidence_cutoff,
                            Jsonb({"snapshot_requests": snapshot_requests, "news_requests": news_requests, "feed": "sip", "scoring_version": SCORING_VERSION}),
                            scan_id,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            logger.exception("Oversold V2 scan failed: %s", scan_id)
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE or2_scans SET status='failed',error=%s,completed_at=now() WHERE id=%s", (str(exc)[:4000], scan_id))
                conn.commit()


def _build_chatgpt_prompt(detail: dict[str, Any]) -> str:
    candidates = list(detail.get("candidates") or [])[:10]
    lines = [
        "Audit these Oversold Reversion candidates as ORIGINAL signals. Do not use hindsight.",
        "Use only information published on or before each candidate's stored evidence_cutoff.",
        "Independently challenge the app score; do not assume its ranking is correct.",
        "",
        "For each stock assess: why it fell; evidence strength; whether the cause is temporary/reversible/uncertain/structural; likely permanent economic damage; whether the price move is disproportionate; balance-sheet survivability; mean-reversion mechanism; contradictory evidence; further downside risk; risk/reward asymmetry; and whether it is a credible profit opportunity.",
        "Return an independent best-to-worst ranking and give each stock INVESTIGATE, WATCH or PASS. Explicitly call out material disagreements with the app score.",
        "",
    ]
    for row in candidates:
        fundamentals = row.get("fundamentals") or {}
        headline_bits = [
            f"{h.get('created_at')}: {h.get('headline')}" for h in (row.get("headlines") or [])[:5]
        ]
        lines.extend([
            f"{row['rank']}. {row['symbol']} ({row.get('name') or row['symbol']})",
            f"Day move: {float(row.get('drop_pct') or 0):.1f}% | Oversold Score: {float(row.get('oversold_score') or 0):.1f}/100 | Initial view: {row.get('initial_view')}",
            f"Components: dislocation {row.get('dislocation_score')}, survivability {row.get('fundamental_survivability')}, reversibility {row.get('catalyst_reversibility')}, impairment risk {row.get('impairment_risk')}, confidence {row.get('confidence')}",
            f"Fundamental quality: {row.get('fundamental_quality')} | Catalyst: {row.get('catalyst_summary')} | Risk flags: {', '.join(row.get('risk_flags') or []) or 'none'}",
            f"Fundamentals: {json.dumps(fundamentals, default=str, separators=(',', ':'))}",
            f"Evidence cutoff: {row.get('evidence_cutoff')}",
            "News: " + (" || ".join(headline_bits) if headline_bits else "none retained"),
            "",
        ])
    lines.extend([
        "Finish with: strongest candidate; strongest reason to avoid it; any statistically oversold candidate that should clearly be rejected; and the key evidence to verify before risking capital.",
        "Do not describe any speculative profit as certain or guaranteed.",
    ])
    return "\n".join(lines)


@router.get("/oversold-v2", response_class=HTMLResponse)
def oversold_v2_page(request: Request):
    _ensure_schema()
    return templates.TemplateResponse("oversold_v2.html", {"request": request})


@router.get("/api/oversold-v2/latest")
def latest_scan() -> dict[str, Any]:
    _ensure_schema()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM or2_scans ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
        conn.rollback()
    return {"scan": None, "candidates": []} if not row else _scan_detail(row["id"])


@router.get("/api/oversold-v2/scans/{scan_id}")
def scan_detail(scan_id: UUID) -> dict[str, Any]:
    return _scan_detail(scan_id)


@router.post("/api/oversold-v2/run", status_code=202)
async def run_scan(
    background_tasks: BackgroundTasks,
    min_drop_pct: float = Query(DEFAULT_MIN_DROP_PCT, ge=5, le=90),
    candidate_limit: int = Query(DEFAULT_CANDIDATE_LIMIT, ge=1, le=MAX_CANDIDATE_LIMIT),
) -> dict[str, Any]:
    scan_id = _create_scan(min_drop_pct, candidate_limit)
    background_tasks.add_task(execute_scan, scan_id, min_drop_pct=min_drop_pct, candidate_limit=candidate_limit)
    return {"status": "running", "scan_id": scan_id}


@router.get("/api/oversold-v2/chatgpt-prompt")
def chatgpt_prompt(scan_id: UUID | None = None) -> dict[str, Any]:
    _ensure_schema()
    if scan_id is None:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM or2_scans WHERE status='completed' ORDER BY started_at DESC LIMIT 1")
                row = cur.fetchone()
            conn.rollback()
        if not row:
            raise HTTPException(404, "No completed Oversold V2 scan available")
        scan_id = row["id"]
    detail = _scan_detail(scan_id)
    return {"scan_id": scan_id, "candidate_count": min(10, len(detail.get("candidates") or [])), "prompt": _build_chatgpt_prompt(detail)}
