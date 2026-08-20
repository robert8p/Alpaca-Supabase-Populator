from __future__ import annotations

"""Runtime integration for point-in-time primary event evidence."""

import asyncio
from contextvars import ContextVar
from typing import Any

from psycopg.types.json import Jsonb

from app.oversold_primary_evidence import (
    PRIMARY_EVIDENCE_VERSION,
    fetch_primary_evidence_batch,
)

_CURRENT_SCAN_ID: ContextVar[str | None] = ContextVar("oversold_primary_evidence_scan_id", default=None)
_STATS_BY_SCAN: dict[str, dict[str, Any]] = {}


def _merge_articles(
    news_map: dict[str, list[dict[str, Any]]],
    primary_map: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    symbols = sorted(set(news_map) | set(primary_map))
    for symbol in symbols:
        # Primary records are retained first. Secondary news remains essential for
        # chronology and interpretation, but cannot crowd authoritative evidence
        # out of the bounded Evidence Snapshot.
        combined = [
            *(primary_map.get(symbol) or []),
            *(news_map.get(symbol) or []),
        ]
        seen: set[str] = set()
        retained: list[dict[str, Any]] = []
        for article in combined:
            if not isinstance(article, dict):
                continue
            key = str(
                article.get("id")
                or article.get("url")
                or article.get("headline")
                or ""
            )
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            retained.append(article)
        output[symbol] = retained[:18]
    return output


def patch_module(module: Any) -> None:
    if getattr(module, "_primary_evidence_runtime_installed", False):
        return

    original_news = module._fetch_news_map
    original_execute = module.execute_scan

    async def fetch_news_map(
        client: Any,
        symbols: list[str],
        *,
        end_at: Any,
    ) -> tuple[dict[str, list[dict[str, Any]]], int]:
        news_map, news_requests = await original_news(client, symbols, end_at=end_at)
        scan_id = _CURRENT_SCAN_ID.get()
        try:
            primary_map, stats = await asyncio.to_thread(
                fetch_primary_evidence_batch,
                symbols=symbols,
                existing_news_map=news_map,
                cutoff=end_at,
            )
        except Exception as exc:
            module.logger.exception("Primary event evidence batch failed")
            primary_map = {symbol: [] for symbol in symbols}
            stats = {
                "version": PRIMARY_EVIDENCE_VERSION,
                "requested_symbols": len(symbols),
                "selected_symbols": 0,
                "completed_symbols": 0,
                "primary_evidence_items": 0,
                "sec_filings": 0,
                "clinical_trial_records": 0,
                "fda_records": 0,
                "request_count": 0,
                "error_count": 1,
                "batch_error": str(exc)[:1000],
            }
        if scan_id:
            _STATS_BY_SCAN[scan_id] = stats
        return _merge_articles(news_map, primary_map), news_requests + int(stats.get("request_count") or 0)

    async def execute_scan(
        scan_id: Any,
        *,
        min_drop_pct: float = module.DEFAULT_MIN_DROP_PCT,
        candidate_limit: int = module.DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        key = str(scan_id)
        token = _CURRENT_SCAN_ID.set(key)
        _STATS_BY_SCAN.pop(key, None)
        try:
            await original_execute(
                scan_id,
                min_drop_pct=min_drop_pct,
                candidate_limit=candidate_limit,
            )
        finally:
            _CURRENT_SCAN_ID.reset(token)

        stats = _STATS_BY_SCAN.pop(key, None) or {
            "version": PRIMARY_EVIDENCE_VERSION,
            "requested_symbols": 0,
            "selected_symbols": 0,
            "completed_symbols": 0,
            "primary_evidence_items": 0,
            "sec_filings": 0,
            "clinical_trial_records": 0,
            "fda_records": 0,
            "request_count": 0,
            "error_count": 0,
            "status": "not_invoked",
        }
        try:
            with module.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE or_scans
                        SET metadata=COALESCE(metadata,'{}'::jsonb) || %s
                        WHERE id=%s
                        """,
                        (
                            Jsonb(
                                {
                                    "primary_event_evidence": stats,
                                    "primary_event_evidence_version": PRIMARY_EVIDENCE_VERSION,
                                    "primary_event_evidence_items": int(stats.get("primary_evidence_items") or 0),
                                    "primary_event_evidence_symbols": int(stats.get("symbols_with_primary_evidence") or 0),
                                }
                            ),
                            scan_id,
                        ),
                    )
                conn.commit()
        except Exception:
            # Evidence statistics are operational metadata. Their persistence must
            # never retroactively turn a completed, immutable signal scan into a
            # failed scan.
            module.logger.exception("Could not persist primary-evidence scan statistics")

    module._fetch_news_map = fetch_news_map
    module.execute_scan = execute_scan
    module._primary_evidence_runtime_installed = True
