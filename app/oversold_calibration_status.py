from __future__ import annotations

"""Shared, version-scoped calibration readiness, distinct from model fitting.

This module never creates labels, mixes model versions, rewrites predictions or
promotes a probability. Scheduled checks persist a small latest-state record even
when there is insufficient evidence to fit a calibration model.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from app.db import connection
from app.oversold_calibration import SIGNAL_ZONE, VALIDATION_CONTRACT, _timestamp, calibration_readiness
from app.oversold_corporate_actions import REVIEW_LAG_DAYS
from app.oversold_scoring import SCORING_CONFIG_VERSION, SCORING_MODEL_VERSION

logger = logging.getLogger(__name__)
STATUS_VERSION = "calibration_pipeline_health_v1"
TARGET = "hit_reversion_within_3_trading_sessions"


def _true(value: Any) -> bool:
    return value is True or value == "true"


def build_pipeline_status(
    rows: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    *,
    now: datetime,
    latest_calibration: dict[str, Any] | None = None,
    last_check: dict[str, Any] | None = None,
    historical_signals: int = 0,
    excluded_rescores: int = 0,
) -> dict[str, Any]:
    now = now.astimezone(UTC)
    readiness = calibration_readiness(samples)
    counts = dict.fromkeys(("scored_signals", "matured_outcomes", "pending_outcomes", "missing_outcome_records",
                           "outcome_errors", "outcomes_never_evaluated", "mature_windows_awaiting_processing",
                           "waiting_review_lag", "reviews_due", "review_errors", "corporate_action_exclusions"), 0)
    counts["scored_signals"] = len(rows)
    signal_days = set()
    window_ends: list[datetime] = []
    review_dates: list[datetime] = []
    for row in rows:
        signal = _timestamp(row.get("signal_timestamp"))
        if signal is not None:
            signal_days.add(signal.astimezone(SIGNAL_ZONE).date())
        if row.get("outcome_id") is None:
            counts["missing_outcome_records"] += 1
            continue
        if row.get("last_evaluated_at") is None:
            counts["outcomes_never_evaluated"] += 1
        if row.get("error") or row.get("path_error"):
            counts["outcome_errors"] += 1
        end = _timestamp(row.get("window_end"))
        if end is not None and signal is not None and end > signal:
            if end > now:
                window_ends.append(end)
            if end + timedelta(days=REVIEW_LAG_DAYS) > now:
                review_dates.append(end + timedelta(days=REVIEW_LAG_DAYS))
        valid = (
            end is not None and signal is not None and signal < end <= now
            and row.get("target_definition") == TARGET
            and _true(row.get("target_matured")) and _true(row.get("path_matured"))
            and row.get("path_contract") == "completed_sessions_v2"
            and _true(row.get("calendar_verified"))
            and row.get("target_contract") == "three_session_target_v3"
        )
        if not valid:
            counts["pending_outcomes"] += 1
            if end is not None and end <= now:
                counts["mature_windows_awaiting_processing"] += 1
        else:
            counts["matured_outcomes"] += 1
            ca = row.get("corporate_action_status")
            if ca == "unchecked":
                if end + timedelta(days=REVIEW_LAG_DAYS) > now:
                    counts["waiting_review_lag"] += 1
                else:
                    counts["reviews_due"] += 1
            elif ca == "review_error":
                counts["review_errors"] += 1
            elif ca == "affected":
                counts["corporate_action_exclusions"] += 1
    counts.update({"current_signal_days": len(signal_days), "raw_eligible_samples": len(samples),
                   "independent_eligible_samples": readiness["sample_count"],
                   "independent_eligible_days": readiness["independent_signal_days"],
                   "positive_count": readiness["positive_count"], "negative_count": readiness["negative_count"],
                   "older_model_originals_excluded": int(historical_signals),
                   "historical_rescore_runs_excluded": int(excluded_rescores)})
    active = bool(latest_calibration and latest_calibration.get("passed"))
    check_result = (last_check or {}).get("result") or {}
    reasons = list(readiness["reasons"])
    if check_result.get("status") == "error":
        stage, label = "processing_error", "Calibration processing error"
        reasons.insert(0, "The most recent scheduled calibration check failed; probabilities were not promoted.")
    elif counts["outcome_errors"] or counts["review_errors"] or counts["missing_outcome_records"]:
        stage, label = "data_issue", "Outcome processing needs attention"
        reasons.insert(0, "Some outcome records or corporate-action reviews have errors; they are not usable evidence.")
    elif active:
        stage, label = "calibrated", "Calibrated"
        reasons = []
    elif latest_calibration and latest_calibration.get("passed") is False:
        stage, label = "failed_quality_checks", "Validation gates not passed"
        reasons.insert(0, "The latest fitted calibration failed quality checks. No probability mapping is active.")
    elif readiness["ready"]:
        stage, label = "ready_for_validation", "Ready for scheduled validation"
        reasons.append("Sample requirements are met; probability remains unavailable until all validation gates pass.")
    elif counts["reviews_due"] or counts["mature_windows_awaiting_processing"]:
        stage, label = "processing_due", "Outcome processing due"
        reasons.insert(0, "Completed outcome windows or eligible corporate-action reviews await the next processing cycle.")
    elif counts["waiting_review_lag"]:
        stage, label = "waiting_for_review", "Waiting for corporate-action review"
        reasons.insert(0, f"The retained corporate-action policy waits {REVIEW_LAG_DAYS} calendar days after the target window before review.")
    elif counts["pending_outcomes"] and not counts["matured_outcomes"]:
        stage, label = "collecting_outcomes", "Collecting three-session outcomes"
        reasons.insert(0, "The current model's original signals have not completed verified three-session outcomes.")
    else:
        stage, label = "collecting_evidence", "Collecting independent calibration evidence"
    return {
        "version": STATUS_VERSION, "stage": stage, "label": label,
        "model_status": "calibrated" if active else "uncalibrated",
        "target_definition": TARGET, "probability_target": "price_target_touch_not_net_profit",
        "scoring_model_version": SCORING_MODEL_VERSION, "scoring_config_version": SCORING_CONFIG_VERSION,
        "checked_at": now.isoformat(), "counts": counts, "readiness": readiness,
        "reasons": reasons, "corporate_action_review_lag_days": REVIEW_LAG_DAYS,
        "next_target_window_end": min(window_ends).isoformat() if window_ends else None,
        "next_policy_review_at": min(review_dates).isoformat() if review_dates else None,
        "last_scheduled_check": last_check,
        "notes": ["Only original scores from this exact model and configuration are calibration evidence.",
                  "Repeated signals with overlapping symbol/outcome windows are deduplicated before counting samples.",
                  "Older model scores and retrospective rescores are not substitutes for independent validation.",
                  "Window and review dates are processing milestones, not promised calibration activation dates.",
                  "A target-touch probability is not a probability of net trading profit."],
    }


def record_calibration_check(result: dict[str, Any]) -> None:
    """One latest record per model/config/validation contract; no unbounded audit growth."""
    # Preserve the original calibration result if monitoring storage is unavailable.
    # The error is logged, not converted to a successful check or a probability.
    try:
        payload = json.loads(json.dumps(result, default=str, allow_nan=False))
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.or_calibration_checks
                        (scoring_model_version,scoring_config_version,validation_contract,result)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (scoring_model_version,scoring_config_version,validation_contract)
                    DO UPDATE SET checked_at=now(),check_count=or_calibration_checks.check_count+1,
                                  result=EXCLUDED.result
                    """,
                    (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION, VALIDATION_CONTRACT, Jsonb(payload)),
                )
            conn.commit()
    except Exception:
        logger.exception("Could not persist calibration readiness check; no calibration state was fabricated")


def calibration_pipeline_status(*, latest_calibration: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.oversold_three_session_target import _calibration_samples

    samples = _calibration_samples()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH originals AS (
                    SELECT DISTINCT ON (evidence_snapshot_id) id,evidence_snapshot_id
                    FROM or_model_runs
                    WHERE run_kind='original' AND scoring_model_version=%s AND scoring_config_version=%s
                    ORDER BY evidence_snapshot_id,created_at,id
                )
                SELECT so.id AS outcome_id,es.signal_timestamp,so.last_evaluated_at,so.error,
                       so.corporate_action_status,
                       so.metadata->>'calibration_window_end_ts' AS window_end,
                       so.metadata->>'calibration_target_definition' AS target_definition,
                       so.metadata->>'calibration_target_matured' AS target_matured,
                       so.metadata->>'three_session_path_matured' AS path_matured,
                       so.metadata->>'three_session_path_contract' AS path_contract,
                       so.metadata->>'three_session_calendar_verified' AS calendar_verified,
                       so.metadata->>'target_contract_version' AS target_contract,
                       so.metadata->>'three_session_path_error' AS path_error
                FROM originals o
                JOIN or_evidence_snapshots es ON es.id=o.evidence_snapshot_id
                LEFT JOIN or_signal_outcomes so ON so.evidence_snapshot_id=o.evidence_snapshot_id
                ORDER BY es.signal_timestamp,o.id
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            rows = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT count(*) FILTER (WHERE run_kind='original' AND
                         (scoring_model_version<>%s OR scoring_config_version<>%s)) AS older_originals,
                       count(*) FILTER (WHERE run_kind='rescore') AS excluded_rescores
                FROM or_model_runs
                """, (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            historical = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT checked_at,check_count,result FROM public.or_calibration_checks
                WHERE scoring_model_version=%s AND scoring_config_version=%s AND validation_contract=%s
                """, (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION, VALIDATION_CONTRACT),
            )
            check = cur.fetchone()
            if latest_calibration is None:
                cur.execute(
                    """SELECT * FROM or_calibration_runs
                       WHERE scoring_model_version=%s AND scoring_config_version=%s
                       ORDER BY created_at DESC,id DESC LIMIT 1""",
                    (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
                )
                latest_calibration = cur.fetchone()
        conn.rollback()
    return build_pipeline_status(rows, samples, now=datetime.now(UTC),
                                 latest_calibration=dict(latest_calibration) if latest_calibration else None,
                                 last_check=dict(check) if check else None,
                                 historical_signals=int(historical.get("older_originals") or 0),
                                 excluded_rescores=int(historical.get("excluded_rescores") or 0))
