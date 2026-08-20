from __future__ import annotations

"""Production-only compatibility helpers for the v3.3 scanner."""

from datetime import UTC, datetime
from typing import Any


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def patch_module(module: Any) -> None:
    """Expose the timestamp parser expected by the additive scan wrapper."""
    if not hasattr(module, "_parse_ts"):
        module._parse_ts = _parse_ts
