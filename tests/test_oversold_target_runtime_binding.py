from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

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
    env = dict(os.environ)
    env.update(
        {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ALPACA_API_KEY": "test",
            "ALPACA_SECRET_KEY": "test",
            "AUTO_MIGRATE": "false",
        }
    )
    code = r'''
import app
from app import oversold_three_session_target as target
assert getattr(target, "_target_v2_marker_installed", False) is True
print("target-v2-marker-ok")
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "target-v2-marker-ok" in completed.stdout
