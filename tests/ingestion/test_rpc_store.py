"""Security and uncertain-outcome tests for the production HTTP boundary."""
import base64
import io
import json
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from astra_ingestion.models import IngestionSpec
from astra_ingestion.rpc_store import (
    MAX_RESPONSE_BYTES, PROJECT_URL, RPC_PATH, RpcAuthenticationError,
    RpcPersistenceError, RpcStore, _NoRedirect, create_store, validate_public_key,
)
from astra_ingestion.store import LeaseLost, QualityHold, RequestDeferred
from astra_ingestion.worker import Worker

PUBLIC_KEY = "sb_publishable_" + "p" * 32
TOKEN = "a" * 64  # Synthetic test capability only.
BASE = {"symbols": ["AAPL"], "start": "2025-09-02T13:30:00Z", "end": "2025-09-02T14:00:00Z", "timeframe": "5Min"}


class Reply:
    def __init__(self, value=None, *, raw=None, status=200, url=PROJECT_URL + RPC_PATH, headers=None):
        self.body = raw if raw is not None else json.dumps({"ok": True, "result": value}).encode()
        self.status, self.url = status, url
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(self.body)), **(headers or {})}
        self.closed = False
        self.position = 0

    def read(self, size):
        return self.body[:size]

    def read1(self, size):
        value = self.body[self.position:self.position+size]
        self.position += len(value)
        return value

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True


class Opener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RpcBoundaryTests(unittest.TestCase):
    def store(self, *outcomes):
        opener = Opener(*outcomes)
        return RpcStore(PROJECT_URL, PUBLIC_KEY, TOKEN, opener=opener), opener

    def test_capability_is_header_only_and_project_origin_is_pinned(self):
        store, opener = self.store(Reply({"ready": True, "schema_version": 1, "rpc_version": 1}))
        self.assertTrue(store.health()["ready"])
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, PROJECT_URL + RPC_PATH)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-astra-ingestion-token"), TOKEN)
        self.assertNotIn(TOKEN, request.data.decode())
        self.assertNotIn(TOKEN, request.full_url)
        self.assertLessEqual(timeout, 15)

    def test_redirects_never_forward_credentials(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 307, "redirect", {}, "https://other.invalid"))
        store, opener = self.store(Reply({}, url="https://other.invalid"))
        with self.assertRaises(RpcPersistenceError):
            store.health()
        self.assertEqual(len(opener.calls), 1)

    def test_service_role_and_other_project_anon_keys_are_rejected(self):
        def jwt(role, ref):
            payload = base64.urlsafe_b64encode(json.dumps({"role": role, "ref": ref}).encode()).decode().rstrip("=")
            return "header." + payload + ".signature"
        for key in ("sb_secret_" + "s" * 40, jwt("service_role", "oxzabweahkoimtevbbny"), jwt("anon", "mnmkxjirpwbptdnvjmpw")):
            with self.subTest(kind=key[:12]), self.assertRaises(ValueError):
                validate_public_key(key)
        validate_public_key(jwt("anon", "oxzabweahkoimtevbbny"))
        for payload in (None, []):
            value=base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
            with self.assertRaises(ValueError):
                validate_public_key("header."+value+".signature")
        for value in ("sb_publishable_"+"a"*20+"\x00", "sb_publishable_"+"a"*20+"é"):
            with self.assertRaises(ValueError):
                validate_public_key(value)

    def test_trickling_response_cannot_reset_whole_response_deadline(self):
        store, opener = self.store(Reply({"ready":True,"schema_version":1,"rpc_version":1}))
        with patch("astra_ingestion.rpc_store.monotonic",side_effect=[100,101,116]):
            with self.assertRaises(RpcPersistenceError):
                store.health()
        self.assertEqual(len(opener.calls),1)

    def test_timeout_never_retries_or_calls_source_after_uncertain_reservation(self):
        claim = {"id": "partition-1", "owner": "worker-1", "generation": 1, "next_page_token": None,
                 "phase": "fetch", "spec": IngestionSpec.from_dict(BASE).to_dict()}
        store, opener = self.store(Reply(claim), TimeoutError("contains-private-transport-context"))
        class Source:
            calls = 0
            def fetch_page(self, *_args):
                self.calls += 1
                raise AssertionError("Provider cannot run after uncertain reservation")
        source = Source()
        with self.assertRaises(RpcPersistenceError) as caught:
            Worker(store, source, worker_id="worker-1").run_once()
        self.assertEqual(source.calls, 0)
        self.assertEqual(len(opener.calls), 2)
        self.assertNotIn("private", str(caught.exception))

    def test_http_failure_is_redacted_and_never_retried(self):
        for status in (401, 403, 429, 500):
            error = HTTPError(PROJECT_URL + RPC_PATH, status, TOKEN, Message(), io.BytesIO(TOKEN.encode()))
            store, opener = self.store(error)
            expected = RpcAuthenticationError if status in (401, 403) else RpcPersistenceError
            with self.subTest(status=status), self.assertRaises(expected) as caught:
                store.list_jobs()
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertEqual(len(opener.calls), 1)

    def test_committed_pacing_response_becomes_deferred_without_another_request(self):
        reply = Reply(raw=b'{"ok":false,"error":{"code":"request_deferred","message":"pacing"}}')
        store, opener = self.store(reply)
        with self.assertRaises(RequestDeferred):
            store.reserve_request({"id":"p", "owner":"w", "generation":1, "next_page_token":None})
        self.assertEqual(len(opener.calls), 1)

    def test_bad_response_and_truncation_do_not_become_success(self):
        replies = [
            Reply(raw=b'{"ok":true,"ok":false,"result":null}'),
            Reply(raw=b'{"ok":true,"result":NaN}'),
            Reply(raw=b'{"ok":true}'),
            Reply(raw=b'{"ok":true,"result":null}', headers={"Content-Length":"500"}),
            Reply({}, headers={"Content-Length":str(MAX_RESPONSE_BYTES + 1)}),
            Reply({}, headers={"Content-Type":"text/html"}),
            Reply({}, headers={"Content-Encoding":"gzip"}),
        ]
        for reply in replies:
            store, opener = self.store(reply)
            with self.subTest(body=reply.body[:30]), self.assertRaises(RpcPersistenceError):
                store.get_job("job-1")
            self.assertEqual(len(opener.calls), 1)

    def test_unknown_error_and_remote_message_do_not_leak(self):
        for code, expected in (("lease_lost",LeaseLost),("quality_hold",QualityHold),("unknown",RpcPersistenceError)):
            value = json.dumps({"ok":False,"error":{"code":code,"message":TOKEN}}).encode()
            store, _ = self.store(Reply(raw=value))
            with self.assertRaises(expected) as caught:
                store.get_job("j")
            self.assertNotIn(TOKEN,str(caught.exception))

    def test_scope_readback_must_match_submitted_scope(self):
        store, _ = self.store(Reply({"id":"j", "scope_hash":"wrong"}))
        with self.assertRaises(RpcPersistenceError):
            store.submit_job(IngestionSpec.from_dict(BASE), "request-001")

    def test_verification_snapshot_rejects_corrupted_record_keys(self):
        record={"symbol":"AAPL","timestamp":BASE["start"],"timeframe":"5Min"}
        store, _ = self.store(Reply({"receipts":[],"records":[{"record_key":"wrong","payload":record}]}))
        with self.assertRaises(QualityHold):
            store.verification_material({"id":"p","owner":"w","generation":1,"next_page_token":None})

    def test_production_factory_has_no_direct_database_fallback(self):
        settings=SimpleNamespace(test_mode=False,database_url="postgresql://admin:secret@localhost/postgres")
        with self.assertRaises(ValueError):
            create_store(settings)


if __name__ == "__main__":
    unittest.main()
