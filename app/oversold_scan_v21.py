from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection
from app.massive_fundamentals import fetch_massive_fundamentals
from app.oversold import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_MIN_DROP_PCT,
    MAX_CANDIDATE_LIMIT,
    MIN_PREV_DOLLAR_VOLUME,
    MIN_PRICE,
    _extract_candidate,
    _fetch_news_map,
    _fetch_snapshots,
    _model_triage,
    _scan_lock,
    _score_candidate,
)
from app.oversold_score_store import persist_original_score
from app.oversold_scoring import (
    MODEL_STATUS,
    SCORING_CONFIG_VERSION,
    SCORING_MODEL_VERSION,
    TARGET_DEFINITION,
    classify_news_for_candidate,
    score_candidate,
)

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
HISTORY_LOOKBACK_DAYS = 160
HISTORY_BATCH_SIZE = 20
NON_OPERATING_V21_RE = re.compile(
    r"\b(etf|etn|exchange[- ]traded fund|exchange[- ]traded note|warrants?|rights?|units?|"
    r"preferred|inverse|leveraged|microsectors|proshares|direxion|tradr|leverage shares|t-rex|"
    r"defiance|graniteshares|yieldmax|roundhill|rex shares)\b",
    re.IGNORECASE,
)
NON_OPERATING_REFERENCE_TYPES = {"ETF", "ETN", "WARRANT", "RIGHT", "UNIT", "FUND", "PFD", "PREFERRED"}


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _operating_asset_v21(asset: dict[str, Any]) -> bool:
    name = str(asset.get("name") or "")
    return not bool(NON_OPERATING_V21_RE.search(name))


def _massive_reference_is_operating(fundamentals: dict[str, Any]) -> bool:
    details = fundamentals.get("ticker_details") if isinstance(fundamentals, dict) else None
    ticker_type = str((details or {}).get("type") or "").upper()
    return not ticker_type or ticker_type not in NON_OPERATING_REFERENCE_TYPES


async def _fetch_daily_history(
    client: AlpacaClient,
    symbols: list[str],
    *,
    cutoff: datetime,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    output: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    request_count = 0
    signal_date = cutoff.astimezone(NY).date()
    start = cutoff - timedelta(days=HISTORY_LOOKBACK_DAYS)
    for batch in _chunks(symbols, HISTORY_BATCH_SIZE):
        token: str | None = None
        while True:
            try:
                result = await client.fetch_bars_page(
                    symbols=batch,
                    timeframe="1Day",
                    start=start.isoformat().replace("+00:00", "Z"),
                    end=cutoff.isoformat().replace("+00:00", "Z"),
                    feed="sip",
                    adjustment="split",
                    asof=signal_date.isoformat(),
                    limit=10000,
                    page_token=token,
                )
            except Exception as exc:
                logger.warning("Oversold daily-history batch failed for %s: %s", ",".join(batch), exc)
                break
            request_count += 1
            data = result.data if isinstance(result.data, dict) else {}
            bars_by_symbol = data.get("bars") if isinstance(data.get("bars"), dict) else {}
            for symbol, bars in bars_by_symbol.items():
                if symbol not in output or not isinstance(bars, list):
                    continue
                for bar in bars:
                    if not isinstance(bar, dict):
                        continue
                    ts = _parse_ts(bar.get("t"))
                    if ts is None or ts.astimezone(NY).date() >= signal_date:
                        continue
                    output[symbol].append(dict(bar))
            token = data.get("next_page_token")
            if not token:
                break
    for symbol in output:
        output[symbol].sort(key=lambda bar: str(bar.get("t") or ""))
        output[symbol] = output[symbol][-80:]
    return output, request_count


async def execute_scan_v21(
    scan_id: UUID,
    *,
    min_drop_pct: float = DEFAULT_MIN_DROP_PCT,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> None:
    candidate_limit = min(max(int(candidate_limit), 1), MAX_CANDIDATE_LIMIT)
    async with _scan_lock:
        try:
            async with AlpacaClient(target_rpm=3000, max_retries=4, backoff_seconds=0.8) as client:
                assets = await client.list_assets(status="active")
                eligible_assets = [
                    asset for asset in assets
                    if asset.get("tradable") is True
                    and str(asset.get("asset_class") or "").lower() == "us_equity"
                    and "otc" not in str(asset.get("exchange") or "").lower()
                    and _operating_asset_v21(asset)
                    and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", str(asset.get("symbol") or "").upper())
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
                raw_candidates.sort(key=lambda item: item["drop_pct"])
                raw_candidates = raw_candidates[:candidate_limit]
                symbols = [item["symbol"] for item in raw_candidates]
                (news_map, news_requests), (history_map, history_requests), (fundamental_map, massive_requests) = await asyncio.gather(
                    _fetch_news_map(client, symbols, end_at=evidence_cutoff),
                    _fetch_daily_history(client, symbols, cutoff=evidence_cutoff),
                    fetch_massive_fundamentals(symbols, cutoff=evidence_cutoff),
                )

            enriched: list[dict[str, Any]] = []
            excluded_reference_instruments = 0
            for item in raw_candidates:
                fundamentals = fundamental_map.get(item["symbol"], {"available": False, "provider": "massive", "reason": "missing_result"})
                if not _massive_reference_is_operating(fundamentals):
                    excluded_reference_instruments += 1
                    continue
                raw_snapshot = dict(item.get("raw_snapshot") or {})
                raw_snapshot["historicalDailyBars"] = history_map.get(item["symbol"], [])
                raw_snapshot["fundamentals"] = fundamentals
                item["raw_snapshot"] = raw_snapshot
                item["fundamentals"] = fundamentals
                articles = news_map.get(item["symbol"], [])
                catalyst_class, catalyst_summary, risk_flags = classify_news_for_candidate(item, articles)
                legacy_score = _score_candidate(
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
                    heuristic_score=legacy_score,
                )
                model = score_candidate(item, articles, catalyst_class, risk_flags)
                item["model_score"] = model
                item["triage_label"] = _model_triage(catalyst_class, model)
                enriched.append(item)

            enriched.sort(key=lambda item: (-float(item["model_score"]["final_score"]), -float(item["model_score"]["evidence_confidence"]), item["drop_pct"]))
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
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (scan_id,symbol) DO UPDATE SET
                                rank=EXCLUDED.rank,last_price=EXCLUDED.last_price,drop_pct=EXCLUDED.drop_pct,
                                bid=EXCLUDED.bid,ask=EXCLUDED.ask,spread_pct=EXCLUDED.spread_pct,
                                catalyst_class=EXCLUDED.catalyst_class,catalyst_summary=EXCLUDED.catalyst_summary,
                                risk_flags=EXCLUDED.risk_flags,headline_count=EXCLUDED.headline_count,
                                headlines=EXCLUDED.headlines,heuristic_score=EXCLUDED.heuristic_score,
                                triage_label=EXCLUDED.triage_label,raw_snapshot=EXCLUDED.raw_snapshot
                            RETURNING id
                            """,
                            (
                                scan_id, rank, item["symbol"], item["name"], item["exchange"], item["prev_close"], item["last_price"], item["drop_pct"],
                                item["prev_volume"], item["prev_dollar_volume"], item["bid"], item["ask"], item["spread_pct"], item["latest_trade_ts"],
                                item["catalyst_class"], item["catalyst_summary"], item["risk_flags"], item["headline_count"], Jsonb(item["headlines"]),
                                item["heuristic_score"], item["triage_label"], Jsonb(item["raw_snapshot"]),
                            ),
                        )
                        candidate_id = int(cur.fetchone()["id"])
                        persist_original_score(cur, candidate_id=candidate_id, scan_id=scan_id, item=item, score=item["model_score"], evidence_cutoff=evidence_cutoff)
                    cur.execute(
                        """
                        UPDATE or_scans SET status='completed',asset_count=%s,snapshot_count=%s,candidate_count=%s,completed_at=now(),metadata=%s WHERE id=%s
                        """,
                        (
                            len(eligible_assets), len(snapshots), len(enriched),
                            Jsonb({
                                "snapshot_requests": snapshot_requests,
                                "news_requests": news_requests,
                                "history_requests": history_requests,
                                "massive_requests": massive_requests,
                                "history_lookback_days": HISTORY_LOOKBACK_DAYS,
                                "feed": "sip",
                                "history_adjustment": "split",
                                "instrument_filter": "operating_company_v2_1",
                                "reference_instruments_excluded": excluded_reference_instruments,
                                "legacy_scoring_model": "heuristic_v1",
                                "scoring_model": SCORING_MODEL_VERSION,
                                "scoring_config": SCORING_CONFIG_VERSION,
                                "model_status": MODEL_STATUS,
                                "target_definition": TARGET_DEFINITION,
                                "evidence_cutoff": evidence_cutoff.isoformat(),
                            }),
                            scan_id,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            logger.exception("Oversold Reversion v2.1 scan %s failed", scan_id)
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE or_scans SET status='failed',error=%s,completed_at=now() WHERE id=%s", (str(exc)[:4000], scan_id))
                conn.commit()
