"""Synthetic REF01 listing/identity evidence tests; no live source acquisition."""
from __future__ import annotations
from copy import deepcopy
import unittest

from astra_ingestion.bulk_ref01 import compile_ref01_candidates, ROUTES
from astra_ingestion.bulk_scope import ScopeError

MEMBERS = tuple(f"co{i:04d}" for i in range(3000))


def eligible(**changes):
    row = {
        "source_route": "reference.equity_resolved_security_v5",
        "source_record_key": "e1",
        "source_sha256": "a" * 64,
        "published_at_utc": "2026-08-01T12:00:00Z",
        "eligibility_state": "ELIGIBLE",
        "company_id": MEMBERS[0],
        "issuer_id": "issuer-one",
        "security_id": "sec-one",
        "ticker_alias": "ABC",
        "listing_start": "2026-07-01",
        "listing_end": None,
        "type": "common_stock",
        "exchange": "NYSE",
        "rank_date_market_cap": 1000,
        "share_class_components": {"common": 100},
        "ADR_ratio": "NOT_APPLICABLE_EVIDENCED",
        "FX": "USD",
        "source_vintage": "2026-08-01",
    }
    row.update(changes)
    return row


class Ref01Tests(unittest.TestCase):
    def compile(self, rows, **kwargs):
        return compile_ref01_candidates(MEMBERS, rows, snapshot_sha256="b" * 64, **kwargs)

    def test_candidate_is_never_population_certification_or_worker_admission(self):
        result = self.compile([eligible()])
        self.assertEqual(result.observed_security_episode_count, 1)
        self.assertEqual(result.selected_company_count, 3000)
        self.assertEqual(len(result.candidate_unit_keys), 3001)
        self.assertEqual(len(result.company_without_candidate_episodes), 2999)
        self.assertEqual(result.held_record_count, 0)
        self.assertEqual(result.late_publication_count, 0)
        self.assertEqual(result.status, "DENOMINATOR_AND_REVIEW_UNRESOLVED")
        self.assertFalse(result.worker_admission_authorized)
        self.assertTrue(any("2026-08-01:2026-10-01" in x for x in result.candidate_unit_keys))
        self.assertEqual(self.compile([eligible()]).metadata_fingerprint_sha256,
                         result.metadata_fingerprint_sha256)

    def test_empty_source_is_not_non_applicability(self):
        result = self.compile([])
        self.assertEqual(result.observed_security_episode_count, 0)
        self.assertEqual(len(result.company_without_candidate_episodes), 3000)
        self.assertEqual(len(result.candidate_unit_keys), 3000)
        self.assertFalse(result.worker_admission_authorized)

    def test_missing_required_or_unresolved_source_is_explicit_hold(self):
        row = eligible(FX=None)
        result = self.compile([row, eligible(
            source_record_key="held",
            security_id="another",
            eligibility_state="HELD")])
        self.assertEqual(result.held_record_count, 2)
        self.assertEqual(result.observed_security_episode_count, 0)

    def test_late_published_source_never_becomes_pit_qualified(self):
        result = self.compile([eligible(published_at_utc="2026-10-29T12:00:00Z")])
        self.assertEqual(result.late_publication_count, 1)
        self.assertEqual(result.observed_security_episode_count, 1)
        self.assertFalse(result.worker_admission_authorized)

    def test_evidenced_exclusion_does_not_forge_episode(self):
        result = self.compile([eligible(eligibility_state="EXCLUDED_WITH_EVIDENCE",
                                        exclusion_evidence_sha256="c" * 64)])
        self.assertEqual(result.observed_security_episode_count, 0)
        with self.assertRaises(ScopeError):
            self.compile([eligible(eligibility_state="EXCLUDED_WITH_EVIDENCE",
                                   exclusion_evidence_sha256=None)])

    def test_duplicate_source_and_overlapping_identity_fail_closed(self):
        row = eligible()
        with self.assertRaises(ScopeError):
            self.compile([row, row])
        other = eligible(source_record_key="different",
                         company_id=MEMBERS[1],
                         source_sha256="c" * 64)
        with self.assertRaises(ScopeError):
            self.compile([row, other])

    def test_separate_nonoverlapping_listing_episodes_are_allowed(self):
        first = eligible(listing_start="2026-08-01", listing_end="2026-08-10")
        second = eligible(source_record_key="s2", listing_start="2026-08-10",
                          listing_end="2026-09-20", ticker_alias="DEF")
        result = self.compile([first, second])
        self.assertEqual(result.observed_security_episode_count, 2)

    def test_date_and_window_validation(self):
        with self.assertRaises(ScopeError):
            self.compile([eligible(listing_start="2026-09-30", listing_end="2026-09-01")])
        with self.assertRaises(ScopeError):
            self.compile([eligible(listing_start="2026-08-99")])
        result = self.compile([eligible(listing_start="2026-10-02", listing_end="2026-11-01")])
        self.assertEqual(result.observed_security_episode_count, 0)

    def test_source_route_membership_and_hash_pin(self):
        self.assertEqual(len(ROUTES), 5)
        for kwargs in [
            {"source_route": "market_reference.*"},
            {"source_route": "reference.unapproved"},
            {"source_sha256": "not-hash"},
            {"company_id": "not-selected"},
            {"published_at_utc": "2026-08-01"},
        ]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ScopeError):
                    self.compile([eligible(**kwargs)])

    def test_selected_cohort_and_snapshot_are_pinned(self):
        with self.assertRaises(ScopeError):
            compile_ref01_candidates(MEMBERS[:-1], [], snapshot_sha256="b" * 64)
        with self.assertRaises(ScopeError):
            compile_ref01_candidates(MEMBERS, [], snapshot_sha256="unverified")


if __name__ == "__main__":
    unittest.main()
