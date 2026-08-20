from __future__ import annotations

"""Diagnostics for v3.5 robust ensemble scoring."""

import sys
from typing import Any

from app.db import connection


def _summary() -> dict[str, Any]:
    from app.oversold_scoring import SCORING_CONFIG_VERSION, SCORING_MODEL_VERSION

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH current_runs AS (
                  SELECT DISTINCT ON (evidence_snapshot_id) *
                  FROM or_model_runs
                  WHERE scoring_model_version=%s
                    AND scoring_config_version=%s
                    AND run_kind IN ('original','rescore')
                  ORDER BY evidence_snapshot_id,
                           CASE WHEN run_kind='original' THEN 0 ELSE 1 END,
                           created_at DESC,id DESC
                )
                SELECT
                  count(*) AS scored_signals,
                  round(avg(final_score)::numeric,2) AS average_robust_score,
                  round(percentile_cont(0.5) within group(order by final_score)::numeric,2) AS median_robust_score,
                  round(max(final_score)::numeric,2) AS maximum_robust_score,
                  round(avg((catalyst_analysis->>'weight_stability_score')::numeric),2) AS average_weight_stability,
                  round(avg((catalyst_analysis->>'event_alignment_score')::numeric),2) AS average_event_alignment,
                  round(avg((catalyst_analysis->>'fundamental_data_quality_score')::numeric),2) AS average_fundamental_quality,
                  round(avg((catalyst_analysis->>'source_dependency_risk')::numeric),2) AS average_source_dependency_risk,
                  round(avg((catalyst_analysis->>'maximum_component_dependency')::numeric),2) AS average_component_dependency,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'causal_provenance_cluster_count')::int,0) >= 2
                  ) AS signals_with_two_causal_clusters,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'event_alignment_score')::numeric,0) >= 60
                  ) AS signals_with_aligned_events,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'fundamental_data_quality_score')::numeric,0) >= 60
                  ) AS signals_with_reliable_fundamentals,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'weight_stability_score')::numeric,0) < 70
                  ) AS weight_unstable_signals,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'maximum_component_dependency')::numeric,999) > 15
                  ) AS component_dependent_signals,
                  count(*) FILTER (WHERE verdict='INVESTIGATE') AS investigate_signals,
                  count(*) FILTER (WHERE verdict='WATCH') AS watch_signals,
                  count(*) FILTER (WHERE verdict='PASS') AS pass_signals
                FROM current_runs
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            summary = dict(cur.fetchone() or {})
            cur.execute(
                """
                WITH current_runs AS (
                  SELECT DISTINCT ON (evidence_snapshot_id) *
                  FROM or_model_runs
                  WHERE scoring_model_version=%s
                    AND scoring_config_version=%s
                    AND run_kind IN ('original','rescore')
                  ORDER BY evidence_snapshot_id,
                           CASE WHEN run_kind='original' THEN 0 ELSE 1 END,
                           created_at DESC,id DESC
                )
                SELECT
                  width_bucket(final_score,0,100,10) AS bucket,
                  count(*) AS signals,
                  round(avg((catalyst_analysis->>'weight_stability_score')::numeric),1) AS average_weight_stability,
                  round(avg((catalyst_analysis->>'event_alignment_score')::numeric),1) AS average_event_alignment
                FROM current_runs
                GROUP BY 1 ORDER BY 1
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            score_buckets = [dict(row) for row in cur.fetchall()]
        conn.rollback()

    scored = int(summary.get("scored_signals") or 0)
    actionable = int(summary.get("investigate_signals") or 0) + int(summary.get("watch_signals") or 0)
    selectivity_warning = None
    if scored >= 100 and actionable == 0:
        selectivity_warning = (
            "No WATCH or INVESTIGATE signal exists across at least 100 current-model snapshots. "
            "Treat this as a model-selectivity warning and retain positive-control/weight-ensemble tests; "
            "do not lower thresholds until matured outcomes show false negatives."
        )
    summary.update(
        {
            "robustness_version": "robust_weight_evidence_ensemble_v1",
            "score_buckets": score_buckets,
            "model_selectivity_warning": selectivity_warning,
            "actionable_signal_rate": actionable / scored if scored else None,
        }
    )
    return summary


def patch_module(target_module: Any) -> None:
    if getattr(target_module, "_v35_diagnostics_installed", False):
        return
    original = target_module._model_diagnostics

    def model_diagnostics() -> dict[str, Any]:
        result = original()
        try:
            robust = _summary()
        except Exception as exc:
            robust = {"status": "unavailable", "error": str(exc)[:500]}
        output = dict(result)
        output["score_robustness"] = robust
        output["catalyst_backend"] = "rules_v3_5_point_in_time_robust_ensemble"
        summary = dict(output.get("summary") or {})
        for key in (
            "average_robust_score",
            "median_robust_score",
            "maximum_robust_score",
            "average_weight_stability",
            "average_event_alignment",
            "average_fundamental_quality",
            "average_source_dependency_risk",
            "average_component_dependency",
            "signals_with_two_causal_clusters",
            "signals_with_aligned_events",
            "signals_with_reliable_fundamentals",
            "weight_unstable_signals",
            "component_dependent_signals",
            "model_selectivity_warning",
            "actionable_signal_rate",
        ):
            summary[key] = robust.get(key)
        output["summary"] = summary
        return output

    target_module._model_diagnostics = model_diagnostics
    target_module._v35_diagnostics_installed = True

    if "pytest" not in sys.modules:
        from app import oversold_public

        oversold_public._model_diagnostics = model_diagnostics
