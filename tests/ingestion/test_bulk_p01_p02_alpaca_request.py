"""P01/P02 September Alpaca one-session request candidate safety."""
from __future__ import annotations

import unittest

from astra_ingestion.bulk_p01_p02_alpaca_request import (
    CONTRACTS, MAX_RECORDS_PER_REQUEST, plan_september_alpaca_sip,
)
from astra_ingestion.bulk_scope import ScopeError

SHA = "c" * 64


def candidate(family="P01", **changes):
    data = dict(
        instrument_key=10, dated_symbol="AAPL", session_day="2026-09-02",
        session_start_utc="2026-09-02T13:30:00Z",
        session_end_utc="2026-09-02T20:00:00Z",
        original_job_deadline="2026-11-01T00:00:00Z",
        manifest_sha256=SHA, contract_sha256=CONTRACTS[family],
        identity_receipt_sha256=SHA, calendar_receipt_sha256=SHA,
        entitlement_receipt_sha256=SHA, reserved_request_count=1,
        reserved_record_count=900,
    )
    data.update(changes)
    return plan_september_alpaca_sip(family, **data)


class AlpacaSeptemberRequestTests(unittest.TestCase):
    def test_exact_provider_feed_adjustment_and_explicit_time(self):
        p = candidate()
        self.assertEqual(p.request, {
            "symbols": "AAPL", "timeframe": "1Min",
            "start": "2026-09-02T13:30:00Z",
            "end": "2026-09-02T20:00:00Z",
            "limit": 900, "adjustment": "raw", "feed": "sip",
            "currency": "USD", "sort": "asc", "asof": "2026-09-02",
        })
        self.assertFalse(p.provider_submission_authorized)
        with self.assertRaises(TypeError):
            p.request["feed"] = "iex"  # immutable after validation
        self.assertFalse(p.worker_admission_authorized)
        self.assertIn("NOT_AUTHORIZED", p.status)

    def test_p02_supports_separately_calendar_verified_extended_range(self):
        p = candidate(
            "P02", session_start_utc="2026-09-02T08:00:00Z",
            session_end_utc="2026-09-02T13:30:00Z",
        )
        self.assertEqual(p.family, "P02")
        self.assertEqual(p.contract_sha256, CONTRACTS["P02"])

    def test_identity_must_use_original_contract_and_native_key(self):
        for family in ("P03", "D06", "REF01"):
            with self.subTest(family=family), self.assertRaises(ScopeError):
                candidate(family="P01", contract_sha256=CONTRACTS["P02"])
        for k in (-1, 1.2, True, None):
            with self.subTest(k=k), self.assertRaises(ScopeError):
                candidate(instrument_key=k)
        for symbol in ("AAPL,MSFT", " aapl", "", "' OR TRUE --", "X" * 200):
            with self.subTest(symbol=symbol), self.assertRaises(ScopeError):
                candidate(dated_symbol=symbol)

    def test_reservations_are_finite_and_not_self_approved(self):
        for n in (0, 2, -1, True, 1.5):
            with self.subTest(requests=n), self.assertRaises(ScopeError):
                candidate(reserved_request_count=n)
        for n in (0, -1, 1001, True, 1.1):
            with self.subTest(records=n), self.assertRaises(ScopeError):
                candidate(reserved_record_count=n)
        p = candidate(reserved_record_count=MAX_RECORDS_PER_REQUEST)
        self.assertEqual(p.request["limit"], 1000)

    def test_hash_pins_required_but_not_inferred_external_proofs(self):
        for field in ("manifest_sha256", "identity_receipt_sha256",
                      "calendar_receipt_sha256", "entitlement_receipt_sha256"):
            with self.subTest(field=field), self.assertRaises(ScopeError):
                candidate(**{field: "unverified"})
        with self.assertRaises(ScopeError):
            candidate(contract_sha256=SHA)

    def test_invalid_utc_bounds_and_expired_original_deadlines(self):
        bad = (
            ("2026-08-31T13:30:00Z","2026-08-31T20:00:00Z"),
            ("2026-09-30T23:00:00Z","2026-10-01T01:00:00Z"),
            ("2026-09-02T13:30:00Z","2026-09-02T13:30:00Z"),
            ("2026-09-02T13:30:01Z","2026-09-02T20:00:00Z"),
            ("2026-09-02T13:30:00+00:00","2026-09-02T20:00:00Z"),
            ("2026-09-02T13:30:00Z","2026-09-04T13:30:00Z"),
        )
        for start,end in bad:
            with self.subTest(start=start,end=end), self.assertRaises(ScopeError):
                candidate(session_start_utc=start,session_end_utc=end)
        with self.assertRaises(ScopeError):
            candidate(original_job_deadline="2026-09-01T00:00:00Z")
        with self.assertRaises(ScopeError):
            candidate(original_job_deadline="invalid")

    def test_dated_symbol_must_match_partition_date(self):
        with self.assertRaises(ScopeError):
            candidate(session_day="2026-09-03")
        with self.assertRaises(ScopeError):
            candidate(session_day="invalid")
        with self.assertRaises(ScopeError):
            candidate(session_day="2026-09-02T00:00:00Z")

    def test_original_immutable_canary_job_must_not_be_reopened(self):
        # Historic finite deadline is correctly rejected for September source.
        with self.assertRaises(ScopeError):
            candidate(original_job_deadline="2026-10-29T01:24:00Z",
                      session_start_utc="2026-09-02T13:30:00Z",
                      session_end_utc="2026-11-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
