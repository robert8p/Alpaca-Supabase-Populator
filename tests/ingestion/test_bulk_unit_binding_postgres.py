"""Disposable-only security and source-unit binding regressions.

Synthetic rows do not attest real REF01/security coverage, distinct reviewers,
JWT over HTTPS, hosted restart/eviction, or permission to deploy.
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
MANIFEST, REPORT, SOURCE, OTHER = "a"*64, "e"*64, "b"*64, "9"*64
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
)


@unittest.skipUnless(URL, "disposable loopback PostgreSQL URL required")
class BulkReviewedUnitPostgresTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  u = urlsplit(URL)
  if (u.scheme not in ("postgres", "postgresql")
      or u.hostname not in ("localhost", "127.0.0.1", "::1")
      or unquote(u.path) != "/astra_ingestion_qualification"
      or u.query or u.fragment):
   raise RuntimeError("only disposable loopback qualification database allowed")
  import psycopg
  cls.pg = psycopg

 def setUp(self):
  self.schema = "astra_unit_binding_test_" + uuid.uuid4().hex[:10]
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
  for fam in FAMILIES:
   self.conn.execute(
    f"INSERT INTO {self.schema}.bulk_scope_evidence_v1 VALUES (%s,%s,%s,%s)",
    (CAPTURE, "contract", fam, self.contract(fam)))
  for filename in FILES:
   self.conn.execute((ROOT/"sql"/filename).read_text().replace("astra_ingestion_v1", self.schema))
  self.sql("bulk_manifest_create_v1", MANIFEST, CAPTURE, RECEIPT, 1, 500)

 def cleanup(self):
  if hasattr(self, "conn"):
   try: self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
   finally: self.conn.close()

 def sql(self, func, *args):
  return self.conn.execute(
   f"SELECT {self.schema}.{func}({','.join(['%s']*len(args))})", args).fetchone()[0]

 @staticmethod
 def contract(fam):
  return hashlib.sha256(fam.encode()).hexdigest()

 def reserve(self, unit, *, fam="REF01", source=SOURCE, dependencies=(), deadline=None):
  return self.sql(
   "bulk_reserve_v1", MANIFEST, fam, unit, "retained_source_reuse", source,
   deadline or datetime.now(timezone.utc)+timedelta(minutes=15),
   0, 10, list(dependencies))

 def family_reviews(self):
  for fam in FAMILIES:
   count = 2 if fam=="REF01" else 1
   self.conn.execute(f"""
    INSERT INTO {self.schema}.bulk_family_review_v1 (
      manifest_sha256,family,contract_sha256,expected_manifest_sha256,
      source_receipt_sha256,provenance_sha256,identity_sha256,pit_sha256,
      expected_units,observed_units,independent_report_sha256)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
   """,(MANIFEST,fam,self.contract(fam),"d"*64,"c"*64,"f"*64,
        "1"*64,"2"*64,count,count,REPORT))
  self.sql("bulk_finalize_retained_review_v1", MANIFEST, REPORT)

 def add_unit(self,fam,unit,source=SOURCE):
  self.conn.execute(f"""
   INSERT INTO {self.schema}.bulk_reviewed_unit_v1(
    manifest_sha256,family,unit_key,source_receipt_sha256,
    provenance_sha256,identity_sha256,pit_sha256,independent_report_sha256)
   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
  """,(MANIFEST,fam,unit,source,"f"*64,"1"*64,"2"*64,REPORT))

 def set_hash(self,fam):
  # Synthetic fixture obtains SQL-computed expected hash; real deployment
  # MUST instead independently pin it from source-backed reviewer evidence.
  return self.conn.execute(f"""
   SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(
    jsonb_build_array(unit_key,source_receipt_sha256,provenance_sha256,
                      identity_sha256,pit_sha256)
    ORDER BY unit_key)::text,'[]'),'UTF8')),'hex')
   FROM {self.schema}.bulk_reviewed_unit_v1
   WHERE manifest_sha256=%s AND family=%s
  """,(MANIFEST,fam)).fetchone()[0]

 def seal_all(self,*,skip=None):
  for fam in FAMILIES:
   if fam==skip: continue
   self.add_unit(fam,f"{fam}:a")
   if fam=="REF01": self.add_unit(fam,"REF01:b")
   self.sql("bulk_seal_unit_set_v1",MANIFEST,fam,REPORT,self.set_hash(fam))

 def test_complete_exact_set_allows_bound_successor_only_after_verification(self):
  first=self.reserve("REF01:a")
  second=self.reserve("REF01:b",dependencies=(first["work_key"],))
  self.family_reviews()
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.seal_all()
  self.assertEqual(self.sql("bulk_runtime_admission_v1",MANIFEST)["complete_family_count"],24)
  claimed=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-a",45)
  self.assertEqual(claimed["work_key"],first["work_key"])
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-b",45))
  self.sql("bulk_commit_page_v1",first["work_key"],"worker-a",
           claimed["claim_fence"],0,SOURCE,"c"*64,3,0)
  # Synthetic administrative verification: NOT an actual independent actor.
  self.sql("bulk_verify_v1",first["work_key"],"worker-a",claimed["claim_fence"],"f"*64)
  successor=self.sql("bulk_runtime_claim_v1",MANIFEST,"worker-b",45)
  self.assertEqual(successor["work_key"],second["work_key"])
  self.assertEqual(successor["attempts"],1)
  self.assertEqual(successor["max_requests"],0)

 def test_unreviewed_reserved_unit_refuses_entire_admission(self):
  attacker=self.reserve("REF01:arbitrary-not-reviewed")
  self.family_reviews()
  self.seal_all()
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker",45))
  self.assertEqual(self.conn.execute(
   f"SELECT status,attempts FROM {self.schema}.bulk_work_v1 WHERE work_key=%s",
   (attacker["work_key"],)).fetchone(),("pending",0))

 def test_mismatched_unit_source_receipt_fails_even_for_valid_key(self):
  mismatched=self.reserve("REF01:a",source=OTHER)
  self.family_reviews()
  self.seal_all()
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker",60))
  self.assertEqual(self.conn.execute(
   f"SELECT attempts FROM {self.schema}.bulk_work_v1 WHERE work_key=%s",
   (mismatched["work_key"],)).fetchone()[0],0)

 def test_missing_family_seal_and_wrong_external_set_hash_fail_closed(self):
  self.family_reviews()
  self.seal_all(skip="CTX07")
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  with self.assertRaises(self.pg.Error):
   self.sql("bulk_seal_unit_set_v1",MANIFEST,"CTX07",REPORT,"9"*64)
  self.add_unit("CTX07","CTX07:a")
  with self.assertRaises(self.pg.Error):
   self.sql("bulk_seal_unit_set_v1",MANIFEST,"CTX07",REPORT,"9"*64)
  self.sql("bulk_seal_unit_set_v1",MANIFEST,"CTX07",REPORT,self.set_hash("CTX07"))
  self.assertIsNotNone(self.sql("bulk_runtime_admission_v1",MANIFEST))

 def test_seals_rows_stop_and_acl_cannot_be_bypassed(self):
  self.family_reviews()
  self.seal_all()
  with self.assertRaises(self.pg.Error):
   self.add_unit("REF01","REF01:unreviewed-late")
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"DELETE FROM {self.schema}.bulk_reviewed_unit_v1")
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"UPDATE {self.schema}.bulk_unit_seal_v1 SET unit_count=3")
  for table in ("bulk_reviewed_unit_v1","bulk_unit_seal_v1"):
   r=self.conn.execute("""
    SELECT c.relrowsecurity FROM pg_class c JOIN pg_namespace n
    ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s
   """,(self.schema,table)).fetchone()
   self.assertEqual(r,(True,))
  for proc in ("bulk_reviewed_unit_insert_guard_v1","bulk_seal_unit_set_v1",
               "bulk_runtime_admission_v1","bulk_runtime_claim_v1"):
   n=self.conn.execute("""
    SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    CROSS JOIN LATERAL aclexplode(p.proacl) acl
    WHERE n.nspname=%s AND p.proname=%s
    AND acl.grantee=0 AND acl.privilege_type='EXECUTE'
   """,(self.schema,proc)).fetchone()[0]
   self.assertEqual(n,0,proc)
  self.sql("bulk_stop_v1",MANIFEST,"newer user stop")
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker",30))

 def test_reviewed_set_cannot_promote_provider_work(self):
  self.family_reviews()
  self.seal_all()
  self.sql("bulk_reserve_v1",MANIFEST,"P01","P01:a",
           "provider_acquisition",SOURCE,
           datetime.now(timezone.utc)+timedelta(minutes=5),1,5,[])
  self.assertIsNone(self.sql("bulk_runtime_admission_v1",MANIFEST))
  self.assertIsNone(self.sql("bulk_runtime_claim_v1",MANIFEST,"worker",45))


if __name__=="__main__":
 unittest.main()
