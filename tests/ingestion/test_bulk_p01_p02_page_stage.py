"""Synthetic-only provider page-stage security/accounting regression tests.

No live provider request, licensed market record, production SQL, reviewer
claim, genuine user JWT, hosted failover proof or deployment in this suite.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import unittest

from astra_ingestion.bulk_p01_p02_alpaca_request import (
    CONTRACTS, plan_september_alpaca_sip,
)
from astra_ingestion.bulk_p01_p02_alpaca_response import inspect_sip_response
from astra_ingestion.bulk_p01_p02_page_stage import build_sip_page_stage_candidate
from astra_ingestion.bulk_scope import ScopeError

SHA = "a" * 64
WORK = "astra-bulk-v1-" + "b" * 64
RECEIPT = "c" * 64
WHEN = "2026-10-30T00:10:00Z"


def plan():
    return plan_september_alpaca_sip(
        "P01", instrument_key=10, dated_symbol="AAPL",
        session_day="2026-09-02",
        session_start_utc="2026-09-02T13:30:00Z",
        session_end_utc="2026-09-02T20:00:00Z",
        original_job_deadline="2026-11-01T00:00:00Z",
        manifest_sha256=SHA, contract_sha256=CONTRACTS["P01"],
        identity_receipt_sha256=SHA, calendar_receipt_sha256=SHA,
        entitlement_receipt_sha256=SHA,
        reserved_request_count=1, reserved_record_count=900,
    )


def bar(t="2026-09-02T13:30:00Z", *, volume=100):
    return dict(t=t, o=10.1, h=10.5, l=10.0, c=10.2,
                v=volume, n=5, vw=10.3)


def response(rows=None, token=None):
    return {"bars": {"AAPL": rows if rows is not None else [bar()]},
            "next_page_token": token}


def claim(**changes):
    row = dict(
        work_key=WORK, claim_owner="restricted-producer", claim_fence=1,
        last_page=-1, manifest_sha256=SHA, family="P01",
        mode="provider_acquisition", status="claimed", stopped=False,
        source_receipt_sha256=RECEIPT, attempts=1,
        original_deadline="2026-11-01T00:00:00Z",
        claim_until="2026-10-30T00:40:00Z",
        max_requests=3, requests_committed=0,
        max_records=999, records_committed=0,
    )
    row.update(changes)
    return row


def stage(c=None, data=None, **kwargs):
    return build_sip_page_stage_candidate(
        plan(), response() if data is None else data,
        claim() if c is None else c,
        received_at_utc=WHEN, **kwargs)


class ProviderPageStageTests(unittest.TestCase):
    def test_candidate_is_deterministic_immutable_and_never_authority(self):
        first = stage()
        second = stage()
        self.assertEqual(first, second)
        self.assertEqual(first.page_no, 0)
        self.assertEqual(first.eligible_records, 1)
        self.assertEqual(first.provider_records_observed, 1)
        self.assertEqual(first.request_increment, 1)
        self.assertEqual(first.request_total_after_candidate, 1)
        self.assertEqual(first.provider_records_total_after_candidate, 1)
        self.assertEqual(len(first.stage_candidate_sha256), 64)
        self.assertFalse(first.worker_admission_authorized)
        self.assertFalse(first.provider_submission_authorized)
        self.assertFalse(first.durable_commit_verified)
        self.assertFalse(first.coverage_certified)
        self.assertNotIn("AUTHORIZED", first.status.replace("NOT_AUTHORIZED", ""))
        with self.assertRaises(AttributeError):
            first.eligible_bars[0].volume = 111

    def test_provider_inclusive_end_counts_against_budget_not_eligible_rows(self):
        rows = [bar("2026-09-02T19:59:00Z"),
                bar("2026-09-02T20:00:00Z")]
        item = stage(c=claim(max_records=2), data=response(rows))
        self.assertEqual(item.eligible_records, 1)
        self.assertEqual(item.provider_records_observed, 2)
        self.assertEqual(item.inclusive_end_records_excluded, 1)
        self.assertEqual(item.provider_records_total_after_candidate, 2)
        self.assertFalse(item.coverage_certified)
        with self.assertRaises(ScopeError):
            stage(c=claim(max_records=1), data=response(rows))
        changed = stage(c=claim(max_records=2), data=response([
            bar("2026-09-02T19:59:00Z"),
            bar("2026-09-02T20:00:00Z", volume=101)]))
        self.assertNotEqual(item.stage_candidate_sha256,
                            changed.stage_candidate_sha256)

    def test_immutable_source_receipt_and_family_binding(self):
        with self.assertRaises(ScopeError):
            stage(c=claim(source_receipt_sha256="not-a-hash"))
        with self.assertRaises(ScopeError):
            stage(c=claim(manifest_sha256="d" * 64))
        with self.assertRaises(ScopeError):
            stage(c=claim(family="P02"))
        with self.assertRaises(ScopeError):
            stage(c=claim(mode="retained_source_reuse"))
        item = stage(c=claim(source_receipt_sha256="d" * 64))
        self.assertNotEqual(item.stage_candidate_sha256,
                            stage().stage_candidate_sha256)

    def test_expired_claim_original_deadline_and_stop_fence_rejected(self):
        for change in (
            {"status": "verified"}, {"stopped": True},
            {"claim_until": WHEN}, {"original_deadline": WHEN},
            {"original_deadline": "2026-12-01T00:00:00Z"},
            {"claim_fence": 0}, {"attempts": 3},
            {"claim_owner": "unsafe owner"}, {"work_key": "wrong"},
        ):
            with self.subTest(change=change), self.assertRaises(ScopeError):
                stage(c=claim(**change))

    def test_all_cumulative_counters_must_be_finite_and_monotonic(self):
        for change in (
            {"requests_committed": 3}, {"max_requests": 0},
            {"max_requests": 201}, {"requests_committed": True},
            {"records_committed": True}, {"max_records": -1},
            {"records_committed": 999}, {"max_records": 0},
            {"last_page": 0}, {"last_page": True},
        ):
            with self.subTest(change=change), self.assertRaises(ScopeError):
                stage(c=claim(**change))

    def test_continuation_requires_exact_prior_committed_source_receipt(self):
        p = plan()
        prev = inspect_sip_response(
            p, response(token="QUJDRA=="), page_no=0)
        receipt = {
            "work_key": WORK, "page_no": 0,
            "source_sha256": prev.page_sha256, "consistent": True,
        }
        c = claim(last_page=0, requests_committed=1, records_committed=1)
        item = stage(c=c, data=response([bar("2026-09-02T13:31:00Z")]),
                     previous=prev, previous_receipt=receipt)
        self.assertEqual(item.page_no, 1)
        self.assertEqual(item.request_total_after_candidate, 2)
        self.assertEqual(item.provider_records_total_after_candidate, 2)
        self.assertFalse(item.next_page_required)
        for mutated in (
            {**receipt, "source_sha256": "d" * 64},
            {**receipt, "consistent": False},
            {**receipt, "page_no": 1},
        ):
            with self.subTest(mutated=mutated), self.assertRaises(ScopeError):
                stage(c=c, data=response([bar("2026-09-02T13:31:00Z")]),
                      previous=prev, previous_receipt=mutated)
        with self.assertRaises(ScopeError):
            stage(c=c, data=response([bar("2026-09-02T13:31:00Z")]),
                  previous=prev, previous_receipt=None)
        with self.assertRaises(ScopeError):
            stage(c=c, data=response([bar("2026-09-02T13:30:00Z")]),
                  previous=prev, previous_receipt=receipt)

    def test_nonadvancing_continuation_empty_page_rejected(self):
        with self.assertRaises(ScopeError):
            stage(data=response(rows=[], token="QUJDRA=="))
        no_token = inspect_sip_response(plan(), response(), page_no=0)
        c = claim(last_page=0, requests_committed=1, records_committed=1)
        with self.assertRaises(ScopeError):
            stage(c=c, data=response([bar("2026-09-02T13:31:00Z")]),
                  previous=no_token,
                  previous_receipt={"work_key": WORK, "page_no": 0,
                                    "source_sha256": no_token.page_sha256,
                                    "consistent": True})

    def test_no_source_authentication_or_db_commit_can_be_claimed(self):
        observed = stage(data=response([]))
        self.assertEqual(observed.eligible_records, 0)
        self.assertFalse(observed.coverage_certified)
        self.assertFalse(observed.provider_submission_authorized)
        self.assertFalse(observed.durable_commit_verified)
        self.assertEqual(observed.status,
                         "CANDIDATE_UNAUTHENTICATED_NOT_SQL_STAGED_NOT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
