"""REF01 source route paging and PIT guard tests (synthetic; no live source proof)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID
import unittest

from astra_ingestion.bulk_ref01 import ROUTES
from astra_ingestion.bulk_ref01_route_probe import (
    MAX_PAGE, SPECS, WINDOW_END_EXCLUSIVE, WINDOW_START,
    inspect_route_page, plan_route_page,
)
from astra_ingestion.bulk_scope import ScopeError

MASSIVE = "reference.massive_security_master_observation_v1"
ALPACA = "reference.alpaca_fixed_window_instruments_v1"
CLASSIFICATION = "market_reference.instrument_classification"
FIGI = "BBG000000001"
ALT = "BBG000000002"


def massive_row(**changes):
    row = {field: None for field in SPECS[MASSIVE].selected_fields}
    row.update({
        "observation_id": 10,
        "composite_figi": FIGI,
        "requested_as_of": date(2026, 8, 3),
        "research_available_at": datetime(2026, 8, 3, 19, 0, tzinfo=timezone.utc),
        "row_hash": "a" * 64,
    })
    row.update(changes)
    return row


class Ref01RouteProbeTests(unittest.TestCase):
    def test_only_five_pinned_source_routes_and_max_page(self):
        self.assertEqual(frozenset(SPECS), ROUTES)
        self.assertEqual(MAX_PAGE, 128)
        for candidate in ("public.anything", "reference.massive_security_master_observation_v1;DELETE",
                          "reference.massive_security_master_observation_v1 WHERE true",
                          "reference.*"):
            with self.subTest(candidate=candidate), self.assertRaises(ScopeError):
                plan_route_page(candidate)
        for bad in (0, 129, -1, 1.5, True):
            with self.subTest(limit=bad), self.assertRaises(ScopeError):
                plan_route_page(ALPACA, limit=bad)

    def test_massive_is_bounded_to_figi_cohort_and_window_without_any_raw_payload(self):
        plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,), limit=2)
        self.assertEqual(plan.route, MASSIVE)
        self.assertIn("requested_as_of >= %s AND requested_as_of < %s", plan.query)
        self.assertIn("composite_figi = ANY(%s) OR share_class_figi = ANY(%s)", plan.query)
        self.assertIn("ORDER BY observation_id LIMIT %s", plan.query)
        self.assertNotIn("raw_payload", plan.query)
        self.assertNotIn("SELECT *", plan.query)
        self.assertEqual(plan.params, ([FIGI], [FIGI], WINDOW_START, WINDOW_END_EXCLUSIVE, 2))
        next_page = plan_route_page(MASSIVE, after=(10,), anchor_figis=(FIGI,), limit=2)
        self.assertIn("(observation_id) > (%s)", next_page.query)
        self.assertEqual(next_page.params[-2:], (10, 2))
        self.assertNotIn(FIGI, plan.query)
        self.assertEqual(plan.status, "READ_ONLY_SOURCE_PROBE_NOT_ADMISSION")

    def test_bad_figi_or_cursor_is_rejected_without_unsafe_query(self):
        for anchors in ((), (FIGI, FIGI), (ALT, FIGI), ("' OR true --",), ("",),
                        tuple(FIGI for _ in range(3001))):
            with self.subTest(anchors=anchors[:3]), self.assertRaises(ScopeError):
                plan_route_page(MASSIVE, anchor_figis=anchors)
        for cursor in (("ten",), (-1,), (1, 2), [1], (True,)):
            with self.subTest(cursor=cursor), self.assertRaises(ScopeError):
                plan_route_page(MASSIVE, anchor_figis=(FIGI,), after=cursor)
        with self.assertRaises(ScopeError):
            plan_route_page(ALPACA, after=(123,))

    def test_classification_composite_unique_keyset_order_is_stable(self):
        plan = plan_route_page(CLASSIFICATION, after=("alpaca", 42, "c" * 64), limit=6)
        self.assertIn("ORDER BY provider,instrument_key,source_row_hash LIMIT %s", plan.query)
        self.assertIn("(provider,instrument_key,source_row_hash) > (%s,%s,%s)", plan.query)
        self.assertEqual(plan.params, ("alpaca", 42, "c" * 64, 6))
        self.assertNotIn("OFFSET", plan.query)

    def test_massive_pit_qualified_page_is_still_not_source_closure(self):
        plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,), limit=2)
        result = inspect_route_page(plan, [massive_row()],
                                    source_snapshot_sha256="b" * 64)
        self.assertEqual(result.page_rows, 1)
        self.assertEqual(result.actual_window_observations, 1)
        self.assertEqual(result.available_by_rank_date, 1)
        self.assertEqual(result.late_or_unknown_publication, 0)
        self.assertEqual(result.next_cursor, (10,))
        self.assertEqual(len(result.page_sha256), 64)
        self.assertFalse(result.worker_admission_authorized)
        self.assertIn("NOT_POPULATION_CLOSURE", result.status)
        changed = inspect_route_page(plan, [massive_row()],
                                     source_snapshot_sha256="c" * 64)
        self.assertNotEqual(result.page_sha256, changed.page_sha256)

    def test_late_or_unknown_research_publication_is_not_pit(self):
        plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,), limit=1)
        for raw in (None, "2026-10-29T10:00:00Z", "not-a-date"):
            with self.subTest(raw=raw):
                result = inspect_route_page(
                    plan, [massive_row(research_available_at=raw)],
                    source_snapshot_sha256="b" * 64,
                )
                self.assertEqual(result.available_by_rank_date, 0)
                self.assertEqual(result.late_or_unknown_publication, 1)

    def test_out_of_window_or_foreign_cohort_row_fails_closed(self):
        plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,))
        for row in (massive_row(requested_as_of="2026-07-31"),
                    massive_row(requested_as_of="2026-10-01"),
                    massive_row(composite_figi=ALT),
                    massive_row(row_hash="invalid")):
            with self.subTest(row=row.get("observation_id")), self.assertRaises(ScopeError):
                inspect_route_page(plan, [row], source_snapshot_sha256="b" * 64)

    def test_duplicate_nonadvancing_and_malformed_source_key_refused(self):
        plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,))
        for rows in ([massive_row(), massive_row()], [massive_row(observation_id=-2)],
                     [massive_row(observation_id=11), massive_row(observation_id=10)],
                     [massive_row(observation_id=None)], [dict(observation_id=1)]):
            with self.subTest(rows=rows), self.assertRaises(ScopeError):
                inspect_route_page(plan, rows, source_snapshot_sha256="b" * 64)
        new_plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,), after=(10,))
        with self.assertRaises(ScopeError):
            inspect_route_page(new_plan, [massive_row()],
                               source_snapshot_sha256="b" * 64)

    def test_empty_route_remains_unverified_and_not_applicable_is_not_inferred(self):
        plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,))
        result = inspect_route_page(plan, [], source_snapshot_sha256="b" * 64)
        self.assertEqual(result.page_rows, 0)
        self.assertEqual(result.actual_window_observations, 0)
        self.assertFalse(result.worker_admission_authorized)
        self.assertEqual(result.status, "OBSERVED_SOURCE_PAGE_NOT_POPULATION_CLOSURE")

    def test_other_route_ingestion_timestamp_cannot_be_publication_proof(self):
        row = {field: None for field in SPECS[ALPACA].selected_fields}
        row.update({
            "symbol": "ABC", "alpaca_asset_id": UUID(int=1),
            "instrument_key": 5,
            "classification_observed_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "provenance": {"native": ["Alpaca", "not historical listing proof"]},
        })
        plan = plan_route_page(ALPACA, after=("AAA",), limit=4)
        result = inspect_route_page(plan, [row], source_snapshot_sha256="d" * 64)
        self.assertEqual(result.available_by_rank_date, 0)
        self.assertEqual(result.actual_window_observations, 0)
        self.assertEqual(result.late_or_unknown_publication, 1)
        self.assertEqual(result.next_cursor, ("ABC",))
        self.assertFalse(result.worker_admission_authorized)

    def test_malformed_snapshot_and_cutoff(self):
        plan = plan_route_page(MASSIVE, anchor_figis=(FIGI,))
        with self.assertRaises(ScopeError):
            inspect_route_page(plan, [massive_row()], source_snapshot_sha256="unverified")
        for cutoff in ("2026-08-03", "broken", None):
            with self.subTest(cutoff=cutoff), self.assertRaises(ScopeError):
                inspect_route_page(plan, [massive_row()],
                                   source_snapshot_sha256="b" * 64,
                                   rank_date_cutoff=cutoff)


if __name__ == "__main__":
    unittest.main()
