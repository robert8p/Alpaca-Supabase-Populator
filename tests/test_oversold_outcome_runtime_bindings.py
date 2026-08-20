from __future__ import annotations

import os
import subprocess
import sys


def test_worker_scheduler_uses_fully_patched_outcome_collector() -> None:
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
from app import oversold_outcome_scheduler, oversold_outcomes
assert oversold_outcome_scheduler.capture_signal_outcomes is oversold_outcomes.capture_signal_outcomes
assert getattr(oversold_outcomes, "_json_safe_outcomes_installed", False) is True
assert getattr(oversold_outcomes, "_v33_outcome_path_installed", False) is True
assert getattr(oversold_outcomes, "_three_session_target_reliability_installed", False) is True
print("outcome-binding-ok")
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
    assert "outcome-binding-ok" in completed.stdout
