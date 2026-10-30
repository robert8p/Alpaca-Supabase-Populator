"""Provider-free offline pre-call/quarantine bridge regressions.

Fabricated OHLC only; no real provider/network, JWT, SQL, worker execution,
licenced records, live review or source population is authenticated here.
"""
from __future__ import annotations
from dataclasses import replace
import unittest

from astra_ingestion.bulk_p01_p02_alpaca_request import CONTRACTS, plan_september_alpaca_sip
from astra_ingestion.bulk_p01_p02_alpaca_response import inspect_sip_response
from astra_ingestion.bulk_provider_precall import provider_request_sha256
from astra_ingestion.bulk_provider_quarantine_bridge import (
    prepare_provider_quarantine_envelope, check_quarantine_summary)
from astra_ingestion.bulk_scope import ScopeError

SHA="a"*64
WORK="astra-bulk-v1-"+"b"*64
DEADLINE="2026-11-01T00:00:00Z"
NOW="2026-10-30T02:10:00Z"

def plan():
    return plan_september_alpaca_sip(
        "P01",instrument_key=100,dated_symbol="AAPL",
        session_day="2026-09-02",session_start_utc="2026-09-02T13:30:00Z",
        session_end_utc="2026-09-02T20:00:00Z",
        original_job_deadline=DEADLINE,manifest_sha256=SHA,
        contract_sha256=CONTRACTS["P01"],
        identity_receipt_sha256=SHA,calendar_receipt_sha256=SHA,
        entitlement_receipt_sha256=SHA,
        reserved_request_count=1,reserved_record_count=900)

def claim(**changes):
    c=dict(work_key=WORK,claim_owner="synthetic-restricted-worker",
      claim_fence=3,last_page=-1,manifest_sha256=SHA,family="P01",
      mode="provider_acquisition",status="claimed",stopped=False,
      source_receipt_sha256="c"*64,attempts=1,original_deadline=DEADLINE,
      claim_until="2026-10-30T02:30:00Z",
      max_requests=2,requests_committed=0,
      max_records=1800,records_committed=0)
    c.update(changes)
    return c

def ticket(p=None,c=None,**changes):
    p=p or plan()
    c=c or claim()
    t=dict(status="RESERVED_NO_PROVIDER_TRANSPORT_GRANT",
      work_key=c["work_key"],page_no=c["last_page"]+1,
      manifest_sha256=SHA,family="P01",claim_fence=c["claim_fence"],
      request_sha256=provider_request_sha256(p),
      records_reserved=900,original_deadline="2026-11-01T00:00:00+00:00",
      provider_submission_authorized=False)
    t.update(changes)
    return t

def bar(stamp="2026-09-02T13:30:00Z"):
    return dict(t=stamp,o=10.1,h=10.5,l=10.0,c=10.2,
                v=100,n=5,vw=10.3)

def response(bars=None,token=None):
    return {"bars":{"AAPL": [bar()] if bars is None else bars},
            "next_page_token":token}

def stage(p=None,c=None,t=None,raw=None,**kwargs):
    p=p or plan()
    c=c or claim()
    t=t or ticket(p,c)
    return prepare_provider_quarantine_envelope(
        p,response() if raw is None else raw,c,t,received_at_utc=NOW,**kwargs)

class QuarantineBridgeTests(unittest.TestCase):
    def test_canonical_private_payload_never_confers_transport_or_commit(self):
        x=stage()
        self.assertEqual((x.work_key,x.page_no,x.fence),(WORK,0,3))
        self.assertEqual((x.eligible_records,x.provider_records_observed),(1,1))
        self.assertFalse(x.transport_authorized)
        self.assertFalse(x.bulk_output_committed)
        self.assertFalse(x.coverage_certified)
        payload=x.sql_stage_payload()
        self.assertEqual(set(payload),{
          "source_page_sha256","stage_candidate_sha256",
          "provider_records_observed","eligible_records",
          "inclusive_end_records_excluded","eligible_bars",
          "next_page_required","continuation_token_sha256",
          "previous_continuation_token_sha256"})
        self.assertEqual(payload["eligible_bars"][0]["timestamp_utc"],
                         "2026-09-02T13:30:00Z")
        self.assertEqual(payload["eligible_bars"][0]["record_sha256"].__len__(),64)
        payload["eligible_bars"][0]["open"]="999999"
        self.assertEqual(x.sql_stage_payload()["eligible_bars"][0]["open"],"10.1")
        self.assertNotIn("10.1",repr(x))
        self.assertEqual(x,stage())

    def test_inclusive_boundary_does_not_credit_eligible_rows(self):
        x=stage(raw=response([bar("2026-09-02T19:59:00Z"),
                              bar("2026-09-02T20:00:00Z")]))
        p=x.sql_stage_payload()
        self.assertEqual((p["provider_records_observed"],
                          p["eligible_records"],
                          p["inclusive_end_records_excluded"]),(2,1,1))
        self.assertEqual(len(p["eligible_bars"]),1)
        self.assertFalse(x.coverage_certified)

    def test_unverified_ticket_or_claim_cannot_be_promoted(self):
        cases=(
           {"c":claim(claim_fence=4)},
           {"c":claim(stopped=True)},
           {"c":claim(claim_until="2026-10-30T02:01:00Z")},
           {"c":claim(attempts=3)},
           {"c":claim(max_records=0)},
           {"t":ticket(provider_submission_authorized=True)},
           {"t":ticket(request_sha256="f"*64)},
           {"t":ticket(records_reserved=899)},
           {"t":ticket(status="AUTHORIZED")},
           {"t":ticket(extra_privilege="admin")},
        )
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ScopeError):
                stage(**case)

    def test_unmodified_request_and_budget_bound_raw_source(self):
        p=plan()
        altered=replace(p,reserved_record_count=899)
        with self.assertRaises(ScopeError):
            stage(p=altered,t=ticket(p))
        with self.assertRaises(ScopeError):
            stage(c=claim(max_records=1),
                  raw=response([bar("2026-09-02T13:30:00Z"),
                                bar("2026-09-02T13:31:00Z")]))
        with self.assertRaises(ScopeError):
            stage(raw=response([bar("2026-09-02T13:30:00Z"),
                                bar("2026-09-02T13:30:00Z")]))

    def test_page_chains_only_from_consistent_previous_receipt(self):
        p=plan()
        prior=inspect_sip_response(p,response(token="QUJDRA=="))
        previous_receipt=dict(work_key=WORK,page_no=0,
                              source_sha256=prior.page_sha256,consistent=True)
        c=claim(last_page=0,requests_committed=1,records_committed=1)
        x=stage(p=p,c=c,t=ticket(p,c),
                raw=response([bar("2026-09-02T13:31:00Z")]),
                previous=prior,previous_receipt=previous_receipt)
        self.assertEqual(x.page_no,1)
        self.assertEqual(len(x.sql_stage_payload()["previous_continuation_token_sha256"]),64)
        with self.assertRaises(ScopeError):
            stage(p=p,c=c,t=ticket(p,c),
                  raw=response([bar("2026-09-02T13:31:00Z")]),
                  previous=prior,
                  previous_receipt={**previous_receipt,"consistent":False})

    def test_readback_only_checks_untrusted_digests_not_authentication(self):
        x=stage()
        r=dict(status="QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED",
            work_key=x.work_key,page_no=x.page_no,
            request_sha256=x.request_sha256,
            source_page_sha256=x.source_page_sha256,
            stage_candidate_sha256=x.stage_candidate_sha256,
            eligible_records=x.eligible_records,
            provider_records_observed=x.provider_records_observed,
            bulk_output_committed=False,consistent=True,
            eligible_bars_sha256="a"*64)
        self.assertTrue(check_quarantine_summary(x,r))
        for bad in ({"consistent":False},{"bulk_output_committed":True},
                    {"page_no":True},{"eligible_records":True},
                    {"eligible_bars_sha256":"not-a-hash"},
                    {"request_sha256":"b"*64},
                    {"status":"BULK_ACCEPTED"}):
            with self.subTest(bad=bad),self.assertRaises(ScopeError):
                check_quarantine_summary(x,{**r,**bad})

if __name__=="__main__":
    unittest.main()
