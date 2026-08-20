from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.oversold_outcomes_json_compat import patch_module


def test_outcome_jsonb_wrapper_serializes_datetimes_recursively() -> None:
    captured = {}

    def original(value):
        captured["value"] = value
        return value

    module = SimpleNamespace(Jsonb=original)
    patch_module(module)
    timestamp = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
    result = module.Jsonb({"first_bar_ts": timestamp, "nested": [timestamp]})
    assert result == {
        "first_bar_ts": "2026-08-20T20:00:00+00:00",
        "nested": ["2026-08-20T20:00:00+00:00"],
    }
    assert captured["value"] == result
    assert getattr(module, "_json_safe_outcomes_installed", False) is True
