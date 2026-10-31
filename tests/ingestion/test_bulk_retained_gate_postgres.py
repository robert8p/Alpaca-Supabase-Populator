"""Disposable PostgreSQL tests for staged 24-family review/retained-only claim.

No production installation. Synthetic administrative fixture DOES NOT prove an
independent hosted review, safe external authenticated transport or RLS actor.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote
import hashlib
import os
import unittest
import uuid

URL = os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL", "")
ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "sql" / "astra_ingestion_bulk_ledger_v1.sql"
GATE = ROOT / "sql" / "astra_ingestion_bulk_retained_gate_v1.sql"
CAPTURE = "top3000-augsep2026-retained-scope-v1"
RECEIPT = "ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496"
MANIFEST = "a" * 64
REPORT = "e" * 64
SOURCE = "b" * 64
FAMILIES = (
    "REF01","P01","P02","D01","N01","N03","D02","D03","D04",
    "F04","F05","S02","F06","CTX06","CTX14","REF03","D05",
    "F01","F02","F03","N02","S01","CTX02","CTX07",
)


@unittest.skipUnless(URL, "isolated PostgreSQL qualification URL required")
class RetainedGatePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        u = urlsplit(URL)
        if (u.scheme not in {"postgres", "postgresql"}
                or u.hostname not in {"localhost", "127.0.0.1", "::1"}
                or unquote(u.path) != "/astra_ingestion_qualification"
                or u.query or u.fragment):
            raise RuntimeError("qualification requires disposable loopback PostgreSQL")
        import psycopg
        cls.pg = psycopg

    def setUp(self):
        self.schema = "astra_bulk_review_test_" + uuid.uuid4().hex[:10]
        self.conn = self.pg.connect(URL, autocommit=True)
        self.addCleanup(self.cleanup)
        self.conn.execute(f"CREATE SCHEMA {self.schema}")
        self.conn.execute(f"""
            CREATE TABLE {self.schema}.bulk_scope_capture_v1(
                capture_key text PRIMARY KEY,evidence_sha256 text NOT NULL,
                evidence_rows int NOT NULL,state text NOT NULL,
                provider_requests int NOT NULL,incremental_cost_microusd bigint NOT NULL);
            INSERT INTO {self.schema}.bulk_scope_capture_v1 VALUES
                ('{CAPTURE}','{RECEIPT}',4136,'CAPTURED_NOT_ADMITTED',0,0);
            CREATE TABLE {self.schema}.bulk_scope_evidence_v1(
                capture_key text NOT NULL,kind text NOT NULL,
                evidence_key text NOT NULL,source_sha256 text NOT NULL,
                PRIMARY KEY(capture_key,kind,evidence_key));
        """)
        for family in FAMILIES:
            self.conn.execute(
                f"INSERT INTO {self.schema}.bulk_scope_evidence_v1 VALUES (%s,%s,%s,%s)",
                (CAPTURE, "contract", family, self.contract_sha(family)))
        self.conn.execute(LEDGER.read_text().replace("astra_ingestion_v1", self.schema))
        self.conn.execute(GATE.read_text().replace("astra_ingestion_v1", self.schema))

    def cleanup(self):
        if hasattr(self, "conn"):
            try:
                self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
            finally:
                self.conn.close()

    @staticmethod
    def contract_sha(family):
        return hashlib.sha256(family.encode("utf-8")).hexdigest()

    def sql(self, fn, *args):
        placeholders = ",".join(["%s"] * len(args))
        return self.conn.execute(f"SELECT {self.schema}.{fn}({placeholders})", args).fetchone()[0]

    def seed_manifest(self):
        return self.sql("bulk_manifest_create_v1", MANIFEST, CAPTURE, RECEIPT, 3, 100)

    def reserve(self, unit, family="REF01", predecessors=None, requests=0):
        return self.sql(
            "bulk_reserve_v1", MANIFEST, family, unit,
            "provider_acquisition" if requests else "retained_source_reuse",
            SOURCE, datetime.now(timezone.utc) + timedelta(minutes=20),
            requests, 10, predecessors or [])

    def add_reviews(self, families=FAMILIES, report=REPORT):
        for family in families:
            self.conn.execute(f"""
                INSERT INTO {self.schema}.bulk_family_review_v1
                (manifest_sha256,family,contract_sha256,expected_manifest_sha256,
                 source_receipt_sha256,provenance_sha256,identity_sha256,pit_sha256,
                 expected_units,observed_units,independent_report_sha256)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,10,10,%s)
            """,(MANIFEST,family,self.contract_sha(family),"d"*64,"c"*64,
                 "f"*64,"1"*64,"2"*64,report))

    def test_unreviewed_manifest_does_not_dispatch_or_consume_claims(self):
        self.seed_manifest()
        item = self.reserve("synthetic:one")
        self.assertIsNone(self.sql("bulk_claim_retained_v1", MANIFEST, "test-worker", 45))
        state = self.conn.execute(
            f"SELECT status,attempts FROM {self.schema}.bulk_work_v1 WHERE work_key=%s",
            (item["work_key"],)).fetchone()
        self.assertEqual(state, ("pending", 0))

    def test_all_24_source_contract_bound_family_reviews_required(self):
        self.seed_manifest()
        self.add_reviews(FAMILIES[:-1])
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_finalize_retained_review_v1", MANIFEST, REPORT)
        self.add_reviews(FAMILIES[-1:])
        admitted = self.sql("bulk_finalize_retained_review_v1", MANIFEST, REPORT)
        self.assertEqual(admitted["family_count"], 24)
        self.assertEqual(admitted["status"], "INDEPENDENTLY_REVIEWED_RETAINED_ONLY")
        self.assertEqual(self.sql("bulk_finalize_retained_review_v1", MANIFEST, REPORT), admitted)
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_finalize_retained_review_v1", MANIFEST, "f"*64)

    def test_retained_mode_only_dependency_successor_requires_reviewed_manifest(self):
        self.seed_manifest()
        provider = self.reserve("synthetic:provider", requests=1)
        first = self.reserve("synthetic:retained")
        second = self.reserve("synthetic:successor", family="P01",
                              predecessors=[first["work_key"]])
        self.add_reviews()
        self.sql("bulk_finalize_retained_review_v1", MANIFEST, REPORT)
        claim = self.sql("bulk_claim_retained_v1", MANIFEST, "test-worker", 45)
        self.assertEqual(claim["work_key"], first["work_key"])
        self.assertEqual(claim["max_requests"], 0)
        self.assertIsNone(self.sql("bulk_claim_retained_v1", MANIFEST, "other-worker", 45))
        self.sql("bulk_commit_page_v1",first["work_key"],"test-worker",
                 claim["claim_fence"],0,"a"*64,"b"*64,5,0)
        # Administrative synthetic verifier only. A real distinct reviewer
        # account, source comparison and restricted rights are STILL required.
        self.sql("bulk_verify_v1",first["work_key"],"test-worker",
                 claim["claim_fence"],"c"*64)
        successor = self.sql("bulk_claim_retained_v1",MANIFEST,"other-worker",45)
        self.assertEqual(successor["work_key"],second["work_key"])
        untouched = self.conn.execute(
            f"SELECT status,attempts FROM {self.schema}.bulk_work_v1 WHERE work_key=%s",
            (provider["work_key"],)).fetchone()
        self.assertEqual(untouched,("pending",0))

    def test_contract_mismatch_and_immutable_review_fail_closed(self):
        self.seed_manifest()
        self.add_reviews()
        self.conn.execute(
            f"DELETE FROM {self.schema}.bulk_scope_evidence_v1 WHERE evidence_key=%s",
            (FAMILIES[0],))
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_finalize_retained_review_v1", MANIFEST, REPORT)
        with self.assertRaises(self.pg.Error):
            self.conn.execute(f"DELETE FROM {self.schema}.bulk_family_review_v1")
        with self.assertRaises(self.pg.Error):
            self.conn.execute(f"UPDATE {self.schema}.bulk_family_review_v1 SET expected_units=9")
        self.assertEqual(self.conn.execute(
            f"SELECT count(*) FROM {self.schema}.bulk_family_review_v1").fetchone()[0],24)

    def test_user_stop_and_expired_job_still_refuse_after_review(self):
        self.seed_manifest()
        expired = self.reserve("synthetic:to-stop")
        self.add_reviews()
        self.sql("bulk_finalize_retained_review_v1", MANIFEST, REPORT)
        self.sql("bulk_stop_v1", MANIFEST, "user stopped")
        self.assertIsNone(self.sql("bulk_claim_retained_v1", MANIFEST, "test-worker", 45))
        self.assertEqual(self.conn.execute(
            f"SELECT status,attempts FROM {self.schema}.bulk_work_v1 WHERE work_key=%s",
            (expired["work_key"],)).fetchone(),("pending",0))


if __name__ == "__main__":
    unittest.main()
