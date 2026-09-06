from __future__ import annotations

"""Evaluation reports aligned to the live three-session target."""

from collections import defaultdict
import math
from typing import Any

from app.db import connection

TARGET_DEFINITION = "hit_reversion_within_3_trading_sessions"


def _num(value: Any) -> float | None:
    try:
        number = float(value) if value is not None else None
        return number if number is not None and math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def profit_proxy_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Report specified exits and cost scenarios separately from target touches."""
    modeled = []
    for row in rows:
        proxy = row.get("profit_proxy") or {}
        if not isinstance(proxy, dict) or proxy.get("status") != "modeled":
            continue
        base, stress = _num(proxy.get("net_return_pct")), _num(proxy.get("stress_net_return_pct"))
        if base is not None and stress is not None:
            modeled.append((base, stress))
    return {
        "sample_count": len(modeled),
        "missing_proxy_count": len(rows) - len(modeled),
        "mean_net_return_pct": _mean([base for base, _ in modeled]),
        "mean_stress_net_return_pct": _mean([stress for _, stress in modeled]),
        "positive_net_exit_rate": sum(base > 0 for base, _ in modeled) / len(modeled) if modeled else None,
        "positive_stress_net_exit_rate": sum(stress > 0 for _, stress in modeled) / len(modeled) if modeled else None,
        "profitable_strategy_validated": False,
        "limitation": "Modeled next-session daily open to third-session close with assumed costs; unverified fills and portfolio returns. Target-touch hit rate is not profitable-trade probability.",
    }


def _bucket(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    output: dict[str, dict[str, Any]] = {}
    for label, values in sorted(grouped.items()):
        output[label] = {
            "n": len(values),
            "exit_return_proxy": profit_proxy_metrics(values),
            "three_session_hit_rate": sum(1 for row in values if row["target"]) / len(values),
            "plus_10_mfe_rate": sum(1 for row in values if (_num(row.get("mfe_3d")) or -999.0) >= 10.0) / len(values),
            "mean_mfe_3d": _mean([value for row in values if (value := _num(row.get("mfe_3d"))) is not None]),
            "mean_mae_3d": _mean([value for row in values if (value := _num(row.get("mae_3d"))) is not None]),
            "mean_return_3d": _mean([value for row in values if (value := _num(row.get("return_3d"))) is not None]),
        }
    return output


def patch_module(module: Any) -> None:
    if getattr(module, "_three_session_evaluation_installed", False):
        return

    def evaluation_report(
        *,
        model_version: str = module.SCORING_MODEL_VERSION,
        config_version: str = module.SCORING_CONFIG_VERSION,
        run_kind: str = "original",
    ) -> dict[str, Any]:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT mr.id,mr.candidate_id,mr.final_score AS score,mr.verdict,
                           mr.calibrated_probability,mr.catalyst_analysis,mr.evidence_confidence,
                           mr.damage_risk,
                           (so.metadata->>'hit_reversion_within_3_sessions')::boolean AS target,
                           so.mfe_3d,so.mae_3d,so.return_3d,
                           so.metadata->'profit_proxy_3d' AS profit_proxy,
                           so.time_to_mfe_3d_sessions,so.time_to_mae_3d_sessions
                    FROM or_model_runs mr
                    JOIN or_signal_outcomes so ON so.evidence_snapshot_id=mr.evidence_snapshot_id
                    WHERE mr.run_kind=%s
                      AND mr.scoring_model_version=%s
                      AND mr.scoring_config_version=%s
                      AND so.eligible_for_calibration=true
                      AND so.metadata->>'calibration_target_definition'=%s
                      AND so.metadata->>'calibration_target_matured'='true'
                      AND so.metadata->>'three_session_path_contract'='completed_sessions_v2'
                      AND so.metadata->>'three_session_calendar_verified'='true'
                      AND so.metadata->>'hit_reversion_within_3_sessions' IS NOT NULL
                    ORDER BY mr.id
                    """,
                    (run_kind, model_version, config_version, TARGET_DEFINITION),
                )
                rows = [dict(row) for row in cur.fetchall()]
            conn.rollback()
        for row in rows:
            analysis = row.get("catalyst_analysis") or {}
            row["event_profile"] = (
                analysis.get("event_taxonomy_primary")
                or analysis.get("event_profile")
                or "unknown"
            )
            row["cause_status"] = analysis.get("cause_verification_status") or "UNVERIFIED"
            row["stability_bucket"] = (
                "stable"
                if (_num(analysis.get("reliability_stability_score")) or 0.0) >= 70.0
                else "unstable"
            )
            row["primary_evidence_bucket"] = (
                "primary_causal"
                if int(analysis.get("primary_causal_evidence_count") or 0) > 0
                else "no_primary_causal"
            )
        hits = sum(1 for row in rows if row["target"])
        calibrated = [row for row in rows if _num(row.get("calibrated_probability")) is not None]
        brier = _mean([
            (float(row["calibrated_probability"]) - (1.0 if row["target"] else 0.0)) ** 2
            for row in calibrated
        ]) if calibrated else None
        investigate = [row for row in rows if row.get("verdict") == "INVESTIGATE"]
        watch = [row for row in rows if row.get("verdict") == "WATCH"]
        passed = [row for row in rows if row.get("verdict") == "PASS"]
        return {
            "scoring_model_version": model_version,
            "scoring_config_version": config_version,
            "target_definition": TARGET_DEFINITION,
            "run_kind": run_kind,
            "sample_size": len(rows),
            "target_is_profitability": False,
            "exit_return_proxy": profit_proxy_metrics(rows),
            "profitability_validation": "not_established",
            "three_session_hit_rate": hits / len(rows) if rows else None,
            "plus_10_mfe_rate": sum(1 for row in rows if (_num(row.get("mfe_3d")) or -999.0) >= 10.0) / len(rows) if rows else None,
            "mean_mfe_3d": _mean([value for row in rows if (value := _num(row.get("mfe_3d"))) is not None]),
            "mean_mae_3d": _mean([value for row in rows if (value := _num(row.get("mae_3d"))) is not None]),
            "mean_return_3d": _mean([value for row in rows if (value := _num(row.get("return_3d"))) is not None]),
            "roc_auc_raw_score": module._auc(rows),
            "pr_auc_raw_score": module._pr_auc(rows),
            "brier_score_if_calibrated": brier,
            "verdict_performance": _bucket(rows, "verdict"),
            "event_type_performance": _bucket(rows, "event_profile"),
            "cause_verification_performance": _bucket(rows, "cause_status"),
            "stability_performance": _bucket(rows, "stability_bucket"),
            "primary_evidence_performance": _bucket(rows, "primary_evidence_bucket"),
            "investigate_precision": sum(1 for row in investigate if row["target"]) / len(investigate) if investigate else None,
            "watch_hit_rate": sum(1 for row in watch if row["target"]) / len(watch) if watch else None,
            "pass_hit_rate": sum(1 for row in passed if row["target"]) / len(passed) if passed else None,
            "limitation": "Target-touch event statistics are descriptive; no out-of-sample net profitability has been established." if rows else "No corporate-action-cleared, calendar-verified, matured three-session outcomes exist for this model/config yet.",
        }

    def original_vs_rescore_report(
        *,
        new_model_version: str = module.SCORING_MODEL_VERSION,
        new_config_version: str = module.SCORING_CONFIG_VERSION,
    ) -> dict[str, Any]:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT old.candidate_id,old.scoring_model_version AS old_version,
                           old.final_score AS old_score,old.verdict AS old_verdict,
                           new.final_score AS new_score,new.verdict AS new_verdict,
                           new.catalyst_analysis AS new_analysis,
                           (so.metadata->>'hit_reversion_within_3_sessions')::boolean AS target,
                           so.mfe_3d,so.mae_3d,so.return_3d,
                           so.metadata->'profit_proxy_3d' AS profit_proxy,
                           so.metadata->>'calibration_target_matured' AS target_matured,
                           so.eligible_for_calibration
                    FROM or_model_runs old
                    JOIN or_model_runs new
                      ON new.candidate_id=old.candidate_id
                     AND new.evidence_snapshot_id=old.evidence_snapshot_id
                    LEFT JOIN or_signal_outcomes so ON so.evidence_snapshot_id=old.evidence_snapshot_id
                    WHERE old.run_kind='original' AND new.run_kind='rescore'
                      AND new.scoring_model_version=%s AND new.scoring_config_version=%s
                      AND NOT (
                        old.scoring_model_version=%s AND old.scoring_config_version=%s
                      )
                    ORDER BY old.candidate_id
                    """,
                    (
                        new_model_version,
                        new_config_version,
                        new_model_version,
                        new_config_version,
                    ),
                )
                rows = [dict(row) for row in cur.fetchall()]
            conn.rollback()
        matured = [
            row for row in rows
            if row.get("target_matured") == "true"
            and row.get("eligible_for_calibration")
            and row.get("target") is not None
        ]
        old_inv = [row for row in matured if row.get("old_verdict") == "INVESTIGATE"]
        new_inv = [row for row in matured if row.get("new_verdict") == "INVESTIGATE"]
        return {
            "target_definition": TARGET_DEFINITION,
            "paired_signals": len(rows),
            "matured_paired_signals": len(matured),
            "old_investigate_precision": sum(1 for row in old_inv if row["target"]) / len(old_inv) if old_inv else None,
            "new_investigate_precision": sum(1 for row in new_inv if row["target"]) / len(new_inv) if new_inv else None,
            "moved_down": sum(1 for row in rows if float(row["new_score"]) < float(row["old_score"])),
            "moved_up": sum(1 for row in rows if float(row["new_score"]) > float(row["old_score"])),
            "verdict_changes": sum(1 for row in rows if row["new_verdict"] != row["old_verdict"]),
            "rows": rows,
            "limitation": "Historical rescores are descriptive and may reflect model-design hindsight; they cannot establish out-of-sample superiority or profitable execution." if matured else "Point-in-time rescores exist, but eligible three-session outcomes have not matured yet.",
        }

    module.evaluation_report = evaluation_report
    module.original_vs_rescore_report = original_vs_rescore_report
    module._three_session_evaluation_installed = True
