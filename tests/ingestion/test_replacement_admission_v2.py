"""Real local PostgreSQL proof for safe supersession of the legacy dispatcher."""
import os
from pathlib import Path
import unittest
import test_rpc_postgres as legacy


@unittest.skipUnless(os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL"), "Explicit disposable PostgreSQL required")
class ReplacementAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = type("ReplacementGateFixture", (legacy.RPCPostgreSQLTests,), {})
        cls.fixture.setUpClass()
        cls.addClassCleanup(cls.fixture.cleanup)

    def test_authenticated_old_admission_is_fenced_without_erasing_evidence(self):
        f = self.fixture("runTest")
        f.setUp()
        f.submit()
        with f.admin() as conn:
            before = conn.execute(f"SELECT request_count,record_count FROM {f.schema}.jobs").fetchone()
            migration = (Path(__file__).resolve().parents[2] / "sql/astra_ingestion_supersede_gate_v2.sql").read_text()
            conn.execute(migration.replace("astra_ingestion_v1", f.schema))
            # Idempotent reconciliation does not rewrite the original scope.
            conn.execute(migration.replace("astra_ingestion_v1", f.schema))
            after = conn.execute(f"SELECT status,request_count,record_count FROM {f.schema}.jobs").fetchone()
            self.assertEqual(after["status"], "SUPERSEDED_BY_SCOPE_CHANGE")
            self.assertEqual((before["request_count"],before["record_count"]), (after["request_count"],after["record_count"]))
        self.assertIsNone(f.ok("claim_next", {"worker_id":"old-worker", "lease_seconds":90}, actor="worker"))
        result = f.rpc("submit_job", {})
        self.assertFalse(result["ok"])
        self.assertIn("SUPERSEDED_BY_SCOPE_CHANGE", result["error"]["message"])
        with self.assertRaises(f.psycopg.Error) as rejected:
            f.rpc("submit_job", {}, token="c" * 64)
        self.assertEqual(rejected.exception.sqlstate, "PT401")


if __name__ == "__main__":
    unittest.main()
