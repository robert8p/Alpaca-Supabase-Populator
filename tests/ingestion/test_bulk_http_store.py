"""Offline only: authenticated-user HTTP contract shape, NOT real JWT proof.

No production credentials, requests, migrations, admissions, reviewer grants,
provider calls or licensed source data. A fabricated test JWT is never a
production credential; only server-side signature + role verification counts.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import unittest
from urllib.error import HTTPError

from astra_ingestion.bulk_http_store import (
    BulkPortAuthError, BulkPortError, RestrictedBulkHttpPort,
)

MANIFEST = "a" * 64
KEY = "sb_publishable_" + "z" * 24
WORK = "astra-bulk-v1-" + "b" * 64
OWNER = "restricted-test-worker"


def fake_jwt(role="authenticated", expiry=None):
    def segment(data):
        return base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode()
        ).decode().rstrip("=")
    expires = expiry if expiry is not None else int(datetime.now(timezone.utc).timestamp()) + 3600
    return segment({"alg": "HS256", "typ": "JWT"}) + "." + segment({
        "role": role, "sub": "synthetic-user-not-authenticated",
        "exp": expires,
    }) + ".testsignature"


class FakeResponse:
    def __init__(self, request, answer, *, status=200, url=None, content_type="application/json"):
        self.status = status
        self._url = url or request.full_url
        self._body = json.dumps(answer, separators=(",", ":")).encode()
        self.headers = {"Content-Type": content_type,
                        "Content-Length": str(len(self._body))}
    def geturl(self):
        return self._url
    def read(self, maximum):
        return self._body[:maximum]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        response = self.replies.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(request, response)


class RestrictedBulkHttpTests(unittest.TestCase):
    def port(self, replies, *, role="authenticated"):
        opener = FakeOpener(replies)
        return RestrictedBulkHttpPort(KEY, fake_jwt(role), opener=opener), opener

    def test_exact_https_authenticated_user_and_four_fixed_rpcs(self):
        receipt = {
            "work_key": WORK, "page_no": 0,
            "records_committed": 2, "requests_committed": 0,
            "source_sha256": "c" * 64, "output_sha256": "d" * 64,
        }
        readback = dict(receipt, consistent=True, actual_records=2,
                        actual_output_sha256="d" * 64)
        port, opener = self.port([
            {"status": "INDEPENDENTLY_REVIEWED_RETAINED_ONLY"},
            {"work_key": WORK, "claim_fence": 1}, receipt, readback,
        ])
        self.assertEqual(port.admission(MANIFEST)["status"],
                         "INDEPENDENTLY_REVIEWED_RETAINED_ONLY")
        self.assertEqual(port.claim_retained(MANIFEST, OWNER, 60)["claim_fence"], 1)
        self.assertEqual(port.commit_retained_page({
            "work_key": WORK, "claim_owner": OWNER, "claim_fence": 1}, 0),
            receipt)
        self.assertEqual(port.readback_receipt(WORK, 0)["consistent"], True)
        expected = [
            "bulk_runtime_admission_v1", "bulk_runtime_claim_v1",
            "bulk_atomic_retained_page_v1", "bulk_retained_receipt_readback_v1",
        ]
        self.assertEqual(len(opener.calls), 4)
        for (request, timeout), name in zip(opener.calls, expected):
            self.assertEqual(timeout, 15)
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.full_url, (
                "https://oxzabweahkoimtevbbny.supabase.co/rest/v1/rpc/" + name))
            self.assertEqual(request.get_header("Content-profile"), "astra_ingestion_v1")
            self.assertEqual(request.get_header("Accept-profile"), "astra_ingestion_v1")
            self.assertTrue(request.get_header("Authorization").startswith("Bearer "))
            self.assertFalse(b"service_role" in request.data)
            self.assertNotIn(b"provider", request.data)

    def test_anonymous_and_expired_tokens_rejected_preflight(self):
        for role in ("anon", "service_role", "supabase_admin"):
            with self.subTest(role=role):
                with self.assertRaises(BulkPortAuthError):
                    RestrictedBulkHttpPort(KEY, fake_jwt(role), opener=FakeOpener([]))
        with self.assertRaises(BulkPortAuthError):
            RestrictedBulkHttpPort(KEY, fake_jwt(expiry=1), opener=FakeOpener([]))
        with self.assertRaises(BulkPortAuthError):
            RestrictedBulkHttpPort(KEY, "malformed", opener=FakeOpener([]))

    def test_public_key_must_not_be_secret(self):
        with self.assertRaises(ValueError):
            RestrictedBulkHttpPort("sb_secret_" + "a" * 24, fake_jwt(), opener=FakeOpener([]))

    def test_invalid_claim_or_page_never_sends_request(self):
        port, opener = self.port([])
        claim = {"work_key": WORK, "claim_owner": OWNER, "claim_fence": 1}
        for action in [
            lambda: port.admission("invalid"),
            lambda: port.claim_retained(MANIFEST, OWNER, 181),
            lambda: port.claim_retained(MANIFEST, OWNER, True),
            lambda: port.claim_retained(MANIFEST, "worker/with/slash", 60),
            lambda: port.commit_retained_page({**claim, "claim_fence": True}, 0),
            lambda: port.commit_retained_page(claim, -1),
            lambda: port.readback_receipt("not-a-work-key", 0),
            lambda: port._rpc("run_any_sql", {"sql": "DELETE"}),
        ]:
            with self.assertRaises(BulkPortError):
                action()
        self.assertEqual(opener.calls, [])

    def test_inconsistent_readback_fails_closed_with_no_write_retry(self):
        port, opener = self.port([{
            "work_key": WORK, "page_no": 0,
            "records_committed": 2, "requests_committed": 0,
            "source_sha256": "c" * 64, "output_sha256": "d" * 64,
            "consistent": False, "actual_records": 1,
            "actual_output_sha256": "e" * 64,
        }])
        with self.assertRaises(BulkPortError):
            port.readback_receipt(WORK, 0)
        self.assertEqual(len(opener.calls), 1)

    def test_explicit_auth_denial_is_not_retried(self):
        url = "https://oxzabweahkoimtevbbny.supabase.co/rest/v1/rpc/bulk_runtime_admission_v1"
        port, opener = self.port([HTTPError(url, 403, "blocked", {}, None)])
        with self.assertRaises(BulkPortAuthError):
            port.admission(MANIFEST)
        self.assertEqual(len(opener.calls), 1)

    def test_redirect_and_untrusted_response_refused(self):
        class Redirect(FakeOpener):
            def open(self, request, timeout):
                self.calls.append((request, timeout))
                return FakeResponse(request, {"status": "ok"}, url="https://evil.example/api")
        opener = Redirect([])
        port = RestrictedBulkHttpPort(KEY, fake_jwt(), opener=opener)
        with self.assertRaises(BulkPortError):
            port.admission(MANIFEST)
        self.assertEqual(len(opener.calls), 1)


if __name__ == "__main__":
    unittest.main()
