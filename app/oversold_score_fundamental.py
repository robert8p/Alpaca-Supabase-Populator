from __future__ import annotations

from typing import Any

from app.oversold_score_common import SALES_SURPRISE_RE, GUIDANCE_RANGE_RE, YOY_SALES_RE, MONEY_RE, STAKE_RE, clamp, _number, _scaled_number


def _sales_surprises(text: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for actual, actual_suffix, direction, estimate, estimate_suffix in SALES_SURPRISE_RE.findall(text):
        actual_value = _scaled_number(actual, actual_suffix)
        estimate_value = _scaled_number(estimate, estimate_suffix)
        if estimate_value <= 0:
            continue
        output.append({"actual": actual_value, "estimate": estimate_value, "direction": direction.lower(), "surprise_pct": ((actual_value / estimate_value) - 1.0) * 100.0})
    return output


def _guidance_shortfalls(text: str) -> list[float]:
    values: list[float] = []
    for low, low_suffix, high, high_suffix, estimate, estimate_suffix in GUIDANCE_RANGE_RE.findall(text):
        low_value = _scaled_number(low, low_suffix)
        high_value = _scaled_number(high, high_suffix)
        estimate_value = _scaled_number(estimate, estimate_suffix)
        if estimate_value > 0:
            values.append((((low_value + high_value) / 2.0) / estimate_value - 1.0) * 100.0)
    return values


def _yoy_sales_declines(text: str) -> list[float]:
    values: list[float] = []
    for current, current_suffix, prior, prior_suffix in YOY_SALES_RE.findall(text):
        current_value = _scaled_number(current, current_suffix)
        prior_value = _scaled_number(prior, prior_suffix)
        if prior_value > 0:
            values.append((1.0 - current_value / prior_value) * 100.0)
    return values


def _financing_amount(text: str) -> float | None:
    amounts = [_scaled_number(value, suffix) for value, suffix in MONEY_RE.findall(text)]
    return max(amounts) if amounts else None


def _major_stake(text: str) -> float | None:
    values = [float(value) for value in STAKE_RE.findall(text)]
    return max(values) if values else None


def fundamental_context(candidate: dict[str, Any]) -> dict[str, Any]:
    fundamentals = candidate.get("fundamentals") or (candidate.get("raw_snapshot") or {}).get("fundamentals") or {}
    detail = fundamentals.get("ticker_details") or {}
    balance = fundamentals.get("balance_sheet") or {}
    cash_flow = fundamentals.get("cash_flow") or {}
    cash = _number(balance.get("cash_and_equivalents"))
    current_liabilities = _number(balance.get("total_current_liabilities"))
    debt_current = _number(balance.get("debt_current")) or 0.0
    long_debt = _number(balance.get("long_term_debt_and_capital_lease_obligations")) or 0.0
    total_debt = debt_current + long_debt
    total_equity = _number(balance.get("total_equity"))
    market_cap = _number(detail.get("market_cap"))
    operating_cf = _number(cash_flow.get("net_cash_from_operating_activities"))
    cash_to_current_liabilities = cash / current_liabilities if cash is not None and current_liabilities and current_liabilities > 0 else None
    debt_to_cash = total_debt / cash if cash and cash > 0 else None
    runway_months = (cash / abs(operating_cf)) * 3.0 if cash is not None and operating_cf is not None and operating_cf < 0 else None
    filing_dates = [str(value) for value in (balance.get("filing_date"), cash_flow.get("filing_date")) if value]
    return {
        "available": bool(fundamentals.get("available")), "provider": fundamentals.get("provider"),
        "errors": fundamentals.get("errors") or [], "market_cap": market_cap,
        "cash_and_equivalents": cash, "current_liabilities": current_liabilities,
        "total_debt": total_debt if (debt_current or long_debt) else None,
        "total_equity": total_equity, "total_assets": _number(balance.get("total_assets")),
        "total_liabilities": _number(balance.get("total_liabilities")),
        "operating_cash_flow_quarterly": operating_cf, "cash_to_current_liabilities": cash_to_current_liabilities,
        "debt_to_cash": debt_to_cash, "estimated_cash_runway_months": runway_months,
        "filing_dates": filing_dates, "sic_description": detail.get("sic_description"), "ticker_type": detail.get("type"),
    }


def resilience_score(candidate: dict[str, Any], risk_flags: list[str]) -> tuple[float, dict[str, Any], list[str]]:
    context = fundamental_context(candidate)
    missing: list[str] = []
    if not context["available"]:
        missing.append("fundamental_balance_sheet")
        score = 45.0
    else:
        score = 50.0
        cash_liab = _number(context.get("cash_to_current_liabilities"))
        if cash_liab is not None:
            if cash_liab >= 1.5:
                score += 15
            elif cash_liab >= 0.75:
                score += 8
            elif cash_liab < 0.20:
                score -= 18
            elif cash_liab < 0.40:
                score -= 8
        else:
            missing.append("cash_to_current_liabilities")
        debt_cash = _number(context.get("debt_to_cash"))
        if debt_cash is not None:
            if debt_cash <= 0.5:
                score += 8
            elif debt_cash >= 5:
                score -= 16
            elif debt_cash >= 2:
                score -= 8
        else:
            missing.append("debt_to_cash")
        equity = _number(context.get("total_equity"))
        if equity is not None and equity <= 0:
            score -= 15
        elif equity is None:
            missing.append("total_equity")
        operating_cf = _number(context.get("operating_cash_flow_quarterly"))
        runway = _number(context.get("estimated_cash_runway_months"))
        if operating_cf is not None:
            if operating_cf > 0:
                score += 8
            elif runway is not None:
                if runway >= 24:
                    score += 7
                elif runway >= 12:
                    score += 3
                elif runway < 6:
                    score -= 18
                elif runway < 9:
                    score -= 10
        else:
            missing.append("operating_cash_flow")
    if "solvency" in risk_flags:
        score = min(score, 20.0)
    if "delisting" in risk_flags:
        score = min(score, 38.0)
    return round(clamp(score), 1), context, sorted(set(missing))
