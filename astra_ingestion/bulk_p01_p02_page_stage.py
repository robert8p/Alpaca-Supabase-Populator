"""Fail-closed, provider-response staging candidate for P01/P02 September SIP.

This prepares an immutable, bounded page for a FUTURE atomic SQL stage/receipt
transaction. It never contacts Alpaca, reserves funds, commits rows, issues a
continuation or confers worker access. The caller's claim/readback mapping is
UNTRUSTED and cannot substitute for the database's real fenced transaction,
reviewed source unit, HTTPS-authenticated principal or provider authenticity.
No licensed prices or access credentials should be recorded in reports/logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from typing import Any, Mapping

from .bulk_p01_p02_alpaca_request import AlpacaSIPRequestPlan
from .bulk_p01_p02_alpaca_response import (
    ObservedSIPBar, SIPResponseWitness, _original_plan, inspect_sip_response,
)
from .bulk_scope import ScopeError, canonical

_WORK = re.compile(r"astra-bulk-v1-[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OWNER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ScopeError("claim/deadline requires explicit UTC timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopeError("malformed claim/deadline UTC timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ScopeError("claim/deadline must be exact UTC")
    return stamp.astimezone(timezone.utc)


def _int(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


@dataclass(frozen=True)
class SIPSourcePageCandidate:
    work_key: str
    manifest_sha256: str
    family: str
    page_no: int
    claim_owner: str
    claim_fence: int
    source_page_sha256: str
    stage_candidate_sha256: str
    eligible_bars: tuple[ObservedSIPBar, ...]
    provider_records_observed: int
    eligible_records: int
    inclusive_end_records_excluded: int
    request_increment: int
    request_total_after_candidate: int
    eligible_records_total_after_candidate: int
    continuation_token_sha256: str | None
    next_page_required: bool
    status: str = "CANDIDATE_UNAUTHENTICATED_NOT_SQL_STAGED_NOT_AUTHORIZED"

    @property
    def worker_admission_authorized(self) -> bool:
        return False

    @property
    def provider_submission_authorized(self) -> bool:
        return False

    @property
    def coverage_certified(self) -> bool:
        return False

    @property
    def durable_commit_verified(self) -> bool:
        return False


def build_sip_page_stage_candidate(
    plan: AlpacaSIPRequestPlan,
    response: Mapping[str, Any],
    claim: Mapping[str, Any],
    *,
    received_at_utc: str,
    previous: SIPResponseWitness | None = None,
    previous_receipt: Mapping[str, Any] | None = None,
) -> SIPSourcePageCandidate:
    """Reparse untrusted response and check bounded, monotone ledger snapshot.

    A previous continuation is only admitted when its exact committed source
    receipt is supplied; even then this is an UNTRUSTED candidate. The SQL
    transaction must reacquire manifest/work locks and authenticate the actor,
    review, original request reservation, physical-host fencing and source.
    The provider call itself needs its own finite pre-call reservation.
    """
    checked = _original_plan(plan)
    if not isinstance(claim, Mapping):
        raise ScopeError("durable claim snapshot missing")
    work = claim.get("work_key")
    owner = claim.get("claim_owner")
    fence = claim.get("claim_fence")
    page_prior = claim.get("last_page")
    if (not isinstance(work, str) or _WORK.fullmatch(work) is None
            or not isinstance(owner, str) or _OWNER.fullmatch(owner) is None
            or not _int(fence, 1, 2**63 - 1)
            or not _int(page_prior, -1, 999)
            or claim.get("manifest_sha256") != checked.manifest_sha256
            or claim.get("family") != checked.family
            or claim.get("mode") != "provider_acquisition"
            or claim.get("status") != "claimed"
            or claim.get("stopped") is not False
            or claim.get("source_receipt_sha256") != checked.entitlement_receipt_sha256
            or not _int(claim.get("attempts"), 1, 2)):
        raise ScopeError("unqualified provider work, immutable source or owner fence")
    now = _utc(received_at_utc)
    if (now >= _utc(checked.original_job_deadline)
            or now >= _utc(claim.get("original_deadline"))
            or _utc(checked.original_job_deadline) != _utc(claim.get("original_deadline"))
            or now >= _utc(claim.get("claim_until"))):
        raise ScopeError("original deadline or finite owner lease expired")
    max_requests, used_requests = claim.get("max_requests"), claim.get("requests_committed")
    max_records, used_records = claim.get("max_records"), claim.get("records_committed")
    if (not _int(max_requests, 1, 200)
            or not _int(used_requests, 0, max_requests)
            or not _int(max_records, 1, 1_000_000)
            or not _int(used_records, 0, max_records)
            or used_requests >= max_requests):
        raise ScopeError("cumulative work request/record reservations exhausted or unknown")
    page_no = page_prior + 1
    prior_sha = prior_timestamp = None
    if page_no == 0:
        if previous is not None or previous_receipt is not None or used_requests != 0 or used_records != 0:
            raise ScopeError("initial provider page cannot inherit earlier effects")
    else:
        if (not isinstance(previous, SIPResponseWitness)
                or not isinstance(previous_receipt, Mapping)
                or previous.page_no != page_prior
                or previous.manifest_sha256 != checked.manifest_sha256
                or previous.contract_sha256 != checked.contract_sha256
                or previous.family != checked.family
                or previous.symbol != checked.symbol
                or previous.instrument_key != checked.instrument_key
                or not previous.continuation_required
                or not previous.next_page_token
                or not previous.bars
                or previous_receipt.get("work_key") != work
                or previous_receipt.get("page_no") != page_prior
                or previous_receipt.get("source_sha256") != previous.page_sha256
                or previous_receipt.get("consistent") is not True
                or used_requests < page_no):
            raise ScopeError("non-advancing/unauthenticated previous provider receipt")
        prior_sha = previous.page_sha256
        prior_timestamp = previous.bars[-1].timestamp_utc
    inspected = inspect_sip_response(
        checked, response, page_no=page_no,
        prior_page_sha256=prior_sha, prior_bar_timestamp_utc=prior_timestamp)
    eligible = len(inspected.bars)
    provider_count = eligible + inspected.excluded_end_bar_count
    if (provider_count > checked.reserved_record_count
            or used_records + eligible > max_records
            or used_requests + checked.reserved_request_count > max_requests
            or inspected.continuation_required and not inspected.bars):
        raise ScopeError("response exceeds cumulative reservation or cannot advance")
    # The original request, source chain and finite claimed counters are bound
    # without embedding credentials, continuation tokens or prices in reports.
    stage = {
        "work_key": work, "manifest": checked.manifest_sha256,
        "family": checked.family, "contract": checked.contract_sha256,
        "source_receipt": checked.entitlement_receipt_sha256,
        "identity_receipt": checked.identity_receipt_sha256,
        "calendar_receipt": checked.calendar_receipt_sha256,
        "page": page_no, "owner": owner, "fence": fence,
        "original_deadline": _utc(checked.original_job_deadline).isoformat(),
        "request": dict(checked.request),
        "prior_page": prior_sha,
        "page_sha256": inspected.page_sha256,
        "provider_observed": provider_count,
        "eligible_record_sha256": [bar.record_sha256 for bar in inspected.bars],
        "excluded_boundary_sha256": inspected.excluded_end_bar_sha256,
        "requests_after": used_requests + 1,
        "eligible_records_after": used_records + eligible,
        "continuation_sha256": (
            sha256(inspected.next_page_token.encode("ascii")).hexdigest()
            if inspected.next_page_token else None),
    }
    return SIPSourcePageCandidate(
        work, checked.manifest_sha256, checked.family, page_no,
        owner, fence, inspected.page_sha256,
        sha256(canonical(stage).encode("utf-8")).hexdigest(),
        inspected.bars, provider_count, eligible,
        inspected.excluded_end_bar_count, 1,
        used_requests + 1, used_records + eligible,
        stage["continuation_sha256"], inspected.continuation_required,
    )
