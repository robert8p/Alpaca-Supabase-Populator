from __future__ import annotations

"""Scanner-selection patch for Oversold Reversion v3.3.

The legacy scanner truncated the loser list by raw decline before causal and
economic analysis.  v3.3 uses a broad, bounded discovery pool and a cheap
decision-relevance priority before the full point-in-time model.  Magnitude is
therefore a trigger, not the ranking objective.
"""

import asyncio
import math
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.oversold_sec_fundamentals import fetch_sec_fundamentals_batch

NY = ZoneInfo("America/New_York")
MAX_MARKET_DISCOVERY_POOL = 300
MAX_FULL_ANALYSIS_POOL = 150


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _price_session(trade_ts: datetime | None) -> str:
    if trade_ts is None:
        return "unknown"
    local = trade_ts.astimezone(NY)
    if local.weekday() >= 5:
        return "closed"
    local_time = local.time()
    if local_time < time(9, 30):
        return "pre_market"
    if local_time < time(16, 0):
        return "regular"
    if local_time < time(20, 0):
        return "after_hours"
    return "closed"


def _market_prefilter_score(candidate: dict[str, Any]) -> float:
    dollar_volume = max(0.0, _finite(candidate.get("prev_dollar_volume")) or 0.0)
    spread = _finite(candidate.get("spread_pct"))
    decline = abs(min(_finite(candidate.get("drop_pct")) or 0.0, 0.0))
    liquidity = min(45.0, max(0.0, math.log10(max(1.0, dollar_volume / 100_000.0)) * 12.0))
    spread_quality = (
        25.0
        if spread is not None and spread <= 0.5
        else 20.0
        if spread is not None and spread <= 1.0
        else 13.0
        if spread is not None and spread <= 2.0
        else 5.0
        if spread is not None and spread <= 5.0
        else 0.0
    )
    abnormality = min(18.0, max(0.0, (decline - 12.0) * 0.65))
    volume = _finite(((candidate.get("raw_snapshot") or {}).get("dailyBar") or {}).get("v"))
    previous = _finite(candidate.get("prev_volume"))
    volume_quality = min(12.0, (volume / previous) * 4.0) if volume is not None and previous else 0.0
    extended_penalty = 10.0 if (candidate.get("price_session_context") or {}).get("extended_hours_only") else 0.0
    return liquidity + spread_quality + abnormality + volume_quality - extended_penalty


def _discovery_priority(candidate: dict[str, Any]) -> float:
    class_score = {
        "B": 32.0,
        "A": 27.0,
        "C": 20.0,
        "U": 4.0,
        "D": -25.0,
        "E": -55.0,
    }.get(str(candidate.get("catalyst_class") or "U"), 0.0)
    flags = {str(flag) for flag in (candidate.get("risk_flags") or [])}
    risk_penalty = 0.0
    for flag, penalty in {
        "solvency": 35.0,
        "delisting": 30.0,
        "dilution": 14.0,
        "clinical_regulatory": 12.0,
        "legal": 8.0,
        "earnings_guidance": 3.0,
    }.items():
        if flag in flags:
            risk_penalty += penalty
    news_bonus = min(8.0, float(candidate.get("headline_count") or 0) * 1.5)
    return _market_prefilter_score(candidate) + class_score + news_bonus - risk_penalty


def _critical_sec_symbols(candidates: list[dict[str, Any]], candidate_limit: int) -> list[str]:
    critical_flags = {
        "solvency",
        "dilution",
        "earnings_guidance",
        "clinical_regulatory",
        "delisting",
        "legal",
    }
    selected: list[str] = []
    for index, candidate in enumerate(candidates):
        flags = {str(flag) for flag in (candidate.get("risk_flags") or [])}
        catalyst_class = str(candidate.get("catalyst_class") or "U")
        if index < min(40, candidate_limit) or flags.intersection(critical_flags) or catalyst_class in {"C", "D", "E"}:
            selected.append(str(candidate["symbol"]).upper())
    return sorted(set(selected))


def patch_module(module: Any) -> None:
    if getattr(module, "_v33_scan_installed", False):
        return
    original_extract = module._extract_candidate

    def extract_candidate(
        symbol: str,
        snapshot: dict[str, Any],
        asset: dict[str, Any],
        min_drop_pct: float,
    ) -> dict[str, Any] | None:
        candidate = original_extract(symbol, snapshot, asset, min_drop_pct)
        if not candidate:
            return None
        latest_trade = snapshot.get("latestTrade") if isinstance(snapshot.get("latestTrade"), dict) else {}
        daily_bar = snapshot.get("dailyBar") if isinstance(snapshot.get("dailyBar"), dict) else {}
        trade_ts = module._parse_ts(latest_trade.get("t"))
        session = _price_session(trade_ts)
        prev_close = _finite(candidate.get("prev_close"))
        last_price = _finite(candidate.get("last_price"))
        regular_price = _finite(daily_bar.get("c"))
        if session == "regular":
            regular_price = last_price
        regular_move = (
            ((regular_price / prev_close) - 1.0) * 100.0
            if regular_price is not None and prev_close and prev_close > 0
            else None
        )
        current_move = _finite(candidate.get("drop_pct"))
        extended_move = (
            ((last_price / regular_price) - 1.0) * 100.0
            if last_price is not None and regular_price and regular_price > 0 and session != "regular"
            else None
        )
        extended_hours_only = bool(
            session in {"pre_market", "after_hours", "closed"}
            and current_move is not None
            and current_move <= -abs(min_drop_pct)
            and (regular_move is None or regular_move > -abs(min_drop_pct))
        )
        candidate["price_session_context"] = {
            "price_session": session,
            "latest_trade_timestamp": trade_ts,
            "current_price": last_price,
            "current_move_pct": round(current_move, 3) if current_move is not None else None,
            "regular_session_reference_price": regular_price,
            "regular_session_move_pct": round(regular_move, 3) if regular_move is not None else None,
            "extended_hours_move_pct": round(extended_move, 3) if extended_move is not None else None,
            "extended_hours_only": extended_hours_only,
            "rule": "latest SIP trade is the signal price; dailyBar close is retained as the regular-session reference when available",
        }
        return candidate

    async def execute_scan(
        scan_id: Any,
        *,
        min_drop_pct: float = module.DEFAULT_MIN_DROP_PCT,
        candidate_limit: int = module.DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        async with module._scan_lock:
            try:
                async with module.AlpacaClient(target_rpm=3000, max_retries=4, backoff_seconds=0.8) as client:
                    assets = await client.list_assets(status="active")
                    eligible_assets = [
                        asset
                        for asset in assets
                        if asset.get("tradable") is True
                        and str(asset.get("asset_class") or "").lower() == "us_equity"
                        and "otc" not in str(asset.get("exchange") or "").lower()
                        and module._is_operating_company_asset(asset)
                        and module.re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", str(asset.get("symbol") or "").upper())
                    ]
                    asset_by_symbol = {
                        str(asset["symbol"]).upper(): asset
                        for asset in eligible_assets
                        if asset.get("symbol")
                    }
                    snapshots, snapshot_requests = await module._fetch_snapshots(client, sorted(asset_by_symbol))
                    evidence_cutoff = datetime.now(UTC)
                    raw_candidates = [
                        candidate
                        for symbol, snapshot in snapshots.items()
                        if symbol in asset_by_symbol
                        and isinstance(snapshot, dict)
                        if (
                            candidate := extract_candidate(
                                symbol,
                                snapshot,
                                asset_by_symbol[symbol],
                                min_drop_pct,
                            )
                        )
                        is not None
                    ]
                    raw_loser_count = len(raw_candidates)
                    raw_candidates.sort(
                        key=lambda item: (
                            -_market_prefilter_score(item),
                            item.get("drop_pct") or 0.0,
                        )
                    )
                    market_pool_limit = min(
                        len(raw_candidates),
                        max(100, min(MAX_MARKET_DISCOVERY_POOL, int(candidate_limit) * 6)),
                    )
                    discovery_pool = raw_candidates[:market_pool_limit]
                    news_map, news_requests = await module._fetch_news_map(
                        client,
                        [item["symbol"] for item in discovery_pool],
                        end_at=evidence_cutoff,
                    )

                classified: list[dict[str, Any]] = []
                for item in discovery_pool:
                    articles = news_map.get(item["symbol"], [])
                    catalyst_class, catalyst_summary, risk_flags = module.classify_news_for_candidate(item, articles)
                    legacy_score = module._score_candidate(
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
                    item["discovery_priority"] = round(_discovery_priority(item), 2)
                    classified.append(item)

                classified.sort(
                    key=lambda item: (
                        -float(item.get("discovery_priority") or 0.0),
                        item.get("drop_pct") or 0.0,
                    )
                )
                analysis_pool_limit = min(
                    len(classified),
                    max(100, min(MAX_FULL_ANALYSIS_POOL, int(candidate_limit) * 2)),
                )
                analysis_pool = classified[:analysis_pool_limit]
                sec_symbols = _critical_sec_symbols(analysis_pool, int(candidate_limit))
                sec_fundamentals = await asyncio.to_thread(
                    fetch_sec_fundamentals_batch,
                    sec_symbols,
                    evidence_cutoff,
                )
                for item in analysis_pool:
                    item["_sec_prefetch_complete"] = True
                    if item["symbol"] in sec_fundamentals:
                        item["_sec_fundamentals"] = sec_fundamentals[item["symbol"]]

                enriched: list[dict[str, Any]] = []
                for item in analysis_pool:
                    item["evidence_cutoff"] = evidence_cutoff
                    model = module.score_candidate(
                        item,
                        item["headlines"],
                        item["catalyst_class"],
                        item["risk_flags"],
                    )
                    item["model_score"] = model
                    item["triage_label"] = module._model_triage(item["catalyst_class"], model)
                    enriched.append(item)

                verdict_order = {"INVESTIGATE": 3, "WATCH": 2, "PASS": 1}
                enriched.sort(
                    key=lambda item: (
                        -verdict_order.get(str(item["model_score"].get("verdict") or "PASS"), 0),
                        -float(item["model_score"]["final_score"]),
                        -float(
                            (item["model_score"].get("catalyst_analysis") or {}).get(
                                "overreaction_quality_score"
                            )
                            or 0.0
                        ),
                        -float(item["model_score"].get("evidence_confidence") or 0.0),
                        item.get("drop_pct") or 0.0,
                    )
                )
                enriched = enriched[: int(candidate_limit)]

                with module.connection() as conn:
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
                                    scan_id,
                                    rank,
                                    item["symbol"],
                                    item["name"],
                                    item["exchange"],
                                    item["prev_close"],
                                    item["last_price"],
                                    item["drop_pct"],
                                    item["prev_volume"],
                                    item["prev_dollar_volume"],
                                    item["bid"],
                                    item["ask"],
                                    item["spread_pct"],
                                    item["latest_trade_ts"],
                                    item["catalyst_class"],
                                    item["catalyst_summary"],
                                    item["risk_flags"],
                                    item["headline_count"],
                                    Jsonb(item["headlines"]),
                                    item["heuristic_score"],
                                    item["triage_label"],
                                    Jsonb(item["raw_snapshot"]),
                                ),
                            )
                            candidate_id = int(cur.fetchone()["id"])
                            module.persist_original_score(
                                cur,
                                candidate_id=candidate_id,
                                scan_id=scan_id,
                                item=item,
                                score=item["model_score"],
                                evidence_cutoff=evidence_cutoff,
                            )
                        cur.execute(
                            """
                            UPDATE or_scans
                            SET status='completed',asset_count=%s,snapshot_count=%s,candidate_count=%s,
                                completed_at=now(),metadata=%s
                            WHERE id=%s
                            """,
                            (
                                len(eligible_assets),
                                len(snapshots),
                                len(enriched),
                                Jsonb(
                                    {
                                        "snapshot_requests": snapshot_requests,
                                        "news_requests": news_requests,
                                        "feed": "sip",
                                        "news_lookback_hours": module.NEWS_LOOKBACK_HOURS,
                                        "min_price": module.MIN_PRICE,
                                        "min_prev_dollar_volume": module.MIN_PREV_DOLLAR_VOLUME,
                                        "instrument_filter": "operating_company_v1_2",
                                        "legacy_scoring_model": "heuristic_v1",
                                        "scoring_model": module.SCORING_MODEL_VERSION,
                                        "scoring_config": module.SCORING_CONFIG_VERSION,
                                        "model_status": module.MODEL_STATUS,
                                        "target_definition": module.TARGET_DEFINITION,
                                        "evidence_cutoff": evidence_cutoff.isoformat(),
                                        "selection_method": "v3_3_broad_discovery_then_opportunity_quality",
                                        "raw_loser_count": raw_loser_count,
                                        "market_discovery_pool_count": len(discovery_pool),
                                        "full_analysis_pool_count": len(analysis_pool),
                                        "sec_fundamental_requests": len(sec_symbols),
                                        "sec_fundamentals_found": len(sec_fundamentals),
                                    }
                                ),
                                scan_id,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                module.logger.exception("Oversold Reversion v3.3 scan %s failed", scan_id)
                with module.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE or_scans SET status='failed',error=%s,completed_at=now() WHERE id=%s",
                            (str(exc)[:4000], scan_id),
                        )
                    conn.commit()

    module._extract_candidate = extract_candidate
    module.execute_scan = execute_scan
    module._v33_scan_installed = True
