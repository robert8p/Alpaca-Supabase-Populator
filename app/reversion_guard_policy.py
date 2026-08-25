from __future__ import annotations

"""Deterministic trade-quality and risk overlay for Oversold Reversion signals.

The upstream scanner answers: "is this sell-off worth researching?"  This module
answers the stricter execution question: "is a new entry allowed yet, how should it
be sized, and what invalidates it?"

The engine deliberately treats missing evidence as uncertainty, never as bullish
information.  It also prevents a large percentage fall, low RSI, or a headline-free
sell-off from overcoming structural damage, dilution, guidance resets, compliance
risk, or a parabolic momentum unwind.
"""

import math
import re
from datetime import UTC, datetime, time
from typing import Any, Iterable
from zoneinfo import ZoneInfo

GUARD_VERSION = "oversold_reversion_guard_v1_0"
NY = ZoneInfo("America/New_York")

DEFAULT_SETTINGS: dict[str, float | int] = {
    "account_value_gbp": 10_000.0,
    "risk_budget_gbp": 50.0,
    "max_position_gbp": 500.0,
    "usd_per_gbp": 1.30,
    "max_theme_positions": 3,
    "max_open_risk_pct": 2.0,
}

# Precedence matters: the first economically specific match wins.
EVENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "existential_or_structural_damage",
        (
            "bankruptcy", "chapter 11", "chapter 7", "insolven", "going concern",
            "debt default", "payment default", "liquidation", "fraud", "accounting fraud",
            "restatement", "material weakness", "delist", "permanent closure",
            "lost key customer", "loses key customer", "license terminated",
        ),
    ),
    (
        "financing_or_dilution",
        (
            "public offering", "secondary offering", "registered direct", "private placement",
            "at-the-market", "atm offering", "convertible note", "convertible senior",
            "convertible debt", "dilution", "dilutive", "warrant exercise", "share issuance",
            "issued shares", "equity raise", "capital raise", "reverse split",
        ),
    ),
    (
        "failed_clinical_or_regulatory_event",
        (
            "failed primary endpoint", "missed primary endpoint", "did not meet the primary endpoint",
            "complete response letter", "clinical hold", "trial terminated", "phase 3 failure",
            "phase iii failure", "fda rejection", "approval denied",
        ),
    ),
    (
        "guidance_or_earnings_quality_reset",
        (
            "cuts guidance", "cut guidance", "lowers guidance", "lowered guidance",
            "reduces guidance", "reduced guidance", "withdraws guidance", "withdrawn guidance",
            "cuts forecast", "lowers forecast", "outlook reduced", "guidance reset",
            "revenue miss", "earnings miss", "margin compression", "cash conversion",
            "free cash flow fell", "negative free cash flow", "profit warning",
        ),
    ),
    (
        "regulatory_legal_or_compliance",
        (
            "subpoena", "investigation", "indict", "department of justice", "doj",
            "securities and exchange commission", "sec probe", "export control",
            "export restriction", "compliance investigation", "regulatory inquiry",
            "criminal charges", "sanctions", "lawsuit", "class action",
        ),
    ),
    (
        "parabolic_momentum_unwind",
        (
            "post_spike_unwind", "post-spike unwind", "parabolic", "momentum unwind",
            "profit taking after a rally", "normalisation after a spike", "normalization after a spike",
            "speculative unwind", "meme stock", "short squeeze unwind",
        ),
    ),
    (
        "temporary_operational_issue",
        (
            "temporary", "temporarily", "transient", "one-off", "one time",
            "shipment delay", "shipping delay", "production delay", "outage", "weather disruption",
            "supply disruption", "technical issue", "operations resume", "resumes operations",
            "legacy backlog", "integration issue", "higher raw material costs", "short-term disruption",
        ),
    ),
    (
        "analyst_or_sentiment_only",
        ("analyst downgrade", "price target cut", "rating downgrade", "sentiment", "sector rotation"),
    ),
)

EVENT_LABELS: dict[str, str] = {
    "existential_or_structural_damage": "Structural / existential damage",
    "financing_or_dilution": "Financing or dilution",
    "failed_clinical_or_regulatory_event": "Failed clinical / regulatory event",
    "guidance_or_earnings_quality_reset": "Guidance or earnings-quality reset",
    "regulatory_legal_or_compliance": "Regulatory, legal or compliance risk",
    "parabolic_momentum_unwind": "Parabolic momentum unwind",
    "temporary_operational_issue": "Potentially temporary operational issue",
    "analyst_or_sentiment_only": "Analyst or sentiment-driven move",
    "unknown_or_unverified": "Unknown or insufficiently verified catalyst",
}

EVENT_PRIORS: dict[str, float] = {
    "existential_or_structural_damage": 3.0,
    "financing_or_dilution": 8.0,
    "failed_clinical_or_regulatory_event": 8.0,
    "guidance_or_earnings_quality_reset": 25.0,
    "regulatory_legal_or_compliance": 22.0,
    "parabolic_momentum_unwind": 12.0,
    "temporary_operational_issue": 80.0,
    "analyst_or_sentiment_only": 66.0,
    "unknown_or_unverified": 35.0,
}

THEME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI / semiconductors", ("semiconductor", "chip", "gpu", "wafer", "optical", "photonics", "data center", "data centre", "ai server", "indium phosphide", "silicon carbide")),
    ("Biotechnology", ("biotech", "clinical trial", "phase 1", "phase 2", "phase 3", "fda", "drug candidate", "therapeutic")),
    ("Defence / aerospace", ("defense", "defence", "aerospace", "missile", "military", "department of defense", "dod")),
    ("Fintech / consumer credit", ("fintech", "buy now pay later", "bnpl", "consumer credit", "payments")),
    ("Automotive", ("automotive", "auto parts", "vehicle", "aftermarket parts", "electric vehicle", "ev")),
    ("Industrials", ("industrial", "manufacturing", "factory", "lighting", "backlog", "raw material")),
    ("Software", ("software", "saas", "cloud platform", "cybersecurity")),
    ("Consumer", ("consumer", "retail", "household", "restaurant", "apparel")),
    ("Energy", ("oil", "gas", "energy", "solar", "wind", "uranium")),
)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


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


def _flatten_text(value: Any) -> list[str]:
    output: list[str] = []
    if value is None:
        return output
    if isinstance(value, dict):
        for item in value.values():
            output.extend(_flatten_text(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            output.extend(_flatten_text(item))
    else:
        output.append(str(value))
    return output


def candidate_text(candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "symbol", "name", "sector_hint", "catalyst_class", "catalyst_summary",
        "risk_flags", "hard_veto_reason", "catalyst_analysis", "explanation", "headlines",
    ):
        parts.extend(_flatten_text(candidate.get(key)))
    return " ".join(parts).lower()


def classify_event(candidate: dict[str, Any]) -> dict[str, Any]:
    text = candidate_text(candidate)
    risk_flags = {str(flag).lower() for flag in (candidate.get("risk_flags") or [])}
    catalyst = candidate.get("catalyst_analysis") if isinstance(candidate.get("catalyst_analysis"), dict) else {}
    declared_type = str(catalyst.get("catalyst_type") or catalyst.get("event_type") or "").lower()
    declared = f"{declared_type} {text}"

    bucket = "unknown_or_unverified"
    matched_terms: list[str] = []

    # Phrase variants in filings and news rarely use identical word order.  These
    # bounded patterns capture the economic statement without turning every mention
    # of "guidance" or "clinical" into a destructive event.
    pattern_rules: tuple[tuple[str, str, str], ...] = (
        (
            "failed_clinical_or_regulatory_event",
            r"\b(fail(?:ed|s)?|miss(?:ed|es)?)\b.{0,45}\b(primary|pivotal) endpoint\b|\b(primary|pivotal) endpoint\b.{0,45}\b(was not met|not met|failed|missed)\b",
            "failed/missed pivotal endpoint",
        ),
        (
            "guidance_or_earnings_quality_reset",
            r"\b(cut|cuts|cutting|lower|lowers|lowered|reduce|reduces|reduced|withdraw|withdraws|withdrew)\b.{0,70}\b(guidance|outlook|forecast)\b|\b(guidance|outlook|forecast)\b.{0,45}\b(cut|lowered|reduced|withdrawn)\b",
            "forward guidance/outlook reduced",
        ),
    )
    for candidate_bucket, pattern, label in pattern_rules:
        if re.search(pattern, declared):
            bucket = candidate_bucket
            matched_terms = [label]
            break

    if bucket == "unknown_or_unverified":
        for candidate_bucket, terms in EVENT_RULES:
            hits = [term for term in terms if term in declared]
            if hits:
                bucket = candidate_bucket
                matched_terms = hits[:6]
                break

    # Structured upstream flags are more reliable than generic mover headlines.
    if "solvency" in risk_flags or "delisting" in risk_flags:
        bucket = "existential_or_structural_damage"
        matched_terms = sorted(risk_flags.intersection({"solvency", "delisting"}))
    elif "dilution" in risk_flags:
        bucket = "financing_or_dilution"
        matched_terms = ["risk flag: dilution"]
    elif declared_type in {"post_spike_unwind", "spike", "momentum_unwind"}:
        bucket = "parabolic_momentum_unwind"
        matched_terms = [f"declared type: {declared_type}"]
    elif declared_type in {"temporary_operational", "temporary_disruption", "operations"} and bucket == "unknown_or_unverified":
        bucket = "temporary_operational_issue"
        matched_terms = [f"declared type: {declared_type}"]

    technical = candidate.get("technical_inputs") if isinstance(candidate.get("technical_inputs"), dict) else {}
    drawdown_60d = _num(technical.get("drawdown_from_60d_high_pct"))
    current_return = _num(technical.get("current_return_pct")) or _num(candidate.get("drop_pct"))
    # A very large prior peak-to-current collapse plus a large one-day fall is a useful
    # warning, but it is not enough on its own to overrule verified primary evidence.
    parabolic_context = bool(drawdown_60d is not None and drawdown_60d <= -55 and current_return is not None and current_return <= -12)
    if parabolic_context and bucket in {"unknown_or_unverified", "analyst_or_sentiment_only"}:
        bucket = "parabolic_momentum_unwind"
        matched_terms = ["technical: >55% below 60-day high after a double-digit sell-off"]

    hard_veto = bool(candidate.get("hard_veto"))
    damage_risk = _num(candidate.get("damage_risk")) or 0.0
    hard_reject = hard_veto or bucket in {
        "existential_or_structural_damage",
        "financing_or_dilution",
        "failed_clinical_or_regulatory_event",
        "parabolic_momentum_unwind",
    }
    if damage_risk >= 78:
        hard_reject = True

    cautious_reset = bucket in {
        "guidance_or_earnings_quality_reset",
        "regulatory_legal_or_compliance",
        "unknown_or_unverified",
    }
    return {
        "bucket": bucket,
        "label": EVENT_LABELS[bucket],
        "matched_terms": matched_terms,
        "prior_score": EVENT_PRIORS[bucket],
        "hard_reject_new_entry": hard_reject,
        "requires_fresh_fair_value": bucket == "guidance_or_earnings_quality_reset",
        "requires_legal_resolution": bucket == "regulatory_legal_or_compliance",
        "cautious_reset": cautious_reset,
        "parabolic_context": parabolic_context,
    }


def infer_theme(candidate: dict[str, Any]) -> str:
    text = candidate_text(candidate)
    for label, terms in THEME_RULES:
        if any(term in text for term in terms):
            return label
    sector = str(candidate.get("sector_hint") or "").strip()
    return sector.title() if sector and sector.lower() != "unknown" else "Other / unknown"


def signal_session(candidate: dict[str, Any]) -> dict[str, Any]:
    ts = _parse_ts(candidate.get("evidence_cutoff") or candidate.get("signal_timestamp") or candidate.get("latest_trade_ts"))
    if ts is None:
        return {"label": "unknown", "is_regular": False, "after_1000_et": False, "timestamp": None}
    local = ts.astimezone(NY)
    wall = local.time().replace(tzinfo=None)
    weekday = local.weekday() < 5
    if not weekday:
        label = "closed"
    elif time(4, 0) <= wall < time(9, 30):
        label = "pre-market"
    elif time(9, 30) <= wall < time(16, 0):
        label = "regular"
    elif time(16, 0) <= wall < time(20, 0):
        label = "after-hours"
    else:
        label = "closed"
    return {
        "label": label,
        "is_regular": label == "regular",
        "after_1000_et": label == "regular" and wall >= time(10, 0),
        "timestamp": local.isoformat(),
        "entry_timing_rule": "No new earnings/event entry in extended hours; wait until at least 10:00 ET and require a higher low plus a reclaim.",
    }
