from __future__ import annotations

from fastapi.testclient import TestClient

import app.reversion_guard_main as guard_app


def sample_payload():
    return {
        "scan": {"id": "00000000-0000-0000-0000-000000000001", "status": "completed", "started_at": "2026-08-19T15:00:00Z"},
        "candidates": [
            {
                "id": 7,
                "scan_id": "00000000-0000-0000-0000-000000000001",
                "rank": 1,
                "symbol": "TEMP",
                "name": "Temporary Semiconductor",
                "prev_close": 20.0,
                "last_price": 16.0,
                "drop_pct": -20.0,
                "prev_dollar_volume": 30_000_000,
                "spread_pct": 0.25,
                "evidence_cutoff": "2026-08-19T15:30:00Z",
                "latest_trade_ts": "2026-08-19T15:30:00Z",
                "catalyst_summary": "Temporary shipment delay; full-year guidance reaffirmed.",
                "risk_flags": [],
                "headlines": [],
                "headline_count": 0,
                "reversion_score": 80.0,
                "model_verdict": "INVESTIGATE",
                "resilience_score": 80.0,
                "confirmation_score": 80.0,
                "damage_risk": 20.0,
                "evidence_confidence": 80.0,
                "hard_veto": False,
                "sector_hint": "technology",
                "catalyst_analysis": {"catalyst_type": "temporary_operational"},
                "technical_inputs": {
                    "session_range_position": 85,
                    "gap_reclaim_pct": 50,
                    "low_reclaim_pct": 70,
                    "vwap_distance_pct": 1,
                    "return_from_open_pct": 3,
                    "atr20": 1,
                },
            }
        ],
    }


def test_latest_endpoint_enriches_upstream_payload(monkeypatch):
    async def fake_cached_get(path: str, force: bool = False):
        assert path == "/api/oversold/latest"
        return sample_payload()

    monkeypatch.setattr(guard_app, "_cached_get", fake_cached_get)
    with TestClient(guard_app.app) as client:
        response = client.get("/api/reversion-guard/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["guard_assessment"]["gate_code"] == "INVESTIGATE_CONFIRMED"
    assert body["portfolio"]["candidate_counts"]["investigate"] == 1


def test_position_endpoint_uses_latest_price_when_current_is_omitted(monkeypatch):
    async def fake_cached_get(path: str, force: bool = False):
        return sample_payload()

    monkeypatch.setattr(guard_app, "_cached_get", fake_cached_get)
    with TestClient(guard_app.app) as client:
        response = client.post(
            "/api/reversion-guard/positions/review",
            json={
                "position": {"symbol": "TEMP", "entry_price_usd": 20, "quantity": 10},
                "settings": {"account_value_gbp": 10000, "risk_budget_gbp": 50, "max_position_gbp": 500, "usd_per_gbp": 1.3, "max_theme_positions": 3, "max_open_risk_pct": 2},
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["current_price_usd"] == 16
    assert body["recovery_to_break_even_pct"] == 25


def test_policy_endpoint_exposes_non_negotiable_rules():
    with TestClient(guard_app.app) as client:
        response = client.get("/api/reversion-guard/policy")
    assert response.status_code == 200
    body = response.json()
    assert "No extended-hours entry" in body["entry_rule"]
    assert "Never average down" in body["averaging_rule"]
