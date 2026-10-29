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


# These are evidence-capture kinds, NOT the 24 research datasets' coverage.
RETAINED_COUNTS = {
    "scope": 1, "cohort": 1, "membership": 1, "company": 3000,
    "contract": 24, "calendar": 42, "preservation": 1065,
    "acceptance_event": 2,
}
RETAINED_RECEIPT_SHA256 = "ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496"
MAX_EVIDENCE_PAGE = 256


@dataclass(frozen=True)
class RetainedManifest:
    """Bounded checked source inventory. Not bulk admission or data acceptance."""

    source_capture_key: str
    original_receipt_sha256: str
    checked_source_rows: int
    company_ids_by_rank: tuple[str, ...]
    sessions: tuple[str, ...]
    scheduled_minutes: int
    preserved_d06_relations: tuple[str, ...]
    family_dependency_waves: tuple[tuple[str, ...], ...]
    # SQL's jsonb_agg receipt is not the same as Python JSON serialization.
    # Independent SQL verification of that aggregate is a SEPARATE gate.
    aggregate_receipt_independently_verified: bool = False
    research_dataset_coverage_certified: bool = False


def read_retained_capture(
    receipt: Mapping[str, Any],
    read_page: Any,
    *,
    page_limit: int = 128,
) -> RetainedManifest:
    """Validate every retained source document using a finite keyset reader.

    Caller supplies a READ-ONLY, consistent-snapshot callback with signature
      read_page(after=(kind,key)|None, limit=page_limit)
        -> {"rows": list[dict], "has_more": bool}.
    It must keyset-filter on (kind,evidence_key) and order strictly ascending.
    Never use offset pagination or turn missing pages into empty populations.
    This performs NO database or provider writes, admits NO acquisition and
    deliberately does not claim independent PostgreSQL JSONB aggregate equality.
    """
    if not isinstance(receipt, Mapping):
        raise ScopeError("retained capture receipt missing")
    if (receipt.get("capture_key") != CAPTURE_KEY
            or receipt.get("evidence_sha256") != RETAINED_RECEIPT_SHA256
            or type(receipt.get("evidence_rows")) is not int
            or receipt["evidence_rows"] != sum(RETAINED_COUNTS.values())
            or receipt.get("state") != "CAPTURED_NOT_ADMITTED"
            or type(receipt.get("provider_requests")) is not int
            or receipt["provider_requests"] != 0
            or type(receipt.get("incremental_cost_microusd")) is not int
            or receipt["incremental_cost_microusd"] != 0):
        raise ScopeError("retained capture receipt does not match pinned scope and zero-cost capture")
    if type(page_limit) is not int or not 1 <= page_limit <= MAX_EVIDENCE_PAGE:
        raise ScopeError("finite bounded page limit required")
    if not callable(read_page):
        raise ScopeError("bounded source reader callback required")

    counts = {kind: 0 for kind in RETAINED_COUNTS}
    companies: dict[int, str] = {}
    sessions: dict[str, int] = {}
    preservation: set[str] = set()
    contracts = []
    after: tuple[str, str] | None = None
    checked = 0
    pages = 0

    while True:
        pages += 1
        if pages > receipt["evidence_rows"] + 1:
            raise ScopeError("retained source page count exceeded")
        page = read_page(after, page_limit)
        if (not isinstance(page, Mapping) or type(page.get("has_more")) is not bool
                or not isinstance(page.get("rows"), list)):
            raise ScopeError("source page needs explicit rows and has_more")
        rows = page["rows"]
        if len(rows) > page_limit or (not rows and page["has_more"]):
            raise ScopeError("source page incomplete, oversized or nonadvancing")
        if checked + len(rows) > receipt["evidence_rows"]:
            raise ScopeError("source evidence exceeds pinned receipt count")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ScopeError("malformed source evidence row")
            kind, key, body, digest = (
                row.get("kind"), row.get("evidence_key"),
                row.get("source_text"), row.get("source_sha256"),
            )
            if (kind not in RETAINED_COUNTS or not isinstance(key, str) or not key
                    or not isinstance(body, str) or not isinstance(digest, str)
                    or not _HASH.fullmatch(digest)):
                raise ScopeError("invalid source evidence kind/key/body/hash")
            cursor = (kind, key)
            if after is not None and cursor <= after:
                raise ScopeError("source keyset duplicate or out-of-order item")
            if sha256_text(body) != digest:
                raise ScopeError("retained source evidence bytes/hash mismatch")
            after = cursor
            counts[kind] += 1
            checked += 1
            if counts[kind] > RETAINED_COUNTS[kind]:
                raise ScopeError("retained evidence kind exceeds pinned cardinality")
            if kind in {"company", "calendar", "preservation"}:
                try:
                    obj = json.loads(body, object_pairs_hook=_strict_object,
                                     parse_constant=lambda _: (_ for _ in ()).throw(ScopeError("non-finite JSON")))
                except (ValueError, TypeError) as exc:
                    raise ScopeError("invalid retained source JSON") from exc
                if not isinstance(obj, dict):
                    raise ScopeError("source record must be an object")
                if kind == "company":
                    rank = obj.get("selection_order")
                    company_id = obj.get("company_id")
                    if (type(rank) is not int or not 1 <= rank <= 3000
                            or not isinstance(company_id, str) or company_id != key
                            or rank in companies or company_id in companies.values()):
                        raise ScopeError("company membership key/rank invalid or duplicated")
                    if (obj.get("membership_accepted") is not True
                            or obj.get("exact_global_rank_certified") is not False
                            or obj.get("financial_capitalization_qualified") is not False
                            or obj.get("full_period_instrument_coverage_accepted") is not False):
                        raise ScopeError("retained company qualification flags drift")
                    companies[rank] = company_id
                elif kind == "calendar":
                    date_text = obj.get("session_date")
                    minutes = obj.get("regular_scheduled_minutes")
                    if (date_text != key or not isinstance(date_text, str)
                            or not re.fullmatch(r"2026-(08|09)-[0-3][0-9]", date_text)
                            or type(minutes) is not int or not 1 <= minutes <= 390
                            or key in sessions):
                        raise ScopeError("calendar session, minutes or key invalid")
                    sessions[key] = minutes
                else:
                    if obj.get("relation_name") != key or key in preservation:
                        raise ScopeError("preserved D06 catalogue key invalid or duplicated")
                    preservation.add(key)
            elif kind == "contract":
                contracts.append({"family_id": key, "contract_text": body,
                                  "contract_sha256": digest})
        if not page["has_more"]:
            break
        if not rows:
            raise ScopeError("retained source reader did not advance")

    if checked != receipt["evidence_rows"] or counts != RETAINED_COUNTS:
        raise ScopeError("retained source evidence incomplete or missing kind")
    if (set(companies) != set(range(1, 3001)) or len(sessions) != 42
            or sum(sessions.values()) != 16380
            or min(sessions) != "2026-08-03" or max(sessions) != "2026-09-30"
            or len(preservation) != 1065):
        raise ScopeError("retained membership, calendar or D06 inventory incomplete")
    checked_contracts = read_contracts(contracts)
    return RetainedManifest(
        source_capture_key=CAPTURE_KEY,
        original_receipt_sha256=receipt["evidence_sha256"],
        checked_source_rows=checked,
        company_ids_by_rank=tuple(companies[i] for i in range(1, 3001)),
        sessions=tuple(sorted(sessions)),
        scheduled_minutes=sum(sessions.values()),
        preserved_d06_relations=tuple(sorted(preservation)),
        family_dependency_waves=dependency_waves(checked_contracts),
    )
