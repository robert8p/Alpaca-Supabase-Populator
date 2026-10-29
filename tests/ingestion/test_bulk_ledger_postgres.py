"""Disposable PostgreSQL checks for the staged, non-installed bulk ledger.

No remote target is accepted; all rows use synthetic source hashes and values.
Production privileges/transport and source completeness are separate gates.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import unittest
from urllib.parse import unquote, urlsplit
import uuid

URL = os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL", "")
ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = ROOT / "sql" / "astra_ingestion_bulk_ledger_v1.sql"
CAPTURE_KEY = "top3000-augsep2026-retained-scope-v1"
RECEIPT = "ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496"
MANIFEST = "a" * 64
SOURCE = "b" * 64


@unittest.skipUnless(URL, "PostgreSQL bulk ledger tests require disposable explicit local URL")
class BulkLedgerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = urlsplit(URL)
        if (target.scheme not in {"postgres", "postgresql"} or
            target.hostname not in {"localhost", "127.0.0.1", "::1"} or
            unquote(target.path) != "/astra_ingestion_qualification" or
            target.query or target.fragment):
            raise RuntimeError("bulk ledger tests accept only disposable loopback qualification database")
        import psycopg
        cls.pg = psycopg

    def setUp(self):
        self.schema = "astra_bulk_ledger_test_" + uuid.uuid4().hex[:12]
        self.conn = self.pg.connect(URL, autocommit=True)
        self.addCleanup(self.cleanup)
        self.conn.execute(f"CREATE SCHEMA {self.schema}")
        self.conn.execute(f"""
          CREATE TABLE {self.schema}.bulk_scope_capture_v1(
           capture_key text PRIMARY KEY,evidence_sha256 text NOT NULL,
           evidence_rows integer NOT NULL,state text NOT NULL,
           provider_requests integer NOT NULL,incremental_cost_microusd bigint NOT NULL);
          INSERT INTO {self.schema}.bulk_scope_capture_v1 VALUES
           ('{CAPTURE_KEY}','{RECEIPT}',4136,'CAPTURED_NOT_ADMITTED',0,0);
        """)
        self.conn.execute(SQL_PATH.read_text().replace("astra_ingestion_v1", self.schema))

    def cleanup(self):
        if hasattr(self, "conn"):
            try:
                self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
            finally:
                self.conn.close()

    def sql(self, name, args=()):
        placeholders = ",".join(["%s"] * len(args))
        return self.conn.execute(f"SELECT {self.schema}.{name}({placeholders})", args).fetchone()[0]

    def manifest(self, requests=3, records=100):
        return self.sql("bulk_manifest_create_v1", (MANIFEST,CAPTURE_KEY,RECEIPT,requests,records))

    def reserve(self, family="REF01", unit="synthetic:a", predecessors=None, *, requests=0, records=10, deadline=None):
        return self.sql("bulk_reserve_v1",(MANIFEST,family,unit,
            "provider_acquisition" if requests else "retained_source_reuse",SOURCE,
            deadline or datetime.now(timezone.utc)+timedelta(minutes=20), requests, records,
            predecessors or []))

    def test_existing_capture_required_and_manifest_collision_fails_closed(self):
        result=self.manifest()
        self.assertEqual(result["reserved_requests"],0)
        self.assertEqual(self.manifest(),result)
        with self.assertRaises(self.pg.Error): self.manifest(records=101)
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_manifest_create_v1",("c"*64,"no-source",RECEIPT,3,100))
        self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {self.schema}.bulk_manifest_v1").fetchone()[0],1)

    def test_atomic_reservation_idempotency_and_dependency_successor(self):
        self.manifest()
        due=datetime.now(timezone.utc)+timedelta(minutes=20)
        a=self.reserve(deadline=due)
        self.assertEqual(self.reserve(deadline=due)["work_key"],a["work_key"])
        b=self.reserve(family="P01",unit="synthetic:b",predecessors=[a["work_key"]])
        self.assertEqual(self.conn.execute(f"SELECT reserved_records FROM {self.schema}.bulk_manifest_v1").fetchone()[0],20)
        claim=self.sql("bulk_claim_v1",(MANIFEST,"worker-one",90))
        self.assertEqual(claim["work_key"],a["work_key"])
        self.assertEqual(self.sql("bulk_claim_v1",(MANIFEST,"worker-two",90)),None)
        receipt=self.sql("bulk_commit_page_v1",(a["work_key"],"worker-one",claim["claim_fence"],0,"c"*64,"d"*64,5,0))
        self.assertEqual(receipt["records_committed"],5)
        again=self.sql("bulk_commit_page_v1",(a["work_key"],"worker-one",claim["claim_fence"],0,"c"*64,"d"*64,5,0))
        self.assertEqual(receipt,again)
        self.assertEqual(self.conn.execute(f"SELECT records_committed FROM {self.schema}.bulk_work_v1 WHERE work_key=%s",(a["work_key"],)).fetchone()[0],5)
        verified=self.sql("bulk_verify_v1",(a["work_key"],"worker-one",claim["claim_fence"],"e"*64))
        self.assertEqual(verified["status"],"verified")
        successor=self.sql("bulk_claim_v1",(MANIFEST,"worker-two",90))
        self.assertEqual(successor["work_key"],b["work_key"])

    def test_reservation_budget_dependency_and_original_deadline_are_finite(self):
        self.manifest(requests=2,records=60)
        a=self.reserve(requests=2,records=40)
        with self.assertRaises(self.pg.Error):self.reserve(unit="over-budget",requests=1)
        with self.assertRaises(self.pg.Error):self.reserve(unit="record-over",records=30)
        with self.assertRaises(self.pg.Error):self.reserve(unit="missing-parent",predecessors=["nonexistent"])
        with self.assertRaises(self.pg.Error):self.reserve(unit="expired",deadline=datetime(2026,10,28,tzinfo=timezone.utc))
        counts=self.conn.execute(f"SELECT reserved_requests,reserved_records FROM {self.schema}.bulk_manifest_v1").fetchone()
        self.assertEqual(counts,(2,40))
        self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {self.schema}.bulk_work_v1").fetchone()[0],1)
        self.assertTrue(a["work_key"].startswith("astra-bulk-v1-"))

    def test_stale_fence_and_expired_claim_fail_closed_not_auto_replaced(self):
        self.manifest()
        a=self.reserve()
        claim=self.sql("bulk_claim_v1",(MANIFEST,"owner-one",30))
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_commit_page_v1",(a["work_key"],"stale-owner",claim["claim_fence"],0,"c"*64,"d"*64,1,0))
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_commit_page_v1",(a["work_key"],"owner-one",claim["claim_fence"]+1,0,"c"*64,"d"*64,1,0))
        self.conn.execute(f"UPDATE {self.schema}.bulk_work_v1 SET claim_until=clock_timestamp()-interval '1 second' WHERE work_key=%s",(a["work_key"],))
        self.assertEqual(self.sql("bulk_claim_v1",(MANIFEST,"owner-two",90)),None)
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_commit_page_v1",(a["work_key"],"owner-one",claim["claim_fence"],0,"c"*64,"d"*64,1,0))
        self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],0)

    def test_stop_irreversibility_and_preserved_completed_receipts(self):
        self.manifest()
        a=self.reserve()
        claim=self.sql("bulk_claim_v1",(MANIFEST,"owner",90))
        self.sql("bulk_commit_page_v1",(a["work_key"],"owner",claim["claim_fence"],0,"c"*64,"d"*64,1,0))
        self.assertTrue(self.sql("bulk_stop_v1",(MANIFEST,"stop from user")))
        self.assertEqual(self.sql("bulk_claim_v1",(MANIFEST,"replacement",90)),None)
        with self.assertRaises(self.pg.Error):
            self.sql("bulk_commit_page_v1",(a["work_key"],"owner",claim["claim_fence"],1,"c"*64,"d"*64,1,0))
        with self.assertRaises(self.pg.Error):
            self.conn.execute(f"UPDATE {self.schema}.bulk_manifest_v1 SET stopped=false WHERE manifest_sha256=%s",(MANIFEST,))
        with self.assertRaises(self.pg.Error):
            self.conn.execute(f"DELETE FROM {self.schema}.bulk_receipt_v1")
        with self.assertRaises(self.pg.Error):
            self.conn.execute(f"UPDATE {self.schema}.bulk_work_v1 SET original_deadline=clock_timestamp()+interval '1 day' WHERE work_key=%s",(a["work_key"],))
        self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],1)

if __name__ == "__main__": unittest.main()