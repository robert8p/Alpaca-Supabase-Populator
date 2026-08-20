from __future__ import annotations

import math
import re
from typing import Any

SCORING_MODEL_VERSION = "oversold_reversion_score_v2_1"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v2"
CATALYST_PROMPT_VERSION = "catalyst_rules_prompt_v2"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v2"
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
    "setup": {
        "minimum_history_bars": 15,
        "history_target_bars": 60,
        "post_spike_caps": {
            "baseline_100pct": 30,
            "baseline_50pct": 40,
            "pre5_100_current20": 40,
            "pre5_50_current10": 50,
        },
    },
}

LEGAL_NAME_STOPWORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "limited", "ltd",
    "plc", "holdings", "holding", "group", "ordinary", "common", "stock", "shares",
    "share", "class", "the", "sa", "nv", "ag", "lp",
}
GENERIC_MARKET_HEADLINE_PATTERNS = (
    "stocks moving", "stocks are on investors", "stocks are on investor", "here are 20 stocks",
    "here are 10 stocks", "market summary", "market-moving news", "stock market today",
    "pre-market session", "premarket session", "intraday session", "after-market session",
    "after market session", "movers",
)
EVENT_TERMS = (
    "earnings", "results", "eps", "sales", "revenue", "guidance", "forecast", "outlook",
    "offering", "private placement", "convertible", "warrant", "at-the-market", "financing",
    "trial", "endpoint", "fda", "ema", "complete response letter", "crl", "approval",
    "contract", "award", "outage", "disruption", "production", "shipment", "recall",
    "lawsuit", "investigation", "subpoena", "fraud", "material weakness", "resign",
    "downgrade", "upgrade", "price target", "rating", "bankruptcy", "going concern",
    "merger", "acquisition", "definitive agreement", "stake", "strategic", "halt",
    "rally", "surge", "plunge", "dips", "falls", "falling", "slips", "cools",
)
EXISTENTIAL_WORDS = (
    "bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern",
    "payment default", "debt default", "accounting fraud", "fraud investigation", "liquidation",
)
STRUCTURAL_WORDS = (
    "permanently close", "permanent closure", "terminates program", "terminated program",
    "discontinues program", "discontinued program", "patent invalid", "patent loss",
    "loses key customer", "lost key customer", "license terminated", "material weakness",
    "collapse in demand", "covenant default",
)
TRANSIENT_WORDS = (
    "temporary", "temporarily", "outage", "weather disruption", "shipment delay", "shipping delay",
    "supply disruption", "technical issue", "production delay", "operations resume", "resumes operations",
    "short-term disruption", "one-time", "one time",
)
ANALYST_WORDS = ("downgrade", "upgrade", "price target", "analyst", "rating")
DILUTION_WORDS = (
    "public offering", "registered direct", "at-the-market", "private placement", "dilution",
    "convertible", "warrant", "securities purchase", "common shares", "common stock offering",
)
BIOTECH_FAILURE_WORDS = (
    "failed primary endpoint", "did not meet the primary endpoint", "missed primary endpoint",
    "primary endpoint was not met", "failed pivotal", "phase 3 failed", "phase iii failed",
)
REGULATORY_FAILURE_WORDS = (
    "complete response letter", "fda rejection", "fda rejects", "not approved", "refuse to file",
)
POSITIVE_TRIAL_WORDS = (
    "met the primary endpoint", "achieved primary endpoint", "positive phase 3", "positive phase iii",
    "fda approval", "fda approves",
)
NEGATIVE_EARNINGS_WORDS = (
    "misses estimate", "miss estimate", "misses estimates", "revenue miss", "sales miss",
    "wider loss", "widens loss", "down from", "cuts guidance", "lowers guidance",
    "reduces guidance", "withdraws guidance", "cuts forecast", "lowers forecast",
)
POSITIVE_EARNINGS_WORDS = (
    "beats estimate", "beats estimates", "raises guidance", "raises forecast",
    "reaffirms guidance", "reiterates guidance", "record revenue",
)
PRIMARY_LIKE_SOURCES = (
    "businesswire", "business wire", "globenewswire", "globe newswire", "pr newswire",
    "accesswire", "sec", "company",
)
SALES_SURPRISE_RE = re.compile(
    r"(?:sales|revenue)\s+\$?([\d,.]+)\s*([KMB]?)\s+"
    r"(miss(?:es)?|beat(?:s)?)\s+\$?([\d,.]+)\s*([KMB]?)\s+(?:estimate|est)",
    re.IGNORECASE,
)
GUIDANCE_RANGE_RE = re.compile(
    r"(?:sees|expects|guides?)\b.*?(?:sales|revenue).*?"
    r"\$?([\d,.]+)\s*([KMB]?)\s*-\s*\$?([\d,.]+)\s*([KMB]?).*?"
    r"(?:vs|versus)\s+\$?([\d,.]+)\s*([KMB]?)\s*(?:estimate|est)",
    re.IGNORECASE,
)
YOY_SALES_RE = re.compile(
    r"(?:sales|revenue)\s+\$?([\d,.]+)\s*([KMB]?)\s+down\s+from\s+\$?([\d,.]+)\s*([KMB]?)",
    re.IGNORECASE,
)
MONEY_RE = re.compile(r"\$([\d,.]+)\s*([KMB])\b", re.IGNORECASE)
STAKE_RE = re.compile(r"(\d+(?:\.\d+)?)%\s+stake", re.IGNORECASE)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _scaled_number(value: str, suffix: str) -> float:
    number = float(value.replace(",", ""))
    multiplier = {"": 1.0, "K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}
    return number * multiplier.get(suffix.upper(), 1.0)


def _piecewise(value: float | None, points: list[tuple[float, float]], default: float = 35.0) -> float:
    if value is None or not points:
        return default
    ordered = sorted(points, key=lambda item: item[0])
    if value <= ordered[0][0]:
        return clamp(ordered[0][1])
    if value >= ordered[-1][0]:
        return clamp(ordered[-1][1])
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:], strict=True):
        if x0 <= value <= x1:
            weight = (value - x0) / (x1 - x0) if x1 != x0 else 1.0
            return clamp(y0 + (y1 - y0) * weight)
    return default


def _article_text(articles: list[dict[str, Any]]) -> str:
    return " ".join(f"{a.get('headline') or ''} {a.get('summary') or ''}" for a in articles).lower()


def _company_tokens(name: Any) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(name or "").lower())
    return [token for token in tokens if len(token) >= 4 and token not in LEGAL_NAME_STOPWORDS][:5]


def article_relevance(candidate: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    headline = str(article.get("headline") or "")
    summary = str(article.get("summary") or "")
    text = f"{headline} {summary}".lower()
    headline_lower = headline.lower()
    symbol = str(candidate.get("symbol") or "").upper()
    symbols = {str(item).upper() for item in article.get("symbols", []) if item}
    symbol_count = len(symbols)
    ticker_mentioned = bool(symbol and re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", f"{headline} {summary}", re.IGNORECASE))
    company_tokens = _company_tokens(candidate.get("name"))
    company_hits = [token for token in company_tokens if token in text]
    company_in_headline = any(token in headline_lower for token in company_tokens)
    generic = any(pattern in headline_lower for pattern in GENERIC_MARKET_HEADLINE_PATTERNS)
    event_term = any(term in text for term in EVENT_TERMS)

    relevance = 5.0
    if symbol_count == 1 and symbol in symbols:
        relevance = 70.0
    elif symbol_count <= 3 and symbol in symbols:
        relevance = 50.0
    elif symbol in symbols:
        relevance = 15.0
    if ticker_mentioned:
        relevance += 20.0
    if company_hits:
        relevance += min(20.0, 8.0 * len(company_hits))
    if company_in_headline:
        relevance += 12.0
    if event_term:
        relevance += 8.0
    if generic:
        relevance -= 25.0
        if not ticker_mentioned and not company_hits:
            relevance = min(relevance, 15.0)
    relevance = clamp(relevance)

    if relevance >= 70 and event_term and not (generic and relevance < 85):
        kind = "direct_event"
    elif relevance >= 50:
        kind = "direct_context"
    else:
        kind = "ambient"
    return {
        "score": round(relevance, 1),
        "kind": kind,
        "generic_market_article": generic,
        "ticker_mentioned": ticker_mentioned,
        "company_token_hits": company_hits,
        "symbol_count": symbol_count,
        "event_term": event_term,
    }


def filter_relevant_articles(candidate: dict[str, Any], articles: list[dict[str, Any]], *, minimum_relevance: float = 45.0) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        relevance = article_relevance(candidate, article)
        if relevance["score"] < minimum_relevance:
            continue
        enriched = dict(article)
        enriched["_relevance"] = relevance
        ranked.append(enriched)
    ranked.sort(key=lambda item: (-float((item.get("_relevance") or {}).get("score") or 0.0), str(item.get("created_at") or "")))
    return ranked


def _evidence_items(articles: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for article in articles[:limit]:
        relevance = article.get("_relevance") or {}
        items.append({
            "id": article.get("id"), "headline": article.get("headline"), "source": article.get("source"),
            "published_at": article.get("created_at"), "url": article.get("url"),
            "relevance_score": relevance.get("score"), "evidence_kind": relevance.get("kind"),
        })
    return items


def infer_sector_hint(articles: list[dict[str, Any]], fundamentals: dict[str, Any] | None = None) -> str:
    detail = (fundamentals or {}).get("ticker_details") or {}
    sic = str(detail.get("sic_description") or "").lower()
    text = f"{sic} " + _article_text(articles)
    if any(w in text for w in ("pharmaceutical", "biotech", "biological", "clinical trial", "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii", "fda", "ema", "endpoint", "drug candidate")):
        return "biotechnology"
    if any(w in text for w in ("bank", "financial", "deposits", "capital ratio", "tier 1", "loan losses", "net interest margin", "funding stress")):
        return "financials"
    if any(w in text for w in ("software", "saas", "arr", "annual recurring revenue", "net retention", "churn", "cybersecurity")):
        return "software"
    if any(w in text for w in ("industrial", "manufacturing", "plant", "production", "factory", "order book", "backlog", "supply chain")):
        return "industrials"
    if any(w in text for w in ("retail", "consumer", "comparable sales", "same-store sales", "inventory", "promotional")):
        return "consumer"
    return "unknown"
