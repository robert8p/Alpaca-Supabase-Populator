from __future__ import annotations

import hashlib
import json
from typing import Any

from app.db import connection
from app.oversold_calibration import _load_samples, calibration_readiness, run_calibration
from app.oversold_scoring import SCORING_CONFIG_VERSION, SCORING_MODEL_VERSION


def calibration_sample_hash(samples: list[dict[str, Any]]) -> str:
    payload = [
        {
            "score": float(row["score"]),
            "target": bool(row["target"]),
            "signal_timestamp": str(row["signal_timestamp"]),
            "sector": str(row.get("sector") or "unknown"),
        }
        for row in samples
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _latest_calibration_sample_hash() -> str | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT metrics->>'sample_hash' AS sample_hash
                FROM or_calibration_runs
                WHERE scoring_model_version=%s AND scoring_config_version=%s
                ORDER BY created_at DESC,id DESC LIMIT 1
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            row = cur.fetchone()
        conn.rollback()
    return str(row["sample_hash"]) if row and row.get("sample_hash") else None


def run_calibration_if_changed() -> dict[str, Any]:
    samples = _load_samples()
    readiness = calibration_readiness(samples)
    if not readiness["ready"]:
        return {"status": "not_ready", **readiness}

    sample_hash = calibration_sample_hash(samples)
    if _latest_calibration_sample_hash() == sample_hash:
        return {"status": "unchanged", "sample_hash": sample_hash, **readiness}

    return run_calibration(samples=samples, sample_hash=sample_hash)
