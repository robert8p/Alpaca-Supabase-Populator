"""Synthetic-only response parsing; no Alpaca calls, actual prices or production state."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from astra_ingestion.bulk_p01_p02_alpaca_request import (
    CONTRACTS, plan_september_alpaca_sip,
)
from astra_ingestion.bulk_p01_p02_alpaca_response import inspect_sip_response
from astra_ingestion.bulk_scope import ScopeError

SHA = "c" * 64


def plan(family="P01"):
    return plan_september_alpaca_sip(
        family, instrument_key=10, dated_symbol="AAPL", session_day="2026-09-02",
        session_start_utc="2026-09-02T13:30:00Z",
        session_end_utc="2026-09-02T20:00:00Z",
        original_job_deadline="2026-11-01T00:00:00Z",
        manifest_sha256=SHA, contract_sha256=CONTRACTS[family],
        identity_receipt_sha256=SHA, calendar_receipt_sha256=SHA,
        entitlement_receipt_sha256=SHA, reserved_request_count=1,
        reserved_record_count=900,
    )


def bar(t="2026-09-02T13:30:00Z", **changes):
    value = dict(t=t, o=10.1, h=10.4, l=10.0, c=10.3,
                 v=100, n=5, vw=10.2)
    value.update(changes)
    return value


class SIPResponseTests(unittest.TestCase):
    def test_original_contract_bound_one_symbol_price_hashes_immutable(self):
        result = inspect_sip_response(
            plan(), {"bars": {"AAPL": [bar()]}, "next_page_token": None})
        self.assertEqual(result.page_no, 0)
        self.assertEqual(len(result.bars), 1)
        self.assertEqual(len(result.bars[0].record_sha256), 64)
        self.assertFalse(result.continuation_required)
        self.assertFalse(result.coverage_certified)
        self.assertFalse(result.worker_admission_authorized)
        self.assertFalse(result.provider_submission_authorized)
        with self.assertRaises(AttributeError):
            result.bars[0].open = "99"

    def test_strict_symbol_and_currency_scope(self):
        for raw in (
            {"bars": {"MSFT": [bar()]}, "next_page_token": None},
            {"bars": {"AAPL": [bar()], "MSFT": []}, "next_page_token": None},
            {"bars": {"AAPL": [bar()]}, "next_page_token": None, "currency": "EUR"},
            {"bars": {"AAPL": [bar()]}, "next_page_token": None, "secret": "bad"},
        ):
            with self.subTest(raw=raw), self.assertRaises(ScopeError):
                inspect_sip_response(plan(), raw)

    def test_out_of_window_inclusive_end_and_duplicates_rejected(self):
        for rows in (
            [bar("2026-09-02T20:00:00Z")],
            [bar("2026-09-02T13:29:00Z")],
            [bar(), bar()],
            [bar("2026-09-02T13:31:00Z"), bar()],
            [bar("2026-09-02T13:30:01Z")],
            [bar("2026-09-02T13:30:00+01:00")],
        ):
            with self.subTest(rows=rows), self.assertRaises(ScopeError):
                inspect_sip_response(plan(), {"bars": {"AAPL": rows}, "next_page_token": None})

    def test_bad_price_relationship_and_numeric_types(self):
        for changes in (
            {"h": 9}, {"l": 11}, {"vw": 11}, {"o": 0},
            {"c": float("nan")}, {"v": -1}, {"n": True},
            {"vw": "10.2"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ScopeError):
                inspect_sip_response(plan(), {
                    "bars": {"AAPL": [bar(**changes)]}, "next_page_token": None,
                })

    def test_response_size_and_bar_keys(self):
        with self.assertRaises(ScopeError):
            inspect_sip_response(plan(), {"bars": {"AAPL": [bar()] * 901},
                                          "next_page_token": None})
        with self.assertRaises(ScopeError):
            inspect_sip_response(plan(), {"bars": {"AAPL": [dict(t="2026-09-02T13:30:00Z")]},
                                          "next_page_token": None})

    def test_empty_page_is_not_an_expected_calendar_or_nonapplicability(self):
        result = inspect_sip_response(plan(), {"bars": {}, "next_page_token": None})
        self.assertEqual(len(result.bars), 0)
        self.assertFalse(result.coverage_certified)

    def test_continuation_does_not_authorize_or_consume_next_request(self):
        first = inspect_sip_response(plan(), {"bars": {"AAPL": [bar()]},
                                               "next_page_token": "QUJDRA=="})
        self.assertTrue(first.continuation_required)
        self.assertEqual(first.next_page_token, "QUJDRA==")
        second = inspect_sip_response(plan(), {
            "bars": {"AAPL": [bar("2026-09-02T13:31:00Z")]},
            "next_page_token": None,
        }, page_no=1, prior_page_sha256=first.page_sha256,
           prior_bar_timestamp_utc="2026-09-02T13:30:00Z")
        self.assertFalse(second.continuation_required)
        self.assertNotEqual(first.page_sha256, second.page_sha256)
        self.assertFalse(second.coverage_certified)
        with self.assertRaises(ScopeError):
            inspect_sip_response(plan(), {"bars": {"AAPL": [bar()]},
                                          "next_page_token": None}, page_no=1,
                                 prior_page_sha256=first.page_sha256,
                                 prior_bar_timestamp_utc="2026-09-02T13:30:00Z")

    def test_forged_or_mutated_request_or_authority_rejected(self):
        p = plan()
        with self.assertRaises(ScopeError):
            inspect_sip_response(replace(p, status="APPROVED"), {
                "bars": {}, "next_page_token": None})
        with self.assertRaises(ScopeError):
            inspect_sip_response(replace(p, contract_sha256="a" * 64), {
                "bars": {}, "next_page_token": None})

    def test_missing_pagination_or_malformed_page_chain_rejected(self):
        for data in ({"bars": {}}, {"bars": {}, "next_page_token": "a" * 1025},
                     {"bars": [], "next_page_token": None}):
            with self.subTest(data=data), self.assertRaises(ScopeError):
                inspect_sip_response(plan(), data)
        with self.assertRaises(ScopeError):
            inspect_sip_response(plan(), {"bars": {}, "next_page_token": None},
                                 page_no=1, prior_page_sha256="a" * 64)

    def test_p02_keeps_family_and_contract_separate(self):
        result = inspect_sip_response(plan("P02"), {
            "bars": {"AAPL": [bar()]}, "next_page_token": None})
        self.assertEqual(result.family, "P02")
        self.assertEqual(result.contract_sha256, CONTRACTS["P02"])


if __name__ == "__main__":
    unittest.main()
