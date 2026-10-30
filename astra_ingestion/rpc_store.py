"""Bounded HTTPS persistence through the fixed ingestion RPC.

Runtime services hold only a public project key and their own capability token.
They never receive a database login, project signing secret or service-role key.
An uncertain HTTP result is fatal to that worker invocation. Only a complete
PostgREST lock-abort response can retry an explicitly listed database RPC.
"""
from __future__ import annotations

import json
import re
import ssl
from http.client import HTTPException
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .models import IngestionSpec
from .source import record_key
from .store import LeaseLost, QualityHold, RequestDeferred

PROJECT_REF = "oxzabweahkoimtevbbny"
PROJECT_URL = "https://" + PROJECT_REF + ".supabase.co"
RPC_PATH = "/rest/v1/rpc/astra_ingestion_rpc_v1"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
RPC_TIMEOUT_SECONDS = 15
TOKEN_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

# These database-only calls still pass through the existing authenticated,
# fenced RPC. This is a retry policy, never an operation authorization gate.
LOCK_ABORT_RETRY_OPERATIONS = frozenset({
    "backfill_claim", "backfill_reserve", "backfill_commit",
    "backfill_reuse_commit", "backfill_verify", "backfill_plan_next",
})
LOCK_ABORT_RETRY_DELAYS = (0.25, 0.75)
MAX_LOCK_ABORT_ERROR_BYTES = 8192

# Diagnostic labels only: this does not authorize any operation. The existing
# remote capability gate remains the sole operation authorization boundary.
RPC_DIAGNOSTIC_OPERATIONS = frozenset({
    "health", "list_jobs", "get_job", "submit_job", "control_job", "claim_next",
    "reserve_request", "commit_page", "verification_material", "finish_verification",
    "fail_claim", "backfill_status", "backfill_claim", "backfill_reserve",
    "backfill_commit", "backfill_defer", "backfill_verify", "backfill_material",
    "backfill_work", "backfill_massive_archive_read", "backfill_massive_archive_commit",
    "backfill_massive_archive_verify", "backfill_identity_material",
    "backfill_identity_source_read", "backfill_identity_source_commit",
    "backfill_identity_refresh", "backfill_breadth_material", "backfill_breadth_project",
    "backfill_delivery_status", "backfill_finalize", "backfill_recover", "backfill_maintain",
    "backfill_plan_snapshot", "backfill_seal_plan", "backfill_plan_next",
    "backfill_reuse_read", "backfill_feature_reuse_commit", "backfill_feature_reuse_verify",
    "backfill_reuse_verify", "backfill_reuse_commit", "backfill_relay_probe",
    "backfill_relay_dispatch",
})
RPC_DIAGNOSTIC_REASONS = frozenset({
    "UNEXPECTED_HTTP_STATUS", "REDIRECT_REFUSED", "RESPONSE_FORMAT",
    "RESPONSE_BOUND", "RESPONSE_DEADLINE", "RESPONSE_INCOMPLETE",
    "HTTP_AUTH_REJECTED", "HTTP_ERROR", "TRANSPORT_ERROR", "RESPONSE_DECODE",
    "RESPONSE_ENVELOPE", "REMOTE_FAILURE_UNRECOGNIZED", "UNCLASSIFIED_PERSISTENCE_FAILURE",
    "LOCK_ABORT_RETRY_EXHAUSTED",
})


def _diagnostic_label(value, allowed, fallback):
    # A string subclass can supply a hostile __hash__/__eq__. Do not coerce,
    # format or retain anything except one exact, bounded local enum value.
    return value if type(value) is str and len(value) <= 64 and value in allowed else fallback


class RpcPersistenceError(RuntimeError):
    """The caller must reconcile durable state before another mutation."""

    def __init__(self, *args, reason_code=None):
        super().__init__(*args)
        self.rpc_operation = "UNKNOWN"
        self.rpc_failure_reason = _diagnostic_label(
            reason_code, RPC_DIAGNOSTIC_REASONS, "UNCLASSIFIED_PERSISTENCE_FAILURE")


class RpcAuthenticationError(RpcPersistenceError):
    pass


def rpc_failure_fields(error):
    """Only fixed local labels may enter logs; never inspect messages or causes."""
    if not isinstance(error, RpcPersistenceError):
        return {}
    attributes = BaseException.__getattribute__(error, "__dict__")
    return {
        "rpc_operation": _diagnostic_label(dict.get(attributes, "rpc_operation"), RPC_DIAGNOSTIC_OPERATIONS, "UNKNOWN"),
        "rpc_failure_reason": _diagnostic_label(dict.get(attributes, "rpc_failure_reason"), RPC_DIAGNOSTIC_REASONS,
                                                "UNCLASSIFIED_PERSISTENCE_FAILURE"),
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # Never forward a capability token, including to another project.
        return None


def validate_endpoint(value: str, project_ref: str = PROJECT_REF) -> str:
    parsed = urlsplit(value)
    if (project_ref != PROJECT_REF or parsed.scheme != "https"
            or parsed.netloc != PROJECT_REF + ".supabase.co"
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("The ingestion API must use the exact admitted Supabase project HTTPS origin")
    return PROJECT_URL


def validate_public_key(value: str) -> None:
    # New publishable keys and legacy anon JWTs are both public gateway keys.
    # Explicitly reject a secret/service-role key even if it would work upstream.
    if not isinstance(value, str) or not value or len(value) > 4096 or any(not 33 <= ord(c) <= 126 for c in value):
        raise ValueError("A Supabase publishable or legacy anon key is required")
    if re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{16,}", value):
        return
    if value.count(".") == 2:
        import base64
        try:
            encoded = value.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if isinstance(claims, dict) and claims.get("role") == "anon" and claims.get("ref") == PROJECT_REF:
                return
        except (ValueError, TypeError, UnicodeError):
            pass
    raise ValueError("Only a publishable key or an anon key bound to the admitted project is accepted")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response field")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Non-finite JSON value")


class RpcStore:
    def __init__(self, api_url: str, publishable_key: str, token: str, *, project_ref=PROJECT_REF, opener=None):
        self.endpoint = validate_endpoint(api_url, project_ref) + RPC_PATH
        validate_public_key(publishable_key)
        if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
            raise ValueError("A dedicated 256-bit ingestion capability token is required")
        self._key = publishable_key
        self._token = token
        self._opener = opener if opener is not None else build_opener(
            _NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def _call(self, operation, payload):
        try:
            return self._call_once(operation, payload)
        except RpcPersistenceError as error:
            # Preserve the same fatal exception and uncertain-write semantics.
            # Only the transport's strict lock-abort path may retry; an exception
            # label supplied by a caller cannot authorize a resend.
            error.rpc_operation = _diagnostic_label(operation, RPC_DIAGNOSTIC_OPERATIONS, "UNKNOWN")
            raise

    def _call_once(self, operation, payload):
        encoded = json.dumps({"operation": operation, "payload": payload},
                             separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ValueError("The ingestion persistence request exceeds its bound")
        request = Request(self.endpoint, data=encoded, method="POST", headers={
            "apikey": self._key,
            "X-Astra-Ingestion-Token": self._token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-store",
        })
        deadline = monotonic() + RPC_TIMEOUT_SECONDS
        timeout = RPC_TIMEOUT_SECONDS
        eligible = type(operation) is str and operation in LOCK_ABORT_RETRY_OPERATIONS
        for attempt in range(len(LOCK_ABORT_RETRY_DELAYS) + 1):
            try:
                raw = self._exchange_once(request, deadline, timeout)
            except HTTPError as exc:
                try:
                    status = exc.code
                    confirmed = eligible and self._confirmed_lock_abort(exc, deadline)
                finally:
                    exc.close()
                if status in (401, 403):
                    raise RpcAuthenticationError("Ingestion capability was rejected", reason_code="HTTP_AUTH_REJECTED") from None
                if not confirmed:
                    raise RpcPersistenceError("Persistence HTTP outcome is unresolved; reconcile before continuing", reason_code="HTTP_ERROR") from None
                # The exact request bytes, claim, reservation and provider page
                # stay in this call. No provider method or enclosing work unit
                # is replayed, and the deadline is never reset after an abort.
                if attempt >= len(LOCK_ABORT_RETRY_DELAYS):
                    raise RpcPersistenceError("Persistence lock retry budget exhausted; reconcile before continuing", reason_code="LOCK_ABORT_RETRY_EXHAUSTED") from None
                delay = LOCK_ABORT_RETRY_DELAYS[attempt]
                if monotonic() + delay >= deadline:
                    raise RpcPersistenceError("Persistence lock retry budget exhausted; reconcile before continuing", reason_code="LOCK_ABORT_RETRY_EXHAUSTED") from None
                sleep(delay)
                timeout = min(RPC_TIMEOUT_SECONDS, deadline - monotonic())
                if timeout <= 0:
                    raise RpcPersistenceError("Persistence lock retry budget exhausted; reconcile before continuing", reason_code="LOCK_ABORT_RETRY_EXHAUSTED") from None
                continue
            break
        try:
            envelope = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                  parse_constant=_invalid_constant)
        except (UnicodeError, ValueError, RecursionError):
            raise RpcPersistenceError("Persistence returned an invalid response", reason_code="RESPONSE_DECODE") from None
        if not isinstance(envelope, dict) or type(envelope.get("ok")) is not bool:
            raise RpcPersistenceError("Persistence returned an invalid envelope", reason_code="RESPONSE_ENVELOPE")
        if envelope["ok"]:
            if set(envelope) != {"ok", "result"}:
                raise RpcPersistenceError("Persistence returned an invalid success envelope", reason_code="RESPONSE_ENVELOPE")
            return envelope["result"]
        error = envelope.get("error")
        if set(envelope) != {"ok", "error"} or not isinstance(error, dict):
            raise RpcPersistenceError("Persistence returned an invalid error envelope", reason_code="RESPONSE_ENVELOPE")
        # Use controlled local messages. A remote error must never echo credentials.
        failures = {
            "lease_lost": (LeaseLost, "Worker ownership or the job deadline is no longer valid"),
            "quality_hold": (QualityHold, "Persistence rejected the operation under its ingestion quality rules"),
            "request_deferred": (RequestDeferred, "Shared provider pacing"),
            "not_found": (KeyError, "The requested ingestion job does not exist"),
            "conflict": (ValueError, "The operation violates the ingestion contract or current job state"),
        }
        failure = failures.get(error.get("code"))
        if failure is None:
            raise RpcPersistenceError("Persistence returned an unrecognized failure", reason_code="REMOTE_FAILURE_UNRECOGNIZED")
        raise failure[0](failure[1])

    def _exchange_once(self, request, deadline, timeout):
        """One send; ambiguous transport/response outcomes always propagate."""
        try:
            response = self._opener.open(request, timeout=timeout)
        except HTTPError:
            # Only the response obtained when opening this request can supply
            # rollback evidence. A later stream failure is always ambiguous.
            raise
        except (URLError, TimeoutError, OSError, HTTPException):
            raise RpcPersistenceError("Persistence transport outcome is unresolved; reconcile before continuing", reason_code="TRANSPORT_ERROR") from None
        try:
            with response:
                if response.status != 200:
                    raise RpcPersistenceError("Unexpected persistence response; reconcile before continuing", reason_code="UNEXPECTED_HTTP_STATUS")
                if response.geturl() != self.endpoint:
                    raise RpcPersistenceError("Persistence redirect refused", reason_code="REDIRECT_REFUSED")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type != "application/json" or response.headers.get("Content-Encoding", "identity") != "identity":
                    raise RpcPersistenceError("Unexpected persistence response format", reason_code="RESPONSE_FORMAT")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE_BYTES):
                    raise RpcPersistenceError("Persistence response exceeds its bound", reason_code="RESPONSE_BOUND")
                chunks, total = [], 0
                while True:
                    if monotonic() >= deadline:
                        raise RpcPersistenceError("Persistence response deadline exceeded; reconcile before continuing", reason_code="RESPONSE_DEADLINE")
                    # read1 performs at most one underlying read. Unlike read(n),
                    # a peer cannot keep this call alive indefinitely by trickling
                    # bytes. The wall bound is the deadline plus one socket timeout.
                    chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - total))
                    if monotonic() >= deadline:
                        raise RpcPersistenceError("Persistence response deadline exceeded; reconcile before continuing", reason_code="RESPONSE_DEADLINE")
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise RpcPersistenceError("Persistence response exceeds its bound", reason_code="RESPONSE_BOUND")
                raw = b"".join(chunks)
                if len(raw) > MAX_RESPONSE_BYTES or length is not None and len(raw) != int(length):
                    raise RpcPersistenceError("Incomplete or oversized persistence response", reason_code="RESPONSE_INCOMPLETE")
        except (URLError, TimeoutError, OSError, HTTPException):
            raise RpcPersistenceError("Persistence transport outcome is unresolved; reconcile before continuing", reason_code="TRANSPORT_ERROR") from None
        return raw

    def _confirmed_lock_abort(self, response, deadline):
        """Recognize one fixed PostgREST error; never return remote error data.

        This relies on the reviewed fixed RPC contract: ordinary outcomes use
        the ok envelope and never manufacture custom HTTP-status error bodies.
        A code in a provider response, application envelope or exception text is
        not rollback evidence. Uncertain/incomplete bodies fail closed.
        """
        if type(response.code) is not int or response.code != 500 or response.geturl() != self.endpoint:
            return False
        headers = response.headers
        if headers is None:
            return False
        # Ambiguous framing is ineligible, even if a first header looks valid.
        for name in ("Content-Type", "Content-Encoding", "Content-Length", "Transfer-Encoding"):
            if hasattr(headers, "get_all") and len(headers.get_all(name, [])) > 1:
                return False
        if (headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json"
                or headers.get("Content-Encoding", "identity").strip().lower() != "identity"):
            return False
        length = headers.get("Content-Length")
        transfer = headers.get("Transfer-Encoding")
        if transfer is not None and (transfer.strip().lower() != "chunked" or length is not None):
            return False
        if length is not None and (not length.isascii() or not length.isdigit()
                                   or len(length) > 10 or int(length) > MAX_LOCK_ABORT_ERROR_BYTES):
            return False
        try:
            chunks, total = [], 0
            while True:
                if monotonic() >= deadline:
                    return False
                chunk = response.read1(min(1024, MAX_LOCK_ABORT_ERROR_BYTES + 1 - total))
                if monotonic() >= deadline:
                    return False
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_LOCK_ABORT_ERROR_BYTES:
                    return False
            raw = b"".join(chunks)
            if length is not None and len(raw) != int(length):
                return False
            envelope = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                  parse_constant=_invalid_constant)
        except (UnicodeError, ValueError, RecursionError, URLError, TimeoutError, OSError, HTTPException):
            return False
        return (type(envelope) is dict and set(envelope) == {"code", "message", "details", "hint"}
                and type(envelope["code"]) is str and envelope["code"] == "55P03"
                and type(envelope["message"]) is str
                and (envelope["details"] is None or type(envelope["details"]) is str)
                and (envelope["hint"] is None or type(envelope["hint"]) is str))

    @staticmethod
    def _claim(claim):
        return {key: claim[key] for key in ("id", "owner", "generation", "next_page_token")}

    def health(self):
        result = self._call("health", {})
        if not isinstance(result, dict) or result.get("ready") is not True or result.get("schema_version") != 1 or result.get("rpc_version") != 1:
            raise RpcPersistenceError("The ingestion API is not ready at the required version")
        return result

    def list_jobs(self, limit=50):
        result = self._call("list_jobs", {"limit": max(1, min(int(limit), 100))})
        if not isinstance(result, list):
            raise RpcPersistenceError("Invalid ingestion jobs response")
        return result

    def get_job(self, job_id):
        result = self._call("get_job", {"job_id": job_id})
        if result is not None and not isinstance(result, dict):
            raise RpcPersistenceError("Invalid ingestion job response")
        return result

    def submit_job(self, spec: IngestionSpec, request_key):
        result = self._call("submit_job", {"spec": spec.to_dict(), "request_key": request_key})
        if not isinstance(result, dict) or result.get("scope_hash") != spec.scope_hash:
            raise RpcPersistenceError("The admitted scope does not match the submitted scope")
        return result

    def control_job(self, job_id, action):
        if action not in ("pause", "resume", "cancel"):
            raise ValueError("Unsupported control")
        return self._call("control_job", {"job_id": job_id, "action": action})

    def backfill_status(self):
        from .backfill_status import public_backfill_status
        result = self._call("backfill_status", {})
        try:
            return public_backfill_status(result)
        except (ValueError, TypeError):
            raise RpcPersistenceError("Invalid replacement-run status response") from None

    def claim_next(self, worker_id, lease_seconds=90):
        result = self._call("claim_next", {"worker_id": worker_id, "lease_seconds": max(30, min(int(lease_seconds), 300))})
        if result is not None:
            if not isinstance(result, dict) or result.get("phase") not in ("fetch", "verify") or result.get("owner") != worker_id:
                raise RpcPersistenceError("Invalid worker claim response")
            IngestionSpec.from_dict(result["spec"])
            self._claim(result)
        return result

    def reserve_request(self, claim):
        return self._call("reserve_request", {"claim": self._claim(claim)})

    def commit_page(self, claim, fetched, parsed):
        return self._call("commit_page", {
            "claim": self._claim(claim), "raw_body": fetched.raw_text,
            "request_id": fetched.request_id, "records": list(parsed.records),
            "next_page_token": parsed.next_page_token, "response_sha256": parsed.response_sha256,
        })

    def verification_material(self, claim):
        result = self._call("verification_material", {"claim": self._claim(claim)})
        if not isinstance(result, dict) or set(result) != {"receipts", "records"} or not isinstance(result["receipts"], list) or not isinstance(result["records"], list):
            raise RpcPersistenceError("Invalid verification snapshot")
        records = []
        for row in result["records"]:
            if not isinstance(row, dict) or not isinstance(row.get("payload"), dict) or row.get("record_key") != record_key(row["payload"]):
                raise QualityHold("Stored record key does not match its payload")
            records.append(row["payload"])
        return result["receipts"], records

    def finish_verification(self, claim, result):
        return self._call("finish_verification", {"claim": self._claim(claim), "result": result})

    def fail_claim(self, claim, *, code, message, retryable=False, retry_after=0, raw_response=None):
        # Non-finite Retry-After means no retry is admissible. JSON cannot carry it.
        import math
        delay = float(retry_after)
        return self._call("fail_claim", {
            "claim": self._claim(claim), "code": str(code)[:100], "message": str(message)[:500],
            "retryable": bool(retryable), "retry_after": delay if math.isfinite(delay) else 253402300799.0,
            "raw_response": raw_response,
        })


def create_store(settings):
    """Direct SQL remains an explicitly local test/qualification backend only."""
    if getattr(settings, "test_mode", False) and getattr(settings, "database_url", ""):
        from .store import Store
        return Store(settings.database_url, test_mode=True)
    if getattr(settings, "database_url", ""):
        raise ValueError("Production runtime does not accept direct database credentials")
    return RpcStore(settings.api_url, settings.publishable_key, settings.rpc_token,
                    project_ref=settings.project_ref)

