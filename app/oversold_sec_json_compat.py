from __future__ import annotations

"""Normalize nested runtime payloads before JSONB persistence."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def json_safe(value: Any) -> Any:
    """Return a deterministic structure accepted by the standard JSON encoder."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe(item) for item in sorted(value, key=lambda item: str(item))]
    return value


def patch_module(module: Any) -> None:
    if getattr(module, "_json_safe_payloads_installed", False):
        return
    original_fetch = module.fetch_sec_fundamentals
    original_batch = module.fetch_sec_fundamentals_batch

    def fetch_sec_fundamentals(symbol: str, cutoff: datetime) -> dict[str, Any] | None:
        result = original_fetch(symbol, cutoff)
        return json_safe(result) if isinstance(result, dict) else None

    def fetch_sec_fundamentals_batch(
        symbols: list[str],
        cutoff: datetime,
        *,
        max_workers: int = module.SEC_MAX_WORKERS,
    ) -> dict[str, dict[str, Any]]:
        result = original_batch(symbols, cutoff, max_workers=max_workers)
        return {
            str(symbol): json_safe(fundamentals)
            for symbol, fundamentals in result.items()
            if isinstance(fundamentals, dict)
        }

    module.fetch_sec_fundamentals = fetch_sec_fundamentals
    module.fetch_sec_fundamentals_batch = fetch_sec_fundamentals_batch
    module._json_safe_payloads_installed = True
