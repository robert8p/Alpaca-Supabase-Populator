"""Bounded source-to-reviewed-unit bridge; no admission or provider access.

The output is a *candidate* for a separately authenticated source reviewer.
It does not create a review, seal or work row, and cannot certify a dataset.
Only ASCII unit keys are accepted until cross-language JSONB normalization
for other code points is explicitly qualified on the actual source contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping

from .bulk_expected import ExpectedUnitPlan, MAX_UNIT_PAGE
from .bulk_manifest_admission import FamilySourcePin, _expected_keys
from .bulk_scope import (
    CAPTURE_KEY, FAMILIES, RETAINED_RECEIPT_SHA256, ScopeError, canonical,
    sha256_text,
)

FIELDS = ("unit_key", "source_sha256", "provenance_sha256",
          "identity_sha256", "point_in_time_sha256")


def _digest(s: object) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def pg_jsonb_reviewed_unit_sha256(ordered_rows: tuple[tuple[str, str, str, str, str], ...]) -> str:
    """Hash the exact PostgreSQL jsonb_agg(array(... ORDER BY unit_key)) text.

    This deliberately supports the ASCII subset only. Other source keys must
    be assigned lossless, independently reviewable ASCII identity tokens before
    attestation; never hash incompatible Python/SQL serialization silently.
    SQL integration regressions compare this digest to PostgreSQL itself.
    """
    if not isinstance(ordered_rows, tuple):
        raise ScopeError("immutable ordered witness tuple required")
    last = None
    for row in ordered_rows:
        if not isinstance(row, tuple) or len(row) != 5 or any(not isinstance(s, str) for s in row):
            raise ScopeError("invalid complete unit witness")
        key = row[0]
        if (not key or len(key) > 512
                or any(ord(c) < 32 or ord(c) > 126 for c in key)
                or (last is not None and key <= last)
                or any(not _digest(s) for s in row[1:])):
            raise ScopeError("noncanonical, unordered or unpinned exact-unit witness")
        last = key
    return hashlib.sha256(
        json.dumps(ordered_rows, ensure_ascii=False, separators=(", ", ": ")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ReviewedUnitCandidate:
    family: str
    expected_manifest_sha256: str
    source_snapshot_sha256: str
    source_observation_sha256: str
    exact_unit_set_sha256: str
    unit_count: int
    # For a distinct reviewer only; never write this from the worker account.
    rows: tuple[tuple[str, str, str, str, str], ...]

    @property
    def worker_admission_authorized(self) -> bool:
        return False


def build_reviewed_unit_candidate(
    plan: ExpectedUnitPlan,
    family: str,
    source_pin: FamilySourcePin,
    read_page: Callable[[str, str | None, int], Mapping[str, Any]],
    *, page_limit: int = 128,
) -> ReviewedUnitCandidate:
    """Bind exact expected unit keys to paginated source-side evidence.

    Source pages must come from one externally pinned snapshot and include
    independent provenance, lifecycle identity and PIT receipts. A separate
    reviewer must validate underlying evidence and source completeness before
    any SQL reviewed-unit INSERT/seal, which are NOT performed here.
    """
    if (not isinstance(plan, ExpectedUnitPlan)
            or plan.capture_key != CAPTURE_KEY
            or plan.capture_receipt_sha256 != RETAINED_RECEIPT_SHA256
            or family not in FAMILIES
            or type(page_limit) is not int or not 1 <= page_limit <= MAX_UNIT_PAGE
            or not callable(read_page)):
        raise ScopeError("invalid or incomplete bounded family/source plan")
    state = plan.family(family)
    if (state.status != "READY_FOR_STAGING" or state.count is None
            or not 1 <= state.count <= 200_000
            or not _digest(state.manifest_sha256)):
        raise ScopeError("unverified family denominator cannot bind source units")
    if (not isinstance(source_pin, FamilySourcePin)
            or source_pin.family != family
            or source_pin.expected_manifest_sha256 != state.manifest_sha256
            or family not in plan.source_bindings
            or source_pin.contract_sha256 != plan.source_bindings[family].contract_sha256
            or not all(_digest(v) for v in (
                source_pin.contract_sha256, source_pin.source_snapshot_sha256,
                source_pin.source_receipt_sha256))):
        raise ScopeError("source snapshot or original contract pin not qualified")
    expected = _expected_keys(plan, family)
    observed: list[tuple[str, str, str, str, str]] = []
    previous = None
    for _ in range(state.count // page_limit + 3):
        reply = read_page(family, previous, page_limit)
        if (not isinstance(reply, Mapping) or type(reply.get("has_more")) is not bool
                or not isinstance(reply.get("rows"), list)
                or len(reply["rows"]) > page_limit
                or (not reply["rows"] and reply["has_more"])):
            raise ScopeError("incomplete or nonadvancing source page")
        for obj in reply["rows"]:
            if (not isinstance(obj, Mapping)
                    or any(not isinstance(obj.get(field), str) for field in FIELDS)):
                raise ScopeError("source metadata witness is incomplete")
            row = tuple(obj[field] for field in FIELDS)
            key = row[0]
            if (not key or (previous is not None and key <= previous)
                    or len(observed) >= state.count + 1):
                raise ScopeError("source units duplicated, unordered or exceed bound")
            observed.append(row)
            previous = key
        if not reply["has_more"]:
            break
    else:
        raise ScopeError("source pagination did not terminate within population bound")
    rows = tuple(observed)
    if len(rows) != state.count or {r[0] for r in rows} != expected:
        raise ScopeError("observed unit keys differ from independently evidenced expected population")
    unit_digest = pg_jsonb_reviewed_unit_sha256(rows)
    source_observation = sha256_text(canonical([list(row) for row in rows]))
    if source_observation != source_pin.source_receipt_sha256:
        raise ScopeError("source snapshot receipt changed or page drifted")
    return ReviewedUnitCandidate(
        family, state.manifest_sha256, source_pin.source_snapshot_sha256,
        source_observation, unit_digest, len(rows), rows,
    )
