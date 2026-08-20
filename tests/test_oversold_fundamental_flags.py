from app.oversold_fundamentals import fundamental_risk_flags


def test_missing_or_healthy_fundamentals_do_not_create_damage_flags():
    assert fundamental_risk_flags(None) == []
    healthy = {
        "diluted_shares_yoy": 0.04,
        "cash_to_assets": 0.20,
        "liabilities_to_assets": 0.55,
        "equity_to_assets": 0.45,
    }
    assert fundamental_risk_flags(healthy) == []


def test_large_share_expansion_creates_dilution_flag():
    fragile = {
        "diluted_shares_yoy": 0.55,
        "cash_to_assets": 0.03,
        "liabilities_to_assets": 0.93,
        "equity_to_assets": 0.07,
    }
    assert fundamental_risk_flags(fragile) == ["dilution"]


def test_solvency_flag_requires_multiple_extreme_balance_sheet_conditions():
    extreme = {
        "diluted_shares_yoy": 0.10,
        "cash_to_assets": 0.005,
        "liabilities_to_assets": 1.08,
        "equity_to_assets": -0.08,
    }
    assert fundamental_risk_flags(extreme) == ["solvency"]

    merely_weak = {
        "diluted_shares_yoy": 0.10,
        "cash_to_assets": 0.02,
        "liabilities_to_assets": 0.94,
        "equity_to_assets": 0.03,
    }
    assert fundamental_risk_flags(merely_weak) == []
