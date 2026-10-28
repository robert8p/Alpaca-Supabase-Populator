"""Production-dialect qualification against an explicitly supplied test server.

These tests never use DATABASE_URL or other application defaults. Only a
loopback PostgreSQL database named astra_ingestion_qualification is admitted.
Every test owns one newly generated schema and removes only that exact schema.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import uuid

from astra_ingestion.models import IngestionSpec
from astra_ingestion.source import FetchResult, parse_page, record_key
from astra_ingestion.store import LeaseLost, Store, canonical
from astra_ingestion.worker import Worker


TEST_URL = os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL", "")
SCHEMA_PATTERN = re.compile(r"astra_ingestion_test_[0-9a-f]{12}\Z")
BASE = {
    "name": "PostgreSQL qualification",
    "symbols": ["AAPL"],
    "start": "2025-09-02T13:30:00Z",
    "end": "2025-09-02T14:00:00Z",
    "timeframe": "5Min",
}


def source_body():
    return json.dumps({"bars": {"AAPL": [{
        "t": BASE["start"], "o": 100, "h": 101, "l": 99,
        "c": 100.5, "v": 100, "n": 4, "vw": 100.25,
    }]}, "next_page_token": None})


class FixtureSource:
    def __init__(self, *, allow_fetch=True):
        self.calls = 0
        self.allow_fetch = allow_fetch

    def fetch_page(self, *_args, **_kwargs):
        self.calls += 1
        if not self.allow_fetch:
            raise AssertionError("A committed source page must not be fetched again")
        return FetchResult(source_body(), "postgres-qualification-fixture")


@unittest.skipUnless(TEST_URL, "PostgreSQL qualification NOT_RUN: ASTRA_INGESTION_POSTGRES_TEST_URL is not set")
class PostgreSQLQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = urlsplit(TEST_URL)
        if (target.scheme not in {"postgres", "postgresql"}
                or target.hostname not in {"localhost", "127.0.0.1", "::1"}
                or unquote(target.path) != "/astra_ingestion_qualification"
                or target.query or target.fragment):
            raise RuntimeError(
                "PostgreSQL qualification requires an explicit loopback URL for "
                "astra_ingestion_qualification, without connection overrides"
            )
        # Missing psycopg is a failure when qualification was explicitly enabled.
        # It must never turn into a skipped or passing integration run.
        import psycopg
        cls.database_error = psycopg.errors.RaiseException

    def setUp(self):
        self.schema = "astra_ingestion_test_" + uuid.uuid4().hex[:12]
        self.store = Store(TEST_URL, test_mode=True, schema=self.schema)
        self.addCleanup(self.drop_owned_schema)
        self.store.migrate()

    def drop_owned_schema(self):
        # The identifier is generated locally and is never taken from the DSN,
        # fixture payload or environment. Never drop an application schema.
        if not SCHEMA_PATTERN.fullmatch(self.schema):
            raise AssertionError("Refusing to clean up a non-qualification schema")
        conn = self.store.connect()
        try:
            conn.execute("DROP SCHEMA IF EXISTS " + self.schema + " CASCADE")
            conn.commit()
        finally:
            conn.close()

    def submit(self, **changes):
        return self.store.submit_job(
            IngestionSpec.from_dict({**BASE, **changes}), "postgres-qualification-001"
        )

    def read(self, statement, args=()):
        with self.store.snapshot() as conn:
            return self.store.execute(conn, statement, args).fetchall()

    def write(self, statement, args=()):
        with self.store.transaction() as conn:
            self.store.execute(conn, statement, args)

    def page(self):
        fetched = FetchResult(source_body(), "postgres-qualification-fixture")
        parsed = parse_page(
            fetched.raw_text, symbol="AAPL", start=BASE["start"],
            end=BASE["end"], timeframe="5Min",
        )
        return fetched, parsed

    def fetch_once(self):
        job = self.submit()
        self.assertEqual(Worker(self.store, FixtureSource()).run_once()["state"], "page_committed")
        return job

    def test_idempotency_and_database_enforced_scope_immutability(self):
        first, repeated = self.submit(), self.submit()
        self.assertEqual(first["id"], repeated["id"])
        self.assertEqual(len(self.store.list_jobs()), 1)
        self.assertEqual(len(self.read("SELECT id FROM {s}partitions")), 1)
        with self.assertRaises(ValueError):
            self.submit(symbols=["MSFT"])
        with self.assertRaises(self.database_error):
            self.write("UPDATE {s}jobs SET spec='{}'")
        with self.assertRaises(self.database_error):
            self.write("UPDATE {s}partitions SET symbol='MSFT'")
        retained = self.store.get_job(first["id"])
        self.assertEqual(retained["scope_hash"], first["scope_hash"])
        self.assertEqual(retained["spec"]["symbols"], ["AAPL"])
        self.assertEqual(retained["partitions"][0]["symbol"], "AAPL")

    def test_page_effect_checkpoint_and_fresh_connection_readback(self):
        job = self.fetch_once()
        fresh = Store(TEST_URL, test_mode=True, schema=self.schema)
        with self.store.snapshot() as first, fresh.snapshot() as second:
            pid_one = first.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            pid_two = second.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            self.assertNotEqual(pid_one, pid_two)
            partition = fresh.execute(second, "SELECT * FROM {s}partitions").fetchone()
            receipt_count = fresh.execute(second, "SELECT count(*) AS n FROM {s}receipts").fetchone()["n"]
            record_count = fresh.execute(second, "SELECT count(*) AS n FROM {s}records").fetchone()["n"]
        self.assertEqual((partition["status"], partition["page_count"], receipt_count, record_count), ("loaded", 1, 1, 1))
        self.assertEqual(fresh.get_job(job["id"])["verification_status"], "pending")
        source = FixtureSource(allow_fetch=False)
        self.assertEqual(Worker(fresh, source).run_once()["state"], "verified")
        self.assertEqual(source.calls, 0)
        final = fresh.get_job(job["id"])
        self.assertEqual((final["status"], final["verification_status"]), ("completed", "passed"))
        self.assertEqual(final["coverage_certification"], "NOT_CERTIFIED")

    def test_replaced_owner_cannot_commit_or_record_a_late_failure(self):
        self.submit()
        old = self.store.claim_next("original")
        self.write("UPDATE {s}partitions SET lease_until=0")
        fresh = Store(TEST_URL, test_mode=True, schema=self.schema)
        replacement = fresh.claim_next("replacement")
        self.assertGreater(replacement["generation"], old["generation"])
        with self.assertRaises(LeaseLost):
            self.store.commit_page(old, *self.page())
        with self.assertRaises(LeaseLost):
            self.store.fail_claim(old, code="stale", message="Obsolete worker")
        self.assertEqual(len(self.read("SELECT * FROM {s}receipts")), 0)
        self.assertEqual(len(self.read("SELECT * FROM {s}records")), 0)
        fresh.reserve_request(replacement)
        fresh.commit_page(replacement, *self.page())
        self.assertEqual(len(self.read("SELECT * FROM {s}records")), 1)

    def test_pause_and_cancel_fence_inflight_claims(self):
        job = self.submit()
        original = self.store.claim_next("before-pause")
        self.store.control_job(job["id"], "pause")
        with self.assertRaises(LeaseLost):
            self.store.commit_page(original, *self.page())
        self.assertIsNone(self.store.claim_next("while-paused"))
        self.store.control_job(job["id"], "resume")
        resumed = self.store.claim_next("after-resume")
        self.assertEqual(resumed["spec"]["symbols"], ["AAPL"])
        self.store.control_job(job["id"], "cancel")
        with self.assertRaises(LeaseLost):
            self.store.commit_page(resumed, *self.page())
        self.assertEqual(self.store.get_job(job["id"])["status"], "cancelled")
        self.assertEqual(len(self.read("SELECT * FROM {s}receipts")), 0)

    def test_expired_during_write_rolls_back_effects_and_checkpoint(self):
        job = self.submit()
        claim = self.store.claim_next("expiring")
        self.store.reserve_request(claim)
        with self.store.snapshot() as conn:
            now = self.store.now(conn)
        with patch.object(self.store, "now", side_effect=[now, now + 301]):
            with self.assertRaises(LeaseLost):
                self.store.commit_page(claim, *self.page())
        self.assertEqual(len(self.read("SELECT * FROM {s}records")), 0)
        self.assertEqual(len(self.read("SELECT * FROM {s}receipts")), 0)
        final = self.store.get_job(job["id"])
        self.assertEqual(final["record_count"], 0)
        self.assertEqual(final["partitions"][0]["page_count"], 0)
        self.assertEqual(final["request_count"], 1)

    def test_changed_target_values_fail_despite_equal_record_counts(self):
        job = self.fetch_once()
        value = json.loads(self.read("SELECT payload FROM {s}records")[0]["payload"])
        value["close"] = "100.75"
        self.write("UPDATE {s}records SET payload=?", (canonical(value),))
        self.assertEqual(Worker(self.store, FixtureSource(allow_fetch=False)).run_once()["state"], "blocked")
        proof = json.loads(self.read("SELECT result FROM {s}verifications")[0]["result"])
        self.assertEqual(proof["changed_count"], 1)
        self.assertEqual(self.store.get_job(job["id"])["status"], "blocked")

    def test_primary_key_corruption_is_detected(self):
        job = self.fetch_once()
        self.write("UPDATE {s}records SET record_key='wrong-key'")
        Worker(self.store, FixtureSource(allow_fetch=False)).run_once()
        final = self.store.get_job(job["id"])
        self.assertEqual(final["status"], "blocked")
        self.assertIn("key does not match", final["partitions"][0]["error"])

    def test_missing_and_unexpected_target_keys_are_both_reported(self):
        job = self.fetch_once()
        value = json.loads(self.read("SELECT payload FROM {s}records")[0]["payload"])
        value["timestamp"] = "2025-09-02T13:35:00Z"
        self.write("UPDATE {s}records SET record_key=?,payload=?", (record_key(value), canonical(value)))
        Worker(self.store, FixtureSource(allow_fetch=False)).run_once()
        proof = json.loads(self.read("SELECT result FROM {s}verifications")[0]["result"])
        self.assertEqual((proof["missing_count"], proof["unexpected_count"]), (1, 1))
        self.assertEqual(self.store.get_job(job["id"])["status"], "blocked")

    def test_corrupt_source_receipt_prevents_verification(self):
        job = self.fetch_once()
        self.write("UPDATE {s}receipts SET body_sha256='corrupt-receipt'")
        Worker(self.store, FixtureSource(allow_fetch=False)).run_once()
        final = self.store.get_job(job["id"])
        self.assertEqual(final["status"], "blocked")
        self.assertIn("receipt hash mismatch", final["partitions"][0]["error"])

    def test_process_crash_after_commit_recovers_without_source_replay(self):
        job = self.submit()
        program = """
import os
from astra_ingestion.store import Store
from astra_ingestion.worker import Worker
from astra_ingestion.source import FetchResult
class Source:
    def fetch_page(self, *args):
        return FetchResult(os.environ['ASTRA_INGESTION_TEST_BODY'], 'postgres-crash-fixture')
store = Store(os.environ['ASTRA_INGESTION_POSTGRES_TEST_URL'], test_mode=True,
              schema=os.environ['ASTRA_INGESTION_TEST_SCHEMA'])
Worker(store, Source(), after_commit=lambda _: os._exit(23)).run_once()
"""
        env = dict(os.environ)
        env.update({
            "ASTRA_INGESTION_POSTGRES_TEST_URL": TEST_URL,
            "ASTRA_INGESTION_TEST_SCHEMA": self.schema,
            "ASTRA_INGESTION_TEST_BODY": source_body(),
        })
        root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = root
        result = subprocess.run([sys.executable, "-c", program], cwd=root, env=env,
                                capture_output=True, text=True, timeout=20)
        # The DSN never appears in the subprocess command line or test output.
        self.assertEqual(result.returncode, 23, result.stderr.replace(TEST_URL, "<test database>"))
        source = FixtureSource(allow_fetch=False)
        fresh = Store(TEST_URL, test_mode=True, schema=self.schema)
        self.assertEqual(Worker(fresh, source).run_once()["state"], "verified")
        self.assertEqual(source.calls, 0)
        self.assertEqual(len(self.read("SELECT * FROM {s}records")), 1)
        self.assertEqual(len(self.read("SELECT * FROM {s}receipts")), 1)
        self.assertEqual(fresh.get_job(job["id"])["status"], "completed")


if __name__ == "__main__":
    unittest.main()
