"""Disposable PostgreSQL qualification of staged, never-executable provider ticket.

Synthetic reviewer rows do not grant real authenticated reviewer identity,
source coverage, hosted recovery, provider transport or production admission.
No external market-data requests, secrets or licensed records are involved.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlsplit,unquote
import hashlib
import os
import unittest
import uuid

URL=os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL","")
ROOT=Path(__file__).resolve().parents[2]
CAPTURE="top3000-augsep2026-retained-scope-v1"
RECEIPT="ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496"
MANIFEST,REPORT,SOURCE="a"*64,"e"*64,"b"*64
FAMILIES=(
 "REF01","P01","P02","D01","N01","N03","D02","D03","D04",
 "F04","F05","S02","F06","CTX06","CTX14","REF03","D05",
 "F01","F02","F03","N02","S01","CTX02","CTX07",
)
SQL_FILES=(
 "astra_ingestion_bulk_ledger_v1.sql",
 "astra_ingestion_bulk_retained_gate_v1.sql",
 "astra_ingestion_bulk_runtime_port_v1.sql",
 "astra_ingestion_bulk_unit_binding_v1.sql",
 "astra_ingestion_bulk_provider_precall_v1.sql",
)


@unittest.skipUnless(URL,"disposable loopback PostgreSQL required")
class ProviderPrecallPostgresTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  u=urlsplit(URL)
  if (u.scheme not in ("postgres","postgresql") or
      u.hostname not in ("localhost","127.0.0.1","::1") or
      unquote(u.path)!="/astra_ingestion_qualification" or u.query or u.fragment):
   raise RuntimeError("only disposable loopback qualification database permitted")
  import psycopg
  cls.pg=psycopg

 def setUp(self):
  self.schema="astra_precall_test_"+uuid.uuid4().hex[:10]
  self.conn=self.pg.connect(URL,autocommit=True)
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
   self.conn.execute(f"INSERT INTO {self.schema}.bulk_scope_evidence_v1 VALUES (%s,%s,%s,%s)",
                     (CAPTURE,"contract",fam,self.contract(fam)))
  for name in SQL_FILES:
   self.conn.execute((ROOT/"sql"/name).read_text().replace("astra_ingestion_v1",self.schema))
  self.sql("bulk_manifest_create_v1",MANIFEST,CAPTURE,RECEIPT,2,100)

 def cleanup(self):
  if hasattr(self,"conn"):
   try:self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
   finally:self.conn.close()

 def sql(self,func,*args):
  return self.conn.execute(
   f"SELECT {self.schema}.{func}({','.join(['%s']*len(args))})",args).fetchone()[0]

 @staticmethod
 def contract(fam):
  return hashlib.sha256(fam.encode("utf-8")).hexdigest()

 def reserve(self,unit="P01:a",*,source=SOURCE,records=10,requests=2):
  return self.sql("bulk_reserve_v1",MANIFEST,"P01",unit,
    "provider_acquisition",source,datetime.now(timezone.utc)+timedelta(minutes=15),
    requests,records,[])

 def review(self,*,provider=False,skip_family=None):
  for fam in FAMILIES:
   self.conn.execute(f"""
    INSERT INTO {self.schema}.bulk_family_review_v1
    (manifest_sha256,family,contract_sha256,expected_manifest_sha256,
     source_receipt_sha256,provenance_sha256,identity_sha256,pit_sha256,
     expected_units,observed_units,independent_report_sha256)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1,1,%s)
    """,(MANIFEST,fam,self.contract(fam),"d"*64,"c"*64,
         "f"*64,"1"*64,"2"*64,REPORT))
  self.sql("bulk_finalize_retained_review_v1",MANIFEST,REPORT)
  for fam in FAMILIES:
   if fam==skip_family: continue
   self.conn.execute(f"""
    INSERT INTO {self.schema}.bulk_reviewed_unit_v1
    (manifest_sha256,family,unit_key,source_receipt_sha256,
     provenance_sha256,identity_sha256,pit_sha256,independent_report_sha256)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """,(MANIFEST,fam,f"{fam}:a",SOURCE,"f"*64,"1"*64,"2"*64,REPORT))
   digest=self.conn.execute(f"""
    SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(
     jsonb_build_array(unit_key,source_receipt_sha256,provenance_sha256,
                       identity_sha256,pit_sha256) ORDER BY unit_key)::text,'[]'),
      'UTF8')),'hex')
    FROM {self.schema}.bulk_reviewed_unit_v1
    WHERE manifest_sha256=%s AND family=%s
   """,(MANIFEST,fam)).fetchone()[0]
   self.sql("bulk_seal_unit_set_v1",MANIFEST,fam,REPORT,digest)
  if provider:
   self.conn.execute(f"""
    INSERT INTO {self.schema}.bulk_provider_review_v1(
    manifest_sha256,independent_report_sha256,
    identity_assurance_sha256,entitlement_assurance_sha256)
    VALUES (%s,%s,%s,%s)
   """,(MANIFEST,REPORT,"1"*64,"2"*64))

 def claim(self):
  return self.sql("bulk_claim_v1",MANIFEST,"synthetic-owner",60)

 def precall(self,w,owner="synthetic-owner",fence=None,page=0,limit=5,request="9"*64):
  return self.sql("bulk_provider_precall_reserve_v1",w["work_key"],
    owner,fence if fence is not None else w["claim_fence"],page,request,limit)

 def test_missing_review_or_unit_set_never_reserves(self):
  self.reserve()
  w=self.claim()
  with self.assertRaises(self.pg.Error):self.precall(w)
  self.review(provider=False)
  with self.assertRaises(self.pg.Error):self.precall(w)
  self.conn.execute(f"""
    INSERT INTO {self.schema}.bulk_provider_review_v1(
    manifest_sha256,independent_report_sha256,identity_assurance_sha256,
    entitlement_assurance_sha256) VALUES (%s,%s,%s,%s)
   """,(MANIFEST,REPORT,"1"*64,"2"*64))
  result=self.precall(w)
  self.assertEqual(result["status"],"RESERVED_NO_PROVIDER_TRANSPORT_GRANT")
  self.assertIs(result["provider_submission_authorized"],False)
  self.assertEqual(result["records_reserved"],5)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_precall_v1").fetchone()[0],1)
  self.assertEqual(self.conn.execute(
   f"SELECT requests_committed FROM {self.schema}.bulk_work_v1 WHERE work_key=%s",
   (w["work_key"],)).fetchone()[0],0)

 def test_duplicate_ticket_and_uncertain_effects_cannot_refetch(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  first=self.precall(w)
  self.assertEqual(first["page_no"],0)
  for digest in ("9"*64,"8"*64):
   with self.assertRaises(self.pg.Error):self.precall(w,request=digest)
  self.conn.execute(
   f"UPDATE {self.schema}.bulk_work_v1 SET claim_until=clock_timestamp()-interval '1 second' WHERE work_key=%s",
   (w["work_key"],))
  with self.assertRaises(self.pg.Error):self.precall(w)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_precall_v1").fetchone()[0],1)
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"DELETE FROM {self.schema}.bulk_provider_precall_v1")
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"UPDATE {self.schema}.bulk_provider_precall_v1 SET records_reserved=9")

 def test_stop_budget_fence_and_wrong_session_rejected(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  for kw in ({"owner":"other"},{"fence":w["claim_fence"]+1},
             {"limit":11},{"page":1},{"request":"not-a-hash"},
             {"limit":0},{"limit":1001}):
   with self.subTest(case=kw),self.assertRaises(self.pg.Error):
    self.precall(w,**kw)
  self.sql("bulk_stop_v1",MANIFEST,"newer user stop")
  with self.assertRaises(self.pg.Error):self.precall(w)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_precall_v1").fetchone()[0],0)

 def test_unreviewed_other_reserved_unit_poison_entire_manifest(self):
  self.reserve()
  self.sql("bulk_reserve_v1",MANIFEST,"REF01","unreviewed:new",
    "retained_source_reuse",SOURCE,
    datetime.now(timezone.utc)+timedelta(minutes=15),0,3,[])
  self.review(provider=True)
  w=self.claim()
  with self.assertRaises(self.pg.Error):self.precall(w)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_precall_v1").fetchone()[0],0)

 def test_no_public_grants_or_production_provider_authority(self):
  for table in ("bulk_provider_review_v1","bulk_provider_precall_v1"):
   self.assertEqual(self.conn.execute("""
    SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n
    ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s
   """,(self.schema,table)).fetchone(),(True,))
  public_exec=self.conn.execute("""
   SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   CROSS JOIN LATERAL aclexplode(p.proacl) x
   WHERE n.nspname=%s AND p.proname=%s
   AND x.grantee=0 AND x.privilege_type='EXECUTE'
  """,(self.schema,"bulk_provider_precall_reserve_v1")).fetchone()[0]
  self.assertEqual(public_exec,0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_review_v1").fetchone()[0],0)


if __name__=="__main__":unittest.main()
