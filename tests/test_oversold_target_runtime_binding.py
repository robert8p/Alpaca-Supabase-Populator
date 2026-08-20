from __future__ import annotations

from types import SimpleNamespace

from app import oversold_three_session_target as live_target
from app.oversold_three_session_target_compat import patch_module


def test_target_hook_uses_v2_backfill(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.oversold_three_session_target_compat.backfill_target_metadata",
        lambda: {"updated": 7},
    )
    module = SimpleNamespace(_mark_three_session_targets=lambda: -1)
    patch_module(module)
    assert module._mark_three_session_targets() == 7
    assert getattr(module, "_target_v2_marker_installed", False) is True


def test_production_bootstrap_installs_target_v2_marker() -> None:
    assert getattr(live_target, "_target_v2_marker_installed", False) is True
