"""Source-only cross-check of a staged pre-call provider ledger reservation.

This code NEVER sends market-data requests or authenticates a SQL/HTTPS actor.
A matching untrusted response cannot establish that a reservation was durably
committed. The future restricted client must authenticate the external server,
read back the immutable ticket and independently enforce runtime admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Mapping
import re

from .bulk_p01_p02_alpaca_request import AlpacaSIPRequestPlan
from .bulk_p01_p02_alpaca_response import _original_plan
from .bulk_scope import ScopeError, canonical

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_WORK = re.compile(r"astra-bulk-v1-[0-9a-f]{64}\Z")
_OWNER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ScopeError("immutable reservation requires UTC Z timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopeError("invalid reservation timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ScopeError("invalid reservation UTC offset")
    return dt.astimezone(timezone.utc)


def provider_request_sha256(plan: AlpacaSIPRequestPlan) -> str:
    """Fingerprint full original immutable request shape, not bare ticker."""
    checked = _original_plan(plan)
    payload = {
        "family": checked.family,
        "instrument_key": checked.instrument_key,
        "manifest": checked.manifest_sha256,
        "contract": checked.contract_sha256,
        "identity": checked.identity_receipt_sha256,
        "calendar": checked.calendar_receipt_sha256,
        "entitlement": checked.entitlement_receipt_sha256,
        "deadline": checked.original_job_deadline,
        "request": dict(checked.request),
        "reserved_requests": checked.reserved_request_count,
        "reserved_records": checked.reserved_record_count,
    }
    return sha256(canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BoundPrecallCandidate:
    work_key: str
    page_no: int
    request_sha256: str
    manifest_sha256: str
    claim_fence: int
    records_reserved: int
    status: str = "BOUND_PRECALL_UNTRUSTED_NOT_AUTHORIZED"

    @property
    def provider_submission_authorized(self) -> bool:
        return False

    @property
    def durable_reservation_verified(self) -> bool:
        return False


def match_precall_candidate(
    plan: AlpacaSIPRequestPlan,
    claim: Mapping[str, Any],
    ticket: Mapping[str, Any],
    *,
    now_utc: str,
) -> BoundPrecallCandidate:
    """Revalidate original request + fenced claim against an UNTRUSTED ticket.

    Only a genuinely authenticated durable SQL readback may precede a
    separately qualified live provider call. This helper cannot issue it.
    """
    checked = _original_plan(plan)
    if not isinstance(claim, Mapping) or not isinstance(ticket, Mapping):
        raise ScopeError("provider claim and pre-call ticket are required")
    timestamp = _utc(now_utc)
    work, owner, fence = claim.get("work_key"), claim.get("claim_owner"), claim.get("claim_fence")
    page_prior = claim.get("last_page")
    if (
        not isinstance(work, str) or _WORK.fullmatch(work) is None
        or not isinstance(owner, str) or _OWNER.fullmatch(owner) is None
        or type(fence) is not int or fence < 1
        or type(page_prior) is not int or not -1 <= page_prior <= 198
        or claim.get("manifest_sha256") != checked.manifest_sha256
        or claim.get("family") != checked.family
        or claim.get("mode") != "provider_acquisition"
        or claim.get("status") != "claimed"
        or claim.get("stopped") is not False
        or not isinstance(claim.get("source_receipt_sha256"), str)
        or _HASH.fullmatch(claim["source_receipt_sha256"]) is None
        or type(claim.get("attempts")) is not int
        or not 1 <= claim["attempts"] <= 2
    ):
        raise ScopeError("provider claim is not fenced and eligible")
    if (
        _utc(claim.get("original_deadline")) != _utc(checked.original_job_deadline)
        or timestamp >= _utc(claim.get("original_deadline"))
        or timestamp >= _utc(claim.get("claim_until"))
    ):
        raise ScopeError("provider original deadline or claim lease expired")
    req_hash = provider_request_sha256(checked)
    expected = {
        "status": "RESERVED_NO_PROVIDER_TRANSPORT_GRANT",
        "work_key": work,
        "page_no": page_prior + 1,
        "manifest_sha256": checked.manifest_sha256,
        "family": checked.family,
        "claim_fence": fence,
        "request_sha256": req_hash,
        "records_reserved": checked.reserved_record_count,
        "original_deadline": checked.original_job_deadline,
        "provider_submission_authorized": False,
    }
    # No coercions of true/false, ints, hashes or timestamps. Additional
    # fields are refused to prevent ambiguous or contradictory privilege data.
    if set(ticket) != set(expected) or any(
        type(ticket[k]) is not type(value) or ticket[k] != value
        for k, value in expected.items()
    ):
        raise ScopeError("pre-call ticket does not bind exact provider plan and fence")
    return BoundPrecallCandidate(
        work, page_prior + 1, req_hash, checked.manifest_sha256,
        fence, checked.reserved_record_count,
    )
