"""Disposable PostgreSQL qualification of atomic retained-source materialisation.

This uses synthetic stage rows and administrative review fixtures ONLY. It cannot
establish 24-family source completeness, licensed-source access, real reviewer
authentication, HTTPS JWT, old-instance cessation or physical host eviction.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit, unquote
import uuid

URL = os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL", "")
ROOT = Path(__file__).resolve().parents[2]
CAPTURE = "top3000-augsep2026-retained-scope-v1"
RECEIPT = "ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496"
FAMILIES = (
 "REF01","P01","P02","D01","N01","N03","D02","D03","D04",
 "F04","F05","S02","F06","CTX06","CTX14","REF03","D05",
 "F01","F02","F03","N02","S01","CTX02","CTX07",
)
FILES = (
 "astra_ingestion_bulk_ledger_v1.sql",
 "astra_ingestion_bulk_retained_gate_v1.sql",
 "astra_ingestion_bulk_runtime_port_v1.sql",
 "astra_ingestion_bulk_unit_binding_v1.sql",
 "astra_ingestion_bulk_atomic_materializer_v1.sql",
)
MANIFEST, REPORT, SOURCE = "a"*64, "e"*64, "b"*64


@unittest.skipUnless(URL, "disposable local PostgreSQL only")
class BulkAtomicMaterializerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  u = urlsplit(URL)
  if (u.scheme not in ("postgres","postgresql")
      or u.hostname not in ("localhost","127.0.0.1","::1")
      or unquote(u.path) != "/astra_ingestion_qualification"
      or u.query or u.fragment):
   raise RuntimeError("local disposable qualification database required")
  import psycopg
  cls.pg = psycopg

 def setUp(self):
  self.schema = "astra_materializer_test_" + uuid.uuid4().hex[:10]
  self.conn = self.pg.connect(URL, autocommit=True)
  self.addCleanup(self.cleanup)
  self.conn.execute(f"CREATE SCHEMA {self.schema}")
  self.conn.execute(f"""
   CREATE TABLE {self.schema}.bulk_scope_capture_v1(
    capture_key text PRIMARY KEY,evidence_sha256 text NOT NULL,
    evidence_rows integer NOT NULL,state text NOT NULL,
    provider_requests integer NOT NULL,incremental_cost_microusd bigint NOT NULL);
   INSERT INTO {self.schema}.bulk_scope_capture_v1 VALUES
    ('{CAPTURE}','{RECEIPT}',4136,'CAPTURED_NOT_ADMITTED',0,0);
   CREATE TABLE {self.schema}.bulk_scope_evidence_v1(
    capture_key text NOT NULL,kind text NOT NULL,evidence_key text NOT NULL,
    source_sha256 text NOT NULL,PRIMARY KEY(capture_key,kind,evidence_key));
  """)
  for fam in FAMILIES:
   self.conn.execute(f"INSERT INTO {self.schema}.bulk_scope_evidence_v1 VALUES (%s,%s,%s,%s)",
                     (CAPTURE,"contract",fam,self.contract(fam)))
  for f in FILES:
   self.conn.execute((ROOT/"sql"/f).read_text().replace("astra_ingestion_v1",self.schema))
  self.sql("bulk_manifest_create_v1",MANIFEST,CAPTURE,RECEIPT,0,500)

 def cleanup(self):
  if hasattr(self,"conn"):
   try: self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
   finally: self.conn.close()

 @staticmethod
 def contract(fam):
  return hashlib.sha256(fam.encode("utf-8")).hexdigest()

 def sql(self,func,*args):
  return self.conn.execute(
   f"SELECT {self.schema}.{func}({','.join(['%s']*len(args))})",args).fetchone()[0]

 def reserve(self,key,*,deadline=None,max_records=10,predecessors=()):
  return self.sql("bulk_reserve_v1",MANIFEST,"REF01",key,"retained_source_reuse",SOURCE,
                  deadline or datetime.now(timezone.utc)+timedelta(minutes=15),
                  0,max_records,list(predecessors))

 def review_and_seal(self):
  for fam in FAMILIES:
   count=2 if fam=="REF01" else 1
   self.conn.execute(f"""
    INSERT INTO {self.schema}.bulk_family_review_v1
    (manifest_sha256,family,contract_sha256,expected_manifest_sha256,
     source_receipt_sha256,provenance_sha256,identity_sha256,pit_sha256,
     expected_units,observed_units,independent_report_sha256)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
   """,(MANIFEST,fam,self.contract(fam),"d"*64,"c"*64,"f"*64,
        "1"*64,"2"*64,count,count,REPORT))
  self.sql("bulk_finalize_retained_review_v1",MANIFEST,REPORT)
  for fam in FAMILIES:
   units=["REF01:a","REF01:b"] if fam=="REF01" else [fam+":a"]
   for unit in units:
    self.conn.execute(f"""
     INSERT INTO {self.schema}.bulk_reviewed_unit_v1
     (manifest_sha256,family,unit_key,source_receipt_sha256,
      provenance_sha256,identity_sha256,pit_sha256,independent_report_sha256)
     VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """,(MANIFEST,fam,unit,SOURCE,"f"*64,"1"*64,"2"*64,REPORT))
   unit_hash=self.conn.execute(f"""
    SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(
     jsonb_build_array(unit_key,source_receipt_sha256,provenance_sha256,
                       identity_sha256,pit_sha256)
      ORDER BY unit_key)::text,'[]'),'UTF8')),'hex')
    FROM {self.schema}.bulk_reviewed_unit_v1
    WHERE manifest_sha256=%s AND family=%s
   """,(MANIFEST,fam)).fetchone()[0]
   self.sql("bulk_seal_unit_set_v1",MANIFEST,fam,REPORT,unit_hash)

 def stage(self,key,rows,*,source=SOURCE,wrong_hash=False):
  body=json.dumps(rows)
  row_hash=self.conn.execute(
   "SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",
   (body,)).fetchone()[0]
  if wrong_hash: row_hash="0"*64
  self.conn.execute(f"""
   INSERT INTO {self.schema}.bulk_retained_source_page_v1
   (work_key,page_no,source_receipt_sha256,rows_sha256,source_rows)
   VALUES (%s,0,%s,%s,%s::jsonb)
  """,(key,source,row_hash,body))

 def test_atomic_output_and_receipt_then_automatic_successor_after_verification(self):
  first=self.reserve("REF01:a")
  second=self.reserve("REF01:b",predecessors=(first["work_key"],))
  self.review_and_seal()
  self.stage(first["work_key"],[{"id":"a"},{"id":"b"}])
  claim=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-a",60)
  self.assertEqual(claim["work_key"],first["work_key"])
  r=self.sql("bulk_atomic_retained_page_v1",first["work_key"],"worker-a",claim["claim_fence"],0)
  self.assertEqual((r["records_committed"],r["requests_committed"]),(2,0))
  readback=self.sql("bulk_retained_receipt_readback_v1",first["work_key"],0)
  self.assertTrue(readback["consistent"])
  self.assertEqual((readback["actual_records"],readback["output_sha256"]),(2,r["output_sha256"]))
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_retained_output_v1").fetchone()[0],2)
  with self.assertRaises(self.pg.Error):
   self.sql("bulk_atomic_retained_page_v1",first["work_key"],"worker-a",claim["claim_fence"],0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],1)
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-b",60))
  # Administrative synthetic fixture; does not certify independent real review.
  self.sql("bulk_verify_v1",first["work_key"],"worker-a",claim["claim_fence"],"f"*64)
  successor=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-b",60)
  self.assertEqual(successor["work_key"],second["work_key"])
  self.stage(second["work_key"],[{"id":"successor"}])
  self.assertEqual(self.sql("bulk_atomic_retained_page_v1",
                   second["work_key"],"worker-b",successor["claim_fence"],0)["records_committed"],1)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],2)

 def test_budget_failure_rolls_back_output_and_receipt_atomically(self):
  first=self.reserve("REF01:a",max_records=1)
  self.review_and_seal()
  self.stage(first["work_key"],[{"id":1},{"id":2}])
  claim=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-a",60)
  with self.assertRaises(self.pg.Error):
   self.sql("bulk_atomic_retained_page_v1",first["work_key"],"worker-a",claim["claim_fence"],0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_retained_output_v1").fetchone()[0],0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],0)
  self.assertEqual(self.conn.execute(
   f"SELECT records_committed,last_page FROM {self.schema}.bulk_work_v1"
   " WHERE work_key=%s",(first["work_key"],)).fetchone(),(0,-1))

 def test_stale_claim_cannot_materialise_and_stop_refuses(self):
  first=self.reserve("REF01:a")
  self.review_and_seal()
  self.stage(first["work_key"],[{"id":1}])
  claim=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-a",60)
  for owner,fence in [("old-instance",claim["claim_fence"]),
                       ("worker-a",claim["claim_fence"]+1)]:
   with self.subTest(owner=owner,fence=fence):
    with self.assertRaises(self.pg.Error):
     self.sql("bulk_atomic_retained_page_v1",first["work_key"],owner,fence,0)
  self.sql("bulk_stop_v1",MANIFEST,"explicit stop in test")
  with self.assertRaises(self.pg.Error):
   self.sql("bulk_atomic_retained_page_v1",first["work_key"],"worker-a",claim["claim_fence"],0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_retained_output_v1").fetchone()[0],0)

 def test_immutable_source_fingerprint_and_output_rows(self):
  first=self.reserve("REF01:a")
  self.review_and_seal()
  with self.assertRaises(self.pg.Error):
   self.stage(first["work_key"],[{"id":1}],wrong_hash=True)
  self.stage(first["work_key"],[{"id":1}])
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"UPDATE {self.schema}.bulk_retained_source_page_v1"
                     " SET source_receipt_sha256=%s WHERE work_key=%s",
                     ("f"*64,first["work_key"]))
  claim=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-a",60)
  self.sql("bulk_atomic_retained_page_v1",first["work_key"],"worker-a",claim["claim_fence"],0)
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"DELETE FROM {self.schema}.bulk_retained_output_v1")
  self.assertFalse(self.conn.execute(f"""
   SELECT bool_or(grantee=0 AND privilege_type='EXECUTE')
   FROM information_schema.routine_privileges
   WHERE specific_schema=%s AND routine_name='bulk_atomic_retained_page_v1'
  """,(self.schema,)).fetchone()[0] or False)


if __name__=="__main__":
 unittest.main()
