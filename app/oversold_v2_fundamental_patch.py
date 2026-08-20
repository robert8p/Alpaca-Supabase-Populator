from __future__ import annotations

from copy import deepcopy
from typing import Any


def install_patch() -> None:
    """Give V2 a conservative fundamentals assessment when filing cache coverage is absent.

    V2 continues to prefer cutoff-valid filing metrics.  If they are unavailable, the
    already-active production scoring engine is used only as a limited-data resilience /
    permanent-damage proxy.  The fallback does not receive filing-level confidence and is
    labelled clearly so it cannot be mistaken for audited financial statement coverage.
    """
    from app import oversold_scoring as production_scoring
    from app import oversold_v2 as target

    if getattr(target, "_limited_fundamentals_patch_installed", False):
        return

    original_loader = target.load_point_in_time_fundamentals
    original_classifier = target.classify_news_for_candidate
    original_score = target._score_candidate
    original_prompt = target._build_chatgpt_prompt

    filing_symbols: set[str] = set()
    proxies: dict[str, dict[str, Any]] = {}

    def load_fundamentals(symbols: list[str], cutoff: Any) -> dict[str, dict[str, Any]]:
        result = original_loader(symbols, cutoff)
        filing_symbols.clear()
        filing_symbols.update(str(symbol).upper() for symbol in result)
        proxies.clear()
        return result

    def classify(candidate: dict[str, Any], articles: list[dict[str, Any]]):
        result = original_classifier(candidate, articles)
        symbol = str(candidate.get("symbol") or "").upper()
        if symbol and symbol not in filing_symbols:
            catalyst_class, _summary, risk_flags = result
            try:
                full = production_scoring.score_candidate(candidate, articles, catalyst_class, risk_flags)
                analysis = full.get("catalyst_analysis") or {}
                proxies[symbol] = {
                    "source": "production_point_in_time_scanner_proxy",
                    "filing_metrics_available": False,
                    "resilience_score": float(full.get("resilience_score") or 35.0),
                    "damage_risk": float(full.get("damage_risk") or 50.0),
                    "evidence_confidence": float(full.get("evidence_confidence") or 0.0),
                    "hard_veto": bool(full.get("hard_veto")),
                    "hard_veto_reason": full.get("hard_veto_reason"),
                    "event_signals": analysis.get("event_signals") or {},
                    "dilution_analysis": analysis.get("dilution_analysis") or {},
                    "fundamental_trace": analysis.get("fundamental_trace") or {},
                    "note": "No cutoff-valid filing metrics were available; this is a conservative event/scanner-based resilience and damage assessment, not a substitute for financial statements.",
                }
            except Exception as exc:  # the V2 scan must remain available if optional enrichment fails
                proxies[symbol] = {
                    "source": "production_point_in_time_scanner_proxy",
                    "filing_metrics_available": False,
                    "resilience_score": 35.0,
                    "damage_risk": 50.0,
                    "evidence_confidence": 0.0,
                    "error": type(exc).__name__,
                    "note": "Limited fundamentals fallback could not be enriched; score remains conservative.",
                }
        return result

    def score(
        item: dict[str, Any],
        fundamentals: dict[str, Any] | None,
        catalyst_class: str,
        risk_flags: list[str],
        headline_count: int,
    ) -> dict[str, Any]:
        result = original_score(item, fundamentals, catalyst_class, risk_flags, headline_count)
        if fundamentals:
            result.setdefault("explanation", {})["fundamental_evidence_mode"] = "cutoff_valid_filing"
            return result

        proxy = proxies.get(str(item.get("symbol") or "").upper())
        if not proxy:
            result["fundamental_quality"] = "Limited · Unknown"
            result.setdefault("explanation", {})["fundamental_evidence_mode"] = "limited_unavailable"
            return result

        resilience = target._clamp(float(proxy.get("resilience_score") or 35.0))
        damage = target._clamp(float(proxy.get("damage_risk") or 50.0))
        quality_score = target._clamp(0.65 * resilience + 0.35 * (100.0 - damage))
        quality_score = min(quality_score, 60.0)

        signals = proxy.get("event_signals") or {}
        dilution = proxy.get("dilution_analysis") or {}
        if proxy.get("hard_veto") or signals.get("existential_or_solvency") or dilution.get("classification") == "capital_distress":
            quality_score = min(quality_score, 15.0)
        elif signals.get("primary_endpoint_failure") or signals.get("structural_impairment") or damage >= 80:
            quality_score = min(quality_score, 25.0)
        elif dilution.get("classification") == "material_dilution":
            quality_score = min(quality_score, 40.0)

        label = "Good" if quality_score >= 60 else "Mixed" if quality_score >= 45 else "Weak" if quality_score >= 30 else "Fragile"
        result["fundamental_quality"] = f"Limited · {label}"
        result["fundamental_survivability"] = round(resilience, 1)
        result["impairment_risk"] = round(max(float(result.get("impairment_risk") or 0.0), damage), 1)

        raw = (
            0.30 * float(result["dislocation_score"])
            + 0.30 * float(result["fundamental_survivability"])
            + 0.25 * float(result["catalyst_reversibility"])
            + 0.15 * (100.0 - float(result["impairment_risk"]))
        )
        confidence = float(result.get("confidence") or 0.0)  # deliberately unchanged: no filing-confidence boost
        confidence_factor = 0.45 + 0.55 * (confidence / 100.0)
        final = 50.0 + (raw - 50.0) * confidence_factor
        existing_cap = (result.get("explanation") or {}).get("hard_cap")
        if existing_cap is not None:
            final = min(final, float(existing_cap))
        if proxy.get("hard_veto"):
            final = min(final, 20.0)
        final = round(target._clamp(final), 1)
        result["oversold_score"] = final
        result["initial_view"] = "Investigate" if final >= 70 else "Watch" if final >= 55 else "Pass"

        explanation = result.setdefault("explanation", {})
        explanation["fundamental_evidence_mode"] = "limited_event_scanner_proxy"
        explanation["fundamental_quality_score"] = round(quality_score, 1)
        explanation["fundamental_proxy"] = proxy
        explanation["fundamental_reasons"] = [
            "cutoff_valid_filing_metrics_missing",
            "production_scanner_resilience_damage_proxy_used",
            "confidence_not_upgraded_for_proxy",
        ]
        return result

    def build_prompt(detail: dict[str, Any]) -> str:
        patched = deepcopy(detail)
        for row in patched.get("candidates") or []:
            if row.get("fundamentals"):
                continue
            proxy = (row.get("explanation") or {}).get("fundamental_proxy")
            if proxy:
                row["fundamentals"] = proxy
        return original_prompt(patched)

    target.load_point_in_time_fundamentals = load_fundamentals
    target.classify_news_for_candidate = classify
    target._score_candidate = score
    target._build_chatgpt_prompt = build_prompt
    target._limited_fundamentals_patch_installed = True
