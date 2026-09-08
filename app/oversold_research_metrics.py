from __future__ import annotations

"""Additive research metrics for Oversold Reversion.

These fields are deliberately display/research inputs only. They do not change
any reversion score, eligibility gate or allocation rule.

Accounting metrics use SEC facts available strictly before the signal cutoff.
Forward P/E / expected EPS growth are best-effort scan-time consensus fields and
are persisted with the original evidence snapshot once captured.
"""

import math
import threading
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

RESEARCH_METRICS_VERSION = "oversold_research_metrics_v1"
FORWARD_SOURCE = "yahoo_finance_quote_v7_scan_time_v1"
FORWARD_TIMEOUT_SECONDS = 8.0
FORWARD_BATCH_SIZE = 40
CACHE_SECONDS = 6 * 60 * 60

DISPLAY_KEYS = (
    "peg_ratio",
    "forward_pe",
    "fcf_yield_pct",
    "roic_pct",
    "balance_sheet_strength_score",
    "expected_eps_growth_pct",
)
RESEARCH_KEYS = DISPLAY_KEYS + (
    "free_cash_flow_ttm",
    "operating_cash_flow_ttm",
    "capex_ttm",
    "operating_income_ttm",
    "pretax_income_ttm",
    "income_tax_expense_ttm",
    "roic_tax_rate",
    "roic_method",
    "fcf_yield_method",
    "balance_sheet_strength_method",
    "forward_eps",
    "trailing_eps",
    "forward_estimate_source",
    "forward_estimate_captured_at",
    "forward_estimate_basis",
    "research_metrics_version",
)

_YAHOO_URLS = (
    "https://query1.finance.yahoo.com/v7/finance/quote",
    "https://query2.finance.yahoo.com/v7/finance/quote",
)
_PRETAX_CONCEPTS = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesAndExtraordinaryItems",
)
_TAX_CONCEPTS = ("IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations")

_lock = threading.Lock()
_sec_json_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_forward_cache: dict[tuple[str, str], dict[str, Any]] = {}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


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


def _cutoff_key(cutoff: datetime) -> str:
    value = cutoff.astimezone(UTC) if cutoff.tzinfo else cutoff.replace(tzinfo=UTC)
    return value.isoformat()


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _dedupe_period_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the latest cutoff-valid restatement for each economic period."""
    selected: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in rows:
        start = row.get("_start")
        end = row.get("_end")
        if start is None or end is None:
            continue
        key = (start, end)
        existing = selected.get(key)
        row_key = (row.get("_filed") or date.min, str(row.get("accn") or ""))
        existing_key = (
            (existing or {}).get("_filed") or date.min,
            str((existing or {}).get("accn") or ""),
        )
        if existing is None or row_key > existing_key:
            selected[key] = row
    return list(selected.values())


def _ttm_from_rows(rows: list[dict[str, Any]]) -> float | None:
    rows = _dedupe_period_rows(rows)
    if not rows:
        return None
    latest_end = max(row["_end"] for row in rows)
    same_end = [row for row in rows if row["_end"] == latest_end]
    annual = [row for row in same_end if 300 <= int(row.get("_duration_days") or 0) <= 410]
    if annual:
        annual.sort(key=lambda row: (row.get("_filed") or date.min, str(row.get("accn") or "")), reverse=True)
        return _finite(annual[0].get("_value"))

    ytd = [row for row in same_end if 55 <= int(row.get("_duration_days") or 0) <= 300]
    if not ytd:
        return None
    current = max(ytd, key=lambda row: int(row.get("_duration_days") or 0))
    current_days = int(current.get("_duration_days") or 0)
    current_value = _finite(current.get("_value"))
    if current_value is None:
        return None

    prior_annual = [
        row for row in rows
        if row["_end"] < latest_end
        and 300 <= int(row.get("_duration_days") or 0) <= 410
        and 120 <= (latest_end - row["_end"]).days <= 500
    ]
    if not prior_annual:
        return None
    prior_year = max(prior_annual, key=lambda row: row["_end"])
    prior_year_value = _finite(prior_year.get("_value"))
    if prior_year_value is None:
        return None

    prior_ytd = [
        row for row in rows
        if row["_end"] < latest_end
        and 325 <= (latest_end - row["_end"]).days <= 405
        and abs(int(row.get("_duration_days") or 0) - current_days) <= 35
    ]
    if not prior_ytd:
        return None
    comparable = min(
        prior_ytd,
        key=lambda row: (
            abs((latest_end - row["_end"]).days - 365),
            abs(int(row.get("_duration_days") or 0) - current_days),
        ),
    )
    comparable_value = _finite(comparable.get("_value"))
    if comparable_value is None:
        return None
    return current_value + prior_year_value - comparable_value


def _ttm_flow(sec_module: Any, companyfacts: dict[str, Any], concepts: tuple[str, ...], cutoff_date: date) -> float | None:
    try:
        rows = sec_module._eligible_rows(companyfacts, concepts, cutoff_date, instant=False)
    except Exception:
        return None
    return _ttm_from_rows(rows)


def _balance_sheet_strength(fundamentals: dict[str, Any]) -> float | None:
    """Transparent 0-100 balance-sheet index; not a probability."""
    cash_to_assets = _finite(fundamentals.get("cash_to_assets"))
    equity_to_assets = _finite(fundamentals.get("equity_to_assets"))
    liabilities_to_assets = _finite(fundamentals.get("liabilities_to_assets"))
    current_ratio = _finite(fundamentals.get("current_ratio"))
    debt_to_assets = _finite(fundamentals.get("debt_to_assets"))

    components: list[tuple[float, float]] = []
    if cash_to_assets is not None:
        components.append((0.25, _clamp((cash_to_assets - 0.01) / 0.24 * 100.0)))
    if equity_to_assets is not None:
        components.append((0.25, _clamp(equity_to_assets / 0.60 * 100.0)))
    if liabilities_to_assets is not None:
        components.append((0.20, _clamp((1.0 - liabilities_to_assets) / 0.65 * 100.0)))
    if current_ratio is not None:
        components.append((0.15, _clamp((current_ratio - 0.50) / 1.50 * 100.0)))
    if debt_to_assets is not None:
        components.append((0.15, _clamp((0.80 - debt_to_assets) / 0.70 * 100.0)))
    if len(components) < 3:
        return None
    weight = sum(item[0] for item in components)
    return round(sum(w * score for w, score in components) / weight, 1) if weight else None


def _forward_row(raw: dict[str, Any], captured_at: datetime) -> dict[str, Any]:
    symbol = str(raw.get("symbol") or "").upper().strip()
    forward_pe = _finite(raw.get("forwardPE"))
    forward_eps = _finite(raw.get("epsForward"))
    trailing_eps = _finite(raw.get("epsTrailingTwelveMonths"))
    price = _finite(raw.get("regularMarketPrice"))
    if (forward_pe is None or forward_pe <= 0) and price and price > 0 and forward_eps and forward_eps > 0:
        forward_pe = price / forward_eps
    if forward_pe is not None and forward_pe <= 0:
        forward_pe = None

    expected_growth = None
    if forward_eps is not None and trailing_eps is not None and forward_eps > 0 and trailing_eps > 0:
        expected_growth = ((forward_eps / trailing_eps) - 1.0) * 100.0
    peg = None
    if forward_pe is not None and expected_growth is not None and expected_growth > 0:
        peg = forward_pe / expected_growth

    return {
        "symbol": symbol,
        "forward_pe": round(forward_pe, 3) if forward_pe is not None else None,
        "forward_eps": round(forward_eps, 6) if forward_eps is not None else None,
        "trailing_eps": round(trailing_eps, 6) if trailing_eps is not None else None,
        "expected_eps_growth_pct": round(expected_growth, 3) if expected_growth is not None else None,
        "peg_ratio": round(peg, 4) if peg is not None else None,
        "forward_estimate_source": FORWARD_SOURCE,
        "forward_estimate_captured_at": captured_at.astimezone(UTC).isoformat(),
        "forward_estimate_basis": "consensus forward EPS versus trailing-twelve-month EPS; PEG = forward P/E divided by positive expected EPS growth percent",
    }


def _fetch_yahoo_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    if not symbols:
        return []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; OversoldReversion/1.0; research-metrics)",
        "Accept": "application/json,text/plain,*/*",
    }
    params = {"symbols": ",".join(symbols)}
    for url in _YAHOO_URLS:
        try:
            with httpx.Client(headers=headers, timeout=httpx.Timeout(FORWARD_TIMEOUT_SECONDS, connect=4.0)) as client:
                response = client.get(url, params=params)
            if response.status_code != 200:
                continue
            payload = response.json()
            result = ((payload or {}).get("quoteResponse") or {}).get("result")
            if isinstance(result, list):
                return [row for row in result if isinstance(row, dict)]
        except Exception:
            continue
    return []


def fetch_forward_estimates_batch(symbols: list[str], cutoff: datetime) -> dict[str, dict[str, Any]]:
    clean = sorted({str(symbol).upper().strip() for symbol in symbols if symbol})
    if not clean:
        return {}
    captured_at = cutoff.astimezone(UTC) if cutoff.tzinfo else cutoff.replace(tzinfo=UTC)
    key_time = _cutoff_key(captured_at)
    output: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    with _lock:
        for symbol in clean:
            cached = _forward_cache.get((symbol, key_time))
            if cached is not None:
                output[symbol] = dict(cached)
            else:
                missing.append(symbol)
    for chunk in _chunks(missing, FORWARD_BATCH_SIZE):
        for raw in _fetch_yahoo_quotes(chunk):
            row = _forward_row(raw, captured_at)
            symbol = row.get("symbol")
            if symbol:
                output[str(symbol)] = row
    with _lock:
        for symbol in clean:
            value = dict(output.get(symbol) or {})
            _forward_cache[(symbol, key_time)] = value
    return output


def _cached_forward(symbol: str, cutoff: datetime) -> dict[str, Any]:
    with _lock:
        return dict(_forward_cache.get((symbol.upper(), _cutoff_key(cutoff))) or {})


def _install_sec_json_cache(sec_module: Any) -> None:
    if getattr(sec_module, "_research_metrics_json_cache_installed", False):
        return
    original = sec_module._get_json

    def cached(url: str) -> dict[str, Any]:
        now = time.monotonic()
        with _lock:
            hit = _sec_json_cache.get(url)
            if hit and now - hit[0] <= CACHE_SECONDS:
                return dict(hit[1])
        value = original(url)
        if isinstance(value, dict):
            with _lock:
                _sec_json_cache[url] = (now, dict(value))
            return dict(value)
        return {}

    sec_module._get_json = cached
    sec_module._research_metrics_json_cache_installed = True


def _extend_sec_fundamentals(sec_module: Any, fundamentals: dict[str, Any], cutoff: datetime) -> dict[str, Any]:
    output = dict(fundamentals)
    cik = str(output.get("cik") or "").strip()
    cutoff_date = cutoff.astimezone(UTC).date() if cutoff.tzinfo else cutoff.date()
    if cik:
        try:
            companyfacts = sec_module._get_json(sec_module.SEC_COMPANYFACTS_URL.format(cik=cik))
        except Exception:
            companyfacts = {}
        if companyfacts:
            ocf_ttm = _ttm_flow(sec_module, companyfacts, sec_module.DURATION_CONCEPTS["operating_cash_flow"], cutoff_date)
            capex_ttm = _ttm_flow(sec_module, companyfacts, sec_module.DURATION_CONCEPTS["capex"], cutoff_date)
            op_income_ttm = _ttm_flow(sec_module, companyfacts, sec_module.DURATION_CONCEPTS["operating_income"], cutoff_date)
            pretax_ttm = _ttm_flow(sec_module, companyfacts, _PRETAX_CONCEPTS, cutoff_date)
            tax_ttm = _ttm_flow(sec_module, companyfacts, _TAX_CONCEPTS, cutoff_date)
            if ocf_ttm is not None:
                output["operating_cash_flow_ttm"] = ocf_ttm
            if capex_ttm is not None:
                output["capex_ttm"] = capex_ttm
            if ocf_ttm is not None and capex_ttm is not None:
                output["free_cash_flow_ttm"] = ocf_ttm - abs(capex_ttm)
            if op_income_ttm is not None:
                output["operating_income_ttm"] = op_income_ttm
            if pretax_ttm is not None:
                output["pretax_income_ttm"] = pretax_ttm
            if tax_ttm is not None:
                output["income_tax_expense_ttm"] = tax_ttm

    output["balance_sheet_strength_score"] = _balance_sheet_strength(output)
    output["balance_sheet_strength_method"] = "weighted cutoff-valid cash/assets, equity/assets, liabilities/assets, current ratio and debt/assets; uncalibrated 0-100 index"
    output["research_metrics_version"] = RESEARCH_METRICS_VERSION
    return output


def _attach_market_derived(fundamentals: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    output = dict(fundamentals)
    signal_price = _finite(candidate.get("last_price"))
    shares = _finite(output.get("shares_outstanding")) or _finite(output.get("diluted_shares"))
    market_cap = _finite(output.get("market_cap"))
    if market_cap is None and signal_price is not None and signal_price > 0 and shares is not None and shares > 0:
        market_cap = signal_price * shares
        output["market_cap"] = market_cap

    fcf_ttm = _finite(output.get("free_cash_flow_ttm"))
    if fcf_ttm is not None and market_cap is not None and market_cap > 0:
        output["fcf_yield_pct"] = round(fcf_ttm / market_cap * 100.0, 3)
        output["fcf_yield_method"] = "cutoff-valid trailing-twelve-month free cash flow divided by signal-time market capitalisation"

    operating_income = _finite(output.get("operating_income_ttm"))
    equity = _finite(output.get("equity"))
    debt = _finite(output.get("total_debt")) or _finite(output.get("long_term_debt"))
    cash = _finite(output.get("cash")) or _finite(output.get("cash_and_equivalents"))
    if operating_income is not None and equity is not None:
        invested_capital = equity + (debt or 0.0) - (cash or 0.0)
        if invested_capital > 0:
            pretax = _finite(output.get("pretax_income_ttm"))
            tax = _finite(output.get("income_tax_expense_ttm"))
            tax_rate = 0.21
            if pretax is not None and pretax > 0 and tax is not None and tax >= 0:
                tax_rate = max(0.0, min(0.50, tax / pretax))
            roic = operating_income * (1.0 - tax_rate) / invested_capital * 100.0
            output["roic_pct"] = round(roic, 3)
            output["roic_tax_rate"] = round(tax_rate, 5)
            output["roic_method"] = "estimated NOPAT from cutoff-valid TTM operating income divided by equity + retained debt - cash; 21% normalized tax fallback"

    forward_pe = _finite(output.get("forward_pe"))
    expected_growth = _finite(output.get("expected_eps_growth_pct"))
    if forward_pe is not None and forward_pe > 0 and expected_growth is not None and expected_growth > 0:
        output["peg_ratio"] = round(forward_pe / expected_growth, 4)
    output["research_metrics_version"] = RESEARCH_METRICS_VERSION
    return output


def research_runtime_enrichment_wrapper(original: Any):
    def wrapped(candidate: dict[str, Any], sector_hint: str | None) -> dict[str, Any]:
        result = original(candidate, sector_hint)
        fundamentals = result.get("fundamentals")
        if not isinstance(fundamentals, dict):
            return result
        merged = dict(fundamentals)
        sec_prefetch = candidate.get("_sec_fundamentals")
        if isinstance(sec_prefetch, dict):
            for key in RESEARCH_KEYS:
                if key in sec_prefetch:
                    merged[key] = sec_prefetch.get(key)
            for key in ("shares_outstanding", "long_term_debt", "cash_and_equivalents", "equity", "debt_to_assets", "current_ratio"):
                if merged.get(key) is None and sec_prefetch.get(key) is not None:
                    merged[key] = sec_prefetch.get(key)
        cutoff = result.get("cutoff")
        if not isinstance(cutoff, datetime):
            cutoff = datetime.now(UTC)
        forward = _cached_forward(str(candidate.get("symbol") or ""), cutoff)
        for key, value in forward.items():
            if key != "symbol":
                merged[key] = value
        result["fundamentals"] = _attach_market_derived(merged, candidate)
        result["mode"] = f"{result.get('mode') or 'live'}+research-metrics"
        return result

    return wrapped


def patch_scoring_module(module: Any) -> None:
    legacy = getattr(module, "_legacy", None)
    if legacy is None or getattr(legacy, "_research_metrics_runtime_installed", False):
        return
    legacy.load_runtime_enrichment = research_runtime_enrichment_wrapper(legacy.load_runtime_enrichment)
    legacy._research_metrics_runtime_installed = True


def patch_scan_module(scan_module: Any, sec_module: Any) -> None:
    if getattr(scan_module, "_research_metrics_scan_installed", False):
        return
    _install_sec_json_cache(sec_module)
    original_batch = scan_module.fetch_sec_fundamentals_batch
    original_selector = scan_module._critical_sec_symbols

    def select_symbols(candidates: list[dict[str, Any]], candidate_limit: int) -> list[str]:
        selected = set(original_selector(candidates, candidate_limit))
        floor = min(len(candidates), max(60, int(candidate_limit)))
        selected.update(str(row.get("symbol") or "").upper() for row in candidates[:floor] if row.get("symbol"))
        return sorted(selected)

    def enriched_batch(symbols: list[str], cutoff: datetime, *, max_workers: int | None = None) -> dict[str, dict[str, Any]]:
        kwargs = {} if max_workers is None else {"max_workers": max_workers}
        base = original_batch(symbols, cutoff, **kwargs)
        forward = fetch_forward_estimates_batch(symbols, cutoff)
        output: dict[str, dict[str, Any]] = {}
        for symbol, fundamentals in base.items():
            if not isinstance(fundamentals, dict):
                continue
            enriched = _extend_sec_fundamentals(sec_module, fundamentals, cutoff)
            for key, value in (forward.get(str(symbol).upper()) or {}).items():
                if key != "symbol":
                    enriched[key] = value
            output[str(symbol).upper()] = enriched
        return output

    scan_module._critical_sec_symbols = select_symbols
    scan_module.fetch_sec_fundamentals_batch = enriched_batch
    scan_module._research_metrics_scan_installed = True


def patch_v2_module(module: Any) -> None:
    if getattr(module, "_research_metrics_v2_installed", False):
        return
    original_project = module._project_candidate
    original_selected = module._selected_fundamentals

    def project_candidate(row: dict[str, Any]) -> dict[str, Any]:
        projected = original_project(row)
        technical = row.get("technical_inputs") if isinstance(row.get("technical_inputs"), dict) else {}
        retained = technical.get("fundamentals") if isinstance(technical.get("fundamentals"), dict) else {}
        destination = projected.get("fundamentals") if isinstance(projected.get("fundamentals"), dict) else {}
        destination = dict(destination)
        for key in RESEARCH_KEYS:
            if key in retained:
                destination[key] = retained.get(key)
        projected["fundamentals"] = destination
        return projected

    def selected_fundamentals(candidate: dict[str, Any]) -> dict[str, Any]:
        selected = original_selected(candidate)
        fundamentals = candidate.get("fundamentals") if isinstance(candidate.get("fundamentals"), dict) else {}
        for key in DISPLAY_KEYS:
            if fundamentals.get(key) is not None:
                selected[key] = fundamentals.get(key)
        return selected

    module._project_candidate = project_candidate
    module._selected_fundamentals = selected_fundamentals
    module._research_metrics_v2_installed = True
