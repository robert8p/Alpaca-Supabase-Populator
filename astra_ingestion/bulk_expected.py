"""Evidence-bound, bounded expected-unit planner for the Top-3,000 bulk target.

No network, provider calls, SQL mutations, deadline creation or admission.
Every family must provide independently retained, contract-bound denominator
and identity evidence before it can produce *staging* units. Staged units do not
certify coverage or release worker jobs. The production ledger must separately
reserve finite requests/records/costs and enforce dependencies and fencing.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import islice, product
from types import MappingProxyType
from typing import Mapping, Iterable

from .bulk_scope import (
    CAPTURE_KEY, FAMILIES, SHARED_FAMILIES, RETAINED_RECEIPT_SHA256,
    RetainedManifest, ScopeError, canonical, read_contracts, sha256_text,
)

SUPPORTED_BASES = frozenset({"company", "session", "company_session", "explicit"})
MAX_UNIT_PAGE = 256
MAX_EXPLICIT_UNITS = 200_000


def _digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class DenominatorEvidence:
    """External evidence that an exact family's expected-unit basis is complete.

    `declared_basis` must match the ORIGINAL family's contract literal
    `expected_unit_basis`. If the retained contract has no such field, no
    units are staged: a new verified contract binding is needed, not a guess.
    For explicit data the complete key collection itself is hashed and checked
    against `unit_keys_sha256`; `eligibility_sha256` pins independently acquired
    point-in-time identity/applicability evidence, not an operator checkbox.
    """
    family: str
    contract_sha256: str
    declared_basis: str
    eligibility_sha256: str
    unit_keys_sha256: str
    explicit_unit_keys: tuple[str, ...] = ()
    # Exact descriptive unit literal from an ORIGINAL retained family contract.
    # Never use it to infer a company/session basis: an independently proved,
    # complete, explicit unit-key population is required when no basis exists.
    original_expected_unit: str | None = None


@dataclass(frozen=True)
class FamilyExpectedUnits:
    family: str
    status: str
    count: int | None
    manifest_sha256: str | None
    reason: str
    basis: str | None = None


@dataclass(frozen=True)
class ExpectedUnitPlan:
    capture_key: str
    capture_receipt_sha256: str
    families: tuple[FamilyExpectedUnits, ...]
    source_bindings: Mapping[str, DenominatorEvidence]
    companies: tuple[str, ...]
    sessions: tuple[str, ...]

    def family(self, family: str) -> FamilyExpectedUnits:
        if family not in FAMILIES:
            raise ScopeError("unknown family; D06 is preservation-only")
        return next(item for item in self.families if item.family == family)

    def page(self, family: str, *, after_index: int = 0, limit: int = 128) -> tuple[tuple[str, ...], int | None]:
        """Stable bounded enumeration. Index valid only within manifest hash.

        This is a source-stage page, never a worker claim or acquisition token.
        No data-family completeness is inferred from the returned page.
        """
        item = self.family(family)
        if item.status != "READY_FOR_STAGING" or item.count is None:
            raise ScopeError("unverified expected-unit denominator cannot be paged")
        if type(after_index) is not int or not 0 <= after_index <= item.count:
            raise ScopeError("invalid bounded index cursor")
        if type(limit) is not int or not 1 <= limit <= MAX_UNIT_PAGE:
            raise ScopeError("page must be bounded to 1–256 units")
        evidence = self.source_bindings[family]
        if evidence.declared_basis == "company":
            seq: Iterable[str] = (f"company:{id}" for id in self.companies)
        elif evidence.declared_basis == "session":
            seq = (f"session:{date}" for date in self.sessions)
        elif evidence.declared_basis == "company_session":
            seq = (f"company:{id}/session:{date}" for id, date in product(self.companies, self.sessions))
        else:
            seq = iter(evidence.explicit_unit_keys)
        values = tuple(islice(seq, after_index, min(item.count, after_index + limit)))
        next_index = after_index + len(values)
        if len(values) != min(limit, item.count - after_index):
            raise ScopeError("source unit enumeration lost expected cardinality")
        return values, (next_index if next_index < item.count else None)


def plan_expected_units(
    capture: RetainedManifest,
    contract_rows: list[Mapping[str, object]],
    evidence: Mapping[str, DenominatorEvidence],
) -> ExpectedUnitPlan:
    """Fail closed per family; do not turn missing evidence into zero units.

    All 24 *original* contract receipts remain mandatory. A family with no
    verified unit-basis binding has UNKNOWN_DENOMINATOR; others can be staged
    independently without treating missing dependencies as completed.
    """
    if (not isinstance(capture, RetainedManifest) or capture.source_capture_key != CAPTURE_KEY
            or capture.original_receipt_sha256 != RETAINED_RECEIPT_SHA256
            or capture.checked_source_rows != 4136
            or len(capture.company_ids_by_rank) != 3000
            or len(set(capture.company_ids_by_rank)) != 3000
            or len(capture.sessions) != 42 or len(set(capture.sessions)) != 42
            or capture.scheduled_minutes != 16380
            or len(capture.preserved_d06_relations) != 1065):
        raise ScopeError("source capture missing or incomplete; cannot derive expected units")
    if not isinstance(evidence, Mapping) or any(f not in FAMILIES for f in evidence):
        raise ScopeError("unexpected unit evidence family (D06 is preservation-only)")
    contracts = read_contracts(contract_rows)
    digests = {r["family_id"]: r["contract_sha256"] for r in contract_rows}
    states = []
    bindings = {}
    for family in FAMILIES:
        definition = evidence.get(family)
        if definition is None:
            states.append(FamilyExpectedUnits(family, "UNKNOWN_DENOMINATOR", None, None,
                                             "missing independently retained contract and applicability evidence"))
            continue
        if not isinstance(definition, DenominatorEvidence) or definition.family != family:
            raise ScopeError("family evidence mismatch")
        if definition.contract_sha256 != digests[family]:
            raise ScopeError("expected-unit definition is not bound to original contract")
        basis = definition.declared_basis
        if basis not in SUPPORTED_BASES:
            raise ScopeError("unsupported or unqualified expected-unit basis")
        # Shared market/macro families cannot silently become 3,000 company jobs.
        if family in SHARED_FAMILIES and basis in {"company", "company_session"}:
            raise ScopeError("shared family cannot be multiplied by company population")
        original = contracts[family]
        literal = original.get("expected_unit")
        if (definition.original_expected_unit is not None and
                definition.original_expected_unit != literal):
            raise ScopeError("original expected-unit literal does not match pinned contract")
        # The actual 24 retained contracts describe 'expected_unit' in precise
        # domain terms; none grants permission to coarsen that population to a
        # company/session grid. The only safe path without an explicit original
        # basis is a completely enumerated external keyset bound to that literal.
        has_original_basis = original.get("expected_unit_basis") == basis
        verified_explicit_literal = (basis == "explicit" and isinstance(literal, str)
                                     and bool(literal.strip()) and
                                     definition.original_expected_unit == literal)
        if not (has_original_basis or verified_explicit_literal):
            states.append(FamilyExpectedUnits(family, "UNKNOWN_DENOMINATOR", None, None,
                                             "original contract has no proven keyset or enumeration basis"))
            continue
        if not _digest(definition.eligibility_sha256) or not _digest(definition.unit_keys_sha256):
            raise ScopeError("applicability and unit-list evidence hashes are mandatory")
        keys = definition.explicit_unit_keys
        if basis == "explicit":
            if (not isinstance(keys, tuple) or not 1 <= len(keys) <= MAX_EXPLICIT_UNITS
                    or any(not isinstance(k, str) or not k or len(k) > 256 for k in keys)
                    or tuple(sorted(set(keys))) != keys):
                raise ScopeError("explicit units must be bounded, unique, sorted and nonempty")
            count = len(keys)
            actual_units_sha = sha256_text(canonical(list(keys)))
        else:
            if keys:
                raise ScopeError("derived unit basis cannot also supply arbitrary explicit keys")
            if basis == "company":
                seq = (f"company:{id}" for id in capture.company_ids_by_rank)
                count = 3000
            elif basis == "session":
                seq = (f"session:{date}" for date in capture.sessions)
                count = 42
            else:
                # Company/session is only a candidate grid; the bound eligibility
                # evidence MUST establish lifecycle/identity validity separately.
                seq = (f"company:{id}/session:{date}" for id, date in product(capture.company_ids_by_rank, capture.sessions))
                count = 126000
            # A streaming digest avoids unbounded materialization of the grid.
            digest = hashlib.sha256()
            digest.update(b"[")
            for n, key in enumerate(seq):
                if n:
                    digest.update(b",")
                digest.update(canonical(key).encode("utf-8"))
            digest.update(b"]")
            actual_units_sha = digest.hexdigest()
        if definition.unit_keys_sha256 != actual_units_sha:
            raise ScopeError("expected-unit key list does not match independently pinned evidence")
        plan_sha = sha256_text(canonical({
            "capture": capture.original_receipt_sha256, "family": family,
            "contract": definition.contract_sha256, "basis": basis,
            "original_expected_unit": definition.original_expected_unit,
            "eligibility": definition.eligibility_sha256, "keys": actual_units_sha,
            "count": count, "version": 1,
        }))
        states.append(FamilyExpectedUnits(family, "READY_FOR_STAGING", count, plan_sha,
                                         "candidate unit keys only; independent coverage and worker admission remain open", basis))
        bindings[family] = definition
    return ExpectedUnitPlan(CAPTURE_KEY, capture.original_receipt_sha256,
                            tuple(states), MappingProxyType(bindings), capture.company_ids_by_rank, capture.sessions)