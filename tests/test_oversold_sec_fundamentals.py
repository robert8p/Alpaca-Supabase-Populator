from __future__ import annotations

import os
from datetime import UTC, datetime

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from app import oversold_sec_fundamentals as sec


def fact(val, *, end, filed, form="10-Q", start=None, accn="000-test"):
    row = {"val": val, "end": end, "filed": filed, "form": form, "accn": accn}
    if start is not None:
        row["start"] = start
    return row


def item(unit: str, rows: list[dict]) -> dict:
    return {"units": {unit: rows}}


def payloads() -> tuple[dict, dict]:
    current_filed = "2026-08-01"
    prior_filed = "2025-08-01"
    instant = lambda value: [
        fact(value, end="2026-06-30", filed=current_filed),
        fact(value * 9, end="2026-06-30", filed="2026-08-20"),
    ]
    quarter = lambda current, prior: [
        fact(current, start="2026-04-01", end="2026-06-30", filed=current_filed),
        fact(prior, start="2025-04-01", end="2025-06-30", filed=prior_filed),
    ]
    facts = {
        "facts": {
            "us-gaap": {
                "Assets": item("USD", instant(100.0)),
                "CashAndCashEquivalentsAtCarryingValue": item("USD", instant(20.0)),
                "Liabilities": item("USD", instant(40.0)),
                "StockholdersEquity": item("USD", instant(60.0)),
                "AssetsCurrent": item("USD", instant(50.0)),
                "LiabilitiesCurrent": item("USD", instant(25.0)),
                "LongTermDebt": item("USD", instant(10.0)),
                "CommonStockSharesOutstanding": item("shares", instant(10_000_000.0)),
                "RevenueFromContractWithCustomerExcludingAssessedTax": item("USD", quarter(30.0, 25.0)),
                "NetIncomeLoss": item("USD", quarter(3.0, 2.0)),
                "OperatingIncomeLoss": item("USD", quarter(4.0, 3.0)),
                "GrossProfit": item("USD", quarter(15.0, 12.0)),
                "NetCashProvidedByUsedInOperatingActivities": item("USD", quarter(-2.0, -1.0)),
                "PaymentsToAcquirePropertyPlantAndEquipment": item("USD", quarter(1.0, 1.0)),
                "WeightedAverageNumberOfDilutedSharesOutstanding": item("shares", quarter(10_000_000.0, 9_000_000.0)),
            }
        }
    }
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["000-test"],
                "form": ["10-Q"],
                "filingDate": [current_filed],
                "reportDate": ["2026-06-30"],
                "acceptanceDateTime": ["2026-08-01T12:00:00.000Z"],
            }
        }
    }
    return facts, submissions


def test_sec_companyfacts_are_point_in_time_and_derived(monkeypatch) -> None:
    facts, submissions = payloads()

    def fake_get(url: str):
        return submissions if "submissions" in url else facts

    monkeypatch.setattr(sec, "_get_json", fake_get)
    result = sec._derive_fundamentals(
        "TEST",
        "0000000001",
        datetime(2026, 8, 20, 15, 0, tzinfo=UTC),
    )
    assert result is not None
    assert result["source"] == "sec_companyfacts_point_in_time_v1"
    assert result["assets"] == 100.0
    assert round(result["revenue_yoy"], 4) == 0.2
    assert round(result["net_margin"], 4) == 0.1
    assert result["current_ratio"] == 2.0
    assert result["debt_to_assets"] == 0.1
    assert round(result["cash_runway_months"], 2) == 20.0
    assert round(result["diluted_shares_yoy"], 4) == round(1_000_000 / 9_000_000, 4)
    assert result["available_from"].isoformat() == "2026-08-01"


def test_same_day_filing_is_excluded() -> None:
    facts, _ = payloads()
    rows = sec._eligible_rows(
        facts,
        ("Assets",),
        datetime(2026, 8, 20, tzinfo=UTC).date(),
        instant=True,
    )
    assert len(rows) == 1
    assert rows[0]["_value"] == 100.0
    assert rows[0]["_filed"].isoformat() == "2026-08-01"
