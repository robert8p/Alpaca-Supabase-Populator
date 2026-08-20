from __future__ import annotations

import ast
import hashlib
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "app" / "intraday_profitability_worker.py"
OUTCOME = ROOT / "app" / "oversold_outcome_scheduler.py"
EDGE = ROOT / "supabase" / "functions" / "intraday-profitability-api" / "index.ts"
HTML = ROOT / "static_intraday" / "index.html"
JS = ROOT / "static_intraday" / "app.js"


class SplitDeploymentContractTests(unittest.TestCase):
    def test_python_modules_parse(self) -> None:
        ast.parse(WORKER.read_text(encoding="utf-8"))
        ast.parse(OUTCOME.read_text(encoding="utf-8"))

    def test_existing_worker_task_hosts_queue_scheduler(self) -> None:
        source = OUTCOME.read_text(encoding="utf-8")
        self.assertIn("run_intraday_profitability_request_scheduler", source)
        self.assertIn('name="intraday-profitability-requests"', source)
        self.assertIn("await asyncio.gather(oversold_task, intraday_task)", source)

    def test_queue_has_single_active_request_guard(self) -> None:
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("ip_scan_requests_one_active_idx", source)
        self.assertIn("WHERE status IN ('queued','running')", source)
        self.assertIn("FOR UPDATE SKIP LOCKED", source)
        self.assertIn("execute_scan(scan_id", source)

    def test_browser_never_contains_privileged_keys(self) -> None:
        browser = HTML.read_text(encoding="utf-8") + JS.read_text(encoding="utf-8")
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", browser)
        self.assertNotIn("ALPACA_SECRET_KEY", browser)
        self.assertNotIn("OPENAI_API_KEY", browser)
        self.assertIn("sessionStorage", browser)

    def test_edge_function_contains_only_access_key_hash(self) -> None:
        edge = EDGE.read_text(encoding="utf-8")
        plaintext = "ip-x3a2KxINS6su04d5nVzi81p9"
        digest = hashlib.sha256(plaintext.encode()).hexdigest()
        self.assertNotIn(plaintext, edge)
        self.assertIn(digest, edge)
        self.assertIn("constantTimeEqual", edge)
        self.assertIn('verify_jwt', (ROOT / "supabase" / "functions" / "intraday-profitability-api" / "README.md").read_text(encoding="utf-8"))

    def test_chatgpt_handoff_is_api_free(self) -> None:
        source = JS.read_text(encoding="utf-8")
        self.assertIn("https://chatgpt.com/", source)
        self.assertIn("copyText", source)
        self.assertNotIn("api.openai.com", source)
        self.assertNotIn("openai", source.lower().replace("no openai api", ""))


if __name__ == "__main__":
    unittest.main()
