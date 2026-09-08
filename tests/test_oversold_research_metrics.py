from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from app.oversold_research_metrics import (
    _attach_market_derived,
    _balance_sheet_strength,
    _forward_row,
    _ttm_from_rows,
)


def flow_row(start: date, end: date, value: float, filed: date, accn: str) -> dict:
    return {
        "_start": start,
        "_end": end,
        "_duration_days": (end - start).days,
        "_value": value,
        "_filed": filed,
        "accn": accn,
    }


def test_ttm_reconstructs_latest_ytd_plus_prior_year_less_prior_ytd() -> None:
    rows = [
        flow_row(date(2026, 1, 1), date(2026, 6, 30), 60.0, date(2026, 8, 1), "current-ytd"),
        flow_row(date(2025, 1, 1), date(2025, 12, 31), 100.0, date(2026, 2, 1), "prior-fy"),
        flow_row(date(2025, 1, 1), date(2025, 6, 30), 40.0, date(2025, 8, 1), "prior-ytd"),
    ]
    assert _ttm_from_rows(rows) == 120.0


def test_ttm_prefers_latest_cutoff_valid_restatement_for_same_period() -> None:
    rows = [
        flow_row(date(2025, 1, 1), date(2025, 12, 31), 90.0, date(2026, 1, 20), "old"),
        flow_row(date(2025, 1, 1), date(2025, 12, 31), 100.0, date(2026, 2, 20), "new"),
    ]
    assert _ttm_from_rows(rows) == 100.0


def test_forward_peg_uses_forward_pe_divided_by_positive_expected_growth_percent() -> None:
    captured = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
    result = _forward_row(
        {
            "symbol": "TEST",
            "forwardPE": 20.0,
            "epsForward": 6.0,
            "epsTrailingTwelveMonths": 5.0,
            "regularMarketPrice": 100.0,
        },
        captured,
    )
    assert result["forward_pe"] == 20.0
    assert result["expected_eps_growth_pct"] == 20.0
    assert result["peg_ratio"] == 1.0
    assert result["forward_estimate_captured_at"] == captured.isoformat()


def test_forward_peg_is_unavailable_when_expected_eps_growth_is_not_positive() -> None:
    result = _forward_row(
        {
            "symbol": "TEST",
            "forwardPE": 12.0,
            "epsForward": 4.0,
            "epsTrailingTwelveMonths": 5.0,
        },
        datetime(2026, 9, 8, tzinfo=UTC),
    )
    assert result["expected_eps_growth_pct"] == -20.0
    assert result["peg_ratio"] is None


def test_market_derived_metrics_use_signal_price_and_cutoff_valid_ttm_inputs() -> None:
    fundamentals = {
        "shares_outstanding": 100.0,
        "free_cash_flow_ttm": 100.0,
        "operating_income_ttm": 200.0,
        "pretax_income_ttm": 250.0,
        "income_tax_expense_ttm": 50.0,
        "equity": 500.0,
        "long_term_debt": 100.0,
        "cash_and_equivalents": 100.0,
        "forward_pe": 20.0,
        "expected_eps_growth_pct": 20.0,
    }
    result = _attach_market_derived(fundamentals, {"last_price": 10.0})
    assert result["market_cap"] == 1000.0
    assert result["fcf_yield_pct"] == 10.0
    assert result["roic_pct"] == 32.0
    assert result["peg_ratio"] == 1.0


def test_balance_sheet_strength_is_bounded_and_requires_multiple_inputs() -> None:
    score = _balance_sheet_strength(
        {
            "cash_to_assets": 0.20,
            "equity_to_assets": 0.55,
            "liabilities_to_assets": 0.45,
            "current_ratio": 1.8,
            "debt_to_assets": 0.20,
        }
    )
    assert score is not None and 0 <= score <= 100
    assert _balance_sheet_strength({"cash_to_assets": 0.20, "current_ratio": 1.5}) is None


def test_main_and_v2_column_enhancer_contains_all_requested_metrics() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "app/static/oversold_fundamental_columns.js").read_text(encoding="utf-8")
    for text in ["PEG", "Forward P/E", "FCF yield", "ROIC", "Balance sheet", "EPS growth"]:
        assert text in script
    assert "/api/oversold-v2/latest" in script
    assert "technical_inputs?.fundamentals" in script


def test_research_metrics_do_not_add_a_new_scoring_gate() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/oversold_research_metrics.py").read_text(encoding="utf-8")
    assert "display/research inputs only" in source
    assert "eligibility_gates" not in source
    assert "decision_thresholds" not in source
