from __future__ import annotations

"""Presentation guard for the simplified day-loser view."""

from typing import Any


def _extended_hours_only(row: dict[str, Any]) -> bool:
    analysis = row.get("catalyst_analysis") if isinstance(row.get("catalyst_analysis"), dict) else {}
    context = analysis.get("price_session_context") if isinstance(analysis.get("price_session_context"), dict) else {}
    if not context:
        snapshot = row.get("raw_snapshot") if isinstance(row.get("raw_snapshot"), dict) else {}
        context = snapshot.get("price_session_context") if isinstance(snapshot.get("price_session_context"), dict) else {}
    value = context.get("extended_hours_only")
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def patch_module(module: Any) -> None:
    if getattr(module, "_session_filter_installed", False):
        return
    original = module._is_researchable_equity

    def is_researchable_equity(row: dict[str, Any]) -> bool:
        # The product promise is a list of the day's US equity losers. A name
        # whose regular-session move did not cross the threshold must not enter
        # the list merely because an after-hours print did.
        return bool(original(row)) and not _extended_hours_only(row)

    module._is_researchable_equity = is_researchable_equity
    module._session_filter_installed = True
