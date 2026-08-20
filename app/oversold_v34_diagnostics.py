from __future__ import annotations

"""Diagnostics for v3.4 conservative scenario scoring."""

import sys
from typing import Any

from app.db import connection


def _reliability_summary() -> dict[str, Any]:
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
                  round(avg((catalyst_analysis->>'reliability_stability_score')::numeric),2) AS average_stability,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'reliability_stability_score')::numeric,0) < 70
                  ) AS unstable_signals,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'evidence_contradiction_severity')::numeric,0) >= 50
                  ) AS material_contradictions,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'estimated_round_trip_friction_pct')::numeric,999) > 1.5
                  ) AS execution_friction_failures,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'primary_causal_evidence_count')::int,0) > 0
                  ) AS signals_with_primary_causal_evidence,
                  count(*) FILTER (
                    WHERE COALESCE((catalyst_analysis->>'independent_causal_source_count')::int,0) >= 2
                  ) AS signals_with_independent_causal_evidence,
                  count(*) FILTER (
                    WHERE catalyst_analysis#>>'{reliability_assessment,execution_friction,quote_state}'='off_hours_liquidity_proxy'
                  ) AS off_hours_proxy_signals,
                  count(*) FILTER (
                    WHERE catalyst_analysis#>>'{reliability_assessment,execution_friction,live_execution_recheck_required}'='true'
                  ) AS live_execution_rechecks_required,
                  round(avg((calculation_trace#>>'{v3_4_reliability,base_v33_score}')::numeric),2) AS average_base_v33_score,
                  round(avg(final_score)::numeric,2) AS average_conservative_score,
                  round(avg(
                    (calculation_trace#>>'{v3_4_reliability,base_v33_score}')::numeric - final_score
                  ),2) AS average_reliability_haircut,
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
                  width_bucket(
                    COALESCE((catalyst_analysis->>'reliability_stability_score')::numeric,0),
                    0,100,5
                  ) AS bucket,
                  count(*) AS signals,
                  round(avg(final_score)::numeric,2) AS average_score
                FROM current_runs
                GROUP BY 1 ORDER BY 1
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            stability_buckets = [dict(row) for row in cur.fetchall()]
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
                SELECT COALESCE(catalyst_analysis#>>'{reliability_assessment,version}','unknown') AS reliability_version,
                       count(*) AS signals
                FROM current_runs
                GROUP BY 1 ORDER BY signals DESC,reliability_version
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION),
            )
            reliability_versions = [dict(row) for row in cur.fetchall()]
        conn.rollback()
    summary["stability_buckets"] = stability_buckets
    summary["reliability_versions"] = reliability_versions
    summary["scoring_config_version"] = SCORING_CONFIG_VERSION
    return summary


def patch_module(target_module: Any) -> None:
    if getattr(target_module, "_v34_diagnostics_installed", False):
        return
    original = target_module._model_diagnostics

    def model_diagnostics() -> dict[str, Any]:
        result = original()
        try:
            reliability = _reliability_summary()
        except Exception as exc:
            reliability = {"status": "unavailable", "error": str(exc)[:500]}
        output = dict(result)
        output["score_reliability"] = reliability
        output["catalyst_backend"] = "rules_v3_4_point_in_time_scenario_stress"
        summary = dict(output.get("summary") or {})
        for key in (
            "average_stability",
            "unstable_signals",
            "material_contradictions",
            "execution_friction_failures",
            "signals_with_primary_causal_evidence",
            "signals_with_independent_causal_evidence",
            "off_hours_proxy_signals",
            "live_execution_rechecks_required",
            "average_base_v33_score",
            "average_conservative_score",
            "average_reliability_haircut",
        ):
            summary[key] = reliability.get(key)
        output["summary"] = summary
        return output

    target_module._model_diagnostics = model_diagnostics
    target_module._v34_diagnostics_installed = True

    if "pytest" not in sys.modules:
        from app import oversold_public

        oversold_public._model_diagnostics = model_diagnostics
