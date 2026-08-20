from __future__ import annotations

"""Additional calibration gates for the v3.5 robust score.

A single train/holdout split can pass by chance. This layer requires the score to
show stable direction across deterministic bootstrap samples and expanding-window
temporal folds before a probability mapping may become active.
"""

import random
from statistics import median
from typing import Any

from psycopg.types.json import Jsonb

BOOTSTRAP_SEED = 3507
BOOTSTRAP_REPETITIONS = 200
MIN_BOOTSTRAP_POSITIVE_RATE = 0.80
MIN_QUARTILE_HIT_RATE_SEPARATION = 0.05
MIN_TEMPORAL_FOLDS = 3
MIN_TEMPORAL_NONNEGATIVE_SKILL_RATE = 0.60
MIN_MEDIAN_TEMPORAL_BRIER_SKILL = 0.0
MIN_MEDIAN_TEMPORAL_AUC = 0.55


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _direction(rows: list[dict[str, Any]]) -> float | None:
    positive = [float(row["score"]) for row in rows if bool(row["target"])]
    negative = [float(row["score"]) for row in rows if not bool(row["target"])]
    if not positive or not negative:
        return None
    return float(_mean(positive) or 0.0) - float(_mean(negative) or 0.0)


def _bootstrap_direction(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 20:
        return {"repetitions": 0, "valid_repetitions": 0, "positive_direction_rate": None, "median_direction": None}
    generator = random.Random(BOOTSTRAP_SEED)
    directions: list[float] = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        sample = [rows[generator.randrange(len(rows))] for _ in range(len(rows))]
        direction = _direction(sample)
        if direction is not None:
            directions.append(direction)
    return {
        "repetitions": BOOTSTRAP_REPETITIONS,
        "valid_repetitions": len(directions),
        "positive_direction_rate": (
            sum(1 for value in directions if value > 0) / len(directions)
            if directions else None
        ),
        "median_direction": median(directions) if directions else None,
    }


def _quartile_separation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 8:
        return {"bottom_count": 0, "top_count": 0, "bottom_hit_rate": None, "top_hit_rate": None, "separation": None}
    ordered = sorted(rows, key=lambda row: float(row["score"]))
    size = max(2, len(ordered) // 4)
    bottom = ordered[:size]
    top = ordered[-size:]
    bottom_rate = sum(1 for row in bottom if row["target"]) / len(bottom)
    top_rate = sum(1 for row in top if row["target"]) / len(top)
    return {
        "bottom_count": len(bottom),
        "top_count": len(top),
        "bottom_hit_rate": bottom_rate,
        "top_hit_rate": top_rate,
        "separation": top_rate - bottom_rate,
    }


def _temporal_folds(module: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (row["signal_timestamp"], float(row["score"])))
    if len(ordered) < 60:
        return []
    fold_size = max(20, len(ordered) // 6)
    first_test_start = max(fold_size * 2, len(ordered) - fold_size * MIN_TEMPORAL_FOLDS)
    folds: list[dict[str, Any]] = []
    start = first_test_start
    while start < len(ordered) and len(folds) < 5:
        training = ordered[:start]
        holdout = ordered[start:min(len(ordered), start + fold_size)]
        start += fold_size
        if len(training) < 30 or len(holdout) < 10:
            continue
        if not any(row["target"] for row in training) or all(row["target"] for row in training):
            continue
        if not any(row["target"] for row in holdout) or all(row["target"] for row in holdout):
            continue
        coefficients = module._fit_regularized_logistic(training)
        probabilities = [module._predict(coefficients, row["score"]) for row in holdout]
        training_base_rate = sum(1 for row in training if row["target"]) / len(training)
        brier, base_brier, skill = module._brier_skill(holdout, probabilities, training_base_rate)
        auc = module._auc(holdout, probabilities)
        folds.append(
            {
                "training_count": len(training),
                "holdout_count": len(holdout),
                "training_end": str(training[-1]["signal_timestamp"]),
                "holdout_start": str(holdout[0]["signal_timestamp"]),
                "holdout_end": str(holdout[-1]["signal_timestamp"]),
                "score_slope": coefficients["score_slope"],
                "brier": brier,
                "base_brier": base_brier,
                "brier_skill": skill,
                "auc": auc,
            }
        )
    return folds


def calibration_robustness_checks(module: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    bootstrap = _bootstrap_direction(rows)
    quartiles = _quartile_separation(rows)
    folds = _temporal_folds(module, rows)
    fold_skills = [float(row["brier_skill"]) for row in folds if row.get("brier_skill") is not None]
    fold_aucs = [float(row["auc"]) for row in folds if row.get("auc") is not None]
    nonnegative_rate = (
        sum(1 for value in fold_skills if value >= 0) / len(fold_skills)
        if fold_skills else None
    )
    checks = {
        "bootstrap_direction_stable": (
            bootstrap["positive_direction_rate"] is not None
            and bootstrap["positive_direction_rate"] >= MIN_BOOTSTRAP_POSITIVE_RATE
        ),
        "top_quartile_outperforms_bottom": (
            quartiles["separation"] is not None
            and quartiles["separation"] >= MIN_QUARTILE_HIT_RATE_SEPARATION
        ),
        "enough_temporal_folds": len(folds) >= MIN_TEMPORAL_FOLDS,
        "temporal_brier_skill_stable": (
            nonnegative_rate is not None
            and nonnegative_rate >= MIN_TEMPORAL_NONNEGATIVE_SKILL_RATE
            and median(fold_skills) >= MIN_MEDIAN_TEMPORAL_BRIER_SKILL
        ),
        "temporal_discrimination": (
            len(fold_aucs) >= MIN_TEMPORAL_FOLDS
            and median(fold_aucs) >= MIN_MEDIAN_TEMPORAL_AUC
        ),
    }
    return {
        "version": "calibration_robustness_v1",
        "sample_count": len(rows),
        "bootstrap": bootstrap,
        "quartile_separation": quartiles,
        "temporal_folds": folds,
        "temporal_nonnegative_brier_skill_rate": nonnegative_rate,
        "median_temporal_brier_skill": median(fold_skills) if fold_skills else None,
        "median_temporal_auc": median(fold_aucs) if fold_aucs else None,
        "thresholds": {
            "minimum_bootstrap_positive_rate": MIN_BOOTSTRAP_POSITIVE_RATE,
            "minimum_quartile_hit_rate_separation": MIN_QUARTILE_HIT_RATE_SEPARATION,
            "minimum_temporal_folds": MIN_TEMPORAL_FOLDS,
            "minimum_temporal_nonnegative_skill_rate": MIN_TEMPORAL_NONNEGATIVE_SKILL_RATE,
            "minimum_median_temporal_brier_skill": MIN_MEDIAN_TEMPORAL_BRIER_SKILL,
            "minimum_median_temporal_auc": MIN_MEDIAN_TEMPORAL_AUC,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def patch_module(module: Any, runtime_module: Any | None = None) -> None:
    if getattr(module, "_v35_calibration_robustness_installed", False):
        return
    original_run = module.run_calibration

    def run_calibration(
        samples: list[dict[str, Any]] | None = None,
        *,
        sample_hash: str | None = None,
    ) -> dict[str, Any]:
        resolved = module._load_samples() if samples is None else samples
        robustness = calibration_robustness_checks(module, resolved)
        result = original_run(samples=resolved, sample_hash=sample_hash)
        output = dict(result)
        output["calibration_robustness"] = robustness
        run_id = output.get("calibration_run_id")
        if run_id is None:
            return output
        passed = bool(output.get("passed")) and bool(robustness["passed"])
        with module.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE or_calibration_runs
                    SET metrics=metrics || %s,
                        quality_checks=quality_checks || %s,
                        passed=%s
                    WHERE id=%s
                    """,
                    (
                        Jsonb({"calibration_robustness": robustness}),
                        Jsonb({"v3_5_calibration_robustness": robustness["checks"]}),
                        passed,
                        run_id,
                    ),
                )
            conn.commit()
        output["passed"] = passed
        if not passed:
            output["status"] = "failed_robustness_checks"
        return output

    module.run_calibration = run_calibration
    module._v35_calibration_robustness_installed = True
    if runtime_module is not None:
        runtime_module.run_calibration = run_calibration
        runtime_module._load_samples = module._load_samples
