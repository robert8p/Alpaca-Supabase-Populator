"""Independent, local-only actual PostgreSQL snapshot-predicate regression.

Uses the established retained-S02 fixture only to build a unique disposable
schema. The three reviewed live helper definitions are checked byte-for-byte
after identifier normalization. No HTTP, provider, deployment, or production
connector is used. Synthetic rows are state-transition fixtures, not acquired
provider data. This does not qualify full planner SEAL, migration authority, or
production-scale performance; those have separate producer qualifications.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import unittest

ADMITTED_LOCAL_URL = "postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification"
SOURCE_CAPTURE_SHA = "bbf5e4771bc2f3d541951f3de4b6f4a5dd990bf7eb4cf6b4ca96b2d2e2e6afc7"
EXPECTED_DELTA_SHA = "67eed4256843c7f84196c6ecee41cc13212c8e93e8a9409e5d321155725007f0"
COHORT_SHA = "2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    fixture_root = args.fixture_root.resolve()
    artifacts = args.artifact_root.resolve()
    if os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL") != ADMITTED_LOCAL_URL:
        raise RuntimeError("Exact explicitly admitted local qualification route required")
    opened: set[Path] = set()

    def audit(event, values):
        if event == "open" and values and isinstance(values[0], str):
            path = Path(values[0]).resolve()
            if (path.is_relative_to(fixture_root) or path.is_relative_to(artifacts)) and path.suffix in {".py", ".sql", ".json"}:
                opened.add(path)

    sys.addaudithook(audit)
    sys.path[:0] = [str(fixture_root), str(fixture_root / "tests/ingestion")]
    from test_backfill_retained_s02_v2 import RetainedS02Tests

    def pinned_json(name: str, pin: str):
        raw = (artifacts / name).read_bytes()
        if sha256(raw).hexdigest() != pin:
            raise AssertionError("Independent source artifact changed: " + name)
        return json.loads(raw)

    baseline = pinned_json("retained_seal_three_function_definitions_v78.json", SOURCE_CAPTURE_SHA)
    delta = pinned_json("independent_expected_predicate_delta_v78.json", EXPECTED_DELTA_SHA)
    old_rows = {row["signature"]: row for row in baseline["functions"]}
    new_rows = {row["signature"]: row for row in delta["functions"]}
    for signature, row in old_rows.items():
        assert sha256(row["definition"].encode()).hexdigest() == row["source_sha256"], signature
    for signature, row in new_rows.items():
        assert sha256(row["candidate_definition"].encode()).hexdigest() == row["candidate_source_sha256"], signature
        assert row["candidate_definition"].replace(delta["new_predicate"], delta["old_predicate"]) == old_rows[signature]["definition"]
    evidence = {"cases": {}, "layers": {"postgresql": "ACTUAL_DISPOSABLE_LOCAL", "provider_data": "SYNTHETIC_STATE_FIXTURES", "http": "NOT_USED", "production": "NOT_USED"}}

    class FocusedSnapshotTests(RetainedS02Tests):
        @classmethod
        def setUpClass(cls):
            super().setUpClass()
            f = cls.fixture("runTest")
            with f.admin() as conn:
                identity = conn.execute("SELECT current_database() db,host(inet_server_addr()) address,version() version").fetchone()
                evidence["database"] = dict(identity)
                assert identity["db"] == "astra_ingestion_qualification"
                assert identity["address"] == "127.0.0.1"
                evidence["fixture_schema"] = f.schema
                pins = {}
                for signature, row in old_rows.items():
                    actual = conn.execute("SELECT pg_get_functiondef(%s::regprocedure) definition", (signature.replace("astra_ingestion_v1", f.schema),)).fetchone()["definition"]
                    normalized = actual.replace(f.schema, "astra_ingestion_v1")
                    assert normalized == row["definition"], signature
                    pins[signature] = sha256(normalized.encode()).hexdigest()
                evidence["normalized_fixture_baseline_sources"] = pins

        def setUp(self):
            super().setUp()
            with self.f.admin() as conn:
                for row in old_rows.values():
                    conn.execute(row["definition"].replace("astra_ingestion_v1", self.f.schema))
            # Genuine immutable static snapshot, retained through every case.
            self.insert_rows([("0-preexisting", "alpaca_reference", "REF01", "Alpaca", self.scope())])

        @staticmethod
        def scope(**extra):
            return {"symbols": ["AAPL"], "member_ids": ["member-1"], "target_start": "2025-09-02", "target_end": "2025-09-02", "market_timezone": "America/New_York", **extra}

        def insert_rows(self, rows, *, pre_snapshot=False):
            with self.f.admin() as conn:
                # Only local fixture setup: emulate tasks existing before the
                # snapshot trigger was installed; leave all scope/identity
                # guards active and restore this one trigger before commit.
                if pre_snapshot:
                    conn.execute(f"ALTER TABLE {self.f.schema}.backfill_tasks_v2 DISABLE TRIGGER backfill_static_plan_snapshot_v2")
                for suffix, kind, family, provider, scope in rows:
                    conn.execute(f"""INSERT INTO {self.f.schema}.backfill_tasks_v2
                        (id,run_id,family,provider,kind,scope,attempts,requests_reserved,records_committed,page_no)
                        VALUES(%s,%s,%s,%s,%s,%s,3,2,7,1)""", (self.run + ":" + suffix, self.run, family, provider, kind, json.dumps(scope)))
                if pre_snapshot:
                    conn.execute(f"ALTER TABLE {self.f.schema}.backfill_tasks_v2 ENABLE TRIGGER backfill_static_plan_snapshot_v2")

        def immutable_state(self):
            with self.f.admin() as conn:
                return {table: conn.execute(f"SELECT to_jsonb(t) row FROM {self.f.schema}.{table} t WHERE " + ("id=%s" if table == "backfill_runs_v2" else "run_id=%s") + " ORDER BY to_jsonb(t)::text", (self.run,)).fetchall()
                        for table in ("backfill_runs_v2", "backfill_tasks_v2", "backfill_members_v2", "backfill_pages_v2")}

        def plan_state(self):
            with self.f.admin() as conn:
                return {table: conn.execute(f"SELECT to_jsonb(t) row FROM {self.f.schema}.{table} t WHERE run_id=%s ORDER BY to_jsonb(t)::text", (self.run,)).fetchall()
                        for table in ("backfill_plan_units_v2", "backfill_plan_coverage_v2")}

        def snapshot(self, limit=500):
            with self.f.admin() as conn:
                return conn.execute(f"SELECT {self.f.schema}.backfill_plan_snapshot_v2(%s,%s) result", (self.run, limit)).fetchone()["result"]

        def install_candidate(self):
            with self.f.admin() as conn:
                before = conn.execute("SELECT oid,to_jsonb(p)-'prosrc' metadata FROM pg_proc p WHERE pronamespace=%s::regnamespace ORDER BY oid", (self.f.schema,)).fetchall()
                for signature, row in new_rows.items():
                    conn.execute(row["candidate_definition"].replace("astra_ingestion_v1", self.f.schema))
                    actual = conn.execute("SELECT pg_get_functiondef(%s::regprocedure) definition", (signature.replace("astra_ingestion_v1", self.f.schema),)).fetchone()["definition"]
                    self.assertEqual(actual.replace(self.f.schema, "astra_ingestion_v1"), row["candidate_definition"])
                after = conn.execute("SELECT oid,to_jsonb(p)-'prosrc' metadata FROM pg_proc p WHERE pronamespace=%s::regnamespace ORDER BY oid", (self.f.schema,)).fetchall()
                self.assertEqual(before, after)
                unchanged = next(row for signature, row in old_rows.items() if "backfill_snapshot_task_v2(" in signature)
                actual = conn.execute("SELECT pg_get_functiondef(%s::regprocedure) definition", (unchanged["signature"].replace("astra_ingestion_v1", self.f.schema),)).fetchone()["definition"]
                self.assertEqual(actual.replace(self.f.schema, "astra_ingestion_v1"), unchanged["definition"])

        def dynamic_case(self, name, kind, family="REF01", provider="Alpaca", **scope_extra):
            self.insert_rows([("a-dynamic", kind, family, provider, self.scope(**scope_extra))])
            business, plan = self.immutable_state(), self.plan_state()
            old = self.snapshot()
            self.assertEqual(old, {"snapshotted": 0, "more": True})
            self.assertEqual(self.immutable_state(), business)
            self.assertEqual(self.plan_state(), plan)
            self.install_candidate()
            repaired = self.snapshot()
            self.assertEqual(repaired, {"snapshotted": 0, "more": False})
            self.assertEqual(self.immutable_state(), business)
            self.assertEqual(self.plan_state(), plan)
            evidence["cases"][name] = {"old": old, "repaired": repaired, "business_rows_and_nonzero_task_counters_unchanged": True, "preexisting_plan_units_and_coverage_unchanged": True, "helper_metadata_unchanged": True}

        def test_identity_refresh(self):
            self.dynamic_case("identity_refresh_of", "alpaca_reference", identity_refresh_of="synthetic-prior-task")

        def test_retained_identity(self):
            self.dynamic_case("retained_identity", "retained_identity", provider="REUSE", shared_cohort_reference=True, cohort_sha256=COHORT_SHA)

        def test_retained_massive_archive(self):
            self.dynamic_case("retained_massive_archive", "retained_massive_archive", family="S02", provider="REUSE", preserve_provider_acquisition=True)

        def test_more_than_500_dynamic_rows_cannot_starve_501_real_static_tasks(self):
            self.insert_rows([(f"a-dynamic-{i:04d}", "retained_identity", "REF01", "REUSE", self.scope(shared_cohort_reference=True, cohort_sha256=COHORT_SHA)) for i in range(501)])
            self.insert_rows([(f"z-static-{i:04d}", "alpaca_reference", "REF01", "Alpaca", self.scope(plan_static=False)) for i in range(501)], pre_snapshot=True)
            business, plan = self.immutable_state(), self.plan_state()
            old = self.snapshot(1000)
            self.assertEqual(old, {"snapshotted": 0, "more": True})
            self.assertEqual(self.plan_state(), plan)
            self.install_candidate()
            first, second, third = self.snapshot(1000), self.snapshot(1000), self.snapshot(1000)
            self.assertEqual(first, {"snapshotted": 500, "more": True})
            self.assertEqual(second, {"snapshotted": 1, "more": False})
            self.assertEqual(third, {"snapshotted": 0, "more": False})
            self.assertEqual(self.immutable_state(), business)
            final_plan = self.plan_state()
            self.assertEqual(len(final_plan["backfill_plan_units_v2"]), 502)
            old_unit = plan["backfill_plan_units_v2"][0]
            self.assertIn(old_unit, final_plan["backfill_plan_units_v2"])
            self.assertEqual(final_plan["backfill_plan_coverage_v2"][0]["row"]["task_count"], 502)
            evidence["cases"]["dynamic_starvation_and_500_cap"] = {"ignored_dynamic_rows": 501, "unsnapshotted_real_static_rows": 501, "old": old, "repaired_calls": [first, second, third], "business_rows_unchanged": True, "retained_preexisting_plan_unit": True, "only_real_static_coverage_added": True}

        def test_plan_static_false_remains_required_by_snapshot_and_seal(self):
            self.insert_rows([("z-ordinary-static-false", "alpaca_reference", "REF01", "Alpaca", self.scope(plan_static=False))], pre_snapshot=True)
            before = self.immutable_state()
            self.install_candidate()
            calendar = json.loads((fixture_root / "evidence/replacement-calendar-v1.json").read_text())
            workflow = {"version": "synthetic-independent-missing-static-v78", "target_start": "2025-09-01", "target_end": "2026-07-31", "market_timezone": "America/New_York", "representative_policy": "synthetic one representative per frozen fixture member", "session_dates": [row["date"] for row in calendar["sessions"] if "2025-09-01" <= row["date"] <= "2026-07-31"]}
            with self.assertRaises(self.f.psycopg.Error) as raised:
                with self.f.admin() as conn:
                    conn.execute(f"SELECT {self.f.schema}.backfill_seal_plan_v2(%s,0,%s,%s)", (self.run, "0" * 64, json.dumps(workflow)))
            self.assertEqual(raised.exception.sqlstate, "AI005")
            self.assertIn("Static task snapshots are incomplete", str(raised.exception))
            result = self.snapshot()
            self.assertEqual(result, {"snapshotted": 1, "more": False})
            self.assertEqual(self.immutable_state(), before)
            with self.f.admin() as conn:
                task = conn.execute(f"SELECT task_id FROM {self.f.schema}.backfill_plan_units_v2 WHERE task_id=%s", (self.run + ":z-ordinary-static-false",)).fetchone()
                self.assertIsNotNone(task)
                self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_plan_manifests_v2 WHERE run_id=%s", (self.run,)).fetchone()["n"], 0)
            evidence["cases"]["ordinary_plan_static_false"] = {"seal_refused_missing_static_sqlstate": raised.exception.sqlstate, "snapshotted": result, "business_rows_unchanged": True, "no_manifest_or_completion_written": True}

        def test_preexisting_option_and_reuse_exclusions_stay_excluded(self):
            self.insert_rows([("a-option-child", "alpaca_option_bars", "CTX02", "Alpaca", self.scope(enumeration_parent="fixture-enumeration")), ("b-reuse-child", "alpaca_reference", "REF01", "Alpaca", self.scope(reuse_parent="fixture-reuse"))])
            business, plan = self.immutable_state(), self.plan_state()
            old = self.snapshot()
            self.assertEqual(old, {"snapshotted": 0, "more": False})
            self.install_candidate()
            repaired = self.snapshot()
            self.assertEqual(repaired, old)
            self.assertEqual(self.immutable_state(), business)
            self.assertEqual(self.plan_state(), plan)
            evidence["cases"]["existing_dynamic_exclusions"] = {"old": old, "repaired": repaired, "business_and_plan_state_unchanged": True}

    selected = ["test_identity_refresh", "test_retained_identity", "test_retained_massive_archive", "test_more_than_500_dynamic_rows_cannot_starve_501_real_static_tasks", "test_plan_static_false_remains_required_by_snapshot_and_seal", "test_preexisting_option_and_reuse_exclusions_stay_excluded"]
    suite = unittest.TestSuite(FocusedSnapshotTests(name) for name in selected)
    log, out, err = io.StringIO(), io.StringIO(), io.StringIO()
    started = perf_counter()
    with redirect_stdout(out), redirect_stderr(err):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if isinstance(filename, str):
            path = Path(filename).resolve()
            if path.is_relative_to(fixture_root) and path.suffix == ".py":
                opened.add(path)
    dependencies = [{"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes()).hexdigest()} for path in sorted(opened) if path.exists()]
    receipt = {"schema": "astra.independent-planner-snapshot-postgres-qualification/1", "passed": result.wasSuccessful() and not result.skipped, "tests": result.testsRun, "errors": len(result.errors), "failures": len(result.failures), "skips": len(result.skipped), "seconds": round(perf_counter() - started, 3), "test_log": log.getvalue(), "stdout": out.getvalue(), "stderr": err.getvalue(), "source_capture_sha256": SOURCE_CAPTURE_SHA, "independent_candidate_delta_sha256": EXPECTED_DELTA_SHA, "candidate_function_sha256": {k: v["candidate_source_sha256"] for k, v in new_rows.items()}, "evidence": evidence, "opened_or_imported_dependencies": dependencies, "production_calls": 0, "external_provider_calls": 0, "migration_authority_tested": False, "full_planner_integration_tested": False, "production_scale_performance_tested": False, "schema_cleanup_requested_by_fixture": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({key: receipt[key] for key in ("passed", "tests", "errors", "failures", "skips", "seconds")}))
    if not receipt["passed"]:
        print(log.getvalue())
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
