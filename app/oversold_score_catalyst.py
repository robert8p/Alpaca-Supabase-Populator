from __future__ import annotations

from typing import Any

from app.oversold_score_common import (
    SCORING_CONFIG, EXISTENTIAL_WORDS, STRUCTURAL_WORDS, TRANSIENT_WORDS, ANALYST_WORDS,
    DILUTION_WORDS, BIOTECH_FAILURE_WORDS, REGULATORY_FAILURE_WORDS, POSITIVE_TRIAL_WORDS,
    NEGATIVE_EARNINGS_WORDS, POSITIVE_EARNINGS_WORDS, PRIMARY_LIKE_SOURCES, clamp, _number,
    _article_text, filter_relevant_articles, _evidence_items, infer_sector_hint,
)
from app.oversold_score_technical import technical_context
from app.oversold_score_fundamental import (
    fundamental_context, _sales_surprises, _guidance_shortfalls, _yoy_sales_declines,
    _financing_amount, _major_stake,
)


def _event_metrics(text: str, fund: dict[str, Any]) -> dict[str, Any]:
    sales = _sales_surprises(text)
    guidance = _guidance_shortfalls(text)
    yoy_declines = _yoy_sales_declines(text)
    financing = _financing_amount(text)
    market_cap = _number(fund.get("market_cap"))
    financing_fraction = financing / market_cap if financing is not None and market_cap and market_cap > 0 else None
    return {
        "sales_surprises": sales,
        "worst_sales_surprise_pct": min((item["surprise_pct"] for item in sales), default=None),
        "guidance_shortfalls_pct": guidance,
        "worst_guidance_shortfall_pct": min(guidance, default=None),
        "yoy_sales_declines_pct": yoy_declines,
        "worst_yoy_sales_decline_pct": max(yoy_declines, default=None),
        "financing_amount": financing,
        "financing_to_market_cap": financing_fraction,
        "major_stake_pct": _major_stake(text),
    }


def _event_base(category: str) -> tuple[float, float, float, float]:
    return {
        "analyst_action": (82, 80, 76, 20),
        "temporary_operational": (88, 86, 80, 18),
        "financing_dilution": (55, 60, 52, 55),
        "earnings_deterioration": (34, 44, 34, 62),
        "earnings_mixed": (52, 55, 48, 50),
        "post_spike_unwind": (55, 60, 42, 35),
        "corporate_transaction": (42, 50, 40, 60),
        "management_event": (50, 55, 48, 48),
        "legal_uncertainty": (38, 45, 40, 62),
        "legal_integrity": (10, 18, 15, 90),
        "structural_impairment": (18, 25, 20, 82),
        "existential_solvency": (5, 8, 10, 96),
        "biotech_failure": (5, 10, 8, 95),
        "regulatory_failure": (8, 12, 10, 92),
        "positive_news_selloff": (58, 60, 72, 25),
        "unknown": (28, 32, 28, 45),
    }.get(category, (28, 32, 28, 45))


def _direct_event_articles(candidate: dict[str, Any], articles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    relevant = filter_relevant_articles(candidate, articles)
    event = [item for item in relevant if (item.get("_relevance") or {}).get("kind") == "direct_event"]
    return relevant, event


def classify_news_for_candidate(candidate: dict[str, Any], articles: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    relevant, event_articles = _direct_event_articles(candidate, articles)
    text = _article_text(event_articles)
    risk_flags: list[str] = []
    if any(word in text for word in EXISTENTIAL_WORDS):
        risk_flags.append("solvency")
    if any(word in text for word in DILUTION_WORDS):
        risk_flags.append("dilution")
    if any(word in text for word in ("trial", "endpoint", "fda", "ema", "complete response letter", "crl")):
        risk_flags.append("clinical_regulatory")
    if any(word in text for word in ("earnings", "eps", "sales", "revenue", "guidance", "forecast", "outlook", "wider loss")):
        risk_flags.append("earnings_guidance")
    if any(word in text for word in ("lawsuit", "subpoena", "investigation", "fraud", "material weakness")):
        risk_flags.append("legal")
    if any(word in text for word in ("ceo resign", "chief executive resign", "cfo resign")):
        risk_flags.append("management")
    if any(word in text for word in ("delist", "nasdaq deficiency", "listing deficiency")):
        risk_flags.append("delisting")
    if event_articles and any(word in text for word in ANALYST_WORDS):
        non_analyst_event = any(word in text for word in ("earnings", "sales", "revenue", "guidance", "offering", "trial", "endpoint", "fda", "outage", "contract", "lawsuit", "bankruptcy"))
        if not non_analyst_event:
            risk_flags.append("analyst_only")
    if not event_articles:
        if relevant:
            return "U", "News mentions the company, but no ticker-specific causal event is verified at the point-in-time cutoff.", sorted(set(risk_flags))
        return "U", "No ticker-specific causal news was retained at the point-in-time evidence cutoff.", ["no_news"]
    if any(word in text for word in EXISTENTIAL_WORDS):
        return "E", "Ticker-specific evidence contains existential solvency, fraud, default, or liquidation risk.", sorted(set(risk_flags))
    if any(word in text for word in STRUCTURAL_WORDS) or any(word in text for word in BIOTECH_FAILURE_WORDS):
        return "D", "Ticker-specific evidence contains potentially structural impairment.", sorted(set(risk_flags))
    if any(word in text for word in TRANSIENT_WORDS):
        return "B", "Ticker-specific evidence contains an explicitly temporary/reversible disruption.", sorted(set(risk_flags))
    if "analyst_only" in risk_flags:
        return "A", "Ticker-specific evidence is dominated by analyst/rating action rather than a new operating failure.", sorted(set(risk_flags))
    if any(flag in risk_flags for flag in ("dilution", "clinical_regulatory", "earnings_guidance", "legal", "management")):
        return "C", "Ticker-specific evidence identifies a material event whose economic damage requires scoring.", sorted(set(risk_flags))
    return "U", "Ticker-specific news exists, but it does not verify a negative causal event for the sell-off.", sorted(set(risk_flags))


def structured_catalyst_analysis(candidate: dict[str, Any], articles: list[dict[str, Any]], catalyst_class: str, risk_flags: list[str]) -> dict[str, Any]:
    relevant, event_articles = _direct_event_articles(candidate, articles)
    event_text = _article_text(event_articles)
    relevant_text = _article_text(relevant)
    technical = technical_context(candidate)
    fund = fundamental_context(candidate)
    fundamentals = candidate.get("fundamentals") or (candidate.get("raw_snapshot") or {}).get("fundamentals")
    sector_hint = infer_sector_hint(event_articles or relevant, fundamentals)
    metrics = _event_metrics(event_text, fund)

    existential = any(word in event_text for word in EXISTENTIAL_WORDS)
    structural = any(word in event_text for word in STRUCTURAL_WORDS)
    biotech_failure = any(word in event_text for word in BIOTECH_FAILURE_WORDS)
    regulatory_failure = any(word in event_text for word in REGULATORY_FAILURE_WORDS)
    positive_trial = any(word in event_text for word in POSITIVE_TRIAL_WORDS)
    transient = any(word in event_text for word in TRANSIENT_WORDS)
    financing = any(word in event_text for word in DILUTION_WORDS)
    analyst = bool(event_articles) and any(word in event_text for word in ANALYST_WORDS)
    analyst_only = analyst and not any(word in event_text for word in ("earnings", "sales", "revenue", "guidance", "offering", "trial", "endpoint", "fda", "outage", "contract", "lawsuit", "bankruptcy"))
    legal_integrity = any(word in event_text for word in ("accounting fraud", "fraud investigation", "material weakness"))
    legal_uncertainty = any(word in event_text for word in ("lawsuit", "subpoena", "investigation")) and not legal_integrity
    management = any(word in event_text for word in ("ceo resign", "chief executive resign", "cfo resign"))
    corporate_transaction = any(word in event_text for word in ("definitive agreement", "merger", "acquisition", "stake"))
    post_spike = bool(technical.get("post_spike_risk")) or any(word in relevant_text for word in ("rally cools", "surge cools", "rally fades", "surge fades", "profit-taking", "profit taking"))
    sales_miss = _number(metrics.get("worst_sales_surprise_pct"))
    guidance_shortfall = _number(metrics.get("worst_guidance_shortfall_pct"))
    yoy_decline = _number(metrics.get("worst_yoy_sales_decline_pct"))
    earnings_negative = any(word in event_text for word in NEGATIVE_EARNINGS_WORDS) or (sales_miss is not None and sales_miss < -2.0) or (guidance_shortfall is not None and guidance_shortfall < -2.0) or (yoy_decline is not None and yoy_decline > 5.0)
    earnings_positive = any(word in event_text for word in POSITIVE_EARNINGS_WORDS) or any(item["surprise_pct"] > 2.0 for item in metrics["sales_surprises"])

    if existential:
        category = "legal_integrity" if legal_integrity else "regulatory_failure" if regulatory_failure else "existential_solvency"
    elif biotech_failure:
        category = "biotech_failure"
    elif regulatory_failure:
        category = "regulatory_failure"
    elif legal_integrity:
        category = "legal_integrity"
    elif structural:
        category = "structural_impairment"
    elif transient:
        category = "temporary_operational"
    elif financing:
        category = "financing_dilution"
    elif earnings_negative and earnings_positive:
        category = "earnings_mixed"
    elif earnings_negative:
        category = "earnings_deterioration"
    elif legal_uncertainty:
        category = "legal_uncertainty"
    elif management:
        category = "management_event"
    elif corporate_transaction:
        category = "corporate_transaction"
    elif analyst_only:
        category = "analyst_action"
    elif post_spike:
        category = "post_spike_unwind"
    elif event_articles and (positive_trial or earnings_positive or any(word in event_text for word in ("contract win", "secured", "expansion", "starts shipment", "launch"))):
        category = "positive_news_selloff"
    else:
        category = "unknown"

    reversibility, horizon_fit, overreaction, damage = _event_base(category)
    drop = abs(min(_number(candidate.get("drop_pct")) or 0.0, 0.0))
    if category in {"analyst_action", "temporary_operational"}:
        overreaction = max(overreaction, clamp(58 + min(drop, 35) * 0.9))
    if category == "financing_dilution":
        fraction = _number(metrics.get("financing_to_market_cap"))
        if fraction is not None:
            if fraction < 0.10:
                damage = min(damage, 38); overreaction = max(overreaction, 68)
            elif fraction < 0.30:
                damage = max(damage, 50)
            elif fraction < 0.60:
                damage = max(damage, 65); reversibility = min(reversibility, 45)
            else:
                damage = max(damage, 78); reversibility = min(reversibility, 32)
        if "convertible" in event_text and "going concern" not in event_text:
            damage = min(max(damage, 48), 72)
        if "upsized" in event_text:
            damage = min(100, damage + 5)
    if category in {"earnings_deterioration", "earnings_mixed"}:
        if sales_miss is not None:
            miss = abs(min(sales_miss, 0.0))
            if miss >= 30:
                damage = max(damage, 76); reversibility = min(reversibility, 25); overreaction = min(overreaction, 34)
            elif miss >= 15:
                damage = max(damage, 65); reversibility = min(reversibility, 38)
            elif miss >= 5:
                damage = max(damage, 55)
        if guidance_shortfall is not None:
            miss = abs(min(guidance_shortfall, 0.0))
            if miss >= 15:
                damage = max(damage, 75); reversibility = min(reversibility, 28)
            elif miss >= 7:
                damage = max(damage, 64)
            elif miss >= 3:
                damage = max(damage, 55)
        if yoy_decline is not None:
            if yoy_decline >= 40:
                damage = max(damage, 78); reversibility = min(reversibility, 25)
            elif yoy_decline >= 20:
                damage = max(damage, 67)
            elif yoy_decline >= 10:
                damage = max(damage, 58)
    if category == "corporate_transaction":
        stake = _number(metrics.get("major_stake_pct"))
        if stake is not None and stake >= 50:
            damage = max(damage, 68); reversibility = min(reversibility, 38)
    poor_liquidity = _number(fund.get("cash_to_current_liabilities"))
    if poor_liquidity is not None and poor_liquidity < 0.20:
        damage = min(100.0, damage + 8.0)
    equity = _number(fund.get("total_equity"))
    if equity is not None and equity <= 0:
        damage = min(100.0, damage + 5.0)
    if positive_trial and not biotech_failure and not regulatory_failure:
        damage = min(damage, 28); reversibility = max(reversibility, 65)

    direct_event_count = len(event_articles)
    unique_sources = {str(article.get("source") or "unknown").strip().lower() for article in event_articles}
    primary_like_count = sum(1 for article in event_articles if any(source in str(article.get("source") or "").lower() for source in PRIMARY_LIKE_SOURCES))
    if direct_event_count:
        evidence_conf = 52.0 + min(12.0, 4.0 * max(0, direct_event_count - 1))
        if len(unique_sources) > 1:
            evidence_conf += min(18.0, 9.0 * (len(unique_sources) - 1))
        if primary_like_count:
            evidence_conf += min(8.0, 4.0 * primary_like_count)
        if len(unique_sources) == 1:
            evidence_conf = min(evidence_conf, 72.0)
    elif category == "post_spike_unwind" and technical.get("history_available"):
        evidence_conf = 62.0
    elif relevant:
        evidence_conf = 38.0
    else:
        evidence_conf = 20.0
    if earnings_negative and earnings_positive:
        evidence_conf -= 8.0

    cause_verified = category not in {"unknown", "positive_news_selloff"} and (bool(event_articles) or (category == "post_spike_unwind" and bool(technical.get("history_available"))))
    catalyst_score = clamp(0.50 * reversibility + 0.25 * horizon_fit + 0.25 * overreaction)
    if not cause_verified:
        catalyst_score = min(catalyst_score, float(SCORING_CONFIG["cause_unknown"]["catalyst_cap"]))
    hard_veto_reason = None
    if existential:
        hard_veto_reason = "existential_or_solvency_event"
    elif biotech_failure:
        hard_veto_reason = "core_pivotal_trial_failure"
    elif regulatory_failure:
        hard_veto_reason = "material_regulatory_failure"
    elif legal_integrity:
        hard_veto_reason = "fraud_or_accounting_integrity_failure"
    elif "going concern" in event_text and financing:
        hard_veto_reason = "catastrophic_financing_risk"
    if hard_veto_reason:
        damage = max(damage, 88.0)

    supporting: list[str] = []
    contradictory: list[str] = []
    if category == "temporary_operational":
        supporting.append("Ticker-specific evidence explicitly describes a temporary or reversible disruption.")
    if category == "analyst_action":
        supporting.append("The verified catalyst is analyst/rating action without a distinct operating failure in the retained evidence.")
    if category == "post_spike_unwind":
        supporting.append("Point-in-time price history shows the decline follows an unusually large recent advance, consistent with a technical unwind rather than fresh permanent damage.")
    if category == "positive_news_selloff":
        supporting.append("Verified company news is positive or non-damaging, but it does not itself explain the sell-off.")
    if category in {"earnings_deterioration", "earnings_mixed"}:
        contradictory.append("Ticker-specific earnings/guidance evidence indicates real economic deterioration that may justify part of the sell-off.")
    if category == "financing_dilution":
        contradictory.append("The sell-off is linked to financing/dilution; reversibility depends on dilution size and balance-sheet survivability.")
    if hard_veto_reason:
        contradictory.append("A verified structural/existential red flag triggers a hard veto.")
    if not cause_verified:
        contradictory.append("The primary cause of the decline is not sufficiently verified; the cause-unknown cap applies.")

    structural_categories = {"earnings_deterioration", "corporate_transaction", "legal_integrity", "regulatory_failure", "biotech_failure", "structural_impairment", "existential_solvency"}
    catalyst_type = "structural" if hard_veto_reason or category in structural_categories else "temporary" if category in {"analyst_action", "temporary_operational", "post_spike_unwind"} else "mixed" if category in {"earnings_mixed", "financing_dilution", "legal_uncertainty"} else "unknown"
    analyst_articles = [article for article in event_articles if any(word in f"{article.get('headline') or ''} {article.get('summary') or ''}".lower() for word in ANALYST_WORDS)]
    primary = event_articles[0].get("headline") if event_articles else relevant[0].get("headline") if relevant else "No independently verified ticker-specific catalyst at the signal cutoff"
    return {
        "primary_catalyst": primary, "catalyst_category": catalyst_class, "event_category": category,
        "catalyst_type": catalyst_type, "reversibility_score": round(reversibility, 1),
        "six_week_horizon_fit": round(horizon_fit, 1), "market_overreaction_score": round(overreaction, 1),
        "fundamental_damage_risk": round(clamp(damage), 1), "evidence_confidence": round(clamp(evidence_conf), 1),
        "supporting_evidence": supporting, "contradictory_evidence": contradictory,
        "red_flags": sorted(set(risk_flags)), "source_claims": _evidence_items(event_articles or relevant),
        "news_relevance": {"retained_article_count": len(articles), "relevant_article_count": len(relevant), "direct_event_count": len(event_articles), "independent_source_count": len(unique_sources), "ambient_article_count": max(0, len(articles) - len(relevant))},
        "event_metrics": metrics, "technical_cause_context": technical,
        "sector_assessment": {"sector_hint": sector_hint, "rubric": SCORING_CONFIG["sector_rubrics"].get(sector_hint, []), "note": "Sector uses point-in-time Massive SIC metadata when available, otherwise ticker-specific event text."},
        "analyst_reaction": {"coverage_available": bool(analyst_articles), "post_event_updates": _evidence_items(analyst_articles, 3), "direction": "negative" if any("downgrade" in str(a.get("headline") or "").lower() for a in analyst_articles) else "mixed" if analyst_articles else "unavailable"},
        "analysis_summary": f"Deterministic point-in-time event analysis v2.1; category={category}.",
        "cause_verified": cause_verified, "hard_veto": hard_veto_reason is not None, "hard_veto_reason": hard_veto_reason,
        "analysis_method": "rules_v2_1_point_in_time", "catalyst_score": round(catalyst_score, 1),
    }
