from __future__ import annotations

from typing import Any, Iterable

from app.reversion_guard_execution import assess_candidate
from app.reversion_guard_evidence import source_evidence
from app.reversion_guard_policy import (
    DEFAULT_SETTINGS,
    EVENT_LABELS,
    _int,
    _num,
    _round,
)


def break_even_recovery_pct(entry_price: float, current_price: float) -> float | None:
    if entry_price <= 0 or current_price <= 0:
        return None
    return max(0.0, (entry_price / current_price - 1.0) * 100.0)


def review_position(position: dict[str, Any], candidate: dict[str, Any] | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    entry = _num(position.get("entry_price_usd") or position.get("entry_price"))
    current = _num(position.get("current_price_usd") or position.get("current_price"))
    quantity = _num(position.get("quantity")) or 0.0
    if entry is None or current is None or entry <= 0 or current <= 0:
        raise ValueError("entry_price_usd and current_price_usd must both be positive")

    pnl_pct = (current / entry - 1.0) * 100.0
    recovery = break_even_recovery_pct(entry, current) or 0.0
    usd_per_gbp = max(0.01, _num(settings.get("usd_per_gbp")) or float(DEFAULT_SETTINGS["usd_per_gbp"]))
    pnl_usd = (current - entry) * quantity
    pnl_gbp = pnl_usd / usd_per_gbp
    market_value_gbp = current * quantity / usd_per_gbp

    candidate_assessment = assess_candidate(candidate, settings) if candidate else None
    event_bucket = candidate_assessment["event"]["bucket"] if candidate_assessment else "unknown_or_unverified"
    hard_reject = bool(candidate_assessment and candidate_assessment["event"]["hard_reject_new_entry"])
    damage_risk = _num(candidate.get("damage_risk")) if candidate else None

    if event_bucket in {"existential_or_structural_damage", "financing_or_dilution", "failed_clinical_or_regulatory_event", "parabolic_momentum_unwind"} or hard_reject:
        action = "EXIT"
        action_label = "Exit — original reversion thesis is invalid"
        sizing = "Do not average down. A bounce is an exit opportunity, not evidence that the original thesis was sound."
    elif pnl_pct >= 6:
        action = "TAKE_PROFIT"
        action_label = "Take profit / close the reversion trade"
        sizing = "Close or retain only a small pre-planned runner with a raised stop."
    elif pnl_pct >= 4:
        action = "TRIM_WINNER"
        action_label = "Trim into the 4–6% profit zone"
        sizing = "Take at least half off and move the remainder to a defined trailing invalidation."
    elif event_bucket == "guidance_or_earnings_quality_reset":
        action = "EXIT_OR_HEAVY_TRIM"
        action_label = "Exit or heavily trim — valuation has reset"
        sizing = "Retain only a small position if you have independently rebuilt fair value from the new guidance."
    elif event_bucket == "regulatory_legal_or_compliance":
        action = "TRIM"
        action_label = "Trim materially — open event risk"
        sizing = "Reduce by at least half unless the position was explicitly sized as a legal/compliance special situation."
    elif event_bucket == "temporary_operational_issue" and pnl_pct > -12:
        action = "HOLD_CONDITIONALLY"
        action_label = "Conditional hold with price and time stop"
        sizing = "Do not add until a higher low and reclaim are confirmed."
    elif recovery >= 25:
        action = "EXIT_OR_HEAVY_TRIM"
        action_label = "Exit or heavily trim — break-even anchoring risk"
        sizing = "The required rebound is now a substantial new bet; reassess from current price, not cost basis."
    else:
        action = "REASSESS_OR_EXIT"
        action_label = "Reassess immediately; exit if no confirmation"
        sizing = "Require a higher low and key-level reclaim within two full sessions."

    time_stop = "By the close of the second full regular session after entry, unless a higher low and reclaim are visible."
    if candidate_assessment and candidate_assessment["risk_plan"].get("available"):
        invalidation = candidate_assessment["risk_plan"].get("provisional_stop_usd")
    else:
        invalidation = round(current * 0.94, 4)

    inferred_price = position.get("current_price_source") == "stored_scan"
    current_scan_price = bool(candidate_assessment and candidate_assessment["execution"]["ready"])
    price_as_of = (candidate or {}).get("latest_trade_ts") if inferred_price else None
    if inferred_price and not current_scan_price:
        action = "REVIEW_STALE_DATA"
        action_label = "Refresh market data before acting"
        sizing = "This P/L uses the stored scan price. The current market price and execution conditions have not been verified."

    return {
        "symbol": str(position.get("symbol") or (candidate or {}).get("symbol") or "").upper(),
        "entry_price_usd": round(entry, 4),
        "current_price_usd": round(current, 4),
        "price_source": "stored_scan" if inferred_price else "user_entered",
        "price_as_of": price_as_of,
        "price_is_current": current_scan_price if inferred_price else None,
        "quantity": quantity,
        "pnl_pct": round(pnl_pct, 2),
        "pnl_usd": round(pnl_usd, 2),
        "pnl_gbp": round(pnl_gbp, 2),
        "market_value_gbp": round(market_value_gbp, 2),
        "recovery_to_break_even_pct": round(recovery, 2),
        "action": action,
        "action_label": action_label,
        "sizing_guidance": sizing,
        "event_bucket": event_bucket,
        "event_label": EVENT_LABELS[event_bucket],
        "provisional_invalidation_usd": invalidation,
        "time_stop": time_stop,
        "averaging_rule": "No averaging down. Add only after confirmation and after recalculating total theme exposure and risk.",
        "break_even_warning": recovery >= 20,
        "candidate_assessment": candidate_assessment,
        "damage_risk": _round(damage_risk, 1),
    }


def portfolio_summary(
    assessments: Iterable[dict[str, Any]],
    positions: Iterable[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    max_theme = max(1, _int(settings.get("max_theme_positions")) or int(DEFAULT_SETTINGS["max_theme_positions"]))
    account = max(1.0, _num(settings.get("account_value_gbp")) or float(DEFAULT_SETTINGS["account_value_gbp"]))
    max_open_risk_pct = max(0.1, _num(settings.get("max_open_risk_pct")) or float(DEFAULT_SETTINGS["max_open_risk_pct"]))

    rows = list(assessments)
    position_rows = list(positions or [])
    theme_counts: dict[str, int] = {}
    for row in position_rows:
        theme = str(row.get("theme") or row.get("candidate_assessment", {}).get("theme") or "Other / unknown")
        theme_counts[theme] = theme_counts.get(theme, 0) + 1

    planned_risk = 0.0
    for row in position_rows:
        risk = _num(row.get("planned_risk_gbp") or row.get("candidate_assessment", {}).get("risk_plan", {}).get("preview_risk_gbp"))
        planned_risk += risk or 0.0

    overexposed = [
        {"theme": theme, "count": count, "limit": max_theme}
        for theme, count in sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))
        if count > max_theme
    ]
    candidate_theme_counts: dict[str, int] = {}
    for row in rows:
        if row.get("recommended_action") == "INVESTIGATE":
            theme = str(row.get("theme") or "Other / unknown")
            candidate_theme_counts[theme] = candidate_theme_counts.get(theme, 0) + 1

    return {
        "candidate_counts": {
            "investigate": sum(1 for row in rows if row.get("recommended_action") == "INVESTIGATE"),
            "wait": sum(1 for row in rows if row.get("recommended_action") == "WAIT"),
            "pass": sum(1 for row in rows if row.get("recommended_action") == "PASS"),
            "reject": sum(1 for row in rows if row.get("recommended_action") == "REJECT"),
        },
        "position_count": len(position_rows),
        "theme_counts": theme_counts,
        "candidate_theme_counts": candidate_theme_counts,
        "overexposed_themes": overexposed,
        "planned_open_risk_gbp": round(planned_risk, 2),
        "planned_open_risk_pct": round(planned_risk / account * 100.0, 3),
        "max_open_risk_pct": max_open_risk_pct,
        "open_risk_breach": planned_risk / account * 100.0 > max_open_risk_pct,
        "correlation_rule": f"No more than {max_theme} positions driven by the same theme or factor.",
        "selection_rule": "Rank by verified overreaction quality and tradability, not by percentage fall.",
    }


def compact_candidate_packet(candidate: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    """Create a bounded, point-in-time packet for the ChatGPT handoff."""
    headlines = source_evidence(candidate)["eligible_articles"]
    compact_news = []
    for article in headlines[:8]:
        if not isinstance(article, dict):
            continue
        compact_news.append(
            {
                "headline": article.get("headline"),
                "summary": article.get("summary"),
                "source": article.get("source"),
                "created_at": article.get("created_at"),
                "url": article.get("url"),
            }
        )
    return {
        "symbol": candidate.get("symbol"),
        "name": candidate.get("name"),
        "signal_timestamp": candidate.get("signal_timestamp"),
        "evidence_cutoff": candidate.get("evidence_cutoff"),
        "move_pct": candidate.get("drop_pct"),
        "price": candidate.get("last_price"),
        "spread_pct": candidate.get("spread_pct"),
        "previous_dollar_volume": candidate.get("prev_dollar_volume"),
        "upstream_score": candidate.get("reversion_score"),
        "score_interpretation": "Uncalibrated research heuristic, not a profit probability",
        "upstream_verdict": candidate.get("model_verdict"),
        "damage_risk": candidate.get("damage_risk"),
        "evidence_confidence": candidate.get("evidence_confidence"),
        "catalyst_summary": candidate.get("catalyst_summary"),
        "catalyst_analysis": candidate.get("catalyst_analysis"),
        "technical_inputs": candidate.get("technical_inputs"),
        "news": compact_news,
        "guard_assessment": assessment,
    }
