from __future__ import annotations

import hashlib
import json
import math
from typing import Any

SCORING_MODEL_VERSION = "oversold_reversion_score_v2"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_19_v1"
CATALYST_PROMPT_VERSION = "catalyst_rules_prompt_v1"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v1"
CALIBRATION_MODEL_VERSION: str | None = None
MODEL_STATUS = "uncalibrated"
TARGET_DEFINITION = "hit_plus_5pct_within_6_weeks"

SCORING_CONFIG: dict[str, Any] = {
    "versions": {
        "scoring_model_version": SCORING_MODEL_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "catalyst_prompt_version": CATALYST_PROMPT_VERSION,
        "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
        "calibration_model_version": CALIBRATION_MODEL_VERSION,
    },
    "target": {"field": TARGET_DEFINITION, "threshold_pct": 5.0, "horizon_weeks": 6},
    "weights": {"setup": 0.25, "catalyst": 0.35, "resilience": 0.15, "confirmation": 0.25},
    "confidence": {"neutral_prior": 50.0},
    "damage": {
        "penalty_start": 25.0,
        "penalty_per_point": 0.20,
        "penalty_max": 15.0,
        "caps": [
            {"min": 0, "max": 29, "cap": 100},
            {"min": 30, "max": 49, "cap": 85},
            {"min": 50, "max": 69, "cap": 65},
            {"min": 70, "max": 84, "cap": 40},
            {"min": 85, "max": 100, "cap": 20},
        ],
    },
    "cause_unknown": {"catalyst_cap": 35, "final_cap": 60, "max_verdict": "WATCH"},
    "decision_thresholds": {"investigate": 75, "watch": 55},
    "calibration": {
        "minimum_matured_signals": 300,
        "minimum_positives": 60,
        "minimum_negatives": 60,
        "minimum_temporal_holdout": 100,
        "require_positive_brier_skill": True,
    },
    "sector_rubrics": {
        "biotechnology": ["trial phase", "primary/secondary endpoint", "statistical significance", "safety", "FDA/EMA", "pipeline concentration", "cash runway", "dilution"],
        "financials": ["liquidity", "capital adequacy", "deposits", "credit deterioration", "regulatory action", "funding stress"],
        "software": ["ARR/revenue guidance", "retention/churn", "customer concentration", "security breach", "competition", "margin trajectory"],
        "industrials": ["production disruption", "order book", "supply chain", "plant incident", "demand destruction"],
        "consumer": ["demand", "inventory", "margin pressure", "comparable sales", "promotional effects"],
    },
}

EXISTENTIAL_WORDS = (
    "bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern",
    "payment default", "debt default", "accounting fraud", "fraud investigation", "liquidation",
)
STRUCTURAL_WORDS = (
    "permanently close", "permanent closure", "terminates program", "terminated program",
    "discontinues program", "discontinued program", "patent invalid", "patent loss",
    "loses key customer", "lost key customer", "license terminated", "material weakness",
)
TRANSIENT_WORDS = (
    "temporary", "temporarily", "outage", "weather disruption", "shipment delay", "shipping delay",
    "supply disruption", "technical issue", "production delay", "operations resume", "resumes operations",
    "short-term disruption",
)
ANALYST_WORDS = ("downgrade", "upgrade", "price target", "analyst", "rating")
DILUTION_WORDS = ("public offering", "registered direct", "at-the-market", "dilution", "convertible", "warrant")
BIOTECH_FAILURE_WORDS = (
    "failed primary endpoint", "did not meet the primary endpoint", "missed primary endpoint",
    "primary endpoint was not met",
)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def infer_sector_hint(articles: list[dict[str, Any]]) -> str:
    text = " ".join(f"{a.get('headline') or ''} {a.get('summary') or ''}" for a in articles).lower()
    if any(w in text for w in ("clinical trial", "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii", "fda", "ema", "endpoint", "drug candidate")):
        return "biotechnology"
    if any(w in text for w in ("deposits", "capital ratio", "tier 1", "loan losses", "net interest margin", "bank liquidity", "funding stress")):
        return "financials"
    if any(w in text for w in ("arr", "annual recurring revenue", "net retention", "churn", "saas", "cybersecurity breach", "software subscription")):
        return "software"
    if any(w in text for w in ("plant", "production", "factory", "order book", "backlog", "supply chain")):
        return "industrials"
    if any(w in text for w in ("comparable sales", "same-store sales", "inventory", "retail", "consumer demand", "promotional")):
        return "consumer"
    return "unknown"


def setup_score(candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    snapshot = candidate.get("raw_snapshot") or {}
    previous = snapshot.get("prevDailyBar") or {}
    daily = snapshot.get("dailyBar") or {}
    drop = abs(min(_number(candidate.get("drop_pct")) or 0.0, 0.0))
    decline = clamp(45.0 + max(0.0, min(drop, 45.0) - 15.0) * (55.0 / 30.0))
    prev_close = _number(candidate.get("prev_close"))
    day_open = _number(daily.get("o"))
    gap_pct = ((day_open / prev_close) - 1.0) * 100.0 if prev_close and day_open else None
    gap_magnitude = abs(min(gap_pct or 0.0, 0.0)) if gap_pct is not None else None
    gap = 35.0 if gap_magnitude is None else clamp(40.0 + min(gap_magnitude, 20.0) * 3.0)
    prev_volume = _number(previous.get("v")) or _number(candidate.get("prev_volume"))
    day_volume = _number(daily.get("v"))
    relative_volume = day_volume / prev_volume if prev_volume and day_volume is not None and prev_volume > 0 else None
    rvol = 35.0 if relative_volume is None else clamp(35.0 + min(relative_volume, 4.0) * 16.25)
    dollar_volume = _number(candidate.get("prev_dollar_volume"))
    if dollar_volume is None:
        liquidity = 30.0
    elif dollar_volume >= 50_000_000:
        liquidity = 95.0
    elif dollar_volume >= 10_000_000:
        liquidity = 82.0
    elif dollar_volume >= 2_000_000:
        liquidity = 65.0
    elif dollar_volume >= 500_000:
        liquidity = 45.0
    else:
        liquidity = 15.0
    spread_pct = _number(candidate.get("spread_pct"))
    if spread_pct is None:
        spread = 35.0
    elif spread_pct <= 0.5:
        spread = 95.0
    elif spread_pct <= 1.0:
        spread = 85.0
    elif spread_pct <= 2.0:
        spread = 68.0
    elif spread_pct <= 5.0:
        spread = 38.0
    else:
        spread = 12.0
    score = 0.45 * decline + 0.15 * gap + 0.15 * rvol + 0.15 * liquidity + 0.10 * spread
    return round(clamp(score), 1), {
        "decline_dislocation": round(decline, 1), "gap_dislocation": round(gap, 1),
        "gap_pct": round(gap_pct, 3) if gap_pct is not None else None,
        "relative_volume": round(relative_volume, 3) if relative_volume is not None else None,
        "relative_volume_score": round(rvol, 1), "liquidity_score": round(liquidity, 1),
        "spread_quality_score": round(spread, 1),
        "weights": {"decline": 0.45, "gap": 0.15, "relative_volume": 0.15, "liquidity": 0.15, "spread": 0.10},
    }


def confirmation_score(candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    snapshot = candidate.get("raw_snapshot") or {}
    daily = snapshot.get("dailyBar") or {}
    previous = snapshot.get("prevDailyBar") or {}
    last_price = _number(candidate.get("last_price")) or _number(daily.get("c"))
    low, high, day_open = _number(daily.get("l")), _number(daily.get("h")), _number(daily.get("o"))
    range_position = clamp((last_price - low) / (high - low) * 100.0) if last_price is not None and low is not None and high is not None and high > low else 30.0
    if last_price is not None and day_open and day_open > 0:
        from_open_pct = ((last_price / day_open) - 1.0) * 100.0
        intraday_reversal = clamp(50.0 + from_open_pct * 8.0)
    else:
        from_open_pct, intraday_reversal = None, 30.0
    prev_volume = _number(previous.get("v")) or _number(candidate.get("prev_volume"))
    day_volume = _number(daily.get("v"))
    relative_volume = day_volume / prev_volume if prev_volume and day_volume is not None and prev_volume > 0 else None
    if relative_volume is None:
        volume_confirmation = 30.0
    elif relative_volume >= 2.0 and range_position >= 55:
        volume_confirmation = 85.0
    elif relative_volume >= 1.25 and range_position >= 45:
        volume_confirmation = 68.0
    elif range_position < 25:
        volume_confirmation = 20.0
    else:
        volume_confirmation = 45.0
    spread_pct = _number(candidate.get("spread_pct"))
    if spread_pct is None:
        spread_normalisation = 30.0
    elif spread_pct <= 0.5:
        spread_normalisation = 90.0
    elif spread_pct <= 1.0:
        spread_normalisation = 78.0
    elif spread_pct <= 2.0:
        spread_normalisation = 60.0
    elif spread_pct <= 5.0:
        spread_normalisation = 30.0
    else:
        spread_normalisation = 10.0
    score = 0.40 * range_position + 0.25 * intraday_reversal + 0.20 * volume_confirmation + 0.15 * spread_normalisation
    return round(clamp(score), 1), {
        "session_range_position": round(range_position, 1),
        "return_from_open_pct": round(from_open_pct, 3) if from_open_pct is not None else None,
        "intraday_reversal_score": round(intraday_reversal, 1),
        "volume_confirmation_score": round(volume_confirmation, 1),
        "spread_normalisation_score": round(spread_normalisation, 1),
        "relative_volume": round(relative_volume, 3) if relative_volume is not None else None,
        "weights": {"range_position": 0.40, "intraday_reversal": 0.25, "volume": 0.20, "spread": 0.15},
    }


def _article_text(articles: list[dict[str, Any]]) -> str:
    return " ".join(f"{a.get('headline') or ''} {a.get('summary') or ''}" for a in articles).lower()


def _evidence_items(articles: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return [{"id": a.get("id"), "headline": a.get("headline"), "source": a.get("source"), "published_at": a.get("created_at"), "url": a.get("url")} for a in articles[:limit]]


def structured_catalyst_analysis(candidate: dict[str, Any], articles: list[dict[str, Any]], catalyst_class: str, risk_flags: list[str]) -> dict[str, Any]:
    text = _article_text(articles)
    sector_hint = infer_sector_hint(articles)
    has_news = bool(articles)
    transient = any(w in text for w in TRANSIENT_WORDS)
    existential = any(w in text for w in EXISTENTIAL_WORDS)
    structural = any(w in text for w in STRUCTURAL_WORDS)
    analyst_only = "analyst_only" in risk_flags or (has_news and any(w in text for w in ANALYST_WORDS) and not structural and not existential)
    biotech_failure = sector_hint == "biotechnology" and any(w in text for w in BIOTECH_FAILURE_WORDS)
    severe_dilution = any(w in text for w in DILUTION_WORDS) and "going concern" in text
    base = {
        "A": (82, 78, 68, 18, 58, 60), "B": (85, 82, 68, 20, 65, 72),
        "C": (48, 52, 42, 52, 48, 60), "D": (18, 22, 18, 80, 32, 72),
        "E": (5, 8, 8, 95, 15, 85), "U": (30, 35, 28, 45, 42, 38),
    }.get(catalyst_class, (30, 35, 28, 45, 42, 38))
    reversibility, horizon_fit, overreaction, damage, resilience, evidence_conf = base
    if not has_news:
        reversibility, horizon_fit, overreaction, damage, resilience, evidence_conf = 20, 25, 20, 45, 42, 20
    if transient:
        reversibility, horizon_fit = max(reversibility, 85), max(horizon_fit, 82)
    if analyst_only:
        reversibility, damage = max(reversibility, 78), min(damage, 25)
    if "solvency" in risk_flags:
        damage, resilience = max(damage, 88), min(resilience, 20)
    if "dilution" in risk_flags:
        damage, resilience = max(damage, 58), min(resilience, 42)
    if "clinical_regulatory" in risk_flags and catalyst_class in {"C", "D", "E"}:
        damage = max(damage, 62)
    if biotech_failure:
        damage, reversibility, horizon_fit, resilience = max(damage, 92), min(reversibility, 10), min(horizon_fit, 15), min(resilience, 25)
    if severe_dilution:
        damage, resilience = max(damage, 90), min(resilience, 15)
    if len(articles) > 1:
        evidence_conf = min(90, evidence_conf + min(12, (len(articles) - 1) * 4))
    catalyst_type = "structural" if existential or biotech_failure or structural else "temporary" if transient or analyst_only or catalyst_class in {"A", "B"} else "mixed" if catalyst_class == "C" else "unknown"
    hard_veto_reason = "existential_or_solvency_event" if existential else "core_pivotal_trial_failure" if biotech_failure else "catastrophic_financing_risk" if severe_dilution else None
    supporting, contradictory = [], []
    if transient:
        supporting.append("Point-in-time news contains explicit temporary/disruption language.")
    if analyst_only:
        supporting.append("The retained catalyst appears dominated by analyst/sentiment action rather than a new operating failure.")
    if structural or existential or biotech_failure:
        contradictory.append("Point-in-time evidence contains structural, existential, or core-asset failure language.")
    if "dilution" in risk_flags:
        contradictory.append("Financing/dilution risk is present in the retained evidence.")
    if not articles:
        contradictory.append("No company-specific news evidence was retained at the signal cutoff; causal attribution is weak.")
    catalyst_score = clamp(0.50 * reversibility + 0.25 * horizon_fit + 0.25 * overreaction)
    cause_verified = has_news and catalyst_class != "U"
    if not cause_verified:
        catalyst_score = min(catalyst_score, float(SCORING_CONFIG["cause_unknown"]["catalyst_cap"]))
    analyst_articles = [a for a in articles if any(w in f"{a.get('headline') or ''} {a.get('summary') or ''}".lower() for w in ANALYST_WORDS)]
    return {
        "primary_catalyst": articles[0].get("headline") if articles else "No independently retained company-specific news at the signal cutoff",
        "catalyst_category": catalyst_class, "catalyst_type": catalyst_type,
        "reversibility_score": round(reversibility, 1), "six_week_horizon_fit": round(horizon_fit, 1),
        "market_overreaction_score": round(overreaction, 1), "fundamental_damage_risk": round(clamp(damage), 1),
        "fundamental_resilience_score": round(clamp(resilience), 1), "evidence_confidence": round(clamp(evidence_conf), 1),
        "supporting_evidence": supporting, "contradictory_evidence": contradictory,
        "red_flags": sorted(set(risk_flags)), "source_claims": _evidence_items(articles),
        "sector_assessment": {"sector_hint": sector_hint, "rubric": SCORING_CONFIG["sector_rubrics"].get(sector_hint, []), "note": "Sector is inferred from point-in-time event text when authoritative sector metadata is unavailable."},
        "analyst_reaction": {"coverage_available": bool(analyst_articles), "post_event_updates": _evidence_items(analyst_articles, 3), "direction": "neutral" if analyst_articles else "unavailable"},
        "analysis_summary": f"Rules-based point-in-time catalyst analysis ({catalyst_class}); no backend LLM is configured in the current app.",
        "cause_verified": cause_verified, "hard_veto": hard_veto_reason is not None, "hard_veto_reason": hard_veto_reason,
        "analysis_method": "rules_v2_no_llm", "catalyst_score": round(catalyst_score, 1),
    }


def market_data_completeness(candidate: dict[str, Any]) -> tuple[float, list[str]]:
    snapshot = candidate.get("raw_snapshot") or {}
    checks = {
        "prev_close": candidate.get("prev_close"), "last_price": candidate.get("last_price"),
        "spread_pct": candidate.get("spread_pct"), "prev_dollar_volume": candidate.get("prev_dollar_volume"),
        "prev_daily_bar": snapshot.get("prevDailyBar"), "daily_bar": snapshot.get("dailyBar"),
        "latest_trade_ts": candidate.get("latest_trade_ts"),
    }
    missing = [k for k, v in checks.items() if v in (None, {}, [])]
    return round((len(checks) - len(missing)) / len(checks) * 100.0, 1), missing


def damage_cap(damage_risk: float) -> float:
    d = clamp(damage_risk)
    for band in SCORING_CONFIG["damage"]["caps"]:
        if band["min"] <= d <= band["max"]:
            return float(band["cap"])
    return 20.0


def final_score(*, setup: float, catalyst: float, resilience: float, confirmation: float, confidence: float, damage_risk: float, cause_verified: bool, hard_veto: bool = False, hard_veto_reason: str | None = None) -> dict[str, Any]:
    w = SCORING_CONFIG["weights"]
    core = setup * w["setup"] + catalyst * w["catalyst"] + resilience * w["resilience"] + confirmation * w["confirmation"]
    neutral = float(SCORING_CONFIG["confidence"]["neutral_prior"])
    confidence_adjusted = neutral + ((core - neutral) * clamp(confidence) / 100.0)
    dcfg = SCORING_CONFIG["damage"]
    penalty = min(float(dcfg["penalty_max"]), max(0.0, clamp(damage_risk) - float(dcfg["penalty_start"])) * float(dcfg["penalty_per_point"]))
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
    resilience = float(analysis["fundamental_resilience_score"])
    damage = float(analysis["fundamental_damage_risk"])
    completeness, missing_market = market_data_completeness(candidate)
    confidence = clamp(0.65 * float(analysis["evidence_confidence"]) + 0.35 * completeness)
    missing_inputs = list(missing_market)
    if not articles:
        missing_inputs.append("company_specific_news")
    result = final_score(setup=setup, catalyst=catalyst, resilience=resilience, confirmation=confirmation, confidence=confidence, damage_risk=damage, cause_verified=bool(analysis["cause_verified"]), hard_veto=bool(analysis["hard_veto"]), hard_veto_reason=analysis.get("hard_veto_reason"))
    if result["verdict"] == "INVESTIGATE":
        explanation = "Dislocation and catalyst reversibility are strong enough to investigate, with permanent-damage risk contained by current point-in-time evidence."
    elif result["verdict"] == "WATCH":
        explanation = "The setup has reversion potential, but evidence, confirmation, or catalyst certainty is not yet strong enough for investigate-grade status."
    else:
        explanation = "Permanent-damage risk, weak evidence, or inadequate reversion economics dominate the oversold setup."
    return {
        "setup_score": setup, "catalyst_score": round(catalyst, 1), "resilience_score": round(resilience, 1),
        "confirmation_score": confirmation, "damage_risk": round(damage, 1), "evidence_confidence": round(confidence, 1),
        "model_status": MODEL_STATUS, "scoring_model_version": SCORING_MODEL_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION, "catalyst_prompt_version": CATALYST_PROMPT_VERSION,
        "catalyst_schema_version": CATALYST_SCHEMA_VERSION, "calibration_model_version": CALIBRATION_MODEL_VERSION,
        "target_definition": TARGET_DEFINITION, "catalyst_analysis": analysis, "missing_inputs": sorted(set(missing_inputs)),
        "explanation": explanation,
        "calculation_trace": {"formula": "core=.25*setup+.35*catalyst+.15*resilience+.25*confirmation; confidence=50+(core-50)*confidence/100; damage penalty/caps then apply", "setup": setup_trace, "confirmation": confirmation_trace, "market_data_completeness": completeness, "final": result, "config": SCORING_CONFIG},
        **result,
    }


def evidence_snapshot_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def public_scoring_contract() -> dict[str, Any]:
    return {"model_status": MODEL_STATUS, "target_definition": TARGET_DEFINITION, "versions": SCORING_CONFIG["versions"], "weights": SCORING_CONFIG["weights"], "confidence": SCORING_CONFIG["confidence"], "damage": SCORING_CONFIG["damage"], "cause_unknown": SCORING_CONFIG["cause_unknown"], "decision_thresholds": SCORING_CONFIG["decision_thresholds"], "calibration": SCORING_CONFIG["calibration"]}
