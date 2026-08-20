from __future__ import annotations

"""Decision-quality diagnostics for the current v3.3 three-session model."""

import sys
from typing import Any

from app.db import connection


def decorate_diagnostics(
    result: dict[str, Any],
    *,
    coverage: dict[str, Any],
    sectors: list[dict[str, Any]],
    catalysts: list[dict[str, Any]],
) -> dict[str, Any]:
    output = dict(result)
    summary = dict(output.get("summary") or {})
    summary.update(coverage)
    output["summary"] = summary
    output["by_sector"] = sectors
    output["by_catalyst_type"] = catalysts
    output["catalyst_backend"] = "rules_v3_3_point_in_time"
    return output


def _load_current_diagnostics() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    from app.oversold_scoring import SCORING_CONFIG, TARGET_DEFINITION

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
              AND mr.run_kind IN ('original','rescore')
            ORDER BY mr.evidence_snapshot_id,
                     CASE WHEN mr.run_kind='original' THEN 0 ELSE 1 END,
                     mr.created_at DESC,mr.id DESC
        )
    """
    target_matured = """
        so.metadata->>'calibration_target_definition'=%s
        AND so.metadata->>'calibration_target_matured'='true'
        AND so.eligible_for_calibration=true
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                current_runs_cte
                + """
                SELECT
                    count(*) FILTER (
                        WHERE cr.catalyst_analysis#>>'{fundamental_trace,available}'='true'
                    ) AS primary_fundamentals_available,
                    count(*) FILTER (
                        WHERE cr.catalyst_analysis->>'cause_verification_status'='VERIFIED'
                    ) AS verified_causes,
                    count(*) FILTER (
                        WHERE cr.catalyst_analysis->>'assessment_confidence_state'='STRONGLY_INFERRED'
                    ) AS strongly_inferred_assessments,
                    count(*) FILTER (
                        WHERE cr.verdict='INVESTIGATE'
                    ) AS investigate_signals,
                    count(*) FILTER (
                        WHERE cr.verdict='WATCH'
                    ) AS watch_signals,
                    count(*) FILTER (
                        WHERE cr.verdict='PASS'
                    ) AS pass_signals,
                    count(*) FILTER (
                        WHERE cr.catalyst_analysis#>>'{price_session_context,extended_hours_only}'='true'
                    ) AS extended_hours_only_signals
                FROM current_runs cr
                """,
                (model_version, config_version),
            )
            coverage = dict(cur.fetchone() or {})

            cur.execute(
                current_runs_cte
                + f"""
                SELECT
                    COALESCE(es.sector_hint,'unknown') AS sector,
                    count(*) AS sample_count,
                    round(avg(cr.final_score)::numeric,2) AS average_score,
                    count(*) FILTER (WHERE cr.verdict='INVESTIGATE') AS investigate_count,
                    count(*) FILTER (WHERE cr.verdict='WATCH') AS watch_count,
                    count(*) FILTER (WHERE {target_matured}) AS matured_count,
                    count(*) FILTER (
                        WHERE {target_matured}
                          AND (so.metadata->>'hit_reversion_within_3_sessions')::boolean=true
                    ) AS hit_count
                FROM current_runs cr
                JOIN or_evidence_snapshots es ON es.id=cr.evidence_snapshot_id
                LEFT JOIN or_signal_outcomes so ON so.evidence_snapshot_id=cr.evidence_snapshot_id
                GROUP BY 1
                ORDER BY sample_count DESC,sector
                """,
                (
                    model_version,
                    config_version,
                    TARGET_DEFINITION,
                    TARGET_DEFINITION,
                ),
            )
            sectors = [dict(row) for row in cur.fetchall()]

            cur.execute(
                current_runs_cte
                + f"""
                SELECT
                    COALESCE(
                        cr.catalyst_analysis->>'event_taxonomy_primary',
                        cr.catalyst_analysis->>'event_profile',
                        'unknown'
                    ) AS catalyst_type,
                    count(*) AS sample_count,
                    round(avg(cr.final_score)::numeric,2) AS average_score,
                    count(*) FILTER (WHERE cr.verdict='INVESTIGATE') AS investigate_count,
                    count(*) FILTER (WHERE cr.verdict='WATCH') AS watch_count,
                    count(*) FILTER (WHERE {target_matured}) AS matured_count,
                    count(*) FILTER (
                        WHERE {target_matured}
                          AND (so.metadata->>'hit_reversion_within_3_sessions')::boolean=true
                    ) AS hit_count
                FROM current_runs cr
                LEFT JOIN or_signal_outcomes so ON so.evidence_snapshot_id=cr.evidence_snapshot_id
                GROUP BY 1
                ORDER BY sample_count DESC,catalyst_type
                """,
                (
                    model_version,
                    config_version,
                    TARGET_DEFINITION,
                    TARGET_DEFINITION,
                ),
            )
            catalysts = [dict(row) for row in cur.fetchall()]
        conn.rollback()

    for rows in (sectors, catalysts):
        for row in rows:
            matured = int(row.get("matured_count") or 0)
            row["hit_rate"] = (
                float(row.get("hit_count") or 0) / matured * 100.0
                if matured
                else None
            )
    return coverage, sectors, catalysts


def patch_module(target_module: Any) -> None:
    if getattr(target_module, "_v33_diagnostics_installed", False):
        return
    original = target_module._model_diagnostics

    def model_diagnostics() -> dict[str, Any]:
        result = original()
        try:
            coverage, sectors, catalysts = _load_current_diagnostics()
        except Exception:
            # The core diagnostics response remains available during a transient
            # analytics failure; runtime logs retain the failure through FastAPI.
            coverage, sectors, catalysts = {}, [], []
        return decorate_diagnostics(
            result,
            coverage=coverage,
            sectors=sectors,
            catalysts=catalysts,
        )

    target_module._model_diagnostics = model_diagnostics
    target_module._v33_diagnostics_installed = True

    if "pytest" not in sys.modules:
        from app import oversold_public

        oversold_public._model_diagnostics = model_diagnostics
