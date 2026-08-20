from pathlib import Path

from app.oversold_v2 import (
    CHATGPT_LAUNCH_MAX_CHARS,
    _build_launch_prompt,
    _is_researchable_equity,
    _project_candidate,
    _project_scan,
)


def robust_row(symbol: str = "TEST", *, score: float | None = 61.2, verdict: str = "WATCH") -> dict:
    return {
        "id": 1,
        "rank": 1,
        "symbol": symbol,
        "name": f"{symbol} Operating Company Common Stock",
        "exchange": "NASDAQ",
        "prev_close": 10.0,
        "last_price": 8.0,
        "drop_pct": -20.0,
        "prev_dollar_volume": 12_000_000.0,
        "spread_pct": 0.6,
        "reversion_score": score,
        "model_verdict": verdict,
        "model_status": "uncalibrated",
        "setup_score": 72.0,
        "resilience_score": 68.0,
        "confirmation_score": 52.0,
        "damage_risk": 28.0,
        "evidence_confidence": 82.0,
        "hard_veto": False,
        "scoring_model_version": "oversold_reversion_score_v3_5",
        "scoring_config_version": "or_score_config_test",
        "target_definition": "hit_reversion_within_3_trading_sessions",
        "headline_count": 2,
        "headlines": [],
        "risk_flags": [],
        "evidence_cutoff": "2026-08-20T19:00:00Z",
        "catalyst_analysis": {
            "cause_verified": True,
            "cause_verification_status": "VERIFIED",
            "event_profile": "temporary_operational",
            "catalyst_type": "temporary",
            "primary_catalyst": "Temporary disruption with operations expected to normalise",
            "reversibility_score": 84.0,
            "overreaction_quality_score": 77.0,
            "three_session_fit_score": 73.0,
            "tail_risk_score": 31.0,
            "fundamental_evidence_state": "VERIFIED_PRIMARY",
            "fundamental_evidence_confidence": 85.0,
            "fundamental_data_quality_score": 92.0,
            "fundamental_trace": {
                "available": True,
                "source": "sec_companyfacts_point_in_time_v1",
                "form": "10-Q",
                "available_from": "2026-08-15",
                "report_period_end": "2026-06-30",
                "age_calendar_days": 5,
                "metric_coverage_count": 18,
                "raw_metrics": {
                    "revenue_yoy": 0.12,
                    "net_margin": 0.08,
                    "cash_to_assets": 0.24,
                    "liabilities_to_assets": 0.42,
                    "equity_to_assets": 0.58,
                    "cash_runway_months": 20.0,
                },
            },
            "price_session_context": {
                "price_session": "regular",
                "current_move_pct": -20.0,
                "regular_session_move_pct": -20.0,
                "extended_hours_move_pct": None,
                "extended_hours_only": False,
            },
            "red_flags": [],
            "failed_eligibility_gates": [],
            "source_claims": [
                {
                    "headline": "Company reports temporary disruption",
                    "source": "SEC EDGAR",
                    "published_at": "2026-08-20T12:00:00Z",
                    "url": "https://example.invalid/evidence",
                }
            ],
            "estimated_round_trip_friction_pct": 0.8,
            "source_dependency_risk": 20.0,
        },
        "calculation_trace": {"final": {"failed_eligibility_gates": []}},
    }


def test_projection_uses_canonical_robust_score_and_verified_sec_fundamentals() -> None:
    projected = _project_candidate(robust_row())
    assert projected["oversold_score"] == 61.2
    assert projected["initial_view"] == "Watch"
    assert projected["fundamental_quality"].startswith("Verified ·")
    assert projected["fundamentals"]["cash_to_assets"] == 0.24
    assert projected["cause_verified"] is True
    assert projected["scoring_model_version"] == "oversold_reversion_score_v3_5"


def test_after_hours_projection_uses_regular_day_move_but_retains_latest_move() -> None:
    row = robust_row()
    row["drop_pct"] = -22.0
    row["catalyst_analysis"]["price_session_context"] = {
        "price_session": "after_hours",
        "current_move_pct": -22.0,
        "regular_session_move_pct": -18.0,
        "extended_hours_move_pct": -4.88,
        "extended_hours_only": False,
    }
    projected = _project_candidate(row)
    assert projected["drop_pct"] == -18.0
    assert projected["latest_move_pct"] == -22.0
    assert projected["price_session"] == "after_hours"


def test_missing_canonical_model_is_conservative() -> None:
    row = robust_row(score=None, verdict="INVESTIGATE")
    projected = _project_candidate(row)
    assert projected["oversold_score"] == 0.0
    assert projected["initial_view"] == "Pass"
    assert projected["model_missing"] is True


def test_shell_and_spac_rows_are_excluded_then_remaining_rows_are_reranked() -> None:
    spac = robust_row("SPAC", score=90.0, verdict="INVESTIGATE")
    spac["name"] = "Example Acquisition Corp. Ordinary Shares"
    operating = robust_row("OPER", score=55.0, verdict="WATCH")
    detail = {
        "scan": {"id": "scan", "status": "completed", "candidate_count": 2, "metadata": {}},
        "candidates": [spac, operating],
    }
    projected = _project_scan(detail)
    assert _is_researchable_equity(spac) is False
    assert [row["symbol"] for row in projected["candidates"]] == ["OPER"]
    assert projected["candidates"][0]["rank"] == 1
    assert projected["scan"]["excluded_non_operating_count"] == 1


def test_compact_chatgpt_launch_prompt_is_bounded_and_keeps_all_top_tickers() -> None:
    candidates = []
    for index in range(10):
        row = _project_candidate(robust_row(f"T{index}", score=60.0 - index, verdict="WATCH"))
        row["rank"] = index + 1
        row["catalyst_summary"] = "Very long causal explanation " * 100
        candidates.append(row)
    detail = {
        "scan": {
            "scoring_model_version": "oversold_reversion_score_v3_5",
            "model_status": "uncalibrated",
            "evidence_cutoff": "2026-08-20T19:00:00Z",
        },
        "candidates": candidates,
    }
    prompt = _build_launch_prompt(detail)
    assert len(prompt) <= CHATGPT_LAUNCH_MAX_CHARS
    for index in range(10):
        assert f"T{index}" in prompt


def test_frontend_uses_compact_launch_prompt_and_requested_view_colours() -> None:
    source = Path("app/static/oversold_v2.js").read_text(encoding="utf-8")
    assert "payload.launch_prompt || fullPrompt" in source
    assert "view === 'pass'" in source and "return 'good'" in source
    assert "view === 'watch'" in source and "return 'mid'" in source
    assert "view === 'fail' || view === 'investigate'" in source and "return 'bad'" in source
