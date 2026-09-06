from __future__ import annotations

import json
import logging
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg.types.json import Jsonb

from app.db import connection
from app.oversold import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_MIN_DROP_PCT,
    LONDON,
    MAX_CANDIDATE_LIMIT,
    _scan_detail as canonical_scan_detail,
    execute_scan as execute_canonical_scan,
)

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PUBLIC_MANUAL_COOLDOWN_SECONDS = 300
STALE_SCAN_MINUTES = 30
CHATGPT_LAUNCH_MAX_CHARS = 4_000
V2_ADAPTER_VERSION = "oversold-v2-canonical-adapter-3"

# The canonical scanner already excludes most non-operating instruments. This
# final presentation filter removes shell/SPAC-like rows that can still be
# technically tradable common equity but do not fit a fundamental-reversion
# workflow.
NON_OPERATING_RESULT_RE = re.compile(
    r"\b(etf|etn|exchange[- ]traded|warrants?|rights?|preferred|units?|"
    r"blank check|special purpose acquisition|acquisition (?:corp|corporation|company)|"
    r"capital investment corp(?:oration)?|closed[- ]end fund)\b",
    re.IGNORECASE,
)
NON_COMMON_SYMBOL_RE = re.compile(r"(?:\.(?:U|WS?|W|R|RT)|-(?:U|WS?|W|R|RT))$", re.IGNORECASE)

FUNDAMENTAL_KEYS = (
    "revenue_yoy",
    "net_margin",
    "operating_margin",
    "gross_margin",
    "cash_to_assets",
    "current_ratio",
    "liabilities_to_assets",
    "equity_to_assets",
    "debt_to_assets",
    "cash_runway_months",
    "diluted_shares_yoy",
    "free_cash_flow",
    "operating_cash_flow",
    "cash_and_equivalents",
    "market_cap",
    "price_to_sales",
)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _humanise(value: Any, fallback: str = "Unknown") -> str:
    text = str(value or "").strip().replace("_", " ").replace("-", " ")
    return text.title() if text else fallback


def _truncate(value: Any, length: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= length else text[: max(1, length - 1)].rstrip() + "…"


def _is_researchable_equity(row: dict[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").upper().strip()
    name = str(row.get("name") or "")
    if not symbol or NON_COMMON_SYMBOL_RE.search(symbol):
        return False
    return not bool(NON_OPERATING_RESULT_RE.search(name))


def _analysis(row: dict[str, Any]) -> dict[str, Any]:
    return _dict(row.get("catalyst_analysis"))


def _calculation_trace(row: dict[str, Any]) -> dict[str, Any]:
    return _dict(row.get("calculation_trace"))


def _fundamental_payload(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = _analysis(row)
    trace = _dict(analysis.get("fundamental_trace"))
    raw = _dict(trace.get("raw_metrics"))

    technical_inputs = _dict(row.get("technical_inputs"))
    technical_fundamentals = _dict(technical_inputs.get("fundamentals"))
    if not raw:
        raw = technical_fundamentals

    selected = {key: raw.get(key) for key in FUNDAMENTAL_KEYS if raw.get(key) is not None}
    metadata = {
        "available": _boolean(trace.get("available")) or bool(selected),
        "source": trace.get("source") or technical_fundamentals.get("source"),
        "form": trace.get("form") or technical_fundamentals.get("form"),
        "available_from": trace.get("available_from") or technical_fundamentals.get("available_from"),
        "report_period_end": trace.get("report_period_end") or technical_fundamentals.get("report_period_end"),
        "age_calendar_days": trace.get("age_calendar_days", technical_fundamentals.get("age_calendar_days")),
        "metric_coverage_count": trace.get("metric_coverage_count", technical_fundamentals.get("metric_coverage_count")),
        "data_quality_score": analysis.get("fundamental_data_quality_score"),
        "evidence_confidence": analysis.get("fundamental_evidence_confidence"),
        "evidence_state": analysis.get("fundamental_evidence_state"),
    }
    return selected, metadata


def _fundamental_quality(row: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    metrics, metadata = _fundamental_payload(row)
    resilience = _number(row.get("resilience_score"))
    damage = _number(row.get("damage_risk"))
    analysis = _analysis(row)
    dilution = _dict(analysis.get("dilution_analysis"))
    hard_veto = _boolean(row.get("hard_veto")) or _boolean(analysis.get("hard_veto"))
    capital_distress = dilution.get("classification") == "capital_distress"

    score = resilience if resilience is not None else 0.0
    if hard_veto or capital_distress or (damage is not None and damage >= 85):
        label = "Fragile"
    elif resilience is None or not metadata.get("available"):
        label = "Unknown"
    elif score >= 75:
        label = "Strong"
    elif score >= 60:
        label = "Good"
    elif score >= 45:
        label = "Mixed"
    elif score >= 30:
        label = "Weak"
    else:
        label = "Fragile"

    data_quality = _number(metadata.get("data_quality_score"))
    evidence_state = str(metadata.get("evidence_state") or "").upper()
    integrity = _dict(_dict(analysis.get("evidence_integrity")).get("fundamentals"))
    if integrity.get("status") == "REJECTED":
        prefix, label = "Rejected evidence", "Unknown"
    elif metadata.get("available") and evidence_state == "VERIFIED_PRIMARY" and data_quality is not None and data_quality >= 60:
        prefix = "Primary sourced"
    elif metadata.get("available"):
        prefix = "Partial"
    else:
        prefix = "Limited"
    return f"{prefix} · {label}", metrics, metadata


def _price_context(row: dict[str, Any]) -> dict[str, Any]:
    analysis = _analysis(row)
    context = _dict(analysis.get("price_session_context"))
    if not context:
        context = _dict(_dict(row.get("raw_snapshot")).get("price_session_context"))
    return context


def _project_candidate(row: dict[str, Any]) -> dict[str, Any]:
    analysis = _analysis(row)
    trace = _calculation_trace(row)
    final_trace = _dict(trace.get("final"))
    robustness = _dict(analysis.get("robustness_assessment"))
    price_context = _price_context(row)
    quality, fundamentals, fundamental_metadata = _fundamental_quality(row)

    score = _number(row.get("reversion_score"))
    if score is None:
        score = _number(row.get("final_score"))
    model_missing = score is None
    score = round(score if score is not None else 0.0, 1)

    verdict = str(row.get("model_verdict") or row.get("verdict") or "PASS").upper()
    if model_missing:
        verdict = "PASS"
    initial_view = verdict.title()

    cause_verified = _boolean(analysis.get("cause_verified"))
    cause_status = str(analysis.get("cause_verification_status") or ("VERIFIED" if cause_verified else "UNVERIFIED"))
    event_profile = str(analysis.get("event_profile") or analysis.get("event_taxonomy_primary") or row.get("catalyst_class") or "unknown")
    primary_catalyst = str(analysis.get("primary_catalyst") or row.get("catalyst_summary") or "No independently verified catalyst")

    regular_move = _number(price_context.get("regular_session_move_pct"))
    latest_move = _number(price_context.get("current_move_pct"))
    stored_move = _number(row.get("drop_pct"))
    price_session = str(price_context.get("price_session") or "unknown")
    display_move = regular_move if price_session != "regular" and regular_move is not None else stored_move
    if display_move is None:
        display_move = latest_move

    failed_gates = _list(analysis.get("failed_eligibility_gates"))
    if not failed_gates:
        failed_gates = _list(final_trace.get("failed_eligibility_gates"))

    source_claims = [
        {
            "headline": claim.get("headline"),
            "source": claim.get("source") or claim.get("source_authority"),
            "published_at": claim.get("published_at") or claim.get("available_at"),
            "url": claim.get("url") or claim.get("source_url"),
        }
        for claim in _list(analysis.get("source_claims"))[:5]
        if isinstance(claim, dict)
    ]

    overreaction = _number(analysis.get("overreaction_quality_score"))
    if overreaction is None:
        overreaction = _number(analysis.get("market_overreaction_score"))

    evidence_cutoff = row.get("evidence_cutoff") or _dict(row.get("evidence_snapshot")).get("evidence_cutoff")
    model_status = str(row.get("model_status") or "uncalibrated")
    probability = _number(row.get("calibrated_probability"))
    if model_status.lower() != "calibrated" or not row.get("calibration_model_version") or probability is None or not 0 <= probability <= 1:
        probability = None
    evidence_integrity = _dict(analysis.get("evidence_integrity"))
    missing_inputs = [str(value) for value in _list(row.get("missing_inputs"))]
    execution_friction = _number(analysis.get("estimated_round_trip_friction_pct"))
    opportunity_gaps = ["No evidence-backed price target or invalidation level stored; net reward/risk is unestablished."]
    if execution_friction is None:
        opportunity_gaps.append("Round-trip execution friction is unavailable.")
    if not evidence_cutoff:
        opportunity_gaps.append("Original evidence cutoff is unavailable.")

    return {
        "id": row.get("id"),
        "rank": row.get("rank"),
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "exchange": row.get("exchange"),
        "prev_close": row.get("prev_close"),
        "last_price": row.get("last_price"),
        "drop_pct": round(display_move, 3) if display_move is not None else None,
        "latest_move_pct": round(latest_move, 3) if latest_move is not None else stored_move,
        "regular_session_move_pct": regular_move,
        "extended_hours_move_pct": _number(price_context.get("extended_hours_move_pct")),
        "price_session": price_session,
        "extended_hours_only": _boolean(price_context.get("extended_hours_only")),
        "prev_dollar_volume": row.get("prev_dollar_volume"),
        "spread_pct": row.get("spread_pct"),
        "oversold_score": score,
        "initial_view": initial_view,
        "model_status": model_status,
        "calibrated_probability": probability,
        "calibration_model_version": row.get("calibration_model_version"),
        "scoring_model_version": row.get("scoring_model_version"),
        "scoring_config_version": row.get("scoring_config_version"),
        "target_definition": row.get("target_definition"),
        "setup_score": _number(row.get("setup_score")),
        "dislocation_score": overreaction if overreaction is not None else _number(row.get("setup_score")),
        "fundamental_survivability": _number(row.get("resilience_score")),
        "catalyst_reversibility": _number(analysis.get("reversibility_score")),
        "confirmation_score": _number(row.get("confirmation_score")),
        "three_session_fit_score": _number(analysis.get("three_session_fit_score")),
        "impairment_risk": _number(row.get("damage_risk")),
        "tail_risk_score": _number(analysis.get("tail_risk_score")),
        "confidence": _number(row.get("evidence_confidence")),
        "fundamental_quality": quality,
        "fundamentals": fundamentals,
        "fundamental_metadata": fundamental_metadata,
        "cause_verified": cause_verified,
        "cause_status": cause_status,
        "catalyst_class": _humanise(event_profile),
        "event_profile": event_profile,
        "catalyst_type": analysis.get("catalyst_type"),
        "catalyst_summary": primary_catalyst,
        "risk_flags": sorted({str(flag) for flag in _list(analysis.get("red_flags")) + _list(row.get("risk_flags"))}),
        "hard_veto": _boolean(row.get("hard_veto")) or _boolean(analysis.get("hard_veto")),
        "hard_veto_reason": row.get("hard_veto_reason") or analysis.get("hard_veto_reason"),
        "failed_gates": [str(value) for value in failed_gates],
        "execution_friction_pct": execution_friction,
        "net_risk_reward_status": "not_established",
        "opportunity_gaps": opportunity_gaps,
        "missing_inputs": missing_inputs,
        "evidence_integrity": evidence_integrity,
        "score_semantics": _dict(analysis.get("score_semantics")),
        "source_dependency_risk": _number(analysis.get("source_dependency_risk")),
        "source_claims": source_claims,
        "headline_count": row.get("headline_count"),
        "headlines": _list(row.get("headlines"))[:10],
        "evidence_cutoff": evidence_cutoff,
        "signal_timestamp": row.get("signal_timestamp"),
        "signal_price": row.get("signal_price"),
        "latest_trade_ts": row.get("latest_trade_ts"),
        "evidence_snapshot_id": row.get("evidence_snapshot_id"),
        "snapshot_hash": row.get("snapshot_hash"),
        "model_explanation": row.get("explanation"),
        "model_missing": model_missing,
        "adapter_version": V2_ADAPTER_VERSION,
        "robustness_summary": {
            "ensemble_median": _number(_dict(robustness.get("ensemble")).get("ensemble_median")),
            "weight_stability_score": _number(analysis.get("weight_stability_score")),
            "event_alignment_score": _number(analysis.get("event_alignment_score")),
            "fundamental_data_quality_score": _number(analysis.get("fundamental_data_quality_score")),
        },
    }


def _project_scan(detail: dict[str, Any], *, limit: int | None = None) -> dict[str, Any]:
    scan = dict(detail.get("scan") or {})
    raw_candidates = [dict(row) for row in detail.get("candidates") or []]
    filtered = [row for row in raw_candidates if _is_researchable_equity(row)]
    candidates = [_project_candidate(row) for row in filtered]

    verdict_order = {"Investigate": 3, "Watch": 2, "Pass": 1, "Fail": 0}
    candidates.sort(
        key=lambda row: (
            -verdict_order.get(str(row.get("initial_view") or "Pass"), 0),
            -float(row.get("oversold_score") or 0.0),
            -float(row.get("confidence") or 0.0),
            float(row.get("drop_pct") or 0.0),
        )
    )
    if limit is not None:
        candidates = candidates[: max(0, int(limit))]
    for rank, candidate in enumerate(candidates, 1):
        candidate["rank"] = rank

    metadata = _dict(scan.get("metadata"))
    scan["canonical_candidate_count"] = int(scan.get("candidate_count") or len(raw_candidates))
    scan["candidate_count"] = len(candidates)
    scan["excluded_non_operating_count"] = len(raw_candidates) - len(filtered)
    scan["evidence_cutoff"] = metadata.get("evidence_cutoff")
    scan["model_status"] = candidates[0].get("model_status") if candidates else metadata.get("model_status")
    scan["scoring_model_version"] = candidates[0].get("scoring_model_version") if candidates else metadata.get("scoring_model")
    scan["target_definition"] = candidates[0].get("target_definition") if candidates else metadata.get("target_definition")
    scan["selection_method"] = metadata.get("selection_method")
    scan["adapter_version"] = V2_ADAPTER_VERSION
    return {"scan": scan or None, "candidates": candidates}


def _latest_scan_id() -> UUID | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM or_scans ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
        conn.rollback()
    return row["id"] if row else None


def _load_projected_scan(scan_id: UUID, *, limit: int | None = None) -> dict[str, Any]:
    return _project_scan(canonical_scan_detail(scan_id), limit=limit)


def _create_or_reuse_scan(min_drop_pct: float, candidate_limit: int) -> tuple[UUID, str, bool]:
    cutoff = datetime.now(UTC) - timedelta(seconds=PUBLIC_MANUAL_COOLDOWN_SECONDS)
    stale_cutoff = datetime.now(UTC) - timedelta(minutes=STALE_SCAN_MINUTES)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(hashtext('oversold_v2_manual_scan')) AS locked")
            locked = bool(cur.fetchone()["locked"])
            if not locked:
                cur.execute("SELECT id,status FROM or_scans WHERE status='running' ORDER BY started_at DESC LIMIT 1")
                active = cur.fetchone()
                conn.rollback()
                if active:
                    return active["id"], active["status"], True
                raise HTTPException(409, "Another Oversold scan is being started. Refresh shortly.")

            cur.execute(
                """
                UPDATE or_scans
                SET status='failed',completed_at=now(),error=COALESCE(error,'Marked stale by Oversold V2 recovery.')
                WHERE status='running' AND started_at < %s
                """,
                (stale_cutoff,),
            )
            cur.execute(
                """
                SELECT id,status FROM or_scans
                WHERE started_at >= %s AND status IN ('running','completed')
                ORDER BY started_at DESC LIMIT 1
                """,
                (cutoff,),
            )
            recent = cur.fetchone()
            if recent:
                conn.commit()
                return recent["id"], recent["status"], True

            cur.execute(
                """
                INSERT INTO or_scans(trigger_source,scan_date,min_drop_pct,candidate_limit,status,metadata)
                VALUES ('manual',%s,%s,%s,'running',%s)
                RETURNING id
                """,
                (
                    datetime.now(LONDON).date(),
                    min_drop_pct,
                    candidate_limit,
                    Jsonb({"requested_by": "oversold_v2", "adapter_version": V2_ADAPTER_VERSION}),
                ),
            )
            scan_id = cur.fetchone()["id"]
        conn.commit()
    return scan_id, "running", False


def _selected_fundamentals(candidate: dict[str, Any]) -> dict[str, Any]:
    fundamentals = _dict(candidate.get("fundamentals"))
    return {key: fundamentals.get(key) for key in FUNDAMENTAL_KEYS if fundamentals.get(key) is not None}


def _source_summary(candidate: dict[str, Any], *, limit: int = 4) -> list[str]:
    output: list[str] = []
    for claim in _list(candidate.get("source_claims"))[:limit]:
        if not isinstance(claim, dict):
            continue
        output.append(
            f"{claim.get('published_at') or 'time unknown'} | {claim.get('source') or 'source unknown'} | "
            f"{_truncate(claim.get('headline'), 220)} | {claim.get('url') or 'URL not retained'}"
        )
    return output


def _build_chatgpt_prompt(detail: dict[str, Any], *, compact: bool = False) -> str:
    candidates = list(detail.get("candidates") or [])[:10]
    scan = _dict(detail.get("scan"))
    lines = [
        "Audit these Oversold Reversion candidates as ORIGINAL, point-in-time signals. Do not use hindsight.",
        "Use only evidence available on or before each stored evidence cutoff; cite primary sources and publication times. If a cutoff is missing, point-in-time verification is unavailable. Independently challenge the app; the priority score and every component (including survivability, reversibility, damage and confidence) are uncalibrated indices, not probabilities or buy recommendations.",
        "For every stock determine: why it fell; causal-evidence strength; temporary versus structural damage; financial survivability; whether the price move exceeds likely permanent damage; a reversion mechanism within the stored target horizon; contradictory evidence; execution/liquidity risk; another-leg-down risk; and whether a credible, asymmetric profit opportunity exists. A filed 8-K or analyst reaction alone does not prove the economic cause, temporary damage or mispricing.",
        "Separate an oversold reading from an investable setup. State an evidence-supported target, thesis invalidation, time limit and upside/downside after spread, slippage and fees where supportable; otherwise mark net reward/risk unestablished and name the missing evidence. Do not invent return probabilities, price levels or a profitable backtest.",
        "Return an independent best-to-worst ranking with INVESTIGATE, WATCH or PASS, and explicitly explain every material disagreement with the app.",
        f"Scanner model: {scan.get('scoring_model_version') or 'unknown'} | model status: {scan.get('model_status') or 'unknown'} | target: {scan.get('target_definition') or 'not retained'} | evidence cutoff: {scan.get('evidence_cutoff')}",
        "",
    ]

    for candidate in candidates:
        fundamentals = _selected_fundamentals(candidate)
        risk_flags = ", ".join(candidate.get("risk_flags") or []) or "none"
        failed_gates = ", ".join(candidate.get("failed_gates") or []) or "none"
        session = candidate.get("price_session") or "unknown"
        source_lines = _source_summary(candidate, limit=2 if compact else 5)
        if compact:
            lines.extend(
                [
                    (
                        f"{candidate['rank']}. {candidate['symbol']} — move {candidate.get('drop_pct')}% regular / "
                        f"{candidate.get('latest_move_pct')}% latest ({session}); robust score {candidate.get('oversold_score')}/100; "
                        f"app view {candidate.get('initial_view')}; cause {candidate.get('cause_status')} / {candidate.get('catalyst_class')}; "
                        f"financial-strength index {candidate.get('fundamental_survivability')}, reversibility index {candidate.get('catalyst_reversibility')}, "
                        f"damage {candidate.get('impairment_risk')}, confidence {candidate.get('confidence')}; "
                        f"fundamentals {candidate.get('fundamental_quality')}; risks {risk_flags}; failed gates {failed_gates}."
                    ),
                    f"Catalyst: {_truncate(candidate.get('catalyst_summary'), 240)}",
                    f"Key fundamentals: {json.dumps(fundamentals, default=str, separators=(',', ':'))}",
                    ("Evidence: " + " || ".join(source_lines)) if source_lines else "Evidence: no retained primary/source claims.",
                    f"Evidence cutoff: {candidate.get('evidence_cutoff')} | original signal: {candidate.get('signal_timestamp')} | model: {candidate.get('scoring_model_version')}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"{candidate['rank']}. {candidate['symbol']} ({candidate.get('name') or candidate['symbol']})",
                    f"Price: regular-session move {candidate.get('drop_pct')}%; latest move {candidate.get('latest_move_pct')}%; session {session}; spread {candidate.get('spread_pct')}%; prior dollar volume {candidate.get('prev_dollar_volume')}",
                    f"App: robust score {candidate.get('oversold_score')}/100; view {candidate.get('initial_view')}; model {candidate.get('scoring_model_version')} ({candidate.get('model_status')})",
                    f"Components: setup {candidate.get('setup_score')}; overreaction/dislocation {candidate.get('dislocation_score')}; survivability {candidate.get('fundamental_survivability')}; reversibility {candidate.get('catalyst_reversibility')}; confirmation {candidate.get('confirmation_score')}; three-session fit {candidate.get('three_session_fit_score')}; damage {candidate.get('impairment_risk')}; tail risk {candidate.get('tail_risk_score')}; evidence confidence {candidate.get('confidence')}",
                    f"Cause: {candidate.get('cause_status')} | profile {candidate.get('catalyst_class')} | type {candidate.get('catalyst_type')} | {_truncate(candidate.get('catalyst_summary'), 500)}",
                    f"Fundamental assessment: {candidate.get('fundamental_quality')} | metadata {json.dumps(candidate.get('fundamental_metadata') or {}, default=str, separators=(',', ':'))}",
                    f"Fundamentals: {json.dumps(fundamentals, default=str, separators=(',', ':'))}",
                    f"Risk flags: {risk_flags} | hard veto: {candidate.get('hard_veto')} ({candidate.get('hard_veto_reason') or 'none'}) | failed eligibility gates: {failed_gates}",
                    f"Execution/provenance: estimated round-trip friction {candidate.get('execution_friction_pct')}%; source dependency risk {candidate.get('source_dependency_risk')}; robust summary {json.dumps(candidate.get('robustness_summary') or {}, default=str, separators=(',', ':'))}",
                    f"Opportunity gaps: {'; '.join(candidate.get('opportunity_gaps') or [])} | missing inputs: {', '.join(candidate.get('missing_inputs') or [])}",
                    f"Evidence integrity: {json.dumps(candidate.get('evidence_integrity') or {}, default=str, separators=(',', ':'))}",
                    f"Original signal: {candidate.get('signal_timestamp')} | signal price: {candidate.get('signal_price')} | evidence cutoff: {candidate.get('evidence_cutoff')}",
                    "Evidence claims: " + (" || ".join(source_lines) if source_lines else "none retained"),
                    "",
                ]
            )

    lines.extend(
        [
            "Finish with: the strongest candidate; the strongest reason to avoid it; any statistically oversold stock that should clearly be rejected; the single most important missing fact for each non-PASS candidate; and the evidence that must be checked before risking capital.",
            "Do not describe profit, a rebound or any forecast as certain. State uncertainty plainly.",
        ]
    )
    return "\n".join(lines)


def _build_launch_prompt(detail: dict[str, Any]) -> str:
    prompt = _build_chatgpt_prompt(detail, compact=True)
    if len(prompt) <= CHATGPT_LAUNCH_MAX_CHARS:
        return prompt

    candidates = list(detail.get("candidates") or [])[:10]
    scan = _dict(detail.get("scan"))
    lines = [
        "Audit original Oversold Reversion signals without hindsight. Use only evidence published by each cutoff and cite it. All scores, survival and reversal components are uncalibrated indices, not probabilities. Rank INVESTIGATE/WATCH/PASS by cause, lasting damage, financial strength, reversion mechanism and net reward/risk. A filing or analyst reaction alone does not establish temporary damage. If price target/invalidation/cost evidence is missing, say net reward/risk is unestablished.",
        f"Original model: {_truncate(scan.get('scoring_model_version') or 'not retained', 70)}; target: {_truncate(scan.get('target_definition') or 'not retained', 80)}.",
    ]
    # Allocate a bounded row budget before adding catalyst text so a long early
    # headline cannot silently remove the tenth signal or its evidence cutoff.
    row_budget = max(0, (CHATGPT_LAUNCH_MAX_CHARS - len("\n".join(lines)) - 2 * len(candidates)) // max(1, len(candidates)))
    for candidate in candidates:
        core = (
            f"{candidate['rank']}. {candidate['symbol']}: move {candidate.get('drop_pct')}%, score {candidate.get('oversold_score')}, "
            f"{candidate.get('initial_view')}, cause {_truncate(candidate.get('cause_status'), 28)}/{_truncate(candidate.get('catalyst_class'), 35)}, "
            f"strength {candidate.get('fundamental_survivability')}, reversal {candidate.get('catalyst_reversibility')}, damage {candidate.get('impairment_risk')}, "
            f"friction {candidate.get('execution_friction_pct')}%, cutoff {candidate.get('evidence_cutoff')}"
        )
        remaining = row_budget - len(core) - len(". Catalyst: ")
        if remaining > 5:
            core += f". Catalyst: {_truncate(candidate.get('catalyst_summary'), remaining)}"
        lines.append(core)
    return "\n".join(lines)


@router.get("/oversold-v2", response_class=HTMLResponse)
def oversold_v2_page(request: Request):
    return templates.TemplateResponse("oversold_v2.html", {"request": request})


@router.get("/api/oversold-v2/latest")
def latest_scan() -> dict[str, Any]:
    scan_id = _latest_scan_id()
    return {"scan": None, "candidates": []} if scan_id is None else _load_projected_scan(scan_id)


@router.get("/api/oversold-v2/scans/{scan_id}")
def scan_detail(scan_id: UUID) -> dict[str, Any]:
    return _load_projected_scan(scan_id)


@router.post("/api/oversold-v2/run", status_code=202)
async def run_scan(
    background_tasks: BackgroundTasks,
    background: bool = Query(True),
    min_drop_pct: float = Query(DEFAULT_MIN_DROP_PCT, ge=5, le=90),
    candidate_limit: int = Query(DEFAULT_CANDIDATE_LIMIT, ge=1, le=MAX_CANDIDATE_LIMIT),
) -> dict[str, Any]:
    scan_id, status, duplicate = _create_or_reuse_scan(min_drop_pct, candidate_limit)
    if duplicate:
        return {
            "status": status,
            "scan_id": scan_id,
            "duplicate": True,
            "cooldown_seconds": PUBLIC_MANUAL_COOLDOWN_SECONDS,
        }
    if background:
        background_tasks.add_task(
            execute_canonical_scan,
            scan_id,
            min_drop_pct=min_drop_pct,
            candidate_limit=candidate_limit,
        )
        return {"status": "running", "scan_id": scan_id, "duplicate": False}
    await execute_canonical_scan(scan_id, min_drop_pct=min_drop_pct, candidate_limit=candidate_limit)
    return _load_projected_scan(scan_id)


@router.get("/api/oversold-v2/chatgpt-prompt")
def chatgpt_prompt(scan_id: UUID | None = None) -> dict[str, Any]:
    if scan_id is None:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM or_scans WHERE status='completed' ORDER BY started_at DESC LIMIT 1")
                row = cur.fetchone()
            conn.rollback()
        if not row:
            raise HTTPException(404, "No completed Oversold scan is available")
        scan_id = row["id"]

    detail = _load_projected_scan(scan_id, limit=10)
    if not detail.get("scan") or detail["scan"].get("status") != "completed":
        raise HTTPException(409, "The selected scan is not complete")
    if not detail.get("candidates"):
        raise HTTPException(404, "The completed scan has no researchable candidates")

    full_prompt = _build_chatgpt_prompt(detail)
    launch_prompt = _build_launch_prompt(detail)
    return {
        "scan_id": scan_id,
        "candidate_count": min(10, len(detail.get("candidates") or [])),
        "prompt": full_prompt,
        "launch_prompt": launch_prompt,
        "prompt_length": len(full_prompt),
        "launch_prompt_length": len(launch_prompt),
        "launch_prompt_limit": CHATGPT_LAUNCH_MAX_CHARS,
    }
