"""Fail-closed, full-24-family source-unit reconciliation before bulk admission.

No network, SQL, provider calls, mutable counters or job creation. The output is
a candidate for INDEPENDENT review, never a database admission credential.
Raw source values, licences and credentials must not enter these fingerprints.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Any

from .bulk_expected import ExpectedUnitPlan, MAX_UNIT_PAGE, plan_expected_units
from .bulk_scope import (
    CAPTURE_KEY, FAMILIES, RETAINED_RECEIPT_SHA256, RetainedManifest,
    ScopeError, canonical, read_contracts, sha256_text,
)

_DIGEST_CHARS = frozenset("0123456789abcdef")
_FIELDS = ("unit_key", "source_sha256", "provenance_sha256",
           "identity_sha256", "point_in_time_sha256")


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _DIGEST_CHARS


@dataclass(frozen=True)
class FamilySourcePin:
    family: str
    contract_sha256: str
    expected_manifest_sha256: str
    source_snapshot_sha256: str
    source_receipt_sha256: str


@dataclass(frozen=True)
class FamilyPreflight:
    family: str
    status: str
    expected_count: int | None
    observed_count: int | None
    missing_count: int | None
    extra_count: int | None
    observation_sha256: str | None


@dataclass(frozen=True)
class ManifestPreflight:
    capture_key: str
    capture_receipt_sha256: str
    family_results: tuple[FamilyPreflight, ...]
    review_fingerprint_sha256: str | None
    status: str

    @property
    def worker_admission_authorized(self) -> bool:
        # An authenticated restricted-runtime reviewer + durable DB admission
        # must check the actual source bytes, PIT and identity evidence.
        return False


def _expected_keys(plan: ExpectedUnitPlan, family: str) -> set[str]:
    state = plan.family(family)
    if state.count is None or state.count < 1 or state.count > 200_000:
        raise ScopeError("nonfinite or out-of-bound expected family population")
    keys: set[str] = set()
    cursor = 0
    while True:
        batch, next_cursor = plan.page(family, after_index=cursor, limit=MAX_UNIT_PAGE)
        if not batch:
            raise ScopeError("expected unit enumeration stopped early")
        for key in batch:
            if not isinstance(key, str) or not key or len(key) > 512 or key in keys:
                raise ScopeError("duplicate or malformed expected unit key")
            keys.add(key)
        if next_cursor is None:
            break
        if type(next_cursor) is not int or next_cursor <= cursor or next_cursor > state.count:
            raise ScopeError("expected source unit cursor did not advance")
        cursor = next_cursor
    if len(keys) != state.count:
        raise ScopeError("expected source unit cardinality mismatch")
    return keys


def _read_witness(
    family: str, expected_count: int,
    read_page: Callable[[str, str | None, int], Mapping[str, Any]],
    page_limit: int,
) -> tuple[set[str], str]:
    after: str | None = None
    keys: set[str] = set()
    digest_rows: list[list[str]] = []
    # Bound hostile nonadvancing pages even when source has extra rows.
    max_pages = (expected_count // page_limit) + 3
    for _ in range(max_pages):
        page = read_page(family, after, page_limit)
        if (not isinstance(page, Mapping) or type(page.get("has_more")) is not bool
                or not isinstance(page.get("rows"), list)):
            raise ScopeError("source reader must return rows and explicit has_more")
        rows = page["rows"]
        if len(rows) > page_limit or (not rows and page["has_more"]):
            raise ScopeError("source reader page overflow or no progress")
        for row in rows:
            if not isinstance(row, Mapping) or any(not isinstance(row.get(field), str)
                                                   for field in _FIELDS):
                raise ScopeError("source row lacks independent unit/provenance/identity/PIT pins")
            key = row["unit_key"]
            if (not key or len(key) > 512 or (after is not None and key <= after)
                    or key in keys or any(not _digest(row[name]) for name in _FIELDS[1:])):
                raise ScopeError("source keyset duplicated, unordered or missing mandatory evidence hash")
            keys.add(key)
            digest_rows.append([row[name] for name in _FIELDS])
            after = key
            if len(keys) > expected_count + 1:
                raise ScopeError("source returned more than the expected bounded population")
        if not page["has_more"]:
            return keys, sha256_text(canonical(digest_rows))
    raise ScopeError("source keyset failed finite pagination")


def compile_manifest_preflight(
    capture: RetainedManifest,
    plan: ExpectedUnitPlan,
    contract_rows: list[Mapping[str, object]],
    source_pins: Mapping[str, FamilySourcePin],
    read_page: Callable[[str, str | None, int], Mapping[str, Any]],
    *, page_limit: int = 128,
) -> ManifestPreflight:
    """Reconcile every expected unit to a bounded external witnessed keyset.

    Witness records are metadata hashes, not independently verified raw data.
    A structurally reconciled output must NOT be submitted directly to the bulk
    ledger. Missing family proofs produce explicit blockers; inconsistent proofs
    raise ScopeError. No subset can be described as full manifest admission.
    """
    if (not isinstance(plan, ExpectedUnitPlan) or plan.capture_key != CAPTURE_KEY
            or plan.capture_receipt_sha256 != RETAINED_RECEIPT_SHA256
            or tuple(x.family for x in plan.families) != FAMILIES):
        raise ScopeError("incomplete or unpinned full 24-family expected plan")
    if (type(page_limit) is not int or not 1 <= page_limit <= MAX_UNIT_PAGE
            or not isinstance(source_pins, Mapping)
            or any(f not in FAMILIES for f in source_pins)
            or not callable(read_page)):
        raise ScopeError("unbounded page, unknown family or missing source adapter")
    # Recompute the entire planner from the original pinned capture and proofs;
    # an arbitrarily constructed ExpectedUnitPlan object cannot pass this gate.
    reconstructed = plan_expected_units(capture, contract_rows, plan.source_bindings)
    if (reconstructed.families != plan.families
            or reconstructed.companies != plan.companies
            or reconstructed.sessions != plan.sessions):
        raise ScopeError("expected-unit planner does not match the retained capture and original contracts")
    plan = reconstructed
    contracts = read_contracts(contract_rows)
    hashes = {row["family_id"]: row["contract_sha256"] for row in contract_rows}
    results: list[FamilyPreflight] = []
    for family in FAMILIES:
        item = plan.family(family)
        if item.status != "READY_FOR_STAGING" or item.count is None or not _digest(item.manifest_sha256):
            results.append(FamilyPreflight(family, "BLOCKED_EXPECTED_POPULATION", item.count,
                                           None, None, None, None))
            continue
        pin = source_pins.get(family)
        if pin is None:
            results.append(FamilyPreflight(family, "BLOCKED_MISSING_SOURCE_PIN", item.count,
                                           None, None, None, None))
            continue
        if (not isinstance(pin, FamilySourcePin) or pin.family != family
                or pin.contract_sha256 != hashes[family]
                or pin.expected_manifest_sha256 != item.manifest_sha256
                or not all(_digest(x) for x in
                           (pin.contract_sha256, pin.source_snapshot_sha256,
                            pin.source_receipt_sha256))):
            raise ScopeError("family source proof does not bind exact original contract, expected units and snapshot")
        if not isinstance(contracts[family].get("dependencies"), list):
            raise ScopeError("original dependency graph missing")
        expected = _expected_keys(plan, family)
        observed, observed_sha = _read_witness(family, len(expected), read_page, page_limit)
        if observed_sha != pin.source_receipt_sha256:
            raise ScopeError("observed source keyset/metadata receipt differs from pinned source receipt")
        missing, extra = len(expected - observed), len(observed - expected)
        results.append(FamilyPreflight(
            family,
            "STRUCTURALLY_RECONCILED_REVIEW_REQUIRED" if not (missing or extra) else "BLOCKED_SOURCE_GAPS",
            len(expected), len(observed), missing, extra, observed_sha,
        ))
    all_ready = all(x.status == "STRUCTURALLY_RECONCILED_REVIEW_REQUIRED" for x in results)
    fingerprint = sha256_text(canonical({
        "capture_key": CAPTURE_KEY, "receipt": RETAINED_RECEIPT_SHA256,
        "families": [[x.family, hashes[x.family], plan.family(x.family).manifest_sha256,
                      source_pins[x.family].source_snapshot_sha256, x.observation_sha256]
                     for x in results],
        "version": 1,
    })) if all_ready else None
    return ManifestPreflight(
        CAPTURE_KEY, RETAINED_RECEIPT_SHA256, tuple(results), fingerprint,
        "INDEPENDENT_REVIEW_REQUIRED" if all_ready else "BLOCKED_INCOMPLETE_FAMILY_EVIDENCE",
    )
