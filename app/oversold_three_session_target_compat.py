from __future__ import annotations

"""Replace the legacy target marker with the explicit v2 three-session contract."""

from typing import Any

from app.oversold_three_session_reliability import backfill_target_metadata


def patch_module(module: Any) -> None:
    if getattr(module, "_target_v2_marker_installed", False):
        return

    def mark_three_session_targets() -> int:
        return int(backfill_target_metadata()["updated"])

    module._mark_three_session_targets = mark_three_session_targets
    module._target_v2_marker_installed = True
