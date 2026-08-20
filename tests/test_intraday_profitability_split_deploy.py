from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "app" / "intraday_profitability_worker.py"
TRACKER = ROOT / "app" / "intraday_profitability_tracking.py"
OUTCOME = ROOT / "app" / "oversold_outcome_scheduler.py"
EDGE_DIR = ROOT / "supabase" / "functions" / "intraday-profitability-api"
EDGE = EDGE_DIR / "index.ts"
SCHEMA = EDGE_DIR / "public_access_schema.sql"
HTML = ROOT / "static_intraday" / "index.html"
JS = ROOT / "static_intraday" / "app.js"
PROMPT_JS = ROOT / "static_intraday" / "prompt.js"


class SplitDeploymentContractTests(unittest.TestCase):
    def test_python_modules_parse(self) -> None:
        ast.parse(WORKER.read_text(encoding="utf-8"))
        ast.parse(TRACKER.read_text(encoding="utf-8"))
        ast.parse(OUTCOME.read_text(encoding="utf-8"))

    def test_existing_worker_task_hosts_queue_and_tracking_schedulers(self) -> None:
        outcome_source = OUTCOME.read_text(encoding="utf-8")
        worker_source = WORKER.read_text(encoding="utf-8")
        self.assertIn("run_intraday_profitability_request_scheduler", outcome_source)
        self.assertIn('name="intraday-profitability-requests"', outcome_source)
        self.assertIn("await asyncio.gather(oversold_task, intraday_task)", outcome_source)
        self.assertIn("run_selected_candidate_tracker", worker_source)
        self.assertIn('name="intraday-selected-outcomes"', worker_source)

    def test_queue_has_single_active_request_guard(self) -> None:
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("ip_scan_requests_one_active_idx", source)
        self.assertIn("WHERE status IN ('queued','running')", source)
        self.assertIn("FOR UPDATE SKIP LOCKED", source)
        self.assertIn("execute_scan(scan_id", source)

    def test_browser_is_credential_free_and_contains_no_privileged_keys(self) -> None:
        browser = HTML.read_text(encoding="utf-8") + JS.read_text(encoding="utf-8") + PROMPT_JS.read_text(encoding="utf-8")
        for forbidden in (
            "SUPABASE_SERVICE_ROLE_KEY",
            "ALPACA_SECRET_KEY",
            "OPENAI_API_KEY",
            "EXPECTED_KEY_SHA256",
            "x-app-user",
            "x-app-key",
            "sessionStorage",
            "loginModal",
            "loginKey",
            "logoutBtn",
        ):
            self.assertNotIn(forbidden, browser)
        self.assertIn("No login required", browser)
        self.assertIn("credentials are required", browser.lower()) is False

    def test_public_edge_api_uses_origin_and_mutation_rate_controls(self) -> None:
        edge = EDGE.read_text(encoding="utf-8")
        for forbidden in ("EXPECTED_USER", "EXPECTED_KEY_SHA256", "constantTimeEqual", "x-app-user", "x-app-key"):
            self.assertNotIn(forbidden, edge)
        self.assertIn("ALLOWED_ORIGINS", edge)
        self.assertIn("originAllowed", edge)
        self.assertIn("ip_public_api_requests", edge)
        self.assertIn("enforceMutationRateLimit", edge)
        self.assertIn("GLOBAL_RUN_COOLDOWN_MS", edge)
        self.assertIn('credentials_required: false', edge)

    def test_rate_limit_schema_is_private_and_rls_enabled(self) -> None:
        schema = SCHEMA.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.ip_public_api_requests", schema)
        self.assertIn("ENABLE ROW LEVEL SECURITY", schema)
        self.assertIn("REVOKE ALL", schema)
        self.assertIn("service_role", schema)

    def test_chatgpt_handoff_is_populated_and_api_free(self) -> None:
        app_source = JS.read_text(encoding="utf-8")
        prompt_source = PROMPT_JS.read_text(encoding="utf-8")
        combined = app_source + prompt_source
        self.assertIn("https://chatgpt.com/", prompt_source)
        self.assertIn("searchParams.set('prompt'", prompt_source)
        self.assertIn("copyText", app_source)
        self.assertNotIn("api.openai.com", combined)
        self.assertNotIn("OPENAI_API_KEY", combined)


if __name__ == "__main__":
    unittest.main()
