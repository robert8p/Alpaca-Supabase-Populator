from __future__ import annotations

import asyncio
import os


FULL = "full"
OVERSOLD_ONLY = "oversold_only"
INTRADAY_ONLY = "intraday_only"
RESEARCH_WORKER = "research_worker"

VALID_RUNTIME_MODES = frozenset({FULL, OVERSOLD_ONLY, INTRADAY_ONLY, RESEARCH_WORKER})
_ten24_collection_scheduled = False


def runtime_mode() -> str:
    """Return the explicit deployment scope, failing closed on a typo."""
    mode = os.getenv("RUNTIME_MODE", FULL).strip().lower()
    if mode not in VALID_RUNTIME_MODES:
        expected = ", ".join(sorted(VALID_RUNTIME_MODES))
        raise RuntimeError(f"Unsupported RUNTIME_MODE={mode!r}; expected one of: {expected}")
    return mode


def canonical_schema_managed() -> bool:
    managed = os.getenv("CANONICAL_SCHEMA_MANAGED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    global _ten24_collection_scheduled
    if managed and not _ten24_collection_scheduled:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            from app.ten24_prospective_collect import run_ten24_prospective_collection_once

            loop.create_task(
                run_ten24_prospective_collection_once(),
                name="ten24-wide-prospective-collection",
            )
            _ten24_collection_scheduled = True
    return managed


def request_is_in_scope(mode: str, path: str) -> bool:
    """Keep health/static available and isolate each surviving public product."""
    if mode == FULL:
        return True
    if path == "/health" or path == "/static" or path.startswith("/static/"):
        return True
    if mode == OVERSOLD_ONLY:
        return (
            path in {"/oversold", "/oversold-v2"}
            or path.startswith("/api/oversold/")
            or path.startswith("/api/oversold-v2/")
        )
    if mode == INTRADAY_ONLY:
        return path == "/intraday-profitability" or path.startswith(
            "/api/intraday-profitability/"
        )
    return False


def root_redirect_for(mode: str) -> str | None:
    if mode == OVERSOLD_ONLY:
        return "/oversold"
    if mode == INTRADAY_ONLY:
        return "/intraday-profitability"
    return None
