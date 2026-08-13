from __future__ import annotations

from app.live_maintenance import _signal_freeze_enabled


def test_signal_freeze_gate_defaults_enabled(monkeypatch) -> None:
    monkeypatch.delenv("E003C_SIGNAL_FREEZE_ENABLED", raising=False)
    assert _signal_freeze_enabled() is True


def test_signal_freeze_gate_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("E003C_SIGNAL_FREEZE_ENABLED", "false")
    assert _signal_freeze_enabled() is False
