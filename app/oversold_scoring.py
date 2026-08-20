from __future__ import annotations

import hashlib
import json
from typing import Any

from app.oversold_score_common import (
    SCORING_MODEL_VERSION, SCORING_CONFIG_VERSION, CATALYST_PROMPT_VERSION, CATALYST_SCHEMA_VERSION,
    CALIBRATION_MODEL_VERSION, MODEL_STATUS, TARGET_DEFINITION, SCORING_CONFIG, clamp,
)
from app.oversold_score_technical import _history_bars, setup_score, confirmation_score
from app.oversold_score_fundamental import resilience_score
from app.oversold_score_catalyst import classify_news_for_candidate, structured_catalyst_analysis


def market_data_completeness(candidate: dict[str, Any]) -> tuple[float, list[str]]:
    snapshot = candidate.get("raw_snapshot") or {}
    history_count = len(_history_bars(candidate))
    checks = {
        "prev_close": candidate.get("prev_close"), "last_price": candidate.get("last_price"),
        "spread_pct": candidate.get("spread_pct"), "prev_dollar_volume": candidate.get("prev_dollar_volume"),
        "prev_daily_bar": snapshot.get("prevDailyBar"), "daily_bar": snapshot.get("dailyBar"),
        "latest_trade_ts": candidate.get("latest_trade_ts"),
        "historical_daily_bars": history_count if history_count >= int(SCORING_CONFIG["setup"]["minimum_history_bars"]) else None,
    }
    missing = [key for key, value in checks.items() if value in (None, {}, [], 0)]
    return round((len(checks) - len(missing)) / len(checks) * 100.0, 1), missing


def fundamental_completeness(context: dict[str, Any]) -> float:
    fields = ("market_cap", "cash_and_equivalents", "current_liabilities", "total_debt", "total_equity", "operating_cash_flow_quarterly")
    present = sum(1 for field in fields if context.get(field) is not None)
    if not context.get("available"):
        return 25.0
    return clamp(40.0 + (present / len(fields)) * 60.0)


def damage_cap(damage_risk: float) -> float:
    damage = clamp(damage_risk)
    for band in SCORING_CONFIG["damage"]["caps"]:
        if band["min"] <= damage <= band["max"]:
            return float(band["cap"])
    return 20.0


def final_score(*, setup: float, catalyst: float, resilience: float, confirmation: float, confidence: float, damage_risk: float, cause_verified: bool, hard_veto: bool = False, hard_veto_reason: str | None = None) -> dict[str, Any]:
    weights = SCORING_CONFIG["weights"]
    core = setup * weights["setup"] + catalyst * weights["catalyst"] + resilience * weights["resilience"] + confirmation * weights["confirmation"]
    neutral = float(SCORING_CONFIG["confidence"]["neutral_prior"])
    confidence_adjusted = neutral + ((core - neutral) * clamp(confidence) / 100.0)
    damage_cfg = SCORING_CONFIG["damage"]
    penalty = min(float(damage_cfg["penalty_max"]), max(0.0, clamp(damage_risk) - float(damage_cfg["penalty_start"])) * float(damage_cfg["penalty_per_point"]))
    pre_cap = clamp(confidence_adjusted - penalty)
    cap = damage_cap(damage_risk)
    applied_caps: list[dict[str, Any]] = [{"type": "damage", "cap": cap}]
    if not cause_verified:
        unknown_cap = float(SCORING_CONFIG["cause_unknown"]["final_cap"])
        cap = min(cap, unknown_cap)
        applied_caps.append({"type": "cause_unknown", "cap": unknown_cap})
    if hard_veto:
        cap = 20.0
        applied_caps.append({"type": "hard_veto", "cap": 20.0, "reason": hard_veto_reason})
    score = round(min(pre_cap, cap), 1)
    if hard_veto or score < SCORING_CONFIG["decision_thresholds"]["watch"]:
        verdict = "PASS"
    elif score >= SCORING_CONFIG["decision_thresholds"]["investigate"] and cause_verified:
        verdict = "INVESTIGATE"
    else:
        verdict = "WATCH"
    return {"core_score": round(core, 2), "confidence_adjusted_score": round(confidence_adjusted, 2), "damage_penalty": round(penalty, 2), "damage_cap": round(damage_cap(damage_risk), 1), "pre_cap_score": round(pre_cap, 2), "final_score": score, "verdict": verdict, "hard_veto": hard_veto, "hard_veto_reason": hard_veto_reason, "caps_applied": applied_caps}


def score_candidate(candidate: dict[str, Any], articles: list[dict[str, Any]], catalyst_class: str, risk_flags: list[str]) -> dict[str, Any]:
    setup, setup_trace = setup_score(candidate)
    confirmation, confirmation_trace = confirmation_score(candidate)
    analysis = structured_catalyst_analysis(candidate, articles, catalyst_class, risk_flags)
    catalyst = float(analysis["catalyst_score"])
    resilience, fundamental_trace, fundamental_missing = resilience_score(candidate, risk_flags)
    damage = float(analysis["fundamental_damage_risk"])
    completeness, missing_market = market_data_completeness(candidate)
    fund_completeness = fundamental_completeness(fundamental_trace)
    confidence = clamp(0.55 * float(analysis["evidence_confidence"]) + 0.35 * completeness + 0.10 * fund_completeness)
    missing_inputs = list(missing_market) + list(fundamental_missing)
    if not analysis.get("news_relevance", {}).get("direct_event_count"):
        missing_inputs.append("verified_ticker_specific_catalyst")
    if not articles:
        missing_inputs.append("company_specific_news")
    result = final_score(setup=setup, catalyst=catalyst, resilience=resilience, confirmation=confirmation, confidence=confidence, damage_risk=damage, cause_verified=bool(analysis["cause_verified"]), hard_veto=bool(analysis["hard_veto"]), hard_veto_reason=analysis.get("hard_veto_reason"))
    event_category = str(analysis.get("event_category") or "unknown")
    if result["verdict"] == "INVESTIGATE":
        explanation = f"Investigate-grade reversion setup: {event_category.replace('_', ' ')} appears reversible relative to the dislocation, with Damage Risk contained."
    elif result["verdict"] == "WATCH":
        explanation = f"Potential reversion remains, but {event_category.replace('_', ' ')} evidence, confirmation, or confidence is not yet investigate-grade."
    else:
        explanation = f"Pass: {event_category.replace('_', ' ')} damage/uncertainty or weak baseline reversion economics dominate the one-day sell-off."
    return {
        "setup_score": setup, "catalyst_score": round(catalyst, 1), "resilience_score": round(resilience, 1),
        "confirmation_score": confirmation, "damage_risk": round(damage, 1), "evidence_confidence": round(confidence, 1),
        "model_status": MODEL_STATUS, "scoring_model_version": SCORING_MODEL_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION, "catalyst_prompt_version": CATALYST_PROMPT_VERSION,
        "catalyst_schema_version": CATALYST_SCHEMA_VERSION, "calibration_model_version": CALIBRATION_MODEL_VERSION,
        "target_definition": TARGET_DEFINITION, "catalyst_analysis": analysis, "missing_inputs": sorted(set(missing_inputs)),
        "explanation": explanation,
        "calculation_trace": {"formula": "core=.25*setup+.35*catalyst+.15*resilience+.25*confirmation; confidence=50+(core-50)*confidence/100; damage penalty/caps then apply", "setup": setup_trace, "confirmation": confirmation_trace, "fundamentals": fundamental_trace, "fundamental_completeness": round(fund_completeness, 1), "market_data_completeness": completeness, "news_relevance": analysis.get("news_relevance"), "final": result, "config": SCORING_CONFIG},
        **result,
    }


def evidence_snapshot_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def public_scoring_contract() -> dict[str, Any]:
    return {"model_status": MODEL_STATUS, "target_definition": TARGET_DEFINITION, "versions": SCORING_CONFIG["versions"], "weights": SCORING_CONFIG["weights"], "confidence": SCORING_CONFIG["confidence"], "damage": SCORING_CONFIG["damage"], "cause_unknown": SCORING_CONFIG["cause_unknown"], "decision_thresholds": SCORING_CONFIG["decision_thresholds"], "calibration": SCORING_CONFIG["calibration"], "setup": SCORING_CONFIG["setup"]}
