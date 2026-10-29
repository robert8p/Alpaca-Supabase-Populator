"""P01/P02 original-source and September gap guards, synthetic only."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest
from uuid import UUID

from astra_ingestion.bulk_p01_p02_source_probe import (
    SOURCE, DERIVED_VIEW, FIELDS, MAX_PAGE,
    inspect_price_page, plan_price_page,
)
from astra_ingestion.bulk_scope import ScopeError

SNAPSHOT = "f" * 64
START = "2026-09-02T13:30:00Z"
END = "2026-09-02T14:00:00Z"


def plan(family="P01", **changes):
    args = {
        "instrument_keys": (10, 20),
        "start_utc": START,
        "end_utc": END,
        "source_snapshot_sha256": SNAPSHOT,
    }
    args.update(changes)
    return plan_price_page(family, **args)


def source_row(key=10, minute="2026-09-02T13:31:00Z", label="regular", **changes):
    row = dict(
        instrument_key=key,
        bar_ts=datetime.fromisoformat(minute.replace("Z", "+00:00")),
        session_label=label,
        open=10.0, high=10.2, low=9.8, close=10.1,
        volume=100, trade_count=10, vwap=10.05,
        loaded_by_job_id=UUID(int=1),
        source_loaded_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    row.update(changes)
    return row


class P01P02SourceTests(unittest.TestCase):
    def test_exact_original_route_no_sql_injection_or_source_view_promotion(self):
        x = plan()
        self.assertEqual(x.route, SOURCE)
        self.assertNotIn("SELECT *", x.query)
        self.assertIn("ORDER BY instrument_key,bar_ts LIMIT %s", x.query)
        self.assertIn("bar_ts >= %s AND bar_ts < %s", x.query)
        self.assertEqual(x.params[-1], 128)
        self.assertNotIn("10,20", x.query)
        self.assertFalse(x.worker_admission_authorized)
        mutating = x.params[0]
        mutating.append(999)
        self.assertEqual(x.params[0], [10, 20])  # fresh array on every access
        with self.assertRaises(ScopeError):
            plan(route=DERIVED_VIEW)
        with self.assertRaises(ScopeError):
            plan(route="public.anything")
        with self.assertRaises(ScopeError):
            plan("D06")

    def test_date_pruning_keyset_parameters_are_bounded(self):
        x = plan(limit=2, after=(10, "2026-09-02T13:31:00Z"))
        self.assertIn("(instrument_key,bar_ts) > (%s,%s)", x.query)
        self.assertEqual(x.params[-3], 10)
        self.assertEqual(x.params[-1], 2)
        self.assertEqual(x.after[0], 10)
        self.assertLessEqual(x.end - x.start, __import__("datetime").timedelta(days=1))
        for n in (0, MAX_PAGE + 1, True, -1, 3.14):
            with self.subTest(limit=n), self.assertRaises(ScopeError):
                plan(limit=n)

    def test_source_instruments_require_exact_sorted_unique_keyset(self):
        for keys in ((), (20, 10), (10, 10), (True,), ("10",), (-1,),
                     tuple(range(129)), [10, 20]):
            with self.subTest(keys=str(keys)[:25]), self.assertRaises(ScopeError):
                plan(instrument_keys=keys)
        with self.assertRaises(ScopeError):
            plan(after=(15, START))
        with self.assertRaises(ScopeError):
            plan(after=(-1, START))
        with self.assertRaises(ScopeError):
            plan(after=(10, "2026-10-01T00:00:00Z"))

    def test_exact_utc_minute_bounds_and_window_enforced(self):
        bad = (
            ("2026-07-31T13:30:00Z", END),
            (START, "2026-10-01T00:01:00Z"),
            (START, START),
            ("2026-09-02T13:30:01Z", END),
            ("2026-09-02T13:30:00+01:00", END),
            ("2026-09-01T00:00:00Z", "2026-09-03T00:00:00Z"),
        )
        for begin, end in bad:
            with self.subTest(begin=begin, end=end), self.assertRaises(ScopeError):
                plan(start_utc=begin, end_utc=end)
        with self.assertRaises(ScopeError):
            plan(source_snapshot_sha256="no evidence")

    def test_price_labels_separate_regular_from_extended(self):
        x = inspect_price_page(plan(), [source_row()])
        self.assertEqual((x.page_rows, x.labelled_regular, x.labelled_extended), (1, 1, 0))
        self.assertFalse(x.coverage_certified)
        self.assertFalse(x.worker_admission_authorized)
        self.assertIn("NOT_EXPECTED_CALENDAR", x.status)
        with self.assertRaises(ScopeError):
            inspect_price_page(plan(), [source_row(label="premarket")])
        e = inspect_price_page(plan("P02"), [source_row(label="premarket")])
        self.assertEqual(e.labelled_extended, 1)
        with self.assertRaises(ScopeError):
            inspect_price_page(plan("P02"), [source_row(label="regular")])

    def test_empty_september_source_cannot_certify_n_a_or_completeness(self):
        x = inspect_price_page(plan(), [])
        self.assertEqual(x.page_rows, 0)
        self.assertFalse(x.coverage_certified)
        self.assertFalse(x.worker_admission_authorized)
        self.assertEqual(x.next_cursor, None)
        self.assertNotIn("COMPLETE", x.status)

    def test_snapshot_and_bar_values_affect_page_digest_without_price_output(self):
        x = inspect_price_page(plan(), [source_row()])
        changed = inspect_price_page(plan(), [source_row(close=10.15)])
        self.assertNotEqual(x.page_sha256, changed.page_sha256)
        self.assertNotIn("10.05", str(x))
        self.assertNotIn("10.15", str(changed))
        self.assertEqual(len(x.page_sha256), 64)

    def test_duplicate_out_of_order_and_out_of_partition_refused(self):
        p = plan()
        for rows in (
            [source_row(), source_row()],
            [source_row(minute="2026-09-02T13:32:00Z"), source_row()],
            [source_row(key=30)],
            [source_row(minute="2026-08-31T13:31:00Z")],
            [source_row(minute="2026-09-02T14:01:00Z")],
            [source_row(minute="2026-09-02T13:31:12Z")],
        ):
            with self.subTest(rows=str(rows)[:30]), self.assertRaises(ScopeError):
                inspect_price_page(p, rows)
        with self.assertRaises(ScopeError):
            inspect_price_page(plan(after=(10, START)), [source_row(minute=START)])

    def test_no_malformed_source_field_or_ohlc_is_silently_accepted(self):
        for row in (
            source_row(high=9.0),
            source_row(open=-1.0),
            source_row(vwap=None),
            source_row(volume=-5),
            source_row(trade_count=1.5),
            source_row(open=float("nan")),
            {k:v for k,v in source_row().items() if k!="session_label"},
        ):
            with self.subTest(row=str(row)[:30]), self.assertRaises(ScopeError):
                inspect_price_page(plan(), [row])

    def test_malformed_response_and_bound_refused(self):
        p = plan(limit=1)
        for rows in ("invalid", None, [source_row(),source_row()], [42]):
            with self.subTest(rows=str(rows)[:30]), self.assertRaises(ScopeError):
                inspect_price_page(p, rows)

    def test_p02_original_contract_has_no_independent_enriched_view(self):
        with self.assertRaises(ScopeError):
            plan("P02", route=DERIVED_VIEW)
        p = plan("P02")
        self.assertEqual(tuple(p.instrument_keys), (10,20))
        self.assertEqual(tuple(FIELDS)[:2], ("instrument_key", "bar_ts"))


if __name__ == "__main__":
    unittest.main()
