"""Offline, no-provider regressions for the staged immutable P01/P02 ticket.

These fabricated mappings are NOT server-authenticated JWT, independent
provider entitlement, a live DB reservation or permission to submit a call.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from astra_ingestion.bulk_p01_p02_alpaca_request import CONTRACTS, plan_september_alpaca_sip
from astra_ingestion.bulk_provider_precall import (
    match_precall_candidate, provider_request_sha256,
)
from astra_ingestion.bulk_scope import ScopeError

SHA="a"*64
WORK="astra-bulk-v1-"+"b"*64
DEADLINE="2026-11-01T00:00:00Z"
NOW="2026-10-30T01:02:00Z"


def plan():
    return plan_september_alpaca_sip(
      "P01",instrument_key=100,dated_symbol="AAPL",
      session_day="2026-09-02",session_start_utc="2026-09-02T13:30:00Z",
      session_end_utc="2026-09-02T20:00:00Z",
      original_job_deadline=DEADLINE,
      manifest_sha256=SHA,contract_sha256=CONTRACTS["P01"],
      identity_receipt_sha256=SHA,calendar_receipt_sha256=SHA,
      entitlement_receipt_sha256=SHA,reserved_request_count=1,
      reserved_record_count=900)


def claim(**changes):
    c=dict(work_key=WORK,claim_owner="restricted-worker",claim_fence=2,
      last_page=-1,manifest_sha256=SHA,family="P01",
      mode="provider_acquisition",status="claimed",stopped=False,
      source_receipt_sha256="c"*64,attempts=1,original_deadline=DEADLINE,
      claim_until="2026-10-30T01:30:00+00:00")
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


class BoundProviderPrecallTests(unittest.TestCase):
    def test_matching_ticket_is_only_an_untrusted_candidate(self):
        p=plan()
        result=match_precall_candidate(p,claim(),ticket(p),now_utc=NOW)
        self.assertEqual(result.work_key,WORK)
        self.assertEqual(result.page_no,0)
        self.assertEqual(result.records_reserved,900)
        self.assertEqual(result.request_sha256,provider_request_sha256(p))
        self.assertFalse(result.provider_submission_authorized)
        self.assertFalse(result.durable_reservation_verified)
        with self.assertRaises(AttributeError):
            result.claim_fence=77

    def test_request_content_or_contract_drift_never_matches_ticket(self):
        p=plan()
        wrong=replace(p,request={**p.request,"limit":901})
        with self.assertRaises(ScopeError):
            provider_request_sha256(wrong)
        mutated=replace(p,reserved_record_count=899)
        with self.assertRaises(ScopeError):
            match_precall_candidate(mutated,claim(),ticket(p),now_utc=NOW)
        with self.assertRaises(ScopeError):
            match_precall_candidate(p,claim(),ticket(p,request_sha256="0"*64),now_utc=NOW)

    def test_claim_owner_fence_stop_attempt_and_original_deadline_protected(self):
        for change in (
           {"work_key":"bad"},{"claim_owner":"bad owner"},
           {"claim_fence":0},{"claim_fence":True},{"claim_fence":3},
           {"mode":"retained_source_reuse"},{"status":"verified"},
           {"stopped":True},{"attempts":3},{"attempts":True},
           {"original_deadline":"2026-11-02T00:00:00Z"},
           {"source_receipt_sha256":"missing"},
           {"claim_until":"2026-10-30T01:00:00Z"},
           {"manifest_sha256":"f"*64},{"family":"P02"},
        ):
            with self.subTest(change=change),self.assertRaises(ScopeError):
                match_precall_candidate(plan(),claim(**change),ticket(),now_utc=NOW)

    def test_ticket_rejects_privilege_promotion_unknown_fields_and_type_confusion(self):
        for bad in (
           {"provider_submission_authorized":True},
           {"claim_fence":True},{"page_no":False},{"records_reserved":True},
           {"status":"PROVIDER_CALL_AUTHORIZED"},{"family":"P02"},
           {"manifest_sha256":"0"*64},{"records_reserved":1000},
           {"original_deadline":"2026-11-02T00:00:00Z"},
           {"original_deadline":"2026-11-01T01:00:00+01:00"},
           {"request_sha256":"f"*64},
           {"extra_control":"admin"},
        ):
            with self.subTest(ticket=bad),self.assertRaises(ScopeError):
                match_precall_candidate(plan(),claim(),ticket(**bad),now_utc=NOW)

    def test_original_deadline_and_finite_claim_expiration(self):
        with self.assertRaises(ScopeError):
            match_precall_candidate(plan(),claim(),ticket(),
                                    now_utc=DEADLINE)
        with self.assertRaises(ScopeError):
            match_precall_candidate(plan(),claim(),ticket(),
                                    now_utc="2026-10-30T01:30:00Z")
        with self.assertRaises(ScopeError):
            match_precall_candidate(plan(),claim(),ticket(),
                                    now_utc="2026-10-30T02:00:00+01:00")

    def test_continuation_requires_next_exact_page_and_request_hash(self):
        c=claim(last_page=0)
        result=match_precall_candidate(plan(),c,ticket(c=c),now_utc=NOW)
        self.assertEqual(result.page_no,1)
        with self.assertRaises(ScopeError):
            match_precall_candidate(plan(),c,ticket(c=c,page_no=0),now_utc=NOW)


if __name__=="__main__":unittest.main()
