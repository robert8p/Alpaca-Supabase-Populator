from __future__ import annotations

"""Oversold Reversion Score v3.2.

This module is an additive compatibility layer over the frozen v3.1 scorer.  It
keeps the existing point-in-time feature/evidence pipeline intact, then applies
an explicit economic-risk layer for price-path normalisation, financing/dilution
severity, cause verification and INVESTIGATE eligibility gates.

The legacy module is loaded under a private module name so historical v3.1 code
remains untouched and reproducible.  app.__init__ exposes this module as
``app.oversold_scoring`` for new runs only.
"""

from copy import deepcopy
from importlib import util as importlib_util
from pathlib import Path
import math
import re
from typing import Any


_LEGACY_PATH = Path(__file__).with_name("oversold_scoring.py")
_SPEC = importlib_util.spec_from_file_location("app._oversold_scoring_v31", _LEGACY_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive startup guard
    raise RuntimeError("Unable to load the frozen v3.1 Oversold Reversion scorer")
_legacy = importlib_util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_legacy)

# Preserve the existing public helper surface for callers/tests that import from
# app.oversold_scoring.  v3.2 overrides only the versioned scoring contract and
# score_candidate/public_scoring_contract below.
for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_legacy, _name))

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_2"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v3"
CATALYST_PROMPT_VERSION = getattr(_legacy, "CATALYST_PROMPT_VERSION", "catalyst_rules_prompt_v3")
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3_2"
CALIBRATION_MODEL_VERSION: str | None = None
MODEL_STATUS = "uncalibrated"
TARGET_DEFINITION = getattr(_legacy, "TARGET_DEFINITION", "hit_plus_5pct_within_6_weeks")

SCORING_CONFIG: dict[str, Any] = deepcopy(_legacy.SCORING_CONFIG)
SCORING_CONFIG["versions"] = {
    "scoring_model_version": SCORING_MODEL_VERSION,
    "scoring_config_version": SCORING_CONFIG_VERSION,
    "catalyst_prompt_version": CATALYST_PROMPT_VERSION,
    "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
    "calibration_model_version": CALIBRATION_MODEL_VERSION,
}
SCORING_CONFIG["damage"] = {
    "penalty_start": 20.0,
    "penalty_per_point": 0.28,
    "penalty_max": 22.0,
    "caps": [
        {"min": 0, "max": 29, "cap": 100},
        {"min": 30, "max": 49, "cap": 82},
        {"min": 50, "max": 64, "cap": 62},
        {"min": 65, "max": 79, "cap": 42},
        {"min": 80, "max": 100, "cap": 20},
    ],
}
SCORING_CONFIG["cause_verification"] = {
    "verified_min_source_confidence": 65.0,
    "strong_partial_min_confidence": 75.0,
    "unverified_final_cap": 50.0,
    "partial_final_cap": 65.0,
    "conflicting_final_cap": 45.0,
}
SCORING_CONFIG["post_spike"] = {
    "lookbacks": [1, 3, 5, 10, 20],
    "spike_threshold_pct": 50.0,
    "extreme_spike_threshold_pct": 100.0,
    "investigate_max_penalty": 12.0,
}
SCORING_CONFIG["financing"] = {
    "material_dilution_threshold": 40.0,
    "capital_distress_threshold": 75.0,
    "hard_veto_threshold": 85.0,
    "investigate_max_severity": 45.0,
}
SCORING_CONFIG["investigate_gates"] = {
    "minimum_evidence_confidence": 65.0,
    "maximum_damage_risk": 64.0,
    "maximum_spread_pct": 5.0,
    "minimum_previous_dollar_volume": 500_000.0,
    "minimum_market_data_completeness": 50.0,
    "minimum_final_score": 75.0,
}

_FINANCING_TERMS = (
    "public offering", "registered direct", "private placement", "at-the-market", "at the market",
    "secondary offering", "convertible", "warrant", "securities purchase agreement", "equity offering",
)
_DISTRESS_TERMS = (
    "going concern", "unable to continue", "debt default", "covenant breach", "liquidity crisis",
    "nasdaq deficiency", "listing deficiency", "delisting", "minimum bid price", "toxic convertible",
)
_REPEATED_RAISE_TERMS = (
    "another offering", "second offering", "additional offering", "subsequent financing", "again raises",
    "additional financing", "repeat financing",
)
_REVERSE_SPLIT_RE = re.compile(r"(?:reverse(?: stock)? split|reverse share split|\b1[- ]for[- ]\d+\b)", re.IGNORECASE)
_PER_SHARE_PRICE_RE = re.compile(r"(?:price(?:d)?(?:\s+at|\s+of)?|at)\s+\$([0-9]+(?:\.[0-9]+)?)\s+per\s+(?:share|unit)", re.IGNORECASE)
_SHARE_COUNT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(million|billion|thousand|m|b|k)?\s+(?:common\s+|ordinary\s+)?shares", re.IGNORECASE)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _article_text(articles: list[dict[str, Any]]) -> str:
    return " ".join(
        f"{item.get('headline') or ''} {item.get('summary') or ''}"
        for item in articles if isinstance(item, dict)
    ).lower()


def _scale_count(value: str, suffix: str | None) -> float:
    factor = {"": 1.0, "k": 1_000.0, "thousand": 1_000.0, "m": 1_000_000.0,
              "million": 1_000_000.0, "b": 1_000_000_000.0, "billion": 1_000_000_000.0}
    return float(value) * factor.get(str(suffix or "").lower(), 1.0)


def _history_closes(result: dict[str, Any]) -> list[float]:
    enrichment = result.get("point_in_time_enrichment") or {}
    rows = enrichment.get("history_bars") or []
    closes: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = _num(row.get("c"))
        if value is not None and value > 0:
            closes.append(value)
    return closes


def price_path_assessment(candidate: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Measure whether the signal is genuinely below its pre-run-up baseline.

    The history bars stored in the evidence snapshot end before the signal date,
    so every return here is available at the original evidence cutoff.
    """
    closes = _history_closes(result)
    previous = _num(candidate.get("prev_close")) or (closes[-1] if closes else None)
    current = _num(candidate.get("last_price"))
    lookbacks = list(SCORING_CONFIG["post_spike"]["lookbacks"])
    prior_returns: dict[str, float | None] = {}
    runups: list[tuple[int, float, float]] = []
    if previous is not None and previous > 0:
        for days in lookbacks:
            if len(closes) >= days + 1:
                baseline = closes[-(days + 1)]
                move = ((previous / baseline) - 1.0) * 100.0 if baseline > 0 else None
                prior_returns[f"return_{days}d_before_signal_pct"] = round(move, 2) if move is not None else None
                if move is not None:
                    runups.append((days, move, baseline))
            else:
                prior_returns[f"return_{days}d_before_signal_pct"] = None

    positive = [item for item in runups if item[1] > 0]
    if positive:
        window, runup_pct, baseline = max(positive, key=lambda item: item[1])
    else:
        window, runup_pct, baseline = (None, None, None)

    current_vs_baseline = None
    retraced = None
    remaining = None
    if current is not None and baseline is not None and baseline > 0:
        current_vs_baseline = ((current / baseline) - 1.0) * 100.0
        if previous is not None and previous > baseline:
            spike_amount = previous - baseline
            retraced = _clamp((previous - current) / spike_amount * 100.0)
            remaining = _clamp((current - baseline) / spike_amount * 100.0)

    threshold = float(SCORING_CONFIG["post_spike"]["spike_threshold_pct"])
    spike_detected = bool(runup_pct is not None and runup_pct >= threshold)
    penalty = 0.0
    setup_cap = 100.0
    reasons: list[str] = []
    if spike_detected:
        if current_vs_baseline is not None and current_vs_baseline >= 30.0:
            penalty, setup_cap = 25.0, 35.0
            reasons.append("current_price_still_materially_above_pre_spike_baseline")
        elif current_vs_baseline is not None and current_vs_baseline >= 10.0:
            penalty, setup_cap = 18.0, 45.0
            reasons.append("most_of_selloff_is_consistent_with_spike_normalisation")
        elif current_vs_baseline is not None and current_vs_baseline >= 0.0:
            penalty, setup_cap = 12.0, 55.0
            reasons.append("price_only_returned_to_pre_spike_baseline")
        else:
            penalty, setup_cap = 4.0, 75.0
            reasons.append("prior_spike_exists_but_price_is_now_below_baseline")
        if runup_pct is not None and runup_pct >= float(SCORING_CONFIG["post_spike"]["extreme_spike_threshold_pct"]):
            penalty = min(30.0, penalty + 4.0)
            setup_cap = min(setup_cap, 32.0 if (current_vs_baseline or 0.0) >= 10 else setup_cap)
            reasons.append("extreme_prior_runup")

    return {
        "prior_returns": prior_returns,
        "runup_window_sessions": window,
        "max_prior_runup_pct": round(runup_pct, 2) if runup_pct is not None else None,
        "pre_spike_baseline_price": round(baseline, 4) if baseline is not None else None,
        "previous_close": round(previous, 4) if previous is not None else None,
        "signal_price": round(current, 4) if current is not None else None,
        "current_vs_pre_spike_baseline_pct": round(current_vs_baseline, 2) if current_vs_baseline is not None else None,
        "spike_retraced_pct": round(retraced, 1) if retraced is not None else None,
        "spike_remaining_pct": round(remaining, 1) if remaining is not None else None,
        "post_spike_unwind": spike_detected,
        "penalty": penalty,
        "setup_cap": setup_cap,
        "reasons": reasons,
    }


def source_quality_hierarchy(candidate: dict[str, Any], articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    causal, trace = _legacy.filter_causal_articles(candidate, articles)
    trace_by_id = {str(item.get("id")): item for item in (trace.get("articles") or [])}
    output: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        headline = str(article.get("headline") or "")
        source = str(article.get("source") or "")
        text = f"{headline} {article.get('summary') or ''}".lower()
        lower_source = source.lower()
        relevance = trace_by_id.get(str(article.get("id"))) or {}
        if any(token in text for token in ("form 8-k", "form 10-q", "form 10-k", "sec filing", "securities and exchange commission")):
            source_type, quality = "regulatory_filing", 100
        elif any(token in lower_source for token in ("company ir", "investor relations", "business wire", "businesswire", "globenewswire", "globe newswire", "accesswire", "pr newswire")):
            source_type, quality = "company_primary_release", 92
        elif "earnings" in text and any(token in text for token in ("reports", "results", "quarter")):
            source_type, quality = "earnings_release", 90
        elif "transcript" in text:
            source_type, quality = "earnings_transcript", 86
        elif any(token in lower_source for token in ("reuters", "dow jones", "bloomberg", "associated press", "wall street journal")):
            source_type, quality = "major_financial_media", 82
        elif relevance.get("generic") and not relevance.get("ticker_mentioned"):
            source_type, quality = "market_movers_listing_only", 20
        elif relevance.get("generic"):
            source_type, quality = "market_movers_specific", 48
        elif article in causal:
            source_type, quality = "specialist_financial_media", 65
        else:
            source_type, quality = "ambiguous_or_unrelated", 10
        output.append({
            "id": article.get("id"),
            "headline": headline,
            "source": source,
            "source_type": source_type,
            "source_quality_score": quality,
            "ticker_relevance": relevance.get("score"),
            "causal_relevance": relevance.get("kind"),
            "published_at": article.get("created_at"),
        })
    return output


def cause_verification_status(result: dict[str, Any]) -> str:
    analysis = result.get("catalyst_analysis") or {}
    quality = analysis.get("evidence_quality_trace") or {}
    relevance = analysis.get("news_relevance_trace") or {}
    if quality.get("conflicting_evidence"):
        return "CONFLICTING"
    if not analysis.get("cause_verified"):
        return "PARTIALLY_VERIFIED" if int(relevance.get("causal_article_count") or 0) > 0 else "UNVERIFIED"
    source_confidence = _num(analysis.get("evidence_confidence")) or 0.0
    direct = any(
        item.get("kind") == "direct_event" and not item.get("generic")
        for item in (relevance.get("articles") or [])
    )
    if source_confidence >= float(SCORING_CONFIG["cause_verification"]["verified_min_source_confidence"]) and direct:
        return "VERIFIED"
    return "PARTIALLY_VERIFIED"


def financing_assessment(candidate: dict[str, Any], articles: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    text = _article_text(articles)
    financing = any(term in text for term in _FINANCING_TERMS)
    reverse_split = bool(_REVERSE_SPLIT_RE.search(text))
    listing_stress = any(term in text for term in ("nasdaq deficiency", "listing deficiency", "delisting", "minimum bid price"))
    going_concern = "going concern" in text or "unable to continue as a going concern" in text
    repeated_raise = any(term in text for term in _REPEATED_RAISE_TERMS)
    convertible = "convertible" in text
    warrants = "warrant" in text

    offering_prices = [_num(value) for value in _PER_SHARE_PRICE_RE.findall(text)]
    offering_prices = [value for value in offering_prices if value is not None and value > 0]
    offering_price = min(offering_prices) if offering_prices else None
    previous = _num(candidate.get("prev_close"))
    discount = ((offering_price / previous) - 1.0) * 100.0 if offering_price and previous and previous > 0 else None

    share_matches = _SHARE_COUNT_RE.findall(text)
    announced_new_shares = max((_scale_count(value, suffix) for value, suffix in share_matches), default=None)

    analysis = result.get("catalyst_analysis") or {}
    fundamentals = (analysis.get("fundamental_trace") or {}).get("raw_metrics") or {}
    shares_yoy = _num(fundamentals.get("diluted_shares_yoy"))
    cash_to_assets = _num(fundamentals.get("cash_to_assets"))
    liabilities_to_assets = _num(fundamentals.get("liabilities_to_assets"))
    equity_to_assets = _num(fundamentals.get("equity_to_assets"))

    if not financing and not reverse_split and not listing_stress and not going_concern:
        return {
            "is_financing_event": False,
            "classification": "not_applicable",
            "severity_score": 0.0,
            "penalty": 0.0,
            "hard_veto": False,
            "reasons": [],
            "offering_price": None,
            "discount_to_previous_close_pct": None,
            "announced_new_shares": None,
            "diluted_shares_yoy": shares_yoy,
            "reverse_split": False,
            "listing_stress": False,
        }

    severity = 20.0 if financing else 15.0
    reasons: list[str] = []
    if shares_yoy is not None:
        if shares_yoy >= 0.50:
            severity += 35; reasons.append("diluted_share_count_yoy_ge_50pct")
        elif shares_yoy >= 0.25:
            severity += 25; reasons.append("diluted_share_count_yoy_ge_25pct")
        elif shares_yoy >= 0.10:
            severity += 12; reasons.append("diluted_share_count_yoy_ge_10pct")
    if discount is not None:
        if discount <= -30:
            severity += 25; reasons.append("offering_discount_ge_30pct")
        elif discount <= -20:
            severity += 18; reasons.append("offering_discount_ge_20pct")
        elif discount <= -10:
            severity += 10; reasons.append("offering_discount_ge_10pct")
    if convertible:
        severity += 12; reasons.append("convertible_security")
    if warrants:
        severity += 10; reasons.append("warrant_overhang")
    if repeated_raise:
        severity += 15; reasons.append("repeated_financing_language")
    if reverse_split:
        severity += 25; reasons.append("reverse_split")
    if listing_stress:
        severity += 20; reasons.append("listing_stress")
    if going_concern:
        severity += 35; reasons.append("going_concern")
    if cash_to_assets is not None and cash_to_assets <= 0.03:
        severity += 15; reasons.append("very_low_cash_to_assets")
    if liabilities_to_assets is not None and liabilities_to_assets >= 0.90:
        severity += 10; reasons.append("very_high_liabilities_to_assets")
    if equity_to_assets is not None and equity_to_assets <= 0.05:
        severity += 10; reasons.append("very_low_equity_to_assets")

    severity = _clamp(severity)
    distress_threshold = float(SCORING_CONFIG["financing"]["capital_distress_threshold"])
    material_threshold = float(SCORING_CONFIG["financing"]["material_dilution_threshold"])
    if severity >= distress_threshold or (reverse_split and listing_stress) or going_concern:
        classification = "capital_distress"
    elif severity >= material_threshold:
        classification = "material_dilution"
    else:
        classification = "financing_benign"
    hard_veto = severity >= float(SCORING_CONFIG["financing"]["hard_veto_threshold"]) or (going_concern and financing)
    penalty = 0.0 if classification == "financing_benign" else min(25.0, max(0.0, severity - 25.0) * 0.30)
    return {
        "is_financing_event": True,
        "classification": classification,
        "severity_score": round(severity, 1),
        "penalty": round(penalty, 1),
        "hard_veto": hard_veto,
        "reasons": reasons,
        "offering_price": offering_price,
        "discount_to_previous_close_pct": round(discount, 2) if discount is not None else None,
        "announced_new_shares": announced_new_shares,
        "diluted_shares_yoy": shares_yoy,
        "cash_to_assets": cash_to_assets,
        "liabilities_to_assets": liabilities_to_assets,
        "equity_to_assets": equity_to_assets,
        "convertible": convertible,
        "warrants": warrants,
        "reverse_split": reverse_split,
        "listing_stress": listing_stress,
        "going_concern": going_concern,
        "repeated_raise": repeated_raise,
    }


def _damage_class(damage: float) -> str:
    if damage >= 80:
        return "STRUCTURAL_OR_EXISTENTIAL"
    if damage >= 55:
        return "HIGH"
    if damage >= 30:
        return "MODERATE"
    return "LOW"


def _damage_cap_v32(damage: float) -> float:
    value = _clamp(damage)
    for band in SCORING_CONFIG["damage"]["caps"]:
        if float(band["min"]) <= value <= float(band["max"]):
            return float(band["cap"])
    return 20.0


def _final_v32(
    candidate: dict[str, Any],
    result: dict[str, Any],
    *,
    setup: float,
    catalyst: float,
    resilience: float,
    confirmation: float,
    confidence: float,
    damage: float,
    cause_status: str,
    spike: dict[str, Any],
    financing: dict[str, Any],
) -> dict[str, Any]:
    weights = SCORING_CONFIG["weights"]
    contributions = {
        "setup": setup * float(weights["setup"]),
        "catalyst": catalyst * float(weights["catalyst"]),
        "resilience": resilience * float(weights["resilience"]),
        "confirmation": confirmation * float(weights["confirmation"]),
    }
    core = sum(contributions.values())
    confidence_adjusted = 50.0 + ((core - 50.0) * _clamp(confidence) / 100.0)
    damage_cfg = SCORING_CONFIG["damage"]
    damage_penalty = min(
        float(damage_cfg["penalty_max"]),
        max(0.0, damage - float(damage_cfg["penalty_start"])) * float(damage_cfg["penalty_per_point"]),
    )
    spike_penalty = float(spike.get("penalty") or 0.0)
    dilution_penalty = float(financing.get("penalty") or 0.0)
    pre_cap = _clamp(confidence_adjusted - damage_penalty - spike_penalty - dilution_penalty)

    cap = _damage_cap_v32(damage)
    caps: list[dict[str, Any]] = [{"type": "damage", "cap": cap}]
    cause_cfg = SCORING_CONFIG["cause_verification"]
    cause_cap = {
        "UNVERIFIED": float(cause_cfg["unverified_final_cap"]),
        "PARTIALLY_VERIFIED": float(cause_cfg["partial_final_cap"]),
        "CONFLICTING": float(cause_cfg["conflicting_final_cap"]),
    }.get(cause_status)
    if cause_cap is not None:
        cap = min(cap, cause_cap)
        caps.append({"type": "cause_verification", "status": cause_status, "cap": cause_cap})

    legacy_hard_veto = bool(result.get("hard_veto"))
    financing_veto = bool(financing.get("hard_veto"))
    hard_veto = legacy_hard_veto or financing_veto
    hard_veto_reason = result.get("hard_veto_reason")
    if financing_veto:
        hard_veto_reason = "severe_dilution_or_capital_distress"
    if hard_veto:
        cap = min(cap, 20.0)
        caps.append({"type": "hard_veto", "cap": 20.0, "reason": hard_veto_reason})

    score = round(min(pre_cap, cap), 1)
    completeness = _num((result.get("calculation_trace") or {}).get("market_data_completeness")) or 0.0
    spread = _num(candidate.get("spread_pct"))
    dollar_volume = _num(candidate.get("prev_dollar_volume"))
    gate_cfg = SCORING_CONFIG["investigate_gates"]
    cause_gate = cause_status == "VERIFIED" or (
        cause_status == "PARTIALLY_VERIFIED" and confidence >= float(cause_cfg["strong_partial_min_confidence"])
    )
    gates = {
        "score_threshold": score >= float(gate_cfg["minimum_final_score"]),
        "cause_verified_or_strong_partial": cause_gate,
        "evidence_confidence": confidence >= float(gate_cfg["minimum_evidence_confidence"]),
        "damage_not_high": damage <= float(gate_cfg["maximum_damage_risk"]),
        "no_structural_veto": not hard_veto,
        "no_capital_distress": financing.get("classification") != "capital_distress",
        "post_spike_not_dominant": spike_penalty <= float(SCORING_CONFIG["post_spike"]["investigate_max_penalty"]),
        "dilution_not_severe": float(financing.get("severity_score") or 0.0) <= float(SCORING_CONFIG["financing"]["investigate_max_severity"]),
        "liquidity": dollar_volume is not None and dollar_volume >= float(gate_cfg["minimum_previous_dollar_volume"]),
        "spread_quality": spread is not None and spread <= float(gate_cfg["maximum_spread_pct"]),
        "market_data_completeness": completeness >= float(gate_cfg["minimum_market_data_completeness"]),
    }
    failed = [name for name, passed in gates.items() if not passed]

    if hard_veto or financing.get("classification") == "capital_distress" or damage >= 80.0:
        verdict = "PASS"
    elif score < float(SCORING_CONFIG["decision_thresholds"]["watch"]):
        verdict = "PASS"
    elif cause_status == "UNVERIFIED" and confidence < 45.0:
        verdict = "PASS"
    elif all(gates.values()):
        verdict = "INVESTIGATE"
    else:
        verdict = "WATCH"

    return {
        "core_score": round(core, 2),
        "weighted_contributions": {key: round(value, 2) for key, value in contributions.items()},
        "confidence_adjusted_score": round(confidence_adjusted, 2),
        "damage_penalty": round(damage_penalty, 2),
        "post_spike_penalty": round(spike_penalty, 2),
        "dilution_penalty": round(dilution_penalty, 2),
        "damage_cap": round(_damage_cap_v32(damage), 1),
        "pre_cap_score": round(pre_cap, 2),
        "final_score": score,
        "verdict": verdict,
        "hard_veto": hard_veto,
        "hard_veto_reason": hard_veto_reason,
        "caps_applied": caps,
        "eligibility_gates": gates,
        "failed_eligibility_gates": failed,
    }


def score_candidate(candidate: dict[str, Any], articles: list[dict[str, Any]], catalyst_class: str, risk_flags: list[str]) -> dict[str, Any]:
    base = _legacy.score_candidate(candidate, articles, catalyst_class, risk_flags)
    analysis = base.setdefault("catalyst_analysis", {})
    spike = price_path_assessment(candidate, base)
    financing = financing_assessment(candidate, articles, base)
    cause_status = cause_verification_status(base)
    sources = source_quality_hierarchy(candidate, articles)

    setup = min(float(base.get("setup_score") or 0.0), float(spike.get("setup_cap") or 100.0))
    catalyst = float(base.get("catalyst_score") or 0.0)
    resilience = float(base.get("resilience_score") or 0.0)
    confirmation = float(base.get("confirmation_score") or 0.0)
    confidence = float(base.get("evidence_confidence") or 0.0)
    damage = float(base.get("damage_risk") or 0.0)

    severity = float(financing.get("severity_score") or 0.0)
    if financing.get("classification") == "material_dilution":
        catalyst = min(catalyst, max(18.0, 68.0 - severity * 0.45))
        damage = max(damage, min(82.0, 45.0 + severity * 0.45))
    elif financing.get("classification") == "capital_distress":
        catalyst = min(catalyst, 18.0)
        damage = max(damage, 88.0)
        resilience = min(resilience, 22.0)
    elif financing.get("classification") == "financing_benign":
        damage = max(damage, 35.0)

    if cause_status == "UNVERIFIED":
        catalyst = min(catalyst, 30.0)
        confidence = min(confidence, 45.0)
    elif cause_status == "CONFLICTING":
        catalyst = min(catalyst, 28.0)
        confidence = min(confidence, 55.0)
    elif cause_status == "PARTIALLY_VERIFIED":
        catalyst = min(catalyst, 55.0)

    final = _final_v32(
        candidate,
        base,
        setup=setup,
        catalyst=catalyst,
        resilience=resilience,
        confirmation=confirmation,
        confidence=confidence,
        damage=damage,
        cause_status=cause_status,
        spike=spike,
        financing=financing,
    )

    if financing.get("classification") == "capital_distress":
        analysis["event_profile"] = "capital_distress"
    elif financing.get("classification") == "material_dilution":
        analysis["event_profile"] = "material_dilution"
    elif financing.get("classification") == "financing_benign":
        analysis["event_profile"] = "financing_benign"
    elif spike.get("post_spike_unwind") and float(spike.get("penalty") or 0.0) >= 12.0:
        analysis["event_profile"] = "post_spike_unwind"

    analysis["cause_verification_status"] = cause_status
    analysis["economic_damage_class"] = _damage_class(damage)
    analysis["spike_adjustment"] = spike
    analysis["dilution_analysis"] = financing
    analysis["source_quality_items"] = sources
    analysis["eligibility_gates"] = final["eligibility_gates"]
    analysis["failed_eligibility_gates"] = final["failed_eligibility_gates"]
    analysis["analysis_method"] = "rules_v3_2_point_in_time"
    analysis["fundamental_damage_risk"] = round(damage, 1)
    analysis["catalyst_score"] = round(catalyst, 1)

    if final["verdict"] == "INVESTIGATE":
        explanation = (
            f"Score {final['final_score']:.1f}/100. {cause_status} cause; {_damage_class(damage).lower()} economic damage. "
            "Price-path, evidence, liquidity and structural-risk INVESTIGATE gates passed."
        )
    elif financing.get("classification") == "capital_distress":
        explanation = (
            f"Score {final['final_score']:.1f}/100 after gating. Financing is classified as capital distress "
            f"(severity {severity:.0f}/100); structural/capital-risk gate forces PASS."
        )
    elif spike.get("post_spike_unwind") and float(spike.get("penalty") or 0.0) >= 12.0:
        baseline_text = spike.get("current_vs_pre_spike_baseline_pct")
        explanation = (
            f"Score {final['final_score']:.1f}/100 after a {float(spike.get('penalty') or 0):.0f}-point post-spike penalty. "
            f"The stock remains {baseline_text if baseline_text is not None else 'unknown'}% versus its pre-spike baseline; verdict capped by price-path normalisation risk."
        )
    elif cause_status in {"UNVERIFIED", "CONFLICTING"}:
        explanation = (
            f"Score {final['final_score']:.1f}/100. Cause is {cause_status}; high decline magnitude cannot substitute for causal evidence. "
            f"Verdict is {final['verdict']}."
        )
    else:
        failed = ", ".join(final["failed_eligibility_gates"][:4]) or "score threshold"
        explanation = (
            f"Score {final['final_score']:.1f}/100. Cause {cause_status}; damage {_damage_class(damage).lower()}. "
            f"INVESTIGATE gates not all satisfied ({failed})."
        )

    trace = base.setdefault("calculation_trace", {})
    trace["formula"] = (
        "v3.2: v3.1 point-in-time components -> explicit price-path/financing/cause adjustments -> "
        "core=.25*setup+.35*catalyst+.15*resilience+.25*confirmation -> confidence shrink -> "
        "damage + spike + dilution penalties -> damage/cause/veto caps -> INVESTIGATE eligibility gates"
    )
    trace["v3_2"] = {
        "price_path": spike,
        "financing": financing,
        "cause_verification_status": cause_status,
        "economic_damage_class": _damage_class(damage),
        "source_quality_hierarchy": sources,
        "weighted_contributions": final["weighted_contributions"],
        "eligibility_gates": final["eligibility_gates"],
        "failed_eligibility_gates": final["failed_eligibility_gates"],
        "penalties": {
            "damage": final["damage_penalty"],
            "post_spike": final["post_spike_penalty"],
            "dilution": final["dilution_penalty"],
        },
    }
    trace["final"] = final
    trace["config"] = SCORING_CONFIG

    base.update({
        "setup_score": round(setup, 1),
        "catalyst_score": round(catalyst, 1),
        "resilience_score": round(resilience, 1),
        "confirmation_score": round(confirmation, 1),
        "damage_risk": round(damage, 1),
        "evidence_confidence": round(confidence, 1),
        "model_status": MODEL_STATUS,
        "scoring_model_version": SCORING_MODEL_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "catalyst_prompt_version": CATALYST_PROMPT_VERSION,
        "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
        "calibration_model_version": CALIBRATION_MODEL_VERSION,
        "target_definition": TARGET_DEFINITION,
        "explanation": explanation,
        **{key: value for key, value in final.items() if key != "weighted_contributions"},
    })
    return base


def public_scoring_contract() -> dict[str, Any]:
    return {
        "model_status": MODEL_STATUS,
        "target_definition": TARGET_DEFINITION,
        "versions": SCORING_CONFIG["versions"],
        "weights": SCORING_CONFIG["weights"],
        "setup_feature_weights": SCORING_CONFIG["setup_feature_weights"],
        "confirmation_feature_weights": SCORING_CONFIG["confirmation_feature_weights"],
        "confidence": SCORING_CONFIG["confidence"],
        "damage": SCORING_CONFIG["damage"],
        "cause_unknown": SCORING_CONFIG.get("cause_unknown"),
        "cause_verification": SCORING_CONFIG["cause_verification"],
        "post_spike": SCORING_CONFIG["post_spike"],
        "financing": SCORING_CONFIG["financing"],
        "investigate_gates": SCORING_CONFIG["investigate_gates"],
        "decision_thresholds": SCORING_CONFIG["decision_thresholds"],
        "calibration": SCORING_CONFIG["calibration"],
    }
