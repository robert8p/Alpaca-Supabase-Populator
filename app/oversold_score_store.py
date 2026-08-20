from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.oversold_calibration import active_calibration_from_cursor, calibrated_probability
from app.oversold_scoring import evidence_snapshot_hash


def apply_active_calibration(score: dict[str, Any], calibration: dict[str, Any] | None) -> dict[str, Any]:
    """Attach the latest already-passed calibration without changing the raw score."""
    probability = calibrated_probability(float(score["final_score"]), calibration)
    if probability is None:
        return score
    score["model_status"] = "calibrated"
    score["calibration_model_version"] = calibration.get("calibration_model_version") if calibration else None
    score["calibrated_probability"] = probability
    trace = score.setdefault("calculation_trace", {})
    trace["calibration"] = {
        "calibration_model_version": score["calibration_model_version"],
        "raw_reversion_score": score["final_score"],
        "calibrated_probability": probability,
        "mapping": "regularized_logistic_raw_score",
    }
    return score


def persist_original_score(
    cur: Any,
    *,
    candidate_id: int,
    scan_id: UUID,
    item: dict[str, Any],
    score: dict[str, Any],
    evidence_cutoff: Any,
) -> tuple[int, int]:
    active_calibration = active_calibration_from_cursor(cur)
    apply_active_calibration(score, active_calibration)

    analysis = score.get("catalyst_analysis") or {}
    sector_hint = ((analysis.get("sector_assessment") or {}).get("sector_hint") or "unknown")
    news_items = item.get("headlines") or []
    technical_inputs = {
        "setup": (score.get("calculation_trace") or {}).get("setup") or {},
        "confirmation": (score.get("calculation_trace") or {}).get("confirmation") or {},
        "market_data_completeness": (score.get("calculation_trace") or {}).get("market_data_completeness"),
    }
    market_data = {
        "prev_close": item.get("prev_close"), "last_price": item.get("last_price"), "drop_pct": item.get("drop_pct"),
        "prev_volume": item.get("prev_volume"), "prev_dollar_volume": item.get("prev_dollar_volume"),
        "bid": item.get("bid"), "ask": item.get("ask"), "spread_pct": item.get("spread_pct"),
        "latest_trade_ts": item.get("latest_trade_ts"), "raw_snapshot": item.get("raw_snapshot") or {},
    }
    source_quality = {
        "missing_inputs": score.get("missing_inputs") or [], "evidence_confidence": score.get("evidence_confidence"),
        "cause_verified": analysis.get("cause_verified"), "analysis_method": analysis.get("analysis_method"),
    }
    hash_payload = {
        "candidate_id": candidate_id, "scan_id": str(scan_id), "symbol": item.get("symbol"),
        "signal_timestamp": evidence_cutoff, "evidence_cutoff": evidence_cutoff,
        "signal_price": item.get("last_price"), "market_data": market_data,
        "technical_inputs": technical_inputs, "news_items": news_items, "sector_hint": sector_hint,
    }
    snapshot_hash = evidence_snapshot_hash(hash_payload)
    analyst_events = (analysis.get("analyst_reaction") or {}).get("post_event_updates") or []

    cur.execute(
        """
        INSERT INTO or_evidence_snapshots(
            candidate_id,scan_id,symbol,company_name,signal_timestamp,evidence_cutoff,signal_price,
            sector_hint,market_data,technical_inputs,news_items,filing_refs,analyst_events,
            source_quality,snapshot_hash,snapshot_kind
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'[]'::jsonb,%s,%s,%s,'original')
        ON CONFLICT (candidate_id,snapshot_kind,evidence_cutoff) DO NOTHING
        RETURNING id
        """,
        (
            candidate_id, scan_id, item.get("symbol"), item.get("name"), evidence_cutoff, evidence_cutoff,
            item.get("last_price"), sector_hint, Jsonb(market_data), Jsonb(technical_inputs), Jsonb(news_items),
            Jsonb(analyst_events), Jsonb(source_quality), snapshot_hash,
        ),
    )
    row = cur.fetchone()
    if row:
        evidence_snapshot_id = int(row["id"])
    else:
        cur.execute("SELECT id FROM or_evidence_snapshots WHERE candidate_id=%s AND snapshot_kind='original' AND evidence_cutoff=%s", (candidate_id, evidence_cutoff))
        evidence_snapshot_id = int(cur.fetchone()["id"])

    cur.execute(
        """
        INSERT INTO or_model_runs(
            candidate_id,evidence_snapshot_id,run_kind,scoring_model_version,scoring_config_version,
            catalyst_prompt_version,catalyst_schema_version,calibration_model_version,model_status,target_definition,
            setup_score,catalyst_score,resilience_score,confirmation_score,damage_risk,evidence_confidence,
            core_score,confidence_adjusted_score,damage_penalty,damage_cap,final_score,calibrated_probability,
            verdict,hard_veto,hard_veto_reason,missing_inputs,catalyst_analysis,calculation_trace,explanation
        ) VALUES (
            %s,%s,'original',%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON CONFLICT (candidate_id,evidence_snapshot_id,run_kind,scoring_model_version,scoring_config_version) DO NOTHING
        RETURNING id
        """,
        (
            candidate_id, evidence_snapshot_id, score["scoring_model_version"], score["scoring_config_version"],
            score["catalyst_prompt_version"], score["catalyst_schema_version"], score.get("calibration_model_version"),
            score["model_status"], score["target_definition"], score["setup_score"], score["catalyst_score"],
            score["resilience_score"], score["confirmation_score"], score["damage_risk"], score["evidence_confidence"],
            score["core_score"], score["confidence_adjusted_score"], score["damage_penalty"], score["damage_cap"],
            score["final_score"], score.get("calibrated_probability"), score["verdict"], score["hard_veto"], score.get("hard_veto_reason"),
            Jsonb(score.get("missing_inputs") or []), Jsonb(score.get("catalyst_analysis") or {}),
            Jsonb(score.get("calculation_trace") or {}), score.get("explanation"),
        ),
    )
    row = cur.fetchone()
    if row:
        model_run_id = int(row["id"])
    else:
        cur.execute(
            "SELECT id FROM or_model_runs WHERE candidate_id=%s AND evidence_snapshot_id=%s AND run_kind='original' AND scoring_model_version=%s AND scoring_config_version=%s",
            (candidate_id, evidence_snapshot_id, score["scoring_model_version"], score["scoring_config_version"]),
        )
        model_run_id = int(cur.fetchone()["id"])

    cur.execute(
        """
        INSERT INTO or_signal_outcomes(
            candidate_id,evidence_snapshot_id,model_run_id,symbol,signal_timestamp,signal_price,horizon_deadline,
            corporate_action_status,trading_status,outcome_resolution,eligible_for_calibration,status,metadata
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,'unchecked','normal','1Day',false,'pending',%s)
        ON CONFLICT (candidate_id) DO NOTHING
        """,
        (
            candidate_id, evidence_snapshot_id, model_run_id, item.get("symbol"), evidence_cutoff,
            item.get("last_price"), evidence_cutoff + timedelta(weeks=6),
            Jsonb({
                "target": "plus_5pct_within_6_weeks",
                "source": "alpaca_sip",
                "price_adjustment": "raw",
                "calibration_exclusion": "pending_corporate_action_review",
            }),
        ),
    )
    return evidence_snapshot_id, model_run_id
