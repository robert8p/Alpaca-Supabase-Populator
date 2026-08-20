from __future__ import annotations

import importlib
import sys
import types
import unittest
from datetime import UTC, datetime, timedelta


def import_backend_module():
    if "app.intraday_profitability" in sys.modules:
        return sys.modules["app.intraday_profitability"]

    psycopg = types.ModuleType("psycopg")
    psycopg_types = types.ModuleType("psycopg.types")
    psycopg_json = types.ModuleType("psycopg.types.json")
    psycopg_json.Jsonb = lambda value: value
    sys.modules.setdefault("psycopg", psycopg)
    sys.modules.setdefault("psycopg.types", psycopg_types)
    sys.modules.setdefault("psycopg.types.json", psycopg_json)

    alpaca = types.ModuleType("app.alpaca")
    alpaca.AlpacaClient = object
    sys.modules["app.alpaca"] = alpaca

    db = types.ModuleType("app.db")
    db.connection = lambda: None
    sys.modules["app.db"] = db

    oversold = types.ModuleType("app.oversold")
    oversold._fetch_snapshots = lambda *args, **kwargs: ({}, 0)
    oversold._is_operating_company_asset = lambda asset: True
    oversold.require_basic = lambda: "test"
    sys.modules["app.oversold"] = oversold

    return importlib.import_module("app.intraday_profitability")


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_backend_module()

    def test_prompt_is_point_in_time_and_top_ten_only(self):
        cutoff = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
        candidates = []
        for rank in range(1, 12):
            candidates.append(
                {
                    "rank": rank,
                    "symbol": f"T{rank}",
                    "name": f"Test {rank}",
                    "direction": "LONG",
                    "setup_type": "CONTINUATION",
                    "profitability_score": 80 - rank,
                    "initial_view": "WATCH",
                    "last_price": 100,
                    "day_move_pct": 1,
                    "spread_bps": 2,
                    "cost_estimate_bps": 5,
                    "move_capacity_120m_pct": 1.2,
                    "return_5m_pct": 0.1,
                    "return_15m_pct": 0.3,
                    "return_30m_pct": 0.5,
                    "return_60m_pct": 0.8,
                    "relative_return_15m_pct": 0.2,
                    "prev_dollar_volume": 500_000_000,
                    "current_dollar_volume": 100_000_000,
                    "relative_volume_pace": 2,
                    "liquidity_score": 90,
                    "opportunity_score": 70,
                    "directional_score": 75,
                    "confirmation_score": 72,
                    "execution_score": 92,
                    "rationale": "Test rationale.",
                    "evidence": {"bars_used": 60},
                }
            )
        prompt = self.module._build_chatgpt_prompt(
            {"scan": {"evidence_cutoff": cutoff, "horizon_end": cutoff + timedelta(minutes=120)}, "candidates": candidates}
        )
        self.assertIn("Do not use hindsight", prompt)
        self.assertIn("evidence cutoff", prompt.lower())
        self.assertIn("P(net profitable)", prompt)
        self.assertIn("10. T10", prompt)
        self.assertNotIn("11. T11", prompt)
        self.assertIn("unvalidated quantitative research heuristic", prompt)

    def test_full_horizon_guard_rejects_late_session(self):
        timestamp = datetime(2026, 8, 20, 18, 1, tzinfo=UTC)
        clock = {"is_open": True, "timestamp": timestamp.isoformat(), "next_close": (timestamp + timedelta(minutes=120)).isoformat()}
        with self.assertRaisesRegex(RuntimeError, "full two-hour"):
            self.module._market_times(clock)

    def test_bars_payload_accepts_alpaca_envelope(self):
        payload = self.module._bars_payload({"bars": {"ABC": [{"c": 1}], "SPY": [{"c": 2}]}, "next_page_token": None})
        self.assertEqual(set(payload), {"ABC", "SPY"})
        self.assertEqual(payload["ABC"][0]["c"], 1)

    def test_schema_has_unique_scan_symbol_contract(self):
        self.assertIn("UNIQUE(scan_id, symbol)", self.module.SCHEMA_SQL)
        self.assertIn("CHECK (direction IN ('LONG','SHORT'))", self.module.SCHEMA_SQL)

    def test_schema_protects_internal_tables_from_supabase_data_api(self):
        self.assertIn("ALTER TABLE public.ip_scans ENABLE ROW LEVEL SECURITY", self.module.SCHEMA_SQL)
        self.assertIn("ALTER TABLE public.ip_candidates ENABLE ROW LEVEL SECURITY", self.module.SCHEMA_SQL)
        self.assertIn(
            "REVOKE ALL ON TABLE public.ip_scans, public.ip_candidates FROM anon, authenticated",
            self.module.SCHEMA_SQL,
        )


if __name__ == "__main__":
    unittest.main()
