"""Bounded HTTPS client for P01/P02 historical Alpaca SIP source pages.

An authenticated TLS connection is *not* an independent reviewer, historical
identity proof, entitlement proof, or bulk admission. This transport is NOT
wired into the deployed worker and MUST NOT be activated without a restricted
production admission adapter that reads a genuine durable ticket, validates
the authenticated runtime principal, and fences its claim immediately before
each call. Unit-test authorizers/openers are synthetic, never hosted evidence.

Neither credentials, provider record values nor continuation tokens belong in
logs, exceptions, repository reports or a public API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import ssl
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener,
)

from .bulk_p01_p02_alpaca_request import AlpacaSIPRequestPlan
from .bulk_p01_p02_alpaca_response import SIPResponseWitness, inspect_sip_response
from .bulk_provider_precall import match_precall_candidate
from .bulk_scope import ScopeError

ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
MAX_BODY_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 12


@dataclass(frozen=True)
class BoundHTTPSPage:
    plan: AlpacaSIPRequestPlan = field(repr=False)
    url: str = field(repr=False)
    work_key: str
    page_no: int
    fence: int
    request_sha256: str
    manifest_sha256: str
    previous: SIPResponseWitness | None = field(default=None, repr=False)
    status: str = "BOUND_NOT_ADMITTED_NOT_SENT"

    @property
    def provider_submission_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class HTTPSPageObservation:
    work_key: str
    page_no: int
    request_sha256: str
    raw_body_sha256: str
    witness: SIPResponseWitness = field(repr=False)
    _response: Mapping[str, Any] = field(repr=False)
    status: str = "HTTPS_OBSERVED_NOT_INDEPENDENTLY_ATTESTED"

    def quarantinable_response(self) -> Mapping[str, Any]:
        # Caller still needs the original fenced durable ticket and a separate
        # authenticated transport attestor, never this object alone.
        return self._response

    @property
    def provider_provenance_accepted(self) -> bool:
        return False

    @property
    def bulk_output_committed(self) -> bool:
        return False


def prepare_bound_https_page(
    plan: AlpacaSIPRequestPlan,
    claim: Mapping[str, Any],
    ticket: Mapping[str, Any],
    *,
    now_utc: str,
    previous: SIPResponseWitness | None = None,
    previous_receipt: Mapping[str, Any] | None = None,
) -> BoundHTTPSPage:
    """Pure candidate. Matching a ticket is NOT independent SQL admission."""
    bound = match_precall_candidate(plan, claim, ticket, now_utc=now_utc)
    if bound.page_no == 0:
        if previous is not None or previous_receipt is not None:
            raise ScopeError("first provider page cannot reuse a predecessor")
        token = None
    else:
        if (previous is None or previous_receipt is None
                or previous.next_page_token is None
                or previous.page_no != bound.page_no - 1
                or previous.manifest_sha256 != bound.manifest_sha256
                or previous.family != plan.family
                or previous.symbol != plan.symbol
                or previous_receipt.get("consistent") is not True
                or previous_receipt.get("source_page_sha256") != previous.page_sha256
                or previous_receipt.get("page_no") != previous.page_no
                or previous_receipt.get("work_key") != bound.work_key):
            raise ScopeError("provider page requires a genuine matching predecessor")
        token = previous.next_page_token
    request = dict(plan.request)
    if token is not None:
        request["page_token"] = token
    if set(request) != set(plan.request) | ({"page_token"} if token else set()):
        raise ScopeError("unrecognized provider URL query parameters")
    # The original approved end bound remains inclusive at the API level;
    # the separately established expected calendar remains [start, end).
    url = ENDPOINT + "?" + urlencode(request)
    return BoundHTTPSPage(
        plan, url, bound.work_key, bound.page_no, bound.claim_fence,
        bound.request_sha256, bound.manifest_sha256, previous,
    )


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate provider JSON field")
        obj[key] = value
    return obj


def _nonfinite(_: str) -> None:
    raise ValueError("non-finite provider numeric field")


def inspect_https_page(
    bound: BoundHTTPSPage,
    *,
    effective_url: str,
    status_code: int,
    content_type: str,
    content_encoding: str | None,
    raw_body: bytes,
) -> HTTPSPageObservation:
    """Strict pure inspection. Network metadata alone is forgeable in tests."""
    if not isinstance(bound, BoundHTTPSPage) or bound.status != "BOUND_NOT_ADMITTED_NOT_SENT":
        raise ScopeError("missing original bounded HTTPS request")
    if effective_url != bound.url or status_code != 200:
        raise ScopeError("provider URL or response status mismatch")
    if not isinstance(content_type, str) or content_type.split(";")[0].strip().lower() != "application/json":
        raise ScopeError("unexpected provider response media type")
    if content_encoding not in (None, "", "identity"):
        raise ScopeError("compressed provider response not admitted")
    if not isinstance(raw_body, bytes) or not 0 < len(raw_body) <= MAX_BODY_BYTES:
        raise ScopeError("provider response exceeds bounded byte reservation")
    try:
        body = json.loads(raw_body.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_nonfinite)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise ScopeError("provider JSON body malformed") from exc
    prior = bound.previous
    if bound.page_no > 0 and (prior is None or not prior.bars):
        # A chained empty page needs a separately verified timestamp cursor
        # before any further request; do not invent an eligible last minute.
        raise ScopeError("provider predecessor lacks verified timestamp cursor")
    witness = inspect_sip_response(
        bound.plan, body, page_no=bound.page_no,
        prior_page_sha256=prior.page_sha256 if prior else None,
        prior_bar_timestamp_utc=prior.bars[-1].timestamp_utc if prior else None,
    )
    return HTTPSPageObservation(
        bound.work_key, bound.page_no, bound.request_sha256,
        sha256(raw_body).hexdigest(), witness, body,
    )


def fetch_once(
    bound: BoundHTTPSPage,
    *,
    api_key: str,
    secret_key: str,
    verified_admission: Callable[[BoundHTTPSPage], bool] | None = None,
    opener: Callable[..., Any] | None = None,
) -> HTTPSPageObservation:
    """Single bounded call; never auto-retry a reserved request.

    The injection is a **future production integration point**, NOT a proof.
    Any fabricated callback (including a test's true value) is untrusted.
    This function must remain unreachable from the production worker until
    independently authenticated runtime readback/role/entitlement exists.
    """
    if (not isinstance(bound, BoundHTTPSPage)
            or not callable(verified_admission)
            or verified_admission(bound) is not True):
        raise ScopeError("live independently authenticated admission unavailable")
    for secret in (api_key, secret_key):
        if (not isinstance(secret, str) or not secret
                or any(ord(c) < 33 or ord(c) > 126 for c in secret)):
            raise ScopeError("provider credential unavailable")
    request = Request(bound.url, headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }, method="GET")
    if opener is None:
        # Do not use ambient HTTPS proxies, plaintext transport, redirects,
        # hostname overrides, insecure TLS contexts or library retries.
        opener = build_opener(
            ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
            _RejectRedirect(),
        ).open
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            return inspect_https_page(
                bound, effective_url=response.geturl(),
                status_code=response.status,
                content_type=response.headers.get("Content-Type", ""),
                content_encoding=response.headers.get("Content-Encoding"),
                raw_body=raw,
            )
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        # No raw upstream error body, URL, proxy details, key, or token in logs.
        raise ScopeError("provider HTTPS transport failed; reconcile before retry") from None
