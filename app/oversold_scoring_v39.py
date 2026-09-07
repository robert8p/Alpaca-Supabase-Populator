from __future__ import annotations

"""Auditable deterministic sensitivity, not a distribution of investment returns.

The v3.1--v3.8 implementations and stored original decisions are unchanged.
Thresholds are governance policy, not empirically fitted success probabilities.
"""

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import math
import re
from typing import Any

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_9"
SCORING_CONFIG_VERSION = "or_score_config_2026_09_07_v11"
ROBUSTNESS_VERSION = "auditable_sensitivity_v2"
MAX_SOURCE_REPLAYS = 8
ALIASES = {"opportunity_threshold": "robust_opportunity_threshold",
           "conservative_opportunity_threshold": "robust_opportunity_threshold",
           "causal_evidence_independence": "causal_provenance_independence",
           "score_stability": "weight_stability"}


def number(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo else result.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _text(article: dict) -> str:
    primary = article.get("primary_evidence") or {}
    return " ".join(str(value or "") for value in
                    (article.get("headline"), article.get("summary"), primary.get("summary"), primary.get("content_excerpt")))


def deduplicate_exact(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """Do not discard different claims merely because they share an event root."""
    from app.oversold_scoring_v35 import _authority
    groups: dict[str, list[dict]] = {}
    for article in articles:
        key = re.sub(r"\s+", " ", _text(article)).strip().lower()
        # Empty records must not be treated as corroboration, or merged by content.
        key = key or json.dumps(article, default=str, sort_keys=True)
        groups.setdefault(key, []).append(article)
    retained, removed = [], []
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda a: (-_authority(a), str(a.get("created_at") or ""), str(a.get("id") or "")))
        retained.append(members[0])
        removed.extend({"id": a.get("id"), "representative_id": members[0].get("id"), "reason": "identical_normalized_text"} for a in members[1:])
    return retained, removed


def provenance_clusters(articles: list[dict], relevance: dict) -> dict:
    """Connected components make common-root clustering transitive/order independent.

    Similarity is still a heuristic. Undeclared common sourcing cannot be proved
    independent just because the wording differs; expose this residual limitation.
    """
    from app.oversold_scoring_v35 import _authority, _jaccard, _normalised_tokens
    causal_ids = {str(row.get("id")) for row in relevance.get("items", []) if row.get("relevance") == "causal"}
    rows = sorted([a for a in articles if str(a.get("id")) in causal_ids], key=lambda a: (str(a.get("id")), _text(a)))
    parents = list(range(len(rows)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    def roots(a):
        primary = a.get("primary_evidence") or {}
        metadata = primary.get("metadata") or {}
        return {str(v).strip().lower() for v in (a.get("provenance_root_id"), a.get("origin_url"),
                a.get("accession_number"), primary.get("accession_number"), primary.get("external_id"),
                metadata.get("provenance_root_id"), metadata.get("origin_url")) if v}
    for i, left in enumerate(rows):
        for j in range(i):
            right = rows[j]
            same = bool(roots(left) & roots(right))
            similar = _jaccard(_normalised_tokens(_text(left)), _normalised_tokens(_text(right))) >= .70
            headline = _jaccard(_normalised_tokens(left.get("headline", "")), _normalised_tokens(right.get("headline", ""))) >= .82
            if same or similar or headline:
                parents[root(i)] = root(j)
    groups: dict[int, list[dict]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(root(i), []).append(row)
    clusters = []
    for members in groups.values():
        clusters.append({"cluster_id": len(clusters) + 1, "article_ids": [m.get("id") for m in members],
                         "headlines": [m.get("headline") for m in members], "sources": sorted({str(m.get("source") or "unknown") for m in members}),
                         "urls": sorted({str(m.get("url") or "") for m in members if m.get("url")}),
                         "article_count": len(members), "is_primary": any(m.get("is_primary_evidence") is True for m in members),
                         "maximum_authority": max(_authority(m) for m in members),
                         "primary_roots": sorted(set().union(*(roots(m) for m in members))),
                         "available_at": sorted({str(m.get("created_at")) for m in members})})
    count = len(clusters)
    primary_count = sum(c["is_primary"] for c in clusters)
    return {"clusters": clusters, "causal_cluster_count": count,
            "primary_causal_cluster_count": primary_count,
            "high_quality_causal_cluster_count": sum(c["maximum_authority"] >= 2 for c in clusters),
            "single_cluster_dependency_risk": None,
            "primary_fact_status": "PRIMARY_PRESENT" if primary_count else "NO_PRIMARY_RETAINED",
            "independence_rule": "common declared roots or near-duplicate connected components; distinct wording is not proof of independence",
            "unresolved_origin_risk": "Undeclared shared reporting remains possible; review claim-level provenance."}


def execution_audit(candidate: dict, friction: dict) -> dict:
    quote = (candidate.get("raw_snapshot") or {}).get("latestQuote") or {}
    bid = number(quote.get("bp", candidate.get("bid")))
    ask = number(quote.get("ap", candidate.get("ask")))
    spread = number(candidate.get("spread_pct"))
    volume = number(candidate.get("prev_dollar_volume"))
    cutoff = timestamp(candidate.get("evidence_cutoff") or candidate.get("latest_trade_ts"))
    quoted = timestamp(quote.get("t"))
    age = (cutoff - quoted).total_seconds() if cutoff and quoted else None
    cost = number(friction.get("estimated_round_trip_friction_pct"))
    reasons = []
    if spread is None or spread < 0 or volume is None or volume <= 0 or cost is None or cost < 0:
        reasons.append("missing_or_invalid_spread_volume_cost")
    if (bid is not None or ask is not None) and not (bid is not None and ask is not None and 0 < bid <= ask):
        reasons.append("invalid_or_crossed_quote")
    if bid is not None and ask is not None and 0 < bid <= ask and spread is not None:
        computed = 200 * (ask - bid) / (ask + bid)
        if abs(computed - spread) > max(.05, abs(computed) * .10):
            reasons.append("spread_units_or_quote_mismatch")
    if age is not None and age < 0:
        reasons.append("quote_after_cutoff")
    if spread is not None and spread > 20:
        reasons.append("extreme_spread_requires_quote_corporate_action_check")
    status = "INVALID" if reasons else "PROXY_ONLY"
    if not reasons and bid is not None and ask is not None and age is not None:
        status = "OBSERVED_QUOTE" if age <= 300 else "STALE_QUOTE"
    return {"status": status, "reasons": reasons, "quote_age_seconds": age,
            "quote_timestamp": quoted.isoformat() if quoted else None,
            "estimate_pct": cost, "units": "percentage_points_round_trip",
            "cost_scenarios_pct": {str(multiplier) + "x": round(cost * multiplier, 4) if cost is not None else None for multiplier in (1, 1.5, 2)},
            "scoring_inputs_valid": status not in {"INVALID", "STALE_QUOTE"},
            "live_execution_verified": False,
            "limitation": "Volume-tier slippage proxy, not executable cost. Fees, order size, depth and new entry quote need independent verification."}


def event_context(candidate: dict, articles: list[dict], family: str) -> dict:
    cutoff = timestamp(candidate.get("evidence_cutoff") or candidate.get("latest_trade_ts"))
    event = timestamp(candidate.get("event_timestamp"))
    onset = timestamp(candidate.get("selloff_onset_timestamp"))
    status = "UNKNOWN"
    if event and onset and cutoff:
        status = "TIMESTAMP_ORDER_ONLY" if event <= onset <= cutoff else "CONTRADICTORY_TIMESTAMPS"
    evidence_dates = sorted({str(a.get("created_at")) for a in articles if a.get("created_at")})
    financial = candidate.get("event_financials") or {}
    available = timestamp(financial.get("available_at"))
    event_financial_status = "NOT_QUANTIFIED"
    if available and cutoff and available <= cutoff and financial.get("source") and financial.get("metrics"):
        event_financial_status = "SUPPLIED_REQUIRES_INDEPENDENT_REVIEW"
    return {"signal_cutoff": cutoff.isoformat() if cutoff else None,
            "event_timestamp": event.isoformat() if event else None,
            "selloff_onset_timestamp": onset.isoformat() if onset else None,
            "timing_status": status, "evidence_availability_timestamps": evidence_dates,
            "event_family": family, "event_financial_status": event_financial_status,
            "event_financial_evidence": financial if event_financial_status != "NOT_QUANTIFIED" else None,
            "limitation": "Article age is recency, not event-to-selloff alignment. Accounts coverage is not shock-specific damage quantification. Do not infer elapsed trading sessions from calendar days."}


def audited_ensemble(module: Any, result: dict) -> dict:
    from app.oversold_scoring_v35 import WEIGHT_SETS, SCENARIO_NAMES
    analysis = result.get("catalyst_analysis") or {}
    robustness = analysis.get("robustness_assessment") or {}
    reliability = analysis.get("reliability_assessment") or {}
    scenarios = reliability.get("scenarios") or {}
    confidence = number(robustness.get("robust_evidence_confidence"), 0.0)
    external_cap = number(reliability.get("external_cap"), 100.0)
    score_cap = number(robustness.get("final_score_cap"), 100.0)
    cost = number((reliability.get("execution_friction") or {}).get("estimated_round_trip_friction_pct"))
    penalty = min(12.0, max(0.0, cost) * 2.5) if cost is not None else 0.0
    rows, missing = [], []
    def evaluate(values, weights, conf, tail):
        raw = module._geometric(values, weights) * (.35 + .65 * conf / 100) - min(24, max(0, tail - 40) * .35)
        capped, cap, _ = module._cap_score(max(0, raw), cause_status=str(analysis.get("cause_verification_status") or "UNVERIFIED"),
            damage=number(result.get("damage_risk"), 0.0), tail_risk=tail,
            critical_fundamentals_missing=bool(analysis.get("critical_fundamentals_required")) and not bool((analysis.get("fundamental_trace") or {}).get("available")),
            hard_veto=bool(result.get("hard_veto")), analysis=analysis, price_context=analysis.get("price_session_context") or {})
        before_cost = min(capped, cap, external_cap)
        return raw, max(0.0, min(max(0.0, before_cost - penalty), score_cap)), before_cost
    for name in SCENARIO_NAMES:
        scenario = scenarios.get(name) or {}
        values = {key: number((scenario.get("values") or {}).get(key)) for key in WEIGHT_SETS["balanced"]}
        conf, tail = number(scenario.get("confidence")), number(scenario.get("tail"))
        if any(value is None or not 0 <= value <= 100 for value in values.values()) or conf is None or tail is None:
            missing.append(name)
            continue
        conf = min(confidence, max(0.0, min(100.0, conf)))
        for weight_name, weights in WEIGHT_SETS.items():
            raw, score, before_cost = evaluate(values, weights, conf, tail)
            passed = score >= 72 and values["overreaction"] >= 60 and values["survivability"] >= 55 and values["three_session_fit"] >= 55 and tail <= 60
            rows.append({"scenario": name, "weight_set": weight_name, "score": score,
                         "raw_pre_cap_score": raw, "before_cost_score": before_cost, "scenario_policy_pass": passed})
    values = [r["score"] for r in rows]
    base = [r for r in rows if r["scenario"] == "base_reliable"]
    raw_range = max((r["raw_pre_cap_score"] for r in base), default=0) - min((r["raw_pre_cap_score"] for r in base), default=0)
    saturated = bool(base) and max(r["score"] for r in base) - min(r["score"] for r in base) < 1e-6 and (max(r["score"] for r in base) <= 0 or raw_range > 1e-6)
    complete = not missing and len(rows) == len(SCENARIO_NAMES) * len(WEIGHT_SETS)
    status = "INCOMPLETE" if not complete else "CENSORED_BY_FLOOR_OR_CAP" if saturated else "MEASURED"
    stability = round(max(0, 100 - raw_range * 3.5), 1) if status == "MEASURED" else None
    drops = {}
    base_scenario = scenarios.get("base_reliable") or {}
    if base:
        base_values = deepcopy(base_scenario["values"])
        conf = min(confidence, number(base_scenario.get("confidence"), 0))
        tail = number(base_scenario.get("tail"), 0)
        full = evaluate(base_values, WEIGHT_SETS["balanced"], conf, tail)[0]
        for component in WEIGHT_SETS["balanced"]:
            adverse = deepcopy(base_values)
            adverse[component] = max(0, adverse[component] - max(10.0, adverse[component] * .20))
            drops[component] = round(max(0, full - evaluate(adverse, WEIGHT_SETS["balanced"], conf, tail)[0]), 3)
    return {"version": ROBUSTNESS_VERSION, "ensemble_member_count": len(rows), "weight_set_count": len(WEIGHT_SETS),
            "scenario_count": len(SCENARIO_NAMES) - len(missing), "missing_scenarios": missing, "complete": complete,
            "robust_lower_score": round(quantile(values, .25) or 0, 1),
            "ensemble_p10": round(quantile(values, .10), 1) if values else None,
            "ensemble_median": round(quantile(values, .50), 1) if values else None,
            "ensemble_p75": round(quantile(values, .75), 1) if values else None,
            "ensemble_minimum": round(min(values), 1) if values else None,
            "ensemble_maximum": round(max(values), 1) if values else None,
            "ensemble_range": round(max(values) - min(values), 2) if values else None,
            "quantile_basis": "ALL members AFTER identical friction transform AND all applicable caps",
            "lower_quartile_before_cost": quantile([r["before_cost_score"] for r in rows], .25),
            "execution_friction_penalty": penalty, "base_weight_range": round(raw_range, 3),
            "weight_stability_score": stability, "weight_sensitivity_status": status,
            "base_weight_threshold_flip": bool(base) and any(r["score"] >= 72 for r in base) and any(r["score"] < 72 for r in base),
            "component_adverse_drops": drops, "maximum_component_dependency": max(drops.values(), default=None),
            "component_method": "reduce each component by max(10 points,20%); FIX all weights; measure pre-cap score loss",
            "scenario_policy_pass_count": sum(r["scenario_policy_pass"] for r in rows),
            "scenario_policy_denominator": len(rows),
            "scenario_policy_pass_rate": sum(r["scenario_policy_pass"] for r in rows) / len(rows) if complete else None,
            "cost_stress_q25": {str(mult) + "x": round(quantile([max(0, min(r["before_cost_score"] - min(12, max(0, cost or 0) * mult * 2.5), score_cap)) for r in rows], .25), 1) if rows and cost is not None else None for mult in (1, 1.5, 2)},
            "members": rows,
            "method": "35 deterministic sensitivity cases; not independent trials, confidence bounds, return quantiles or win probabilities. Policy thresholds are uncalibrated."}


def _finalize(module, candidate, articles, result):
    analysis = result.setdefault("catalyst_analysis", {})
    robustness = analysis.setdefault("robustness_assessment", {})
    ensemble = audited_ensemble(module, result)
    robustness["legacy_v35_ensemble"] = robustness.get("ensemble")
    robustness["ensemble"] = ensemble
    execution = execution_audit(candidate, (analysis.get("reliability_assessment") or {}).get("execution_friction") or {})
    context = event_context(candidate, articles, ((analysis.get("reliability_assessment") or {}).get("evidence_relevance") or {}).get("event_family", "unknown"))
    gates = {key: bool(value) for key, value in (analysis.get("eligibility_gates") or {}).items() if key not in ALIASES and key != "stress_gate_pass_rate"}
    gates.update(robust_opportunity_threshold=ensemble["robust_lower_score"] >= 72,
                 ensemble_median=number(ensemble["ensemble_median"], 0) >= 75,
                 weight_stability=number(ensemble["weight_stability_score"], 0) >= 70 and not ensemble["base_weight_threshold_flip"],
                 component_independence=number(ensemble["maximum_component_dependency"], 100) <= 15,
                 complete_sensitivity_grid=ensemble["complete"],
                 execution_input_integrity=execution["scoring_inputs_valid"],
                 execution_friction=number(execution["estimate_pct"], math.inf) <= 1.5,
                 measured_stress_acceptance=number(ensemble["scenario_policy_pass_rate"], 0) >= .60)
    analysis.update(eligibility_gates=gates, weight_stability_score=ensemble["weight_stability_score"],
                    maximum_component_dependency=ensemble["maximum_component_dependency"],
                    robustness_version=ROBUSTNESS_VERSION, event_context=context, execution_audit=execution,
                    reliability_stress_gate_pass_rate=ensemble["scenario_policy_pass_rate"])
    robustness.update(version=ROBUSTNESS_VERSION, execution_audit=execution, event_context=context,
                      compatibility_gate_aliases={key: gates.get(value, False) for key, value in ALIASES.items()},
                      threshold_status="expert_policy_not_outcome_calibrated")
    result["final_score"] = ensemble["robust_lower_score"]
    return result


def _decide(result: dict) -> None:
    analysis = result["catalyst_analysis"]
    gates = analysis["eligibility_gates"]
    failed = [name for name, passed in gates.items() if not passed]
    analysis["failed_eligibility_gates"] = failed
    severe = (analysis.get("dilution_analysis") or {}).get("classification") == "capital_distress" or bool(result.get("hard_veto")) or number(analysis.get("tail_risk_score"), 0) >= 90 or number(result.get("damage_risk"), 0) >= 80 or number(analysis.get("evidence_contradiction_severity"), 0) >= 75
    score = result["final_score"]
    verdict = "PASS" if severe or score < 48 else "INVESTIGATE" if all(gates.values()) else "WATCH"
    result["verdict"] = verdict
    result["explanation"] = f"v3.9 deterministic sensitivity score {score:.1f}/100; {verdict}. " + ("All research-policy gates met; allocation still needs independent review." if not failed else "Unique failed gates: " + ", ".join(failed) + ".")
    result.setdefault("calculation_trace", {})["final"] = {"robust_lower_score": score, "verdict": verdict, "eligibility_gates": gates, "failed_eligibility_gates": failed}


def patch_module(module: Any) -> None:
    if getattr(module, "_v39_installed", False):
        return
    original_score, original_contract = module.score_candidate, module.public_scoring_contract
    from app.oversold_scoring_v38_evidence_integrity import prepare_evidence
    def score_candidate(candidate, articles, catalyst_class, risk_flags):
        clean, available, audit = prepare_evidence(candidate, articles)
        retained, duplicates = deduplicate_exact(available)
        result = original_score(deepcopy(clean), deepcopy(retained), catalyst_class, list(risk_flags or []))
        result = _finalize(module, clean, retained, result)
        analysis = result["catalyst_analysis"]
        # Retain every exclusion, even though the inner integrity pass saw only valid rows.
        inner_audit = analysis.get("evidence_integrity") or {}
        inner_audit["excluded_articles"] = audit["excluded_articles"]
        inner_audit["issues"] = sorted(set(inner_audit.get("issues", []) + audit.get("issues", [])))
        inner_audit["duplicate_articles"] = duplicates
        analysis["evidence_integrity"] = inner_audit
        relevance = (analysis.get("reliability_assessment") or {}).get("evidence_relevance") or {}
        provenance = provenance_clusters(retained, relevance)
        robustness = analysis["robustness_assessment"]
        robustness["declared_origin_provenance"] = provenance
        frozen = deepcopy(clean)
        enrichment = result.get("point_in_time_enrichment") or {}
        for key in ("history_bars", "intraday_bars", "benchmark_context", "fundamentals"):
            frozen[key] = deepcopy(clean.get(key) if clean.get(key) is not None else enrichment.get(key))
        frozen["history_bars"] = frozen.get("history_bars") or []
        frozen["benchmark_context"] = frozen.get("benchmark_context") or {}
        frozen["_sec_fundamentals"] = deepcopy(frozen.get("fundamentals"))
        frozen["_sec_prefetch_complete"] = True
        baseline = _finalize(module, frozen, retained, original_score(deepcopy(frozen), deepcopy(retained), catalyst_class, list(risk_flags or [])))
        replay_comparable = abs(baseline["final_score"] - result["final_score"]) <= .11
        replay_rows = []
        clusters = provenance["clusters"]
        # Bounded replays use captured inputs only, not new enrichment or later news.
        for cluster in clusters[:MAX_SOURCE_REPLAYS]:
            excluded = {str(i) for i in cluster["article_ids"]}
            remaining = [a for a in retained if str(a.get("id")) not in excluded]
            replay_input = deepcopy(frozen)
            shared_financial_root = str((frozen.get("fundamentals") or {}).get("accession_number") or "").lower()
            if shared_financial_root and shared_financial_root in cluster["primary_roots"]:
                replay_input["fundamentals"] = None
                replay_input["_sec_fundamentals"] = None
            replay = original_score(replay_input, deepcopy(remaining), catalyst_class, list(risk_flags or []))
            replay = _finalize(module, frozen, remaining, replay)
            _decide(replay)
            replay_rows.append({"removed_cluster": cluster["cluster_id"], "removed_article_ids": cluster["article_ids"],
                                "score": replay["final_score"], "score_drop": round(result["final_score"] - replay["final_score"], 2),
                                "verdict": replay["verdict"], "cause_status": replay["catalyst_analysis"].get("cause_verification_status"),
                                "hard_veto": bool(replay.get("hard_veto")), "failed_gates": replay["catalyst_analysis"]["failed_eligibility_gates"]})
        identifiers = [str(a.get("id")) for a in retained]
        identity_valid = all(a.get("id") is not None for a in retained) and len(set(identifiers)) == len(identifiers)
        complete = identity_valid and replay_comparable and bool(clusters) and len(replay_rows) == len(clusters)
        ablation = {"status": "AMBIGUOUS_ARTICLE_IDENTITIES" if not identity_valid else "INCOMPARABLE_REPLAY" if not replay_comparable else "COMPLETE" if complete else "NO_CAUSAL_CLUSTERS" if not clusters else "INCOMPLETE_BOUNDED",
                    "frozen_baseline_score": baseline["final_score"], "baseline_reproduced": replay_comparable,
                    "replayed_clusters": len(replay_rows), "total_clusters": len(clusters), "maximum_replays": MAX_SOURCE_REPLAYS,
                    "worst_score": min((r["score"] for r in replay_rows), default=None),
                    "maximum_score_drop": max((r["score_drop"] for r in replay_rows), default=None),
                    "cases": replay_rows, "cutoff": clean.get("evidence_cutoff") or clean.get("latest_trade_ts"),
                    "frozen_input_hash": hashlib.sha256(json.dumps(frozen, default=str, sort_keys=True).encode()).hexdigest(),
                    "method": "Remove each entire declared/similarity cluster, rerun economic model with captured price/financial inputs, then recompute sensitivity. Undeclared lineage remains a limitation."}
        robustness["source_removal"] = ablation
        gates = analysis["eligibility_gates"]
        gates["source_removal_robustness"] = complete and ablation["worst_score"] >= 48 and not any(r["hard_veto"] for r in replay_rows)
        gates["declared_origin_independence"] = provenance["causal_cluster_count"] >= 2
        groups = {"economics": [], "evidence": [], "timing": [], "execution": [], "sensitivity": []}
        for key, passed in gates.items():
            if passed:
                continue
            group = "execution" if any(token in key for token in ("execution", "spread", "liquidity")) else "sensitivity" if any(token in key for token in ("robust", "ensemble", "sensitivity", "stress", "weight", "component", "source_removal")) else "evidence" if any(token in key for token in ("cause", "causal", "evidence", "fundamental", "origin")) else "timing" if any(token in key for token in ("session", "alignment")) else "economics"
            groups[group].append(key)
        analysis["failure_groups"] = {key: value for key, value in groups.items() if value}
        analysis["source_removal"] = ablation
        analysis["source_dependency_risk"] = None  # old count lookup is not a measured probability
        analysis["allocation_status"] = "INDEPENDENT_REVIEW_REQUIRED"
        analysis["analysis_method"] = "rules_v3_9_auditable_deterministic_sensitivity"
        result.update(scoring_model_version=SCORING_MODEL_VERSION, scoring_config_version=SCORING_CONFIG_VERSION,
                      calibration_model_version=None, model_status="uncalibrated")
        _decide(result)
        robustness["legacy_robustness_gates"] = robustness.get("robustness_gates")
        robustness["robustness_gates"] = deepcopy(analysis["eligibility_gates"])
        result.setdefault("calculation_trace", {})["formula"] = robustness["ensemble"]["method"]
        result["calculation_trace"]["v3_8_evidence_integrity"] = deepcopy(inner_audit)
        result.setdefault("calculation_trace", {})["v3_9_robustness"] = deepcopy(robustness)
        return result
    def public_scoring_contract():
        contract = deepcopy(original_contract())
        contract["versions"] = deepcopy(module.SCORING_CONFIG["versions"])
        contract["score_semantics"] = {"name": "Deterministic sensitivity score", "range": "0-100", "calibrated_probability": False,
            "meaning": "p25 of 35 predeclared weight/scenario cases, all after identical cost transform and applicable caps; not a statistical confidence bound or expected return"}
        contract["ranking_rule"] = "Compare current-version scores only; do not overwrite or silently mix original model runs. Research ranking is not allocation permission."
        contract["robustness_audit"] = {"version": ROBUSTNESS_VERSION, "raw_weight_sensitivity": True,
            "source_removal_max_cases": MAX_SOURCE_REPLAYS, "stress_definition": "actual count / 35 deterministic cases meeting score and economic policy; not a win rate",
            "thresholds": {"score_p25": 72, "score_median": 75, "weight_stability": 70, "maximum_component_dependency": 15, "stress_acceptance": .60, "maximum_friction_pct": 1.5, "source_removal_watch_floor": 48},
            "validation": "Policy thresholds, cost proxies and weight/scenario design have not been shown to predict net profits; out-of-sample validation required.",
            "event_timing": "Article recency is not causal alignment; verify event, selloff onset and cutoff separately, including exchange holidays.",
            "allocation": "Buy-or-better as-of consensus + independent INVESTIGATE + verified provenance/timing/financial impact/stability/execution; otherwise zero. Never force deployment of capital."}
        return contract
    module.SCORING_MODEL_VERSION = SCORING_MODEL_VERSION
    module.SCORING_CONFIG_VERSION = SCORING_CONFIG_VERSION
    module.SCORING_CONFIG = deepcopy(module.SCORING_CONFIG)
    module.SCORING_CONFIG["versions"].update(scoring_model_version=SCORING_MODEL_VERSION, scoring_config_version=SCORING_CONFIG_VERSION)
    module.score_candidate, module.public_scoring_contract = score_candidate, public_scoring_contract
    module._v39_installed = True
