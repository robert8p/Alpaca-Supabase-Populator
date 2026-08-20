from __future__ import annotations

"""Oversold Reversion Score v3.4: conservative reliability layer.

v3.4 does not pretend that one deterministic point estimate is precise. It
classifies the relevance and independence of retained evidence, detects material
claim contradictions, estimates execution friction, stress-tests uncertain model
components and ranks on a conservative scenario score. The v3.3 base calculation
remains visible in the immutable calculation trace.
"""

import math
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_4"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v6"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3_4"
RELIABILITY_VERSION = "reliability_scenarios_v1"

EVENT_FAMILIES: dict[str, tuple[str, ...]] = {
    "financing": ("financing", "dilution", "offering", "capital_distress", "listing_risk"),
    "earnings": ("earnings", "guidance", "deterioration", "margin", "revenue"),
    "clinical": ("clinical", "endpoint", "trial", "pivotal", "phase"),
    "regulatory": ("regulatory", "fda", "approval", "clinical_hold", "recall"),
    "operations": ("operational", "outage", "disruption", "production", "customer"),
    "legal": ("legal", "litigation", "investigation", "fraud", "governance"),
    "analyst": ("analyst", "rating", "price_target"),
    "transaction": ("control_transaction", "merger", "acquisition"),
    "spike": ("post_spike", "unwind", "technical"),
    "solvency": ("solvency", "bankruptcy", "default", "going_concern", "capital_distress"),
}
FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "financing": ("offering", "registered direct", "private placement", "warrant", "convertible", "dilution", "proceeds"),
    "earnings": ("earnings", "revenue", "sales", "guidance", "forecast", "outlook", "margin", "ebitda", "eps"),
    "clinical": ("clinical trial", "phase 3", "phase iii", "endpoint", "statistically significant", "safety"),
    "regulatory": ("fda", "approval", "complete response letter", "clinical hold", "recall", "clearance"),
    "operations": ("outage", "production", "operations", "shutdown", "resumed", "disruption", "customer", "contract"),
    "legal": ("lawsuit", "litigation", "investigation", "subpoena", "fraud", "material weakness", "restatement"),
    "analyst": ("analyst", "downgrade", "upgrade", "rating", "price target", "overweight", "underperform"),
    "transaction": ("merger", "acquisition", "tender offer", "business combination", "change of control"),
    "spike": ("rally", "surge", "spike", "profit taking", "unwind", "volatility"),
    "solvency": ("bankruptcy", "chapter 11", "going concern", "substantial doubt", "default", "covenant", "liquidity"),
}
CLAIM_PATTERNS: dict[str, dict[str, tuple[re.Pattern[str], ...]]] = {
    "guidance": {
        "positive": (
            re.compile(r"\b(?:reaffirm(?:ed|s)?|maintain(?:ed|s)?|unchanged|raise(?:d|s)?|increase(?:d|s)?)\b.{0,45}\b(?:guidance|outlook|forecast)\b", re.I),
            re.compile(r"\b(?:guidance|outlook|forecast)\b.{0,45}\b(?:reaffirm(?:ed|s)?|unchanged|raised|increased)\b", re.I),
        ),
        "negative": (
            re.compile(r"\b(?:cut|lower(?:ed|s)?|reduc(?:e|ed|es)|withdraw(?:n|s)?|suspend(?:ed|s)?|miss(?:ed|es)?)\b.{0,45}\b(?:guidance|outlook|forecast)\b", re.I),
            re.compile(r"\b(?:guidance|outlook|forecast)\b.{0,45}\b(?:cut|lowered|reduced|withdrawn|suspended)\b", re.I),
        ),
    },
    "operations": {
        "positive": (
            re.compile(r"\b(?:operations?|production|service)\b.{0,45}\b(?:resum(?:e|ed)|restor(?:e|ed)|reopen(?:ed)?|normal(?:ised|ized))\b", re.I),
            re.compile(r"\b(?:resum(?:e|ed)|restor(?:e|ed)|reopen(?:ed)?)\b.{0,45}\b(?:operations?|production|service)\b", re.I),
        ),
        "negative": (
            re.compile(r"\b(?:operations?|production|service)\b.{0,45}\b(?:halt(?:ed)?|suspend(?:ed)?|shutdown|closed|disrupt(?:ed|ion))\b", re.I),
            re.compile(r"\b(?:halt(?:ed)?|suspend(?:ed)?|shutdown|closure)\b.{0,45}\b(?:operations?|production|service)\b", re.I),
        ),
    },
    "clinical": {
        "positive": (
            re.compile(r"\b(?:met|achieved|reached)\b.{0,35}\bprimary endpoint\b", re.I),
            re.compile(r"\bprimary endpoint\b.{0,35}\b(?:met|achieved|statistically significant)\b", re.I),
        ),
        "negative": (
            re.compile(r"\b(?:missed|failed|did not meet|not met)\b.{0,35}\bprimary endpoint\b", re.I),
            re.compile(r"\bprimary endpoint\b.{0,35}\b(?:missed|failed|not met)\b", re.I),
        ),
    },
    "regulatory": {
        "positive": (
            re.compile(r"\b(?:approved|approval granted|clearance granted|clinical hold lifted)\b", re.I),
        ),
        "negative": (
            re.compile(r"\b(?:complete response letter|clinical hold|rejected|denied|refuse(?:d)? to file)\b", re.I),
        ),
    },
    "financing": {
        "positive": (
            re.compile(r"\b(?:no warrants?|without warrants?|no convertible securities|fully funded|non-dilutive)\b", re.I),
        ),
        "negative": (
            re.compile(r"\b(?:warrants?|convertible securities|deep(?:ly)? discounted|material dilution|toxic financing)\b", re.I),
        ),
    },
    "solvency": {
        "positive": (
            re.compile(r"\b(?:sufficient liquidity|no substantial doubt|fully funded through|debt covenant compliance)\b", re.I),
        ),
        "negative": (
            re.compile(r"\b(?:going concern|substantial doubt|chapter 11|bankruptcy|debt default|covenant breach)\b", re.I),
        ),
    },
}
RESOLUTION_FAMILIES = {"operations", "regulatory"}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _article_text(article: dict[str, Any]) -> str:
    primary = article.get("primary_evidence") if isinstance(article.get("primary_evidence"), dict) else {}
    return "\n".join(
        str(value or "")
        for value in (
            article.get("headline"),
            article.get("summary"),
            primary.get("summary"),
            primary.get("content_excerpt"),
        )
    ).lower()


def _source_key(article: dict[str, Any]) -> str:
    authority = str(article.get("source_authority") or article.get("source") or "").strip().lower()
    if authority:
        return authority[:120]
    host = urlparse(str(article.get("url") or "")).hostname or "unknown"
    return host.lower()


def _source_authority(article: dict[str, Any]) -> float:
    if article.get("is_primary_evidence") is True:
        metadata = ((article.get("primary_evidence") or {}).get("metadata") or {})
        return 2.2 if metadata.get("context_only") else 3.0
    source = str(article.get("source") or "").lower()
    if any(token in source for token in ("reuters", "bloomberg", "associated press", "dow jones")):
        return 2.2
    if any(token in source for token in ("company ir", "investor relations", "business wire", "globenewswire")):
        return 2.0
    if source:
        return 1.2
    return 0.7


def _profile_family(analysis: dict[str, Any]) -> str:
    profile = str(
        analysis.get("event_taxonomy_primary")
        or analysis.get("event_profile")
        or analysis.get("catalyst_type")
        or "unknown"
    ).lower()
    for family, tokens in EVENT_FAMILIES.items():
        if any(token in profile for token in tokens):
            return family
    return "unknown"


def classify_evidence_relevance(
    articles: list[dict[str, Any]],
    analysis: dict[str, Any],
    cutoff: datetime | None,
) -> dict[str, Any]:
    family = _profile_family(analysis)
    keywords = FAMILY_KEYWORDS.get(family, ())
    items: list[dict[str, Any]] = []
    causal_sources: set[str] = set()
    high_quality_sources: set[str] = set()
    causal_primary = 0
    causal_secondary = 0
    for article in articles:
        if not isinstance(article, dict):
            continue
        text = _article_text(article)
        created = _parse_ts(article.get("created_at"))
        age_hours = (
            max(0.0, (cutoff - created).total_seconds() / 3600.0)
            if cutoff is not None and created is not None and created <= cutoff
            else None
        )
        primary = article.get("is_primary_evidence") is True
        primary_meta = ((article.get("primary_evidence") or {}).get("metadata") or {})
        context_only = bool(primary_meta.get("context_only"))
        matches = [keyword for keyword in keywords if keyword in text]
        if matches and not context_only and (age_hours is None or age_hours <= 96):
            relevance = "causal"
        elif matches:
            relevance = "supporting"
        else:
            relevance = "context"
        authority = _source_authority(article)
        source = _source_key(article)
        if relevance == "causal":
            causal_sources.add(source)
            if primary:
                causal_primary += 1
            else:
                causal_secondary += 1
        if authority >= 2.0 and relevance in {"causal", "supporting"}:
            high_quality_sources.add(source)
        items.append(
            {
                "id": article.get("id"),
                "headline": article.get("headline"),
                "source": source,
                "source_authority": authority,
                "is_primary": primary,
                "context_only": context_only,
                "age_hours": round(age_hours, 2) if age_hours is not None else None,
                "event_family": family,
                "matched_terms": matches[:8],
                "relevance": relevance,
            }
        )
    return {
        "event_family": family,
        "items": items,
        "causal_primary_count": causal_primary,
        "causal_secondary_count": causal_secondary,
        "causal_independent_sources": len(causal_sources),
        "high_quality_independent_sources": len(high_quality_sources),
        "causal_evidence_available": bool(causal_sources),
    }


def detect_claim_contradictions(articles: list[dict[str, Any]]) -> dict[str, Any]:
    claims: dict[str, dict[str, list[dict[str, Any]]]] = {
        family: {"positive": [], "negative": []} for family in CLAIM_PATTERNS
    }
    for article in articles:
        if not isinstance(article, dict):
            continue
        text = _article_text(article)
        created = _parse_ts(article.get("created_at"))
        authority = _source_authority(article)
        for family, sides in CLAIM_PATTERNS.items():
            for side, patterns in sides.items():
                if any(pattern.search(text) for pattern in patterns):
                    claims[family][side].append(
                        {
                            "id": article.get("id"),
                            "headline": article.get("headline"),
                            "source": _source_key(article),
                            "created_at": created.isoformat() if created else None,
                            "timestamp": created,
                            "authority": authority,
                            "is_primary": article.get("is_primary_evidence") is True,
                        }
                    )
    unresolved: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for family, sides in claims.items():
        if not sides["positive"] or not sides["negative"]:
            continue
        latest_positive = max(
            sides["positive"], key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=UTC)
        )
        latest_negative = max(
            sides["negative"], key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=UTC)
        )
        positive_ts = latest_positive.get("timestamp")
        negative_ts = latest_negative.get("timestamp")
        if (
            family in RESOLUTION_FAMILIES
            and positive_ts is not None
            and negative_ts is not None
            and positive_ts > negative_ts
            and (positive_ts - negative_ts).total_seconds() >= 900
        ):
            resolved.append(
                {
                    "family": family,
                    "resolution": "later_positive_resolution",
                    "positive": {key: value for key, value in latest_positive.items() if key != "timestamp"},
                    "negative": {key: value for key, value in latest_negative.items() if key != "timestamp"},
                }
            )
            continue
        minimum_authority = min(
            max(item["authority"] for item in sides["positive"]),
            max(item["authority"] for item in sides["negative"]),
        )
        unresolved.append(
            {
                "family": family,
                "positive": [{key: value for key, value in item.items() if key != "timestamp"} for item in sides["positive"][:4]],
                "negative": [{key: value for key, value in item.items() if key != "timestamp"} for item in sides["negative"][:4]],
                "minimum_side_authority": minimum_authority,
                "primary_on_both_sides": any(item["is_primary"] for item in sides["positive"])
                and any(item["is_primary"] for item in sides["negative"]),
            }
        )
    severity = 0.0
    for item in unresolved:
        severity += 24.0 + 8.0 * max(0.0, float(item["minimum_side_authority"]) - 1.0)
        if item["primary_on_both_sides"]:
            severity += 12.0
    if len(unresolved) > 1:
        severity += 10.0
    return {
        "severity": round(_clamp(severity), 1),
        "unresolved_count": len(unresolved),
        "resolved_sequence_count": len(resolved),
        "unresolved": unresolved,
        "resolved_sequences": resolved,
    }


def estimate_execution_friction(candidate: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    spread = max(0.0, _num(candidate.get("spread_pct")) or 0.0)
    dollar_volume = max(0.0, _num(candidate.get("prev_dollar_volume")) or 0.0)
    _trace, raw = (analysis.get("fundamental_trace") or {}, {})
    if isinstance(analysis.get("fundamental_trace"), dict):
        raw = analysis["fundamental_trace"].get("raw_metrics") or {}
    market_cap = _num(raw.get("market_cap"))
    if dollar_volume >= 100_000_000:
        one_way_slippage = 0.08
    elif dollar_volume >= 25_000_000:
        one_way_slippage = 0.15
    elif dollar_volume >= 5_000_000:
        one_way_slippage = 0.30
    elif dollar_volume >= 2_000_000:
        one_way_slippage = 0.55
    elif dollar_volume >= 500_000:
        one_way_slippage = 0.90
    else:
        one_way_slippage = 1.50
    if market_cap is not None and market_cap < 25_000_000:
        one_way_slippage += 0.35
    elif market_cap is not None and market_cap < 75_000_000:
        one_way_slippage += 0.18
    round_trip = spread + 2.0 * one_way_slippage
    return {
        "spread_pct": round(spread, 3),
        "one_way_slippage_proxy_pct": round(one_way_slippage, 3),
        "estimated_round_trip_friction_pct": round(round_trip, 3),
        "previous_dollar_volume": dollar_volume,
        "market_cap": market_cap,
        "method": "quoted spread plus two volume/microcap slippage proxies; conservative ranking input, not an execution quote",
    }


def _confidence_cap(relevance: dict[str, Any], cause_status: str) -> float:
    if cause_status == "CONFLICTING":
        return 42.0
    if cause_status == "UNVERIFIED":
        return 45.0
    if relevance["causal_primary_count"] >= 1 and relevance["causal_independent_sources"] >= 2:
        return 95.0
    if relevance["causal_primary_count"] >= 1:
        return 86.0
    if relevance["high_quality_independent_sources"] >= 2:
        return 80.0
    if relevance["high_quality_independent_sources"] == 1:
        return 68.0
    if relevance["causal_independent_sources"] >= 2:
        return 65.0
    return 52.0


def _scenario_score(
    module: Any,
    *,
    values: dict[str, float],
    confidence: float,
    tail_risk: float,
    cause_status: str,
    damage: float,
    critical_fundamentals_missing: bool,
    hard_veto: bool,
    analysis: dict[str, Any],
    price_context: dict[str, Any],
    external_cap: float,
) -> float:
    raw = module._geometric(values, module.SCORING_CONFIG["v3_3"]["weights"])
    confidence_multiplier = 0.35 + 0.65 * (_clamp(confidence) / 100.0)
    adjusted = raw * confidence_multiplier
    tail_penalty = min(24.0, max(0.0, tail_risk - 40.0) * 0.35)
    pre_cap = module._clamp(adjusted - tail_penalty)
    capped, cap, _caps = module._cap_score(
        pre_cap,
        cause_status=cause_status,
        damage=damage,
        tail_risk=tail_risk,
        critical_fundamentals_missing=critical_fundamentals_missing,
        hard_veto=hard_veto,
        analysis=analysis,
        price_context=price_context,
    )
    return round(min(capped, cap, external_cap), 2)


def reliability_scenarios(module: Any, candidate: dict[str, Any], result: dict[str, Any], articles: list[dict[str, Any]]) -> dict[str, Any]:
    analysis = result.get("catalyst_analysis") if isinstance(result.get("catalyst_analysis"), dict) else {}
    cutoff = _parse_ts(candidate.get("evidence_cutoff") or candidate.get("latest_trade_ts"))
    relevance = classify_evidence_relevance(articles, analysis, cutoff)
    contradictions = detect_claim_contradictions(articles)
    cause_status = str(analysis.get("cause_verification_status") or "UNVERIFIED")
    if contradictions["severity"] >= 60:
        cause_status = "CONFLICTING"
    base_confidence = _clamp(_num(result.get("evidence_confidence")) or 0.0)
    cap = _confidence_cap(relevance, cause_status)
    contradiction_deduction = min(25.0, contradictions["severity"] * 0.18)
    adjusted_confidence = _clamp(min(base_confidence, cap) - contradiction_deduction)

    component_values = dict(((result.get("calculation_trace") or {}).get("v3_3") or {}).get("component_scores") or {})
    values = {
        "overreaction": _clamp(_num(component_values.get("overreaction")) or _num(analysis.get("overreaction_quality_score")) or 0.0),
        "reversibility": _clamp(_num(component_values.get("reversibility")) or _num(analysis.get("reversibility_score")) or result.get("catalyst_score") or 0.0),
        "survivability": _clamp(_num(component_values.get("survivability")) or _num(analysis.get("survivability_score")) or 0.0),
        "three_session_fit": _clamp(_num(component_values.get("three_session_fit")) or _num(analysis.get("three_session_fit_score")) or 0.0),
        "confirmation": _clamp(_num(component_values.get("confirmation")) or result.get("confirmation_score") or 0.0),
        "technical_exhaustion": _clamp(_num(component_values.get("technical_exhaustion")) or result.get("setup_score") or 0.0),
    }
    tail_risk = _clamp(_num(analysis.get("tail_risk_score")) or result.get("damage_risk") or 0.0)
    damage = _clamp(_num(result.get("damage_risk")) or 0.0)
    fundamental_trace = analysis.get("fundamental_trace") if isinstance(analysis.get("fundamental_trace"), dict) else {}
    coverage = int(fundamental_trace.get("metric_coverage_count") or 0)
    fundamentals_available = bool(fundamental_trace.get("available") and coverage > 0)
    critical_missing = bool(analysis.get("critical_fundamentals_required")) and not fundamentals_available
    price_context = analysis.get("price_session_context") if isinstance(analysis.get("price_session_context"), dict) else {}
    friction = estimate_execution_friction(candidate, analysis)
    market_cap = _num(friction.get("market_cap"))

    external_cap = 100.0
    if contradictions["severity"] >= 75:
        external_cap = min(external_cap, 30.0)
    elif contradictions["severity"] >= 50:
        external_cap = min(external_cap, 50.0)
    if market_cap is not None and market_cap < 25_000_000:
        external_cap = min(external_cap, 40.0)
    elif market_cap is not None and market_cap < 75_000_000:
        external_cap = min(external_cap, 65.0)

    uncertainty_base = max(3.0, (100.0 - adjusted_confidence) * 0.18)
    cause_uncertainty = 0.0 if cause_status == "VERIFIED" else 8.0 if cause_status == "PARTIALLY_VERIFIED" else 16.0
    contradiction_uncertainty = contradictions["severity"] * 0.10
    extended_uncertainty = 8.0 if price_context.get("extended_hours_only") else 0.0
    financial_uncertainty = 20.0 if not fundamentals_available else max(4.0, 14.0 - min(10, coverage))
    if market_cap is not None and market_cap < 75_000_000:
        financial_uncertainty += 5.0
    uncertainty = {
        "overreaction": min(30.0, uncertainty_base + cause_uncertainty + contradiction_uncertainty + extended_uncertainty),
        "reversibility": min(30.0, uncertainty_base + cause_uncertainty + contradiction_uncertainty),
        "survivability": min(30.0, uncertainty_base + financial_uncertainty),
        "three_session_fit": min(25.0, uncertainty_base + (8.0 if relevance["event_family"] == "unknown" else 2.0)),
        "confirmation": min(22.0, uncertainty_base + extended_uncertainty),
        "technical_exhaustion": min(12.0, uncertainty_base * 0.55),
    }

    def changed(deltas: dict[str, float]) -> dict[str, float]:
        return {key: _clamp(value + deltas.get(key, 0.0)) for key, value in values.items()}

    scenarios: dict[str, dict[str, Any]] = {
        "base_reliable": {"values": values, "confidence": adjusted_confidence, "tail": tail_risk},
        "evidence_downside": {
            "values": changed({"overreaction": -uncertainty["overreaction"], "reversibility": -uncertainty["reversibility"]}),
            "confidence": max(0.0, adjusted_confidence - 10.0),
            "tail": min(100.0, tail_risk + contradictions["severity"] * 0.10),
        },
        "financial_downside": {
            "values": changed({"survivability": -uncertainty["survivability"]}),
            "confidence": adjusted_confidence,
            "tail": min(100.0, tail_risk + max(8.0, uncertainty["survivability"] * 0.65)),
        },
        "timing_downside": {
            "values": changed({"three_session_fit": -uncertainty["three_session_fit"], "confirmation": -uncertainty["confirmation"]}),
            "confidence": adjusted_confidence,
            "tail": min(100.0, tail_risk + 5.0),
        },
        "joint_downside": {
            "values": changed({key: -value * 0.65 for key, value in uncertainty.items()}),
            "confidence": max(0.0, adjusted_confidence - 10.0),
            "tail": min(100.0, tail_risk + 12.0),
        },
        "modest_upside": {
            "values": changed({key: value * 0.35 for key, value in uncertainty.items()}),
            "confidence": adjusted_confidence,
            "tail": max(0.0, tail_risk - 5.0),
        },
    }
    for scenario in scenarios.values():
        scenario["score"] = _scenario_score(
            module,
            values=scenario["values"],
            confidence=scenario["confidence"],
            tail_risk=scenario["tail"],
            cause_status=cause_status,
            damage=damage,
            critical_fundamentals_missing=critical_missing,
            hard_veto=bool(result.get("hard_veto")),
            analysis=analysis,
            price_context=price_context,
            external_cap=external_cap,
        )
    downside_names = ["base_reliable", "evidence_downside", "financial_downside", "timing_downside", "joint_downside"]
    downside_scores = sorted(float(scenarios[name]["score"]) for name in downside_names)
    conservative_before_cost = sum(downside_scores[:2]) / 2.0
    friction_penalty = min(15.0, float(friction["estimated_round_trip_friction_pct"]) * 4.0)
    conservative_score = round(max(0.0, conservative_before_cost - friction_penalty), 1)
    score_range = max(float(item["score"]) for item in scenarios.values()) - min(float(item["score"]) for item in scenarios.values())
    stability = round(max(0.0, 100.0 - score_range * 2.0), 1)

    scenario_passes = 0
    for name in downside_names:
        scenario = scenarios[name]
        scenario_values = scenario["values"]
        if (
            scenario["score"] >= 72.0
            and scenario_values["overreaction"] >= 60.0
            and scenario_values["survivability"] >= 55.0
            and scenario_values["three_session_fit"] >= 55.0
            and scenario["tail"] <= 60.0
        ):
            scenario_passes += 1
    stress_pass_rate = round(scenario_passes / len(downside_names), 3)
    return {
        "version": RELIABILITY_VERSION,
        "base_v33_score": float(result.get("final_score") or 0.0),
        "adjusted_evidence_confidence": round(adjusted_confidence, 1),
        "evidence_confidence_cap": round(cap, 1),
        "evidence_relevance": relevance,
        "contradictions": contradictions,
        "execution_friction": friction,
        "component_uncertainty": {key: round(value, 2) for key, value in uncertainty.items()},
        "scenarios": scenarios,
        "conservative_before_cost": round(conservative_before_cost, 2),
        "execution_friction_penalty": round(friction_penalty, 2),
        "conservative_score": conservative_score,
        "stability_score": stability,
        "scenario_score_range": round(score_range, 2),
        "stress_gate_pass_rate": stress_pass_rate,
        "external_cap": external_cap,
        "cause_status_after_contradictions": cause_status,
    }


def patch_module(module: Any) -> None:
    if getattr(module, "_v34_reliability_installed", False):
        return
    original_score = module.score_candidate
    original_contract = module.public_scoring_contract

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
    module.SCORING_CONFIG["v3_4"] = {
        "ranking_score": "conservative scenario score after execution-friction penalty",
        "scenario_method": "mean of two lowest base/downside scenario scores",
        "minimum_stability_score": 70.0,
        "minimum_stress_gate_pass_rate": 0.60,
        "maximum_round_trip_friction_pct": 1.50,
        "extreme_microcap_market_cap": 25_000_000.0,
        "contradiction_investigate_ceiling": 50.0,
    }

    def score_candidate(
        candidate: dict[str, Any],
        articles: list[dict[str, Any]],
        catalyst_class: str,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        result = original_score(candidate, articles, catalyst_class, risk_flags)
        reliability = reliability_scenarios(module, candidate, result, articles)
        analysis = result.setdefault("catalyst_analysis", {})
        base_gates = dict(analysis.get("eligibility_gates") or {})
        contradiction = reliability["contradictions"]
        relevance = reliability["evidence_relevance"]
        friction = reliability["execution_friction"]
        market_cap = _num(friction.get("market_cap"))
        reliable_cause = reliability["cause_status_after_contradictions"]
        evidence_independence = (
            relevance["causal_primary_count"] >= 1
            or relevance["high_quality_independent_sources"] >= 2
            or relevance["causal_independent_sources"] >= 2
        )
        reliability_gates = {
            "conservative_opportunity_threshold": reliability["conservative_score"] >= 72.0,
            "score_stability": reliability["stability_score"] >= 70.0,
            "stress_gate_pass_rate": reliability["stress_gate_pass_rate"] >= 0.60,
            "no_material_evidence_contradiction": contradiction["severity"] < 50.0,
            "causal_evidence_independence": evidence_independence,
            "execution_friction": friction["estimated_round_trip_friction_pct"] <= 1.50,
            "not_extreme_microcap": market_cap is None or market_cap >= 25_000_000.0,
        }
        gates = {**base_gates, **reliability_gates}
        failed = [name for name, passed in gates.items() if not passed]
        severe = (
            bool(result.get("hard_veto"))
            or (_num(analysis.get("tail_risk_score")) or 0.0) >= 90.0
            or (_num(result.get("damage_risk")) or 0.0) >= 80.0
            or reliable_cause == "CONFLICTING" and contradiction["severity"] >= 75.0
        )
        score = float(reliability["conservative_score"])
        if severe or score < 40.0:
            verdict = "PASS"
        elif all(gates.values()):
            verdict = "INVESTIGATE"
        elif score >= 48.0 and contradiction["severity"] < 75.0:
            verdict = "WATCH"
        else:
            verdict = "PASS"

        analysis.update(
            {
                "cause_verification_status": reliable_cause,
                "evidence_confidence_before_reliability": result.get("evidence_confidence"),
                "reliability_assessment": reliability,
                "reliability_version": RELIABILITY_VERSION,
                "reliability_stability_score": reliability["stability_score"],
                "reliability_stress_gate_pass_rate": reliability["stress_gate_pass_rate"],
                "estimated_round_trip_friction_pct": friction["estimated_round_trip_friction_pct"],
                "primary_causal_evidence_count": relevance["causal_primary_count"],
                "independent_causal_source_count": relevance["causal_independent_sources"],
                "evidence_contradiction_severity": contradiction["severity"],
                "eligibility_gates": gates,
                "failed_eligibility_gates": failed,
                "analysis_method": "rules_v3_4_point_in_time_scenario_stress",
            }
        )
        trace = result.setdefault("calculation_trace", {})
        trace["v3_4_reliability"] = reliability
        trace["formula"] = (
            "v3.4: v3.3 opportunity components -> evidence relevance/contradiction confidence cap -> "
            "deterministic evidence, financial, timing and joint downside scenarios -> mean of two "
            "lowest scenario scores -> execution-friction penalty -> reliability and economic gates"
        )
        trace["final"] = {
            "base_v33_score": reliability["base_v33_score"],
            "conservative_score": score,
            "stability_score": reliability["stability_score"],
            "stress_gate_pass_rate": reliability["stress_gate_pass_rate"],
            "execution_friction_pct": friction["estimated_round_trip_friction_pct"],
            "verdict": verdict,
            "eligibility_gates": gates,
            "failed_eligibility_gates": failed,
        }
        result.update(
            {
                "scoring_model_version": SCORING_MODEL_VERSION,
                "scoring_config_version": SCORING_CONFIG_VERSION,
                "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
                "calibration_model_version": None,
                "model_status": "uncalibrated",
                "evidence_confidence": reliability["adjusted_evidence_confidence"],
                "confidence_adjusted_score": reliability["conservative_before_cost"],
                "pre_cap_score": reliability["conservative_before_cost"],
                "damage_penalty": round(
                    float(result.get("damage_penalty") or 0.0)
                    + float(reliability["execution_friction_penalty"]),
                    2,
                ),
                "damage_cap": min(float(result.get("damage_cap") or 100.0), float(reliability["external_cap"])),
                "final_score": score,
                "verdict": verdict,
                "explanation": (
                    f"Conservative opportunity {score:.1f}/100 from v3.3 base "
                    f"{reliability['base_v33_score']:.1f}; stability {reliability['stability_score']:.0f}, "
                    f"stress pass rate {reliability['stress_gate_pass_rate'] * 100:.0f}%, "
                    f"estimated friction {friction['estimated_round_trip_friction_pct']:.2f}%, "
                    f"contradiction severity {contradiction['severity']:.0f}. "
                    + (
                        "All reliability and economic gates passed."
                        if verdict == "INVESTIGATE"
                        else f"{verdict}: failed gates include {', '.join(failed[:6]) or 'score threshold'}."
                    )
                ),
            }
        )
        return result

    def public_scoring_contract() -> dict[str, Any]:
        contract = deepcopy(original_contract())
        contract.update(
            {
                "model_status": "uncalibrated",
                "versions": module.SCORING_CONFIG["versions"],
                "score_semantics": {
                    "name": "Conservative Opportunity Score",
                    "range": "0-100",
                    "calibrated_probability": False,
                    "meaning": "lower-confidence scenario estimate after execution-cost and asymmetric-risk controls",
                },
                "reliability_architecture": deepcopy(module.SCORING_CONFIG["v3_4"]),
                "ranking_rule": "rank by v3.4 conservative score, not the optimistic/base point estimate",
                "new_reliability_gates": [
                    "stable across deterministic downside scenarios",
                    "sufficient stress-scenario gate pass rate",
                    "no material unresolved evidence contradiction",
                    "causal evidence independence",
                    "estimated round-trip friction at most 1.5%",
                    "no extreme sub-$25m market-cap risk when market cap is available",
                ],
            }
        )
        return contract

    module.score_candidate = score_candidate
    module.public_scoring_contract = public_scoring_contract
    module._v34_reliability_installed = True
