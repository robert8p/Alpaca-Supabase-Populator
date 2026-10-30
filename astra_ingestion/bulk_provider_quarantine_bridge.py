"""Offline P01/P02 pre-call -> parsed provider page -> quarantine envelope.

No provider I/O, SQL rights, JWT authentication, transport grant, source
attestation, bulk output commit or coverage certification. A durable separate
actor must independently authenticate and insert via the restricted SQL stage.
Do not log this envelope: its in-memory JSON contains licensed market rows.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from json import dumps, loads
from typing import Any, Mapping

from .bulk_authenticated_provider_transport import BoundHTTPSPage, HTTPSPageObservation
from .bulk_p01_p02_alpaca_request import AlpacaSIPRequestPlan
from .bulk_p01_p02_alpaca_response import SIPResponseWitness
from .bulk_p01_p02_page_stage import build_sip_page_stage_candidate
from .bulk_provider_precall import match_precall_candidate
from .bulk_scope import ScopeError


@dataclass(frozen=True)
class ProviderQuarantineEnvelope:
    work_key: str
    page_no: int
    owner: str
    fence: int
    request_sha256: str
    source_page_sha256: str
    stage_candidate_sha256: str
    eligible_records: int
    provider_records_observed: int
    # Contains observed prices. Never include in logs, repo reports or repr.
    _private_stage_json: str = field(repr=False)
    status: str = "OFFLINE_QUARANTINE_ENVELOPE_UNAUTHENTICATED"

    @property
    def transport_authorized(self) -> bool:
        return False

    @property
    def bulk_output_committed(self) -> bool:
        return False

    @property
    def coverage_certified(self) -> bool:
        return False

    def sql_stage_payload(self) -> dict[str, Any]:
        """Return a fresh private payload; this is not authenticated input."""
        return loads(self._private_stage_json)


def prepare_provider_quarantine_envelope(
    plan: AlpacaSIPRequestPlan,
    response: Mapping[str, Any],
    claim: Mapping[str, Any],
    reserved_ticket: Mapping[str, Any],
    *,
    received_at_utc: str,
    previous: SIPResponseWitness | None = None,
    previous_receipt: Mapping[str, Any] | None = None,
) -> ProviderQuarantineEnvelope:
    """Two independent parser/claim checks before creating one private payload.

    The caller must separately reconcile an authenticated pre-call database
    readback and the provider TLS response. A copied fake ticket is not proof.
    """
    bound = match_precall_candidate(plan, claim, reserved_ticket, now_utc=received_at_utc)
    candidate = build_sip_page_stage_candidate(
        plan, response, claim, received_at_utc=received_at_utc,
        previous=previous, previous_receipt=previous_receipt)
    if (bound.work_key != candidate.work_key
            or bound.page_no != candidate.page_no
            or bound.manifest_sha256 != candidate.manifest_sha256
            or bound.claim_fence != candidate.claim_fence
            or candidate.claim_owner != claim.get("claim_owner")
            or candidate.family != plan.family
            or candidate.provider_records_observed > bound.records_reserved
            or candidate.request_increment != 1
            or candidate.provider_submission_authorized
            or candidate.worker_admission_authorized
            or candidate.coverage_certified
            or candidate.durable_commit_verified):
        raise ScopeError("untrusted page cannot be bound to exact durable pre-call")

    prev_token_sha: str | None = None
    if candidate.page_no > 0:
        if previous is None or not previous.next_page_token:
            raise ScopeError("missing exact predecessor continuation witness")
        prev_token_sha = sha256(previous.next_page_token.encode("ascii")).hexdigest()
        if previous_receipt is None or previous_receipt.get("consistent") is not True:
            raise ScopeError("predecessor receipt lacks independent consistency")

    bars = [asdict(bar) for bar in candidate.eligible_bars]
    payload = dict(
        source_page_sha256=candidate.source_page_sha256,
        stage_candidate_sha256=candidate.stage_candidate_sha256,
        provider_records_observed=candidate.provider_records_observed,
        eligible_records=candidate.eligible_records,
        inclusive_end_records_excluded=candidate.inclusive_end_records_excluded,
        eligible_bars=bars,
        next_page_required=candidate.next_page_required,
        continuation_token_sha256=candidate.continuation_token_sha256,
        previous_continuation_token_sha256=prev_token_sha,
    )
    if set(payload) != {
        "source_page_sha256", "stage_candidate_sha256",
        "provider_records_observed", "eligible_records",
        "inclusive_end_records_excluded", "eligible_bars", "next_page_required",
        "continuation_token_sha256", "previous_continuation_token_sha256",
    }:
        raise ScopeError("provider quarantine schema drift")
    return ProviderQuarantineEnvelope(
        candidate.work_key, candidate.page_no, candidate.claim_owner,
        candidate.claim_fence, bound.request_sha256,
        candidate.source_page_sha256, candidate.stage_candidate_sha256,
        candidate.eligible_records, candidate.provider_records_observed,
        dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
    )


def check_quarantine_summary(
    envelope: ProviderQuarantineEnvelope,
    database_summary: Mapping[str, Any],
) -> bool:
    """Compare an UNTRUSTED DB response; never infer live SQL/JWT authenticity."""
    if not isinstance(envelope, ProviderQuarantineEnvelope) or not isinstance(database_summary, Mapping):
        raise ScopeError("quarantine receipt envelope and summary required")
    expected = {
        "status": "QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED",
        "work_key": envelope.work_key,
        "page_no": envelope.page_no,
        "request_sha256": envelope.request_sha256,
        "source_page_sha256": envelope.source_page_sha256,
        "stage_candidate_sha256": envelope.stage_candidate_sha256,
        "eligible_records": envelope.eligible_records,
        "provider_records_observed": envelope.provider_records_observed,
        "bulk_output_committed": False,
        "consistent": True,
    }
    for key, value in expected.items():
        if (key not in database_summary or
                type(database_summary[key]) is not type(value) or
                database_summary[key] != value):
            raise ScopeError("quarantine result contradicts immutable source candidate")
    digest = database_summary.get("eligible_bars_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ScopeError("missing SQL source-array digest")
    return True


def prepare_https_observation_quarantine(
    bound: BoundHTTPSPage,
    observation: HTTPSPageObservation,
    claim: Mapping[str, Any],
    reserved_ticket: Mapping[str, Any],
    *,
    received_at_utc: str,
    previous_receipt: Mapping[str, Any] | None = None,
) -> ProviderQuarantineEnvelope:
    """Cross-check two source-only witnesses before constructing a quarantine.

    This accepts a bounded *observed* HTTPS page; it DOES NOT authorize a live
    HTTP call, attest true TLS provenance, write SQL, or admit bulk ingestion.
    The production worker still requires an authenticated durable admission
    adapter and a separate trusted transport pin.
    """
    if (not isinstance(bound, BoundHTTPSPage)
            or not isinstance(observation, HTTPSPageObservation)
            or bound.status != "BOUND_NOT_ADMITTED_NOT_SENT"
            or observation.status != "HTTPS_OBSERVED_NOT_INDEPENDENTLY_ATTESTED"
            or bound.provider_submission_authorized
            or observation.provider_provenance_accepted
            or observation.bulk_output_committed
            or bound.work_key != observation.work_key
            or bound.page_no != observation.page_no
            or bound.request_sha256 != observation.request_sha256
            or bound.request_url_sha256 != observation.request_url_sha256
            or bound.manifest_sha256 != observation.witness.manifest_sha256
            or bound.plan.family != observation.witness.family
            or bound.plan.instrument_key != observation.witness.instrument_key
            or bound.plan.symbol != observation.witness.symbol
            or observation.witness.page_no != bound.page_no):
        raise ScopeError("HTTPS source observation does not match original bound request")
    if (bound.page_no == 0 and previous_receipt is not None
            or bound.page_no > 0 and previous_receipt is None):
        raise ScopeError("HTTPS source continuation receipt missing or unexpected")
    envelope = prepare_provider_quarantine_envelope(
        bound.plan, observation.quarantinable_response(), claim, reserved_ticket,
        received_at_utc=received_at_utc,
        previous=bound.previous,
        previous_receipt=previous_receipt,
    )
    if (envelope.work_key != bound.work_key
            or envelope.page_no != bound.page_no
            or envelope.fence != bound.fence
            or envelope.request_sha256 != bound.request_sha256
            or envelope.source_page_sha256 != observation.witness.page_sha256
            or envelope.provider_records_observed != (
                len(observation.witness.bars)
                + observation.witness.excluded_end_bar_count
            )):
        raise ScopeError("HTTP source witness disagrees with immutable quarantine")
    return envelope
