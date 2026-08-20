from __future__ import annotations

import os
import subprocess
import sys


def test_production_bootstrap_loads_scanner_and_runtime_patches() -> None:
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
from app import oversold
from app import oversold_calibration
from app import oversold_outcome_scheduler
from app import oversold_outcomes
from app import oversold_v2
from app.oversold_scoring import SCORING_CONFIG_VERSION, SCORING_MODEL_VERSION

assert SCORING_MODEL_VERSION == "oversold_reversion_score_v3_7"
assert SCORING_CONFIG_VERSION == "or_score_config_2026_08_20_v9"
assert hasattr(oversold, "_parse_ts")
assert getattr(oversold, "_v33_scan_installed", False) is True
assert getattr(oversold_outcomes, "_v33_outcome_path_installed", False) is True
assert getattr(oversold_outcomes, "_three_session_target_reliability_installed", False) is True
assert getattr(oversold_outcome_scheduler, "_three_session_outcome_bootstrap_installed", False) is True
assert getattr(oversold_calibration, "_v35_calibration_robustness_installed", False) is True
assert getattr(oversold_v2, "_session_filter_installed", False) is True
from app.oversold_scoring import public_scoring_contract
contract = public_scoring_contract()
assert contract["score_semantics"]["name"] == "Robust Opportunity Score"
assert contract["subject_attribution"]["version"] == "subject_attribution_v1"
assert contract["local_attribution"]["version"] == "local_clause_attribution_v1"
print("production-bootstrap-ok")
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
    assert "production-bootstrap-ok" in completed.stdout
