from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from app.reversion_guard_evidence import (
    execution_evidence,
    higher_low_evidence,
    market_data,
    source_evidence,
    technical_inputs,
)

from app.reversion_guard_policy import (
    DEFAULT_SETTINGS,
    EVENT_LABELS,
    GUARD_VERSION,
    _clamp,
    _num,
    _parse_ts,
    _round,
    classify_event,
    infer_theme,
    signal_session,
)


def confirmation_assessment(candidate: dict[str, Any], session: dict[str, Any] | None = None) -> dict[str, Any]:
    technical = technical_inputs(candidate)
    direct: list[tuple[str, bool | None, float]] = []

    range_position = _num(technical.get("session_range_position"))
    direct.append(("Closed/last traded in upper 60% of session range", None if range_position is None else range_position >= 60, 22.0))
    gap_reclaim = _num(technical.get("gap_reclaim_pct"))
    direct.append(("Reclaimed at least 30% of the opening gap", None if gap_reclaim is None else gap_reclaim >= 30, 20.0))
    low_reclaim = _num(technical.get("low_reclaim_pct"))
    direct.append(("Reclaimed at least 45% of the low-to-prior-close distance", None if low_reclaim is None else low_reclaim >= 45, 22.0))
    vwap_distance = _num(technical.get("vwap_distance_pct"))
    direct.append(("At or above VWAP", None if vwap_distance is None else vwap_distance >= 0, 20.0))
    return_from_open = _num(technical.get("return_from_open_pct"))
    direct.append(("Non-negative return from session open", None if return_from_open is None else return_from_open >= 0, 16.0))

    available = [item for item in direct if item[1] is not None]
    direct_score = sum(weight for _, passed, weight in available if passed)
    maximum = sum(weight for _, _, weight in available)
    normalised = (direct_score / maximum * 100.0) if maximum > 0 else None
    upstream = _num(candidate.get("confirmation_score"))
    if normalised is None:
        score = upstream if upstream is not None else 25.0
    elif upstream is None:
        score = normalised
    else:
        score = normalised * 0.75 + upstream * 0.25

    session = session or signal_session(candidate)
    pattern = higher_low_evidence(candidate)
    reclaim = vwap_distance is not None and vwap_distance >= 0
    if not session.get("is_regular") or not session.get("after_1000_et"):
        score = min(score, 45.0)
        status = "extended_hours_or_too_early"
    elif not pattern["confirmed"]:
        score = min(score, 62.0)
        status = pattern["status"]
    elif not reclaim:
        score = min(score, 62.0)
        status = "waiting_for_reclaim"
    elif score >= 68:
        status = "confirmed"
    elif score >= 45:
        status = "forming"
    else:
        status = "not_confirmed"

    return {
        "score": round(_clamp(score), 1),
        "status": status,
        "checks": [
            {"label": label, "passed": passed, "weight": weight}
            for label, passed, weight in direct
        ],
        "available_check_count": len(available),
        "higher_low_evidence": pattern,
        "reclaim_observed": reclaim,
        "required_pattern": "A higher low after the regular-session open plus reclaim of VWAP or a prior intraday pivot.",
        "averaging_rule": "Never average down into a falling price. Recalculate only after a higher low and a confirmed reclaim.",
    }


def execution_quality(candidate: dict[str, Any], *, as_of: datetime | None = None) -> dict[str, Any]:
    evidence = execution_evidence(candidate, as_of=as_of)
    spread = evidence["spread_pct"]
    liquidity = _num(candidate.get("prev_dollar_volume")) or 0.0
    if spread is None:
        spread_score = 35.0
    elif spread <= 0.5:
        spread_score = 100.0
    elif spread <= 1.0:
        spread_score = 88.0
    elif spread <= 2.0:
        spread_score = 68.0
    elif spread <= 3.0:
        spread_score = 50.0
    elif spread <= 5.0:
        spread_score = 25.0
    else:
        spread_score = 5.0

    if liquidity >= 50_000_000:
        liquidity_score = 100.0
    elif liquidity >= 10_000_000:
        liquidity_score = 88.0
    elif liquidity >= 2_000_000:
        liquidity_score = 68.0
    elif liquidity >= 500_000:
        liquidity_score = 42.0
    else:
        liquidity_score = 10.0
    score = spread_score * 0.55 + liquidity_score * 0.45
    if not evidence["ready"]:
        score = min(score, 44.0)
    return {
        "score": round(score, 1),
        "spread_pct": _round(spread, 3),
        "previous_dollar_volume": _round(liquidity, 0),
        "spread_score": spread_score,
        "liquidity_score": liquidity_score,
        "limit_orders_only": True,
        "evidence": evidence,
        "ready": evidence["ready"],
    }


def _snapshot_bar(candidate: dict[str, Any]) -> dict[str, Any]:
    values = market_data(candidate)
    snapshot = values.get("raw_snapshot") if isinstance(values.get("raw_snapshot"), dict) else {}
    daily = snapshot.get("dailyBar") if isinstance(snapshot.get("dailyBar"), dict) else {}
    return daily


def risk_plan(candidate: dict[str, Any], settings: dict[str, Any], entry_allowed: bool) -> dict[str, Any]:
    price = _num(candidate.get("last_price"))
    if price is None or price <= 0:
        return {"available": False, "reason": "No valid reference price."}

    technical = technical_inputs(candidate)
    atr = _num(technical.get("atr20"))
    daily = _snapshot_bar(candidate)
    day_low = _num(daily.get("l"))
    day_open = _num(daily.get("o"))
    vwap = _num(daily.get("vw")) or _num(technical.get("vwap"))

    buffer_value = max((atr or price * 0.04) * 0.12, price * 0.004)
    if day_low is not None and 0 < day_low < price:
        stop = day_low - buffer_value
        stop_basis = "Below signal-session low with volatility buffer"
    else:
        stop = price - max(atr or 0.0, price * 0.06)
        stop_basis = "One ATR / 6% provisional stop; replace with confirmed higher-low invalidation"
    stop = max(0.01, min(stop, price * 0.995))
    risk_per_share = price - stop
    risk_pct = risk_per_share / price * 100.0

    risk_budget_gbp = max(0.0, _num(settings.get("risk_budget_gbp")) or float(DEFAULT_SETTINGS["risk_budget_gbp"]))
    max_position_gbp = max(0.0, _num(settings.get("max_position_gbp")) or float(DEFAULT_SETTINGS["max_position_gbp"]))
    usd_per_gbp = max(0.01, _num(settings.get("usd_per_gbp")) or float(DEFAULT_SETTINGS["usd_per_gbp"]))
    account_value_gbp = max(1.0, _num(settings.get("account_value_gbp")) or float(DEFAULT_SETTINGS["account_value_gbp"]))

    risk_budget_usd = risk_budget_gbp * usd_per_gbp
    cap_usd = max_position_gbp * usd_per_gbp
    shares_by_risk = math.floor(risk_budget_usd / risk_per_share) if risk_per_share > 0 else 0
    shares_by_cap = math.floor(cap_usd / price) if price > 0 else 0
    preview_shares = max(0, min(shares_by_risk, shares_by_cap))
    preview_position_gbp = preview_shares * price / usd_per_gbp
    preview_risk_gbp = preview_shares * risk_per_share / usd_per_gbp

    too_wide = risk_pct > 12.0
    too_tight = risk_pct < 1.0
    recommended_shares = preview_shares if entry_allowed and not too_wide and not too_tight else 0
    target_1r = price + risk_per_share
    target_15r = price + 1.5 * risk_per_share
    target_4 = price * 1.04
    target_6 = price * 1.06

    entry_trigger_parts = ["higher low", "VWAP reclaim"]
    if vwap:
        entry_trigger_parts.append(f"hold above ${vwap:.2f}")
    if day_open:
        entry_trigger_parts.append(f"or reclaim signal open ${day_open:.2f}")

    return {
        "available": True,
        "reference_price_usd": round(price, 4),
        "provisional_stop_usd": round(stop, 4),
        "stop_basis": stop_basis,
        "risk_per_share_usd": round(risk_per_share, 4),
        "risk_distance_pct": round(risk_pct, 2),
        "risk_budget_gbp": round(risk_budget_gbp, 2),
        "max_position_gbp": round(max_position_gbp, 2),
        "usd_per_gbp": round(usd_per_gbp, 4),
        "preview_shares_after_confirmation": preview_shares,
        "recommended_shares_now": recommended_shares,
        "preview_position_gbp": round(preview_position_gbp, 2),
        "preview_risk_gbp": round(preview_risk_gbp, 2),
        "preview_risk_pct_of_account": round(preview_risk_gbp / account_value_gbp * 100.0, 3),
        "one_r_target_usd": round(target_1r, 4),
        "one_point_five_r_target_usd": round(target_15r, 4),
        "profit_zone_usd": [round(target_4, 4), round(target_6, 4)],
        "target_basis": "Illustrative +1R/+1.5R and +4–6% planning levels; no estimated probability of reaching them.",
        "profit_probability": None,
        "expected_net_return_pct": None,
        "reward_risk_status": "UNESTIMATED: no independent valuation target or complete execution-cost estimate",
        "stop_loss_is_guaranteed": False,
        "gap_risk_note": "A stop defines intended invalidation; gaps and slippage can exceed the planned loss.",
        "entry_trigger": ", ".join(entry_trigger_parts),
        "time_stop": "Exit by the close of the second full regular session if the stock has not formed a higher low and reclaimed a key level.",
        "too_wide_to_size": too_wide,
        "too_tight_to_trust": too_tight,
        "sizing_rule": "Illustrative sizing uses the smaller of the saved risk-budget and maximum-position settings; review execution costs before trading.",
    }


def _base_opportunity(candidate: dict[str, Any]) -> float:
    direct = _num(candidate.get("reversion_score"))
    if direct is not None:
        return _clamp(direct)
    components = [
        _num(candidate.get("setup_score")),
        _num(candidate.get("catalyst_score")),
        _num(candidate.get("resilience_score")),
        _num(candidate.get("confirmation_score")),
    ]
    values = [value for value in components if value is not None]
    return _clamp(sum(values) / len(values)) if values else 35.0


def assess_candidate(
    candidate: dict[str, Any], settings: dict[str, Any] | None = None,
    *, as_of: datetime | None = None, historical: bool = False,
) -> dict[str, Any]:
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    now = _parse_ts(as_of) or datetime.now(UTC)
    if historical:
        now = _parse_ts(candidate.get("evidence_cutoff") or candidate.get("signal_timestamp")) or now
    evidence = source_evidence(candidate)
    eligible = evidence.pop("eligible_articles")
    source_text = " ".join(" ".join(str(item.get(key) or "") for key in ("headline", "summary", "content")) for item in eligible)
    event = classify_event({**candidate, "classification_text": source_text or "No eligible catalyst source", "headlines": eligible})
    # Structured benign labels still need matching economic source content.
    source_event = classify_event({"classification_text": source_text or "No eligible catalyst source", "headlines": eligible})
    benign = {"temporary_operational_issue", "analyst_or_sentiment_only"}
    source_supports_event = bool(eligible and source_event["bucket"] == event["bucket"])
    cause_verified = evidence["upstream_cause_verified"] and source_supports_event
    evidence["source_supports_event"] = source_supports_event
    evidence["cause_verified"] = cause_verified
    if event["bucket"] in benign and not cause_verified:
        event = classify_event({"classification_text": "No eligible verified catalyst source", "headlines": []})
    session = signal_session(candidate)
    confirmation = confirmation_assessment(candidate, session)
    execution = execution_quality(candidate, as_of=now)
    base = _base_opportunity(candidate)
    resilience = _num(candidate.get("resilience_score"))
    if resilience is None:
        resilience = max(10.0, 100.0 - (_num(candidate.get("damage_risk")) or 50.0))
    confidence = _num(candidate.get("evidence_confidence")) or 0.0

    score = (
        base * 0.34
        + event["prior_score"] * 0.25
        + confirmation["score"] * 0.18
        + execution["score"] * 0.10
        + _clamp(resilience) * 0.08
        + _clamp(confidence) * 0.05
    )

    caps: list[tuple[float, str]] = []
    if event["hard_reject_new_entry"]:
        caps.append((20.0, "Structural/dilution/failed-event/parabolic hard gate"))
    elif event["bucket"] == "guidance_or_earnings_quality_reset":
        caps.append((48.0, "Forward fair-value reset requires a new valuation anchor"))
    elif event["bucket"] == "regulatory_legal_or_compliance":
        caps.append((42.0, "Open legal/compliance risk is not a clean short-horizon reversion catalyst"))
    elif event["bucket"] == "unknown_or_unverified":
        caps.append((52.0, "Unknown cause cannot be treated as transient"))
    if confidence < 45 or not cause_verified:
        caps.append((45.0, "Low evidence confidence"))
    if confirmation["status"] != "confirmed":
        caps.append((62.0, "Price confirmation absent"))
    if execution["score"] < 45:
        caps.append((38.0, "Execution friction / liquidity gate"))
    for cap, _ in caps:
        score = min(score, cap)
    score = round(_clamp(score), 1)

    gates: list[dict[str, Any]] = []

    def gate(name: str, passed: bool, detail: str, severity: str = "required") -> None:
        gates.append({"name": name, "passed": bool(passed), "detail": detail, "severity": severity})

    gate("No structural hard veto", not event["hard_reject_new_entry"], EVENT_LABELS[event["bucket"]])
    gate("Cause sufficiently verified", cause_verified and confidence >= 55, f"Source support: {source_supports_event}; cutoff-valid sources: {evidence['eligible_source_count']}; confidence {confidence:.1f}/100 (heuristic)")
    gate("Regular-session timing", bool(session["is_regular"] and session["after_1000_et"]), f"Signal/evidence cutoff session: {session['label']}")
    gate("Price confirmation", confirmation["status"] == "confirmed", f"Confirmation {confirmation['score']:.1f}/100 ({confirmation['status']})")
    gate("Current execution evidence", execution["ready"], "; ".join(execution["evidence"]["issues"]) or "Current non-crossed bid/ask and trade at or before cutoff")
    gate("Execution quality", execution["ready"] and execution["score"] >= 55, f"Execution quality {execution['score']:.1f}/100")
    gate("Opportunity quality", score >= 68 and base >= 60, f"Guard score {score:.1f}; upstream opportunity {base:.1f}")

    if event["hard_reject_new_entry"]:
        gate_code = "REJECT_NEW_ENTRY"
        gate_label = "Reject new entry"
        action = "REJECT"
    elif event["bucket"] == "guidance_or_earnings_quality_reset":
        gate_code = "WAIT_FOR_NEW_FAIR_VALUE"
        gate_label = "Wait for new fair-value anchor"
        action = "WAIT"
    elif event["bucket"] == "regulatory_legal_or_compliance":
        gate_code = "WAIT_FOR_RISK_RESOLUTION"
        gate_label = "Wait for legal/compliance clarity"
        action = "WAIT"
    elif event["bucket"] == "unknown_or_unverified" or confidence < 55 or not cause_verified:
        gate_code = "WAIT_FOR_EVIDENCE"
        gate_label = "Wait for verified catalyst"
        action = "WAIT"
    elif not session["is_regular"] or not session["after_1000_et"]:
        gate_code = "WAIT_FOR_REGULAR_SESSION"
        gate_label = "Wait until 10:00 ET+"
        action = "WAIT"
    elif not execution["ready"]:
        gate_code = "WAIT_FOR_CURRENT_MARKET_DATA"
        gate_label = "Wait for current quote and trade"
        action = "WAIT"
    elif confirmation["status"] != "confirmed":
        gate_code = "WAIT_FOR_CONFIRMATION"
        gate_label = "Wait for higher low + reclaim"
        action = "WAIT"
    elif execution["score"] < 55 or score < 68 or base < 60:
        gate_code = "PASS_LOW_QUALITY"
        gate_label = "Pass — insufficient setup quality"
        action = "PASS"
    else:
        gate_code = "INVESTIGATE_CONFIRMED"
        gate_label = "Investigate — confirmed setup"
        action = "INVESTIGATE"

    plan = risk_plan(candidate, settings, entry_allowed=gate_code == "INVESTIGATE_CONFIRMED")
    if plan.get("too_wide_to_size") and gate_code == "INVESTIGATE_CONFIRMED":
        gate_code = "PASS_RISK_TOO_WIDE"
        gate_label = "Pass — invalidation too wide"
        action = "PASS"
        plan["recommended_shares_now"] = 0
    if plan.get("too_tight_to_trust") and gate_code == "INVESTIGATE_CONFIRMED":
        gate_code = "WAIT_FOR_BETTER_STRUCTURE"
        gate_label = "Wait — stop structure unreliable"
        action = "WAIT"
        plan["recommended_shares_now"] = 0
    if historical:
        plan["recommended_shares_now"] = 0
        plan["historical_only"] = True

    reasons: list[str] = []
    reasons.append(f"Catalyst: {EVENT_LABELS[event['bucket']]}")
    if event["matched_terms"]:
        reasons.append("Evidence markers: " + ", ".join(event["matched_terms"][:4]))
    reasons.append(f"Upstream opportunity {base:.1f}/100; guard score {score:.1f}/100")
    reasons.append(f"Confirmation {confirmation['score']:.1f}/100; execution {execution['score']:.1f}/100")
    if caps:
        reasons.append("Caps: " + "; ".join(reason for _, reason in caps))

    theme = infer_theme(candidate)
    return {
        "guard_version": GUARD_VERSION,
        "model_status": "UNCALIBRATED_HEURISTIC",
        "profit_probability": None,
        "expected_net_return_pct": None,
        "score_meaning": "Research and evidence ranking, not the probability of a profitable trade.",
        "assessment_context": "historical_at_cutoff" if historical else "current_entry_review",
        "assessed_at": now.isoformat(),
        "candidate_id": candidate.get("id"),
        "scan_id": candidate.get("scan_id"),
        "symbol": candidate.get("symbol"),
        "name": candidate.get("name"),
        "rank": candidate.get("rank"),
        "theme": theme,
        "event": event,
        "session": session,
        "confirmation": confirmation,
        "execution": execution,
        "evidence": evidence,
        "upstream_opportunity_score": round(base, 1),
        "guard_score": score,
        "gate_code": gate_code,
        "gate_label": gate_label,
        "recommended_action": action,
        "research_action": "PASS" if event["hard_reject_new_entry"] else "INVESTIGATE" if cause_verified and event["bucket"] in benign and base >= 60 else "WATCH",
        "gates": gates,
        "risk_plan": plan,
        "reasons": reasons,
        "anti_thesis_drift": "A failed short-term trade must not become a long-term investment without a fresh, explicit investment thesis.",
        "no_hindsight": "Source attribution and price-pattern checks use eligible records at or before cutoff; current execution review also checks quote/trade age at assessment time.",
    }
