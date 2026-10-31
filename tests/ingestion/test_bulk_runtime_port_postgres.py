"""Disposable PostgreSQL checks for STAGED restricted ASTRA runtime port.

Fabricated evidence is not real independent review, production identity,
HTTPS JWT, full 24-family source coverage, or hosted materialisation.
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
CAPTURE = "top3000-augsep2026-retained-scope-v1"
RECEIPT = "ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496"
MANIFEST, REPORT, SOURCE = "a" * 64, "e" * 64, "b" * 64
FAMILIES = (
 "REF01","P01","P02","D01","N01","N03","D02","D03","D04",
 "F04","F05","S02","F06","CTX06","CTX14","REF03","D05",
 "F01","F02","F03","N02","S01","CTX02","CTX07",
)

@unittest.skipUnless(URL, "disposable PostgreSQL qualification URL required")
class BulkRuntimePortPostgresTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  u = urlsplit(URL)
  if (u.scheme not in ("postgres","postgresql") or
      u.hostname not in ("localhost","127.0.0.1","::1") or
      unquote(u.path) != "/astra_ingestion_qualification" or u.query or u.fragment):
   raise RuntimeError("ASTRA tests require disposable loopback PostgreSQL")
  import psycopg
  cls.pg = psycopg

 def setUp(self):
  self.schema = "astra_bulk_runtime_test_" + uuid.uuid4().hex[:10]
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
    (CAPTURE,"contract",family,self.contract_sha(family)))
  for name in ("astra_ingestion_bulk_ledger_v1.sql",
               "astra_ingestion_bulk_retained_gate_v1.sql",
               "astra_ingestion_bulk_runtime_port_v1.sql"):
   self.conn.execute((ROOT/"sql"/name).read_text().replace("astra_ingestion_v1",self.schema))

 def cleanup(self):
  if hasattr(self,"conn"):
   try: self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
   finally: self.conn.close()

 @staticmethod
 def contract_sha(family):
  return hashlib.sha256(family.encode("utf-8")).hexdigest()

 def sql(self,name,*args):
  return self.conn.execute(
   f"SELECT {self.schema}.{name}({','.join(['%s']*len(args))})",args).fetchone()[0]

 def manifest(self):
  return self.sql("bulk_manifest_create_v1",MANIFEST,CAPTURE,RECEIPT,1,100)

 def reserve(self,unit,predecessors=None):
  return self.sql("bulk_reserve_v1",MANIFEST,"REF01",unit,"retained_source_reuse",
                  SOURCE,datetime.now(timezone.utc)+timedelta(minutes=15),0,10,predecessors or [])

 def review(self):
  for family in FAMILIES:
   self.conn.execute(f"""
    INSERT INTO {self.schema}.bulk_family_review_v1
    (manifest_sha256,family,contract_sha256,expected_manifest_sha256,
     source_receipt_sha256,provenance_sha256,identity_sha256,pit_sha256,
     expected_units,observed_units,independent_report_sha256)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,10,10,%s)
    """,(MANIFEST,family,self.contract_sha(family),"d"*64,"c"*64,
          "f"*64,"1"*64,"2"*64,REPORT))
  return self.sql("bulk_finalize_retained_review_v1",MANIFEST,REPORT)

 def test_dispatcher_shape_and_automatic_dependency_eligibility(self):
  self.manifest()
  first=self.reserve("synthetic-first")
  successor=self.reserve("synthetic-next",[first["work_key"]])
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-a",60))
  self.review()
  self.assertEqual(self.sql("bulk_runtime_admission_v1",MANIFEST),{
   "status":"INDEPENDENTLY_REVIEWED_RETAINED_ONLY",
   "manifest_sha256":MANIFEST,"capture_key":CAPTURE,
   "capture_receipt_sha256":RECEIPT,"complete_family_count":24,
   "independent_review_sha256":REPORT,"stopped":False})
  claimed=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-a",60)
  self.assertEqual(claimed["work_key"],first["work_key"])
  self.assertEqual(claimed["max_requests"],0)
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-b",60))
  self.sql("bulk_commit_page_v1",first["work_key"],"worker-a",
           claimed["claim_fence"],0,"c"*64,"d"*64,3,0)
  # This is synthetic administrative verification, NOT genuine review.
  self.sql("bulk_verify_v1",first["work_key"],"worker-a",claimed["claim_fence"],"f"*64)
  next_claim=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-b",60)
  self.assertEqual(next_claim["work_key"],successor["work_key"])

 def test_original_source_contract_drift_refuses_admission(self):
  self.manifest()
  self.reserve("source-drift")
  self.review()
  self.conn.execute(f"DELETE FROM {self.schema}.bulk_scope_evidence_v1 WHERE evidence_key='REF01'")
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker",30))

 def test_user_stop_and_unknown_manifest_fail_closed(self):
  self.manifest()
  self.reserve("stopped")
  self.review()
  self.assertIsNone(self.sql("bulk_runtime_admission_v1","0"*64))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1","0"*64,"worker",45))
  self.sql("bulk_stop_v1",MANIFEST,"user stop")
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker",45))

 def test_provider_and_invalid_owner_not_admitted(self):
  self.manifest()
  self.sql("bulk_reserve_v1",MANIFEST,"P01","provider","provider_acquisition",SOURCE,
           datetime.now(timezone.utc)+timedelta(minutes=15),1,5,[])
  self.review()
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker",45))
  with self.assertRaises(self.pg.Error):
   self.sql("bulk_runtime_claim_v1",MANIFEST,"bad actor",45)

 def test_public_execute_explicitly_revoked(self):
  for name in ("bulk_runtime_admission_v1","bulk_runtime_claim_v1"):
   # A function owner correctly retains EXECUTE. Inspect ACL grantee OID 0
   # (PUBLIC) explicitly, rather than matching the owner's '=X/' substring.
   public_exec=self.conn.execute("""
    SELECT count(*) FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace
    CROSS JOIN LATERAL aclexplode(p.proacl) permission
    WHERE n.nspname=%s AND p.proname=%s
    AND permission.grantee=0 AND permission.privilege_type='EXECUTE'
   """,(self.schema,name)).fetchone()[0]
   self.assertEqual(public_exec,0)
  # There is deliberately NO grant to an application role in staged SQL.

if __name__=="__main__":
 unittest.main()
