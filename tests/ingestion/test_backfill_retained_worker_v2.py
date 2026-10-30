"""Actual worker/RPC integration for retained S02 and interrupted acknowledgments."""
import os
import unittest

from astra_ingestion.backfill_worker_v2 import BackfillWorker
import test_backfill_retained_s02_v2 as source


class NoExternalProvider:
    def supported_kinds(self):
        return ()

    def require_credentials(self, _claim):
        raise AssertionError("Retained source work must not acquire provider credentials")

    def fetch(self, _claim):
        raise AssertionError("Retained source work must not dispatch a provider request")


@unittest.skipUnless(os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL"), "Explicit disposable PostgreSQL required")
class RetainedWorkerTests(unittest.TestCase):
    setUpClass = classmethod(source.RetainedS02Tests.setUpClass.__func__)
    rewrite = classmethod(source.RetainedS02Tests.rewrite.__func__)
    setUp = source.RetainedS02Tests.setUp
    task = source.RetainedS02Tests.task
    call = source.RetainedS02Tests.call
    claim = source.RetainedS02Tests.claim
    fence = staticmethod(source.RetainedS02Tests.fence)
    record = staticmethod(source.RetainedS02Tests.record)
    source_page = source.RetainedS02Tests.source_page
    seed = source.RetainedS02Tests.seed
    report = source.RetainedS02Tests.report

    def worker(self, after_commit=None):
        fixture = self

        class Store:
            def _call(self, operation, payload):
                return fixture.call(operation, payload)

        return BackfillWorker(Store(), NoExternalProvider(), retained_massive_enabled=True,
                              worker_id="retained-worker-integration", after_commit=after_commit,
                              source_revision="local-qualified-retained-worker")

    def test_worker_commits_verifies_and_automatically_consumes_monitor_successor(self):
        self.source_page(1, [self.record()], next_page=2)
        self.source_page(2, [self.record(day="2026-07-31")])
        self.assertEqual(self.seed(1), 1)
        worker = self.worker()
        first = worker.run_once()
        self.assertEqual(first["record_count"], 1)
        self.assertEqual(first["referenced_candidate_records"], 1)
        self.call("backfill_maintain", {"limit": 2})
        second = worker.run_once()
        self.assertNotEqual(first["task_id"], second["task_id"])
        self.assertEqual(second["referenced_candidate_records"], 1)
        self.assertEqual(worker.run_once()["state"], "idle")
        with self.f.admin() as conn:
            counts = conn.execute(f"SELECT requests_reserved,pages_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s", (self.run,)).fetchone()
            self.assertEqual(dict(counts), {"requests_reserved": 0, "pages_committed": 2})
            proofs = conn.execute(f"SELECT retained_s02_verification FROM {self.f.schema}.backfill_readbacks_v2 WHERE run_id=%s", (self.run,)).fetchall()
            self.assertEqual(len(proofs), 2)
            self.assertTrue(all(p["retained_s02_verification"]["passed"] for p in proofs))
        self.assertEqual(self.report()["nonminute_coverage"]["logical_output_records"], 2)

    def test_monitor_reconciles_post_commit_interruption_without_reacquisition(self):
        self.source_page(1, [self.record()])
        self.seed(1)

        def interrupted(_claim):
            raise RuntimeError("synthetic interruption after durable commit")

        with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
            self.worker(interrupted).run_once()
        with self.f.admin() as conn:
            saved = conn.execute(f"SELECT task_id,body_sha256 FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s", (self.run,)).fetchone()
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_readbacks_v2 WHERE run_id=%s", (self.run,)).fetchone()["n"], 0)
        self.call("backfill_maintain", {"limit": 2})
        self.assertEqual(self.worker().run_once()["state"], "idle")
        with self.f.admin() as conn:
            current = conn.execute(f"SELECT task_id,body_sha256 FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s", (self.run,)).fetchall()
            self.assertEqual([dict(x) for x in current], [dict(saved)])
            proof = conn.execute(f"SELECT retained_s02_verification FROM {self.f.schema}.backfill_readbacks_v2 WHERE run_id=%s", (self.run,)).fetchone()
            self.assertTrue(proof["retained_s02_verification"]["passed"])


if __name__ == "__main__":
    unittest.main()
