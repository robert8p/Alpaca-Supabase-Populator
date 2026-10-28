import base64
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from astra_ingestion import api
from astra_ingestion.store import Store

HAS_ASGI = all(importlib.util.find_spec(name) is not None for name in ("fastapi", "httpx"))


def authorization(password="correct-test-password"):
    return "Basic " + base64.b64encode(("rob:" + password).encode()).decode()


def spec():
    return {"symbols": ["AAPL"], "start": "2025-09-02T13:30:00Z", "end": "2025-09-02T20:00:00Z"}


class ASGIImportTests(unittest.TestCase):
    def test_module_import_does_not_import_runtime_dependencies(self):
        original = __import__
        def guarded(name, *args, **kwargs):
            if name == "fastapi" or name.startswith("starlette") or name == "uvicorn":
                raise AssertionError("Runtime dependency imported eagerly")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=guarded):
            importlib.reload(api)


@unittest.skipUnless(HAS_ASGI, "ASGI qualification NOT_RUN: pinned FastAPI and httpx dependencies are unavailable")
class ASGITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        self.folder = tempfile.TemporaryDirectory(prefix="astra-asgi-test-")
        self.store = Store("sqlite:///" + str(Path(self.folder.name) / "test.db"), test_mode=True)
        self.store.migrate()
        self.settings = SimpleNamespace(database_url=self.store.database_url, username="rob", password="correct-test-password", test_mode=True, service_version="1.0.0")
        self.client = TestClient(api.create_app(self.settings, self.store))
        self.headers = {"Authorization": authorization(), "X-Ingestion-Control": "1", "Idempotency-Key": "asgi-test-key-0001"}

    def tearDown(self):
        self.client.close()
        self.folder.cleanup()

    def submit(self, headers=None, value=None):
        return self.client.post("/api/jobs", json={"spec": spec() if value is None else value}, headers=self.headers if headers is None else headers)

    def test_health_is_public_minimal_and_truthful(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "version": "1.0.0"})
        with patch.object(self.store, "health", return_value={"ready": False}):
            self.assertEqual(self.client.get("/healthz").status_code, 503)

    def test_authentication_assets_and_duplicate_credentials(self):
        denied = self.client.get("/api/jobs")
        self.assertEqual(denied.status_code, 401)
        self.assertIn("Basic", denied.headers["www-authenticate"])
        response = self.client.get("/", headers={"Authorization": authorization()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        duplicate = self.client.get("/api/jobs", headers=[("Authorization", authorization()), ("Authorization", authorization())])
        self.assertEqual(duplicate.status_code, 401)

    def test_job_submission_is_idempotent_and_scope_bound(self):
        first, second = self.submit(), self.submit()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["job"]["id"], second.json()["job"]["id"])
        changed = self.submit(value={**spec(), "symbols": ["MSFT"]})
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(len(self.store.list_jobs()), 1)
        short = self.submit(headers={**self.headers, "Idempotency-Key": "short"})
        self.assertEqual(short.status_code, 400)

    def test_control_headers_and_origin_are_enforced(self):
        missing = self.submit(headers={"Authorization": authorization(), "Idempotency-Key": "asgi-key-0001"})
        self.assertEqual(missing.status_code, 403)
        cross = self.submit(headers={**self.headers, "Origin": "http://other.example"})
        self.assertEqual(cross.status_code, 403)
        duplicate_headers = list(self.headers.items()) + [("Origin", "http://testserver"), ("Origin", "http://testserver")]
        self.assertEqual(self.submit(headers=duplicate_headers).status_code, 403)
        self.assertEqual(self.submit(headers={**self.headers, "Origin": "http://testserver"}).status_code, 200)
        self.assertEqual(self.client.options("/api/jobs").status_code, 403)

    def test_body_bounds_and_json_contract(self):
        streamed = iter((b'{"padding":"', b"x" * (16 * 1024), b'"}'))
        response = self.client.post("/api/jobs", content=streamed, headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        invalid = self.client.post("/api/jobs", content=b'{"spec":{},"spec":{}}', headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.submit(value={**spec(), "unrecognised": True}).status_code, 409)

    def test_pause_resume_cancel_use_real_store_and_require_empty_objects(self):
        job_id = self.submit().json()["job"]["id"]
        for action, expected in (("pause", "paused"), ("resume", "running"), ("cancel", "cancelled")):
            response = self.client.post(f"/api/jobs/{job_id}/{action}", json={}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["job"]["status"], expected)
        extra = self.client.post(f"/api/jobs/{job_id}/resume", json={"release_hold": True}, headers=self.headers)
        self.assertEqual(extra.status_code, 400)

    def test_storage_errors_are_sanitized(self):
        with patch.object(self.store, "list_jobs", side_effect=RuntimeError("postgresql://secret:password@private.example/db")):
            response = self.client.get("/api/jobs", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("password", response.text)
        self.assertNotIn("private.example", response.text)

    def test_production_password_and_https_origin(self):
        from fastapi.testclient import TestClient
        self.settings.test_mode = False
        with self.assertRaises(ValueError):
            api.create_app(self.settings, self.store)
        self.settings.password = "p" * 32
        with TestClient(api.create_app(self.settings, self.store)) as production:
            headers = {**self.headers, "Authorization": authorization("p" * 32), "Origin": "http://testserver"}
            self.assertEqual(production.post("/api/jobs", json={"spec": spec()}, headers=headers).status_code, 403)
            headers["Origin"] = "https://testserver"
            response = production.post("/api/jobs", json={"spec": spec()}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
