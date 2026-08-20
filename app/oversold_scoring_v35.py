from __future__ import annotations

"""Oversold Reversion Score v3.5: robust lower-bound opportunity quality.

v3.4 introduced deterministic downside scenarios but ranked on the mean of its two
worst scenario scores. That is safe, yet it can turn a decision system into a
universal rejection system. v3.5 keeps every economic and structural gate, then
adds four reliability controls:

* provenance clusters, so syndicated copies are not counted as independent proof;
* event/cutoff alignment, so stale context cannot masquerade as the sell-off cause;
* event-specific fundamental-data quality, not merely a count of populated fields;
* a deterministic ensemble across plausible weight sets and uncertainty scenarios.

The ranking score is the lower quartile of that ensemble after execution friction
and hard economic caps. The minimum/worst scenario remains visible, but does not
alone define the score. This is a robustness estimate, not a calibrated probability.
"""

import math
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_5"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v7"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3_5"
ROBUSTNESS_VERSION = "robust_weight_evidence_ensemble_v1"

V34_RELIABILITY_GATES = {
    "conservative_opportunity_threshold",
    "score_stability",
    "stress_gate_pass_rate",
    "no_material_evidence_contradiction",
    "causal_evidence_independence",
    "execution_friction",
    "not_extreme_microcap",
}
STOPWORDS = {
    "about", "after", "also", "announced", "before", "being", "company", "could",
    "from", "have", "into", "more", "said", "shares", "stock", "that", "their",
    "there", "they", "this", "through", "today", "under", "which", "with", "would",
    "form", "filed", "filing", "report", "reports", "inc", "corp", "corporation",
}
WEIGHT_SETS: dict[str, dict[str, float]] = {
    "balanced": {
        "overreaction": 0.28,
        "reversibility": 0.22,
        "survivability": 0.20,
        "three_session_fit": 0.15,
        "confirmation": 0.10,
        "technical_exhaustion": 0.05,
    },
    "economic_damage_focus": {
        "overreaction": 0.31,
        "reversibility": 0.22,
        "survivability": 0.24,
        "three_session_fit": 0.13,
        "confirmation": 0.07,
        "technical_exhaustion": 0.03,
    },
    "survival_focus": {
        "overreaction": 0.24,
        "reversibility": 0.18,
        "survivability": 0.31,
        "three_session_fit": 0.14,
        "confirmation": 0.09,
        "technical_exhaustion": 0.04,
    },
    "reversibility_focus": {
        "overreaction": 0.25,
        "reversibility": 0.30,
        "survivability": 0.20,
        "three_session_fit": 0.14,
        "confirmation": 0.08,
        "technical_exhaustion": 0.03,
    },
    "timing_focus": {
        "overreaction": 0.24,
        "reversibility": 0.19,
        "survivability": 0.18,
        "three_session_fit": 0.27,
        "confirmation": 0.09,
        "technical_exhaustion": 0.03,
    },
    "confirmation_focus": {
        "overreaction": 0.25,
        "reversibility": 0.20,
        "survivability": 0.19,
        "three_session_fit": 0.15,
        "confirmation": 0.17,
        "technical_exhaustion": 0.04,
    },
    "technical_light": {
        "overreaction": 0.30,
        "reversibility": 0.24,
        "survivability": 0.22,
        "three_session_fit": 0.15,
        "confirmation": 0.07,
        "technical_exhaustion": 0.02,
    },
}
SCENARIO_NAMES = (
    "base_reliable",
    "evidence_downside",
    "financial_downside",
    "timing_downside",
    "joint_downside",
)
EVENT_CRITICAL_METRICS: dict[str, tuple[str, ...]] = {
    "financing": (
        "cash_to_assets", "liabilities_to_assets", "equity_to_assets", "debt_to_assets",
        "current_ratio", "cash_runway_months", "diluted_shares_yoy",
    ),
    "solvency": (
        "cash_to_assets", "liabilities_to_assets", "equity_to_assets", "debt_to_assets",
        "current_ratio", "cash_runway_months", "operating_cash_flow",
    ),
    "clinical": (
        "cash_to_assets", "liabilities_to_assets", "debt_to_assets", "current_ratio",
        "cash_runway_months", "diluted_shares_yoy",
    ),
    "regulatory": (
        "cash_to_assets", "liabilities_to_assets", "debt_to_assets", "current_ratio",
        "cash_runway_months",
    ),
    "earnings": (
        "revenue_yoy", "net_margin", "operating_margin", "cash_to_assets",
        "liabilities_to_assets", "operating_cash_flow",
    ),
    "operations": (
        "cash_to_assets", "liabilities_to_assets", "current_ratio", "cash_runway_months",
    ),
    "legal": (
        "cash_to_assets", "liabilities_to_assets", "current_ratio", "cash_runway_months",
    ),
    "transaction": ("cash_to_assets", "liabilities_to_assets", "equity_to_assets"),
    "analyst": ("cash_to_assets", "liabilities_to_assets", "equity_to_assets"),
    "spike": ("cash_to_assets", "liabilities_to_assets", "equity_to_assets"),
    "unknown": ("cash_to_assets", "liabilities_to_assets", "equity_to_assets"),
}


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


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = _clamp(probability, 0.0, 1.0) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _normalised_tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", str(value or "").lower())
    return {token for token in tokens if token not in STOPWORDS}


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
    )


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _primary_root(article: dict[str, Any]) -> str | None:
    if article.get("is_primary_evidence") is not True:
        return None
    record = article.get("primary_evidence") if isinstance(article.get("primary_evidence"), dict) else {}
    source_kind = str(article.get("source_kind") or record.get("source_kind") or "primary")
    accession = str(record.get("accession_number") or "").strip()
    external_id = str(record.get("external_id") or "").strip()
    content_hash = str(record.get("content_hash") or "").strip()
    root = accession or external_id or content_hash or str(article.get("id") or "")
    return f"{source_kind}:{root}" if root else None


def _authority(article: dict[str, Any]) -> float:
    if article.get("is_primary_evidence") is True:
        metadata = ((article.get("primary_evidence") or {}).get("metadata") or {})
        return 2.2 if metadata.get("context_only") else 3.0
    source = str(article.get("source") or "").lower()
    if any(token in source for token in ("reuters", "bloomberg", "dow jones", "associated press")):
        return 2.2
    if any(token in source for token in ("company ir", "investor relations", "business wire", "globenewswire")):
        return 2.0
    return 1.2 if source else 0.7


def _host(article: dict[str, Any]) -> str:
    return (urlparse(str(article.get("url") or "")).hostname or "unknown").lower()


def evidence_provenance_clusters(
    articles: list[dict[str, Any]],
    relevance: dict[str, Any],
) -> dict[str, Any]:
    relevance_by_id = {
        str(item.get("id")): item
        for item in (relevance.get("items") or [])
        if isinstance(item, dict)
    }
    candidates: list[dict[str, Any]] = []
    for index, article in enumerate(articles):
        if not isinstance(article, dict):
            continue
        item = relevance_by_id.get(str(article.get("id"))) or {}
        if item.get("relevance") != "causal":
            continue
        tokens = _normalised_tokens(_article_text(article))
        candidates.append(
            {
                "index": index,
                "id": article.get("id"),
                "headline": article.get("headline"),
                "source": article.get("source"),
                "host": _host(article),
                "authority": _authority(article),
                "is_primary": article.get("is_primary_evidence") is True,
                "primary_root": _primary_root(article),
                "tokens": tokens,
                "age_hours": _num(item.get("age_hours")),
            }
        )

    clusters: list[dict[str, Any]] = []
    for item in candidates:
        matched: dict[str, Any] | None = None
        for cluster in clusters:
            same_primary = bool(
                item["primary_root"]
                and item["primary_root"] in cluster["primary_roots"]
            )
            similarity = max(
                (_jaccard(item["tokens"], member["tokens"]) for member in cluster["members"]),
                default=0.0,
            )
            headline_similarity = max(
                (
                    _jaccard(
                        _normalised_tokens(str(item.get("headline") or "")),
                        _normalised_tokens(str(member.get("headline") or "")),
                    )
                    for member in cluster["members"]
                ),
                default=0.0,
            )
            if same_primary or similarity >= 0.70 or headline_similarity >= 0.82:
                matched = cluster
                break
        if matched is None:
            matched = {
                "cluster_id": len(clusters) + 1,
                "members": [],
                "primary_roots": set(),
            }
            clusters.append(matched)
        matched["members"].append(item)
        if item["primary_root"]:
            matched["primary_roots"].add(item["primary_root"])

    serialised: list[dict[str, Any]] = []
    for cluster in clusters:
        members = cluster["members"]
        authorities = sorted({str(member.get("source") or member.get("host") or "unknown") for member in members})
        serialised.append(
            {
                "cluster_id": cluster["cluster_id"],
                "article_ids": [member.get("id") for member in members],
                "headlines": [member.get("headline") for member in members],
                "sources": authorities,
                "article_count": len(members),
                "is_primary": any(member["is_primary"] for member in members),
                "maximum_authority": max((member["authority"] for member in members), default=0.0),
                "minimum_age_hours": min(
                    (member["age_hours"] for member in members if member["age_hours"] is not None),
                    default=None,
                ),
                "primary_roots": sorted(cluster["primary_roots"]),
            }
        )

    count = len(serialised)
    primary_clusters = sum(1 for cluster in serialised if cluster["is_primary"])
    high_quality_clusters = sum(1 for cluster in serialised if cluster["maximum_authority"] >= 2.0)
    dependency_risk = 100.0 if count == 0 else 85.0 if count == 1 else 45.0 if count == 2 else 20.0 if count == 3 else 5.0
    confidence_cap = (
        45.0
        if count == 0
        else 78.0 if count == 1 and primary_clusters else 62.0 if count == 1
        else 92.0 if count >= 2 and primary_clusters else 82.0 if count >= 2 and high_quality_clusters >= 2
        else 70.0
    )
    if count >= 3 and primary_clusters:
        confidence_cap = 96.0
    return {
        "clusters": serialised,
        "causal_cluster_count": count,
        "primary_causal_cluster_count": primary_clusters,
        "high_quality_causal_cluster_count": high_quality_clusters,
        "leave_one_cluster_out_minimum": max(0, count - 1),
        "single_cluster_dependency_risk": dependency_risk,
        "cluster_confidence_cap": confidence_cap,
        "independence_rule": "near-duplicate and common primary-root evidence counts as one provenance cluster",
    }


def event_alignment_quality(clusters: dict[str, Any]) -> dict[str, Any]:
    scores: list[float] = []
    ages: list[float] = []
    for cluster in clusters.get("clusters") or []:
        age = _num(cluster.get("minimum_age_hours"))
        if age is None:
            continue
        ages.append(age)
        if age <= 6:
            value = 100.0
        elif age <= 18:
            value = 92.0
        elif age <= 36:
            value = 80.0
        elif age <= 72:
            value = 60.0
        elif age <= 96:
            value = 40.0
        else:
            value = 20.0
        if cluster.get("is_primary"):
            value = min(100.0, value + 5.0)
        scores.append(value)
    if not scores:
        return {
            "score": 0.0,
            "nearest_causal_age_hours": None,
            "causal_clusters_with_timestamp": 0,
            "rule": "no cutoff-valid causal cluster timestamp",
        }
    nearest = min(ages)
    score = max(scores)
    if len([value for value in scores if value >= 80]) >= 2:
        score = min(100.0, score + 4.0)
    return {
        "score": round(score, 1),
        "nearest_causal_age_hours": round(nearest, 2),
        "causal_clusters_with_timestamp": len(scores),
        "rule": "causal evidence inside 36h is strong; 36-72h is acceptable; older evidence is context unless independently confirmed",
    }


def fundamental_data_quality(analysis: dict[str, Any], event_family: str) -> dict[str, Any]:
    trace = analysis.get("fundamental_trace") if isinstance(analysis.get("fundamental_trace"), dict) else {}
    raw = trace.get("raw_metrics") if isinstance(trace.get("raw_metrics"), dict) else {}
    available = bool(trace.get("available"))
    source = str(trace.get("source") or "")
    age = _num(trace.get("age_calendar_days"))
    total_coverage = int(trace.get("metric_coverage_count") or 0)
    required = EVENT_CRITICAL_METRICS.get(event_family, EVENT_CRITICAL_METRICS["unknown"])
    available_required = [name for name in required if _num(raw.get(name)) is not None]
    coverage_ratio = len(available_required) / len(required) if required else 0.0

    if not available:
        return {
            "score": 0.0,
            "available": False,
            "event_family": event_family,
            "required_metrics": list(required),
            "available_required_metrics": [],
            "required_coverage_ratio": 0.0,
            "source": source or None,
            "age_calendar_days": age,
            "accounting_consistency": None,
        }

    source_points = 20.0 if "sec" in source.lower() else 13.0
    if age is None:
        freshness_points = 7.0
    elif age <= 120:
        freshness_points = 20.0
    elif age <= 240:
        freshness_points = 14.0
    elif age <= 365:
        freshness_points = 8.0
    else:
        freshness_points = 3.0
    coverage_points = coverage_ratio * 40.0
    breadth_points = min(10.0, total_coverage / 10.0 * 10.0)

    assets = _num(raw.get("assets"))
    liabilities = _num(raw.get("liabilities"))
    equity = _num(raw.get("equity"))
    consistency: float | None = None
    if assets is not None and assets != 0 and liabilities is not None and equity is not None:
        consistency = abs(assets - liabilities - equity) / abs(assets)
        consistency_points = 10.0 if consistency <= 0.08 else 6.0 if consistency <= 0.18 else 1.0
    else:
        consistency_points = 5.0
    score = source_points + freshness_points + coverage_points + breadth_points + consistency_points
    return {
        "score": round(_clamp(score), 1),
        "available": True,
        "event_family": event_family,
        "required_metrics": list(required),
        "available_required_metrics": available_required,
        "required_coverage_ratio": round(coverage_ratio, 3),
        "source": source or None,
        "age_calendar_days": age,
        "metric_coverage_count": total_coverage,
        "accounting_consistency": round(consistency, 4) if consistency is not None else None,
    }


def _score_with_weights(
    module: Any,
    *,
    values: dict[str, float],
    weights: dict[str, float],
    confidence: float,
    tail_risk: float,
    result: dict[str, Any],
    analysis: dict[str, Any],
    external_cap: float,
) -> float:
    cause_status = str(analysis.get("cause_verification_status") or "UNVERIFIED")
    damage = _clamp(_num(result.get("damage_risk")) or 0.0)
    fundamental_trace = analysis.get("fundamental_trace") if isinstance(analysis.get("fundamental_trace"), dict) else {}
    critical_missing = bool(analysis.get("critical_fundamentals_required")) and not bool(fundamental_trace.get("available"))
    price_context = analysis.get("price_session_context") if isinstance(analysis.get("price_session_context"), dict) else {}
    raw = module._geometric(values, weights)
    multiplier = 0.35 + 0.65 * (_clamp(confidence) / 100.0)
    adjusted = raw * multiplier
    tail_penalty = min(24.0, max(0.0, tail_risk - 40.0) * 0.35)
    pre_cap = module._clamp(adjusted - tail_penalty)
    capped, cap, _ = module._cap_score(
        pre_cap,
        cause_status=cause_status,
        damage=damage,
        tail_risk=tail_risk,
        critical_fundamentals_missing=critical_missing,
        hard_veto=bool(result.get("hard_veto")),
        analysis=analysis,
        price_context=price_context,
    )
    return round(min(capped, cap, external_cap), 3)


def robust_weight_ensemble(
    module: Any,
    result: dict[str, Any],
    analysis: dict[str, Any],
    robust_confidence: float,
) -> dict[str, Any]:
    reliability = analysis.get("reliability_assessment") if isinstance(analysis.get("reliability_assessment"), dict) else {}
    scenarios = reliability.get("scenarios") if isinstance(reliability.get("scenarios"), dict) else {}
    external_cap = float(reliability.get("external_cap") or 100.0)
    scores: list[float] = []
    rows: list[dict[str, Any]] = []
    base_weight_scores: list[float] = []

    for scenario_name in SCENARIO_NAMES:
        scenario = scenarios.get(scenario_name) if isinstance(scenarios.get(scenario_name), dict) else None
        if scenario is None:
            continue
        values = {
            key: _clamp(_num(value) or 0.0)
            for key, value in (scenario.get("values") or {}).items()
            if key in WEIGHT_SETS["balanced"]
        }
        if len(values) != len(WEIGHT_SETS["balanced"]):
            continue
        confidence = min(robust_confidence, _clamp(_num(scenario.get("confidence")) or robust_confidence))
        tail = _clamp(_num(scenario.get("tail")) or _num(analysis.get("tail_risk_score")) or 0.0)
        for weight_name, weights in WEIGHT_SETS.items():
            score = _score_with_weights(
                module,
                values=values,
                weights=weights,
                confidence=confidence,
                tail_risk=tail,
                result=result,
                analysis=analysis,
                external_cap=external_cap,
            )
            scores.append(score)
            rows.append({"scenario": scenario_name, "weight_set": weight_name, "score": score})
            if scenario_name == "base_reliable":
                base_weight_scores.append(score)

    if not scores:
        fallback = float(result.get("final_score") or 0.0)
        scores = [fallback]
        base_weight_scores = [fallback]
    friction = reliability.get("execution_friction") if isinstance(reliability.get("execution_friction"), dict) else {}
    round_trip = max(0.0, _num(friction.get("estimated_round_trip_friction_pct")) or 0.0)
    friction_penalty = min(12.0, round_trip * 2.5)
    lower_quartile_before_cost = _quantile(scores, 0.25)
    robust_score = max(0.0, lower_quartile_before_cost - friction_penalty)
    base_range = max(base_weight_scores) - min(base_weight_scores) if base_weight_scores else 0.0
    weight_stability = max(0.0, 100.0 - base_range * 3.5)

    base_scenario = scenarios.get("base_reliable") if isinstance(scenarios.get("base_reliable"), dict) else {}
    base_values = {
        key: _clamp(_num(value) or 0.0)
        for key, value in (base_scenario.get("values") or {}).items()
        if key in WEIGHT_SETS["balanced"]
    }
    component_drops: dict[str, float] = {}
    if len(base_values) == len(WEIGHT_SETS["balanced"]):
        full = _score_with_weights(
            module,
            values=base_values,
            weights=WEIGHT_SETS["balanced"],
            confidence=min(robust_confidence, _clamp(_num(base_scenario.get("confidence")) or robust_confidence)),
            tail_risk=_clamp(_num(base_scenario.get("tail")) or _num(analysis.get("tail_risk_score")) or 0.0),
            result=result,
            analysis=analysis,
            external_cap=external_cap,
        )
        for component in base_values:
            reduced_values = {key: value for key, value in base_values.items() if key != component}
            reduced_weights = {key: value for key, value in WEIGHT_SETS["balanced"].items() if key != component}
            total = sum(reduced_weights.values())
            reduced_weights = {key: value / total for key, value in reduced_weights.items()}
            reduced = _score_with_weights(
                module,
                values=reduced_values,
                weights=reduced_weights,
                confidence=min(robust_confidence, _clamp(_num(base_scenario.get("confidence")) or robust_confidence)),
                tail_risk=_clamp(_num(base_scenario.get("tail")) or _num(analysis.get("tail_risk_score")) or 0.0),
                result=result,
                analysis=analysis,
                external_cap=external_cap,
            )
            component_drops[component] = round(max(0.0, full - reduced), 2)
    maximum_component_dependency = max(component_drops.values(), default=0.0)
    return {
        "version": ROBUSTNESS_VERSION,
        "ensemble_member_count": len(scores),
        "weight_set_count": len(WEIGHT_SETS),
        "scenario_count": len({row["scenario"] for row in rows}),
        "lower_quartile_before_cost": round(lower_quartile_before_cost, 2),
        "execution_friction_penalty": round(friction_penalty, 2),
        "robust_lower_score": round(robust_score, 1),
        "ensemble_p10": round(_quantile(scores, 0.10), 2),
        "ensemble_median": round(_quantile(scores, 0.50), 2),
        "ensemble_p75": round(_quantile(scores, 0.75), 2),
        "ensemble_minimum": round(min(scores), 2),
        "ensemble_maximum": round(max(scores), 2),
        "ensemble_range": round(max(scores) - min(scores), 2),
        "base_weight_range": round(base_range, 2),
        "weight_stability_score": round(weight_stability, 1),
        "component_leave_one_out_drops": component_drops,
        "maximum_component_dependency": round(maximum_component_dependency, 2),
        "members": rows,
        "method": "lower quartile across seven economically plausible weight sets and five deterministic base/downside scenarios, less execution friction",
    }


def patch_module(module: Any) -> None:
    if getattr(module, "_v35_robust_ensemble_installed", False):
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
    module.SCORING_CONFIG["v3_5"] = {
        "ranking_score": "lower-quartile robust ensemble score after execution friction and economic caps",
        "weight_sets": deepcopy(WEIGHT_SETS),
        "scenario_names": list(SCENARIO_NAMES),
        "minimum_robust_score": 72.0,
        "minimum_ensemble_median": 75.0,
        "minimum_weight_stability": 70.0,
        "maximum_component_dependency": 15.0,
        "minimum_causal_clusters": 2,
        "minimum_event_alignment": 60.0,
        "minimum_critical_fundamental_quality": 60.0,
    }

    def score_candidate(
        candidate: dict[str, Any],
        articles: list[dict[str, Any]],
        catalyst_class: str,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        result = original_score(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        reliability = analysis.get("reliability_assessment") if isinstance(analysis.get("reliability_assessment"), dict) else {}
        relevance = reliability.get("evidence_relevance") if isinstance(reliability.get("evidence_relevance"), dict) else {}
        clusters = evidence_provenance_clusters(articles, relevance)
        alignment = event_alignment_quality(clusters)
        event_family = str(relevance.get("event_family") or "unknown")
        fundamental_quality = fundamental_data_quality(analysis, event_family)
        robust_confidence = min(
            _clamp(_num(result.get("evidence_confidence")) or 0.0),
            float(clusters["cluster_confidence_cap"]),
        )
        ensemble = robust_weight_ensemble(module, result, analysis, robust_confidence)

        contradiction = reliability.get("contradictions") if isinstance(reliability.get("contradictions"), dict) else {}
        contradiction_severity = _clamp(_num(contradiction.get("severity")) or 0.0)
        friction = reliability.get("execution_friction") if isinstance(reliability.get("execution_friction"), dict) else {}
        friction_pct = max(0.0, _num(friction.get("estimated_round_trip_friction_pct")) or 0.0)
        critical_fundamentals = bool(analysis.get("critical_fundamentals_required"))

        score_caps: list[dict[str, Any]] = []
        score_cap = 100.0

        def apply_cap(name: str, value: float, reason: str) -> None:
            nonlocal score_cap
            score_cap = min(score_cap, value)
            score_caps.append({"type": name, "cap": value, "reason": reason})

        if clusters["causal_cluster_count"] < 2:
            apply_cap("single_or_missing_causal_cluster", 60.0, "a single provenance root cannot establish an INVESTIGATE-grade causal conclusion")
        if alignment["score"] < 40.0:
            apply_cap("stale_or_unaligned_event_evidence", 45.0, "causal evidence is not close enough to the signal")
        elif alignment["score"] < 60.0:
            apply_cap("weak_event_alignment", 65.0, "event timing is only weakly aligned to the sell-off")
        if critical_fundamentals and fundamental_quality["score"] < 40.0:
            apply_cap("critical_financial_evidence_poor", 45.0, "critical event lacks sufficiently current and relevant financial evidence")
        elif critical_fundamentals and fundamental_quality["score"] < 60.0:
            apply_cap("critical_financial_evidence_partial", 60.0, "critical financial evidence is incomplete")
        if ensemble["weight_stability_score"] < 50.0:
            apply_cap("weight_instability", 55.0, "score changes materially across plausible economic weights")
        if ensemble["maximum_component_dependency"] > 20.0:
            apply_cap("single_component_dependency", 60.0, "one component contributes too much of the base conclusion")
        if contradiction_severity >= 75.0:
            apply_cap("severe_evidence_contradiction", 30.0, "authoritative evidence contains unresolved material contradictions")
        elif contradiction_severity >= 50.0:
            apply_cap("material_evidence_contradiction", 50.0, "authoritative evidence contains a material unresolved contradiction")

        score = round(min(float(ensemble["robust_lower_score"]), score_cap), 1)
        old_gates = dict(analysis.get("eligibility_gates") or {})
        economic_gates = {
            name: bool(passed)
            for name, passed in old_gates.items()
            if name not in V34_RELIABILITY_GATES
        }
        independent_clusters = (
            clusters["causal_cluster_count"] >= 2
            and (
                clusters["primary_causal_cluster_count"] >= 1
                or clusters["high_quality_causal_cluster_count"] >= 2
            )
        )
        robust_gates = {
            "robust_opportunity_threshold": score >= 72.0,
            "ensemble_median": ensemble["ensemble_median"] >= 75.0,
            "weight_stability": ensemble["weight_stability_score"] >= 70.0,
            "component_independence": ensemble["maximum_component_dependency"] <= 15.0,
            "causal_provenance_independence": independent_clusters,
            "event_cutoff_alignment": alignment["score"] >= 60.0,
            "critical_fundamental_data_quality": (
                not critical_fundamentals or fundamental_quality["score"] >= 60.0
            ),
            "no_material_evidence_contradiction": contradiction_severity < 50.0,
            "execution_friction": friction_pct <= 1.50,
        }
        gates = {**economic_gates, **robust_gates}
        failed = [name for name, passed in gates.items() if not passed]
        severe = (
            bool(result.get("hard_veto"))
            or (_num(analysis.get("tail_risk_score")) or 0.0) >= 90.0
            or (_num(result.get("damage_risk")) or 0.0) >= 80.0
            or contradiction_severity >= 75.0
        )
        if severe or score < 40.0:
            verdict = "PASS"
        elif all(gates.values()):
            verdict = "INVESTIGATE"
        elif score >= 48.0:
            verdict = "WATCH"
        else:
            verdict = "PASS"

        robustness = {
            "version": ROBUSTNESS_VERSION,
            "evidence_provenance": clusters,
            "event_alignment": alignment,
            "fundamental_data_quality": fundamental_quality,
            "robust_evidence_confidence": round(robust_confidence, 1),
            "ensemble": ensemble,
            "score_caps": score_caps,
            "final_score_cap": round(score_cap, 1),
            "economic_gates_carried_forward": economic_gates,
            "robustness_gates": robust_gates,
        }
        analysis.update(
            {
                "robustness_assessment": robustness,
                "robustness_version": ROBUSTNESS_VERSION,
                "causal_provenance_cluster_count": clusters["causal_cluster_count"],
                "primary_causal_cluster_count": clusters["primary_causal_cluster_count"],
                "source_dependency_risk": clusters["single_cluster_dependency_risk"],
                "event_alignment_score": alignment["score"],
                "fundamental_data_quality_score": fundamental_quality["score"],
                "weight_stability_score": ensemble["weight_stability_score"],
                "maximum_component_dependency": ensemble["maximum_component_dependency"],
                "eligibility_gates": gates,
                "failed_eligibility_gates": failed,
                "analysis_method": "rules_v3_5_point_in_time_robust_ensemble",
            }
        )
        trace = result.setdefault("calculation_trace", {})
        trace["v3_5_robustness"] = robustness
        trace["formula"] = (
            "v3.5: v3.4 point-in-time economic components and uncertainty scenarios -> provenance-cluster "
            "confidence cap -> seven plausible weight sets -> lower-quartile ensemble score -> execution-friction "
            "penalty -> event-alignment, financial-quality, contradiction and structural caps -> robust gates"
        )
        trace["final"] = {
            "base_v34_score": result.get("final_score"),
            "robust_lower_score": score,
            "ensemble_median": ensemble["ensemble_median"],
            "weight_stability_score": ensemble["weight_stability_score"],
            "maximum_component_dependency": ensemble["maximum_component_dependency"],
            "causal_provenance_cluster_count": clusters["causal_cluster_count"],
            "event_alignment_score": alignment["score"],
            "fundamental_data_quality_score": fundamental_quality["score"],
            "score_caps": score_caps,
            "verdict": verdict,
            "eligibility_gates": gates,
            "failed_eligibility_gates": failed,
        }
        base_v34_score = float(result.get("final_score") or 0.0)
        result.update(
            {
                "scoring_model_version": SCORING_MODEL_VERSION,
                "scoring_config_version": SCORING_CONFIG_VERSION,
                "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
                "calibration_model_version": None,
                "model_status": "uncalibrated",
                "evidence_confidence": round(robust_confidence, 1),
                "confidence_adjusted_score": ensemble["lower_quartile_before_cost"],
                "pre_cap_score": ensemble["robust_lower_score"],
                "damage_penalty": round(
                    float(result.get("damage_penalty") or 0.0)
                    + float(ensemble["execution_friction_penalty"]),
                    2,
                ),
                "damage_cap": min(float(result.get("damage_cap") or 100.0), score_cap),
                "final_score": score,
                "verdict": verdict,
                "explanation": (
                    f"Robust opportunity {score:.1f}/100 from v3.4 conservative point {base_v34_score:.1f}; "
                    f"ensemble median {ensemble['ensemble_median']:.1f}, weight stability "
                    f"{ensemble['weight_stability_score']:.0f}, causal clusters "
                    f"{clusters['causal_cluster_count']}, event alignment {alignment['score']:.0f}, "
                    f"fundamental quality {fundamental_quality['score']:.0f}, robust evidence "
                    f"{robust_confidence:.0f}. "
                    + (
                        "All economic and robustness gates passed."
                        if verdict == "INVESTIGATE"
                        else f"{verdict}: failed gates include {', '.join(failed[:7]) or 'score threshold'}."
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
                    "name": "Robust Opportunity Score",
                    "range": "0-100",
                    "calibrated_probability": False,
                    "meaning": "lower-quartile score across plausible economic weights and evidence/financial/timing uncertainty scenarios after costs and hard loss controls",
                },
                "robustness_architecture": deepcopy(module.SCORING_CONFIG["v3_5"]),
                "ranking_rule": "rank by v3.5 robust lower-quartile score; retain median, p10, minimum and v3.4 point estimate for audit",
                "source_independence_rule": "near-duplicate and common-root evidence is one provenance cluster; INVESTIGATE requires at least two independent causal clusters",
                "new_robustness_gates": [
                    "robust score at least 72",
                    "ensemble median at least 75",
                    "stable across plausible weight sets",
                    "not dependent on one model component",
                    "at least two independent causal provenance clusters",
                    "causal evidence aligned to the signal cutoff",
                    "event-specific fundamental-data quality where financially critical",
                    "no material unresolved evidence contradiction",
                    "estimated round-trip friction at most 1.5%",
                ],
            }
        )
        return contract

    module.score_candidate = score_candidate
    module.public_scoring_contract = public_scoring_contract
    module._v35_robust_ensemble_installed = True
