"""Read-only replacement status over both transports and the existing UI."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from astra_ingestion import api
from astra_ingestion.rpc_store import PROJECT_URL, RpcPersistenceError, RpcStore
import test_web as web_fixture

ROOT = Path(__file__).resolve().parents[2]
HAS_ASGI = all(importlib.util.find_spec(name) is not None for name in ("fastapi", "httpx"))


def snapshot():
    return {
        "observed_at": "2026-10-30T08:00:00Z",
        "runs": [{"id": "fixed-run-1", "status": "ACTIVE", "members": 3000,
            "pages_committed": 24, "records_committed": 3492, "requests_reserved": 24,
            "last_progress_at": "2026-10-30T07:59:00Z",
            "scope": {"private": "private-fixture-secret"},
            "metadata": {"planning_complete": False, "planner_phase": "MEMBERS",
                "planner_next_selection_order": 7, "provider_secret": "private-fixture-secret"},
            "provider_dependencies": [{"provider": "Massive", "state": "BLOCKED_EXTERNAL",
                "dependency": "MASSIVE_WORKER_CREDENTIAL", "code": "MISSING_PROVIDER_CREDENTIAL",
                "evidence": {"private": "private-fixture-secret"}}],
            "tasks": [{"family": "N01", "kind": "alpaca_news", "provider": "Alpaca",
                "status": "PENDING", "tasks": 10, "records": 0}],
            "unsupported_pending_kinds": ["massive_short_volume"]}],
        "delivery": {"observed_at": "2026-10-30T08:00:00Z", "runs": [{"run_id": "fixed-run-1",
            "run_status": "ACTIVE", "planning_complete": False, "required_readbacks_remaining": 0,
            "families": [{"family": "N01", "planned_units": 10, "terminal_units": 2,
                "committed_records": 25, "work_completion": "IN_PROGRESS"}],
            "outstanding_actions": [{"error_message": "private-fixture-secret"}]}]}}


class StatusAdapterTests(unittest.TestCase):
    def store(self, value):
        store = RpcStore(PROJECT_URL, "sb_publishable_" + "p" * 32, "a" * 64, opener=Mock())
        store._call = Mock(return_value=value)
        return store

    def test_one_read_operation_projects_counts_without_private_evidence(self):
        original = snapshot()
        store = self.store(original)
        report = store.backfill_status()
        store._call.assert_called_once_with("backfill_status", {})
        self.assertNotIn("private-fixture-secret", json.dumps(report))
        self.assertNotIn("scope", report["runs"][0])
        self.assertEqual(report["runs"][0]["metadata"]["planner_next_selection_order"], 7)
        self.assertEqual(report["runs"][0]["provider_dependencies"][0]["state"], "BLOCKED_EXTERNAL")
        self.assertEqual(report["delivery"]["runs"][0]["families"][0]["committed_records"], 25)
        self.assertEqual(original["runs"][0]["metadata"]["provider_secret"], "private-fixture-secret")

    def test_missing_progress_and_coverage_stay_unknown(self):
        report = self.store({"runs": [{"id": "run-minimal", "status": "ACTIVE"}]}).backfill_status()
        self.assertNotIn("records_committed", report["runs"][0])
        self.assertNotIn("planning_complete", report["runs"][0]["metadata"])
        self.assertNotIn("applicable_data_coverage_established", report["runs"][0]["metadata"])
        self.assertNotIn("delivery", report)

    def test_nested_coverage_preserves_units_unknown_denominators_and_null_reasons(self):
        data = snapshot()
        family = data["delivery"]["runs"][0]["families"][0]
        family["nonminute_coverage"] = {
            "source_count_basis": "PHYSICAL_PROVIDER_RECORD_OCCURRENCES_NOT_GLOBAL_UNIQUE_EVENTS",
            "logical_output_records": 2, "expected_applicable_records": None,
            "coverage_fraction": None, "raw_body": "private-fixture-secret",
            "variants": [{"source_variant": "alpaca_news", "physical_records": 2,
                          "evidence": "private-fixture-secret"}],
            "fields": [{"field": "headline", "period": "TARGET", "observed_field_slots": 2,
                        "usable_values": 1, "missing_values": 1,
                        "raw_body": "private-fixture-secret",
                        "null_or_unusable_reasons": {"FIELD_NOT_RETURNED": 1,
                            "private-fixture-secret": 7, "INVALID_SECRET": "private-fixture-secret"}}]}
        report = self.store(data).backfill_status()
        coverage = report["delivery"]["runs"][0]["families"][0]["nonminute_coverage"]
        self.assertIsNone(coverage["expected_applicable_records"])
        self.assertIsNone(coverage["coverage_fraction"])
        self.assertEqual(coverage["logical_output_records"], 2)
        self.assertEqual(coverage["fields"][0]["null_or_unusable_reasons"], {"FIELD_NOT_RETURNED": 1})
        self.assertIn("NOT_GLOBAL_UNIQUE_EVENTS", coverage["source_count_basis"])
        self.assertNotIn("private-fixture-secret", json.dumps(report))

    def test_nested_coverage_has_explicit_size_bounds(self):
        for coverage in ({"fields": [{}] * 513}, {"variants": [{}] * 33},
                         {"fields": [{"null_or_unusable_reasons": []}]}):
            data = snapshot()
            data["delivery"]["runs"][0]["families"][0]["nonminute_coverage"] = coverage
            with self.assertRaises(RpcPersistenceError):
                self.store(data).backfill_status()

    def test_shared_record_counts_keep_distinct_units_and_strip_private_nested_evidence(self):
        data = snapshot()
        data["delivery"]["runs"][0]["families"][0]["nonminute_coverage"] = {
            "variant_count_basis": "PHYSICAL_PROVIDER_RECORD_OCCURRENCES",
            "shared_records": {"unique_articles": 2, "verified_source_occurrences": 3,
                "source_versions": 2, "article_security_links": 4,
                "unique_contract_references": 5, "unique_contract_session_bars": 120, "non_session_option_bar_records": 2,
                "expected_applicable_records": None, "coverage_fraction": None,
                "counts_additive_across_record_types": False, "cross_provider_matching": "NOT_ASSERTED",
                "date_axes": [{"record_type": "ACTION", "date_axis": "declaration_date",
                    "period": "TARGET", "records": 1, "raw_body": "private-fixture-secret"}],
                "shared_action_workflows": {"open_units": 7, "blocked_units": 1,
                    "evidence": "private-fixture-secret"},
                "contract_work": {"registered_contract_windows": 5, "expected_contract_population": None,
                    "historical_enumeration_completeness_certified": False, "evidence": "private-fixture-secret"},
                "private": "private-fixture-secret"},
            "fields": [{"record_type": "ARTICLE", "field": "headline", "observed_field_slots": 2}],
            "source_occurrence_fields": [{"field": "headline", "observed_field_slots": 3,
                "null_or_unusable_reasons": {"FIELD_NOT_RETURNED": 1, "private-fixture-secret": 1},
                "raw_body": "private-fixture-secret"}]}
        report = self.store(data).backfill_status()
        coverage = report["delivery"]["runs"][0]["families"][0]["nonminute_coverage"]
        shared = coverage["shared_records"]
        self.assertEqual((shared["unique_articles"], shared["verified_source_occurrences"]), (2, 3))
        self.assertEqual((shared["unique_contract_references"], shared["unique_contract_session_bars"]), (5, 120))
        self.assertEqual(shared["non_session_option_bar_records"], 2)
        self.assertIsNone(shared["expected_applicable_records"])
        self.assertFalse(shared["counts_additive_across_record_types"])
        self.assertEqual(shared["date_axes"][0],
            {"record_type": "ACTION", "date_axis": "declaration_date", "period": "TARGET", "records": 1})
        self.assertEqual(shared["shared_action_workflows"], {"open_units": 7, "blocked_units": 1})
        self.assertEqual(shared["contract_work"], {"registered_contract_windows": 5,
            "expected_contract_population": None, "historical_enumeration_completeness_certified": False})
        self.assertEqual(coverage["fields"][0]["record_type"], "ARTICLE")
        self.assertEqual(coverage["source_occurrence_fields"][0]["null_or_unusable_reasons"], {"FIELD_NOT_RETURNED": 1})
        self.assertNotIn("private-fixture-secret", json.dumps(report))

    def test_shared_record_projection_bounds_and_unknowns_are_preserved(self):
        for coverage in ({"source_occurrence_fields": [{}] * 513},
                         {"shared_records": {"date_axes": [{}] * 257}},
                         {"shared_records": {"shared_action_workflows": []}},
                         {"shared_records": {"contract_work": []}},
                         {"shared_records": []}):
            data = snapshot()
            data["delivery"]["runs"][0]["families"][0]["nonminute_coverage"] = coverage
            with self.assertRaises(RpcPersistenceError):
                self.store(data).backfill_status()
        data = snapshot()
        data["delivery"]["runs"][0]["families"][0]["nonminute_coverage"] = {
            "source_occurrence_fields": None,
            "shared_records": {"shared_action_workflows": None, "expected_applicable_records": None}}
        coverage = self.store(data).backfill_status()["delivery"]["runs"][0]["families"][0]["nonminute_coverage"]
        self.assertIsNone(coverage["source_occurrence_fields"])
        self.assertIsNone(coverage["shared_records"]["shared_action_workflows"])
        self.assertIsNone(coverage["shared_records"]["expected_applicable_records"])

    def test_invalid_status_is_a_sanitized_persistence_failure(self):
        cases = [None, [], {"runs": None}, {"runs": [None]}, {"runs": [{}] * 21},
                 {"runs": [], "delivery": {"runs": None}},
                 {"runs": [{"metadata": "private-fixture-secret"}]}]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(RpcPersistenceError) as caught:
                self.store(value).backfill_status()
            self.assertNotIn("private-fixture-secret", str(caught.exception))


class WebStatusTests(unittest.TestCase):
    request = web_fixture.WebContractTests.request

    def setUp(self):
        self.settings = SimpleNamespace(username="operator", password="a-test-password-that-is-long-enough",
            test_mode=True, service_version="test-version")
        self.store = Mock()
        self.store.backfill_status.return_value = {"runs": [], "observed_at": "2026-10-30T08:00:00Z"}

    def test_exact_route_requires_auth_before_any_status_read(self):
        status, headers, body = self.request("/api/backfill/status", authenticated=False)
        self.assertEqual(status, 401)
        self.assertIn("Basic", headers["WWW-Authenticate"])
        self.store.backfill_status.assert_not_called()
        status, headers, body = self.request("/api/backfill/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), self.store.backfill_status.return_value)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.store.backfill_status.assert_called_once_with()
        self.assertEqual(self.request("/api/backfill/status", "POST", {})[0], 404)
        self.assertEqual(len(self.store.mock_calls), 1)

    def test_storage_failure_does_not_return_credentials(self):
        self.store.backfill_status.side_effect = RuntimeError("postgresql://secret:private-fixture-secret@db")
        status, _, body = self.request("/api/backfill/status")
        self.assertEqual(status, 503)
        self.assertNotIn(b"private-fixture-secret", body)
        self.assertNotIn(b"postgresql", body)


@unittest.skipUnless(HAS_ASGI, "Pinned ASGI test dependencies required")
class ASGIStatusTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        self.store = Mock()
        self.store.backfill_status.return_value = {"runs": [], "observed_at": "2026-10-30T08:00:00Z"}
        settings = SimpleNamespace(username="operator", password="a-test-password-that-is-long-enough",
            test_mode=True, service_version="test-version")
        self.client = TestClient(api.create_app(settings, self.store))
        self.addCleanup(self.client.close)
        import base64
        self.headers = {"Authorization": "Basic " + base64.b64encode(
            (settings.username + ":" + settings.password).encode()).decode()}

    def test_production_transport_status_auth_read_only_and_headers(self):
        self.assertEqual(self.client.get("/api/backfill/status").status_code, 401)
        self.store.backfill_status.assert_not_called()
        response = self.client.get("/api/backfill/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.store.backfill_status.return_value)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertNotIn("access-control-allow-origin", response.headers)
        self.store.backfill_status.assert_called_once_with()
        denied = self.client.post("/api/backfill/status", json={}, headers={**self.headers, "X-Ingestion-Control": "1"})
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(len(self.store.mock_calls), 1)

    def test_production_status_failure_is_sanitized(self):
        self.store.backfill_status.side_effect = RuntimeError("private-fixture-secret")
        response = self.client.get("/api/backfill/status", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-fixture-secret", response.text)


class BrowserStatusContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node required for local DOM contract qualification")
    def test_actual_ui_handles_unknowns_matching_runs_staleness_and_independent_reads(self):
        result = subprocess.run(["node", str(Path(__file__).with_name("backfill_status_ui_contract.js"))],
            cwd=ROOT, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("replacement UI contract passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
