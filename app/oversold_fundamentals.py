from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db import connection

FUNDAMENTAL_SOURCE = "research_pid_fundamental.filing_events_v1"


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
        output[str(row["symbol"]).upper()] = row
    return output
