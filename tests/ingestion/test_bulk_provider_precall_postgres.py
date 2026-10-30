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
 "astra_ingestion_bulk_provider_response_quarantine_v1.sql",
 "astra_ingestion_bulk_provider_atomic_receipt_v1.sql",
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
   self.add_request_review()

 def add_request_review(self,*,request="9"*64,limit=5,page=0):
  work=self.conn.execute(
   f"SELECT work_key FROM {self.schema}.bulk_work_v1 WHERE manifest_sha256=%s AND family='P01' AND unit_key='P01:a'",
   (MANIFEST,)).fetchone()
  if work is None:raise AssertionError("expected synthetic P01 unit")
  self.conn.execute(f"""
   INSERT INTO {self.schema}.bulk_provider_reviewed_request_v1(
     work_key,page_no,manifest_sha256,family,source_receipt_sha256,
     independent_report_sha256,request_sha256,records_reserved)
   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
  """,(work[0],page,MANIFEST,"P01",SOURCE,REPORT,request,limit))

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
  with self.assertRaises(self.pg.Error):self.precall(w)
  self.add_request_review()
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

 def test_request_digest_or_reserved_max_must_match_separate_review(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  for kw in ({"request":"8"*64},{"limit":6},{"limit":1}):
   with self.subTest(case=kw),self.assertRaises(self.pg.Error):
    self.precall(w,**kw)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_precall_v1").fetchone()[0],0)
  self.precall(w)
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"UPDATE {self.schema}.bulk_provider_reviewed_request_v1 SET request_sha256=%s",("7"*64,))
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"DELETE FROM {self.schema}.bulk_provider_reviewed_request_v1")

 def test_no_public_grants_or_production_provider_authority(self):
  for table in ("bulk_provider_review_v1","bulk_provider_precall_v1",
                "bulk_provider_reviewed_request_v1"):
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


 def synthetic_stage(self,**changes):
  # Fabricated bars; never licensed provider records or genuine source proof.
  row=dict(timestamp_utc="2026-09-02T13:30:00Z",
   open="10.1",high="10.5",low="10",close="10.2",vwap="10.3",
   volume=100,trade_count=5,record_sha256="6"*64)
  stage=dict(source_page_sha256="f"*64,stage_candidate_sha256="7"*64,
   provider_records_observed=1,eligible_records=1,
   inclusive_end_records_excluded=0,eligible_bars=[row],
   next_page_required=False,continuation_token_sha256=None,
   previous_continuation_token_sha256=None)
  stage.update(changes)
  return stage

 def quarantine(self,w,stage=None,*,owner="synthetic-owner",fence=None,request="9"*64,page=0):
  from psycopg.types.json import Jsonb
  return self.sql("bulk_provider_quarantine_response_v1",w["work_key"],
   owner,fence if fence is not None else w["claim_fence"],
   page,request,Jsonb(self.synthetic_stage() if stage is None else stage))

 def test_response_stages_atomically_without_provider_output_or_budget_double_count(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  result=self.quarantine(w)
  self.assertEqual(result["status"],"QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED")
  self.assertEqual((result["eligible_records"],result["provider_records_observed"]),(1,1))
  self.assertFalse(result["bulk_output_committed"])
  self.assertFalse(result["provider_submission_authorized"])
  self.assertFalse(result["coverage_certified"])
  readback=self.sql("bulk_provider_quarantine_readback_v1",w["work_key"],0)
  self.assertTrue(readback["consistent"])
  self.assertEqual(readback["stage_candidate_sha256"],"7"*64)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_response_quarantine_v1"
  ).fetchone()[0],1)
  self.assertEqual(self.conn.execute(
   f"SELECT requests_committed,records_committed,last_page FROM {self.schema}.bulk_work_v1"
   " WHERE work_key=%s",(w["work_key"],)).fetchone(),(0,0,-1))
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],0)
  with self.assertRaises(self.pg.Error):self.quarantine(w)
  with self.assertRaises(self.pg.Error):self.precall(w)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_response_quarantine_v1"
  ).fetchone()[0],1)

 def test_response_refuses_missing_ticket_stale_owner_and_review_mismatch(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  with self.assertRaises(self.pg.Error):self.quarantine(w)
  self.precall(w)
  for change in ({"owner":"other"},{"fence":w["claim_fence"]+1},
                 {"request":"8"*64},{"page":1}):
   with self.subTest(change=change),self.assertRaises(self.pg.Error):
    self.quarantine(w,**change)
  self.sql("bulk_stop_v1",MANIFEST,"synthetic explicit stop")
  with self.assertRaises(self.pg.Error):self.quarantine(w)
  self.assertIsNone(self.sql("bulk_provider_quarantine_readback_v1",w["work_key"],0))

 def test_response_refuses_payload_rewriting_type_confusion_and_count_fraud(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  base=self.synthetic_stage()
  mutations=(
   {"source_page_sha256":"wrong"},
   {"stage_candidate_sha256":"wrong"},
   {"provider_records_observed":6},
   {"provider_records_observed":True},
   {"eligible_records":False},
   {"eligible_records":2},
   {"inclusive_end_records_excluded":2},
   {"next_page_required":True},
   {"continuation_token_sha256":"1"*64},
   {"previous_continuation_token_sha256":"2"*64},
   {"eligible_bars":"not-array"},
   {"extra_field":"AUTHORIZED"},
   {"eligible_bars":[{**base["eligible_bars"][0],"time":"extra"}]},
   {"eligible_bars":[{**base["eligible_bars"][0],"record_sha256":"bad"}]},
   {"eligible_bars":[{**base["eligible_bars"][0],"timestamp_utc":"2026-08-02T13:30:00Z"}]},
   {"eligible_bars":[{**base["eligible_bars"][0],"trade_count":True}]},
   {"eligible_bars":[base["eligible_bars"][0],base["eligible_bars"][0]],
    "provider_records_observed":2,"eligible_records":2},
  )
  for changes in mutations:
   with self.subTest(changes=changes),self.assertRaises(self.pg.Error):
    self.quarantine(w,{**base,**changes})
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_response_quarantine_v1"
  ).fetchone()[0],0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],0)

 def test_response_accepts_bound_inclusive_end_without_false_eligible_credit(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  stage=self.synthetic_stage(provider_records_observed=2,
   eligible_records=1,inclusive_end_records_excluded=1)
  result=self.quarantine(w,stage)
  self.assertEqual(result["provider_records_observed"],2)
  self.assertEqual(result["eligible_records"],1)
  self.assertFalse(result["coverage_certified"])
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"UPDATE {self.schema}.bulk_provider_response_quarantine_v1"
                     " SET eligible_records=2")
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"DELETE FROM {self.schema}.bulk_provider_response_quarantine_v1")

 def test_response_finite_reservation_and_monotone_continuation_hold(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  row=self.synthetic_stage()["eligible_bars"][0]
  another={**row,"timestamp_utc":"2026-09-02T13:31:00Z",
           "record_sha256":"5"*64}
  for stage in (
   self.synthetic_stage(provider_records_observed=6,eligible_records=6,
                        eligible_bars=[row]*6),
   self.synthetic_stage(next_page_required=True),
   self.synthetic_stage(eligible_records=2,provider_records_observed=2,
                        eligible_bars=[another,row]),
   self.synthetic_stage(eligible_records=2,provider_records_observed=2,
                        eligible_bars=[row,row]),
  ):
   with self.subTest(stage=stage),self.assertRaises(self.pg.Error):
    self.quarantine(w,stage)
  valid=self.synthetic_stage(
   next_page_required=True,continuation_token_sha256="3"*64)
  result=self.quarantine(w,valid)
  self.assertEqual(result["eligible_records"],1)
  self.assertIsNone(self.sql("bulk_provider_quarantine_readback_v1",w["work_key"],1))
  with self.assertRaises(self.pg.Error):
   self.quarantine(w,self.synthetic_stage(
    previous_continuation_token_sha256="3"*64),page=1)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_response_quarantine_v1"
  ).fetchone()[0],1)

 def test_response_stage_is_not_public_or_general_transport_grant(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  for fn in ("bulk_provider_quarantine_response_v1",
             "bulk_provider_quarantine_readback_v1"):
   n=self.conn.execute("""
    SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    CROSS JOIN LATERAL aclexplode(p.proacl) x
    WHERE n.nspname=%s AND p.proname=%s
    AND x.grantee=0 AND x.privilege_type='EXECUTE'
   """,(self.schema,fn)).fetchone()[0]
   self.assertEqual(n,0)
  self.assertTrue(self.conn.execute("""
    SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n
    ON n.oid=c.relnamespace WHERE n.nspname=%s
    AND c.relname='bulk_provider_response_quarantine_v1'
   """,(self.schema,)).fetchone()[0])
  self.assertIsNone(self.sql("bulk_provider_quarantine_readback_v1",w["work_key"],0))



 def test_inclusive_end_records_count_against_all_page_budgets(self):
  # One boundary observation is excluded from output but still consumed at
  # the remote provider; it must not be available for another request.
  self.reserve(records=10,requests=2)
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  self.quarantine(w,self.synthetic_stage(
   provider_records_observed=2,eligible_records=1,
   inclusive_end_records_excluded=1,
   next_page_required=True,continuation_token_sha256="3"*64))
  # Disposable generic receipt is a test fixture only. It MUST NOT be used
  # for live provider authentication, production provenance or bulk admission.
  self.sql("bulk_commit_page_v1",w["work_key"],"synthetic-owner",
   w["claim_fence"],0,"f"*64,"d"*64,1,1)
  self.add_request_review(page=1,limit=9,request="8"*64)
  # Old behavior allowed 1 eligible+9 new = 10, although source consumed
  # 2+9 = 11 > immutable record budget. Deny before provider submission.
  with self.assertRaises(self.pg.Error):
   self.precall(w,page=1,limit=9,request="8"*64)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_precall_v1").fetchone()[0],1)
  self.assertEqual(self.conn.execute(
   f"SELECT requests_committed,records_committed FROM {self.schema}.bulk_work_v1"
   " WHERE work_key=%s",(w["work_key"],)).fetchone(),(1,1))

 def test_terminal_provider_page_cannot_issue_another_request(self):
  self.reserve(records=10,requests=2)
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  self.quarantine(w)  # terminal page: next_page_required=false
  self.sql("bulk_commit_page_v1",w["work_key"],"synthetic-owner",
   w["claim_fence"],0,"f"*64,"d"*64,1,1)
  self.add_request_review(page=1,limit=3,request="8"*64)
  with self.assertRaises(self.pg.Error):
   self.precall(w,page=1,limit=3,request="8"*64)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_precall_v1").fetchone()[0],1)


 def transport_proof(self,w,*,request="9"*64,source="f"*64,
                     bars_sha=None,provider_receipt="4"*64):
  if bars_sha is None:
   bars_sha=self.conn.execute(f"""
    SELECT eligible_bars_sha256
    FROM {self.schema}.bulk_provider_response_quarantine_v1
    WHERE work_key=%s AND page_no=0
   """,(w["work_key"],)).fetchone()[0]
  self.conn.execute(f"""
   INSERT INTO {self.schema}.bulk_provider_transport_proof_v1(
    work_key,page_no,request_sha256,source_page_sha256,eligible_bars_sha256,
    provider_https_receipt_sha256,origin)
   VALUES (%s,0,%s,%s,%s,%s,'ALPACA_STOCK_BARS_1MIN_SIP_RAW')
  """,(w["work_key"],request,source,bars_sha,provider_receipt))

 def provider_atomic(self,w,*,owner="synthetic-owner",fence=None,page=0):
  return self.sql("bulk_atomic_provider_page_v1",w["work_key"],owner,
   fence if fence is not None else w["claim_fence"],page)

 def test_atomic_provider_page_requires_separate_exact_provenance(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  self.quarantine(w)
  with self.assertRaises(self.pg.Error):self.provider_atomic(w)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_output_v1").fetchone()[0],0)
  self.transport_proof(w)
  result=self.provider_atomic(w)
  self.assertEqual(result["status"],
   "ATOMically_COMMITTED_PENDING_INDEPENDENT_TRANSPORT_AND_SOURCE_ACCEPTANCE")
  self.assertEqual(result["eligible_records_committed"],1)
  self.assertFalse(result["coverage_certified"])
  self.assertFalse(result["source_authenticity_independently_certified"])
  snapshot=self.sql("bulk_provider_atomic_readback_v1",w["work_key"],0)
  self.assertTrue(snapshot["consistent"])
  self.assertEqual(snapshot["provider_records_observed"],1)
  self.assertEqual((snapshot["actual_output_records"],snapshot["records_committed"]),(1,1))
  self.assertEqual(self.conn.execute(
   f"SELECT requests_committed,records_committed,last_page FROM {self.schema}.bulk_work_v1"
   " WHERE work_key=%s",(w["work_key"],)).fetchone(),(1,1,0))
  with self.assertRaises(self.pg.Error):self.provider_atomic(w)
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"UPDATE {self.schema}.bulk_provider_output_v1 SET ordinal=2")
  with self.assertRaises(self.pg.Error):
   self.conn.execute(f"DELETE FROM {self.schema}.bulk_provider_transport_proof_v1")
  self.assertTrue(self.sql("bulk_provider_atomic_readback_v1",w["work_key"],0)["consistent"])

 def test_atomic_provider_mismatched_transport_proof_never_commits(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  self.quarantine(w)
  self.transport_proof(w,source="8"*64)
  with self.assertRaises(self.pg.Error):self.provider_atomic(w)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_output_v1").fetchone()[0],0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],0)
  self.assertIsNone(self.sql("bulk_provider_atomic_readback_v1",w["work_key"],0))

 def test_atomic_provider_rejects_stale_owner_and_user_stop(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  self.quarantine(w)
  self.transport_proof(w)
  for kw in ({"owner":"impostor"},{"fence":w["claim_fence"]+1},{"page":1}):
   with self.subTest(kw=kw),self.assertRaises(self.pg.Error):
    self.provider_atomic(w,**kw)
  self.sql("bulk_stop_v1",MANIFEST,"explicit synthetic user stop")
  with self.assertRaises(self.pg.Error):self.provider_atomic(w)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_receipt_v1").fetchone()[0],0)

 def test_atomic_provider_zero_eligible_still_debits_real_request(self):
  self.reserve()
  self.review(provider=True)
  w=self.claim()
  self.precall(w)
  self.quarantine(w,self.synthetic_stage(
   provider_records_observed=1,eligible_records=0,
   inclusive_end_records_excluded=1,eligible_bars=[]))
  self.transport_proof(w)
  result=self.provider_atomic(w)
  self.assertEqual(result["eligible_records_committed"],0)
  self.assertEqual(result["provider_records_consumed"],1)
  snapshot=self.sql("bulk_provider_atomic_readback_v1",w["work_key"],0)
  self.assertTrue(snapshot["consistent"])
  self.assertEqual(snapshot["records_committed"],0)
  self.assertEqual(snapshot["requests_committed"],1)
  self.assertFalse(snapshot["coverage_certified"])
  with self.assertRaises(self.pg.Error):
   self.sql("bulk_verify_v1",w["work_key"],"synthetic-owner",w["claim_fence"],"1"*64)

 def test_atomic_provider_schema_private_and_no_generic_transport_grant(self):
  for table in ("bulk_provider_transport_proof_v1","bulk_provider_output_v1"):
   self.assertTrue(self.conn.execute("""
    SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n
    ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s
   """,(self.schema,table)).fetchone()[0])
  for fn in ("bulk_atomic_provider_page_v1","bulk_provider_atomic_readback_v1"):
   num=self.conn.execute("""
    SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    CROSS JOIN LATERAL aclexplode(p.proacl) x
    WHERE n.nspname=%s AND p.proname=%s
      AND x.grantee=0 AND x.privilege_type='EXECUTE'
   """,(self.schema,fn)).fetchone()[0]
   self.assertEqual(num,0)
  self.assertEqual(self.conn.execute(
   f"SELECT count(*) FROM {self.schema}.bulk_provider_transport_proof_v1").fetchone()[0],0)



if __name__=="__main__":unittest.main()
