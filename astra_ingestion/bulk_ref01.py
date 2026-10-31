"""REF01 effective-dated US-security episode reconstruction (source-only).

Consumes *normalised* records from the five declared retained REF01 routes.
Does not query those routes, guess aliases or infer population closure from the
3,000 accepted companies. This produces a candidate universe and explicit holds,
not an independently verified denominator, trading signal or worker permission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Mapping, Iterable
import re

from .bulk_scope import CAPTURE_KEY, RETAINED_RECEIPT_SHA256, ScopeError, canonical, sha256_text

ROUTES = frozenset({
    "reference.alpaca_fixed_window_instruments_v1",
    "market_reference.instrument_classification",
    "reference.equity_identity_resolution_day_v5",
    "reference.equity_resolved_security_v5",
    "reference.massive_security_master_observation_v1",
})
WINDOW_START, WINDOW_END = date(2026, 8, 1), date(2026, 10, 1)
REQUIRED = (
    "company_id", "issuer_id", "security_id", "ticker_alias",
    "listing_start", "listing_end", "type", "exchange",
    "rank_date_market_cap", "share_class_components", "ADR_ratio",
    "FX", "source_vintage",
)
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_ROWS = 200_000


@dataclass(frozen=True)
class Ref01Candidate:
    candidate_unit_keys: tuple[str, ...]
    observed_security_episode_count: int
    selected_company_count: int
    company_without_candidate_episodes: tuple[str, ...]
    held_record_count: int
    late_publication_count: int
    metadata_fingerprint_sha256: str
    membership_sha256: str
    status: str = "DENOMINATOR_AND_REVIEW_UNRESOLVED"

    @property
    def worker_admission_authorized(self) -> bool:
        return False


def _date(value: object, *, required: bool = True) -> date | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ScopeError("REF01 effective dates require exact YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ScopeError("REF01 impossible effective date") from exc


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ScopeError("REF01 historical publication time missing")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopeError("REF01 invalid publication timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ScopeError("REF01 publication time not exact UTC")
    return dt


def compile_ref01_candidates(
    accepted_company_ids: tuple[str, ...],
    normalized_records: Iterable[Mapping[str, object]],
    *,
    snapshot_sha256: str,
    as_of_utc: str = "2026-08-03T20:00:00Z",
) -> Ref01Candidate:
    """Preserve missing/held episodes and temporal ambiguity as explicit gaps.

    Eligible classification is evidence supplied by a future source projector;
    neither a ticker suffix nor a provider row implies an eligible common/ADR.
    Every source row is tied to one declared route and its immutable receipt.
    No source absence is converted to a company-level N/A determination.
    """
    if (not isinstance(accepted_company_ids, tuple)
            or len(accepted_company_ids) != 3000
            or len(set(accepted_company_ids)) != 3000
            or any(not isinstance(x, str) or not x or len(x) > 128
                   for x in accepted_company_ids)
            or not isinstance(snapshot_sha256, str)
            or HEX.fullmatch(snapshot_sha256) is None):
        raise ScopeError("REF01 membership must reuse exact 3,000-company cohort and source snapshot")
    as_of = _timestamp(as_of_utc)
    selected = set(accepted_company_ids)
    episodes: dict[str, tuple[str, str, date, date, str]] = {}
    lifecycles: dict[str, list[tuple[date, date, str]]] = {}
    seen_sources: set[tuple[str, str]] = set()
    with_episode: set[str] = set()
    held = 0
    late = 0
    seen = 0
    proof_rows: list[tuple[str, str, str]] = []
    for row in normalized_records:
        seen += 1
        if seen > MAX_ROWS:
            raise ScopeError("REF01 source enumeration exceeds finite bound")
        if not isinstance(row, Mapping):
            raise ScopeError("REF01 source row malformed")
        route, digest = row.get("source_route"), row.get("source_sha256")
        if route not in ROUTES or not isinstance(digest, str) or HEX.fullmatch(digest) is None:
            raise ScopeError("REF01 source route or receipt not pinned")
        source_key = row.get("source_record_key")
        if not isinstance(source_key, str) or not 1 <= len(source_key) <= 256:
            raise ScopeError("REF01 source record lacks stable key")
        receipt_key = (route, source_key)
        if receipt_key in seen_sources:
            raise ScopeError("REF01 duplicate source observation, not a new episode")
        seen_sources.add(receipt_key)
        company = row.get("company_id")
        if company not in selected:
            # Unselected entities cannot silently enlarge or certify the cohort.
            raise ScopeError("REF01 source contains unselected company mapping")
        publication = _timestamp(row.get("published_at_utc"))
        if publication > as_of:
            late += 1
        classification = row.get("eligibility_state")
        if classification not in ("ELIGIBLE", "EXCLUDED_WITH_EVIDENCE", "HELD"):
            raise ScopeError("REF01 class eligibility requires explicit source evidence")
        proof_rows.append((route, source_key, digest))
        # Any excluded class must have a separate durable source explanation.
        if classification == "EXCLUDED_WITH_EVIDENCE":
            if (not isinstance(row.get("exclusion_evidence_sha256"), str)
                    or HEX.fullmatch(row["exclusion_evidence_sha256"]) is None):
                raise ScopeError("REF01 unproved exclusion cannot be N/A")
            continue
        if classification == "HELD":
            held += 1
            continue
        missing = [x for x in REQUIRED if x not in row or (row[x] is None and x != "listing_end")]
        if missing:
            held += 1
            continue
        for field in ("issuer_id", "security_id", "ticker_alias", "type",
                      "exchange", "source_vintage"):
            value = row[field]
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ScopeError("REF01 required identifier or source vintage invalid")
        start = _date(row["listing_start"])
        stop = _date(row["listing_end"], required=False)
        stop = stop or WINDOW_END
        if stop <= start:
            raise ScopeError("REF01 effective episode has inverted interval")
        start, stop = max(start, WINDOW_START), min(stop, WINDOW_END)
        if stop <= start:
            continue  # Outside selected window, with dated source evidence.
        sec = str(row["security_id"])
        key = f"company:{company}/security:{sec}/episode:{start.isoformat()}:{stop.isoformat()}"
        if len(key) > 512:
            raise ScopeError("REF01 episode key exceeds bound")
        # Different ticker aliases may share a security ID only in disjoint
        # valid windows; same episode from different sources must be adjudicated.
        for left, right, prior_company in lifecycles.get(sec, ()):
            if start < right and left < stop:
                raise ScopeError("REF01 security episode overlaps; identity conflict requires adjudication")
        if key in episodes:
            raise ScopeError("REF01 duplicate effective-dated episode")
        episodes[key] = (company, sec, start, stop, digest)
        lifecycles.setdefault(sec, []).append((start, stop, company))
        with_episode.add(company)
    company_keys = tuple(f"company:{id}" for id in accepted_company_ids)
    membership_hash = sha256_text(canonical(list(accepted_company_ids)))
    keys = tuple(sorted((*company_keys, *episodes)))
    return Ref01Candidate(
        candidate_unit_keys=keys,
        observed_security_episode_count=len(episodes),
        selected_company_count=len(accepted_company_ids),
        company_without_candidate_episodes=tuple(sorted(selected - with_episode)),
        held_record_count=held,
        late_publication_count=late,
        metadata_fingerprint_sha256=sha256_text(canonical({
            "capture_key": CAPTURE_KEY,
            "retained_receipt": RETAINED_RECEIPT_SHA256,
            "membership_sha256": membership_hash,
            "snapshot": snapshot_sha256,
            "company_count": 3000,
            "source_rows": sorted(proof_rows),
            "episodes": sorted(
                [key, ep[4]] for key, ep in episodes.items()
            ),
            "held": held,
            "late": late,
        })),
        membership_sha256=membership_hash,
    )
