from __future__ import annotations

"""Scoring integration for primary event evidence.

Primary records improve attribution and assessment confidence. They do not add a
bullish opportunity component and therefore cannot rescue structural damage.
"""

from typing import Any

SOURCE_QUALITY = {
    "sec_filing": ("regulatory_filing", 100),
    "clinical_trial_registry": ("clinical_trial_registry", 95),
    "fda_regulatory_record": ("regulatory_record", 98),
}


def _primary_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        article
        for article in articles
        if isinstance(article, dict) and article.get("is_primary_evidence") is True
    ]


def _primary_refs(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for article in _primary_articles(articles):
        record = article.get("primary_evidence") if isinstance(article.get("primary_evidence"), dict) else {}
        source_kind = str(article.get("source_kind") or record.get("source_kind") or "unknown")
        external_id = str(record.get("external_id") or article.get("id") or "")
        key = (source_kind, external_id)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "source_kind": source_kind,
                "source_authority": article.get("source_authority") or record.get("source_authority"),
                "external_id": external_id,
                "headline": article.get("headline"),
                "available_at": record.get("available_at") or article.get("created_at"),
                "source_url": record.get("source_url") or article.get("url"),
                "content_hash": record.get("content_hash"),
                "point_in_time_rule": (record.get("metadata") or {}).get("point_in_time_rule"),
            }
        )
    return refs


def patch_module(module: Any) -> None:
    if getattr(module, "_primary_evidence_scoring_installed", False):
        return

    original_hierarchy = module.source_quality_hierarchy
    original_score = module.score_candidate
    legacy = getattr(module, "_legacy", None)

    if legacy is not None and not getattr(legacy, "_primary_evidence_quality_installed", False):
        original_quality = legacy._source_evidence_quality

        def source_evidence_quality(
            candidate: dict[str, Any],
            articles: list[dict[str, Any]],
            *,
            cause_recognised: bool,
            conflicting: bool,
        ) -> tuple[float, dict[str, Any]]:
            score, trace = original_quality(
                candidate,
                articles,
                cause_recognised=cause_recognised,
                conflicting=conflicting,
            )
            refs = _primary_refs(articles)
            if refs:
                source_kinds = sorted({str(ref.get("source_kind") or "unknown") for ref in refs})
                authorities = sorted({str(ref.get("source_authority") or "unknown") for ref in refs})
                # A primary document proves what the issuer/regulator disclosed;
                # it only supports high causal confidence when the event itself is
                # recognised. An unrelated recent filing is not a verified cause.
                score = max(score, 90.0 if cause_recognised and not conflicting else 58.0)
                if conflicting:
                    score = min(score, 72.0)
                trace = dict(trace)
                trace.update(
                    {
                        "primary_evidence_count": len(refs),
                        "primary_evidence_source_kinds": source_kinds,
                        "primary_evidence_authorities": authorities,
                        "authoritative_source_present": True,
                        "point_in_time_primary_evidence": True,
                    }
                )
            else:
                trace = dict(trace)
                trace.setdefault("primary_evidence_count", 0)
                trace.setdefault("point_in_time_primary_evidence", False)
            return module._clamp(score), trace

        legacy._source_evidence_quality = source_evidence_quality
        legacy._primary_evidence_quality_installed = True

    def source_quality_hierarchy(
        candidate: dict[str, Any],
        articles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items = original_hierarchy(candidate, articles)
        by_id = {str(article.get("id")): article for article in articles if isinstance(article, dict)}
        for item in items:
            article = by_id.get(str(item.get("id")))
            if not article or article.get("is_primary_evidence") is not True:
                continue
            source_kind = str(article.get("source_kind") or "unknown")
            source_type, quality = SOURCE_QUALITY.get(source_kind, ("primary_source", 92))
            item["source_type"] = source_type
            item["source_quality_score"] = quality
            item["is_primary_evidence"] = True
            item["source_authority"] = article.get("source_authority")
            item["available_at"] = (article.get("primary_evidence") or {}).get("available_at") or article.get("created_at")
        return items

    def score_candidate(
        candidate: dict[str, Any],
        articles: list[dict[str, Any]],
        catalyst_class: str,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        result = original_score(candidate, articles, catalyst_class, risk_flags)
        refs = _primary_refs(articles)
        analysis = result.setdefault("catalyst_analysis", {})
        analysis["primary_event_evidence_items"] = refs
        analysis["primary_event_evidence_count"] = len(refs)
        analysis["primary_event_evidence_source_kinds"] = sorted(
            {str(ref.get("source_kind") or "unknown") for ref in refs}
        )
        analysis["primary_event_evidence_state"] = (
            "CUTOFF_VALID_PRIMARY_EVIDENCE_RETAINED"
            if refs
            else "NO_CUTOFF_VALID_PRIMARY_RECORD_RETAINED"
        )
        trace = result.setdefault("calculation_trace", {})
        trace["primary_event_evidence"] = {
            "count": len(refs),
            "items": refs,
            "role": "causal attribution and assessment confidence; never a standalone bullish component",
        }
        return result

    module.source_quality_hierarchy = source_quality_hierarchy
    module.score_candidate = score_candidate
    module._primary_evidence_scoring_installed = True
