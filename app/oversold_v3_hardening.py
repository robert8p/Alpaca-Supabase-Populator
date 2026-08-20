from __future__ import annotations

import re
from typing import Any

GENERIC_HEADLINE_PATTERNS = (
    "stocks moving", "stocks are on investors", "stocks are on investor", "here are 20 stocks",
    "here are 10 stocks", "market-moving news", "market moving news", "market summary",
    "stock market today", "pre-market session", "premarket session", "intraday session",
    "after-market session", "after market session", "dow gains", "dow falls", "nasdaq down",
    "crude oil", "home depot", "keysight shares", "flexsteel industries shares",
)
LEGAL_NAME_STOPWORDS = {
    "inc", "incorporated", "corp", "corporation", "company", "co", "limited", "ltd", "plc",
    "holdings", "holding", "group", "ordinary", "common", "stock", "shares", "share", "class",
    "the", "sa", "nv", "ag", "lp",
}
EVENT_TERMS = (
    "earnings", "eps", "sales", "revenue", "guidance", "forecast", "outlook", "offering",
    "private placement", "convertible", "warrant", "financing", "trial", "endpoint", "fda", "ema",
    "approval", "contract", "award", "outage", "disruption", "production", "shipment", "recall",
    "lawsuit", "investigation", "subpoena", "fraud", "material weakness", "resign", "downgrade",
    "upgrade", "price target", "rating", "bankruptcy", "going concern", "merger", "acquisition",
    "definitive agreement", "stake", "strategic", "halt", "rally", "surge", "plunge", "dips",
    "falls", "falling", "slips", "cools", "profit-taking", "profit taking",
)

SALES_SURPRISE_RE = re.compile(
    r"(?:sales|revenue)\s+\$?([\d,.]+)\s*([KMB]?)\s+"
    r"(miss(?:es)?|beat(?:s)?)\s+\$?([\d,.]+)\s*([KMB]?)\s+(?:estimate|est)",
    re.IGNORECASE,
)
GUIDANCE_RANGE_RE = re.compile(
    r"(?:sees|expects|guides?|forecast(?:s)?)\b.*?(?:sales|revenue).*?"
    r"\$?([\d,.]+)\s*([KMB]?)\s*-\s*\$?([\d,.]+)\s*([KMB]?).*?"
    r"(?:vs|versus)\s+\$?([\d,.]+)\s*([KMB]?)\s*(?:estimate|est)",
    re.IGNORECASE,
)
YOY_SALES_RE = re.compile(
    r"(?:sales|revenue)\s+\$?([\d,.]+)\s*([KMB]?)\s+(?:down\s+from|vs\.?\s*\$?)\s*\$?([\d,.]+)\s*([KMB]?)\s*(?:yoy|year[- ]over[- ]year)?",
    re.IGNORECASE,
)
STAKE_RE = re.compile(r"(\d+(?:\.\d+)?)%\s+stake", re.IGNORECASE)
MONEY_RE = re.compile(r"\$([\d,.]+)\s*([KMB])\b", re.IGNORECASE)
POST_SPIKE_RE = re.compile(r"(\d+(?:\.\d+)?)%\s+(?:intraday\s+)?(?:rally|surge|gain|jump)", re.IGNORECASE)


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _scaled(value: str, suffix: str) -> float:
    factor = {"": 1.0, "K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}
    return float(value.replace(",", "")) * factor.get(suffix.upper(), 1.0)


def _company_tokens(name: Any) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(name or "").lower())
    return [token for token in tokens if len(token) >= 4 and token not in LEGAL_NAME_STOPWORDS][:6]


def article_relevance(candidate: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    headline = str(article.get("headline") or "")
    summary = str(article.get("summary") or "")
    text = f"{headline} {summary}"
    lower = text.lower()
    headline_lower = headline.lower()
    symbol = str(candidate.get("symbol") or "").upper()
    symbols = {str(item).upper() for item in article.get("symbols", []) if item}
    symbol_count = len(symbols)
    ticker_mentioned = bool(symbol and re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", text, re.IGNORECASE))
    company_tokens = _company_tokens(candidate.get("name"))
    company_hits = [token for token in company_tokens if token in lower]
    company_in_headline = any(token in headline_lower for token in company_tokens)
    generic = any(pattern in headline_lower for pattern in GENERIC_HEADLINE_PATTERNS)
    event_term = any(term in lower for term in EVENT_TERMS)

    if symbol_count == 1 and symbol in symbols:
        relevance = 78.0
    elif symbol in symbols and symbol_count <= 3:
        relevance = 48.0
    elif symbol in symbols:
        relevance = 12.0
    else:
        relevance = 0.0
    if ticker_mentioned:
        relevance += 18.0
    if company_hits:
        relevance += min(24.0, 8.0 * len(company_hits))
    if company_in_headline:
        relevance += 10.0
    if event_term:
        relevance += 7.0
    if generic:
        relevance -= 25.0
        if not ticker_mentioned and not company_hits:
            relevance = min(relevance, 12.0)
    relevance = max(0.0, min(100.0, relevance))
    if relevance >= 70.0 and event_term:
        kind = "direct_event"
    elif relevance >= 48.0:
        kind = "direct_context"
    else:
        kind = "ambient"
    return {
        "score": round(relevance, 1),
        "kind": kind,
        "generic": generic,
        "ticker_mentioned": ticker_mentioned,
        "company_token_hits": company_hits,
        "symbol_count": symbol_count,
        "event_term": event_term,
    }


def filter_causal_articles(candidate: dict[str, Any], articles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    relevant: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        relevance = article_relevance(candidate, article)
        trace.append({
            "id": article.get("id"), "headline": article.get("headline"),
            "source": article.get("source"), **relevance,
        })
        if relevance["score"] >= 48.0:
            enriched = dict(article)
            enriched["_causal_relevance"] = relevance
            relevant.append(enriched)
    relevant.sort(
        key=lambda item: (
            -float((item.get("_causal_relevance") or {}).get("score") or 0.0),
            str(item.get("created_at") or ""),
        )
    )
    return relevant, {
        "retained_article_count": len(articles),
        "causal_article_count": len(relevant),
        "ambient_article_count": max(0, len(articles) - len(relevant)),
        "articles": trace,
    }


def quantified_event_metrics(text: str) -> dict[str, Any]:
    sales: list[dict[str, Any]] = []
    for actual, actual_suffix, direction, estimate, estimate_suffix in SALES_SURPRISE_RE.findall(text):
        actual_value = _scaled(actual, actual_suffix)
        estimate_value = _scaled(estimate, estimate_suffix)
        if estimate_value <= 0:
            continue
        surprise = ((actual_value / estimate_value) - 1.0) * 100.0
        sales.append({"actual": actual_value, "estimate": estimate_value, "direction": direction.lower(), "surprise_pct": surprise})

    guidance: list[float] = []
    for low, low_suffix, high, high_suffix, estimate, estimate_suffix in GUIDANCE_RANGE_RE.findall(text):
        low_value = _scaled(low, low_suffix)
        high_value = _scaled(high, high_suffix)
        estimate_value = _scaled(estimate, estimate_suffix)
        if estimate_value > 0:
            guidance.append((((low_value + high_value) / 2.0) / estimate_value - 1.0) * 100.0)

    yoy_declines: list[float] = []
    for current, current_suffix, prior, prior_suffix in YOY_SALES_RE.findall(text):
        current_value = _scaled(current, current_suffix)
        prior_value = _scaled(prior, prior_suffix)
        if prior_value > 0:
            yoy_declines.append((1.0 - current_value / prior_value) * 100.0)

    stake_values = [float(value) for value in STAKE_RE.findall(text)]
    money_values = [_scaled(value, suffix) for value, suffix in MONEY_RE.findall(text)]
    prior_spikes = [float(value) for value in POST_SPIKE_RE.findall(text)]
    return {
        "sales_surprises": sales,
        "worst_sales_surprise_pct": min((item["surprise_pct"] for item in sales), default=None),
        "guidance_shortfalls_pct": guidance,
        "worst_guidance_shortfall_pct": min(guidance, default=None),
        "yoy_sales_declines_pct": yoy_declines,
        "worst_yoy_sales_decline_pct": max(yoy_declines, default=None),
        "stake_pct": max(stake_values) if stake_values else None,
        "largest_money_amount": max(money_values) if money_values else None,
        "prior_spike_pct": max(prior_spikes) if prior_spikes else None,
    }


def apply_quantified_event_hardening(
    *,
    signals: dict[str, bool],
    profile: dict[str, Any],
    text: str,
    tech: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    metrics = quantified_event_metrics(text)
    adjusted = dict(profile)
    reasons: list[str] = []
    damage = float(adjusted.get("damage") or 45.0)
    reversibility = float(adjusted.get("reversibility") or 30.0)
    horizon = float(adjusted.get("horizon") or 35.0)

    sales_miss = _number(metrics.get("worst_sales_surprise_pct"))
    guidance_shortfall = _number(metrics.get("worst_guidance_shortfall_pct"))
    yoy_decline = _number(metrics.get("worst_yoy_sales_decline_pct"))
    stake = _number(metrics.get("stake_pct"))
    narrative_spike = _number(metrics.get("prior_spike_pct"))
    sma20 = _number(tech.get("sma20_distance_pct"))
    shock_z = _number(tech.get("shock_z"))

    quantitative_earnings = False
    if sales_miss is not None and sales_miss < -2.0:
        quantitative_earnings = True
        miss = abs(sales_miss)
        if miss >= 30:
            damage = max(damage, 78.0); reversibility = min(reversibility, 24.0); horizon = min(horizon, 30.0)
            reasons.append("sales_miss_ge_30pct")
        elif miss >= 15:
            damage = max(damage, 68.0); reversibility = min(reversibility, 35.0); horizon = min(horizon, 42.0)
            reasons.append("sales_miss_ge_15pct")
        elif miss >= 5:
            damage = max(damage, 58.0); reversibility = min(reversibility, 44.0)
            reasons.append("sales_miss_ge_5pct")
    if guidance_shortfall is not None and guidance_shortfall < -2.0:
        quantitative_earnings = True
        miss = abs(guidance_shortfall)
        if miss >= 15:
            damage = max(damage, 75.0); reversibility = min(reversibility, 28.0); horizon = min(horizon, 34.0)
            reasons.append("guidance_shortfall_ge_15pct")
        elif miss >= 7:
            damage = max(damage, 65.0); reversibility = min(reversibility, 38.0)
            reasons.append("guidance_shortfall_ge_7pct")
        elif miss >= 3:
            damage = max(damage, 56.0)
            reasons.append("guidance_shortfall_ge_3pct")
    if yoy_decline is not None and yoy_decline > 5.0:
        quantitative_earnings = True
        if yoy_decline >= 40:
            damage = max(damage, 80.0); reversibility = min(reversibility, 24.0); horizon = min(horizon, 30.0)
            reasons.append("yoy_revenue_decline_ge_40pct")
        elif yoy_decline >= 20:
            damage = max(damage, 68.0); reversibility = min(reversibility, 34.0)
            reasons.append("yoy_revenue_decline_ge_20pct")
        elif yoy_decline >= 10:
            damage = max(damage, 58.0)
            reasons.append("yoy_revenue_decline_ge_10pct")

    if quantitative_earnings:
        signals["earnings_miss"] = True
        if adjusted.get("name") == "unknown":
            adjusted["name"] = "quantified_earnings_deterioration"

    transaction = False
    if stake is not None and stake >= 50.0:
        transaction = True
        if stake >= 90.0:
            damage = max(damage, 72.0); reversibility = min(reversibility, 32.0); horizon = min(horizon, 40.0)
            reasons.append("controlling_stake_ge_90pct")
        else:
            damage = max(damage, 60.0); reversibility = min(reversibility, 42.0)
            reasons.append("controlling_stake_ge_50pct")
        if adjusted.get("name") == "unknown":
            adjusted["name"] = "control_transaction"

    post_spike = bool(
        (narrative_spike is not None and narrative_spike >= 50.0)
        or (sma20 is not None and sma20 >= 40.0)
        or (sma20 is not None and sma20 >= 20.0 and (shock_z is None or shock_z < 2.0))
    )
    if post_spike and adjusted.get("name") == "unknown" and not quantitative_earnings and not transaction:
        adjusted["name"] = "post_spike_unwind"
        damage = min(damage, 35.0)
        reversibility = max(reversibility, 60.0)
        horizon = max(horizon, 58.0)
        reasons.append("post_spike_unwind_context")

    adjusted["damage"] = max(0.0, min(100.0, damage))
    adjusted["reversibility"] = max(0.0, min(100.0, reversibility))
    adjusted["horizon"] = max(0.0, min(100.0, horizon))
    metrics["quantitative_earnings_event"] = quantitative_earnings
    metrics["control_transaction"] = transaction
    metrics["post_spike_context"] = post_spike
    return adjusted, metrics, reasons


def setup_post_spike_cap(tech: dict[str, Any]) -> tuple[float, list[str]]:
    sma20 = _number(tech.get("sma20_distance_pct"))
    sma50 = _number(tech.get("sma50_distance_pct"))
    shock_z = _number(tech.get("shock_z"))
    cap = 100.0
    reasons: list[str] = []
    baseline = max(value for value in (sma20, sma50) if value is not None) if any(value is not None for value in (sma20, sma50)) else None
    if baseline is not None and baseline >= 100.0:
        cap = 30.0; reasons.append("still_over_100pct_above_moving_average_baseline")
    elif baseline is not None and baseline >= 50.0:
        cap = 40.0; reasons.append("still_over_50pct_above_moving_average_baseline")
    elif baseline is not None and baseline >= 20.0 and (shock_z is None or shock_z < 2.0):
        cap = 50.0; reasons.append("recent_spike_unwind_not_baseline_oversold")
    elif baseline is not None and baseline >= 10.0 and (shock_z is None or shock_z < 1.5):
        cap = 55.0; reasons.append("price_remains_above_recent_baseline")
    return cap, reasons


def direct_news_risk_flags(text: str) -> list[str]:
    lower = text.lower()
    mapping = {
        "solvency": ("bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern", "debt default"),
        "dilution": ("public offering", "registered direct", "at-the-market", "at the market", "private placement", "dilution", "convertible", "warrant", "secondary offering"),
        "clinical_regulatory": ("phase 3", "phase iii", "clinical trial", "primary endpoint", "secondary endpoint", "fda", "complete response letter", "crl"),
        "earnings_guidance": ("earnings", "eps", "sales", "revenue", "guidance", "forecast", "outlook"),
        "legal": ("lawsuit", "subpoena", "investigation", "fraud", "material weakness"),
        "management": ("ceo resign", "chief executive resign", "cfo resign"),
        "delisting": ("delist", "nasdaq deficiency", "listing deficiency"),
    }
    return sorted(flag for flag, terms in mapping.items() if any(term in lower for term in terms))


def classify_news_for_candidate(candidate: dict[str, Any], articles: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    causal, trace = filter_causal_articles(candidate, articles)
    if not causal:
        return "U", "No ticker-specific causal news was verified at the point-in-time evidence cutoff.", ["no_news"] if not articles else []
    text = " ".join(f"{item.get('headline') or ''} {item.get('summary') or ''}" for item in causal).lower()
    flags = direct_news_risk_flags(text)
    if any(term in text for term in ("bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern", "debt default", "fraud investigation", "liquidation")):
        return "E", "Ticker-specific evidence indicates existential or integrity risk.", flags
    if any(term in text for term in ("permanent closure", "terminates program", "discontinues program", "patent invalid", "loses key customer", "business model impairment")):
        return "D", "Ticker-specific evidence indicates potential structural impairment.", flags
    if any(term in text for term in ("temporary", "temporarily", "outage", "shipment delay", "technical issue", "production delay", "operations resume", "short-term disruption")):
        return "B", "Ticker-specific evidence indicates a potentially temporary/reversible disruption.", flags
    metrics = quantified_event_metrics(text)
    if flags or metrics.get("stake_pct") is not None or metrics.get("prior_spike_pct") is not None:
        return "C", "Ticker-specific evidence identifies a material repricing event requiring economic severity scoring.", flags
    if any(term in text for term in ("downgrade", "upgrade", "price target", "analyst", "rating")):
        flags.append("analyst_only")
        return "A", "Ticker-specific evidence is dominated by analyst/sentiment action rather than a new operating event.", sorted(set(flags))
    return "U", "Ticker-specific news exists, but no negative causal event is confidently identified.", flags
