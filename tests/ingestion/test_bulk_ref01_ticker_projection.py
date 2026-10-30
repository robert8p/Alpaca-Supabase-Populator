"""REF01 original-source cohort ticker candidates: synthetic, never accepted identity."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone, timedelta
import unittest

from astra_ingestion.bulk_ref01_ticker_projection import (
    plan_ticker_projection, inspect_ticker_projection_page,
)
from astra_ingestion.bulk_scope import ScopeError

SRC = "d" * 64


def row(key="company:001", matches=1, **change):
    r = {
        "company_key": key, "accepted_company_receipt_sha256": "a" * 64,
        "ticker": "TEST", "matching_source_rows": matches,
        "instrument_key": 101 if matches == 1 else None,
        "alpaca_asset_id": "00000000-0000-0000-0000-000000000001" if matches == 1 else None,
        "classification_observed_at": datetime(2026, 10, 29, tzinfo=timezone.utc) if matches == 1 else None,
    }
    r.update(change)
    return r


class Ref01TickerProjectionTests(unittest.TestCase):
    def test_exact_original_sources_and_bounded_keyset_not_arbitrary_sql(self):
        p = plan_ticker_projection(SRC, after_company_key="company:001", page_limit=5)
        self.assertEqual(p.params, (
            "top3000-augsep2026-retained-scope-v1", "company:001", "company:001", 5))
        self.assertIn("astra_ingestion_v1.bulk_scope_evidence_v1", p.sql)
        self.assertIn("reference.alpaca_fixed_window_instruments_v1", p.sql)
        self.assertIn("ORDER BY evidence_key LIMIT %s", p.sql)
        self.assertIn("count(*)::integer", p.sql)
        self.assertNotIn("SELECT *", p.sql)
        self.assertNotIn("raw_payload", p.sql)
        self.assertIn("NOT_IDENTITY_CERTIFICATION", p.status)
        for params in (
            dict(source_snapshot_sha256="wrong"),
            dict(source_snapshot_sha256=SRC, after_company_key="';DROP TABLE"),
            dict(source_snapshot_sha256=SRC, page_limit=129),
            dict(source_snapshot_sha256=SRC, page_limit=True),
        ):
            with self.subTest(params=params), self.assertRaises(ScopeError):
                plan_ticker_projection(**params)

    def test_match_candidate_even_postdated_source_never_certifies_history(self):
        p = plan_ticker_projection(SRC)
        result = inspect_ticker_projection_page(p, [row()])
        self.assertEqual(result.source_rows, 1)
        self.assertEqual(result.exact_one_match, 1)
        self.assertEqual(result.unmatched, 0)
        self.assertEqual(result.ambiguous, 0)
        self.assertEqual(result.next_company_key, "company:001")
        self.assertFalse(result.coverage_certified)
        self.assertFalse(result.worker_admission_authorized)
        self.assertFalse(result.candidates[0].identity_certified)
        self.assertIn("UNVERIFIED", result.candidates[0].status)
        self.assertEqual(len(result.candidates[0].evidence_sha256), 64)

    def test_ambiguous_source_match_never_silently_selected(self):
        p = plan_ticker_projection(SRC)
        result = inspect_ticker_projection_page(p, [
            row("company:001", matches=0),
            row("company:002", matches=2),
            row("company:003", matches=1)])
        self.assertEqual((result.exact_one_match, result.unmatched, result.ambiguous),
                         (1, 1, 1))
        self.assertIsNone(result.candidates[0].instrument_key)
        self.assertIsNone(result.candidates[1].instrument_key)
        with self.assertRaises(ScopeError):
            inspect_ticker_projection_page(p, [row(matches=2, instrument_key=200)])

    def test_source_drift_and_missing_candidate_change_receipt(self):
        p = plan_ticker_projection(SRC)
        one = inspect_ticker_projection_page(p, [row()])
        different = inspect_ticker_projection_page(p, [row(instrument_key=102)])
        different_snapshot = inspect_ticker_projection_page(
            plan_ticker_projection("e" * 64), [row()])
        self.assertNotEqual(one.page_sha256, different.page_sha256)
        self.assertNotEqual(one.page_sha256, different_snapshot.page_sha256)

    def test_pagination_is_stable_and_cannot_hide_missing_companies(self):
        p = plan_ticker_projection(SRC, after_company_key="company:001", page_limit=2)
        with self.assertRaises(ScopeError):
            inspect_ticker_projection_page(p, [row("company:001")])
        with self.assertRaises(ScopeError):
            inspect_ticker_projection_page(p, [
                row("company:003"), row("company:002")])
        with self.assertRaises(ScopeError):
            inspect_ticker_projection_page(p, [
                row("company:002"), row("company:003"), row("company:004")])
        empty = inspect_ticker_projection_page(p, [])
        self.assertEqual(empty.source_rows, 0)
        self.assertFalse(empty.coverage_certified)

    def test_missing_or_unsafe_identity_provenance_never_qualifies(self):
        p = plan_ticker_projection(SRC)
        for r in (
            row(accepted_company_receipt_sha256="bad"),
            row(company_key="company key with spaces"),
            row(ticker="test"),
            row(instrument_key=None),
            row(instrument_key=True),
            row(matching_source_rows=-1),
            row(matching_source_rows=True),
            row(classification_observed_at=datetime(2026, 8, 3)),
            row(classification_observed_at=datetime(2026, 8, 3, tzinfo=timezone(timedelta(hours=1)))),
            {**row(), "unchecked": "raw-provider-field"},
        ):
            with self.subTest(row=r), self.assertRaises(ScopeError):
                inspect_ticker_projection_page(p, [r])

    def test_caller_cannot_replace_preapproved_query_or_status(self):
        p = plan_ticker_projection(SRC)
        for forged in (replace(p, sql="SELECT 1"),
                       replace(p, params=()),
                       replace(p, status="INDEPENDENTLY_ACCEPTED"),
                       replace(p, page_limit=500)):
            with self.subTest(forged=forged.status), self.assertRaises(ScopeError):
                inspect_ticker_projection_page(forged, [row()])


if __name__ == "__main__":
    unittest.main()
