from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

from app.oversold_features import technical_features
from app.oversold_live_enrichment import load_runtime_enrichment
from app.oversold_v3_hardening import (
    apply_quantified_event_hardening, direct_news_risk_flags, filter_causal_articles,
    setup_post_spike_cap,
)

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_1"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v2"
CATALYST_PROMPT_VERSION = "catalyst_rules_prompt_v3"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3"
CALIBRATION_MODEL_VERSION: str | None = None
MODEL_STATUS = "uncalibrated"
TARGET_DEFINITION = "hit_plus_5pct_within_6_weeks"

SCORING_CONFIG: dict[str, Any] = {
    "versions": {
        "scoring_model_version": SCORING_MODEL_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "catalyst_prompt_version": CATALYST_PROMPT_VERSION,
        "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
        "calibration_model_version": CALIBRATION_MODEL_VERSION,
    },
    "target": {"field": TARGET_DEFINITION, "threshold_pct": 5.0, "horizon_weeks": 6},
    "weights": {"setup": 0.25, "catalyst": 0.35, "resilience": 0.15, "confirmation": 0.25},
    "setup_feature_weights": {
        "raw_decline": 0.15,
        "volatility_shock": 0.20,
        "recent_high_drawdown": 0.10,
        "moving_average_dislocation": 0.15,
        "rsi": 0.10,
        "volume_anomaly": 0.10,
        "relative_move": 0.10,
        "tradability": 0.10,
    },
    "confirmation_feature_weights": {
        "range_position": 0.25,
        "intraday_reversal": 0.20,
        "gap_reclaim": 0.20,
        "vwap_reclaim": 0.15,
        "volume_stabilisation": 0.10,
        "spread_quality": 0.10,
    },
    "confidence": {"neutral_prior": 50.0},
    "damage": {
        "penalty_start": 25.0,
        "penalty_per_point": 0.20,
        "penalty_max": 15.0,
        "caps": [
            {"min": 0, "max": 29, "cap": 100},
            {"min": 30, "max": 49, "cap": 85},
            {"min": 50, "max": 69, "cap": 65},
            {"min": 70, "max": 84, "cap": 40},
            {"min": 85, "max": 100, "cap": 20},
        ],
    },
    "cause_unknown": {"catalyst_cap": 35, "final_cap": 60, "max_verdict": "WATCH"},
    "decision_thresholds": {"investigate": 75, "watch": 55},
    "calibration": {
        "minimum_matured_signals": 300,
        "minimum_positives": 60,
        "minimum_negatives": 60,
        "minimum_temporal_holdout": 100,
        "require_positive_brier_skill": True,
    },
    "sector_rubrics": {
        "biotechnology": ["trial phase", "primary/secondary endpoint", "statistical significance", "safety", "FDA/EMA", "pipeline concentration", "cash runway", "dilution"],
        "financials": ["liquidity", "capital adequacy", "deposits", "credit deterioration", "regulatory action", "funding stress"],
        "software": ["ARR/revenue guidance", "retention/churn", "customer concentration", "security breach", "competition", "margin trajectory"],
        "industrials": ["production disruption", "order book", "supply chain", "plant incident", "demand destruction"],
        "consumer": ["demand", "inventory", "margin pressure", "comparable sales", "promotional effects"],
    },
}

EXISTENTIAL_WORDS = (
    "bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern",
    "payment default", "debt default", "liquidation", "unable to continue as a going concern",
)
FRAUD_WORDS = (
    "accounting fraud", "fraud investigation", "financial fraud", "falsified", "restatement due to fraud",
)
STRUCTURAL_WORDS = (
    "permanently close", "permanent closure", "terminates program", "terminated program",
    "discontinues program", "discontinued program", "patent invalid", "patent loss",
    "loses key customer", "lost key customer", "license terminated", "business model impairment",
    "collapse in core demand", "demand collapse", "permanent margin impairment",
)
TEMPORARY_WORDS = (
    "temporary", "temporarily", "outage", "weather disruption", "shipment delay", "shipping delay",
    "supply disruption", "technical issue", "production delay", "short-term disruption", "one-time",
)
RESUME_WORDS = (
    "operations resume", "resumes operations", "production resumes", "restart", "restarts production",
    "resolved", "restored service", "back online",
)
BROAD_SECTOR_WORDS = (
    "sector sell-off", "sector selloff", "industry-wide", "industry wide", "risk-off", "risk off",
    "broad market sell-off", "broad market selloff", "peer group sell-off", "peer group selloff",
)
ANALYST_WORDS = ("downgrade", "upgrade", "price target", "analyst", "rating", "broker")
TARGET_CUT_WORDS = ("price target cut", "cuts price target", "price target lowered", "lowers price target", "target reduced")
TARGET_RAISE_WORDS = ("price target raised", "raises price target", "target increased")
GUIDANCE_CUT_WORDS = (
    "cuts guidance", "cut guidance", "lowers guidance", "lowered guidance", "reduces guidance",
    "reduced guidance", "withdraws guidance", "withdrew guidance", "profit warning", "revenue warning",
    "cuts forecast", "lowers forecast", "reduced forecast", "guidance reset",
)
GUIDANCE_REAFFIRM_WORDS = ("reaffirms guidance", "reiterates guidance", "maintains guidance", "guidance unchanged")
EARNINGS_MISS_WORDS = ("earnings miss", "misses estimates", "missed estimates", "revenue miss", "missed revenue", "misses revenue")
DILUTION_WORDS = ("public offering", "registered direct", "at-the-market", "at the market", "dilution", "convertible", "warrant", "secondary offering")
CLINICAL_PRIMARY_FAILURE_WORDS = (
    "failed primary endpoint", "did not meet the primary endpoint", "missed primary endpoint",
    "primary endpoint was not met", "primary endpoint not met", "failed pivotal trial", "pivotal trial failed",
)
CLINICAL_SECONDARY_MISS_WORDS = ("missed secondary endpoint", "secondary endpoint was not met", "secondary endpoint not met")
PRIMARY_SUCCESS_WORDS = ("met the primary endpoint", "primary endpoint was met", "achieved primary endpoint")
FDA_REJECTION_WORDS = ("fda rejects", "fda rejected", "complete response letter", " crl ", "regulatory rejection")
CLINICAL_HOLD_WORDS = ("clinical hold", "partial clinical hold", "trial halted", "study halted")
SAFETY_WORDS = ("safety signal", "serious adverse event", "unexpected adverse events", "toxicity")
MAJOR_CUSTOMER_WORDS = ("loses key customer", "lost key customer", "major customer loss", "largest customer terminated")
SECURITY_BREACH_WORDS = ("security breach", "cybersecurity incident", "ransomware", "data breach")
LEGAL_WORDS = ("lawsuit", "subpoena", "investigation", "regulatory investigation", "sec investigation")
MANAGEMENT_WORDS = ("ceo resign", "chief executive resign", "cfo resign", "chief financial officer resign")
DELISTING_WORDS = ("listing deficiency", "nasdaq deficiency", "delisting notice", "faces delisting")

PRIMARY_SOURCE_TOKENS = (
    "company ir", "investor relations", "business wire", "businesswire", "globenewswire", "globe newswire",
    "pr newswire", "accesswire", "sec filing", "securities and exchange commission",
)
HIGH_QUALITY_SOURCE_TOKENS = ("reuters", "dow jones", "associated press", "bloomberg", "wall street journal")


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


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


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _linear_score(value: float | None, low: float, high: float, *, low_score: float = 20.0, high_score: float = 95.0, fallback: float = 35.0) -> float:
    if value is None:
        return fallback
    if high <= low:
        return fallback
    fraction = clamp((value - low) / (high - low), 0.0, 1.0)
    return clamp(low_score + fraction * (high_score - low_score))


def infer_sector_hint(articles: list[dict[str, Any]]) -> str:
    text = _article_text(articles)
    if any(w in text for w in ("clinical trial", "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii", "fda", "ema", "endpoint", "drug candidate", "biotech", "pharma")):
        return "biotechnology"
    if any(w in text for w in ("deposits", "capital ratio", "tier 1", "loan losses", "net interest margin", "bank liquidity", "funding stress", "bank")):
        return "financials"
    if any(w in text for w in ("arr", "annual recurring revenue", "net retention", "churn", "saas", "cybersecurity breach", "software subscription", "cloud software")):
        return "software"
    if any(w in text for w in ("plant", "production", "factory", "order book", "backlog", "supply chain", "industrial")):
        return "industrials"
    if any(w in text for w in ("comparable sales", "same-store sales", "inventory", "retail", "consumer demand", "promotional", "store traffic")):
        return "consumer"
    return "unknown"


def _article_text(articles: list[dict[str, Any]]) -> str:
    return " ".join(f"{a.get('headline') or ''} {a.get('summary') or ''}" for a in articles).lower()


def _evidence_items(articles: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return [
        {
            "id": a.get("id"),
            "headline": a.get("headline"),
            "source": a.get("source"),
            "published_at": a.get("created_at"),
            "url": a.get("url"),
        }
        for a in articles[:limit]
    ]


def _source_name(article: dict[str, Any]) -> str:
    return str(article.get("source") or "unknown").strip().lower()


def _source_evidence_quality(candidate: dict[str, Any], articles: list[dict[str, Any]], *, cause_recognised: bool, conflicting: bool) -> tuple[float, dict[str, Any]]:
    if not articles:
        return 15.0, {
            "article_count": 0,
            "independent_source_count": 0,
            "authoritative_source_present": False,
            "freshest_age_hours": None,
            "conflicting_evidence": conflicting,
        }
    sources = {_source_name(article) for article in articles if _source_name(article) != "unknown"}
    count = len(sources)
    source_score = 58.0 if count <= 1 else 70.0 if count == 2 else 79.0 if count == 3 else 85.0
    authoritative = any(any(token in _source_name(article) for token in PRIMARY_SOURCE_TOKENS + HIGH_QUALITY_SOURCE_TOKENS) for article in articles)
    if authoritative:
        source_score += 9.0
    cutoff = _parse_ts(candidate.get("evidence_cutoff")) or _parse_ts(candidate.get("latest_trade_ts"))
    published = [_parse_ts(article.get("created_at")) for article in articles]
    valid_published = [value for value in published if value is not None]
    freshest_age_hours = None
    if cutoff is not None and valid_published:
        freshest_age_hours = max(0.0, min((cutoff - value).total_seconds() / 3600.0 for value in valid_published))
        if freshest_age_hours <= 12:
            source_score += 7.0
        elif freshest_age_hours <= 36:
            source_score += 3.0
        elif freshest_age_hours > 72:
            source_score -= 8.0
    if not cause_recognised:
        source_score -= 20.0
    if conflicting:
        source_score -= 14.0
    score = clamp(source_score)
    return score, {
        "article_count": len(articles),
        "independent_source_count": count,
        "sources": sorted(sources),
        "authoritative_source_present": authoritative,
        "freshest_age_hours": round(freshest_age_hours, 2) if freshest_age_hours is not None else None,
        "conflicting_evidence": conflicting,
    }


def _event_signals(text: str, risk_flags: list[str], sector_hint: str) -> dict[str, bool]:
    analyst = _contains_any(text, ANALYST_WORDS) or "analyst_only" in risk_flags
    guidance_cut = _contains_any(text, GUIDANCE_CUT_WORDS)
    earnings_miss = _contains_any(text, EARNINGS_MISS_WORDS)
    dilution = _contains_any(text, DILUTION_WORDS) or "dilution" in risk_flags
    temporary = _contains_any(text, TEMPORARY_WORDS)
    resumed = _contains_any(text, RESUME_WORDS)
    broad_sector = _contains_any(text, BROAD_SECTOR_WORDS)
    primary_failure = sector_hint == "biotechnology" and _contains_any(text, CLINICAL_PRIMARY_FAILURE_WORDS)
    secondary_miss = sector_hint == "biotechnology" and _contains_any(text, CLINICAL_SECONDARY_MISS_WORDS)
    primary_success = sector_hint == "biotechnology" and _contains_any(text, PRIMARY_SUCCESS_WORDS)
    fda_rejection = sector_hint == "biotechnology" and _contains_any(f" {text} ", FDA_REJECTION_WORDS)
    clinical_hold = sector_hint == "biotechnology" and _contains_any(text, CLINICAL_HOLD_WORDS)
    safety = sector_hint == "biotechnology" and _contains_any(text, SAFETY_WORDS)
    existential = _contains_any(text, EXISTENTIAL_WORDS) or "solvency" in risk_flags
    fraud = _contains_any(text, FRAUD_WORDS)
    structural = _contains_any(text, STRUCTURAL_WORDS)
    major_customer = _contains_any(text, MAJOR_CUSTOMER_WORDS)
    security_breach = _contains_any(text, SECURITY_BREACH_WORDS)
    legal = _contains_any(text, LEGAL_WORDS) or "legal" in risk_flags
    management = _contains_any(text, MANAGEMENT_WORDS) or "management" in risk_flags
    delisting = _contains_any(text, DELISTING_WORDS) or "delisting" in risk_flags
    target_cut = _contains_any(text, TARGET_CUT_WORDS)
    target_raise = _contains_any(text, TARGET_RAISE_WORDS)
    guidance_reaffirm = _contains_any(text, GUIDANCE_REAFFIRM_WORDS)
    operating_material = any((guidance_cut, earnings_miss, dilution, primary_failure, fda_rejection, clinical_hold, safety, existential, fraud, structural, major_customer, security_breach, legal))
    analyst_only = analyst and not operating_material
    catastrophic_financing = dilution and existential
    return {
        "temporary_operational": temporary,
        "operations_resumed": resumed,
        "broad_sector_risk_off": broad_sector,
        "analyst_action": analyst,
        "analyst_only": analyst_only,
        "analyst_target_cut": target_cut,
        "analyst_target_raise": target_raise,
        "guidance_cut": guidance_cut,
        "guidance_reaffirmed": guidance_reaffirm,
        "earnings_miss": earnings_miss,
        "dilution_or_financing": dilution,
        "catastrophic_financing": catastrophic_financing,
        "primary_endpoint_failure": primary_failure,
        "secondary_endpoint_miss": secondary_miss,
        "primary_endpoint_success": primary_success,
        "fda_rejection_or_crl": fda_rejection,
        "clinical_hold": clinical_hold,
        "safety_signal": safety,
        "existential_or_solvency": existential,
        "fraud_or_accounting_credibility": fraud,
        "structural_impairment": structural,
        "major_customer_loss": major_customer,
        "security_breach": security_breach,
        "legal_or_regulatory": legal,
        "management_departure": management,
        "listing_risk": delisting,
    }


def _event_profile(signals: dict[str, bool], catalyst_class: str) -> dict[str, Any]:
    profile = {"name": "unknown", "damage": 45.0, "reversibility": 30.0, "horizon": 35.0, "hard_veto_reason": None}
    if signals["existential_or_solvency"]:
        profile = {"name": "existential_or_solvency", "damage": 95.0, "reversibility": 5.0, "horizon": 5.0, "hard_veto_reason": "existential_or_solvency_event"}
    elif signals["primary_endpoint_failure"]:
        profile = {"name": "core_pivotal_trial_failure", "damage": 93.0, "reversibility": 8.0, "horizon": 10.0, "hard_veto_reason": "core_pivotal_trial_failure"}
    elif signals["catastrophic_financing"]:
        profile = {"name": "catastrophic_financing", "damage": 91.0, "reversibility": 10.0, "horizon": 12.0, "hard_veto_reason": "catastrophic_financing_risk"}
    elif signals["fraud_or_accounting_credibility"]:
        profile = {"name": "fraud_or_accounting", "damage": 88.0, "reversibility": 12.0, "horizon": 15.0, "hard_veto_reason": None}
    elif signals["fda_rejection_or_crl"]:
        profile = {"name": "fda_rejection_or_crl", "damage": 87.0, "reversibility": 15.0, "horizon": 18.0, "hard_veto_reason": None}
    elif signals["structural_impairment"] or signals["major_customer_loss"]:
        profile = {"name": "structural_business_impairment", "damage": 82.0, "reversibility": 18.0, "horizon": 22.0, "hard_veto_reason": None}
    elif signals["clinical_hold"] or signals["safety_signal"]:
        profile = {"name": "clinical_safety_or_hold", "damage": 78.0, "reversibility": 24.0, "horizon": 28.0, "hard_veto_reason": None}
    elif signals["guidance_cut"]:
        profile = {"name": "guidance_reset", "damage": 68.0, "reversibility": 32.0, "horizon": 38.0, "hard_veto_reason": None}
    elif signals["legal_or_regulatory"]:
        profile = {"name": "legal_or_regulatory", "damage": 62.0, "reversibility": 38.0, "horizon": 45.0, "hard_veto_reason": None}
    elif signals["security_breach"]:
        profile = {"name": "security_breach", "damage": 60.0, "reversibility": 45.0, "horizon": 52.0, "hard_veto_reason": None}
    elif signals["dilution_or_financing"]:
        profile = {"name": "survivable_financing_or_dilution", "damage": 58.0, "reversibility": 46.0, "horizon": 52.0, "hard_veto_reason": None}
    elif signals["earnings_miss"]:
        profile = {"name": "earnings_miss", "damage": 55.0, "reversibility": 45.0, "horizon": 50.0, "hard_veto_reason": None}
    elif signals["secondary_endpoint_miss"] and signals["primary_endpoint_success"]:
        profile = {"name": "secondary_endpoint_miss_primary_intact", "damage": 42.0, "reversibility": 60.0, "horizon": 64.0, "hard_veto_reason": None}
    elif signals["management_departure"]:
        profile = {"name": "management_departure", "damage": 45.0, "reversibility": 54.0, "horizon": 58.0, "hard_veto_reason": None}
    elif signals["listing_risk"]:
        profile = {"name": "listing_risk", "damage": 65.0, "reversibility": 36.0, "horizon": 42.0, "hard_veto_reason": None}
    elif signals["operations_resumed"]:
        profile = {"name": "temporary_disruption_resolved", "damage": 18.0, "reversibility": 93.0, "horizon": 92.0, "hard_veto_reason": None}
    elif signals["temporary_operational"]:
        profile = {"name": "temporary_operational_disruption", "damage": 25.0, "reversibility": 87.0, "horizon": 86.0, "hard_veto_reason": None}
    elif signals["broad_sector_risk_off"]:
        profile = {"name": "broad_sector_risk_off", "damage": 18.0, "reversibility": 89.0, "horizon": 86.0, "hard_veto_reason": None}
    elif signals["analyst_only"]:
        damage = 27.0 if signals["analyst_target_cut"] else 20.0
        profile = {"name": "analyst_only", "damage": damage, "reversibility": 82.0, "horizon": 80.0, "hard_veto_reason": None}
    elif signals["guidance_reaffirmed"]:
        profile = {"name": "guidance_reaffirmed", "damage": 25.0, "reversibility": 78.0, "horizon": 76.0, "hard_veto_reason": None}
    elif catalyst_class == "D":
        profile = {"name": "structural_class_without_specific_rule", "damage": 76.0, "reversibility": 22.0, "horizon": 28.0, "hard_veto_reason": None}
    elif catalyst_class == "E":
        profile = {"name": "existential_class_without_specific_rule", "damage": 90.0, "reversibility": 10.0, "horizon": 12.0, "hard_veto_reason": None}
    return profile


def _fundamental_resilience(fundamentals: dict[str, Any] | None, signals: dict[str, bool], risk_flags: list[str]) -> tuple[float, float, dict[str, Any]]:
    contributions: dict[str, float] = {}
    if not fundamentals:
        score = 45.0
        confidence = 35.0
        source = None
        age_days = None
        coverage = 0
    else:
        score = 50.0
        coverage = int(fundamentals.get("metric_coverage_count") or 0)
        confidence = clamp(45.0 + min(coverage, 10) * 4.0)
        source = fundamentals.get("source")
        age_days = fundamentals.get("age_calendar_days")
        cash_to_assets = _number(fundamentals.get("cash_to_assets"))
        liabilities_to_assets = _number(fundamentals.get("liabilities_to_assets"))
        equity_to_assets = _number(fundamentals.get("equity_to_assets"))
        revenue_yoy = _number(fundamentals.get("revenue_yoy"))
        net_margin = _number(fundamentals.get("net_margin"))
        net_margin_delta = _number(fundamentals.get("net_margin_yoy_delta"))
        diluted_shares_yoy = _number(fundamentals.get("diluted_shares_yoy"))

        if cash_to_assets is not None:
            delta = 18.0 if cash_to_assets >= 0.30 else 10.0 if cash_to_assets >= 0.15 else -15.0 if cash_to_assets < 0.05 else 0.0
            score += delta
            contributions["cash_to_assets"] = delta
        if liabilities_to_assets is not None:
            delta = 10.0 if liabilities_to_assets <= 0.50 else -22.0 if liabilities_to_assets >= 0.90 else -10.0 if liabilities_to_assets >= 0.80 else 0.0
            score += delta
            contributions["liabilities_to_assets"] = delta
        if equity_to_assets is not None:
            delta = 10.0 if equity_to_assets >= 0.30 else -20.0 if equity_to_assets <= 0.05 else -8.0 if equity_to_assets <= 0.12 else 0.0
            score += delta
            contributions["equity_to_assets"] = delta
        if revenue_yoy is not None:
            delta = 10.0 if revenue_yoy >= 0.10 else -16.0 if revenue_yoy <= -0.25 else -8.0 if revenue_yoy <= -0.10 else 0.0
            score += delta
            contributions["revenue_yoy"] = delta
        if net_margin is not None:
            delta = 8.0 if net_margin >= 0.05 else -14.0 if net_margin <= -0.20 else -7.0 if net_margin < 0 else 0.0
            score += delta
            contributions["net_margin"] = delta
        if net_margin_delta is not None:
            delta = -10.0 if net_margin_delta <= -0.10 else 5.0 if net_margin_delta >= 0.05 else 0.0
            score += delta
            contributions["net_margin_yoy_delta"] = delta
        if diluted_shares_yoy is not None:
            delta = -25.0 if diluted_shares_yoy >= 0.50 else -15.0 if diluted_shares_yoy >= 0.20 else -7.0 if diluted_shares_yoy >= 0.10 else 4.0 if diluted_shares_yoy <= -0.05 else 0.0
            score += delta
            contributions["diluted_shares_yoy"] = delta
        if age_days is not None and age_days > 180:
            score = 45.0 + (score - 45.0) * 0.65
            confidence -= 12.0
            contributions["staleness_shrink"] = -12.0

    if signals["existential_or_solvency"] or "solvency" in risk_flags:
        score = min(score, 18.0)
    elif signals["catastrophic_financing"]:
        score = min(score, 20.0)
    elif signals["dilution_or_financing"] or "dilution" in risk_flags:
        score -= 10.0
    if signals["temporary_operational"] or signals["operations_resumed"] or signals["broad_sector_risk_off"] or signals["analyst_only"]:
        score += 5.0
    if signals["guidance_cut"]:
        score -= 6.0

    return round(clamp(score), 1), round(clamp(confidence), 1), {
        "available": fundamentals is not None,
        "source": source,
        "form": fundamentals.get("form") if fundamentals else None,
        "available_from": fundamentals.get("available_from") if fundamentals else None,
        "report_period_end": fundamentals.get("report_period_end") if fundamentals else None,
        "age_calendar_days": age_days,
        "metric_coverage_count": coverage,
        "contributions": contributions,
        "raw_metrics": {
            key: fundamentals.get(key) if fundamentals else None
            for key in (
                "revenue_yoy", "net_margin", "net_margin_yoy_delta", "operating_margin", "gross_margin",
                "eps_change_symmetric", "net_income_change_symmetric", "diluted_shares_yoy",
                "cash_to_assets", "liabilities_to_assets", "equity_to_assets",
            )
        },
    }


def _dislocation_strength(tech: dict[str, Any], drop_pct: float | None) -> float:
    drop = abs(min(drop_pct or 0.0, 0.0))
    raw = _linear_score(drop, 15.0, 45.0, low_score=55.0, high_score=95.0, fallback=45.0)
    shock_z = _number(tech.get("shock_z"))
    shock = _linear_score(shock_z, 1.5, 5.0, low_score=40.0, high_score=98.0, fallback=raw)
    atr_multiple = _number(tech.get("atr_move_multiple"))
    atr = _linear_score(atr_multiple, 1.5, 5.0, low_score=40.0, high_score=98.0, fallback=shock)
    return clamp(0.45 * raw + 0.35 * shock + 0.20 * atr)


def setup_score(candidate: dict[str, Any], tech: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    drop = abs(min(_number(candidate.get("drop_pct")) or 0.0, 0.0))
    raw_decline = _linear_score(drop, 15.0, 45.0, low_score=55.0, high_score=95.0, fallback=45.0)
    volatility_shock = _linear_score(_number(tech.get("shock_z")), 1.5, 5.0, low_score=40.0, high_score=98.0, fallback=raw_decline)
    drawdown = abs(min(_number(tech.get("drawdown_from_60d_high_pct")) or -drop, 0.0))
    recent_high_drawdown = _linear_score(drawdown, 15.0, 60.0, low_score=45.0, high_score=92.0, fallback=raw_decline)
    ma_distances = [abs(min(value, 0.0)) for value in (_number(tech.get("sma20_distance_pct")), _number(tech.get("sma50_distance_pct"))) if value is not None]
    ma_dislocation_value = sum(ma_distances) / len(ma_distances) if ma_distances else drop
    moving_average_dislocation = _linear_score(ma_dislocation_value, 10.0, 40.0, low_score=40.0, high_score=95.0, fallback=raw_decline)

    rsi = _number(tech.get("rsi14"))
    if rsi is None:
        rsi_score = min(80.0, raw_decline)
    elif rsi <= 15:
        rsi_score = 95.0
    elif rsi <= 25:
        rsi_score = 86.0
    elif rsi <= 35:
        rsi_score = 68.0
    elif rsi <= 45:
        rsi_score = 40.0
    else:
        rsi_score = 18.0

    rvol = _number(tech.get("relative_volume20"))
    if rvol is None:
        snapshot = candidate.get("raw_snapshot") or {}
        previous = snapshot.get("prevDailyBar") or {}
        daily = snapshot.get("dailyBar") or {}
        previous_volume = _number(previous.get("v")) or _number(candidate.get("prev_volume"))
        current_volume = _number(daily.get("v"))
        rvol = current_volume / previous_volume if previous_volume and current_volume is not None and previous_volume > 0 else None
    volume_anomaly = _linear_score(rvol, 0.8, 4.0, low_score=32.0, high_score=94.0, fallback=45.0)

    relative_candidates = [
        abs(min(value, 0.0))
        for value in (_number(tech.get("market_relative_move_pct")), _number(tech.get("sector_relative_move_pct")))
        if value is not None
    ]
    relative_value = max(relative_candidates) if relative_candidates else None
    relative_move = _linear_score(relative_value, 3.0, 25.0, low_score=35.0, high_score=95.0, fallback=50.0)

    dollar_volume = _number(candidate.get("prev_dollar_volume"))
    if dollar_volume is None:
        liquidity = 35.0
    elif dollar_volume >= 50_000_000:
        liquidity = 95.0
    elif dollar_volume >= 10_000_000:
        liquidity = 84.0
    elif dollar_volume >= 2_000_000:
        liquidity = 67.0
    elif dollar_volume >= 500_000:
        liquidity = 45.0
    else:
        liquidity = 15.0
    spread_pct = _number(candidate.get("spread_pct"))
    if spread_pct is None:
        spread = 35.0
    elif spread_pct <= 0.5:
        spread = 95.0
    elif spread_pct <= 1.0:
        spread = 85.0
    elif spread_pct <= 2.0:
        spread = 68.0
    elif spread_pct <= 5.0:
        spread = 38.0
    else:
        spread = 12.0
    tradability = 0.60 * liquidity + 0.40 * spread

    components = {
        "raw_decline": raw_decline,
        "volatility_shock": volatility_shock,
        "recent_high_drawdown": recent_high_drawdown,
        "moving_average_dislocation": moving_average_dislocation,
        "rsi": rsi_score,
        "volume_anomaly": volume_anomaly,
        "relative_move": relative_move,
        "tradability": tradability,
    }
    weights = SCORING_CONFIG["setup_feature_weights"]
    raw_score = sum(components[key] * float(weights[key]) for key in weights)
    setup_cap, setup_cap_reasons = setup_post_spike_cap(tech)
    score = min(raw_score, setup_cap)
    return round(clamp(score), 1), {
        "component_scores": {key: round(value, 1) for key, value in components.items()},
        "weights": weights,
        "technical_features": tech,
        "liquidity_score": round(liquidity, 1),
        "spread_quality_score": round(spread, 1),
        "raw_setup_score": round(clamp(raw_score), 1),
        "setup_cap": round(setup_cap, 1),
        "setup_cap_reasons": setup_cap_reasons,
        "dislocation_strength": round(_dislocation_strength(tech, _number(candidate.get("drop_pct"))), 1),
    }


def confirmation_score(candidate: dict[str, Any], tech: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    range_position = _number(tech.get("session_range_position"))
    range_score = clamp(range_position if range_position is not None else 30.0)
    from_open = _number(tech.get("return_from_open_pct"))
    intraday_reversal = clamp(50.0 + (from_open or 0.0) * 7.0) if from_open is not None else 35.0
    gap_reclaim = _number(tech.get("gap_reclaim_pct"))
    gap_score = clamp(35.0 + gap_reclaim * 0.75) if gap_reclaim is not None else 40.0
    vwap_distance = _number(tech.get("vwap_distance_pct"))
    if vwap_distance is None:
        vwap_score = 35.0
    elif vwap_distance >= 1.0:
        vwap_score = 88.0
    elif vwap_distance >= 0.0:
        vwap_score = 72.0
    elif vwap_distance >= -1.0:
        vwap_score = 50.0
    else:
        vwap_score = 25.0
    rvol = _number(tech.get("relative_volume20"))
    if rvol is None:
        snapshot = candidate.get("raw_snapshot") or {}
        previous = snapshot.get("prevDailyBar") or {}
        daily = snapshot.get("dailyBar") or {}
        prev_volume = _number(previous.get("v")) or _number(candidate.get("prev_volume"))
        current_volume = _number(daily.get("v"))
        rvol = current_volume / prev_volume if prev_volume and current_volume is not None and prev_volume > 0 else None
    if rvol is None:
        volume_score = 35.0
    elif rvol >= 2.0 and range_score >= 55:
        volume_score = 88.0
    elif rvol >= 1.25 and range_score >= 45:
        volume_score = 70.0
    elif range_score < 25:
        volume_score = 20.0
    else:
        volume_score = 46.0
    spread_pct = _number(candidate.get("spread_pct"))
    if spread_pct is None:
        spread_score = 35.0
    elif spread_pct <= 0.5:
        spread_score = 92.0
    elif spread_pct <= 1.0:
        spread_score = 80.0
    elif spread_pct <= 2.0:
        spread_score = 62.0
    elif spread_pct <= 5.0:
        spread_score = 30.0
    else:
        spread_score = 10.0

    components = {
        "range_position": range_score,
        "intraday_reversal": intraday_reversal,
        "gap_reclaim": gap_score,
        "vwap_reclaim": vwap_score,
        "volume_stabilisation": volume_score,
        "spread_quality": spread_score,
    }
    weights = SCORING_CONFIG["confirmation_feature_weights"]
    score = sum(components[key] * float(weights[key]) for key in weights)
    return round(clamp(score), 1), {
        "component_scores": {key: round(value, 1) for key, value in components.items()},
        "weights": weights,
        "technical_features": {
            key: tech.get(key)
            for key in (
                "session_range_position", "return_from_open_pct", "gap_pct", "gap_reclaim_pct",
                "low_reclaim_pct", "vwap", "vwap_distance_pct", "relative_volume20", "volume_z20",
            )
        },
    }


def structured_catalyst_analysis(
    candidate: dict[str, Any],
    articles: list[dict[str, Any]],
    catalyst_class: str,
    risk_flags: list[str],
    tech: dict[str, Any],
    fundamentals: dict[str, Any] | None,
) -> dict[str, Any]:
    causal_articles, news_relevance_trace = filter_causal_articles(candidate, articles)
    text = _article_text(causal_articles)
    sector_hint = infer_sector_hint(causal_articles)
    filing_risk_flags = list((fundamentals or {}).get("derived_risk_flags") or [])
    effective_risk_flags = sorted(set(filing_risk_flags + direct_news_risk_flags(text)))
    signals = _event_signals(text, effective_risk_flags, sector_hint)
    profile = _event_profile(signals, catalyst_class if causal_articles else "U")
    profile, event_metrics, quantitative_adjustments = apply_quantified_event_hardening(
        signals=signals, profile=profile, text=text, tech=tech
    )
    recognised_signals = [name for name, value in signals.items() if value and name not in {"analyst_action", "analyst_target_cut", "analyst_target_raise", "primary_endpoint_success", "guidance_reaffirmed"}]
    custom_cause = bool(event_metrics.get("quantitative_earnings_event") or event_metrics.get("control_transaction") or event_metrics.get("post_spike_context"))
    cause_recognised = bool(recognised_signals) or signals["analyst_only"] or signals["guidance_reaffirmed"] or custom_cause
    has_news = bool(causal_articles)
    conflicting = bool((signals["temporary_operational"] or signals["operations_resumed"] or signals["broad_sector_risk_off"] or signals["analyst_only"]) and (signals["structural_impairment"] or signals["existential_or_solvency"] or signals["guidance_cut"] or signals["primary_endpoint_failure"] or signals["fda_rejection_or_crl"]))

    reversibility = float(profile["reversibility"])
    horizon_fit = float(profile["horizon"])
    event_damage = float(profile["damage"])
    resilience, fundamental_confidence, fundamental_trace = _fundamental_resilience(fundamentals, signals, effective_risk_flags)

    if signals["guidance_reaffirmed"] and not signals["guidance_cut"]:
        reversibility = max(reversibility, 76.0)
        event_damage = min(event_damage, 30.0)
    if signals["primary_endpoint_success"] and signals["secondary_endpoint_miss"]:
        event_damage = min(event_damage, 45.0)
    if signals["analyst_target_raise"] and signals["analyst_only"]:
        event_damage = min(event_damage, 18.0)
        reversibility = max(reversibility, 86.0)
    if conflicting:
        reversibility = min(reversibility, 35.0)
        event_damage = max(event_damage, 72.0)

    if "clinical_regulatory" in effective_risk_flags and sector_hint == "biotechnology" and not signals["primary_endpoint_success"]:
        event_damage = max(event_damage, 60.0)
    if "dilution" in effective_risk_flags:
        event_damage = max(event_damage, 55.0)
    if "solvency" in effective_risk_flags:
        event_damage = max(event_damage, 90.0)

    dislocation = _dislocation_strength(tech, _number(candidate.get("drop_pct")))
    market_overreaction = clamp(0.65 * dislocation + 0.35 * reversibility - 0.45 * event_damage + 25.0)
    catalyst_score = clamp(0.50 * reversibility + 0.25 * horizon_fit + 0.25 * market_overreaction)
    cause_verified = has_news and cause_recognised
    if not cause_verified:
        catalyst_score = min(catalyst_score, float(SCORING_CONFIG["cause_unknown"]["catalyst_cap"]))

    source_confidence, source_trace = _source_evidence_quality(candidate, causal_articles, cause_recognised=cause_recognised, conflicting=conflicting)
    supporting: list[str] = []
    contradictory: list[str] = []
    if signals["operations_resumed"]:
        supporting.append("Point-in-time evidence says the disruption was resolved or operations resumed.")
    elif signals["temporary_operational"]:
        supporting.append("Point-in-time evidence contains explicit temporary/disruption language.")
    if signals["broad_sector_risk_off"]:
        supporting.append("The retained evidence describes a broad sector/risk-off move rather than clear company-specific impairment.")
    if signals["analyst_only"]:
        supporting.append("The identified catalyst is analyst/sentiment action without a separately recognised operating failure in the retained evidence.")
    if signals["guidance_reaffirmed"]:
        supporting.append("Guidance was described as maintained/reaffirmed in cutoff-valid evidence.")
    if signals["primary_endpoint_success"] and signals["secondary_endpoint_miss"]:
        supporting.append("The primary clinical endpoint was described as intact despite a secondary-endpoint miss.")
    if event_damage >= 70:
        contradictory.append(f"The recognised event profile ({profile['name']}) carries high structural-damage risk.")
    if signals["guidance_cut"]:
        contradictory.append("Cutoff-valid evidence indicates a guidance/forecast reset, which can represent genuine price discovery.")
    if signals["dilution_or_financing"]:
        contradictory.append("Financing/dilution risk is present in the retained evidence.")
    if signals["legal_or_regulatory"] or signals["fraud_or_accounting_credibility"]:
        contradictory.append("Legal/regulatory/accounting credibility risk is present in the retained evidence.")
    if not causal_articles:
        contradictory.append("No ticker-specific causal article survived the relevance filter at the signal cutoff; causal attribution is weak.")
    if conflicting:
        contradictory.append("The retained evidence contains both reversible and structural signals; the model treats this conflict conservatively.")

    analyst_articles = [article for article in causal_articles if _contains_any(f"{article.get('headline') or ''} {article.get('summary') or ''}".lower(), ANALYST_WORDS)]
    if analyst_articles:
        if signals["analyst_target_raise"] and not signals["analyst_target_cut"]:
            analyst_direction = "supportive"
        elif signals["analyst_target_cut"] and not signals["analyst_target_raise"]:
            analyst_direction = "negative"
        elif signals["analyst_target_cut"] and signals["analyst_target_raise"]:
            analyst_direction = "mixed"
        else:
            analyst_direction = "neutral"
    else:
        analyst_direction = "unavailable"

    primary = causal_articles[0].get("headline") if causal_articles else "No independently verified ticker-specific catalyst at the signal cutoff"
    catalyst_type = "structural" if event_damage >= 70 else "temporary" if event_damage <= 30 and reversibility >= 70 else "mixed" if cause_verified else "unknown"
    hard_veto_reason = profile.get("hard_veto_reason")

    return {
        "primary_catalyst": primary,
        "catalyst_category": catalyst_class,
        "catalyst_type": catalyst_type,
        "event_profile": profile["name"],
        "event_signals": signals,
        "reversibility_score": round(reversibility, 1),
        "six_week_horizon_fit": round(horizon_fit, 1),
        "market_overreaction_score": round(market_overreaction, 1),
        "fundamental_damage_risk": round(clamp(event_damage), 1),
        "fundamental_resilience_score": round(resilience, 1),
        "fundamental_evidence_confidence": round(fundamental_confidence, 1),
        "fundamental_trace": fundamental_trace,
        "evidence_confidence": round(source_confidence, 1),
        "evidence_quality_trace": source_trace,
        "supporting_evidence": supporting,
        "contradictory_evidence": contradictory,
        "red_flags": sorted(set(effective_risk_flags)),
        "source_claims": _evidence_items(causal_articles),
        "news_relevance_trace": news_relevance_trace,
        "event_metrics": event_metrics,
        "quantitative_adjustments": quantitative_adjustments,
        "sector_assessment": {
            "sector_hint": sector_hint,
            "rubric": SCORING_CONFIG["sector_rubrics"].get(sector_hint, []),
            "note": "Sector is inferred from point-in-time event text when authoritative sector metadata is unavailable.",
        },
        "analyst_reaction": {
            "coverage_available": bool(analyst_articles),
            "post_event_updates": _evidence_items(analyst_articles, 3),
            "direction": analyst_direction,
        },
        "analysis_summary": f"Rules-based point-in-time catalyst analysis v3 ({profile['name']}); no backend LLM is configured in the current app.",
        "cause_verified": cause_verified,
        "hard_veto": hard_veto_reason is not None,
        "hard_veto_reason": hard_veto_reason,
        "analysis_method": "rules_v3_point_in_time",
        "catalyst_score": round(catalyst_score, 1),
    }


def market_data_completeness(candidate: dict[str, Any], tech: dict[str, Any]) -> tuple[float, list[str]]:
    snapshot = candidate.get("raw_snapshot") or {}
    checks = {
        "prev_close": candidate.get("prev_close"),
        "last_price": candidate.get("last_price"),
        "spread_pct": candidate.get("spread_pct"),
        "prev_dollar_volume": candidate.get("prev_dollar_volume"),
        "prev_daily_bar": snapshot.get("prevDailyBar"),
        "daily_bar": snapshot.get("dailyBar"),
        "latest_trade_ts": candidate.get("latest_trade_ts"),
    }
    missing = [key for key, value in checks.items() if value in (None, {}, [])]
    snapshot_score = (len(checks) - len(missing)) / len(checks) * 100.0
    history_score = _number(tech.get("technical_history_completeness")) or 0.0
    combined = 0.65 * snapshot_score + 0.35 * history_score
    if history_score < 30:
        missing.append("historical_technical_context")
    return round(combined, 1), missing


def damage_cap(damage_risk: float) -> float:
    damage = clamp(damage_risk)
    for band in SCORING_CONFIG["damage"]["caps"]:
        if band["min"] <= damage <= band["max"]:
            return float(band["cap"])
    return 20.0


def final_score(
    *,
    setup: float,
    catalyst: float,
    resilience: float,
    confirmation: float,
    confidence: float,
    damage_risk: float,
    cause_verified: bool,
    hard_veto: bool = False,
    hard_veto_reason: str | None = None,
) -> dict[str, Any]:
    weights = SCORING_CONFIG["weights"]
    core = setup * weights["setup"] + catalyst * weights["catalyst"] + resilience * weights["resilience"] + confirmation * weights["confirmation"]
    neutral = float(SCORING_CONFIG["confidence"]["neutral_prior"])
    confidence_adjusted = neutral + ((core - neutral) * clamp(confidence) / 100.0)
    damage_config = SCORING_CONFIG["damage"]
    penalty = min(
        float(damage_config["penalty_max"]),
        max(0.0, clamp(damage_risk) - float(damage_config["penalty_start"])) * float(damage_config["penalty_per_point"]),
    )
    pre_cap = clamp(confidence_adjusted - penalty)
    cap = damage_cap(damage_risk)
    applied_caps: list[dict[str, Any]] = [{"type": "damage", "cap": cap}]
    if not cause_verified:
        unknown_cap = float(SCORING_CONFIG["cause_unknown"]["final_cap"])
        cap = min(cap, unknown_cap)
        applied_caps.append({"type": "cause_unknown", "cap": unknown_cap})
    if hard_veto:
        cap = 20.0
        applied_caps.append({"type": "hard_veto", "cap": 20.0, "reason": hard_veto_reason})
    score = round(min(pre_cap, cap), 1)
    if hard_veto or score < SCORING_CONFIG["decision_thresholds"]["watch"]:
        verdict = "PASS"
    elif score >= SCORING_CONFIG["decision_thresholds"]["investigate"] and cause_verified:
        verdict = "INVESTIGATE"
    else:
        verdict = "WATCH"
    return {
        "core_score": round(core, 2),
        "confidence_adjusted_score": round(confidence_adjusted, 2),
        "damage_penalty": round(penalty, 2),
        "damage_cap": round(damage_cap(damage_risk), 1),
        "pre_cap_score": round(pre_cap, 2),
        "final_score": score,
        "verdict": verdict,
        "hard_veto": hard_veto,
        "hard_veto_reason": hard_veto_reason,
        "caps_applied": applied_caps,
    }


def score_candidate(candidate: dict[str, Any], articles: list[dict[str, Any]], catalyst_class: str, risk_flags: list[str]) -> dict[str, Any]:
    causal_for_sector, _ = filter_causal_articles(candidate, articles)
    sector_hint = infer_sector_hint(causal_for_sector)
    enrichment = load_runtime_enrichment(candidate, sector_hint)
    scoring_candidate = dict(candidate)
    scoring_candidate["evidence_cutoff"] = enrichment.get("cutoff")
    scoring_candidate["history_bars"] = enrichment.get("history_bars") or []
    scoring_candidate["benchmark_context"] = enrichment.get("benchmark_context") or {}
    scoring_candidate["fundamentals"] = enrichment.get("fundamentals")

    tech = technical_features(scoring_candidate, sector_hint)
    analysis = structured_catalyst_analysis(
        scoring_candidate,
        articles,
        catalyst_class,
        risk_flags,
        tech,
        enrichment.get("fundamentals"),
    )
    setup, setup_trace = setup_score(scoring_candidate, tech)
    confirmation, confirmation_trace = confirmation_score(scoring_candidate, tech)
    catalyst = float(analysis["catalyst_score"])
    resilience = float(analysis["fundamental_resilience_score"])
    damage = float(analysis["fundamental_damage_risk"])
    completeness, missing_market = market_data_completeness(scoring_candidate, tech)
    fundamental_confidence = float(analysis.get("fundamental_evidence_confidence") or 35.0)
    confidence = clamp(0.65 * float(analysis["evidence_confidence"]) + 0.25 * completeness + 0.10 * fundamental_confidence)

    missing_inputs = list(missing_market)
    if not articles:
        missing_inputs.append("company_specific_news")
    if not analysis.get("news_relevance_trace", {}).get("causal_article_count"):
        missing_inputs.append("verified_ticker_specific_catalyst")
    if enrichment.get("fundamentals") is None:
        missing_inputs.append("point_in_time_fundamentals")
    if enrichment.get("errors"):
        missing_inputs.append("enrichment_partial_failure")

    result = final_score(
        setup=setup,
        catalyst=catalyst,
        resilience=resilience,
        confirmation=confirmation,
        confidence=confidence,
        damage_risk=damage,
        cause_verified=bool(analysis["cause_verified"]),
        hard_veto=bool(analysis["hard_veto"]),
        hard_veto_reason=analysis.get("hard_veto_reason"),
    )
    if result["verdict"] == "INVESTIGATE":
        explanation = "The sell-off is statistically dislocated and the verified catalyst appears sufficiently reversible, with structural-damage risk contained by the point-in-time evidence."
    elif result["verdict"] == "WATCH":
        explanation = "The setup has reversion potential, but confirmation, fundamental resilience, catalyst certainty, or evidence coverage is not yet investigate-grade."
    else:
        explanation = "Permanent-damage risk, weak causal evidence, inadequate confirmation, or poor reversion economics dominate the oversold setup."

    compact_history = [
        {key: bar.get(key) for key in ("t", "o", "h", "l", "c", "v", "vw") if bar.get(key) is not None}
        for bar in (enrichment.get("history_bars") or [])[-60:]
        if isinstance(bar, dict)
    ]
    benchmark_evidence: dict[str, Any] = {}
    for symbol, context in (enrichment.get("benchmark_context") or {}).items():
        if not isinstance(context, dict):
            continue
        benchmark_evidence[symbol] = {
            "snapshot": context.get("snapshot") or {},
            "history_bars": [
                {key: bar.get(key) for key in ("t", "o", "h", "l", "c", "v", "vw") if bar.get(key) is not None}
                for bar in (context.get("history_bars") or [])[-60:]
                if isinstance(bar, dict)
            ],
        }

    return {
        "setup_score": setup,
        "catalyst_score": round(catalyst, 1),
        "resilience_score": round(resilience, 1),
        "confirmation_score": confirmation,
        "damage_risk": round(damage, 1),
        "evidence_confidence": round(confidence, 1),
        "model_status": MODEL_STATUS,
        "scoring_model_version": SCORING_MODEL_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "catalyst_prompt_version": CATALYST_PROMPT_VERSION,
        "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
        "calibration_model_version": CALIBRATION_MODEL_VERSION,
        "target_definition": TARGET_DEFINITION,
        "catalyst_analysis": analysis,
        "missing_inputs": sorted(set(missing_inputs)),
        "explanation": explanation,
        "point_in_time_enrichment": {
            "mode": enrichment.get("mode"),
            "errors": enrichment.get("errors") or [],
            "history_requests": enrichment.get("history_requests") or 0,
            "benchmark_requests": enrichment.get("benchmark_requests") or 0,
            "history_bars": compact_history,
            "benchmark_context": benchmark_evidence,
            "fundamentals": enrichment.get("fundamentals"),
        },
        "calculation_trace": {
            "formula": "core=.25*setup+.35*catalyst+.15*resilience+.25*confirmation; confidence=50+(core-50)*confidence/100; damage penalty/caps then apply",
            "setup": setup_trace,
            "confirmation": confirmation_trace,
            "market_data_completeness": completeness,
            "confidence_inputs": {
                "event_evidence_confidence": analysis["evidence_confidence"],
                "market_data_completeness": completeness,
                "fundamental_evidence_confidence": fundamental_confidence,
                "weights": {"event": 0.65, "market": 0.25, "fundamentals": 0.10},
            },
            "final": result,
            "config": SCORING_CONFIG,
        },
        **result,
    }


def evidence_snapshot_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
        "cause_unknown": SCORING_CONFIG["cause_unknown"],
        "decision_thresholds": SCORING_CONFIG["decision_thresholds"],
        "calibration": SCORING_CONFIG["calibration"],
    }
