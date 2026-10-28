"""Small authenticated control surface for the isolated ingestion service.

The web process never imports the legacy scanner package or starts a worker.
This standard-library transport is for local qualification only; production
uses astra_ingestion.serve (Uvicorn/ASGI).
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
MAX_BODY = 16 * 1024
JOB_ROUTE = re.compile(r"^/api/jobs/([A-Za-z0-9_-]{1,100})$")
CONTROL_ROUTE = re.compile(r"^/api/jobs/([A-Za-z0-9_-]{1,100})/(pause|resume|cancel)$")


def _normal_host(value: str, scheme: str) -> tuple[str, int]:
    parsed = urlsplit(f"{scheme}://{value}")
    if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Invalid host")
    return parsed.hostname.lower(), parsed.port or (443 if scheme == "https" else 80)


def make_handler(settings, store):
    """Return a handler bound to explicit settings and a persistence adapter."""
    username = str(settings.username).encode("utf-8")
    password = str(settings.password).encode("utf-8")
    if not username or b":" in username or not password:
        raise ValueError("An ingestion username and password are required")
    if not getattr(settings, "test_mode", False) and len(password) < 32:
        raise ValueError("The ingestion password must contain at least 32 bytes")
    version = str(getattr(settings, "service_version", "1.0.0"))

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ASTRAIngestion"
        sys_version = ""

        def setup(self):
            self.request.settimeout(10)
            super().setup()

        def log_message(self, _format, *_args):
            # Request URLs, headers, credentials and payloads stay out of logs.
            return

        def _send(self, status, body, content_type="application/json; charset=utf-8", *, challenge=False):
            data = json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8") if isinstance(body, dict) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.send_header("Connection", "close")
            if challenge:
                self.send_header("WWW-Authenticate", 'Basic realm="ASTRA Ingestion", charset="UTF-8"')
            self.end_headers()
            self.close_connection = True
            if self.command != "HEAD":
                self.wfile.write(data)

        def _authenticated(self):
            headers = self.headers.get_all("Authorization", [])
            valid = False
            if len(headers) == 1:
                try:
                    method, encoded = headers[0].split(" ", 1)
                    decoded = base64.b64decode(encoded, validate=True)
                    given_user, given_password = decoded.split(b":", 1)
                    user_matches = hmac.compare_digest(given_user, username)
                    password_matches = hmac.compare_digest(given_password, password)
                    valid = method.lower() == "basic" and user_matches and password_matches
                except (ValueError, binascii.Error):
                    pass
            if not valid:
                self._send(401, {"error": "Authentication required."}, challenge=True)
            return valid

        def _control_allowed(self):
            if self.headers.get_all("X-Ingestion-Control", []) != ["1"]:
                self._send(403, {"error": "An explicit ingestion control header is required."})
                return False
            origins = self.headers.get_all("Origin", [])
            hosts = self.headers.get_all("Host", [])
            if len(hosts) != 1 or len(origins) > 1:
                self._send(403, {"error": "The request origin is not allowed."})
                return False
            if origins:
                try:
                    origin = urlsplit(origins[0])
                    # Production is HTTPS behind a TLS proxy. Forwarded headers
                    # are never trusted to relax this rule.
                    scheme = "http" if getattr(settings, "test_mode", False) else "https"
                    expected = _normal_host(hosts[0], scheme)
                    actual = _normal_host(origin.netloc, origin.scheme)
                    valid = origin.scheme == scheme and not origin.path and not origin.query and not origin.fragment and actual == expected
                except ValueError:
                    valid = False
                if not valid:
                    self._send(403, {"error": "The request origin is not allowed."})
                    return False
            return True

        def _body(self):
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit():
                self._send(400, {"error": "Supply one valid Content-Length and a JSON body."})
                return None
            size = int(lengths[0])
            if size > MAX_BODY:
                self._send(413, {"error": "The request body exceeds 16 KiB."})
                return None
            if self.headers.get_content_type() != "application/json":
                self._send(415, {"error": "Content-Type must be application/json."})
                return None
            try:
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError("Incomplete body")
                value = json.loads(raw.decode("utf-8"), parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("Invalid number")))
                if not isinstance(value, dict):
                    raise ValueError("Expected object")
                return value
            except (UnicodeDecodeError, ValueError, TimeoutError):
                self._send(400, {"error": "The request must contain a complete JSON object."})
                return None

        def _failure(self, exc):
            if isinstance(exc, KeyError):
                self._send(404, {"error": "The requested job does not exist."})
            elif isinstance(exc, (ValueError, TypeError)):
                self._send(409, {"error": "The request violates the ingestion contract or current job state."})
            else:
                LOGGER.error("Ingestion persistence request failed (%s)", type(exc).__name__)
                self._send(503, {"error": "Ingestion storage is temporarily unavailable."})

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/healthz":
                try:
                    state = store.health()
                    ready = isinstance(state, dict) and state.get("ok", True) is not False and state.get("status", "ok") in {"ok", "ready", "healthy"}
                    self._send(200 if ready else 503, {"status": "ready" if ready else "unavailable", "version": version})
                except Exception:
                    self._send(503, {"status": "unavailable", "version": version})
                return
            if not self._authenticated():
                return
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8")}
            try:
                if path in assets:
                    filename, mime = assets[path]
                    self._send(200, (STATIC / filename).read_bytes(), mime)
                elif path == "/api/jobs":
                    self._send(200, {"jobs": store.list_jobs(limit=50)})
                elif match := JOB_ROUTE.fullmatch(path):
                    job = store.get_job(match.group(1))
                    if job is None:
                        raise KeyError(match.group(1))
                    self._send(200, {"job": job})
                else:
                    self._send(404, {"error": "Not found."})
            except Exception as exc:
                self._failure(exc)

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            if not self._authenticated() or not self._control_allowed():
                return
            body = self._body()
            if body is None:
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/jobs":
                    from .models import IngestionSpec
                    keys = self.headers.get_all("Idempotency-Key", [])
                    if len(keys) != 1 or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", keys[0]):
                        self._send(400, {"error": "Supply a valid Idempotency-Key of 8 to 128 characters."})
                        return
                    if set(body) != {"spec"} or not isinstance(body["spec"], dict):
                        self._send(400, {"error": "Supply one spec object."})
                        return
                    job = store.submit_job(IngestionSpec.from_dict(body["spec"]), keys[0])
                    self._send(200, {"job": job})
                elif match := CONTROL_ROUTE.fullmatch(path):
                    if body:
                        self._send(400, {"error": "Job controls require an empty JSON object."})
                        return
                    self._send(200, {"job": store.control_job(match.group(1), match.group(2))})
                else:
                    self._send(404, {"error": "Not found."})
            except Exception as exc:
                self._failure(exc)

        def do_OPTIONS(self):
            self._send(403, {"error": "Cross-origin access is not enabled."})

        def do_PUT(self):
            self._send(405, {"error": "Method not allowed."})

        do_PATCH = do_PUT
        do_DELETE = do_PUT

    return Handler


def make_server(settings, store, host="127.0.0.1", port=0):
    server = ThreadingHTTPServer((host, port), make_handler(settings, store))
    server.daemon_threads = True
    return server


def main():
    from .config import Settings
    from .store import Store
    settings = Settings.from_env()
    if not settings.test_mode:
        raise SystemExit("Use python -m astra_ingestion.serve for production")
    server = make_server(settings, Store(settings.database_url), host=settings.host, port=settings.port)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
