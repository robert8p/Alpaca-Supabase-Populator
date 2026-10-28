from __future__ import annotations

import base64
import http.client
import io
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from astra_ingestion.web import make_handler, make_server


class MemorySocket:
    def __init__(self, request=b""):
        self.input = io.BytesIO(request)
        self.output = bytearray()

    def makefile(self, *_args, **_kwargs):
        return self.input

    def sendall(self, value):
        self.output.extend(value)

    def settimeout(self, _value):
        pass


class FakeSpec:
    @classmethod
    def from_dict(cls, data):
        if not data.get("symbols"):
            raise ValueError("Explicit symbols are required")
        obj = cls()
        obj.data = data
        return obj


class FakeStore:
    def __init__(self):
        self.jobs = {}
        self.keys = {}
        self.controls = []
        self.fail = False

    def health(self):
        if self.fail:
            raise RuntimeError("postgres://operator:SECRET@db/private")
        return {"status": "ok", "private_connection": "must-not-be-returned"}

    def list_jobs(self, limit=50):
        if self.fail:
            raise RuntimeError("postgres://operator:SECRET@db/private")
        return list(self.jobs.values())[:limit]

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def submit_job(self, spec, request_key):
        if request_key in self.keys:
            if self.keys[request_key][0] != spec.data:
                raise ValueError("Idempotency conflict")
            return self.keys[request_key][1]
        job = {"id": f"job-{len(self.jobs)+1}", "name": spec.data.get("name", "Test job"), "spec": spec.data, "status": "queued", "verification_status": "pending", "record_count": 0, "request_count": 0, "partitions": [], "events": []}
        self.jobs[job["id"]] = job
        self.keys[request_key] = (spec.data, job)
        return job

    def control_job(self, job_id, action):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        job = self.jobs[job_id]
        if job["status"] == "blocked":
            raise ValueError("Quality holds cannot be released by controls")
        self.controls.append((job_id, action))
        job["status"] = {"pause": "paused", "resume": "queued", "cancel": "cancelled"}[action]
        return job


class WebContractTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(username="operator", password="a-test-password-that-is-long-enough", test_mode=True, service_version="test-version")
        self.store = FakeStore()
        self.model_patch = patch.dict(sys.modules, {"astra_ingestion.models": SimpleNamespace(IngestionSpec=FakeSpec)})
        self.model_patch.start()
        self.addCleanup(self.model_patch.stop)

    def request(self, path="/api/jobs", method="GET", body=None, headers=None, authenticated=True, raw_body=None):
        items = [("Host", "localhost:8123")]
        if authenticated:
            token = base64.b64encode(f"{self.settings.username}:{self.settings.password}".encode()).decode()
            items.append(("Authorization", "Basic " + token))
        raw = raw_body if raw_body is not None else json.dumps(body if body is not None else {}).encode()
        if method == "POST":
            items.extend([("Content-Type", "application/json"), ("Content-Length", str(len(raw))), ("X-Ingestion-Control", "1")])
        if headers:
            for key, value in headers.items():
                items = [(k, v) for k, v in items if k.lower() != key.lower()]
                if value is not None:
                    items.append((key, value))
        request = f"{method} {path} HTTP/1.1\r\n".encode() + b"".join(f"{k}: {v}\r\n".encode() for k, v in items) + b"\r\n"
        if method == "POST":
            request += raw
        connection = MemorySocket(request)
        make_handler(self.settings, self.store)(connection, ("127.0.0.1", 10000), SimpleNamespace())
        response = http.client.HTTPResponse(MemorySocket(bytes(connection.output)), method=method)
        response.begin()
        payload = response.read()
        return response.status, dict(response.getheaders()), payload

    def submit(self, key="request-1", spec=None, **kwargs):
        return self.request("/api/jobs", "POST", {"spec": spec or {"symbols": ["AAPL"]}}, headers={"Idempotency-Key": key, **kwargs.pop("headers", {})}, **kwargs)

    def test_authentication_challenge_and_no_store_access(self):
        self.store.fail = True
        status, headers, body = self.request(authenticated=False)
        self.assertEqual(status, 401)
        self.assertIn("Basic", headers["WWW-Authenticate"])
        self.assertNotIn(b"SECRET", body)

    def test_wrong_password_and_malformed_basic_rejected(self):
        for authorization in ["Bearer abc", "Basic !!!!", "Basic " + base64.b64encode(b"operator:wrong").decode()]:
            with self.subTest(authorization=authorization):
                self.assertEqual(self.request(headers={"Authorization": authorization})[0], 401)

    def test_public_health_is_minimal_and_failure_is_unavailable(self):
        status, _, body = self.request("/healthz", authenticated=False)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ready", "version": "test-version"})
        self.store.fail = True
        status, _, body = self.request("/healthz", authenticated=False)
        self.assertEqual(status, 503)
        self.assertNotIn(b"SECRET", body)

    def test_same_origin_mutation_and_replay_keep_one_job(self):
        first = self.submit(headers={"Origin": "http://localhost:8123"})
        second = self.submit(headers={"Origin": "http://localhost:8123"})
        self.assertEqual(first[0], 200)
        self.assertEqual(json.loads(first[2])["job"]["id"], json.loads(second[2])["job"]["id"])
        self.assertEqual(len(self.store.jobs), 1)

    def test_key_reuse_with_changed_scope_is_conflict(self):
        self.assertEqual(self.submit()[0], 200)
        self.assertEqual(self.submit(spec={"symbols": ["MSFT"]})[0], 409)
        self.assertEqual(len(self.store.jobs), 1)

    def test_cross_origin_and_missing_control_header_rejected(self):
        for origin in ["http://evil.example", "http://localhost:8124", "null", "http://localhost:8123/path", "http://user@localhost:8123"]:
            with self.subTest(origin=origin):
                self.assertEqual(self.submit(headers={"Origin": origin})[0], 403)
        self.assertEqual(self.submit(headers={"X-Ingestion-Control": None})[0], 403)
        self.assertEqual(len(self.store.jobs), 0)

    def test_forwarded_header_cannot_relax_production_https_origin(self):
        self.settings.test_mode = False
        self.assertEqual(self.submit(headers={"Origin": "http://localhost:8123", "X-Forwarded-Proto": "https"})[0], 403)
        self.assertEqual(self.submit(headers={"Origin": "https://localhost:8123"})[0], 200)

    def test_missing_invalid_and_oversized_idempotency_keys_rejected(self):
        for key in ["", "x" * 129, "contains a space"]:
            with self.subTest(key=key):
                self.assertEqual(self.submit(key=key)[0], 400)

    def test_body_bounds_encoding_and_content_type(self):
        cases = [
            ({"Content-Length": "17000"}, b"{}", 413),
            ({"Transfer-Encoding": "chunked"}, b"{}", 400),
            ({"Content-Length": None}, b"{}", 400),
            ({"Content-Type": "text/plain"}, b"{}", 415),
            ({}, b"{broken", 400),
            ({}, b"[]", 400),
            ({}, b"{\"spec\":NaN}", 400),
            ({}, b"\xff", 400),
        ]
        for headers, body, expected in cases:
            with self.subTest(headers=headers, body=body):
                self.assertEqual(self.request("/api/jobs", "POST", headers={"Idempotency-Key": "body-test", **headers}, raw_body=body)[0], expected)

    def test_get_job_controls_and_held_work_cannot_resume(self):
        self.submit()
        status, _, body = self.request("/api/jobs/job-1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["job"]["verification_status"], "pending")
        self.assertEqual(self.request("/api/jobs/job-1/pause", "POST", {})[0], 200)
        self.assertEqual(self.store.jobs["job-1"]["status"], "paused")
        self.store.jobs["job-1"]["status"] = "blocked"
        self.assertEqual(self.request("/api/jobs/job-1/resume", "POST", {})[0], 409)
        self.assertEqual(self.store.jobs["job-1"]["status"], "blocked")
        self.assertEqual(self.request("/api/jobs/missing/cancel", "POST", {})[0], 404)

    def test_database_failure_is_sanitized(self):
        self.store.fail = True
        status, _, body = self.request()
        self.assertEqual(status, 503)
        self.assertNotIn(b"postgres", body)
        self.assertNotIn(b"SECRET", body)

    def test_static_assets_auth_headers_head_and_path_traversal(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"ASTRA Ingestion", body)
        self.assertNotIn(self.settings.password.encode(), body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("/app.js", authenticated=False)[0], 401)
        self.assertEqual(self.request("/styles.css")[0], 200)
        self.assertEqual(self.request("/../config.py")[0], 404)
        self.assertEqual(self.request("/", "HEAD")[2], b"")

    def test_no_cors_and_unsupported_controls(self):
        status, headers, _ = self.request("/api/jobs", "OPTIONS", authenticated=False)
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.request("/api/jobs/job-1/release", "POST", {})[0], 404)

    def test_production_password_requirement(self):
        self.settings.test_mode = False
        self.settings.password = "short"
        with self.assertRaises(ValueError):
            make_handler(self.settings, self.store)


if __name__ == "__main__":
    unittest.main()
