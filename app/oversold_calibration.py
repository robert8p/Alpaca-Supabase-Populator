from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from app.db import connection
from app.oversold_scoring import SCORING_CONFIG, SCORING_CONFIG_VERSION, SCORING_MODEL_VERSION

CALIBRATION_FAMILY_VERSION = "regularized_logistic_score_v1"
L2_PENALTY = 1.0
MAX_ITERATIONS = 100
CONVERGENCE_TOLERANCE = 1e-8
MAX_CALIBRATION_ERROR = 0.15
MIN_HALF_HOLDOUT_BRIER_SKILL = -0.10
MIN_SECTOR_SAMPLE_FOR_STABILITY = 20
MIN_SECTOR_BRIER_SKILL = -0.25


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 700.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -700.0))
    return z / (1.0 + z)


def calibrated_probability(raw_score: float, calibration: dict[str, Any] | None) -> float | None:
    if not calibration or not calibration.get("passed"):
        return None
    metrics = calibration.get("metrics") or {}
    coefficients = metrics.get("coefficients") or {}
    try:
        intercept = float(coefficients["intercept"])
        slope = float(coefficients["score_slope"])
    except (KeyError, TypeError, ValueError):
        return None
    x = (float(raw_score) - 50.0) / 10.0
    return _sigmoid(intercept + slope * x)


def active_calibration_from_cursor(cur: Any) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM or_calibration_runs
        WHERE passed=true AND scoring_model_version=%s AND scoring_config_version=%s
        ORDER BY created_at DESC,id DESC LIMIT 1
        """,
        (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def load_active_calibration() -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            row = active_calibration_from_cursor(cur)
        conn.rollback()
    return row


def _fit_regularized_logistic(samples: list[dict[str, Any]]) -> dict[str, float]:
    if not samples:
        raise ValueError("No calibration training samples")
    positives = sum(1 for row in samples if row["target"])
    base_rate = min(1.0 - 1e-6, max(1e-6, positives / len(samples)))
    intercept = math.log(base_rate / (1.0 - base_rate))
    slope = 0.0
    for _ in range(MAX_ITERATIONS):
        g0 = 0.0
        g1 = L2_PENALTY * slope
        h00 = 0.0
        h01 = 0.0
        h11 = L2_PENALTY
        for row in samples:
            x = (float(row["score"]) - 50.0) / 10.0
            y = 1.0 if row["target"] else 0.0
            p = _sigmoid(intercept + slope * x)
            weight = max(1e-9, p * (1.0 - p))
            error = p - y
            g0 += error
            g1 += error * x
            h00 += weight
            h01 += weight * x
            h11 += weight * x * x
        determinant = h00 * h11 - h01 * h01
        if abs(determinant) < 1e-12:
            break
        delta0 = (h11 * g0 - h01 * g1) / determinant
        delta1 = (-h01 * g0 + h00 * g1) / determinant
        intercept -= delta0
        slope -= delta1
        if max(abs(delta0), abs(delta1)) < CONVERGENCE_TOLERANCE:
            break
    return {"intercept": intercept, "score_slope": slope, "l2_penalty": L2_PENALTY}


def _predict(coefficients: dict[str, float], score: float) -> float:
    x = (float(score) - 50.0) / 10.0
    return _sigmoid(coefficients["intercept"] + coefficients["score_slope"] * x)


def _brier(rows: list[dict[str, Any]], probabilities: list[float]) -> float | None:
    if not rows:
        return None
    return sum((p - (1.0 if row["target"] else 0.0)) ** 2 for row, p in zip(rows, probabilities, strict=True)) / len(rows)


def _auc(rows: list[dict[str, Any]], probabilities: list[float]) -> float | None:
    paired = sorted(zip(probabilities, rows, strict=True), key=lambda item: item[0])
    positives = sum(1 for _, row in paired if row["target"])
    negatives = len(paired) - positives
    if positives == 0 or negatives == 0:
        return None
    rank_sum = 0.0
    index = 0
    while index < len(paired):
        end = index + 1
        while end < len(paired) and paired[end][0] == paired[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(1 for _, row in paired[index:end] if row["target"])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _calibration_buckets(rows: list[dict[str, Any]], probabilities: list[float], buckets: int = 10) -> tuple[list[dict[str, Any]], float]:
    output: list[dict[str, Any]] = []
    weighted_error = 0.0
    total = len(rows)
    for bucket in range(buckets):
        low = bucket / buckets
        high = (bucket + 1) / buckets
        members = [(row, p) for row, p in zip(rows, probabilities, strict=True) if (low <= p < high) or (bucket == buckets - 1 and p == 1.0)]
        if not members:
            continue
        mean_p = sum(p for _, p in members) / len(members)
        actual = sum(1.0 if row["target"] else 0.0 for row, _ in members) / len(members)
        error = abs(mean_p - actual)
        weighted_error += error * len(members)
        output.append({"low": low, "high": high, "count": len(members), "mean_probability": mean_p, "actual_rate": actual, "absolute_error": error})
    return output, weighted_error / total if total else 1.0


def _brier_skill(rows: list[dict[str, Any]], probabilities: list[float], base_rate: float) -> tuple[float | None, float | None, float | None]:
    brier = _brier(rows, probabilities)
    base = _brier(rows, [base_rate] * len(rows))
    if brier is None or base is None or base <= 0:
        return brier, base, None
    return brier, base, 1.0 - (brier / base)


def _load_samples() -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mr.final_score AS score,so.hit_plus_5pct_within_6_weeks AS target,
                       so.signal_timestamp,COALESCE(es.sector_hint,'unknown') AS sector
                FROM or_model_runs mr
                JOIN or_signal_outcomes so ON so.model_run_id=mr.id
                JOIN or_evidence_snapshots es ON es.id=mr.evidence_snapshot_id
                WHERE mr.run_kind='original'
                  AND mr.scoring_model_version=%s AND mr.scoring_config_version=%s
                  AND so.status='matured' AND so.eligible_for_calibration=true
                  AND so.hit_plus_5pct_within_6_weeks IS NOT NULL
                ORDER BY so.signal_timestamp,mr.id
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()
    return rows


def calibration_readiness(samples: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = SCORING_CONFIG["calibration"]
    positives = sum(1 for row in samples if row["target"])
    negatives = len(samples) - positives
    reasons: list[str] = []
    if len(samples) < cfg["minimum_matured_signals"]:
        reasons.append(f"matured {len(samples)} < {cfg['minimum_matured_signals']}")
    if positives < cfg["minimum_positives"]:
        reasons.append(f"positives {positives} < {cfg['minimum_positives']}")
    if negatives < cfg["minimum_negatives"]:
        reasons.append(f"negatives {negatives} < {cfg['minimum_negatives']}")
    if len(samples) < cfg["minimum_temporal_holdout"] + 2:
        reasons.append("insufficient observations for temporal training/holdout split")
    return {"ready": not reasons, "sample_count": len(samples), "positive_count": positives, "negative_count": negatives, "reasons": reasons}


def run_calibration(
    samples: list[dict[str, Any]] | None = None,
    *,
    sample_hash: str | None = None,
) -> dict[str, Any]:
    samples = _load_samples() if samples is None else samples
    readiness = calibration_readiness(samples)
    if not readiness["ready"]:
        return {"status": "not_ready", **readiness}

    cfg = SCORING_CONFIG["calibration"]
    holdout_size = max(int(cfg["minimum_temporal_holdout"]), int(round(len(samples) * 0.20)))
    holdout_size = min(holdout_size, len(samples) - 2)
    training = samples[:-holdout_size]
    holdout = samples[-holdout_size:]
    coefficients = _fit_regularized_logistic(training)
    training_base_rate = sum(1 for row in training if row["target"]) / len(training)
    probabilities = [_predict(coefficients, row["score"]) for row in holdout]
    brier, base_brier, brier_skill = _brier_skill(holdout, probabilities, training_base_rate)
    buckets, calibration_error = _calibration_buckets(holdout, probabilities)
    auc = _auc(holdout, probabilities)

    halves: list[dict[str, Any]] = []
    midpoint = len(holdout) // 2
    for label, subset, probs in (("early", holdout[:midpoint], probabilities[:midpoint]), ("late", holdout[midpoint:], probabilities[midpoint:])):
        sub_brier, sub_base, sub_skill = _brier_skill(subset, probs, training_base_rate)
        halves.append({"window": label, "count": len(subset), "brier": sub_brier, "base_brier": sub_base, "brier_skill": sub_skill})

    sector_metrics: list[dict[str, Any]] = []
    sectors = sorted({str(row["sector"]) for row in holdout})
    for sector in sectors:
        indices = [idx for idx, row in enumerate(holdout) if str(row["sector"]) == sector]
        if len(indices) < MIN_SECTOR_SAMPLE_FOR_STABILITY:
            continue
        subset = [holdout[idx] for idx in indices]
        probs = [probabilities[idx] for idx in indices]
        sub_brier, sub_base, sub_skill = _brier_skill(subset, probs, training_base_rate)
        sector_metrics.append({"sector": sector, "count": len(indices), "brier": sub_brier, "base_brier": sub_base, "brier_skill": sub_skill})

    quality_checks = {
        "sample_thresholds": readiness,
        "positive_score_slope": coefficients["score_slope"] > 0,
        "positive_brier_skill": brier_skill is not None and brier_skill > 0,
        "calibration_error_acceptable": calibration_error <= MAX_CALIBRATION_ERROR,
        "temporal_halves_stable": all(item["brier_skill"] is not None and item["brier_skill"] >= MIN_HALF_HOLDOUT_BRIER_SKILL for item in halves),
        "sector_stability_where_testable": all(item["brier_skill"] is not None and item["brier_skill"] >= MIN_SECTOR_BRIER_SKILL for item in sector_metrics),
    }
    passed = all(value if isinstance(value, bool) else bool(value.get("ready")) for value in quality_checks.values())
    version = f"{CALIBRATION_FAMILY_VERSION}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    metrics = {
        "model_type": "regularized_logistic_regression",
        "feature": "raw_reversion_score",
        "feature_transform": "(score-50)/10",
        "sample_hash": sample_hash,
        "coefficients": coefficients,
        "training_count": len(training),
        "holdout_count": len(holdout),
        "training_base_rate": training_base_rate,
        "holdout_auc": auc,
        "calibration_buckets": buckets,
        "temporal_halves": halves,
        "sector_metrics": sector_metrics,
        "quality_thresholds": {
            "maximum_calibration_error": MAX_CALIBRATION_ERROR,
            "minimum_half_holdout_brier_skill": MIN_HALF_HOLDOUT_BRIER_SKILL,
            "minimum_sector_sample": MIN_SECTOR_SAMPLE_FOR_STABILITY,
            "minimum_sector_brier_skill": MIN_SECTOR_BRIER_SKILL,
        },
    }
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO or_calibration_runs(
                    calibration_model_version,scoring_model_version,scoring_config_version,
                    training_cutoff,temporal_holdout_start,temporal_holdout_end,
                    matured_count,positive_count,negative_count,brier_score,base_rate_brier,brier_skill,
                    calibration_error,metrics,quality_checks,passed
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,created_at
                """,
                (
                    version, SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION,
                    training[-1]["signal_timestamp"], holdout[0]["signal_timestamp"], holdout[-1]["signal_timestamp"],
                    len(samples), readiness["positive_count"], readiness["negative_count"], brier, base_brier, brier_skill,
                    calibration_error, Jsonb(metrics), Jsonb(quality_checks), passed,
                ),
            )
            inserted = cur.fetchone()
        conn.commit()
    return {
        "status": "passed" if passed else "failed_quality_checks",
        "calibration_run_id": inserted["id"],
        "calibration_model_version": version,
        "sample_hash": sample_hash,
        "passed": passed,
        "brier_score": brier,
        "base_rate_brier": base_brier,
        "brier_skill": brier_skill,
        "calibration_error": calibration_error,
        "auc": auc,
        "quality_checks": quality_checks,
    }


if __name__ == "__main__":
    print(json.dumps(run_calibration(), default=str, indent=2))
