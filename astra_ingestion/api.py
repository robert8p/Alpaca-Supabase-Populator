"""Production ASGI control surface; import is inert and dependency-free.

FastAPI is imported only by create_app. The factory does not migrate the
database, start workers, or import the legacy scanner application.
"""

import asyncio
import base64
import binascii
import hmac
import json
import logging
from pathlib import Path
import re
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
MAX_BODY = 16 * 1024
BODY_TIMEOUT_SECONDS = 10
JOB_ROUTE = re.compile(r"^/api/jobs/([A-Za-z0-9_-]{1,100})$")
CONTROL_ROUTE = re.compile(r"^/api/jobs/([A-Za-z0-9_-]{1,100})/(pause|resume|cancel)$")
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


def _normal_host(value, scheme):
    parsed = urlsplit(f"{scheme}://{value}")
    if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Invalid host")
    return parsed.hostname.lower(), parsed.port or (443 if scheme == "https" else 80)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON field")
        value[key] = item
    return value


def _invalid_constant(_value):
    raise ValueError("Invalid JSON number")


def create_app(settings=None, store=None):
    """Build an authenticated app with explicit, injectable dependencies."""
    try:
        from fastapi import FastAPI, Request
        from starlette.concurrency import run_in_threadpool
        from starlette.requests import ClientDisconnect
        from starlette.responses import JSONResponse, Response
    except ImportError as exc:
        raise RuntimeError("Install the pinned ingestion ASGI runtime dependencies") from exc

    from .config import Settings
    from .models import IngestionSpec
    from .rpc_store import create_store

    settings = Settings.from_env() if settings is None else settings
    store = create_store(settings) if store is None else store
    username = str(settings.username).encode("utf-8")
    password = str(settings.password).encode("utf-8")
    test_mode = bool(getattr(settings, "test_mode", False))
    if not username or b":" in username or not password:
        raise ValueError("An ingestion username and password are required")
    if not test_mode and len(password) < 32:
        raise ValueError("The ingestion password must contain at least 32 bytes")
    version = str(getattr(settings, "service_version", "1.0.0"))
    app = FastAPI(title="ASTRA Ingestion", docs_url=None, redoc_url=None, openapi_url=None, debug=False)

    def send(status, body, *, challenge=False):
        headers = {"WWW-Authenticate": 'Basic realm="ASTRA Ingestion", charset="UTF-8"'} if challenge else None
        return JSONResponse(body, status_code=status, headers=headers)

    def header_values(request, name):
        key = name.lower().encode("ascii")
        return [value.decode("latin-1") for field, value in request.scope.get("headers", []) if field.lower() == key]

    def authenticated(request):
        values = header_values(request, "Authorization")
        if len(values) != 1:
            return False
        try:
            method, encoded = values[0].split(" ", 1)
            decoded = base64.b64decode(encoded, validate=True)
            given_user, given_password = decoded.split(b":", 1)
            user_matches = hmac.compare_digest(given_user, username)
            password_matches = hmac.compare_digest(given_password, password)
            return method.lower() == "basic" and user_matches and password_matches
        except (ValueError, binascii.Error):
            return False

    def control_allowed(request):
        if header_values(request, "X-Ingestion-Control") != ["1"]:
            return False
        hosts, origins = header_values(request, "Host"), header_values(request, "Origin")
        if len(hosts) != 1 or len(origins) > 1:
            return False
        scheme = "http" if test_mode else "https"
        try:
            expected = _normal_host(hosts[0], scheme)
            if origins:
                origin = urlsplit(origins[0])
                actual = _normal_host(origin.netloc, origin.scheme)
                if origin.scheme != scheme or origin.path or origin.query or origin.fragment or actual != expected:
                    return False
        except ValueError:
            return False
        return True

    async def body(request):
        lengths = header_values(request, "Content-Length")
        if len(lengths) > 1 or lengths and not lengths[0].isdigit():
            return None, send(400, {"error": "Supply one valid Content-Length when present."})
        if lengths and int(lengths[0]) > MAX_BODY:
            return None, send(413, {"error": "The request body exceeds 16 KiB."})
        content_types = header_values(request, "Content-Type")
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            return None, send(415, {"error": "Content-Type must be application/json."})

        async def bounded_read():
            chunks, total = [], 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_BODY:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)

        try:
            raw = await asyncio.wait_for(bounded_read(), timeout=BODY_TIMEOUT_SECONDS)
            if raw is None:
                return None, send(413, {"error": "The request body exceeds 16 KiB."})
            if lengths and len(raw) != int(lengths[0]):
                raise ValueError("Incomplete request body")
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
            if not isinstance(value, dict):
                raise ValueError("Expected object")
            return value, None
        except TimeoutError:
            return None, send(408, {"error": "The request body did not arrive in time."})
        except (UnicodeDecodeError, ValueError, RecursionError, ClientDisconnect):
            return None, send(400, {"error": "The request must contain a complete JSON object."})

    def failure(exc):
        if isinstance(exc, KeyError):
            return send(404, {"error": "The requested job does not exist."})
        if isinstance(exc, (ValueError, TypeError)):
            return send(409, {"error": "The request violates the ingestion contract or current job state."})
        LOGGER.error("Ingestion persistence request failed (%s)", type(exc).__name__)
        return send(503, {"error": "Ingestion storage is temporarily unavailable."})

    @app.middleware("http")
    async def secure_responses(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:
            response = failure(exc)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        if not test_mode:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "OPTIONS", "PUT", "PATCH", "DELETE"])
    async def dispatch(request: Request, path: str):
        route = "/" + path
        method = request.method
        if method in {"GET", "HEAD"} and route == "/healthz":
            try:
                state = await run_in_threadpool(store.health)
                ready = isinstance(state, dict) and state.get("ready") is True
            except Exception:
                ready = False
            return send(200 if ready else 503, {"status": "ready" if ready else "unavailable", "version": version})
        if method == "OPTIONS":
            return send(403, {"error": "Cross-origin access is not enabled."})
        if method not in {"GET", "HEAD", "POST"}:
            return send(405, {"error": "Method not allowed."})
        if not authenticated(request):
            return send(401, {"error": "Authentication required."}, challenge=True)
        try:
            if method in {"GET", "HEAD"}:
                assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/styles.css": ("styles.css", "text/css")}
                if route in assets:
                    filename, mime = assets[route]
                    content = await run_in_threadpool((STATIC / filename).read_bytes)
                    return Response(content, media_type=mime)
                if route == "/api/jobs":
                    return send(200, {"jobs": await run_in_threadpool(store.list_jobs, limit=50)})
                match = JOB_ROUTE.fullmatch(route)
                if match:
                    job = await run_in_threadpool(store.get_job, match.group(1))
                    if job is None:
                        raise KeyError(match.group(1))
                    return send(200, {"job": job})
                return send(404, {"error": "Not found."})

            if not control_allowed(request):
                return send(403, {"error": "The request origin or ingestion control header is not allowed."})
            value, error = await body(request)
            if error is not None:
                return error
            if route == "/api/jobs":
                keys = header_values(request, "Idempotency-Key")
                if len(keys) != 1 or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", keys[0]):
                    return send(400, {"error": "Supply a valid Idempotency-Key of 8 to 128 characters."})
                if set(value) != {"spec"} or not isinstance(value["spec"], dict):
                    return send(400, {"error": "Supply one spec object."})
                spec = IngestionSpec.from_dict(value["spec"])
                return send(200, {"job": await run_in_threadpool(store.submit_job, spec, keys[0])})
            match = CONTROL_ROUTE.fullmatch(route)
            if match:
                if value:
                    return send(400, {"error": "Job controls require an empty JSON object."})
                return send(200, {"job": await run_in_threadpool(store.control_job, match.group(1), match.group(2))})
            return send(404, {"error": "Not found."})
        except Exception as exc:
            return failure(exc)

    return app
