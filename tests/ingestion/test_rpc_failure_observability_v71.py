"""Attribute fatal RPC failures without exposing data or replaying an effect."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
import io
import json
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from astra_ingestion import worker as cli
from astra_ingestion.backfill_worker_v2 import BackfillWorker
from astra_ingestion.rpc_store import (
    MAX_RESPONSE_BYTES, PROJECT_URL, RPC_PATH, RpcAuthenticationError,
    RpcPersistenceError, RpcStore, rpc_failure_fields,
)
from astra_ingestion.store import LeaseLost, QualityHold, RequestDeferred
from test_rpc_store import Opener, PUBLIC_KEY, Reply, TOKEN


SECRET = "synthetic-private-token-and-payload-never-log"


class HostileString(str):
    def __hash__(self):
        raise AssertionError("Untrusted string subclass must not be hashed")

    def __str__(self):
        raise AssertionError("Untrusted string subclass must not be formatted")


class HostileValue:
    def __str__(self):
        raise AssertionError("Untrusted value must not be formatted")

    def __repr__(self):
        raise AssertionError("Untrusted value must not be inspected")


class NeverReadBody(io.BytesIO):
    def __init__(self):
        super().__init__(SECRET.encode())
        self.read_count = 0

    def read(self, *_args):
        self.read_count += 1
        raise AssertionError("HTTP error body must not be read")


class RpcFailureObservabilityTests(unittest.TestCase):
    def store(self, *outcomes):
        opener = Opener(*outcomes)
        return RpcStore(PROJECT_URL, PUBLIC_KEY, TOKEN, opener=opener), opener

    def record(self, error):
        record = cli.runtime_error_record(error)
        encoded = json.dumps(record, separators=(",", ":"))
        self.assertLessEqual(len(encoded.encode()), 256)
        for forbidden in (SECRET, TOKEN, PUBLIC_KEY, "Traceback", "raw_body", "payload"):
            self.assertNotIn(forbidden, encoded)
        self.assertLessEqual(set(record), {"state", "error_type", "rpc_operation", "rpc_failure_reason"})
        return record

    def test_remote_failures_receive_local_labels_without_reading_error_bodies(self):
        for status in (401, 403, 429, 500, 504):
            with self.subTest(status=status):
                body = NeverReadBody()
                headers = Message(); headers["X-Private"] = SECRET
                remote = HTTPError(PROJECT_URL + RPC_PATH + "?" + SECRET, status, SECRET, headers, body)
                remote.__cause__ = RuntimeError(SECRET)
                store, opener = self.store(remote)
                with self.assertRaises(RpcPersistenceError) as caught:
                    store._call("backfill_material", {"private": SECRET})
                error = caught.exception
                expected_class = RpcAuthenticationError if status in (401, 403) else RpcPersistenceError
                self.assertIs(type(error), expected_class)
                expected_message = "Ingestion capability was rejected" if status in (401, 403) else "Persistence HTTP outcome is unresolved; reconcile before continuing"
                self.assertEqual(str(error), expected_message)
                self.assertEqual(body.read_count, 0)
                self.assertTrue(body.closed)
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(opener.calls[0][1], 15)
                result = self.record(error)
                self.assertEqual(result["rpc_operation"], "backfill_material")
                self.assertEqual(result["rpc_failure_reason"], "HTTP_AUTH_REJECTED" if status in (401, 403) else "HTTP_ERROR")

    def test_malformed_response_categories_do_not_echo_remote_content(self):
        cases = [
            (Reply({}, status=502), "UNEXPECTED_HTTP_STATUS"),
            (Reply({}, url="https://other.invalid/" + SECRET), "REDIRECT_REFUSED"),
            (Reply(raw=SECRET.encode(), headers={"Content-Type": "text/html"}), "RESPONSE_FORMAT"),
            (Reply({}, headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}), "RESPONSE_BOUND"),
            (Reply({}, headers={"Content-Length": "100000"}), "RESPONSE_INCOMPLETE"),
            (Reply(raw=SECRET.encode()), "RESPONSE_DECODE"),
            (Reply(raw=b'{"ok":true,"result":null,"unexpected":1}'), "RESPONSE_ENVELOPE"),
            (Reply(raw=json.dumps({"ok": False, "error": {"code": SECRET, "message": SECRET}}).encode()), "REMOTE_FAILURE_UNRECOGNIZED"),
            (TimeoutError(SECRET), "TRANSPORT_ERROR"),
        ]
        for outcome, reason in cases:
            with self.subTest(reason=reason):
                store, opener = self.store(outcome)
                with self.assertRaises(RpcPersistenceError) as caught:
                    store._call("backfill_commit", {"raw_body": SECRET})
                self.assertEqual(self.record(caught.exception)["rpc_failure_reason"], reason)
                self.assertEqual(len(opener.calls), 1)

    def test_whole_response_deadline_is_unchanged(self):
        reply = Reply({"ready": True})
        store, opener = self.store(reply)
        with patch("astra_ingestion.rpc_store.monotonic", side_effect=[100, 101, 116]):
            with self.assertRaises(RpcPersistenceError) as caught:
                store._call("backfill_claim", {})
        self.assertEqual(self.record(caught.exception)["rpc_failure_reason"], "RESPONSE_DEADLINE")
        self.assertEqual(str(caught.exception), "Persistence response deadline exceeded; reconcile before continuing")
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0][1], 15)
        self.assertTrue(reply.closed)

    def test_unknown_operations_do_not_become_log_labels_or_change_request(self):
        for operation in (SECRET, SECRET * 10000, "backfill_material\n" + SECRET, [SECRET], {"x": SECRET}, HostileString("backfill_material")):
            store, opener = self.store(Reply(raw=b"invalid-json"))
            with self.assertRaises(RpcPersistenceError) as caught:
                store._call(operation, {})
            self.assertEqual(self.record(caught.exception)["rpc_operation"], "UNKNOWN")
            # The diagnostic allowlist must never become a replacement auth gate
            # or silently rewrite the operation submitted to the existing RPC.
            self.assertEqual(json.loads(opener.calls[0][0].data)["operation"], operation)
            self.assertEqual(len(opener.calls), 1)

    def test_constructor_and_mutated_attributes_use_strict_fixed_fallbacks(self):
        for hostile in (SECRET, SECRET * 10000, [SECRET], {SECRET: SECRET}, HostileValue(), HostileString("HTTP_ERROR")):
            error = RpcPersistenceError(SECRET, reason_code=hostile)
            self.assertEqual(self.record(error)["rpc_failure_reason"], "UNCLASSIFIED_PERSISTENCE_FAILURE")
            error.rpc_operation = hostile
            error.rpc_failure_reason = hostile
            error.token = TOKEN
            error.payload = {SECRET: SECRET}
            error.__cause__ = RuntimeError(SECRET)
            error.__context__ = ValueError(SECRET)
            result = self.record(error)
            self.assertEqual(result["rpc_operation"], "UNKNOWN")
            self.assertEqual(result["rpc_failure_reason"], "UNCLASSIFIED_PERSISTENCE_FAILURE")

    def test_same_exception_identity_and_args_escape_without_retry(self):
        original = RpcPersistenceError("original controlled message", 7, reason_code="HTTP_ERROR")
        store, opener = self.store()
        with patch.object(store, "_call_once", side_effect=original) as once:
            with self.assertRaises(RpcPersistenceError) as caught:
                store._call("backfill_commit", {})
        self.assertIs(caught.exception, original)
        self.assertEqual(original.args, ("original controlled message", 7))
        once.assert_called_once_with("backfill_commit", {})
        self.assertEqual(opener.calls, [])
        self.assertEqual(self.record(original)["rpc_operation"], "backfill_commit")

    def test_handled_database_dispositions_keep_existing_exception_classes(self):
        for code, expected in (("lease_lost", LeaseLost), ("quality_hold", QualityHold), ("request_deferred", RequestDeferred), ("not_found", KeyError), ("conflict", ValueError)):
            store, opener = self.store(Reply(raw=json.dumps({"ok": False, "error": {"code": code, "message": SECRET}}).encode()))
            with self.assertRaises(expected) as caught:
                store._call("backfill_reserve", {})
            self.assertNotIsInstance(caught.exception, RpcPersistenceError)
            self.assertEqual(rpc_failure_fields(caught.exception), {})
            self.assertEqual(len(opener.calls), 1)

    def test_current_replacement_worker_does_not_fetch_defer_or_retry_uncertain_reservation(self):
        claim = {"id": "task-fixture", "run_id": "fixture-run", "owner": "fixture-worker", "generation": 1,
                 "run_fence": 1, "page_no": 0, "family": "N01", "kind": "alpaca_news", "provider": "Alpaca", "scope": {}}
        store, opener = self.store(Reply(claim), TimeoutError(SECRET))
        provider = SimpleNamespace(supported_kinds=lambda: ("alpaca_news",), require_credentials=Mock(), fetch=Mock())
        backfill = BackfillWorker(store, provider, worker_id="fixture-worker")
        with self.assertRaises(RpcPersistenceError) as caught:
            backfill.run_once()
        provider.fetch.assert_not_called()
        self.assertEqual([json.loads(req.data)["operation"] for req, _ in opener.calls], ["backfill_claim", "backfill_reserve"])
        self.assertEqual(self.record(caught.exception)["rpc_operation"], "backfill_reserve")

    def test_actual_cli_fails_once_and_logs_only_bounded_safe_fields(self):
        body = NeverReadBody()
        remote = HTTPError(PROJECT_URL + RPC_PATH, 500, SECRET, Message(), body)
        remote.__context__ = RuntimeError(SECRET)
        real_store, opener = self.store(remote)
        backfill = SimpleNamespace(run_once=Mock(side_effect=lambda: real_store._call("backfill_material", {"raw_body": SECRET})))
        settings = SimpleNamespace(api_key=SECRET, secret_key=SECRET, lease_seconds=90, test_mode=False, worker_poll_seconds=2)
        startup_store = SimpleNamespace(health=Mock())
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli.Settings, "from_env", return_value=settings), patch("astra_ingestion.rpc_store.create_store", return_value=startup_store), \
             patch.object(cli, "AlpacaSource"), patch("astra_ingestion.backfill_worker_v2.from_settings", return_value=backfill), \
             patch.object(cli.signal, "signal"), redirect_stdout(stdout), redirect_stderr(stderr):
            result = cli.main()
        self.assertEqual(result, 1)
        backfill.run_once.assert_called_once()
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        record = json.loads(stderr.getvalue())
        self.assertEqual(record, {"state": "unresolved_runtime_error", "error_type": "RpcPersistenceError",
                                  "rpc_operation": "backfill_material", "rpc_failure_reason": "HTTP_ERROR"})
        self.assertLess(len(stderr.getvalue().encode()), 256)
        self.assertNotIn(SECRET, stderr.getvalue())
        self.assertNotIn(TOKEN, stderr.getvalue())
        self.assertEqual(body.read_count, 0)

    def test_failure_context_is_per_exception_not_shared_between_concurrent_calls(self):
        barrier = Barrier(2)
        store, _ = self.store()
        def invoke(operation, _payload):
            barrier.wait(timeout=2)
            raise RpcPersistenceError(SECRET, reason_code="TRANSPORT_ERROR")
        def call(operation):
            try:
                store._call(operation, {})
            except RpcPersistenceError as error:
                return rpc_failure_fields(error)
        with patch.object(store, "_call_once", side_effect=invoke) as once, ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(call, ("backfill_claim", "backfill_material")))
        self.assertEqual(once.call_count, 2)
        self.assertEqual([r["rpc_operation"] for r in results], ["backfill_claim", "backfill_material"])

    def test_success_keeps_response_request_origin_headers_and_timeout(self):
        value = {"state": "page_committed", "page_no": 0}
        store, opener = self.store(Reply(value))
        payload = {"claim": {"id": "fixture"}, "raw_body": SECRET}
        self.assertEqual(store._call("backfill_commit", payload), value)
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, PROJECT_URL + RPC_PATH)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, 15)
        self.assertEqual(request.get_header("X-astra-ingestion-token"), TOKEN)
        self.assertEqual(json.loads(request.data), {"operation": "backfill_commit", "payload": payload})

    def test_custom_rpc_exception_type_name_cannot_add_data_to_log(self):
        hostile_class = type(SECRET.replace("-", "_"), (RpcPersistenceError,), {})
        record = self.record(hostile_class(SECRET, reason_code="HTTP_ERROR"))
        self.assertEqual(record["error_type"], "RpcPersistenceError")
        oversized = type("X" * 10000, (RuntimeError,), {})
        self.assertEqual(cli.runtime_error_record(oversized(SECRET))["error_type"], "Exception")
        sensitive_type = type(TOKEN, (RuntimeError,), {})
        self.assertEqual(self.record(sensitive_type(SECRET))["error_type"], "Exception")


if __name__ == "__main__":
    unittest.main()
