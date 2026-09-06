from __future__ import annotations

"""Three-trading-session calibration contract for Oversold Reversion.

The scoring model remains Score v3.2. This module versions the target/configuration
and patches the outcome/calibration runtime so a calibration success must occur by
the end of the third trading session after the stored signal. Longer-horizon
outcome fields remain available for research, but they cannot turn a late rebound
into a calibration success.
"""

import sys
from typing import Any

from app.db import connection

TARGET_DEFINITION = "hit_reversion_within_3_trading_sessions"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v4"
TARGET_TRADING_SESSIONS = 3
# Preserve the established internal reversion threshold. The user-facing UI no
# longer exposes the threshold; calibration changes here are about the horizon.
TARGET_RETURN_FRACTION = 0.05
CALIBRATION_FAMILY_VERSION = "regularized_logistic_score_3session_purged_v2"


def patch_scoring(module: Any) -> None:
    """Version the scoring contract without altering v3.2 score arithmetic."""
    module.SCORING_CONFIG_VERSION = SCORING_CONFIG_VERSION
    module.TARGET_DEFINITION = TARGET_DEFINITION
    module.SCORING_CONFIG["versions"]["scoring_config_version"] = SCORING_CONFIG_VERSION
    module.SCORING_CONFIG["target"] = {
        "field": TARGET_DEFINITION,
        "threshold_fraction": TARGET_RETURN_FRACTION,
        "horizon_trading_sessions": TARGET_TRADING_SESSIONS,
        "display_label": "reversion within 3 trading sessions",
    }
    module.SCORING_CONFIG.setdefault("calibration", {})["target_horizon_trading_sessions"] = TARGET_TRADING_SESSIONS


def _mark_three_session_targets() -> int:
    """Freeze the 3-session calibration label once three daily bars exist.

    ``trading_days_to_plus_5`` is retained as an internal legacy outcome field.
    It records the first session touching the established reversion threshold.
    Converting that to ``<= 3`` provides the new target without rewriting the
    long-horizon outcome schema or historical raw-price evidence.
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE or_signal_outcomes
                SET metadata = metadata || jsonb_build_object(
                    'calibration_target_definition', %s,
                    'calibration_target_matured', true,
                    'calibration_window_sessions', %s,
                    'calibration_window_end_ts', COALESCE(
                        NULLIF(metadata->>'calibration_window_end_ts','')::timestamptz,
                        signal_timestamp + interval '7 days'
                    ),
                    'hit_reversion_within_3_sessions', COALESCE(
                        trading_days_to_plus_5 BETWEEN 1 AND %s,
                        false
                    )
                ),
                updated_at = now()
                WHERE COALESCE(NULLIF(metadata->>'bar_count','')::int,0) >= %s
                  AND (
                    metadata->>'calibration_target_definition' IS DISTINCT FROM %s
                    OR metadata->>'calibration_target_matured' IS DISTINCT FROM 'true'
                    OR metadata->>'hit_reversion_within_3_sessions' IS NULL
                  )
                """,
                (
                    TARGET_DEFINITION,
                    TARGET_TRADING_SESSIONS,
                    TARGET_TRADING_SESSIONS,
                    TARGET_TRADING_SESSIONS,
                    TARGET_DEFINITION,
                ),
            )
            changed = cur.rowcount or 0
        conn.commit()
    return int(changed)


def _calibration_samples() -> list[dict[str, Any]]:
    """Load one current-model score per immutable Evidence Snapshot.

    Probability calibration uses only scores recorded at the original decision.
    Append-only historical rescores remain descriptive research, never holdout
    evidence for a model designed after those outcomes were observable.
    """
    from app.oversold_scoring import SCORING_CONFIG_VERSION as CURRENT_CONFIG, SCORING_MODEL_VERSION

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH current_runs AS (
                    SELECT DISTINCT ON (mr.evidence_snapshot_id)
                        mr.evidence_snapshot_id,
                        mr.final_score AS score,
                        mr.id AS model_run_id
                    FROM or_model_runs mr
                    WHERE mr.scoring_model_version=%s
                      AND mr.scoring_config_version=%s
                      AND mr.run_kind='original'
                    ORDER BY mr.evidence_snapshot_id,
                             CASE WHEN mr.run_kind='original' THEN 0 ELSE 1 END,
                             mr.created_at DESC,
                             mr.id DESC
                )
                SELECT cr.score,
                       (so.metadata->>'hit_reversion_within_3_sessions')::boolean AS target,
                       so.signal_timestamp,so.symbol,cr.evidence_snapshot_id,
                       cr.model_run_id,
                       (so.metadata->>'calibration_window_end_ts')::timestamptz AS outcome_end,
                       'original' AS run_kind,
                       COALESCE(es.sector_hint,'unknown') AS sector
                FROM current_runs cr
                JOIN or_evidence_snapshots es ON es.id=cr.evidence_snapshot_id
                JOIN or_signal_outcomes so ON so.evidence_snapshot_id=cr.evidence_snapshot_id
                WHERE so.eligible_for_calibration=true
                  AND so.metadata->>'calibration_target_definition'=%s
                  AND so.metadata->>'calibration_target_matured'='true'
                  AND so.metadata->>'three_session_path_contract'='completed_sessions_v2'
                  AND so.metadata->>'three_session_calendar_verified'='true'
                  AND so.metadata->>'target_contract_version'='three_session_target_v3'
                  AND so.metadata->>'hit_reversion_within_3_sessions' IS NOT NULL
                ORDER BY so.signal_timestamp,cr.model_run_id
                """,
                (SCORING_MODEL_VERSION, CURRENT_CONFIG, TARGET_DEFINITION),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()
    return rows


def _corporate_action_review_due(limit: int = 500) -> list[dict[str, Any]]:
    """Review the 3-session target window, not the legacy six-week horizon.

    The existing delayed/recheck corporate-action policy remains in force. This
    keeps calibration conservative while no longer requiring six-week outcome
    maturity before the review clock can start.
    """
    from app import oversold_corporate_actions as ca

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,candidate_id,symbol,signal_timestamp,signal_price,horizon_deadline,status,
                       corporate_action_status,eligible_for_calibration,metadata
                FROM or_signal_outcomes
                WHERE status IN ('pending','matured')
                  AND metadata->>'calibration_target_definition'=%s
                  AND metadata->>'calibration_target_matured'='true'
                  AND COALESCE(
                        NULLIF(metadata->>'calibration_window_end_ts','')::timestamptz,
                        signal_timestamp + interval '7 days'
                      ) + (%s * interval '1 day') <= now()
                  AND (
                    corporate_action_status IN ('unchecked','review_error')
                    OR (
                        corporate_action_status='clear'
                        AND COALESCE(
                              NULLIF(metadata->>'calibration_window_end_ts','')::timestamptz,
                              signal_timestamp + interval '7 days'
                            ) >= now() - (%s * interval '1 day')
                        AND COALESCE(
                              NULLIF(metadata->>'corporate_action_checked_at','')::timestamptz,
                              'epoch'::timestamptz
                            ) <= now() - (%s * interval '1 day')
                    )
                  )
                ORDER BY COALESCE(
                           NULLIF(metadata->>'calibration_window_end_ts','')::timestamptz,
                           signal_timestamp + interval '7 days'
                         ), id
                LIMIT %s
                """,
                (
                    TARGET_DEFINITION,
                    ca.REVIEW_LAG_DAYS,
                    ca.RECHECK_HORIZON_DAYS,
                    ca.RECHECK_INTERVAL_DAYS,
                    limit,
                ),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()
    return rows


def _model_diagnostics() -> dict[str, Any]:
    """Version-scoped diagnostics for the three-session calibration target."""
    from app.oversold_calibration import active_calibration_from_cursor
    from app.oversold_scoring import SCORING_CONFIG, public_scoring_contract

    versions = SCORING_CONFIG["versions"]
    model_version = versions["scoring_model_version"]
    config_version = versions["scoring_config_version"]
    current_runs_cte = """
        WITH current_runs AS (
            SELECT DISTINCT ON (mr.evidence_snapshot_id)
                mr.*
            FROM or_model_runs mr
            WHERE mr.scoring_model_version=%s
              AND mr.scoring_config_version=%s
              AND mr.run_kind='original'
            ORDER BY mr.evidence_snapshot_id,
                     CASE WHEN mr.run_kind='original' THEN 0 ELSE 1 END,
                     mr.created_at DESC,mr.id DESC
        )
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                current_runs_cte +
                """
                SELECT
                    count(*) AS scored_signals,
                    count(*) FILTER (WHERE cr.model_status='calibrated') AS calibrated_predictions,
                    count(*) FILTER (WHERE cr.missing_inputs @> '[\"company_specific_news\"]'::jsonb) AS missing_news_count,
                    count(*) FILTER (WHERE cr.missing_inputs @> '[\"point_in_time_fundamentals\"]'::jsonb) AS missing_fundamentals_count,
                    count(*) FILTER (WHERE cr.missing_inputs @> '[\"enrichment_partial_failure\"]'::jsonb) AS enrichment_failure_count,
                    count(*) FILTER (WHERE cr.hard_veto) AS hard_veto_count,
                    count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                      AND so.metadata->>'calibration_target_matured'='true') AS matured_outcomes,
                    count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                      AND so.metadata->>'calibration_target_matured'='true'
                                      AND so.eligible_for_calibration) AS calibration_eligible_matured,
                    count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                      AND so.metadata->>'calibration_target_matured'='true'
                                      AND so.eligible_for_calibration
                                      AND (so.metadata->>'hit_reversion_within_3_sessions')::boolean=true) AS eligible_hits,
                    count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                      AND so.metadata->>'calibration_target_matured'='true'
                                      AND so.eligible_for_calibration
                                      AND (so.metadata->>'hit_reversion_within_3_sessions')::boolean=false) AS eligible_misses,
                    count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                      AND so.metadata->>'calibration_target_matured'='true'
                                      AND so.corporate_action_status='affected') AS corporate_action_exclusions,
                    count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                      AND so.metadata->>'calibration_target_matured'='true'
                                      AND so.corporate_action_status='unchecked') AS corporate_action_unchecked
                FROM current_runs cr
                LEFT JOIN or_signal_outcomes so ON so.evidence_snapshot_id=cr.evidence_snapshot_id
                """,
                (
                    model_version,
                    config_version,
                    TARGET_DEFINITION,
                    TARGET_DEFINITION,
                    TARGET_DEFINITION,
                    TARGET_DEFINITION,
                    TARGET_DEFINITION,
                    TARGET_DEFINITION,
                ),
            )
            summary = dict(cur.fetchone() or {})

            cur.execute(
                current_runs_cte +
                """
                SELECT LEAST(9,FLOOR(cr.final_score/10)::int) AS bucket,
                       count(*) AS sample_count,
                       count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                         AND so.metadata->>'calibration_target_matured'='true'
                                         AND so.eligible_for_calibration) AS matured_count,
                       count(*) FILTER (WHERE so.metadata->>'calibration_target_definition'=%s
                                         AND so.metadata->>'calibration_target_matured'='true'
                                         AND so.eligible_for_calibration
                                         AND (so.metadata->>'hit_reversion_within_3_sessions')::boolean=true) AS hit_count
                FROM current_runs cr
                LEFT JOIN or_signal_outcomes so ON so.evidence_snapshot_id=cr.evidence_snapshot_id
                GROUP BY 1 ORDER BY 1
                """,
                (model_version, config_version, TARGET_DEFINITION, TARGET_DEFINITION),
            )
            buckets = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT * FROM or_calibration_runs
                WHERE scoring_model_version=%s AND scoring_config_version=%s
                ORDER BY created_at DESC,id DESC LIMIT 1
                """,
                (model_version, config_version),
            )
            latest_calibration = cur.fetchone()
            active_calibration = active_calibration_from_cursor(cur)
        conn.rollback()

    matured = int(summary.get("calibration_eligible_matured") or 0)
    positives = int(summary.get("eligible_hits") or 0)
    negatives = int(summary.get("eligible_misses") or 0)
    cfg = SCORING_CONFIG["calibration"]
    reasons: list[str] = []
    if matured < int(cfg["minimum_matured_signals"]):
        reasons.append(f"Need {cfg['minimum_matured_signals']} calibration-eligible 3-session outcomes; have {matured}.")
    if positives < int(cfg["minimum_positives"]):
        reasons.append(f"Need {cfg['minimum_positives']} positive 3-session outcomes; have {positives}.")
    if negatives < int(cfg["minimum_negatives"]):
        reasons.append(f"Need {cfg['minimum_negatives']} negative 3-session outcomes; have {negatives}.")
    if not active_calibration:
        reasons.append("No temporal calibration run has passed the quality checks for the current 3-session target.")

    calibrated = bool(active_calibration)
    return {
        "model_status": "calibrated" if calibrated else "uncalibrated",
        "calibration_status": "Calibrated" if calibrated else "Uncalibrated",
        "calibration_reasons": reasons,
        "summary": summary,
        "score_buckets": [
            {
                **row,
                "range": f"{int(row['bucket']) * 10}-{int(row['bucket']) * 10 + 9}",
                "hit_rate": (float(row["hit_count"]) / float(row["matured_count"]) * 100.0)
                            if row.get("matured_count") else None,
            }
            for row in buckets
        ],
        "by_sector": [],
        "by_catalyst_type": [],
        "latest_calibration_run": dict(latest_calibration) if latest_calibration else None,
        "active_calibration_run": dict(active_calibration) if active_calibration else None,
        "active_calibration_model_version": active_calibration.get("calibration_model_version") if active_calibration else None,
        "contract": public_scoring_contract(),
        "catalyst_backend": "rules_v3_2_point_in_time",
        "target_horizon_trading_sessions": TARGET_TRADING_SESSIONS,
        "calibration_guard": (
            "Calibration success must occur within 3 trading sessions. Later reversions remain research outcomes "
            "but do not count as calibration successes. Corporate-action review remains required before eligibility."
        ),
    }


def install_runtime_patches() -> None:
    """Patch runtime modules after the canonical scoring alias has been installed."""
    from app import oversold_calibration as calibration
    from app import oversold_corporate_actions as corporate_actions
    from app import oversold_outcomes as outcomes

    if not hasattr(outcomes, "_legacy_capture_signal_outcomes"):
        outcomes._legacy_capture_signal_outcomes = outcomes.capture_signal_outcomes

        async def capture_signal_outcomes(limit: int = 500) -> dict[str, int]:
            result = await outcomes._legacy_capture_signal_outcomes(limit=limit)
            result["three_session_targets_matured"] = _mark_three_session_targets()
            return result

        outcomes.capture_signal_outcomes = capture_signal_outcomes

    calibration._load_samples = _calibration_samples
    calibration.CALIBRATION_FAMILY_VERSION = CALIBRATION_FAMILY_VERSION

    if not hasattr(corporate_actions, "_legacy_classify_corporate_actions"):
        corporate_actions._legacy_classify_corporate_actions = corporate_actions.classify_corporate_actions

        def classify_corporate_actions(row: dict[str, Any], actions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
            adjusted = dict(row)
            metadata = adjusted.get("metadata") if isinstance(adjusted.get("metadata"), dict) else {}
            window_end = metadata.get("calibration_window_end_ts")
            if window_end:
                adjusted["horizon_deadline"] = window_end
            return corporate_actions._legacy_classify_corporate_actions(adjusted, actions)

        corporate_actions.classify_corporate_actions = classify_corporate_actions

    corporate_actions._load_review_due = _corporate_action_review_due

    # Importing the web router from package bootstrap is intentionally skipped in
    # pytest to keep pure scoring tests isolated from runtime settings. Production
    # imports it here so the diagnostics route resolves this versioned target.
    if "pytest" not in sys.modules:
        from app import oversold_public
        oversold_public._model_diagnostics = _model_diagnostics
