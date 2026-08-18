from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.db import connection

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()
optional_security = HTTPBasic(auto_error=False)
LONDON = ZoneInfo("Europe/London")

DEFAULT_MIN_DROP_PCT = 15.0
DEFAULT_CANDIDATE_LIMIT = 50
MAX_CANDIDATE_LIMIT = 100
MIN_PRICE = 1.0
MIN_PREV_DOLLAR_VOLUME = 500_000.0
SNAPSHOT_BATCH_SIZE = 100
SNAPSHOT_CONCURRENCY = 8
NEWS_LOOKBACK_HOURS = 72
NEWS_SYMBOL_BATCH_SIZE = 20
NEWS_MAX_PAGES = 2
NON_OPERATING_INSTRUMENT_RE = re.compile(
    r"\b(etf|exchange[- ]traded fund|warrants?|rights?|units?|preferred)\b",
    re.IGNORECASE,
)

EXISTENTIAL_WORDS = (
    "bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern",
    "payment default", "debt default", "accounting fraud", "fraud investigation",
    "delist", "liquidation",
)
STRUCTURAL_WORDS = (
    "permanently close", "permanent closure", "terminates program", "terminated program",
    "discontinues program", "discontinued program", "patent invalid", "patent loss",
    "loses key customer", "lost key customer", "license terminated",
)
MATERIAL_WORDS = (
    "phase 3", "phase iii", "clinical trial", "primary endpoint", "secondary endpoint",
    "fda", "complete response letter", "crl", "earnings", "revenue miss", "misses estimates",
    "guidance", "cuts forecast", "lowers forecast", "public offering", "registered direct",
    "at-the-market", "dilution", "convertible", "subpoena", "investigation", "lawsuit",
    "ceo resign", "chief executive resign", "recall",
)
TRANSIENT_WORDS = (
    "temporary", "temporarily", "outage", "weather disruption", "shipment delay",
    "shipping delay", "supply disruption", "technical issue", "production delay",
    "operations resume", "resumes operations", "short-term disruption",
)
ANALYST_WORDS = ("downgrade", "upgrade", "price target", "analyst", "rating")
RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "solvency": ("bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern", "debt default"),
    "dilution": ("public offering", "registered direct", "at-the-market", "dilution", "convertible", "warrant"),
    "clinical_regulatory": ("phase 3", "phase iii", "clinical trial", "primary endpoint", "fda", "complete response letter", "crl"),
    "earnings_guidance": ("earnings", "revenue miss", "guidance", "forecast"),
    "legal": ("lawsuit", "subpoena", "investigation", "fraud"),
    "management": ("ceo resign", "chief executive resign", "cfo resign"),
    "delisting": ("delist", "nasdaq deficiency", "listing deficiency"),
}

_scan_lock = asyncio.Lock()


def _basic_auth_ok(credentials: HTTPBasicCredentials | None) -> bool:
    return bool(
        credentials
        and secrets.compare_digest(credentials.username.encode(), settings.app_username.encode())
        and secrets.compare_digest(credentials.password.encode(), settings.app_password.encode())
    )


def require_basic(credentials: HTTPBasicCredentials | None = Depends(optional_security)) -> str:
    if not _basic_auth_ok(credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def authorize_run(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(optional_security),
) -> str:
    if _basic_auth_ok(credentials):
        return "basic"
    expected = os.getenv("OVERSOLD_TRIGGER_TOKEN", "")
    supplied = request.headers.get("X-Oversold-Token", "")
    if expected and supplied and secrets.compare_digest(expected.encode(), supplied.encode()):
        return "token"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def _snapshot_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    nested = data.get("snapshots")
    return nested if isinstance(nested, dict) else data


def _is_operating_company_asset(asset: dict[str, Any]) -> bool:
    name = str(asset.get("name") or "")
    return not bool(NON_OPERATING_INSTRUMENT_RE.search(name))


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _classify_news(articles: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    if not articles:
        return "U", "No recent company-specific Alpaca news found in the 72-hour window.", ["no_news"]

    text = " ".join(
        " ".join(str(article.get(key) or "") for key in ("headline", "summary")).lower()
        for article in articles
    )
    risk_flags = [flag for flag, words in RISK_KEYWORDS.items() if _contains_any(text, words)]

    if _contains_any(text, EXISTENTIAL_WORDS):
        return "E", "Existential-risk language detected (solvency, fraud, delisting or liquidation).", sorted(set(risk_flags))
    if _contains_any(text, STRUCTURAL_WORDS):
        return "D", "Potential structural impairment language detected.", sorted(set(risk_flags))
    if _contains_any(text, MATERIAL_WORDS):
        return "C", "Material but uncertain repricing catalyst detected; underlying facts require review.", sorted(set(risk_flags))
    if _contains_any(text, TRANSIENT_WORDS):
        return "B", "Potentially temporary operational/disruption catalyst detected.", sorted(set(risk_flags))
    if _contains_any(text, ANALYST_WORDS):
        risk_flags.append("analyst_only")
        return "A", "News appears dominated by analyst/sentiment action rather than a clear new operating event.", sorted(set(risk_flags))
    return "U", "Recent news exists, but the catalyst is not confidently classified by the first-pass rules.", sorted(set(risk_flags))


def _score_candidate(
    *,
    drop_pct: float,
    prev_dollar_volume: float | None,
    spread_pct: float | None,
    catalyst_class: str,
    headline_count: int,
) -> int:
    severity = abs(min(drop_pct, 0.0))
    score = 10 + min(25, max(0, round((severity - DEFAULT_MIN_DROP_PCT) * 0.55)))

    liquidity = prev_dollar_volume or 0.0
    score += 15 if liquidity >= 50_000_000 else 12 if liquidity >= 10_000_000 else 8 if liquidity >= 2_000_000 else 4 if liquidity >= MIN_PREV_DOLLAR_VOLUME else 0

    if spread_pct is not None:
        score += 10 if spread_pct <= 0.50 else 8 if spread_pct <= 1.00 else 5 if spread_pct <= 2.00 else 1 if spread_pct <= 5.00 else 0

    score += {"A": 20, "B": 20, "C": 10, "D": -5, "E": -25, "U": 4}.get(catalyst_class, 0)
    score += 5 if headline_count else -5
    return max(0, min(100, int(score)))


def _triage_label(catalyst_class: str, score: int) -> str:
    if catalyst_class == "E":
        return "PASS / EXISTENTIAL RISK"
    if catalyst_class == "D":
        return "PASS / STRUCTURAL RISK"
    if score >= 70:
        return "INVESTIGATE NOW"
    if score >= 55:
        return "REVIEW"
    return "LOW PRIORITY"


async def _fetch_snapshots(client: AlpacaClient, symbols: list[str]) -> tuple[dict[str, Any], int]:
    semaphore = asyncio.Semaphore(SNAPSHOT_CONCURRENCY)

    async def one(batch: list[str]) -> dict[str, Any]:
        async with semaphore:
            url = f"{client.settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/snapshots"
            result = await client._get(url, {"symbols": ",".join(batch), "feed": "sip"})
            return _snapshot_payload(result.data)

    batches = _chunks(symbols, SNAPSHOT_BATCH_SIZE)
    results = await asyncio.gather(*(one(batch) for batch in batches), return_exceptions=True)
    merged: dict[str, Any] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Snapshot batch failed: %s", result)
        else:
            merged.update(result)
    return merged, len(batches)


async def _fetch_news_map(client: AlpacaClient, symbols: list[str]) -> tuple[dict[str, list[dict[str, Any]]], int]:
    now = datetime.now(UTC)
    start = now - timedelta(hours=NEWS_LOOKBACK_HOURS)
    output: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    request_count = 0

    for batch in _chunks(symbols, NEWS_SYMBOL_BATCH_SIZE):
        token: str | None = None
        for _ in range(NEWS_MAX_PAGES):
            url = f"{client.settings.alpaca_data_base_url.rstrip('/')}/v1beta1/news"
            params: dict[str, Any] = {
                "symbols": ",".join(batch),
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": now.isoformat().replace("+00:00", "Z"),
                "sort": "desc",
                "limit": 50,
                "include_content": "false",
            }
            if token:
                params["page_token"] = token
            try:
                result = await client._get(url, params)
            except Exception as exc:
                logger.warning("News batch failed for %s: %s", ",".join(batch), exc)
                break
            request_count += 1
            data = result.data if isinstance(result.data, dict) else {}
            articles = data.get("news") if isinstance(data.get("news"), list) else []
            for article in articles:
                if not isinstance(article, dict):
                    continue
                article_symbols = {str(s).upper() for s in article.get("symbols", []) if s}
                compact = {
                    "id": article.get("id"),
                    "headline": article.get("headline"),
                    "summary": article.get("summary"),
                    "source": article.get("source"),
                    "created_at": article.get("created_at"),
                    "updated_at": article.get("updated_at"),
                    "url": article.get("url"),
                    "symbols": sorted(article_symbols),
                }
                for symbol in article_symbols.intersection(output):
                    output[symbol].append(compact)
            token = data.get("next_page_token")
            if not token:
                break

    for symbol, articles in output.items():
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for article in articles:
            key = str(article.get("id") or article.get("url") or article.get("headline") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            deduped.append(article)
        output[symbol] = deduped[:10]
    return output, request_count


def _create_scan(trigger_source: str, min_drop_pct: float, candidate_limit: int) -> UUID:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO or_scans(trigger_source,scan_date,min_drop_pct,candidate_limit,status)
                VALUES (%s,%s,%s,%s,'running') RETURNING id
                """,
                (trigger_source, datetime.now(LONDON).date(), min_drop_pct, candidate_limit),
            )
            scan_id = cur.fetchone()["id"]
        conn.commit()
    return scan_id


def _existing_scheduled_scan() -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,status,started_at,completed_at
                FROM or_scans
                WHERE scan_date=%s AND trigger_source='scheduled'
                  AND status IN ('running','completed')
                ORDER BY started_at DESC LIMIT 1
                """,
                (datetime.now(LONDON).date(),),
            )
            row = cur.fetchone()
        conn.rollback()
    return row


def _extract_candidate(symbol: str, snapshot: dict[str, Any], asset: dict[str, Any], min_drop_pct: float) -> dict[str, Any] | None:
    previous = snapshot.get("prevDailyBar") or {}
    latest_trade = snapshot.get("latestTrade") or {}
    latest_quote = snapshot.get("latestQuote") or {}
    minute_bar = snapshot.get("minuteBar") or {}
    daily_bar = snapshot.get("dailyBar") or {}

    prev_close = _number(previous.get("c"))
    last_price = _number(latest_trade.get("p")) or _number(minute_bar.get("c")) or _number(daily_bar.get("c"))
    if not prev_close or not last_price or prev_close <= 0 or last_price < MIN_PRICE:
        return None

    drop_pct = ((last_price / prev_close) - 1.0) * 100.0
    if drop_pct > -abs(min_drop_pct):
        return None

    prev_volume = _integer(previous.get("v"))
    prev_dollar_volume = prev_close * prev_volume if prev_volume is not None else None
    if prev_dollar_volume is not None and prev_dollar_volume < MIN_PREV_DOLLAR_VOLUME:
        return None

    bid = _number(latest_quote.get("bp"))
    ask = _number(latest_quote.get("ap"))
    spread_pct = None
    if bid and ask and ask >= bid and ((ask + bid) / 2) > 0:
        spread_pct = ((ask - bid) / ((ask + bid) / 2)) * 100.0

    return {
        "symbol": symbol,
        "name": asset.get("name"),
        "exchange": asset.get("exchange"),
        "prev_close": prev_close,
        "last_price": last_price,
        "drop_pct": drop_pct,
        "prev_volume": prev_volume,
        "prev_dollar_volume": prev_dollar_volume,
        "bid": bid,
        "ask": ask,
        "spread_pct": spread_pct,
        "latest_trade_ts": latest_trade.get("t"),
        "raw_snapshot": snapshot,
    }


async def execute_scan(
    scan_id: UUID,
    *,
    min_drop_pct: float = DEFAULT_MIN_DROP_PCT,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> None:
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
                    and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", str(asset.get("symbol") or "").upper())
                ]
                asset_by_symbol = {
                    str(asset["symbol"]).upper(): asset
                    for asset in eligible_assets if asset.get("symbol")
                }
                snapshots, snapshot_requests = await _fetch_snapshots(client, sorted(asset_by_symbol))

                raw_candidates = [
                    candidate
                    for symbol, snapshot in snapshots.items()
                    if symbol in asset_by_symbol and isinstance(snapshot, dict)
                    if (candidate := _extract_candidate(symbol, snapshot, asset_by_symbol[symbol], min_drop_pct)) is not None
                ]
                raw_candidates.sort(key=lambda item: item["drop_pct"])
                raw_candidates = raw_candidates[:candidate_limit]
                news_map, news_requests = await _fetch_news_map(client, [item["symbol"] for item in raw_candidates])

            enriched: list[dict[str, Any]] = []
            for item in raw_candidates:
                articles = news_map.get(item["symbol"], [])
                catalyst_class, catalyst_summary, risk_flags = _classify_news(articles)
                score = _score_candidate(
                    drop_pct=item["drop_pct"],
                    prev_dollar_volume=item["prev_dollar_volume"],
                    spread_pct=item["spread_pct"],
                    catalyst_class=catalyst_class,
                    headline_count=len(articles),
                )
                item.update(
                    catalyst_class=catalyst_class,
                    catalyst_summary=catalyst_summary,
                    risk_flags=risk_flags,
                    headlines=articles,
                    headline_count=len(articles),
                    heuristic_score=score,
                    triage_label=_triage_label(catalyst_class, score),
                )
                enriched.append(item)

            enriched.sort(
                key=lambda item: (
                    item["triage_label"] not in {"INVESTIGATE NOW", "REVIEW"},
                    -item["heuristic_score"],
                    item["drop_pct"],
                )
            )

            with connection() as conn:
                with conn.cursor() as cur:
                    for rank, item in enumerate(enriched, 1):
                        cur.execute(
                            """
                            INSERT INTO or_candidates(
                                scan_id,rank,symbol,name,exchange,prev_close,last_price,drop_pct,
                                prev_volume,prev_dollar_volume,bid,ask,spread_pct,latest_trade_ts,
                                catalyst_class,catalyst_summary,risk_flags,headline_count,headlines,
                                heuristic_score,triage_label,raw_snapshot
                            ) VALUES (
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s
                            )
                            ON CONFLICT (scan_id,symbol) DO UPDATE SET
                                rank=EXCLUDED.rank,last_price=EXCLUDED.last_price,drop_pct=EXCLUDED.drop_pct,
                                bid=EXCLUDED.bid,ask=EXCLUDED.ask,spread_pct=EXCLUDED.spread_pct,
                                catalyst_class=EXCLUDED.catalyst_class,catalyst_summary=EXCLUDED.catalyst_summary,
                                risk_flags=EXCLUDED.risk_flags,headline_count=EXCLUDED.headline_count,
                                headlines=EXCLUDED.headlines,heuristic_score=EXCLUDED.heuristic_score,
                                triage_label=EXCLUDED.triage_label,raw_snapshot=EXCLUDED.raw_snapshot
                            """,
                            (
                                scan_id, rank, item["symbol"], item["name"], item["exchange"],
                                item["prev_close"], item["last_price"], item["drop_pct"], item["prev_volume"],
                                item["prev_dollar_volume"], item["bid"], item["ask"], item["spread_pct"],
                                item["latest_trade_ts"], item["catalyst_class"], item["catalyst_summary"],
                                item["risk_flags"], item["headline_count"], Jsonb(item["headlines"]),
                                item["heuristic_score"], item["triage_label"], Jsonb(item["raw_snapshot"]),
                            ),
                        )
                    cur.execute(
                        """
                        UPDATE or_scans
                        SET status='completed',asset_count=%s,snapshot_count=%s,candidate_count=%s,
                            completed_at=now(),metadata=%s
                        WHERE id=%s
                        """,
                        (
                            len(eligible_assets), len(snapshots), len(enriched),
                            Jsonb({
                                "snapshot_requests": snapshot_requests,
                                "news_requests": news_requests,
                                "feed": "sip",
                                "news_lookback_hours": NEWS_LOOKBACK_HOURS,
                                "min_price": MIN_PRICE,
                                "min_prev_dollar_volume": MIN_PREV_DOLLAR_VOLUME,
                                "instrument_filter": "operating_company_v1",
                                "scoring_model": "heuristic_v1",
                            }),
                            scan_id,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            logger.exception("Oversold Reversion scan %s failed", scan_id)
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE or_scans SET status='failed',error=%s,completed_at=now() WHERE id=%s",
                        (str(exc)[:4000], scan_id),
                    )
                conn.commit()


def _scan_detail(scan_id: UUID) -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM or_scans WHERE id=%s", (scan_id,))
            scan = cur.fetchone()
            if not scan:
                raise HTTPException(404, "Scan not found")
            cur.execute(
                """
                SELECT id,rank,symbol,name,exchange,prev_close,last_price,drop_pct,
                       prev_volume,prev_dollar_volume,bid,ask,spread_pct,latest_trade_ts,
                       catalyst_class,catalyst_summary,risk_flags,headline_count,headlines,
                       heuristic_score,triage_label,decision,review_notes,reviewed_at,created_at
                FROM or_candidates WHERE scan_id=%s ORDER BY rank
                """,
                (scan_id,),
            )
            candidates = cur.fetchall()
        conn.rollback()
    return {"scan": scan, "candidates": candidates}


@router.get("/oversold", response_class=HTMLResponse)
def oversold_page(request: Request, _: str = Depends(require_basic)):
    return templates.TemplateResponse("oversold.html", {"request": request})


@router.get("/api/oversold/latest")
def latest_scan(_: str = Depends(require_basic)) -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM or_scans ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
        conn.rollback()
    return {"scan": None, "candidates": []} if not row else _scan_detail(row["id"])


@router.get("/api/oversold/scans/{scan_id}")
def scan_detail(scan_id: UUID, _: str = Depends(require_basic)) -> dict[str, Any]:
    return _scan_detail(scan_id)


@router.post("/api/oversold/run", status_code=202)
async def run_scan(
    background_tasks: BackgroundTasks,
    request: Request,
    scheduled: bool = Query(False),
    background: bool = Query(True),
    min_drop_pct: float = Query(DEFAULT_MIN_DROP_PCT, ge=5, le=90),
    candidate_limit: int = Query(DEFAULT_CANDIDATE_LIMIT, ge=1, le=MAX_CANDIDATE_LIMIT),
    auth_mode: str = Depends(authorize_run),
) -> dict[str, Any]:
    if scheduled:
        local_now = datetime.now(LONDON)
        if not (local_now.weekday() < 5 and local_now.hour == 22 and 45 <= local_now.minute <= 59):
            return {"status": "skipped", "reason": "outside_london_scan_window", "local_time": local_now.isoformat()}
        existing = _existing_scheduled_scan()
        if existing:
            return {"status": existing["status"], "scan_id": existing["id"], "duplicate": True}

    trigger_source = "scheduled" if scheduled else "manual"
    scan_id = _create_scan(trigger_source, min_drop_pct, candidate_limit)
    if background:
        background_tasks.add_task(
            execute_scan,
            scan_id,
            min_drop_pct=min_drop_pct,
            candidate_limit=candidate_limit,
        )
        return {"status": "running", "scan_id": scan_id, "trigger_source": trigger_source, "auth_mode": auth_mode}

    await execute_scan(scan_id, min_drop_pct=min_drop_pct, candidate_limit=candidate_limit)
    return _scan_detail(scan_id)


@router.patch("/api/oversold/candidates/{candidate_id}")
def update_candidate(
    candidate_id: int,
    payload: dict[str, Any],
    _: str = Depends(require_basic),
) -> dict[str, Any]:
    decision = str(payload.get("decision") or "").lower()
    if decision not in {"unreviewed", "watch", "investigate", "pass", "traded"}:
        raise HTTPException(400, "Invalid decision")
    review_notes = str(payload.get("review_notes") or "")[:4000]
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE or_candidates SET decision=%s,review_notes=%s,reviewed_at=now()
                WHERE id=%s RETURNING id,decision,review_notes,reviewed_at
                """,
                (decision, review_notes, candidate_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Candidate not found")
        conn.commit()
    return row
