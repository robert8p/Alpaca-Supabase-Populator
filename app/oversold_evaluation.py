from __future__ import annotations

"""Point-in-time evaluation utilities for Oversold Reversion.

Historical comparisons are append-only: v3.2 rescores the immutable Evidence
Snapshot used by the original signal, never today's data and never the original
model row. Snapshots whose ORIGINAL run is already v3.2 are deliberately skipped;
there is no analytical value in storing a duplicate v3.2 rescore of a v3.2 signal.
"""

from collections import defaultdict
import math
from typing import Any

from psycopg.types.json import Jsonb

from app.db import connection
from app.oversold_scoring import (
    CATALYST_PROMPT_VERSION,
    CATALYST_SCHEMA_VERSION,
    SCORING_CONFIG_VERSION,
    SCORING_MODEL_VERSION,
    TARGET_DEFINITION,
    score_candidate,
)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _auc(rows: list[dict[str, Any]], score_key: str = "score") -> float | None:
    ranked = sorted(rows, key=lambda row: float(row[score_key]))
    positives = sum(1 for row in ranked if row["target"])
    negatives = len(ranked) - positives
    if not positives or not negatives:
        return None
    rank_sum = 0.0
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and float(ranked[end][score_key]) == float(ranked[index][score_key]):
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(1 for row in ranked[index:end] if row["target"])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _pr_auc(rows: list[dict[str, Any]], score_key: str = "score") -> float | None:
    positives = sum(1 for row in rows if row["target"])
    if not positives:
        return None
    ordered = sorted(rows, key=lambda row: float(row[score_key]), reverse=True)
    tp = fp = 0
    previous_recall = 0.0
    area = 0.0
    for row in ordered:
        if row["target"]:
            tp += 1
        else:
            fp += 1
        recall = tp / positives
        precision = tp / (tp + fp)
        area += precision * max(0.0, recall - previous_recall)
        previous_recall = recall
    return area


def _bucket_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    output: dict[str, dict[str, Any]] = {}
    for label, values in sorted(grouped.items()):
        hits = sum(1 for row in values if row["target"])
        plus10 = sum(1 for row in values if (_num(row.get("mfe_6w")) or -999.0) >= 10.0)
        output[label] = {
            "n": len(values),
            "plus_5_hit_rate": hits / len(values) if values else None,
            "plus_10_hit_rate": plus10 / len(values) if values else None,
            "mean_mfe_6w": _mean([v for row in values if (v := _num(row.get("mfe_6w"))) is not None]),
            "mean_mae_6w": _mean([v for row in values if (v := _num(row.get("mae_6w"))) is not None]),
        }
    return output


def evaluation_report(
    *,
    model_version: str = SCORING_MODEL_VERSION,
    config_version: str = SCORING_CONFIG_VERSION,
    run_kind: str = "original",
) -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mr.id,mr.candidate_id,mr.final_score AS score,mr.verdict,mr.calibrated_probability,
                       mr.catalyst_analysis,mr.evidence_confidence,mr.damage_risk,
                       so.hit_plus_5pct_within_6_weeks AS target,so.mfe_6w,so.mae_6w,so.return_6w,
                       so.trading_days_to_plus_5,so.hours_to_plus_5
                FROM or_model_runs mr
                JOIN or_signal_outcomes so ON so.candidate_id=mr.candidate_id
                WHERE mr.run_kind=%s
                  AND mr.scoring_model_version=%s AND mr.scoring_config_version=%s
                  AND so.status='matured' AND so.eligible_for_calibration=true
                  AND so.hit_plus_5pct_within_6_weeks IS NOT NULL
                ORDER BY mr.id
                """,
                (run_kind, model_version, config_version),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()

    for row in rows:
        analysis = row.get("catalyst_analysis") or {}
        row["event_profile"] = analysis.get("event_taxonomy_primary") or analysis.get("event_profile") or "unknown"
        row["cause_status"] = analysis.get("cause_verification_status") or ("VERIFIED" if analysis.get("cause_verified") else "UNVERIFIED")
        spike = analysis.get("spike_adjustment") or {}
        financing = analysis.get("dilution_analysis") or {}
        row["post_spike_bucket"] = "post_spike_unwind" if spike.get("post_spike_unwind") else "no_post_spike_unwind"
        row["financing_bucket"] = financing.get("classification") or ("financing_unspecified" if "financing" in str(analysis.get("event_profile") or "") else "not_financing")

    hits = sum(1 for row in rows if row["target"])
    plus10 = sum(1 for row in rows if (_num(row.get("mfe_6w")) or -999.0) >= 10.0)
    investigate = [row for row in rows if row.get("verdict") == "INVESTIGATE"]
    watch = [row for row in rows if row.get("verdict") == "WATCH"]
    passed = [row for row in rows if row.get("verdict") == "PASS"]
    calibrated = [row for row in rows if _num(row.get("calibrated_probability")) is not None]
    brier = _mean([
        (float(row["calibrated_probability"]) - (1.0 if row["target"] else 0.0)) ** 2
        for row in calibrated
    ]) if calibrated else None
    return {
        "scoring_model_version": model_version,
        "scoring_config_version": config_version,
        "run_kind": run_kind,
        "sample_size": len(rows),
        "plus_5_hit_rate": hits / len(rows) if rows else None,
        "plus_10_hit_rate": plus10 / len(rows) if rows else None,
        "mean_mfe_6w": _mean([v for row in rows if (v := _num(row.get("mfe_6w"))) is not None]),
        "mean_mae_6w": _mean([v for row in rows if (v := _num(row.get("mae_6w"))) is not None]),
        "mean_close_6w": _mean([v for row in rows if (v := _num(row.get("return_6w"))) is not None]),
        "roc_auc_raw_score": _auc(rows),
        "pr_auc_raw_score": _pr_auc(rows),
        "brier_score_if_calibrated": brier,
        "verdict_performance": _bucket_metrics(rows, "verdict"),
        "event_type_performance": _bucket_metrics(rows, "event_profile"),
        "cause_verification_performance": _bucket_metrics(rows, "cause_status"),
        "post_spike_performance": _bucket_metrics(rows, "post_spike_bucket"),
        "financing_performance": _bucket_metrics(rows, "financing_bucket"),
        "investigate_precision": (sum(1 for row in investigate if row["target"]) / len(investigate)) if investigate else None,
        "watch_hit_rate": (sum(1 for row in watch if row["target"]) / len(watch)) if watch else None,
        "pass_hit_rate": (sum(1 for row in passed if row["target"]) / len(passed)) if passed else None,
        "limitation": None if rows else "No matured calibration-eligible six-week outcomes exist for this model/config yet.",
    }


def _reconstruct_candidate(row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str, list[str]]:
    market = row.get("market_data") or {}
    technical = row.get("technical_inputs") or {}
    candidate = dict(market)
    candidate.update({
        "symbol": row.get("symbol"),
        "name": row.get("company_name"),
        "evidence_cutoff": row.get("evidence_cutoff"),
        "latest_trade_ts": market.get("latest_trade_ts") or row.get("signal_timestamp"),
        "last_price": market.get("last_price") or row.get("signal_price"),
        "history_bars": market.get("history_bars") or [],
        "benchmark_context": market.get("benchmark_context") or {},
        "fundamentals": technical.get("fundamentals") or None,
    })
    articles = [dict(item) for item in (row.get("news_items") or []) if isinstance(item, dict)]
    return candidate, articles, str(row.get("catalyst_class") or "U"), list(row.get("risk_flags") or [])


def rescore_historical_snapshots(*, limit: int = 500) -> dict[str, int]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT es.*,c.catalyst_class,c.risk_flags
                FROM or_evidence_snapshots es
                JOIN or_candidates c ON c.id=es.candidate_id
                JOIN or_model_runs original
                  ON original.evidence_snapshot_id=es.id AND original.candidate_id=es.candidate_id
                 AND original.run_kind='original'
                WHERE es.snapshot_kind='original'
                  AND NOT (original.scoring_model_version=%s AND original.scoring_config_version=%s)
                  AND NOT EXISTS (
                    SELECT 1 FROM or_model_runs mr
                    WHERE mr.candidate_id=es.candidate_id AND mr.evidence_snapshot_id=es.id
                      AND mr.run_kind='rescore' AND mr.scoring_model_version=%s AND mr.scoring_config_version=%s
                  )
                ORDER BY es.signal_timestamp,es.id LIMIT %s
                """,
                (SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION, SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION, limit),
            )
            snapshots = [dict(row) for row in cur.fetchall()]
        conn.rollback()

    inserted = errors = 0
    for snapshot in snapshots:
        try:
            candidate, articles, catalyst_class, risk_flags = _reconstruct_candidate(snapshot)
            score = score_candidate(candidate, articles, catalyst_class, risk_flags)
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO or_model_runs(
                            candidate_id,evidence_snapshot_id,run_kind,scoring_model_version,scoring_config_version,
                            catalyst_prompt_version,catalyst_schema_version,calibration_model_version,model_status,target_definition,
                            setup_score,catalyst_score,resilience_score,confirmation_score,damage_risk,evidence_confidence,
                            core_score,confidence_adjusted_score,damage_penalty,damage_cap,final_score,calibrated_probability,
                            verdict,hard_veto,hard_veto_reason,missing_inputs,catalyst_analysis,calculation_trace,explanation
                        ) VALUES (
                            %s,%s,'rescore',%s,%s,%s,%s,NULL,'uncalibrated',%s,
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s
                        )
                        ON CONFLICT (candidate_id,evidence_snapshot_id,run_kind,scoring_model_version,scoring_config_version) DO NOTHING
                        """,
                        (
                            snapshot["candidate_id"], snapshot["id"], SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION,
                            CATALYST_PROMPT_VERSION, CATALYST_SCHEMA_VERSION, TARGET_DEFINITION,
                            score["setup_score"], score["catalyst_score"], score["resilience_score"], score["confirmation_score"],
                            score["damage_risk"], score["evidence_confidence"], score["core_score"], score["confidence_adjusted_score"],
                            score["damage_penalty"], score["damage_cap"], score["final_score"], score["verdict"], score["hard_veto"],
                            score.get("hard_veto_reason"), Jsonb(score.get("missing_inputs") or []), Jsonb(score.get("catalyst_analysis") or {}),
                            Jsonb(score.get("calculation_trace") or {}), score.get("explanation"),
                        ),
                    )
                    inserted += max(0, cur.rowcount or 0)
                conn.commit()
        except Exception:
            errors += 1
    return {"eligible_snapshots": len(snapshots), "inserted": inserted, "errors": errors}


def original_vs_rescore_report(*, new_model_version: str = SCORING_MODEL_VERSION, new_config_version: str = SCORING_CONFIG_VERSION) -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT old.candidate_id,old.scoring_model_version AS old_version,old.final_score AS old_score,old.verdict AS old_verdict,
                       new.final_score AS new_score,new.verdict AS new_verdict,new.catalyst_analysis AS new_analysis,
                       so.status AS outcome_status,so.hit_plus_5pct_within_6_weeks AS target,so.mfe_6w,so.mae_6w
                FROM or_model_runs old
                JOIN or_model_runs new
                  ON new.candidate_id=old.candidate_id AND new.evidence_snapshot_id=old.evidence_snapshot_id
                LEFT JOIN or_signal_outcomes so ON so.candidate_id=old.candidate_id
                WHERE old.run_kind='original' AND new.run_kind='rescore'
                  AND new.scoring_model_version=%s AND new.scoring_config_version=%s
                  AND NOT (old.scoring_model_version=%s AND old.scoring_config_version=%s)
                ORDER BY old.candidate_id
                """,
                (new_model_version, new_config_version, new_model_version, new_config_version),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()

    matured = [row for row in rows if row.get("outcome_status") == "matured" and row.get("target") is not None]
    old_inv = [row for row in matured if row.get("old_verdict") == "INVESTIGATE"]
    new_inv = [row for row in matured if row.get("new_verdict") == "INVESTIGATE"]
    return {
        "paired_signals": len(rows),
        "matured_paired_signals": len(matured),
        "old_investigate_precision": (sum(1 for row in old_inv if row["target"]) / len(old_inv)) if old_inv else None,
        "new_investigate_precision": (sum(1 for row in new_inv if row["target"]) / len(new_inv)) if new_inv else None,
        "moved_down": sum(1 for row in rows if float(row["new_score"]) < float(row["old_score"])),
        "moved_up": sum(1 for row in rows if float(row["new_score"]) > float(row["old_score"])),
        "verdict_changes": sum(1 for row in rows if row["new_verdict"] != row["old_verdict"]),
        "rows": rows,
        "limitation": None if matured else "Point-in-time rescores exist, but six-week outcomes have not matured yet; no performance-superiority claim is valid yet.",
    }
