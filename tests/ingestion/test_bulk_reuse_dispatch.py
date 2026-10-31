"""Fail-closed synthetic tests of provider-free bulk dispatcher.

No connector, provider, production database, or implicit engineering admission.
Separate simulated verifier must release predecessor before successor is claimable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from astra_ingestion.bulk_reuse_dispatch import RetainedOnlyDispatcher, DispatchRefused
from astra_ingestion.bulk_scope import CAPTURE_KEY, RETAINED_RECEIPT_SHA256

MANIFEST = "a" * 64
OWNER = "bulk-worker-test"
NOW = datetime(2026, 10, 29, 17, 0, tzinfo=timezone.utc)


def claim(index: int, *, mode: str = "retained_source_reuse",
          deadline: datetime | None = None) -> dict:
    return {
        "manifest_sha256": MANIFEST,
        "work_key": "astra-bulk-v1-" + str(index) * 64,
        "mode": mode,
        "status": "claimed",
        "claim_owner": OWNER,
        "claim_fence": 1,
        "attempts": 1,
        "max_requests": 0,
        "requests_committed": 0,
        "max_records": 10,
        "records_committed": 0,
        "last_page": -1,
        "original_deadline": (deadline or NOW + timedelta(minutes=10)).isoformat(),
        "claim_until": (NOW + timedelta(seconds=60)).isoformat(),
    }


class SyntheticDurablePort:
    def __init__(self):
        self.gate = {
            "status": "INDEPENDENTLY_REVIEWED_RETAINED_ONLY",
            "manifest_sha256": MANIFEST,
            "capture_key": CAPTURE_KEY,
            "capture_receipt_sha256": RETAINED_RECEIPT_SHA256,
            "complete_family_count": 24,
            "independent_review_sha256": "e" * 64,
            "stopped": False,
        }
        self.work = [claim(1), claim(2)]
        self.verified = set()
        self.pending_review = set()
        self.committed = []
        self.provider_calls = 0
        self.attempts = 0

    def admission(self, manifest):
        return self.gate if manifest == MANIFEST else None

    def claim_retained(self, manifest, owner, lease_seconds):
        self.attempts += 1
        for i, work in enumerate(self.work):
            if i and self.work[i - 1]["work_key"] not in self.verified:
                continue
            if work["work_key"] not in self.pending_review and work["work_key"] not in self.verified:
                self.pending_review.add(work["work_key"])
                return work.copy()
        return None

    def commit_retained_page(self, work, page):
        record = {
            "work_key": work["work_key"],
            "page_no": page,
            "requests_committed": 0,
            "records_committed": 3,
            "source_sha256": "c" * 64,
            "output_sha256": "d" * 64,
        }
        self.committed.append(record)
        return record

    def independent_reviewer_release(self, work_key):
        # The dispatcher has no access to this capability; in production
        # reviewer evidence + restricted SQL must be independently enforced.
        if work_key not in self.pending_review:
            raise AssertionError("cannot review a work item not committed")
        self.verified.add(work_key)


class BulkReuseDispatchTests(unittest.TestCase):
    def make(self, port):
        return RetainedOnlyDispatcher(port, manifest_sha256=MANIFEST,
                                      worker_id=OWNER, lease_seconds=60)

    def test_dispatch_commits_page_then_requires_independent_review_for_successor(self):
        port = SyntheticDurablePort()
        worker = self.make(port)
        first = worker.run_bounded(max_items=5, now=NOW)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["state"], "committed_review_required")
        self.assertEqual(len(port.committed), 1)
        self.assertEqual(port.provider_calls, 0)
        self.assertEqual(worker.run_bounded(max_items=3, now=NOW), ())
        port.independent_reviewer_release(first[0]["work_key"])
        second = worker.run_bounded(max_items=5, now=NOW)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(second[0]["work_key"], first[0]["work_key"])
        self.assertEqual(len(port.committed), 2)
        self.assertEqual(port.provider_calls, 0)

    def test_incomplete_or_unreviewed_manifest_never_claims(self):
        for key, value in [
            ("status", "INDEPENDENT_REVIEW_REQUIRED"),
            ("capture_receipt_sha256", "0" * 64),
            ("complete_family_count", 23),
            ("independent_review_sha256", "non-digest"),
            ("stopped", True),
        ]:
            with self.subTest(key=key):
                port = SyntheticDurablePort()
                port.gate[key] = value
                with self.assertRaises(DispatchRefused):
                    self.make(port).run_one(now=NOW)
                self.assertEqual(port.attempts, 0)

    def test_no_programme_cutoff_but_each_job_keeps_its_original_deadline(self):
        later = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)
        port = SyntheticDurablePort()
        port.work[0]["original_deadline"] = (later + timedelta(minutes=30)).isoformat()
        port.work[0]["claim_until"] = (later + timedelta(seconds=45)).isoformat()
        done = self.make(port).run_one(now=later)
        self.assertEqual(done["state"], "committed_review_required")
        expired = SyntheticDurablePort()
        expired.work[0]["original_deadline"] = (later - timedelta(seconds=1)).isoformat()
        expired.work[0]["claim_until"] = (later + timedelta(seconds=45)).isoformat()
        with self.assertRaises(DispatchRefused):
            self.make(expired).run_one(now=later)
        self.assertEqual(expired.committed, [])

    def test_provider_job_rejected_before_materialisation(self):
        port = SyntheticDurablePort()
        port.work[0]["mode"] = "provider_acquisition"
        with self.assertRaises(DispatchRefused):
            self.make(port).run_one(now=NOW)
        self.assertEqual(port.committed, [])
        self.assertEqual(port.provider_calls, 0)

    def test_original_deadline_and_expired_lease_refuse(self):
        for field, value in [
            ("original_deadline", (NOW - timedelta(seconds=1)).isoformat()),
            ("claim_until", (NOW - timedelta(seconds=1)).isoformat()),
        ]:
            with self.subTest(field=field):
                port = SyntheticDurablePort()
                port.work[0][field] = value
                with self.assertRaises(DispatchRefused):
                    self.make(port).run_one(now=NOW)
                self.assertEqual(port.committed, [])

    def test_stale_fence_wrong_owner_and_counter_budget_refuse(self):
        for field, value in [
            ("claim_fence", 0), ("claim_owner", "previous-owner"),
            ("max_requests", 1), ("requests_committed", 1),
            ("attempts", 3), ("records_committed", 11),
            ("manifest_sha256", "f" * 64),
        ]:
            with self.subTest(field=field):
                port = SyntheticDurablePort()
                port.work[0][field] = value
                with self.assertRaises(DispatchRefused):
                    self.make(port).run_one(now=NOW)
                self.assertEqual(port.committed, [])

    def test_no_replay_after_unknown_receipt_commit(self):
        port = SyntheticDurablePort()
        original = port.commit_retained_page
        def bad_receipt(work, page):
            result = original(work, page)
            result["source_sha256"] = "malformed"
            return result
        port.commit_retained_page = bad_receipt
        with self.assertRaises(DispatchRefused):
            self.make(port).run_one(now=NOW)
        self.assertEqual(len(port.committed), 1)
        self.assertEqual(port.attempts, 1)

    def test_nonadvancing_store_claim_fails_closed(self):
        port = SyntheticDurablePort()
        port.claim_retained = lambda manifest, owner, lease: port.work[0].copy()
        with self.assertRaises(DispatchRefused):
            self.make(port).run_bounded(max_items=3, now=NOW)
        self.assertEqual(len(port.committed), 2)

    def test_bounded_parameters_are_strict(self):
        port = SyntheticDurablePort()
        for lease in (0, 181, True):
            with self.assertRaises(DispatchRefused):
                RetainedOnlyDispatcher(port, manifest_sha256=MANIFEST,
                                       worker_id=OWNER, lease_seconds=lease)
        with self.assertRaises(DispatchRefused):
            self.make(port).run_bounded(max_items=17, now=NOW)
        with self.assertRaises(DispatchRefused):
            self.make(port).run_bounded(max_items=True, now=NOW)

    def test_retained_receipt_cannot_forge_provider_usage(self):
        port = SyntheticDurablePort()
        original = port.commit_retained_page
        def provider_receipt(work, page):
            result = original(work, page)
            return {**result, "requests_committed": 1}
        port.commit_retained_page = provider_receipt
        with self.assertRaises(DispatchRefused):
            self.make(port).run_one(now=NOW)
        self.assertEqual(port.provider_calls, 0)


if __name__ == "__main__":
    unittest.main()
