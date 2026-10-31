"""Strict confirmed-abort classification; no real network/provider requests."""
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from http.client import IncompleteRead
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from astra_ingestion import rpc_store as rpc
from astra_ingestion.backfill_worker_v2 import BackfillWorker
from astra_ingestion.store import LeaseLost, QualityHold, RequestDeferred
from astra_ingestion.worker import runtime_error_record
from test_backfill_worker_v2 import FixtureProvider, synthetic_claim
from test_rpc_store import Opener, PUBLIC_KEY, Reply, TOKEN

ENDPOINT = rpc.PROJECT_URL + rpc.RPC_PATH
SECRET = "SYNTHETIC_PRIVATE_ERROR_BODY_MUST_NEVER_BE_LOGGED"


class Body(io.BytesIO):
    def __init__(self, value, *, fail=None, before_read=None):
        super().__init__(value)
        self.reads = []
        self.fail = fail
        self.before_read = before_read

    def read1(self, size):
        self.reads.append(size)
        if self.before_read:
            self.before_read()
        if self.fail:
            raise self.fail
        return super().read1(size)


def error_response(*, code="55P03", status=500, value=None, raw=None,
                   url=ENDPOINT, headers=None, omit_length=False, fail=None,
                   before_read=None):
    value = value if value is not None else {
        "code": code, "message": SECRET, "details": SECRET, "hint": SECRET}
    raw = json.dumps(value).encode() if raw is None else raw
    metadata = Message()
    metadata["Content-Type"] = "application/json; charset=utf-8"
    if not omit_length:
        metadata["Content-Length"] = str(len(raw))
    for key, item in (headers or {}).items():
        if key in metadata:
            del metadata[key]
        if item is not None:
            metadata[key] = item
    body = Body(raw, fail=fail, before_read=before_read)
    error = HTTPError(url, status, SECRET, metadata, body)
    error.__cause__ = RuntimeError(SECRET)
    return error, body


class Clock:
    def __init__(self):
        self.now = 100.0
        self.delays = []

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.delays.append(delay)
        self.now += delay


class LockAbortRetryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.enterContext(patch.object(rpc, "monotonic", self.clock.monotonic))
        self.enterContext(patch.object(rpc, "sleep", self.clock.sleep))

    def store(self, *outcomes):
        opener = Opener(*outcomes)
        return rpc.RpcStore(rpc.PROJECT_URL, PUBLIC_KEY, TOKEN, opener=opener), opener

    def assert_safe(self, error, operation, reason):
        record = runtime_error_record(error)
        self.assertEqual(record, {"state": "unresolved_runtime_error", "error_type": "RpcPersistenceError",
                                  "rpc_operation": operation, "rpc_failure_reason": reason})
        encoded = json.dumps(record)
        self.assertLess(len(encoded.encode()), 256)
        for forbidden in (SECRET, TOKEN, PUBLIC_KEY, "raw_body", "payload", "Traceback"):
            self.assertNotIn(forbidden, encoded)
            self.assertNotIn(forbidden, str(error))

    def test_seven_database_operations_retry_only_complete_native_error(self):
        expected = {"backfill_claim", "backfill_reserve", "backfill_commit", "backfill_reuse_commit",
                    "backfill_verify", "backfill_plan_next", "backfill_defer"}
        self.assertEqual(rpc.LOCK_ABORT_RETRY_OPERATIONS, expected)
        for operation in sorted(expected):
            with self.subTest(operation=operation):
                error, body = error_response()
                store, opener = self.store(error, Reply({"state": "fixture-success"}))
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = store._call(operation, {"raw_body": SECRET})
                self.assertEqual(result, {"state": "fixture-success"})
                self.assertEqual(len(opener.calls), 2)
                self.assertEqual(opener.calls[0][0].data, opener.calls[1][0].data)
                self.assertEqual(opener.calls[0][0].header_items(), opener.calls[1][0].header_items())
                self.assertEqual(opener.calls[1][0].full_url, ENDPOINT)
                self.assertTrue(body.closed)
                self.assertGreater(len(body.reads), 0)
                self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_two_retries_serialize_once_even_if_original_payload_changes(self):
        first, _ = error_response()
        second, _ = error_response()
        payload = {"claim": {"generation": 7}, "raw_body": SECRET}
        store, opener = self.store(first, second, Reply("done"))
        original_open = opener.open
        def mutate(request, timeout):
            result = None
            try:
                result = original_open(request, timeout)
            finally:
                payload["claim"]["generation"] = 99
                payload["raw_body"] = "changed after serialization"
            return result
        opener.open = mutate
        with patch.object(rpc.json, "dumps", wraps=json.dumps) as dumps:
            self.assertEqual(store._call("backfill_commit", payload), "done")
            self.assertEqual(dumps.call_count, 1)
        self.assertEqual(len(opener.calls), 3)
        self.assertEqual({req.data for req, _ in opener.calls}, {opener.calls[0][0].data})
        self.assertEqual(json.loads(opener.calls[0][0].data)["payload"]["claim"]["generation"], 7)
        self.assertEqual(self.clock.delays, [0.25, 0.75])
        self.assertEqual([timeout for _, timeout in opener.calls], [15, 14.75, 14.0])

    def test_exhaustion_is_three_sends_with_only_fixed_safe_labels(self):
        outcomes = [error_response() for _ in range(3)]
        store, opener = self.store(*(x[0] for x in outcomes), Reply("must not send"))
        with self.assertRaises(rpc.RpcPersistenceError) as caught:
            store._call("backfill_claim", {})
        self.assertEqual(len(opener.calls), 3)
        self.assertEqual(self.clock.delays, [0.25, 0.75])
        self.assertTrue(all(body.closed for _, body in outcomes))
        self.assert_safe(caught.exception, "backfill_claim", "LOCK_ABORT_RETRY_EXHAUSTED")

    def test_ineligible_operations_statuses_origins_and_headers_are_not_read(self):
        cases = [("backfill_material", {}), ("backfill_maintain", {}), ("backfill_relay_dispatch", {}),
                 ("health", {}), ("submit_job", {})]
        cases += [("backfill_commit", {"status": status}) for status in (301, 307, 401, 403, 429, 502, 503, 504)]
        cases += [("backfill_commit", {"url": url}) for url in ("https://other.invalid" + rpc.RPC_PATH,
                    ENDPOINT + "?private=" + SECRET, ENDPOINT + "#fragment", rpc.PROJECT_URL + "/wrong")]
        cases += [("backfill_commit", {"headers": headers}) for headers in (
            {"Content-Type": "text/html"}, {"Content-Type": None}, {"Content-Encoding": "gzip"},
            {"Content-Length": "-1"}, {"Content-Length": "99999999999999999999999"},
            {"Content-Length": str(rpc.MAX_LOCK_ABORT_ERROR_BYTES + 1)},
            {"Transfer-Encoding": "chunked"}, {"Transfer-Encoding": "gzip"})]
        for operation, options in cases:
            with self.subTest(operation=operation, options=options):
                error, body = error_response(**options)
                store, opener = self.store(error, Reply("must not send"))
                with self.assertRaises(rpc.RpcPersistenceError):
                    store._call(operation, {})
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(body.reads, [])
                self.assertTrue(body.closed)

    def test_duplicate_framing_headers_are_not_read(self):
        for header in ("Content-Type", "Content-Encoding", "Content-Length", "Transfer-Encoding"):
            error, body = error_response()
            error.headers[header] = error.headers.get(header, "identity")
            if len(error.headers.get_all(header)) == 1:
                error.headers[header] = "identity"
            store, opener = self.store(error)
            with self.assertRaises(rpc.RpcPersistenceError):
                store._call("backfill_commit", {})
            self.assertEqual(body.reads, [])
            self.assertEqual(len(opener.calls), 1)

    def test_complete_eof_without_content_length_is_allowed(self):
        for headers in ({}, {"Transfer-Encoding": "chunked"}):
            error, body = error_response(omit_length=True, headers=headers)
            store, opener = self.store(error, Reply("done"))
            self.assertEqual(store._call("backfill_commit", {}), "done")
            self.assertEqual(len(opener.calls), 2)
            self.assertTrue(body.closed)

    def test_wrong_sqlstates_and_application_envelopes_never_retry(self):
        values = [{"code": code, "message": "55P03 " + SECRET, "details": None, "hint": None}
                  for code in ("55000", "57014", "40001", "40003", "40P01", "PGRST003", "55p03", 55003, None, ["55P03"])]
        values += [{"ok": False, "error": {"code": "55P03"}},
                   {"ok": True, "result": {"code": "55P03"}},
                   {"code": "55P03", "message": SECRET},
                   {"code": "55P03", "message": SECRET, "details": {}, "hint": None},
                   {"code": "55P03", "message": None, "details": None, "hint": None},
                   {"code": "55P03", "message": SECRET, "details": None, "hint": None, "extra": 1}]
        for value in values:
            with self.subTest(value=value):
                error, body = error_response(value=value)
                store, opener = self.store(error, Reply("must not send"))
                with self.assertRaises(rpc.RpcPersistenceError) as caught:
                    store._call("backfill_commit", {})
                self.assertEqual(len(opener.calls), 1)
                self.assertTrue(body.closed)
                self.assert_safe(caught.exception, "backfill_commit", "HTTP_ERROR")

    def test_invalid_json_and_incomplete_or_oversized_error_fail_closed(self):
        raws = [b'{"code":"55P03","code":"55P03","message":"x","details":null,"hint":null}',
                b'{"code":"55P03","message":"x","details":NaN,"hint":null}',
                b'\xff', b'{"code":"55P03"', b'[]', b'null', b'{} trailing',
                b'[' * 1500 + b']' * 1500, b'x' * (rpc.MAX_LOCK_ABORT_ERROR_BYTES + 1)]
        for raw in raws:
            error, body = error_response(raw=raw, omit_length=True)
            store, opener = self.store(error)
            with self.assertRaises(rpc.RpcPersistenceError):
                store._call("backfill_commit", {})
            self.assertEqual(len(opener.calls), 1)
            self.assertTrue(body.closed)
            self.assertLessEqual(sum(body.reads), rpc.MAX_LOCK_ABORT_ERROR_BYTES + 1024)
        error, body = error_response(headers={"Content-Length": "1000"})
        store, opener = self.store(error)
        with self.assertRaises(rpc.RpcPersistenceError):
            store._call("backfill_commit", {})
        self.assertEqual(len(opener.calls), 1)

    def test_error_stream_failures_and_trickling_never_retry(self):
        for failure in (TimeoutError(SECRET), URLError(SECRET), IncompleteRead(b"55P03", 10)):
            error, body = error_response(fail=failure)
            store, opener = self.store(error)
            with self.assertRaises(rpc.RpcPersistenceError):
                store._call("backfill_commit", {})
            self.assertEqual(len(opener.calls), 1)
            self.assertTrue(body.closed)
        error, body = error_response(before_read=lambda: setattr(self.clock, "now", self.clock.now + 16))
        store, opener = self.store(error)
        with self.assertRaises(rpc.RpcPersistenceError):
            store._call("backfill_commit", {})
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(len(body.reads), 1)

    def test_deadline_does_not_reset_or_launch_after_backoff_expiry(self):
        error, _ = error_response()
        store, opener = self.store(error, Reply("must not send"))
        original = self.clock.sleep
        def expired(delay):
            original(delay)
            self.clock.now = 116
        with patch.object(rpc, "sleep", expired):
            with self.assertRaises(rpc.RpcPersistenceError) as caught:
                store._call("backfill_commit", {})
        self.assertEqual(len(opener.calls), 1)
        self.assert_safe(caught.exception, "backfill_commit", "LOCK_ABORT_RETRY_EXHAUSTED")

    def test_unknown_second_outcome_stops_even_after_a_confirmed_abort(self):
        for outcome in (TimeoutError(SECRET), URLError(SECRET), Reply(raw=b"invalid"), Reply({}, status=502)):
            error, _ = error_response()
            store, opener = self.store(error, outcome, Reply("must not send"))
            with self.assertRaises(rpc.RpcPersistenceError):
                store._call("backfill_commit", {})
            self.assertEqual(len(opener.calls), 2)

    def test_success_response_stream_cannot_be_reclassified_as_rollback(self):
        response = Reply("committed")
        error, _ = error_response()
        response.read1 = Mock(side_effect=error)
        store, opener = self.store(response, Reply("must not send"))
        with self.assertRaises(rpc.RpcPersistenceError) as caught:
            store._call("backfill_commit", {})
        self.assertEqual(len(opener.calls), 1)
        self.assert_safe(caught.exception, "backfill_commit", "TRANSPORT_ERROR")

    def test_authentication_and_ownership_dispositions_after_abort_stop(self):
        for code, expected in (("lease_lost", LeaseLost), ("quality_hold", QualityHold), ("request_deferred", RequestDeferred)):
            error, _ = error_response()
            store, opener = self.store(error, Reply(raw=json.dumps({"ok": False, "error": {"code": code, "message": SECRET}}).encode()))
            with self.assertRaises(expected):
                store._call("backfill_commit", {})
            self.assertEqual(len(opener.calls), 2)
        for status in (401, 403):
            error, _ = error_response()
            rejected, body = error_response(status=status)
            store, opener = self.store(error, rejected)
            with self.assertRaises(rpc.RpcAuthenticationError):
                store._call("backfill_commit", {})
            self.assertEqual(len(opener.calls), 2)
            self.assertEqual(body.reads, [])

    def test_exception_reason_cannot_authorize_retry_or_swallow_interrupt(self):
        original = rpc.RpcPersistenceError(SECRET, reason_code="LOCK_ABORT_RETRY_EXHAUSTED")
        store, opener = self.store()
        with patch.object(store, "_call_once", side_effect=original):
            with self.assertRaises(rpc.RpcPersistenceError) as caught:
                store._call("backfill_commit", {})
        self.assertIs(caught.exception, original)
        self.assertEqual(opener.calls, [])
        error, _ = error_response()
        store, opener = self.store(error)
        with patch.object(rpc, "sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                store._call("backfill_commit", {})
        self.assertEqual(len(opener.calls), 1)

    def test_worker_retries_commit_and_verification_without_provider_replay(self):
        claim, provider = synthetic_claim(), FixtureProvider()
        page = provider.page
        committed = {"state": "page_committed", "record_count": len(page.records), "body_sha256": page.body_sha256}
        verified = {"state": "committed", "record_count": len(page.records),
                    "body_sha256": page.body_sha256, "readback_sha256": page.body_sha256}
        commit_error, _ = error_response()
        verify_error, _ = error_response()
        store, opener = self.store(Reply(claim), Reply({"state": "reserved"}), commit_error,
                                   Reply(committed), verify_error, Reply(verified))
        result = BackfillWorker(store, provider).run_once()
        # The existing worker merges the RPC result last, preserving its state.
        self.assertEqual(result["state"], "page_committed")
        self.assertEqual(provider.fetch_count, 1)
        operations = [json.loads(req.data)["operation"] for req, _ in opener.calls]
        self.assertEqual(operations, ["backfill_claim", "backfill_reserve", "backfill_commit", "backfill_commit", "backfill_verify", "backfill_verify"])
        self.assertEqual(opener.calls[2][0].data, opener.calls[3][0].data)
        self.assertEqual(opener.calls[4][0].data, opener.calls[5][0].data)

    def test_worker_unknown_commit_is_fatal_and_planner_abort_resumes_once(self):
        claim, provider = synthetic_claim(), FixtureProvider()
        store, opener = self.store(Reply(claim), Reply({"state": "reserved"}), TimeoutError(SECRET))
        with self.assertRaises(rpc.RpcPersistenceError):
            BackfillWorker(store, provider).run_once()
        self.assertEqual(provider.fetch_count, 1)
        self.assertEqual(len(opener.calls), 3)
        error, _ = error_response()
        store, opener = self.store(error, Reply({"plan_complete": False}), Reply(None))
        result = BackfillWorker(store, FixtureProvider(), planning_enabled=True).run_once()
        self.assertEqual(result["state"], "idle")
        self.assertEqual([json.loads(req.data)["operation"] for req, _ in opener.calls],
                         ["backfill_plan_next", "backfill_plan_next", "backfill_claim"])


if __name__ == "__main__":
    unittest.main()
