"""Pinned Top-3,000 scope and fail-closed planning, separate from v1 canaries.

This module neither submits jobs nor contacts providers. Captured membership is
not financial/identity qualification. Unknown coverage remains unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

FAMILIES = (
    "REF01", "P01", "P02", "D01", "N01", "N03", "D02", "D03", "D04",
    "F04", "F05", "S02", "F06", "CTX06", "CTX14", "REF03", "D05",
    "F01", "F02", "F03", "N02", "S01", "CTX02", "CTX07",
)
SHARED_FAMILIES = frozenset({"CTX06", "CTX07", "CTX14", "REF03"})
SCOPE_ID = "corrected_company_scope_8e6ca1178f03822c"
CAPTURE_KEY = "top3000-augsep2026-retained-scope-v1"
COHORT_SHA256 = "2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec"
ACCEPTANCE_SHA256 = "20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9"
CONTRACT_SET_SHA256 = "e47a1e4152768418bd8e6187310b34cfc7b096edbc1e1de11fe243275e046dc0"
START = "2026-08-01T04:00:00Z"
END_EXCLUSIVE = "2026-10-01T04:00:00Z"
CAMPAIGN_END = "2026-11-05T02:00:00Z"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class ScopeError(ValueError):
    """An evidence or scope boundary failed; no work may be admitted."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScopeError("duplicate JSON key")
        result[key] = value
    return result


def read_contracts(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Check retained original text, exact family membership, pins and DAG.

    Hash the original UTF-8 text, NOT an independently reserialized object.
    Return a fresh object so callers cannot mutate a cached accepted definition.
    """
    if len(rows) != len(FAMILIES):
        raise ScopeError("all 24 original family contracts are required")
    contracts, hashes = {}, {}
    for row in rows:
        family = row["family_id"]
        text, expected = row["contract_text"], row["contract_sha256"]
        if family not in FAMILIES or family in contracts:
            raise ScopeError("unknown or duplicate family; D06 is preservation-only")
        if not isinstance(text, str) or sha256_text(text) != expected:
            raise ScopeError("original contract bytes do not match receipt")
        try:
            contract = json.loads(text, object_pairs_hook=_strict_object,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ScopeError("non-finite JSON")))
        except (ValueError, TypeError) as exc:
            raise ScopeError("invalid contract JSON") from exc
        if not isinstance(contract, dict):
            raise ScopeError("contract must be an object")
        deps = contract.get("dependencies")
        if (not isinstance(deps, list) or any(not isinstance(d, str) for d in deps)
                or len(deps) != len(set(deps)) or any(d not in FAMILIES for d in deps)):
            raise ScopeError("invalid contract dependency")
        contracts[family], hashes[family] = contract, expected
    digest = sha256_text("\n".join(f"{f}:{hashes[f]}" for f in sorted(hashes)))
    if digest != CONTRACT_SET_SHA256:
        raise ScopeError("original 24-contract set changed")
    dependency_waves(contracts)
    return contracts


def dependency_waves(contracts: Mapping[str, Mapping[str, Any]]) -> tuple[tuple[str, ...], ...]:
    """Deterministic independent work groups, not permission to run adapters."""
    if set(contracts) != set(FAMILIES):
        raise ScopeError("incomplete family dependency graph")
    remaining = {f: set(c["dependencies"]) for f, c in contracts.items()}
    if any(not deps <= set(FAMILIES) for deps in remaining.values()):
        raise ScopeError("unknown dependency")
    waves = []
    while remaining:
        ready = tuple(sorted(f for f, deps in remaining.items() if not deps))
        if not ready:
            raise ScopeError("cyclic family dependencies")
        waves.append(ready)
        remaining = {f: deps - set(ready) for f, deps in remaining.items() if f not in ready}
    return tuple(waves)


def _utc(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ScopeError("invalid explicit UTC deadline") from exc
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ScopeError("deadline must specify UTC")
    return result


@dataclass(frozen=True)
class BoundedPartition:
    """Immutable proposal. It is not an executable bulk admission token.

    Provider/record maxima are reservations, never refreshed on retry. They are
    included in the stable key together with original deadline and source pins.
    A durable accounting adapter must reserve them atomically before execution.
    """
    manifest_sha256: str
    family: str
    unit_key: str
    mode: str
    source_receipt_sha256: str
    original_deadline: str
    max_requests: int
    max_records: int
    incremental_cost_microusd: int = 0

    def __post_init__(self):
        if self.family not in FAMILIES:
            raise ScopeError("family is not acquisition-admitted; D06 cannot be acquired")
        if self.mode not in {"retained_source_reuse", "provider_acquisition"}:
            raise ScopeError("unknown partition mode")
        if not isinstance(self.unit_key, str) or not self.unit_key or len(self.unit_key) > 512:
            raise ScopeError("bounded explicit unit key required")
        for value in (self.manifest_sha256, self.source_receipt_sha256):
            if not isinstance(value, str) or not _HASH.fullmatch(value):
                raise ScopeError("exact manifest/source evidence hash required")
        for value in (self.max_requests, self.max_records, self.incremental_cost_microusd):
            if type(value) is not int or value < 0:
                raise ScopeError("finite nonnegative integer accounting required")
        if self.max_records == 0 or self.max_records > 1_000_000:
            raise ScopeError("partition record reservation outside engineering bound")
        if self.max_requests > 200 or self.incremental_cost_microusd != 0:
            raise ScopeError("no new paid financial headroom")
        if self.mode == "retained_source_reuse" and self.max_requests != 0:
            raise ScopeError("retained-source reuse cannot consume provider requests")
        if self.mode == "provider_acquisition" and self.max_requests == 0:
            raise ScopeError("provider reservation must be explicit")
        if _utc(self.original_deadline) > _utc(CAMPAIGN_END):
            raise ScopeError("partition exceeds campaign bound")

    @property
    def idempotency_key(self) -> str:
        return "astra-bulk-v1-" + sha256_text(canonical(self.__dict__))

    def require_current(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ScopeError("current time must be timezone-aware")
        if now.astimezone(timezone.utc) >= _utc(self.original_deadline):
            raise ScopeError("original partition deadline expired; do not re-key")


def coverage_state(expected: int | None, verified: int, unavailable: int = 0) -> str:
    """No task count or missing denominator can certify coverage."""
    if any(type(n) is not int or n < 0 for n in (verified, unavailable)):
        raise ScopeError("invalid coverage count")
    if expected is None:
        return "UNKNOWN_DENOMINATOR"
    if type(expected) is not int or expected < 0 or verified + unavailable > expected:
        raise ScopeError("invalid coverage denominator")
    if unavailable:
        return "INCOMPLETE_UNAVAILABLE"
    if verified != expected:
        return "INCOMPLETE"
    # Even a counted complete set still needs independent source verification.
    return "COUNT_RECONCILED_NOT_CERTIFIED"
