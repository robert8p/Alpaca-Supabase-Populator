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

    module.cause_verification_status = cause_verification_status
    module.financing_assessment = financing_assessment
    module.price_path_assessment = price_path_assessment
