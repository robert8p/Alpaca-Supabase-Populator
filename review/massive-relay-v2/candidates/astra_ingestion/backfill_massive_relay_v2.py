"""Bounded adapter for the existing Edge function's managed Massive credential.

Only authenticated readiness can advertise capabilities. This module owns no
queue, scheduling, credential export, reservation or database mutation retry.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from http.client import HTTPException
import json
import re
import ssl
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .backfill_provider_v2 import (
    KINDS, MAX_BODY_BYTES, MAX_PARTIAL_BODY_BYTES, ProviderPage, ProviderProblem,
    _NoRedirect, _parse, _retry_delay, _stamp, parse_response, request_for,
)
from .rpc_store import TOKEN_PATTERN, validate_endpoint, validate_public_key
from .store import LeaseLost

PROTOCOL = "astra-massive-relay-v2"
EDGE_PATH = "/functions/v1/population-top3000-news-v1"
MAX_RELAY_RESPONSE_BYTES = 4 * 1024 * 1024 + 65536
RELAY_TIMEOUT_SECONDS = 35
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_HEADERS = {"X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"}


class _RelayFailure(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class ManagedMassivePage(ProviderPage):
    def payload(self):
        result = super().payload()
        result["adapter_version"] = "fixed3000-managed-massive-relay-v2.1"
        return result


class MassiveRelay:
    def __init__(self, api_url, publishable_key, worker_token, *, opener=None):
        self.endpoint = validate_endpoint(api_url) + EDGE_PATH
        validate_public_key(publishable_key)
        if not isinstance(worker_token, str) or not TOKEN_PATTERN.fullmatch(worker_token):
            raise ValueError("The relay requires the existing dedicated worker capability")
        self._key, self._token = publishable_key, worker_token
        self._opener = opener or build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
        self.ready = False
        self.last_probe_state = "NOT_OBSERVED"

    def _edge(self, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        if len(body) > 65536:
            raise _RelayFailure("REQUEST_REJECTED")
        request = Request(self.endpoint, data=body, method="POST", headers={
            "apikey": self._key, "X-Astra-Ingestion-Token": self._token,
            "X-Astra-Replacement-Relay": PROTOCOL, "Content-Type": "application/json",
            "Accept": "application/json", "Accept-Encoding": "identity", "Cache-Control": "no-store"})
        deadline = monotonic() + RELAY_TIMEOUT_SECONDS
        try:
            try:
                response = self._opener.open(request, timeout=RELAY_TIMEOUT_SECONDS)
            except HTTPError as error:
                response = error
            with response:
                status = response.status if hasattr(response, "status") else response.code
                if response.geturl() != self.endpoint or response.headers.get("Content-Encoding", "identity") not in ("", "identity"):
                    raise _RelayFailure("RELAY_CONTROL_UNAVAILABLE")
                if response.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                    raise _RelayFailure("RELAY_CONTROL_UNAVAILABLE")
                declared = response.headers.get("Content-Length")
                if declared is not None and (not declared.isdigit() or int(declared) > MAX_RELAY_RESPONSE_BYTES):
                    raise _RelayFailure("RELAY_CONTROL_UNAVAILABLE")
                raw = bytearray()
                while len(raw) <= MAX_RELAY_RESPONSE_BYTES:
                    if monotonic() >= deadline:
                        raise _RelayFailure("SOURCE_READ_TIMEOUT")
                    part = response.read1(min(65536, MAX_RELAY_RESPONSE_BYTES + 1 - len(raw)))
                    if monotonic() >= deadline:
                        raise _RelayFailure("SOURCE_READ_TIMEOUT")
                    if not part:
                        break
                    raw.extend(part)
                if len(raw) > MAX_RELAY_RESPONSE_BYTES or declared is not None and len(raw) != int(declared):
                    raise _RelayFailure("RELAY_CONTROL_UNAVAILABLE")
        except (URLError, TimeoutError, OSError, HTTPException):
            raise _RelayFailure("SOURCE_TRANSPORT_ERROR") from None
        try:
            value = _parse(bytes(raw).decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            raise _RelayFailure("RELAY_CONTROL_UNAVAILABLE") from None
        if not isinstance(value, dict):
            raise _RelayFailure("RELAY_CONTROL_UNAVAILABLE")
        if status != 200:
            allowed = {"AUTHENTICATION_REQUIRED", "MASSIVE_CREDENTIAL_UNAVAILABLE", "CLAIM_REJECTED",
                "REQUEST_REJECTED", "DISPATCH_ALREADY_USED", "SOURCE_TRANSPORT_ERROR", "SOURCE_READ_TIMEOUT",
                "RELAY_CONTROL_UNAVAILABLE", "SOURCE_CREDENTIAL_ECHO", "UNEXPECTED_SOURCE_TRANSPORT"}
            code = value.get("error")
            raise _RelayFailure(code if isinstance(code, str) and code in allowed else "RELAY_CONTROL_UNAVAILABLE")
        return value

    def probe(self):
        self.ready = False
        try:
            value = self._edge({"action": "probe"})
            if set(value) != {"ready"} or type(value["ready"]) is not bool:
                raise _RelayFailure("RELAY_CONTROL_UNAVAILABLE")
            self.ready = value["ready"]
            self.last_probe_state = "AUTHENTICATED_READY" if self.ready else "AUTHENTICATED_CREDENTIAL_UNAVAILABLE"
        except _RelayFailure:
            self.last_probe_state = "READINESS_UNCONFIRMED"
        return self.ready

    def require_credentials(self, task):
        if not task.get("kind", "").startswith("massive_"):
            raise ProviderProblem("INVALID_TASK_SCOPE", "Managed relay accepts only the admitted Massive adapters")
        if not self.ready and not self.probe():
            raise ProviderProblem("BLOCKED_EXTERNAL", "Managed Massive capability is not currently authenticated as ready",
                evidence={"dependency": "MASSIVE_WORKER_CREDENTIAL", "not_a_provider_limitation": True,
                          "relay_readiness": self.last_probe_state})

    def fetch(self, task):
        self.require_credentials(task)
        plan = request_for(task)
        claim = {name: task[name] for name in ("id", "run_id", "owner", "generation", "run_fence", "page_no")}
        try:
            value = self._edge({"action": "fetch", "claim": claim, "request": plan})
        except _RelayFailure as error:
            evidence = {"request": plan, "transport": "existing_managed_massive_relay",
                        "same_reservation_replay": False, "relay_code": error.code}
            if error.code == "CLAIM_REJECTED":
                raise LeaseLost("Managed relay rejected stale ownership or reservation") from None
            if error.code in {"MASSIVE_CREDENTIAL_UNAVAILABLE", "AUTHENTICATION_REQUIRED"}:
                self.ready = False
                evidence.update(dependency="MASSIVE_WORKER_CREDENTIAL", not_a_provider_limitation=True)
                raise ProviderProblem("BLOCKED_EXTERNAL", "Managed Massive authorization is unavailable", evidence=evidence) from None
            retry = error.code in {"DISPATCH_ALREADY_USED", "SOURCE_TRANSPORT_ERROR", "SOURCE_READ_TIMEOUT", "RELAY_CONTROL_UNAVAILABLE"}
            code = "SOURCE_TRANSPORT_ERROR" if retry else error.code
            raise ProviderProblem(code, "Managed source dispatch requires a new counted attempt" if retry else "Managed source response requires operational review",
                retryable=retry, retry_after=30 if retry else 0, evidence=evidence) from None
        base = {"protocol", "dispatch_id", "request_sha256", "http_status", "headers", "fetched_at",
                "response_complete", "body_base64", "body_bytes", "body_sha256"}
        extra = {"read_limit_bytes", "observed_prefix_bytes", "observed_prefix_sha256"}
        try:
            complete = value["response_complete"]
            if type(complete) is not bool or set(value) != (base if complete else base | extra):
                raise ValueError("envelope")
            expected_hash = sha256(json.dumps(plan, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            if value["protocol"] != PROTOCOL or value["request_sha256"] != expected_hash:
                raise ValueError("request binding")
            if not isinstance(value["dispatch_id"], str) or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value["dispatch_id"]):
                raise ValueError("dispatch")
            data = base64.b64decode(value["body_base64"], validate=True)
            if type(value["body_bytes"]) is not int or len(data) != value["body_bytes"] or len(data) > (MAX_BODY_BYTES if complete else MAX_PARTIAL_BODY_BYTES):
                raise ValueError("bytes")
            if sha256(data).hexdigest() != value["body_sha256"] or _stamp(value["fetched_at"]) is None:
                raise ValueError("source hash or time")
            status, headers = value["http_status"], value["headers"]
            if type(status) is not int or not 100 <= status <= 599 or not isinstance(headers, dict) or not set(headers) <= _SAFE_HEADERS:
                raise ValueError("status or headers")
            if any(not isinstance(item, str) or len(item) > 512 or re.search(r"[\x00-\x1f\x7f]", item) for item in headers.values()):
                raise ValueError("headers")
            if self._token.encode() in data or any(self._token in item for item in headers.values()):
                raise ValueError("credential reflection")
            if not complete and (value["read_limit_bytes"] != MAX_BODY_BYTES or value["observed_prefix_bytes"] != MAX_BODY_BYTES + 1
                    or not isinstance(value["observed_prefix_sha256"], str) or not _DIGEST.fullmatch(value["observed_prefix_sha256"])):
                raise ValueError("incomplete source")
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ProviderProblem("SOURCE_RELAY_PROTOCOL_ERROR", "Managed source envelope failed integrity validation",
                                  evidence={"request": plan, "response_complete": False}) from None
        evidence = {"request": plan, "http_status": status, "headers": headers, "fetched_at": value["fetched_at"],
                    "relay_dispatch_id": value["dispatch_id"]}
        if not complete:
            evidence.update(response_complete=False, read_limit_bytes=MAX_BODY_BYTES,
                observed_prefix_bytes=value["observed_prefix_bytes"], observed_prefix_sha256=value["observed_prefix_sha256"],
                partial_body_base64=value["body_base64"], partial_body_bytes=len(data), partial_body_sha256=value["body_sha256"],
                cursor_controls_page_size=bool(plan["params"].get("cursor")), adapter_version="fixed3000-managed-massive-relay-v2.1")
        else:
            try:
                raw = data.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                prefix = data[:MAX_PARTIAL_BODY_BYTES]
                evidence.update(response_complete=True, source_body_bytes=len(data), source_body_sha256=value["body_sha256"],
                    source_encoding_error="INVALID_UTF8", full_raw_body_retained=False,
                    partial_body_base64=base64.b64encode(prefix).decode("ascii"), partial_body_bytes=len(prefix),
                    partial_body_sha256=sha256(prefix).hexdigest())
                code = "SOURCE_PARSE_ERROR" if status == 200 else "SOURCE_RATE_LIMIT" if status == 429 else "BLOCKED_EXTERNAL" if status in (401,403) else "SOURCE_HTTP_ERROR"
                raise ProviderProblem(code, "Source bytes are not valid UTF-8; original-byte hash and bounded prefix retained",
                    retryable=status in (408,425,429,500,502,503,504), retry_after=_retry_delay(headers) if status != 200 else 0,
                    evidence=evidence) from None
            evidence.update(raw_body=raw, body_sha256=value["body_sha256"])
        if status != 200:
            code = "SOURCE_RATE_LIMIT" if status == 429 else "BLOCKED_EXTERNAL" if status in (401, 403) else "SOURCE_HTTP_ERROR"
            raise ProviderProblem(code, "Provider request returned HTTP " + str(status),
                retryable=status in (408,425,429,500,502,503,504), retry_after=_retry_delay(headers), evidence=evidence)
        if not complete:
            raise ProviderProblem("SOURCE_PAGE_TOO_LARGE", "Response exceeds the bounded body size; retry only at a smaller durable page limit",
                retryable=plan["params"].get("limit",1)>1 and not evidence["cursor_controls_page_size"],
                retry_after=_retry_delay(headers) if "Retry-After" in headers else 2, evidence=evidence)
        try:
            records,cursor,quality = parse_response(task, plan, raw)
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            evidence["parser_error_type"] = type(error).__name__
            raise ProviderProblem("SOURCE_PARSE_ERROR", "Source retained but parsing requires repair", evidence=evidence) from None
        return ManagedMassivePage(raw, value["body_sha256"], status, headers.get("X-Request-ID"),
            value["fetched_at"], plan, records, cursor, quality, headers)


class ProviderWithManagedMassive:
    """Composition adapter; direct configured credentials retain their current path."""
    def __init__(self, direct, relay):
        self.direct, self.relay = direct, relay
        self.direct_kinds = frozenset(direct.supported_kinds())
        self.relay_active = False

    def supported_kinds(self):
        self.relay_active = not any(kind.startswith("massive_") for kind in self.direct_kinds) and self.relay.probe()
        return tuple(kind for kind in KINDS if kind in self.direct_kinds or self.relay_active and kind.startswith("massive_"))

    def require_credentials(self, task):
        return (self.relay if self.relay_active and task["kind"].startswith("massive_") else self.direct).require_credentials(task)

    def fetch(self, task):
        return (self.relay if self.relay_active and task["kind"].startswith("massive_") else self.direct).fetch(task)
