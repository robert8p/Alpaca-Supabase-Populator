from __future__ import annotations

"""Observable evidence checks for the Guard, independent of upstream scores."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from app.reversion_guard_policy import NY, _num, _parse_ts

# Operational freshness limits, not a fitted trading edge or a market-hours calendar.
MAX_QUOTE_AGE_SECONDS = 300
MAX_TRADE_AGE_SECONDS = 900


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _source_timestamp(value: Any) -> datetime | None:
    timestamp = _parse_ts(value)
    if timestamp and isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        # A date-only filing record proves no particular intraday availability.
        return timestamp + timedelta(days=1)
    return timestamp


def technical_inputs(candidate: dict[str, Any]) -> dict[str, Any]:
    analysis = _dict(candidate.get("catalyst_analysis"))
    snapshot = _dict(candidate.get("evidence_snapshot"))
    stored = _dict(candidate.get("technical_inputs")) or _dict(snapshot.get("technical_inputs"))
    output: dict[str, Any] = {}
    for part in (
        _dict(stored.get("setup")), _dict(stored.get("confirmation")), stored,
        _dict(analysis.get("technical_features")), _dict(candidate.get("technical_features")),
    ):
        output.update(part)
    return output


def market_data(candidate: dict[str, Any]) -> dict[str, Any]:
    snapshot = _dict(candidate.get("evidence_snapshot"))
    return {**_dict(snapshot.get("market_data")), **_dict(candidate.get("market_data")), **candidate}


def source_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep source content that was available by cutoff; never verify from a score."""
    cutoff = _parse_ts(candidate.get("evidence_cutoff") or candidate.get("signal_timestamp"))
    analysis = _dict(candidate.get("catalyst_analysis"))
    integrity = _dict(analysis.get("evidence_integrity"))
    context_ids = {str(value) for value in integrity.get("context_only_article_ids", [])}
    rejected_ids = {
        str(item.get("id")) for item in integrity.get("excluded_articles", []) if isinstance(item, dict)
    }
    status = str(candidate.get("cause_verification_status") or analysis.get("cause_verification_status") or
                 analysis.get("verification_status") or "UNVERIFIED").upper()
    verified_claim = candidate.get("cause_verified", analysis.get("cause_verified")) is True
    if "cause_verified" not in candidate and "cause_verified" not in analysis:
        verified_claim = status == "VERIFIED"
    articles = candidate.get("headlines") or candidate.get("evidence_news") or []
    symbol = str(candidate.get("symbol") or "").upper()
    name = str(candidate.get("name") or "").lower()
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for article in articles if isinstance(articles, list) else []:
        if not isinstance(article, dict):
            continue
        primary = _dict(article.get("primary_evidence"))
        metadata = _dict(primary.get("metadata"))
        timestamp_values = [primary.get("available_at"), article.get("available_at"),
                            article.get("created_at"), article.get("published_at"), article.get("updated_at")]
        supplied = [value for value in timestamp_values if value is not None and value != ""]
        timestamps = [_source_timestamp(value) for value in supplied]
        malformed_timestamp = any(value is None for value in timestamps)
        available = max((value for value in timestamps if value is not None), default=None)
        article_id = str(article.get("id"))
        content = " ".join(str(article.get(key) or "") for key in ("headline", "summary", "content"))
        url = urlparse(str(article.get("url") or primary.get("url") or ""))
        symbols = article.get("symbols") or article.get("tickers") or []
        if isinstance(symbols, str):
            symbols = [symbols]
        related = symbol in {str(item).upper() for item in symbols}
        related = related or bool(name and name in content.lower())
        related = related or bool(symbol and re.search(r"(?<!\w)" + re.escape(symbol) + r"(?!\w)", content))
        reason = None
        if cutoff is None or available is None or malformed_timestamp:
            reason = "Missing evidence cutoff or source availability timestamp"
        elif available > cutoff:
            reason = "Source appeared after the evidence cutoff"
        elif article_id in rejected_ids:
            reason = "Upstream integrity check excluded this source"
        elif metadata.get("context_only") or article_id in context_ids:
            reason = "Filing metadata establishes a document, not an economic cause"
        elif url.scheme not in {"http", "https"} or not url.netloc:
            reason = "No traceable source URL"
        elif not related:
            reason = "Source cannot be attributed to this issuer"
        elif re.fullmatch(r".*filed\s+form\s+[\w/-]+\s*[—–-]?\s*(?:items?\s+[\d.,\s]+)?[.]?", content.strip(), re.I):
            reason = "Filing metadata alone does not establish why the price fell"
        if reason:
            excluded.append({"id": article.get("id"), "reason": reason})
        else:
            accepted.append(article)
    return {
        "upstream_verification_status": status,
        "upstream_cause_verified": verified_claim,
        "eligible_articles": accepted,
        "eligible_source_count": len(accepted),
        "excluded_articles": excluded,
        "cutoff": cutoff.isoformat() if cutoff else None,
        "integrity_version": integrity.get("version"),
    }


def execution_evidence(candidate: dict[str, Any], *, as_of: datetime | None = None) -> dict[str, Any]:
    now = _parse_ts(as_of) or datetime.now(UTC)
    cutoff = _parse_ts(candidate.get("evidence_cutoff") or candidate.get("signal_timestamp"))
    values = market_data(candidate)
    snapshot = _dict(values.get("raw_snapshot"))
    quote = _dict(snapshot.get("latestQuote"))
    trade = _dict(snapshot.get("latestTrade"))
    upstream = _dict(technical_inputs(candidate).get("execution_evidence"))
    bid = _num(values.get("bid"))
    ask = _num(values.get("ask"))
    bid = bid if bid is not None else _num(quote.get("bp", upstream.get("bid")))
    ask = ask if ask is not None else _num(quote.get("ap", upstream.get("ask")))
    quote_ts = _parse_ts(quote.get("t") or values.get("latest_quote_ts") or upstream.get("latest_quote_timestamp"))
    trade_ts = _parse_ts(values.get("latest_trade_ts") or trade.get("t") or upstream.get("latest_trade_timestamp"))
    price = _num(values.get("last_price"))
    quote_age = (now - quote_ts).total_seconds() if quote_ts else None
    trade_age = (now - trade_ts).total_seconds() if trade_ts else None
    issues: list[str] = []
    if cutoff is None:
        issues.append("Evidence cutoff is unavailable")
    elif cutoff > now:
        issues.append("Evidence cutoff is in the future")
    quote_valid = bid is not None and ask is not None and 0 < bid <= ask
    if not quote_valid:
        issues.append("Current bid/ask is missing, invalid or crossed")
    if price is None or price <= 0:
        issues.append("Reference trade price is unavailable")
    for label, timestamp, age, limit in (
        ("Quote", quote_ts, quote_age, MAX_QUOTE_AGE_SECONDS),
        ("Trade", trade_ts, trade_age, MAX_TRADE_AGE_SECONDS),
    ):
        if timestamp is None:
            issues.append(f"{label} timestamp is unavailable")
        elif (cutoff is not None and timestamp > cutoff) or age < 0:
            issues.append(f"{label} timestamp is after the evidence cutoff or in the future")
        elif age > limit:
            issues.append(f"{label} is stale ({age:.0f}s old; limit {limit}s)")
    if upstream.get("point_in_time_valid") is False or upstream.get("current_quote_valid") is False:
        issues.append("Upstream execution integrity check failed")
    return {
        "ready": not issues,
        "status": "CURRENT" if not issues else "UNAVAILABLE_OR_STALE",
        "issues": issues,
        "bid": bid,
        "ask": ask,
        "spread_pct": (ask - bid) / ((ask + bid) / 2) * 100 if quote_valid else None,
        "quote_timestamp": quote_ts.isoformat() if quote_ts else None,
        "trade_timestamp": trade_ts.isoformat() if trade_ts else None,
        "quote_age_seconds": quote_age,
        "trade_age_seconds": trade_age,
        "assessed_at": now.isoformat(),
        "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
        "max_trade_age_seconds": MAX_TRADE_AGE_SECONDS,
    }


def higher_low_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    """Confirm two observed intraday swing lows; daily aggregates cannot prove them."""
    values = market_data(candidate)
    technical = technical_inputs(candidate)
    cutoff = _parse_ts(candidate.get("evidence_cutoff") or candidate.get("signal_timestamp"))
    bars = values.get("intraday_bars") or technical.get("intraday_bars") or []
    valid: list[tuple[datetime, float]] = []
    for bar in bars if isinstance(bars, list) else []:
        if not isinstance(bar, dict):
            continue
        ts = _parse_ts(bar.get("t") or bar.get("timestamp"))
        low = _num(bar.get("l", bar.get("low")))
        high = _num(bar.get("h", bar.get("high")))
        if not ts or not cutoff or ts + timedelta(minutes=1) > cutoff or low is None or high is None or not 0 < low <= high:
            continue
        local = ts.astimezone(NY)
        if local.date() != cutoff.astimezone(NY).date() or not ("09:30" <= local.strftime("%H:%M") < "16:00"):
            continue
        valid.append((ts, low))
    valid.sort()
    if len({ts for ts, _ in valid}) != len(valid):
        return {"confirmed": False, "status": "ambiguous_bar_timestamps", "bar_count": len(valid)}
    if any((right[0] - left[0]).total_seconds() != 60 for left, right in zip(valid, valid[1:])):
        return {"confirmed": False, "status": "pattern_evidence_missing", "reason": "Intraday minute path is not contiguous", "bar_count": len(valid)}
    # At least five bars and two strict local minima; require the latest bar to be
    # current enough that a prior recovery is not mistaken for present structure.
    fresh = bool(valid and cutoff and 0 <= (cutoff - valid[-1][0]).total_seconds() <= MAX_TRADE_AGE_SECONDS)
    pivots = [valid[i] for i in range(1, len(valid) - 1)
              if valid[i][1] < valid[i - 1][1] and valid[i][1] < valid[i + 1][1]]
    observed = len(valid) >= 5 and len(pivots) >= 2 and fresh
    confirmed = bool(observed and pivots[-1][1] > pivots[-2][1] and valid[-1][1] > pivots[-1][1])
    return {
        "confirmed": confirmed,
        "status": "observed_higher_low" if confirmed else "not_confirmed" if observed else "pattern_evidence_missing",
        "bar_count": len(valid),
        "previous_swing_low": pivots[-2][1] if len(pivots) >= 2 else None,
        "latest_swing_low": pivots[-1][1] if pivots else None,
        "definition": "Two completed regular-session swing lows, second above first, with a subsequent bar holding above the second low.",
    }
