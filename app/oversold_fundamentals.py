from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.db import connection

FUNDAMENTAL_SOURCE = "research_pid_fundamental.filing_events_v1"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def fundamental_risk_flags(fundamentals: dict[str, Any] | None) -> list[str]:
    """Derive only high-confidence risk flags from cutoff-valid periodic filings.

    These flags feed the same structural-risk rules as news evidence. They are
    intentionally conservative: weak profitability alone does not become a
    solvency claim, and missing fundamentals produce no favourable or adverse flag.
    """
    if not fundamentals:
        return []
    flags: list[str] = []
    diluted_shares_yoy = _number(fundamentals.get("diluted_shares_yoy"))
    cash_to_assets = _number(fundamentals.get("cash_to_assets"))
    liabilities_to_assets = _number(fundamentals.get("liabilities_to_assets"))
    equity_to_assets = _number(fundamentals.get("equity_to_assets"))

    if diluted_shares_yoy is not None and diluted_shares_yoy >= 0.20:
        flags.append("dilution")

    # Only label filing-derived solvency risk when multiple balance-sheet ratios
    # simultaneously indicate an extreme condition. This is a risk flag, not a
    # declaration of bankruptcy or going-concern status.
    if (
        cash_to_assets is not None
        and liabilities_to_assets is not None
        and equity_to_assets is not None
        and cash_to_assets <= 0.01
        and liabilities_to_assets >= 1.00
        and equity_to_assets <= 0.00
    ):
        flags.append("solvency")
    return flags


def load_point_in_time_fundamentals(symbols: list[str], cutoff: datetime) -> dict[str, dict[str, Any]]:
    """Load the newest periodic filing facts known strictly before the signal date.

    The research cache exposes `available_from` as a date rather than an exact SEC
    acceptance timestamp. To prevent same-day look-ahead leakage, a filing dated on
    the signal date is deliberately not used by the original model run.
    """
    clean_symbols = sorted({str(symbol).upper() for symbol in symbols if symbol})
    if not clean_symbols:
        return {}
    cutoff_date = cutoff.date()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol)
                    symbol,accession_number,form,available_from,report_period_end,research_block,
                    revenue_yoy,net_margin,net_margin_yoy_delta,operating_margin,gross_margin,
                    eps_change_symmetric,net_income_change_symmetric,diluted_shares_yoy,
                    cash_to_assets,liabilities_to_assets,equity_to_assets,metric_coverage_count,
                    source_definition_hash,created_at
                FROM research_pid_fundamental.filing_events_v1
                WHERE symbol = ANY(%s)
                  AND available_from < %s
                  AND form IN ('10-Q','10-Q/A','10-K','10-K/A','20-F','20-F/A','40-F','40-F/A')
                ORDER BY symbol,available_from DESC,report_period_end DESC NULLS LAST,created_at DESC
                """,
                (clean_symbols, cutoff_date),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()

    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        available_from = row.get("available_from")
        age_days = (cutoff_date - available_from).days if available_from is not None else None
        row["source"] = FUNDAMENTAL_SOURCE
        row["point_in_time_rule"] = "available_from_strictly_before_signal_date"
        row["age_calendar_days"] = age_days
        row["derived_risk_flags"] = fundamental_risk_flags(row)
        output[str(row["symbol"]).upper()] = row
    return output
