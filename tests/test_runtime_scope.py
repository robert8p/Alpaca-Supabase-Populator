from __future__ import annotations

import os
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "runtime_scope.py"
SPEC = importlib.util.spec_from_file_location("runtime_scope_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime_scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_scope)

FULL = runtime_scope.FULL
INTRADAY_ONLY = runtime_scope.INTRADAY_ONLY
OVERSOLD_ONLY = runtime_scope.OVERSOLD_ONLY
RESEARCH_WORKER = runtime_scope.RESEARCH_WORKER
request_is_in_scope = runtime_scope.request_is_in_scope
root_redirect_for = runtime_scope.root_redirect_for
runtime_mode = runtime_scope.runtime_mode


class RuntimeScopeTests(unittest.TestCase):
    def test_full_mode_preserves_legacy_compatibility(self) -> None:
        self.assertTrue(request_is_in_scope(FULL, "/api/jobs"))
        self.assertIsNone(root_redirect_for(FULL))

    def test_oversold_mode_isolates_routes(self) -> None:
        cases = {
            "/health": True,
            "/static/oversold.js": True,
            "/oversold": True,
            "/oversold-v2": True,
            "/api/oversold/tracked": True,
            "/api/oversold-v2/latest": True,
            "/api/jobs": False,
            "/intraday-profitability": False,
        }
        for path, allowed in cases.items():
            with self.subTest(path=path):
                self.assertEqual(request_is_in_scope(OVERSOLD_ONLY, path), allowed)

    def test_intraday_mode_isolates_routes(self) -> None:
        cases = {
            "/health": True,
            "/static/intraday_profitability.js": True,
            "/intraday-profitability": True,
            "/api/intraday-profitability/latest": True,
            "/api/jobs": False,
            "/oversold": False,
        }
        for path, allowed in cases.items():
            with self.subTest(path=path):
                self.assertEqual(request_is_in_scope(INTRADAY_ONLY, path), allowed)

    def test_research_worker_exposes_only_health_and_static(self) -> None:
        self.assertTrue(request_is_in_scope(RESEARCH_WORKER, "/health"))
        self.assertFalse(request_is_in_scope(RESEARCH_WORKER, "/api/jobs"))

    def test_root_redirects_to_surviving_product(self) -> None:
        self.assertEqual(root_redirect_for(OVERSOLD_ONLY), "/oversold")
        self.assertEqual(root_redirect_for(INTRADAY_ONLY), "/intraday-profitability")

    def test_invalid_mode_fails_closed(self) -> None:
        with patch.dict(os.environ, {"RUNTIME_MODE": "typo"}):
            with self.assertRaisesRegex(RuntimeError, "Unsupported RUNTIME_MODE"):
                runtime_mode()


if __name__ == "__main__":
    unittest.main()
