"""Provider-free transport tests; no real HTTP, secrets, review or entitlement.

All tickets, bar records, TLS observations and authorization callbacks are
synthetic. The tests do NOT constitute hosted authenticated source provenance.
"""
from __future__ import annotations

from dataclasses import replace
import json
import unittest

from astra_ingestion.bulk_p01_p02_alpaca_request import CONTRACTS, plan_september_alpaca_sip
from astra_ingestion.bulk_p01_p02_alpaca_response import inspect_sip_response
from astra_ingestion.bulk_provider_precall import provider_request_sha256
from astra_ingestion.bulk_authenticated_provider_transport import (
    BoundHTTPSPage, ENDPOINT, MAX_BODY_BYTES, TIMEOUT_SECONDS, fetch_once,
    inspect_https_page, prepare_bound_https_page,
)
from astra_ingestion.bulk_scope import ScopeError


SHA = "a" * 64
WORK = "astra-bulk-v1-" + "b" * 64
DEADLINE = "2026-11-01T00:00:00Z"
NOW = "2026-10-30T04:10:00Z"


def plan():
    return plan_september_alpaca_sip(
        "P01", instrument_key=100, dated_symbol="AAPL",
        session_day="2026-09-02",
        session_start_utc="2026-09-02T13:30:00Z",
        session_end_utc="2026-09-02T20:00:00Z",
        original_job_deadline=DEADLINE, manifest_sha256=SHA,
        contract_sha256=CONTRACTS["P01"],
        identity_receipt_sha256=SHA, calendar_receipt_sha256=SHA,
        entitlement_receipt_sha256=SHA,
        reserved_request_count=1, reserved_record_count=900)


def claim(**changes):
    c = dict(
        work_key=WORK, claim_owner="synthetic-restricted-worker",
        claim_fence=3, last_page=-1, manifest_sha256=SHA,
        family="P01", mode="provider_acquisition", status="claimed",
        stopped=False, source_receipt_sha256="c"*64, attempts=1,
        original_deadline=DEADLINE, claim_until="2026-10-30T04:40:00Z",
        max_requests=2, requests_committed=0,
        max_records=1800, records_committed=0,
    )
    c.update(changes)
    return c


def ticket(p=None, c=None, **changes):
    p = p or plan()
    c = c or claim()
    t = dict(status="RESERVED_NO_PROVIDER_TRANSPORT_GRANT",
             work_key=c["work_key"], page_no=c["last_page"] + 1,
             manifest_sha256=SHA, family="P01",
             claim_fence=c["claim_fence"],
             request_sha256=provider_request_sha256(p),
             records_reserved=900,
             original_deadline="2026-11-01T00:00:00+00:00",
             provider_submission_authorized=False)
    t.update(changes)
    return t


def bar(t="2026-09-02T13:30:00Z"):
    return dict(t=t, o=10.1, h=10.5, l=10.0, c=10.2,
                v=100, n=5, vw=10.3)


def response(bars=None, token=None):
    return {"bars": {"AAPL": [bar()] if bars is None else bars},
            "next_page_token": token}


def bound(p=None, c=None, t=None, **kwargs):
    p = p or plan()
    c = c or claim()
    return prepare_bound_https_page(
        p, c, t or ticket(p, c), now_utc=NOW, **kwargs)


def inspect(b=None, body=None, **changes):
    b = b or bound()
    payload = json.dumps(response() if body is None else body).encode("utf-8")
    k = dict(effective_url=b.url, status_code=200,
             content_type="application/json; charset=utf-8",
             content_encoding=None, raw_body=payload)
    k.update(changes)
    return inspect_https_page(b, **k)


class FakeResponse:
    def __init__(self, url, payload, *, content_type="application/json",
                 content_encoding=None, status=200):
        self._url = url
        self._payload = payload
        self.status = status
        self.headers = {"Content-Type": content_type}
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self._url

    def read(self, limit):
        return self._payload[:limit]


class TransportStageTests(unittest.TestCase):
    def test_exact_query_and_source_only_status(self):
        b = bound()
        self.assertTrue(b.url.startswith(ENDPOINT + "?"))
        for value in ("symbols=AAPL", "timeframe=1Min", "feed=sip",
                      "adjustment=raw", "currency=USD", "asof=2026-09-02",
                      "limit=900", "sort=asc"):
            self.assertIn(value, b.url)
        self.assertNotIn("page_token", b.url)
        self.assertFalse(b.provider_submission_authorized)
        self.assertNotIn(b.url, repr(b))
        self.assertEqual(b.request_sha256, provider_request_sha256(plan()))

    def test_immutable_ticket_fencing_and_deadline(self):
        for kw in ({"c": claim(stopped=True)}, {"c": claim(attempts=3)},
                   {"c": claim(claim_until="2026-10-30T04:09:00Z")},
                   {"t": ticket(request_sha256="f" * 64)},
                   {"t": ticket(page_no=1)},
                   {"t": ticket(provider_submission_authorized=True)}):
            with self.subTest(kw=kw), self.assertRaises(ScopeError):
                bound(**kw)
        with self.assertRaises(ScopeError):
            bound(p=replace(plan(), reserved_record_count=800),
                  t=ticket())

    def test_continuation_must_match_predecessor(self):
        p = plan()
        prev = inspect_sip_response(
            p, response(token="QUJDRA=="))
        c = claim(last_page=0, requests_committed=1, records_committed=1)
        t = ticket(p, c)
        receipt = dict(consistent=True, work_key=WORK, page_no=0,
                       source_page_sha256=prev.page_sha256)
        b = bound(p, c, t, previous=prev, previous_receipt=receipt)
        self.assertIn("page_token=QUJDRA%3D%3D", b.url)
        self.assertEqual(b.page_no, 1)
        with self.assertRaises(ScopeError):
            bound(p, c, t, previous=prev,
                  previous_receipt={**receipt, "source_page_sha256": "f"*64})
        with self.assertRaises(ScopeError):
            bound(p, c, t, previous=prev,
                  previous_receipt={**receipt, "consistent": False})
        with self.assertRaises(ScopeError):
            bound(p, c, t, previous=None, previous_receipt=receipt)

    def test_observation_is_not_provider_attestation_or_coverage(self):
        x = inspect()
        self.assertEqual(x.request_sha256, provider_request_sha256(plan()))
        self.assertEqual(x.witness.page_no, 0)
        self.assertEqual(len(x.witness.bars), 1)
        self.assertEqual(len(x.raw_body_sha256), 64)
        self.assertFalse(x.provider_provenance_accepted)
        self.assertFalse(x.bulk_output_committed)
        self.assertNotIn("10.1", repr(x))
        self.assertEqual(x.quarantinable_response()["bars"]["AAPL"][0]["o"], 10.1)

    def test_no_redirect_wrong_status_media_compression_oversize_or_empty(self):
        b = bound()
        for changes in (
            {"effective_url": "https://evil.example/v2/stocks/bars"},
            {"status_code": 302},
            {"status_code": 401},
            {"content_type": "text/html"},
            {"content_encoding": "gzip"},
            {"raw_body": b""},
            {"raw_body": b"x" * (MAX_BODY_BYTES + 1)},
        ):
            with self.subTest(changes=list(changes)), self.assertRaises(ScopeError):
                inspect(b, **changes)

    def test_duplicate_json_keys_nonfinite_and_foreign_symbol_rejected(self):
        for raw in (
            b'{"bars":{},"bars":{},"next_page_token":null}',
            b'{"bars":{"AAPL":[]},"next_page_token":NaN}',
            b'{"bars":{"TSLA":[]},"next_page_token":null}',
            b'{"bars":{"AAPL":[]},"next_page_token":true}',
            b'{"bars":{"AAPL":[{"t":"2026-09-02T21:00:00Z","o":10,"h":10,"l":10,"c":10,"v":1,"n":1,"vw":10}]},"next_page_token":null}',
        ):
            with self.subTest(raw=raw[:40]), self.assertRaises(ScopeError):
                inspect(raw_body=raw)

    def test_inclusive_end_consumes_source_but_not_eligible(self):
        x = inspect(body=response([
            bar("2026-09-02T19:59:00Z"), bar("2026-09-02T20:00:00Z")]))
        self.assertEqual(len(x.witness.bars), 1)
        self.assertEqual(x.witness.excluded_end_bar_count, 1)
        self.assertFalse(x.provider_provenance_accepted)

    def test_no_network_without_separate_runtime_admission(self):
        b = bound()
        called = []
        def forbidden(*args, **kwargs):
            called.append(1)
            raise AssertionError("network must not be opened")
        for approval in (None, lambda _: False, lambda _: "true"):
            with self.assertRaises(ScopeError):
                fetch_once(b, api_key="fake", secret_key="fake",
                           verified_admission=approval, opener=forbidden)
        self.assertFalse(called)

    def test_transport_synthetic_approval_still_not_independent_evidence(self):
        b = bound()
        called = []
        def fake_open(request, *, timeout):
            called.append((request, timeout))
            return FakeResponse(b.url, json.dumps(response()).encode())
        x = fetch_once(b, api_key="synthetic-key", secret_key="synthetic-secret",
                       verified_admission=lambda _: True, opener=fake_open)
        self.assertEqual(len(called), 1)
        req, timeout = called[0]
        self.assertEqual(req.full_url, b.url)
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(timeout, TIMEOUT_SECONDS)
        self.assertIn("Apca-api-key-id", req.headers)
        self.assertNotIn("synthetic-secret", repr(x))
        self.assertFalse(x.provider_provenance_accepted)

    def test_single_call_error_redacted_no_internal_retry(self):
        b = bound()
        calls = []
        def flaky(req, *, timeout):
            calls.append(1)
            raise TimeoutError("synthetic-secret original token query")
        with self.assertRaisesRegex(ScopeError, "reconcile before retry") as error:
            fetch_once(b, api_key="key", secret_key="synthetic-secret",
                       verified_admission=lambda _: True, opener=flaky)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("synthetic-secret", str(error.exception))
        self.assertNotIn("query", str(error.exception))

    def test_empty_last_page_not_coverage(self):
        x = inspect(body=response(bars=[]))
        self.assertEqual(len(x.witness.bars), 0)
        self.assertFalse(x.provider_provenance_accepted)
        self.assertFalse(x.bulk_output_committed)


if __name__ == "__main__":
    unittest.main()
