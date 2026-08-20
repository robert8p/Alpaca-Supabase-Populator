from __future__ import annotations

"""Oversold Reversion Score v3.3: purpose-aligned opportunity quality.

v3.2 remains reproducible.  This additive layer reinterprets the same point-in-time
evidence for the actual three-session thesis: a candidate must be mispriced,
survivable, timely and adequately evidenced.  Confidence can only reduce an
opportunity score; it can never pull a weak setup upward toward a neutral prior.
"""

import math
from copy import deepcopy
from typing import Any

from app.oversold_sec_fundamentals import runtime_enrichment_wrapper

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_3"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v5"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3_3"
PURPOSE_STATEMENT = (
    "Prioritise liquid US sell-offs where verified price damage appears materially "
    "greater than justified economic damage, the business can survive, and a reversion "
    "within three trading sessions offers favourable asymmetric risk."
)

CRITICAL_FINANCIAL_PROFILES = {
    "financing_benign",
    "material_dilution",
    "capital_distress",
    "quantified_earnings_deterioration",
    "earnings_miss",
    "guidance_reset",
    "guidance_reduction",
    "listing_risk",
    "failed_catalyst",
    "binary_thesis_failure",
}
STRUCTURAL_PROFILES = {
    "capital_distress",
    "binary_thesis_failure",
    "failed_catalyst",
    "fraud_or_governance",
    "structural_impairment",
    "existential_or_solvency",
    "primary_endpoint_failure",
}
THREE_SESSION_FIT: dict[str, float] = {
    "temporary_disruption_resolved": 95.0,
    "temporary_operational_disruption": 88.0,
    "temporary_operational_issue": 88.0,
    "broad_sector_risk_off": 86.0,
    "guidance_reaffirmed": 82.0,
    "analyst_only": 72.0,
    "analyst_action": 68.0,
    "secondary_endpoint_miss_primary_intact": 62.0,
    "financing_benign": 58.0,
    "management_departure": 48.0,
    "earnings_miss": 46.0,
    "quantified_earnings_deterioration": 42.0,
    "guidance_reset": 35.0,
    "guidance_reduction": 35.0,
    "legal_or_regulatory": 32.0,
    "regulatory_issue": 30.0,
    "litigation": 30.0,
    "security_breach": 30.0,
    "control_transaction": 25.0,
    "post_spike_unwind": 20.0,
    "material_dilution": 20.0,
    "listing_risk": 18.0,
    "capital_distress": 8.0,
    "binary_thesis_failure": 5.0,
    "failed_catalyst": 5.0,
    "fraud_or_governance": 5.0,
    "unknown": 30.0,
}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _geometric(values: dict[str, float], weights: dict[str, float]) -> float:
    total = sum(float(weights.get(key, 0.0)) for key in values)
    if total <= 0:
        return 0.0
    log_sum = 0.0
    for key, value in values.items():
        weight = float(weights.get(key, 0.0)) / total
        log_sum += weight * math.log(max(1.0, _clamp(value)))
    return math.exp(log_sum)


def _event_profile(analysis: dict[str, Any]) -> str:
    return str(
        analysis.get("event_taxonomy_primary")
        or analysis.get("event_profile")
        or analysis.get("catalyst_type")
        or "unknown"
    )


def _three_session_fit(analysis: dict[str, Any], damage: float) -> float:
    profile = _event_profile(analysis)
    fit = THREE_SESSION_FIT.get(profile)
    if fit is None:
        legacy = _num(analysis.get("six_week_horizon_fit"))
        fit = 0.55 * (legacy if legacy is not None else 45.0) + 0.45 * max(5.0, 100.0 - damage)
        fit = min(fit, 55.0)
    metrics = analysis.get("event_metrics") if isinstance(analysis.get("event_metrics"), dict) else {}
    deterioration = _num(metrics.get("deterioration_severity"))
    if profile == "quantified_earnings_deterioration" and deterioration is not None:
        fit -= min(22.0, deterioration * 0.22)
    return _clamp(fit)


def _fundamental_trace(analysis: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    trace = analysis.get("fundamental_trace") if isinstance(analysis.get("fundamental_trace"), dict) else {}
    raw = trace.get("raw_metrics") if isinstance(trace.get("raw_metrics"), dict) else {}
    return trace, raw


def _survivability(
    base: float,
    analysis: dict[str, Any],
    damage: float,
) -> tuple[float, list[str], bool]:
    score = _clamp(base)
    reasons: list[str] = []
    trace, raw = _fundamental_trace(analysis)
    fundamentals_available = bool(trace.get("available"))
    profile = _event_profile(analysis)
    financing = analysis.get("dilution_analysis") if isinstance(analysis.get("dilution_analysis"), dict) else {}
    signals = analysis.get("event_signals") if isinstance(analysis.get("event_signals"), dict) else {}

    runway = _num(raw.get("cash_runway_months"))
    current_ratio = _num(raw.get("current_ratio"))
    debt_to_assets = _num(raw.get("debt_to_assets"))
    cash_to_assets = _num(raw.get("cash_to_assets"))
    liabilities_to_assets = _num(raw.get("liabilities_to_assets"))
    diluted_shares_yoy = _num(raw.get("diluted_shares_yoy"))

    if runway is not None:
        if runway < 3:
            score = min(score, 12.0)
            reasons.append("cash_runway_under_3_months")
        elif runway < 6:
            score = min(score, 25.0)
            reasons.append("cash_runway_under_6_months")
        elif runway < 12:
            score = min(score, 45.0)
            reasons.append("cash_runway_under_12_months")
        elif runway >= 24:
            score += 8.0
            reasons.append("cash_runway_at_least_24_months")
    if current_ratio is not None:
        if current_ratio < 0.7:
            score -= 15.0
            reasons.append("current_ratio_below_0_7")
        elif current_ratio >= 1.5:
            score += 6.0
            reasons.append("current_ratio_at_least_1_5")
    if debt_to_assets is not None:
        if debt_to_assets >= 0.75:
            score -= 18.0
            reasons.append("debt_to_assets_at_least_75pct")
        elif debt_to_assets >= 0.50:
            score -= 8.0
            reasons.append("debt_to_assets_at_least_50pct")
    if cash_to_assets is not None:
        if cash_to_assets < 0.03:
            score -= 12.0
            reasons.append("cash_to_assets_below_3pct")
        elif cash_to_assets >= 0.20:
            score += 6.0
            reasons.append("cash_to_assets_at_least_20pct")
    if liabilities_to_assets is not None and liabilities_to_assets >= 1.0:
        score = min(score, 15.0)
        reasons.append("liabilities_exceed_assets")
    if diluted_shares_yoy is not None:
        if diluted_shares_yoy >= 0.50:
            score = min(score, 30.0)
            reasons.append("diluted_shares_up_at_least_50pct")
        elif diluted_shares_yoy >= 0.20:
            score -= 12.0
            reasons.append("diluted_shares_up_at_least_20pct")

    financing_class = str(financing.get("classification") or "not_applicable")
    if financing_class == "capital_distress":
        score = min(score, 10.0)
        reasons.append("capital_distress")
    elif financing_class == "material_dilution":
        score = min(score, 38.0)
        reasons.append("material_dilution")
    elif financing_class == "financing_benign":
        score = min(score, 68.0)
        reasons.append("financing_requires_survival_evidence")

    if signals.get("existential_or_solvency"):
        score = min(score, 8.0)
        reasons.append("existential_or_solvency_signal")
    if signals.get("primary_endpoint_failure"):
        score = min(score, 20.0)
        reasons.append("pivotal_or_primary_failure")
    if damage >= 80:
        score = min(score, 18.0)
    elif damage >= 65:
        score = min(score, 45.0)

    critical = (
        profile in CRITICAL_FINANCIAL_PROFILES
        or financing_class != "not_applicable"
        or damage >= 55
        or bool(signals.get("existential_or_solvency"))
    )
    if critical and not fundamentals_available:
        score = min(score, 45.0)
        reasons.append("critical_financial_evidence_unavailable")
    return _clamp(score), reasons, critical


def _overreaction_quality(
    setup: float,
    reversibility: float,
    damage: float,
    analysis: dict[str, Any],
) -> tuple[float, list[str]]:
    trace = analysis.get("spike_adjustment") if isinstance(analysis.get("spike_adjustment"), dict) else {}
    dislocation = setup
    value = 50.0 + 0.55 * (dislocation - 50.0) + 0.35 * (reversibility - 50.0) - 0.80 * (damage - 50.0)
    reasons: list[str] = []
    cause_status = str(analysis.get("cause_verification_status") or "UNVERIFIED")
    if cause_status == "UNVERIFIED":
        value = min(value, 45.0)
        reasons.append("cause_unverified")
    elif cause_status == "CONFLICTING":
        value = min(value, 40.0)
        reasons.append("cause_conflicting")
    if trace.get("post_spike_unwind") and float(trace.get("penalty") or 0.0) >= 12.0:
        value = min(value, 30.0)
        reasons.append("selloff_dominated_by_post_spike_normalisation")
    return _clamp(value), reasons


def _tail_risk(
    damage: float,
    analysis: dict[str, Any],
    survivability: float,
    hard_veto: bool,
) -> tuple[float, list[str]]:
    score = _clamp(damage)
    reasons: list[str] = []
    financing = analysis.get("dilution_analysis") if isinstance(analysis.get("dilution_analysis"), dict) else {}
    severity = _num(financing.get("severity_score"))
    if severity is not None:
        score = max(score, severity)
    profile = _event_profile(analysis)
    signals = analysis.get("event_signals") if isinstance(analysis.get("event_signals"), dict) else {}
    if hard_veto:
        score = 100.0
        reasons.append("hard_veto")
    if profile in STRUCTURAL_PROFILES or signals.get("existential_or_solvency"):
        score = max(score, 90.0)
        reasons.append("structural_or_existential_profile")
    if signals.get("primary_endpoint_failure"):
        score = max(score, 92.0)
        reasons.append("pivotal_failure")
    if financing.get("classification") == "capital_distress":
        score = max(score, 95.0)
        reasons.append("capital_distress")
    if survivability < 25:
        score = max(score, 85.0)
        reasons.append("very_low_survivability")
    elif survivability < 45:
        score = max(score, 70.0)
        reasons.append("low_survivability")
    return _clamp(score), reasons


def _confidence_state(cause_status: str, confidence: float, fundamentals_available: bool) -> str:
    if cause_status == "VERIFIED" and confidence >= 75 and fundamentals_available:
        return "VERIFIED"
    if cause_status == "VERIFIED" and confidence >= 65:
        return "STRONGLY_INFERRED"
    if cause_status == "PARTIALLY_VERIFIED" and confidence >= 70:
        return "STRONGLY_INFERRED"
    if cause_status in {"VERIFIED", "PARTIALLY_VERIFIED"}:
        return "WEAKLY_INFERRED"
    if cause_status == "CONFLICTING":
        return "CONFLICTING"
    return "UNKNOWN"


def _price_session_context(candidate: dict[str, Any]) -> dict[str, Any]:
    value = candidate.get("price_session_context")
    return dict(value) if isinstance(value, dict) else {}


def _cap_score(
    score: float,
    *,
    cause_status: str,
    damage: float,
    tail_risk: float,
    critical_fundamentals_missing: bool,
    hard_veto: bool,
    analysis: dict[str, Any],
    price_context: dict[str, Any],
) -> tuple[float, float, list[dict[str, Any]]]:
    cap = 100.0
    caps: list[dict[str, Any]] = []

    def apply(name: str, value: float, reason: str | None = None) -> None:
        nonlocal cap
        if value < cap:
            cap = value
        caps.append({"type": name, "cap": value, "reason": reason})

    financing = analysis.get("dilution_analysis") if isinstance(analysis.get("dilution_analysis"), dict) else {}
    spike = analysis.get("spike_adjustment") if isinstance(analysis.get("spike_adjustment"), dict) else {}
    if hard_veto:
        apply("hard_veto", 15.0, "verified structural or capital-loss event")
    if damage >= 80:
        apply("structural_damage", 20.0)
    elif damage >= 65:
        apply("high_damage", 45.0)
    if tail_risk >= 90:
        apply("extreme_tail_risk", 18.0)
    elif tail_risk >= 75:
        apply("high_tail_risk", 35.0)
    if financing.get("classification") == "capital_distress":
        apply("capital_distress", 15.0)
    elif financing.get("classification") == "material_dilution":
        apply("material_dilution", 40.0)
    if spike.get("post_spike_unwind") and float(spike.get("penalty") or 0.0) >= 12:
        apply("post_spike_normalisation", 30.0)
    if cause_status == "UNVERIFIED":
        apply("unverified_cause", 45.0)
    elif cause_status == "CONFLICTING":
        apply("conflicting_cause", 40.0)
    elif cause_status == "PARTIALLY_VERIFIED":
        apply("partial_cause", 65.0)
    if critical_fundamentals_missing:
        apply("critical_fundamentals_unavailable", 55.0)
    if price_context.get("extended_hours_only"):
        apply("extended_hours_only_dislocation", 50.0)
    return min(score, cap), cap, caps


def patch_module(module: Any) -> None:
    if getattr(module, "_v33_installed", False):
        return
    original_score_candidate = module.score_candidate
    original_contract = module.public_scoring_contract

    legacy = getattr(module, "_legacy", None)
    if legacy is not None and not getattr(legacy, "_v33_sec_runtime_installed", False):
        legacy.load_runtime_enrichment = runtime_enrichment_wrapper(legacy.load_runtime_enrichment)
        legacy._v33_sec_runtime_installed = True

    module.SCORING_MODEL_VERSION = SCORING_MODEL_VERSION
    module.SCORING_CONFIG_VERSION = SCORING_CONFIG_VERSION
    module.CATALYST_SCHEMA_VERSION = CATALYST_SCHEMA_VERSION
    module.CALIBRATION_MODEL_VERSION = None
    module.MODEL_STATUS = "uncalibrated"
    module.SCORING_CONFIG = deepcopy(module.SCORING_CONFIG)
    module.SCORING_CONFIG["versions"].update(
        {
            "scoring_model_version": SCORING_MODEL_VERSION,
            "scoring_config_version": SCORING_CONFIG_VERSION,
            "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
            "calibration_model_version": None,
        }
    )
    module.SCORING_CONFIG["purpose"] = PURPOSE_STATEMENT
    module.SCORING_CONFIG["decision_thresholds"] = {"investigate": 72.0, "watch": 48.0}
    module.SCORING_CONFIG["v3_3"] = {
        "aggregation": "weighted_geometric_mean",
        "weights": {
            "overreaction": 0.28,
            "reversibility": 0.22,
            "survivability": 0.20,
            "three_session_fit": 0.15,
            "confirmation": 0.10,
            "technical_exhaustion": 0.05,
        },
        "confidence_multiplier": "0.35 + 0.65 * evidence_confidence",
        "minimum_investigate_dollar_volume": 2_000_000.0,
        "maximum_investigate_spread_pct": 3.0,
        "critical_fundamentals_required": True,
    }

    def score_candidate(
        candidate: dict[str, Any],
        articles: list[dict[str, Any]],
        catalyst_class: str,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        result = original_score_candidate(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        cause_status = str(analysis.get("cause_verification_status") or ("VERIFIED" if analysis.get("cause_verified") else "UNVERIFIED"))
        setup = _clamp(float(result.get("setup_score") or 0.0))
        catalyst = _clamp(float(result.get("catalyst_score") or 0.0))
        resilience = _clamp(float(result.get("resilience_score") or 0.0))
        confirmation = _clamp(float(result.get("confirmation_score") or 0.0))
        damage = _clamp(float(result.get("damage_risk") or 0.0))
        confidence = _clamp(float(result.get("evidence_confidence") or 0.0))
        reversibility = _clamp(_num(analysis.get("reversibility_score")) or catalyst)
        timing = _three_session_fit(analysis, damage)
        overreaction, overreaction_reasons = _overreaction_quality(setup, reversibility, damage, analysis)
        survivability, survivability_reasons, critical_fundamentals = _survivability(resilience, analysis, damage)
        tail_risk, tail_reasons = _tail_risk(damage, analysis, survivability, bool(result.get("hard_veto")))
        fundamental_trace, _raw = _fundamental_trace(analysis)
        enrichment_fundamentals = (
            (result.get("point_in_time_enrichment") or {}).get("fundamentals")
            if isinstance(result.get("point_in_time_enrichment"), dict)
            else None
        )
        if isinstance(enrichment_fundamentals, dict):
            raw_metrics = fundamental_trace.setdefault("raw_metrics", {})
            for key in (
                "cash_runway_months", "debt_to_assets", "current_ratio", "free_cash_flow",
                "operating_cash_flow", "cash_and_equivalents", "long_term_debt",
                "assets", "liabilities", "equity", "shares_outstanding", "market_cap",
                "annualized_revenue", "price_to_sales", "period_kind",
            ):
                if enrichment_fundamentals.get(key) is not None:
                    raw_metrics[key] = enrichment_fundamentals.get(key)
            fundamental_trace["available"] = True
            fundamental_trace["source"] = enrichment_fundamentals.get("source")
            fundamental_trace["form"] = enrichment_fundamentals.get("form")
            fundamental_trace["available_from"] = enrichment_fundamentals.get("available_from")
            fundamental_trace["report_period_end"] = enrichment_fundamentals.get("report_period_end")
            fundamental_trace["age_calendar_days"] = enrichment_fundamentals.get("age_calendar_days")
            fundamental_trace["metric_coverage_count"] = enrichment_fundamentals.get("metric_coverage_count")
        fundamentals_available = bool(fundamental_trace.get("available"))
        critical_fundamentals_missing = critical_fundamentals and not fundamentals_available
        price_context = _price_session_context(candidate)

        values = {
            "overreaction": overreaction,
            "reversibility": reversibility,
            "survivability": survivability,
            "three_session_fit": timing,
            "confirmation": confirmation,
            "technical_exhaustion": setup,
        }
        weights = module.SCORING_CONFIG["v3_3"]["weights"]
        raw_opportunity = _geometric(values, weights)
        confidence_multiplier = 0.35 + 0.65 * (confidence / 100.0)
        confidence_adjusted = raw_opportunity * confidence_multiplier
        tail_penalty = min(24.0, max(0.0, tail_risk - 40.0) * 0.35)
        pre_cap = _clamp(confidence_adjusted - tail_penalty)
        capped, cap, caps = _cap_score(
            pre_cap,
            cause_status=cause_status,
            damage=damage,
            tail_risk=tail_risk,
            critical_fundamentals_missing=critical_fundamentals_missing,
            hard_veto=bool(result.get("hard_veto")),
            analysis=analysis,
            price_context=price_context,
        )
        score = round(capped, 1)

        dollar_volume = _num(candidate.get("prev_dollar_volume"))
        spread = _num(candidate.get("spread_pct"))
        financing = analysis.get("dilution_analysis") if isinstance(analysis.get("dilution_analysis"), dict) else {}
        spike = analysis.get("spike_adjustment") if isinstance(analysis.get("spike_adjustment"), dict) else {}
        strong_partial = cause_status == "PARTIALLY_VERIFIED" and confidence >= 75.0
        gates = {
            "opportunity_threshold": score >= 72.0,
            "cause_verified_or_strong_partial": cause_status == "VERIFIED" or strong_partial,
            "evidence_confidence": confidence >= 65.0,
            "overreaction_quality": overreaction >= 60.0,
            "survivability": survivability >= 55.0,
            "three_session_fit": timing >= 55.0,
            "damage_not_high": damage <= 60.0,
            "tail_risk_acceptable": tail_risk <= 60.0,
            "critical_fundamentals_available": not critical_fundamentals_missing,
            "no_structural_veto": not bool(result.get("hard_veto")),
            "no_capital_distress": financing.get("classification") != "capital_distress",
            "dilution_not_material": financing.get("classification") != "material_dilution",
            "post_spike_not_dominant": not (
                spike.get("post_spike_unwind") and float(spike.get("penalty") or 0.0) >= 12.0
            ),
            "liquidity": dollar_volume is not None and dollar_volume >= 2_000_000.0,
            "spread_quality": spread is not None and spread <= 3.0,
            "regular_session_confirmation": not bool(price_context.get("extended_hours_only")),
        }
        failed = [name for name, passed in gates.items() if not passed]

        if (
            bool(result.get("hard_veto"))
            or financing.get("classification") == "capital_distress"
            or damage >= 80.0
            or tail_risk >= 90.0
            or score < 40.0
        ):
            verdict = "PASS"
        elif all(gates.values()):
            verdict = "INVESTIGATE"
        elif score >= 48.0:
            verdict = "WATCH"
        else:
            verdict = "PASS"

        confidence_state = _confidence_state(cause_status, confidence, fundamentals_available)
        evidence_state = (
            "VERIFIED_PRIMARY"
            if fundamentals_available and int(fundamental_trace.get("metric_coverage_count") or 0) >= 6
            else "PARTIAL_PRIMARY"
            if fundamentals_available
            else "UNAVAILABLE"
        )
        explanation = (
            f"Opportunity {score:.1f}/100; overreaction {overreaction:.0f}, survivability {survivability:.0f}, "
            f"three-session fit {timing:.0f}, tail risk {tail_risk:.0f}, evidence {confidence:.0f}. "
            + (
                "All INVESTIGATE gates passed."
                if verdict == "INVESTIGATE"
                else f"{verdict}: failed gates include {', '.join(failed[:5]) or 'opportunity threshold'}."
            )
        )

        analysis["three_session_fit_score"] = round(timing, 1)
        analysis["overreaction_quality_score"] = round(overreaction, 1)
        analysis["survivability_score"] = round(survivability, 1)
        analysis["tail_risk_score"] = round(tail_risk, 1)
        analysis["assessment_confidence_state"] = confidence_state
        analysis["fundamental_evidence_state"] = evidence_state
        analysis["critical_fundamentals_required"] = critical_fundamentals
        analysis["eligibility_gates"] = gates
        analysis["failed_eligibility_gates"] = failed
        analysis["analysis_method"] = "rules_v3_3_point_in_time"
        analysis["overreaction_reasons"] = overreaction_reasons
        analysis["survivability_reasons"] = survivability_reasons
        analysis["tail_risk_reasons"] = tail_reasons
        analysis["price_session_context"] = price_context

        trace = result.setdefault("calculation_trace", {})
        trace["formula"] = (
            "v3.3: geometric(overreaction,reversibility,survivability,three_session_fit,"
            "confirmation,technical_exhaustion) * one-way confidence multiplier - asymmetric "
            "tail penalty -> economic caps -> INVESTIGATE gates"
        )
        trace["v3_3"] = {
            "purpose": PURPOSE_STATEMENT,
            "component_scores": {key: round(value, 2) for key, value in values.items()},
            "weights": weights,
            "raw_opportunity_quality": round(raw_opportunity, 2),
            "confidence_multiplier": round(confidence_multiplier, 4),
            "confidence_adjusted_opportunity": round(confidence_adjusted, 2),
            "tail_risk_penalty": round(tail_penalty, 2),
            "pre_cap_score": round(pre_cap, 2),
            "final_cap": round(cap, 1),
            "caps_applied": caps,
            "eligibility_gates": gates,
            "failed_eligibility_gates": failed,
            "price_session_context": price_context,
        }
        trace["final"] = {
            "final_score": score,
            "verdict": verdict,
            "eligibility_gates": gates,
            "failed_eligibility_gates": failed,
            "caps_applied": caps,
        }

        result.update(
            {
                "model_status": "uncalibrated",
                "scoring_model_version": SCORING_MODEL_VERSION,
                "scoring_config_version": SCORING_CONFIG_VERSION,
                "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
                "calibration_model_version": None,
                "core_score": round(raw_opportunity, 2),
                "confidence_adjusted_score": round(confidence_adjusted, 2),
                "damage_penalty": round(tail_penalty, 2),
                "damage_cap": round(cap, 1),
                "pre_cap_score": round(pre_cap, 2),
                "final_score": score,
                "verdict": verdict,
                "missing_inputs": list(dict.fromkeys(result.get("missing_inputs") or [])),
                "explanation": explanation,
            }
        )
        return result

    def public_scoring_contract() -> dict[str, Any]:
        base = original_contract()
        base.update(
            {
                "model_status": "uncalibrated",
                "purpose": PURPOSE_STATEMENT,
                "target_definition": module.TARGET_DEFINITION,
                "versions": module.SCORING_CONFIG["versions"],
                "opportunity_architecture": module.SCORING_CONFIG["v3_3"],
                "confidence_rule": (
                    "Evidence confidence is displayed separately and can only reduce the opportunity score; "
                    "missing evidence never raises a candidate."
                ),
                "hard_gates": [
                    "verified or exceptionally strong partial cause",
                    "acceptable economic damage and tail risk",
                    "survivability",
                    "critical financial evidence when the event requires it",
                    "liquidity and spread quality",
                    "regular-session confirmation",
                    "no capital distress, material dilution or dominant post-spike normalisation",
                ],
            }
        )
        return base

    module.score_candidate = score_candidate
    module.public_scoring_contract = public_scoring_contract
    module._v33_installed = True
