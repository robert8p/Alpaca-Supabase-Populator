from __future__ import annotations

"""Small compatibility corrections applied to the v3.2 scoring layer.

Kept separate from the main layer so the frozen v3.1 scorer remains untouched and
these edge-case contracts are obvious/reviewable.
"""

import re
from typing import Any


_NEGATED_FINANCING_PATTERNS = (
    re.compile(r"\bno\s+warrants?\s+or\s+convertibles?\b", re.IGNORECASE),
    re.compile(r"\bwithout\s+warrants?\s+or\s+convertibles?\b", re.IGNORECASE),
    re.compile(r"\bno\s+warrants?\b", re.IGNORECASE),
    re.compile(r"\bwithout\s+warrants?\b", re.IGNORECASE),
    re.compile(r"\bno\s+convertibles?\b", re.IGNORECASE),
    re.compile(r"\bwithout\s+convertibles?\b", re.IGNORECASE),
)


def _sanitize_negated_financing_text(value: Any) -> str:
    text = str(value or "")
    for pattern in _NEGATED_FINANCING_PATTERNS:
        text = pattern.sub("no additional dilutive security", text)
    return text


def patch_module(module: Any) -> None:
    original_financing = module.financing_assessment
    original_price_path = module.price_path_assessment
    original_source_hierarchy = module.source_quality_hierarchy
    original_score_candidate = module.score_candidate

    def cause_verification_status(result: dict[str, Any]) -> str:
        analysis = result.get("catalyst_analysis") or {}
        quality = analysis.get("evidence_quality_trace") or {}
        relevance = analysis.get("news_relevance_trace") or {}
        if quality.get("conflicting_evidence"):
            return "CONFLICTING"
        if not analysis.get("cause_verified"):
            return "PARTIALLY_VERIFIED" if int(relevance.get("causal_article_count") or 0) > 0 else "UNVERIFIED"
        source_confidence = module._num(analysis.get("evidence_confidence")) or 0.0
        articles = relevance.get("articles") or []
        explicit_direct = any(
            item.get("kind") == "direct_event" and not item.get("generic")
            for item in articles
        )
        # Internal/legacy callers may already provide a ticker-associated article
        # without a symbols field. v3.1 intentionally preserves that contract.
        # Treat a non-generic, event-specific direct-context article as VERIFIED
        # when its source confidence also clears the configured threshold.
        implicit_direct = any(
            item.get("symbol_metadata_present") is False
            and item.get("event_term")
            and not item.get("generic")
            and float(item.get("score") or 0.0) >= 48.0
            for item in articles
        )
        threshold = float(module.SCORING_CONFIG["cause_verification"]["verified_min_source_confidence"])
        return "VERIFIED" if source_confidence >= threshold and (explicit_direct or implicit_direct) else "PARTIALLY_VERIFIED"

    def financing_assessment(candidate: dict[str, Any], articles: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
        sanitized: list[dict[str, Any]] = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            clean = dict(article)
            clean["headline"] = _sanitize_negated_financing_text(article.get("headline"))
            clean["summary"] = _sanitize_negated_financing_text(article.get("summary"))
            sanitized.append(clean)
        return original_financing(candidate, sanitized, result)

    def price_path_assessment(candidate: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        assessment = original_price_path(candidate, result)
        current_vs_baseline = module._num(assessment.get("current_vs_pre_spike_baseline_pct"))
        if assessment.get("post_spike_unwind") and current_vs_baseline is not None and current_vs_baseline < 0.0:
            # Once price is genuinely below the measured pre-spike baseline, the
            # prior run-up is context rather than a dominant oversold veto.
            assessment["penalty"] = min(float(assessment.get("penalty") or 0.0), 4.0)
            assessment["setup_cap"] = max(float(assessment.get("setup_cap") or 0.0), 75.0)
        return assessment

    def damage_class(damage: float) -> str:
        # Match the economic interpretation in the audit spec: one-quarter misses,
        # manageable guidance resets and modest dilution are Moderate unless the
        # quantified impairment crosses the stronger 65+ damage band.
        if damage >= 80:
            return "STRUCTURAL_OR_EXISTENTIAL"
        if damage >= 65:
            return "HIGH"
        if damage >= 30:
            return "MODERATE"
        return "LOW"

    def source_quality_hierarchy(candidate: dict[str, Any], articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = original_source_hierarchy(candidate, articles)
        for item in items:
            headline = str(item.get("headline") or "").lower()
            relevance = str(item.get("causal_relevance") or "")
            if "transcript" in headline:
                item["source_type"] = "earnings_transcript"
                item["source_quality_score"] = max(int(item.get("source_quality_score") or 0), 86)
            elif relevance == "direct_event" and any(token in headline for token in (" eps ", "sales $", "revenue $", "guidance", "sees q", "sees fy")):
                item["source_type"] = "specialist_financial_media"
                item["source_quality_score"] = max(int(item.get("source_quality_score") or 0), 65)
        return items

    def event_taxonomy(analysis: dict[str, Any]) -> tuple[str, list[str]]:
        profile = str(analysis.get("event_profile") or analysis.get("catalyst_type") or "unknown")
        signals = analysis.get("event_signals") or {}
        dilution = analysis.get("dilution_analysis") or {}
        spike = analysis.get("spike_adjustment") or {}
        tags: list[str] = []

        financing_class = dilution.get("classification")
        if financing_class in {"financing_benign", "material_dilution", "capital_distress"}:
            primary = str(financing_class)
        elif spike.get("post_spike_unwind") and float(spike.get("penalty") or 0.0) >= 12.0:
            primary = "post_spike_unwind"
        elif profile == "quantified_earnings_deterioration":
            primary = "quantified_earnings_deterioration"
        elif profile in {"guidance_reset", "guidance_cut"} or signals.get("guidance_cut"):
            primary = "guidance_reduction"
        elif profile in {"temporary_disruption", "temporary_operational_issue"} or signals.get("temporary_operational"):
            primary = "temporary_operational_issue"
        elif profile in {"analyst_only", "analyst_action"} or signals.get("analyst_action"):
            primary = "analyst_action"
        elif signals.get("primary_endpoint_failure"):
            primary = "binary_thesis_failure"
        elif signals.get("fda_rejection_or_crl"):
            primary = "regulatory_issue"
        elif signals.get("fraud_or_accounting_credibility"):
            primary = "fraud_or_governance"
        elif signals.get("legal_or_regulatory"):
            primary = "litigation" if "lawsuit" in str(analysis.get("primary_catalyst") or "").lower() else "regulatory_issue"
        elif signals.get("broad_sector_risk_off"):
            primary = "sentiment_overreaction"
        elif profile in {"technical_selloff", "sentiment_overreaction"}:
            primary = profile
        else:
            primary = "unknown" if profile in {"unknown", "unverified_news"} else profile

        if dilution.get("reverse_split") or dilution.get("listing_stress"):
            tags.append("reverse_split_or_listing_stress")
        if signals.get("existential_or_solvency"):
            tags.append("capital_distress")
        if signals.get("primary_endpoint_failure"):
            tags.append("failed_catalyst")
        if signals.get("structural_impairment"):
            tags.append("binary_thesis_failure")
        if signals.get("fraud_or_accounting_credibility"):
            tags.append("fraud_or_governance")
        if primary not in tags:
            tags.insert(0, primary)
        return primary, list(dict.fromkeys(tags))

    def score_candidate(candidate: dict[str, Any], articles: list[dict[str, Any]], catalyst_class: str, risk_flags: list[str]) -> dict[str, Any]:
        result = original_score_candidate(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        # original_score_candidate used the patched helper functions above, but it
        # ran before this wrapper has a chance to normalize display semantics.
        normalized_damage = damage_class(float(result.get("damage_risk") or 0.0))
        primary_taxonomy, taxonomy_tags = event_taxonomy(analysis)
        analysis["economic_damage_class"] = normalized_damage
        analysis["event_taxonomy_primary"] = primary_taxonomy
        analysis["event_taxonomy_tags"] = taxonomy_tags
        if result.get("calculation_trace", {}).get("v3_2") is not None:
            result["calculation_trace"]["v3_2"]["economic_damage_class"] = normalized_damage
            result["calculation_trace"]["v3_2"]["event_taxonomy_primary"] = primary_taxonomy
            result["calculation_trace"]["v3_2"]["event_taxonomy_tags"] = taxonomy_tags
        return result

    module.cause_verification_status = cause_verification_status
    module.financing_assessment = financing_assessment
    module.price_path_assessment = price_path_assessment
    module._damage_class = damage_class
    module.source_quality_hierarchy = source_quality_hierarchy
    module.score_candidate = score_candidate
