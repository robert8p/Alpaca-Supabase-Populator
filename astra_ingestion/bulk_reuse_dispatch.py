"""Bounded provider-free retained-source dispatcher for the staged ASTRA bulk ledger.

This is a restricted-runtime *component*, not a deployment or admission grant.
An independent reviewer must release a full-24-family manifest in the durable
store before any claim. The SQL store must enforce the same restriction under
a separate no-provider principal; this Python check is defense in depth only.

The dispatcher never requests provider data, never creates manifests/jobs,
never issues attestation, and never automatically recovers expired leases.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping

from .bulk_scope import CAPTURE_KEY, RETAINED_RECEIPT_SHA256, ScopeError

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_WORK = re.compile(r"astra-bulk-v1-[0-9a-f]{64}\Z")
_MAX_ITEMS = 16
_MIN_LEASE, _MAX_LEASE = 10, 180


class DispatchRefused(ScopeError):
    """Refuse execution before doing irreversible work."""


def _sha(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise DispatchRefused("missing original UTC deadline or claim expiry")
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DispatchRefused("invalid UTC deadline") from exc
    if when.tzinfo is None or when.utcoffset().total_seconds() != 0:
        raise DispatchRefused("deadline must be timezone-aware UTC")
    return when


class RetainedOnlyDispatcher:
    """Execute at most a finite set of separately admitted *retained* pages.

    Expected restricted store protocol (also to be verified at SQL/RLS layer):
      admission(manifest) -> server-side independent review record or None
      claim_retained(manifest, owner, lease_seconds) -> DB-fenced claim or None
      commit_retained_page(claim, next_page) -> atomic committed receipt
    The store must not expose provider acquisition through these operations.
    Verification and worker admission are separate restricted principals.
    """

    def __init__(self, store: Any, *, manifest_sha256: str, worker_id: str,
                 lease_seconds: int = 60):
        if not _sha(manifest_sha256):
            raise DispatchRefused("exact reviewed manifest required")
        if (not isinstance(worker_id, str) or not 1 <= len(worker_id) <= 128
                or not re.fullmatch(r"[a-zA-Z0-9_.:-]+", worker_id)):
            raise DispatchRefused("bounded non-secret worker identity required")
        if type(lease_seconds) is not int or not _MIN_LEASE <= lease_seconds <= _MAX_LEASE:
            raise DispatchRefused("claim lease must be finite")
        self.store = store
        self.manifest = manifest_sha256
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    def _admitted(self) -> None:
        # No authorisation from a caller-supplied preflight, synthetic witness,
        # mutable manifest or this worker's own claimed attestation.
        gate = self.store.admission(self.manifest)
        if (not isinstance(gate, Mapping)
                or gate.get("status") != "INDEPENDENTLY_REVIEWED_RETAINED_ONLY"
                or gate.get("manifest_sha256") != self.manifest
                or gate.get("capture_key") != CAPTURE_KEY
                or gate.get("capture_receipt_sha256") != RETAINED_RECEIPT_SHA256
                or gate.get("complete_family_count") != 24
                or not _sha(gate.get("independent_review_sha256"))
                or gate.get("stopped") is not False):
            raise DispatchRefused("durably independently reviewed 24-family admission missing")

    def run_one(self, *, now: datetime | None = None) -> dict[str, Any]:
        self._admitted()
        claim = self.store.claim_retained(self.manifest, self.worker_id, self.lease_seconds)
        if claim is None:
            return {"state": "idle"}
        if not isinstance(claim, Mapping):
            raise DispatchRefused("malformed durable claim")
        if (claim.get("manifest_sha256") != self.manifest
                or not isinstance(claim.get("work_key"), str)
                or _WORK.fullmatch(claim["work_key"]) is None
                or claim.get("mode") != "retained_source_reuse"
                or claim.get("status") != "claimed"
                or claim.get("claim_owner") != self.worker_id
                or type(claim.get("claim_fence")) is not int
                or claim["claim_fence"] < 1
                or type(claim.get("attempts")) is not int
                or not 1 <= claim["attempts"] <= 2
                or type(claim.get("max_requests")) is not int
                or claim["max_requests"] != 0
                or type(claim.get("requests_committed")) is not int
                or claim["requests_committed"] != 0
                or type(claim.get("max_records")) is not int
                or not 1 <= claim["max_records"] <= 1000000
                or type(claim.get("records_committed")) is not int
                or not 0 <= claim["records_committed"] <= claim["max_records"]
                or type(claim.get("last_page")) is not int
                or claim["last_page"] < -1):
            raise DispatchRefused("non-retained, unfenced or over-budget claim rejected")
        effective_now = now or datetime.now(timezone.utc)
        if effective_now.tzinfo is None:
            raise DispatchRefused("timezone-aware current time required")
        now_utc = effective_now.astimezone(timezone.utc)
        if _utc(claim.get("original_deadline")) <= now_utc:
            raise DispatchRefused("original job deadline expired; no replay")
        if _utc(claim.get("claim_until")) <= now_utc:
            raise DispatchRefused("claim expired; no unsafe takeover")
        page = claim["last_page"] + 1
        # Store must atomically read retained source, materialise the output
        # and commit its immutable receipt under the same DB ownership fence.
        # A response is not verified data acceptance or independent attestation.
        receipt = self.store.commit_retained_page(dict(claim), page)
        if (not isinstance(receipt, Mapping)
                or receipt.get("work_key") != claim["work_key"]
                or receipt.get("page_no") != page
                or type(receipt.get("requests_committed")) is not int
                or receipt["requests_committed"] != 0
                or type(receipt.get("records_committed")) is not int
                or not 1 <= receipt["records_committed"] <=
                        claim["max_records"] - claim["records_committed"]
                or not _sha(receipt.get("source_sha256"))
                or not _sha(receipt.get("output_sha256"))):
            raise DispatchRefused("durable retained receipt invalid; reconcile effects before retry")
        return {
            "state": "committed_review_required",
            "work_key": claim["work_key"],
            "page_no": page,
            "records": receipt["records_committed"],
        }

    def run_bounded(self, *, max_items: int = 2,
                    now: datetime | None = None) -> tuple[dict[str, Any], ...]:
        if type(max_items) is not int or not 1 <= max_items <= _MAX_ITEMS:
            raise DispatchRefused("bounded maximum of 1–16 claim operations required")
        outcomes = []
        seen = set()
        for _ in range(max_items):
            result = self.run_one(now=now)
            if result["state"] == "idle":
                break
            # A loop must not repeatedly claim the same unit awaiting review.
            if result["work_key"] in seen:
                raise DispatchRefused("non-advancing durable executor repeated a claim")
            seen.add(result["work_key"])
            outcomes.append(result)
        return tuple(outcomes)
