from __future__ import annotations

import ast
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "app" / "intraday_profitability_worker.py"
TRACKER = ROOT / "app" / "intraday_profitability_tracking.py"
OUTCOME = ROOT / "app" / "oversold_outcome_scheduler.py"
EDGE = ROOT / "supabase" / "functions" / "intraday-profitability-api" / "index.ts"
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

    def test_browser_never_contains_privileged_keys(self) -> None:
        browser = (
            HTML.read_text(encoding="utf-8")
            + JS.read_text(encoding="utf-8")
            + PROMPT_JS.read_text(encoding="utf-8")
        )
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", browser)
        self.assertNotIn("ALPACA_SECRET_KEY", browser)
        self.assertNotIn("OPENAI_API_KEY", browser)
        self.assertNotIn("EXPECTED_KEY_SHA256", browser)
        self.assertIn("sessionStorage", browser)

    def test_edge_function_contains_only_a_sha256_access_key_digest(self) -> None:
        edge = EDGE.read_text(encoding="utf-8")
        match = re.search(r'EXPECTED_KEY_SHA256\s*=\s*"([0-9a-f]{64})"', edge)
        self.assertIsNotNone(match)
        self.assertNotRegex(edge, r'ip-[A-Za-z0-9_-]{20,}')
        self.assertIn("constantTimeEqual", edge)
        self.assertIn(
            "verify_jwt",
            (
                ROOT
                / "supabase"
                / "functions"
                / "intraday-profitability-api"
                / "README.md"
            ).read_text(encoding="utf-8"),
        )

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
