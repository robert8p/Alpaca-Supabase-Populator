from app.oversold_v2 import _score_candidate


def base_item(drop_pct: float = -25.0):
    return {"drop_pct": drop_pct, "prev_dollar_volume": 20_000_000.0, "spread_pct": 0.4}


def strong_fundamentals():
    return {
        "revenue_yoy": 0.18,
        "net_margin": 0.12,
        "cash_to_assets": 0.24,
        "liabilities_to_assets": 0.35,
        "equity_to_assets": 0.58,
        "diluted_shares_yoy": 0.01,
    }


def fragile_fundamentals():
    return {
        "revenue_yoy": -0.35,
        "net_margin": -0.30,
        "cash_to_assets": 0.01,
        "liabilities_to_assets": 1.08,
        "equity_to_assets": -0.08,
        "diluted_shares_yoy": 0.35,
    }


def test_transient_event_with_strong_fundamentals_ranks_above_structural_event():
    transient = _score_candidate(base_item(), strong_fundamentals(), "B", [], 2)
    structural = _score_candidate(base_item(), strong_fundamentals(), "D", [], 2)
    assert transient["oversold_score"] > structural["oversold_score"]
    assert structural["oversold_score"] <= 40


def test_existential_risk_is_hard_capped_even_after_large_drop():
    result = _score_candidate(base_item(-55), strong_fundamentals(), "E", ["solvency"], 3)
    assert result["oversold_score"] <= 20
    assert result["initial_view"] == "Pass"


def test_missing_fundamentals_do_not_create_bullish_survivability():
    missing = _score_candidate(base_item(), None, "U", [], 0)
    strong = _score_candidate(base_item(), strong_fundamentals(), "U", [], 0)
    assert missing["fundamental_survivability"] == 35
    assert missing["confidence"] < strong["confidence"]
    assert missing["oversold_score"] < strong["oversold_score"]


def test_dilution_caps_opportunity_score():
    result = _score_candidate(base_item(-40), strong_fundamentals(), "C", ["dilution"], 2)
    assert result["oversold_score"] <= 55


def test_fragile_fundamentals_reduce_survivability():
    strong = _score_candidate(base_item(), strong_fundamentals(), "B", [], 2)
    fragile = _score_candidate(base_item(), fragile_fundamentals(), "B", [], 2)
    assert fragile["fundamental_survivability"] < strong["fundamental_survivability"]
    assert fragile["oversold_score"] < strong["oversold_score"]
