from __future__ import annotations

"""Point-in-time SEC fundamentals fallback for Oversold Reversion.

The existing research cache remains the preferred source.  This module only fills
symbols missing from that cache and applies a strict filed-before-cutoff rule so
same-day filings cannot leak into an original signal.
"""

import concurrent.futures
import math
import os
import threading
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_CACHE_SECONDS = 6 * 60 * 60
SEC_TIMEOUT_SECONDS = float(os.getenv("OVERSOLD_SEC_TIMEOUT_SECONDS", "7"))
SEC_MAX_WORKERS = max(1, min(6, int(os.getenv("OVERSOLD_SEC_MAX_WORKERS", "4"))))
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "OversoldReversion/1.0 contact=robert8p@gmail.com",
)

_lock = threading.Lock()
_ticker_cache: tuple[float, dict[str, str]] | None = None
_fundamental_cache: dict[tuple[str, str], tuple[float, dict[str, Any] | None]] = {}

PERIODIC_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}

BALANCE_CONCEPTS: dict[str, tuple[str, ...]] = {
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndDueFromBanks",
    ),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "long_term_debt": (
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "LongTermDebtCurrent",
    ),
    "shares_outstanding": (
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ),
}
DURATION_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_income": ("OperatingIncomeLoss",),
    "gross_profit": ("GrossProfit",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForProceedsFromOtherPropertyPlantAndEquipment",
    ),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _headers() -> dict[str, str]:
    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def _get_json(url: str) -> dict[str, Any]:
    with httpx.Client(headers=_headers(), timeout=httpx.Timeout(SEC_TIMEOUT_SECONDS, connect=4.0)) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {}


def _ticker_map() -> dict[str, str]:
    global _ticker_cache
    now = time.monotonic()
    with _lock:
        if _ticker_cache and now - _ticker_cache[0] <= SEC_CACHE_SECONDS:
            return dict(_ticker_cache[1])
    payload = _get_json(SEC_TICKERS_URL)
    mapping: dict[str, str] = {}
    for row in payload.values():
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper().strip()
        cik = row.get("cik_str")
        if ticker and cik is not None:
            mapping[ticker] = f"{int(cik):010d}"
    with _lock:
        _ticker_cache = (now, mapping)
    return dict(mapping)


def _units_for_concept(companyfacts: dict[str, Any], concept: str) -> list[dict[str, Any]]:
    facts = companyfacts.get("facts") if isinstance(companyfacts.get("facts"), dict) else {}
    for namespace in ("us-gaap", "dei", "ifrs-full"):
        ns = facts.get(namespace)
        if not isinstance(ns, dict):
            continue
        item = ns.get(concept)
        if not isinstance(item, dict):
            continue
        units = item.get("units")
        if not isinstance(units, dict):
            continue
        rows: list[dict[str, Any]] = []
        for unit_name, values in units.items():
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict):
                    rows.append({**value, "_unit": unit_name, "_concept": concept})
        if rows:
            return rows
    return []


def _eligible_rows(
    companyfacts: dict[str, Any],
    concepts: tuple[str, ...],
    cutoff_date: date,
    *,
    instant: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept in concepts:
        for row in _units_for_concept(companyfacts, concept):
            filed = _parse_date(row.get("filed"))
            end = _parse_date(row.get("end"))
            start = _parse_date(row.get("start"))
            form = str(row.get("form") or "")
            value = _finite(row.get("val"))
            if (
                filed is None
                or end is None
                or value is None
                or form not in PERIODIC_FORMS
                or filed >= cutoff_date
            ):
                continue
            if instant and start is not None:
                continue
            if not instant and start is None:
                continue
            duration_days = (end - start).days if start is not None else None
            rows.append(
                {
                    **row,
                    "_filed": filed,
                    "_end": end,
                    "_start": start,
                    "_duration_days": duration_days,
                    "_value": value,
                }
            )
    return rows


def _latest_instant(companyfacts: dict[str, Any], concepts: tuple[str, ...], cutoff_date: date) -> dict[str, Any] | None:
    rows = _eligible_rows(companyfacts, concepts, cutoff_date, instant=True)
    if not rows:
        return None
    rows.sort(key=lambda row: (row["_end"], row["_filed"], str(row.get("accn") or "")), reverse=True)
    return rows[0]


def _duration_kind(row: dict[str, Any]) -> str:
    days = int(row.get("_duration_days") or 0)
    if 65 <= days <= 125:
        return "quarter"
    if 250 <= days <= 410:
        return "annual"
    if 125 < days < 250:
        return "interim"
    return "other"


def _latest_duration(companyfacts: dict[str, Any], concepts: tuple[str, ...], cutoff_date: date) -> dict[str, Any] | None:
    rows = _eligible_rows(companyfacts, concepts, cutoff_date, instant=False)
    if not rows:
        return None
    priority = {"quarter": 4, "annual": 3, "interim": 2, "other": 1}
    rows.sort(
        key=lambda row: (
            row["_end"],
            priority[_duration_kind(row)],
            row["_filed"],
            -abs((row.get("_duration_days") or 0) - (90 if _duration_kind(row) == "quarter" else 365)),
        ),
        reverse=True,
    )
    latest_end = rows[0]["_end"]
    near_latest = [row for row in rows if abs((latest_end - row["_end"]).days) <= 10]
    near_latest.sort(
        key=lambda row: (
            priority[_duration_kind(row)],
            row["_filed"],
            -abs((row.get("_duration_days") or 0) - (90 if _duration_kind(row) == "quarter" else 365)),
        ),
        reverse=True,
    )
    return near_latest[0]


def _prior_comparable(
    companyfacts: dict[str, Any],
    concepts: tuple[str, ...],
    cutoff_date: date,
    latest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not latest:
        return None
    rows = _eligible_rows(companyfacts, concepts, cutoff_date, instant=False)
    target_end = latest["_end"]
    target_days = int(latest.get("_duration_days") or 0)
    candidates = [
        row
        for row in rows
        if 330 <= (target_end - row["_end"]).days <= 400
        and abs(int(row.get("_duration_days") or 0) - target_days) <= 25
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row["_end"], row["_filed"]), reverse=True)
    return candidates[0]


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _symmetric_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    denominator = abs(current) + abs(prior)
    return None if denominator == 0 else 2.0 * (current - prior) / denominator


def _submission_ref(submissions: dict[str, Any], cutoff_date: date) -> dict[str, Any] | None:
    recent = ((submissions.get("filings") or {}).get("recent") or {}) if isinstance(submissions, dict) else {}
    if not isinstance(recent, dict):
        return None
    accessions = recent.get("accessionNumber") or []
    forms = recent.get("form") or []
    filing_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    accepted = recent.get("acceptanceDateTime") or []
    for index, form in enumerate(forms):
        if str(form) not in PERIODIC_FORMS:
            continue
        filed = _parse_date(filing_dates[index] if index < len(filing_dates) else None)
        if filed is None or filed >= cutoff_date:
            continue
        return {
            "accession_number": accessions[index] if index < len(accessions) else None,
            "form": form,
            "available_from": filed,
            "report_period_end": _parse_date(report_dates[index] if index < len(report_dates) else None),
            "acceptance_datetime": accepted[index] if index < len(accepted) else None,
        }
    return None


def _value(row: dict[str, Any] | None) -> float | None:
    return _finite(row.get("_value")) if row else None


def _derive_fundamentals(symbol: str, cik: str, cutoff: datetime) -> dict[str, Any] | None:
    cutoff_date = cutoff.astimezone(UTC).date() if cutoff.tzinfo else cutoff.date()
    companyfacts = _get_json(SEC_COMPANYFACTS_URL.format(cik=cik))
    submissions: dict[str, Any] = {}
    try:
        submissions = _get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
    except Exception:
        submissions = {}

    instant = {
        name: _latest_instant(companyfacts, concepts, cutoff_date)
        for name, concepts in BALANCE_CONCEPTS.items()
    }
    duration = {
        name: _latest_duration(companyfacts, concepts, cutoff_date)
        for name, concepts in DURATION_CONCEPTS.items()
    }
    if not any(instant.values()) and not any(duration.values()):
        return None

    prior = {
        name: _prior_comparable(companyfacts, DURATION_CONCEPTS[name], cutoff_date, duration[name])
        for name in DURATION_CONCEPTS
    }
    cash = _value(instant["cash"])
    assets = _value(instant["assets"])
    liabilities = _value(instant["liabilities"])
    equity = _value(instant["equity"])
    current_assets = _value(instant["current_assets"])
    current_liabilities = _value(instant["current_liabilities"])
    debt = _value(instant["long_term_debt"])
    shares = _value(instant["shares_outstanding"])

    revenue = _value(duration["revenue"])
    prior_revenue = _value(prior["revenue"])
    net_income = _value(duration["net_income"])
    prior_net_income = _value(prior["net_income"])
    operating_income = _value(duration["operating_income"])
    gross_profit = _value(duration["gross_profit"])
    ocf = _value(duration["operating_cash_flow"])
    capex = _value(duration["capex"])
    diluted_shares = _value(duration["diluted_shares"])
    prior_diluted_shares = _value(prior["diluted_shares"])

    period_kind = _duration_kind(duration["revenue"]) if duration["revenue"] else (
        _duration_kind(duration["net_income"]) if duration["net_income"] else "unknown"
    )
    months = 3.0 if period_kind == "quarter" else 12.0 if period_kind == "annual" else 6.0
    free_cash_flow = None if ocf is None else ocf - (capex or 0.0)
    cash_burn = -free_cash_flow if free_cash_flow is not None and free_cash_flow < 0 else 0.0
    runway_months = (cash / cash_burn * months) if cash is not None and cash_burn and cash_burn > 0 else None

    filing_ref = _submission_ref(submissions, cutoff_date)
    source_rows = [row for row in [*instant.values(), *duration.values()] if row]
    freshest_filed = max((row["_filed"] for row in source_rows), default=None)
    latest_period = max((row["_end"] for row in source_rows), default=None)
    accession = (filing_ref or {}).get("accession_number") or next(
        (row.get("accn") for row in source_rows if row.get("accn")), None
    )
    form = (filing_ref or {}).get("form") or next((row.get("form") for row in source_rows if row.get("form")), None)

    metrics = {
        "revenue_yoy": _ratio((revenue - prior_revenue) if revenue is not None and prior_revenue is not None else None, abs(prior_revenue) if prior_revenue else None),
        "net_margin": _ratio(net_income, revenue),
        "net_margin_yoy_delta": (
            (_ratio(net_income, revenue) or 0.0) - (_ratio(prior_net_income, prior_revenue) or 0.0)
            if _ratio(net_income, revenue) is not None and _ratio(prior_net_income, prior_revenue) is not None
            else None
        ),
        "operating_margin": _ratio(operating_income, revenue),
        "gross_margin": _ratio(gross_profit, revenue),
        "eps_change_symmetric": None,
        "net_income_change_symmetric": _symmetric_change(net_income, prior_net_income),
        "diluted_shares_yoy": _ratio(
            (diluted_shares - prior_diluted_shares)
            if diluted_shares is not None and prior_diluted_shares is not None
            else None,
            abs(prior_diluted_shares) if prior_diluted_shares else None,
        ),
        "cash_to_assets": _ratio(cash, assets),
        "liabilities_to_assets": _ratio(liabilities, assets),
        "equity_to_assets": _ratio(equity, assets),
        "debt_to_assets": _ratio(debt, assets),
        "current_ratio": _ratio(current_assets, current_liabilities),
        "cash_runway_months": runway_months,
        "free_cash_flow": free_cash_flow,
        "operating_cash_flow": ocf,
        "cash_and_equivalents": cash,
        "long_term_debt": debt,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "shares_outstanding": shares,
        "latest_revenue": revenue,
        "period_kind": period_kind,
    }
    covered = [key for key, value in metrics.items() if value is not None and key not in {"period_kind"}]
    if len(covered) < 3:
        return None
    age_days = (cutoff_date - freshest_filed).days if freshest_filed else None
    return {
        "symbol": symbol,
        "cik": cik,
        "source": "sec_companyfacts_point_in_time_v1",
        "source_url": SEC_COMPANYFACTS_URL.format(cik=cik),
        "accession_number": accession,
        "form": form,
        "available_from": freshest_filed,
        "report_period_end": latest_period,
        "age_calendar_days": age_days,
        "metric_coverage_count": len(covered),
        "source_definition_hash": "sec_companyfacts_point_in_time_v1",
        "point_in_time_rule": "sec_filed_date_strictly_before_signal_date",
        **metrics,
    }


def fetch_sec_fundamentals(symbol: str, cutoff: datetime) -> dict[str, Any] | None:
    clean = str(symbol or "").upper().strip()
    if not clean:
        return None
    cutoff_date = cutoff.astimezone(UTC).date() if cutoff.tzinfo else cutoff.date()
    cache_key = (clean, cutoff_date.isoformat())
    now = time.monotonic()
    with _lock:
        cached = _fundamental_cache.get(cache_key)
        if cached and now - cached[0] <= SEC_CACHE_SECONDS:
            return dict(cached[1]) if isinstance(cached[1], dict) else None
    cik = _ticker_map().get(clean)
    if not cik:
        return None
    try:
        result = _derive_fundamentals(clean, cik, cutoff)
    except Exception:
        result = None
    with _lock:
        _fundamental_cache[cache_key] = (now, result)
    return dict(result) if isinstance(result, dict) else None


def fetch_sec_fundamentals_batch(
    symbols: list[str],
    cutoff: datetime,
    *,
    max_workers: int = SEC_MAX_WORKERS,
) -> dict[str, dict[str, Any]]:
    clean = sorted({str(symbol).upper().strip() for symbol in symbols if symbol})
    if not clean:
        return {}
    output: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_sec_fundamentals, symbol, cutoff): symbol for symbol in clean}
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                value = future.result()
            except Exception:
                value = None
            if isinstance(value, dict):
                output[symbol] = value
    return output


def runtime_enrichment_wrapper(original: Any):
    """Attach prefetched/fallback SEC facts after normal market enrichment."""

    def wrapped(candidate: dict[str, Any], sector_hint: str | None) -> dict[str, Any]:
        result = original(candidate, sector_hint)
        if isinstance(result.get("fundamentals"), dict):
            return result
        cutoff = result.get("cutoff")
        if not isinstance(cutoff, datetime):
            cutoff = datetime.now(UTC)
        symbol = str(candidate.get("symbol") or "").upper()
        fundamentals = candidate.get("_sec_fundamentals")
        if not isinstance(fundamentals, dict) and not candidate.get("_sec_prefetch_complete"):
            fundamentals = fetch_sec_fundamentals(symbol, cutoff)
        if isinstance(fundamentals, dict):
            fundamentals = dict(fundamentals)
            signal_price = _finite(candidate.get("last_price"))
            shares = _finite(fundamentals.get("shares_outstanding"))
            revenue = _finite(fundamentals.get("latest_revenue"))
            period_kind = str(fundamentals.get("period_kind") or "unknown")
            annualizer = 4.0 if period_kind == "quarter" else 2.0 if period_kind == "interim" else 1.0
            market_cap = signal_price * shares if signal_price and shares else None
            annualized_revenue = revenue * annualizer if revenue is not None else None
            fundamentals["market_cap"] = market_cap
            fundamentals["annualized_revenue"] = annualized_revenue
            fundamentals["price_to_sales"] = _ratio(market_cap, annualized_revenue)
            result["fundamentals"] = fundamentals
            result["mode"] = f"{result.get('mode') or 'live'}+sec"
            result.setdefault("errors", [])
        return result

    return wrapped
