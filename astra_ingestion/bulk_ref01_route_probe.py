"""Finite read-only page plans for the five ORIGINAL REF01 source relations.

These are executable query *plans* for a separately authenticated READ-ONLY
PostgreSQL client, not a database connection, admission token or certified
historical security universe. Only native metadata needed for mapping and
point-in-time checks is selected; provider payloads and prices are excluded.

The original capture contains 3,000 accepted company anchor FIGIs but does NOT
certify historical security episodes, qualified rank-date market caps, listing
start dates or a complete denominator. A returned zero is a source gap, not N/A.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
import re
from typing import Any, Mapping, Sequence

from .bulk_ref01 import ROUTES
from .bulk_scope import ScopeError, canonical, sha256_text

MAX_PAGE = 128
WINDOW_START = "2026-08-01"
WINDOW_END_EXCLUSIVE = "2026-10-01"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FIGI = re.compile(r"[A-Z0-9]{12}\Z")


@dataclass(frozen=True)
class RouteSpec:
    key_fields: tuple[str, ...]
    selected_fields: tuple[str, ...]
    window_field: str | None = None


# Confirmed against the exact original five live relation schemas on 29 Oct.
# Primary/unique key ordering is pinned: no OFFSET, arbitrary SQL or wildcard.
SPECS: dict[str, RouteSpec] = {
    "reference.alpaca_fixed_window_instruments_v1": RouteSpec(
        ("symbol",),
        ("symbol", "alpaca_asset_id", "exchange", "massive_type",
         "instrument_key", "classification_observed_at", "provenance"),
    ),
    "market_reference.instrument_classification": RouteSpec(
        ("provider", "instrument_key", "source_row_hash"),
        ("provider", "instrument_key", "source_row_hash", "instrument_type",
         "classified_at", "confidence", "source_project_ref"),
    ),
    "reference.equity_identity_resolution_day_v5": RouteSpec(
        ("observation_id",),
        ("observation_id", "instrument_key", "identity_anchor",
         "source_row_sha256", "recorded_at", "verified", "verification"),
    ),
    "reference.equity_resolved_security_v5": RouteSpec(
        ("security_key",),
        ("security_key", "instrument_key", "composite_figi", "share_class_figi",
         "cik", "primary_exchange", "native_symbol", "security_type",
         "trade_form", "created_at", "evidence"),
    ),
    "reference.massive_security_master_observation_v1": RouteSpec(
        ("observation_id",),
        ("observation_id", "instrument_key", "composite_figi",
         "share_class_figi", "ticker", "requested_as_of", "security_type",
         "primary_exchange", "currency_name", "delisted_utc",
         "provider_last_updated_utc", "research_available_at",
         "source_observed_at", "source_route", "row_hash"),
        "requested_as_of",
    ),
}
if frozenset(SPECS) != ROUTES:
    raise RuntimeError("REF01 source plan drifted from original five routes")


@dataclass(frozen=True)
class RoutePagePlan:
    route: str
    query: str
    params: tuple[Any, ...]
    limit: int
    cursor: tuple[Any, ...] | None
    status: str = "READ_ONLY_SOURCE_PROBE_NOT_ADMISSION"


def _cursor(spec: RouteSpec, cursor: tuple[Any, ...] | None) -> tuple[Any, ...] | None:
    if cursor is None:
        return None
    if not isinstance(cursor, tuple) or len(cursor) != len(spec.key_fields):
        raise ScopeError("REF01 malformed source keyset cursor")
    for field, value in zip(spec.key_fields, cursor):
        if field in {"instrument_key", "observation_id"}:
            if type(value) is not int or value < 0:
                raise ScopeError("REF01 numeric source cursor must be nonnegative integer")
        elif not isinstance(value, str) or not value or len(value) > 256:
            raise ScopeError("REF01 source cursor requires bounded stable text")
    return cursor


def plan_route_page(
    route: str,
    *,
    after: tuple[Any, ...] | None = None,
    limit: int = 128,
    anchor_figis: tuple[str, ...] = (),
) -> RoutePagePlan:
    """Fixed SQL identifiers; all caller values are query parameters.

    The large Massive table is *always* scoped to the selected FIGIs and the
    Aug-Sep date window. Its requested_as_of is NOT a publication timestamp.
    Other routes are finite keyset scans with no inferred historical validity.
    Callers must use a consistent database snapshot for successive pages.
    """
    if route not in SPECS:
        raise ScopeError("REF01 only permits the five exact source routes")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise ScopeError("REF01 read page must be bounded to 1-128 rows")
    spec = SPECS[route]
    last = _cursor(spec, after)
    params: list[Any] = []
    conditions = []
    if spec.window_field:
        if (not isinstance(anchor_figis, tuple) or not 1 <= len(anchor_figis) <= 3000
                or tuple(sorted(set(anchor_figis))) != anchor_figis
                or any(not isinstance(f, str) or not _FIGI.fullmatch(f)
                       for f in anchor_figis)):
            raise ScopeError("Massive window probe requires pinned sorted unique cohort FIGIs")
        conditions.append("(composite_figi = ANY(%s) OR share_class_figi = ANY(%s))")
        params.extend([list(anchor_figis), list(anchor_figis)])
        conditions.append("requested_as_of >= %s AND requested_as_of < %s")
        params.extend([WINDOW_START, WINDOW_END_EXCLUSIVE])
    if last is not None:
        lhs = "(" + ",".join(spec.key_fields) + ")"
        rhs = "(" + ",".join("%s" for _ in last) + ")"
        conditions.append(lhs + " > " + rhs)
        params.extend(last)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = (
        "SELECT " + ",".join(spec.selected_fields) + " FROM " + route
        + where + " ORDER BY " + ",".join(spec.key_fields) + " LIMIT %s"
    )
    params.append(limit)
    return RoutePagePlan(route, query, tuple(params), limit, last)


@dataclass(frozen=True)
class RoutePageEvidence:
    route: str
    page_rows: int
    next_cursor: tuple[Any, ...] | None
    page_sha256: str
    actual_window_observations: int
    available_by_rank_date: int
    late_or_unknown_publication: int
    status: str = "OBSERVED_SOURCE_PAGE_NOT_POPULATION_CLOSURE"

    @property
    def worker_admission_authorized(self) -> bool:
        return False


def inspect_route_page(
    plan: RoutePagePlan,
    rows: Sequence[Mapping[str, Any]],
    *,
    source_snapshot_sha256: str,
    rank_date_cutoff: str = "2026-08-03T20:00:00Z",
) -> RoutePageEvidence:
    """Fail-closed, source-byte candidate receipt; never an independent seal.

    The result is ONLY a page witness. If an input relation has no publication
    timestamp, all observations are classified publication-UNKNOWN, including
    a source creation/ingestion timestamp. A received row is never silently
    evidence that a security was listed through the entire target window.
    """
    if (not isinstance(plan, RoutePagePlan) or plan.route not in SPECS
            or not isinstance(source_snapshot_sha256, str)
            or not _SHA.fullmatch(source_snapshot_sha256)):
        raise ScopeError("REF01 page lacks pinned source snapshot")
    if (not isinstance(rows, (tuple, list)) or len(rows) > plan.limit
            or any(not isinstance(x, Mapping) for x in rows)):
        raise ScopeError("REF01 source response malformed or unbounded")
    if not isinstance(rank_date_cutoff, str):
        raise ScopeError("REF01 rank date cutoff must be an explicit UTC timestamp")
    try:
        cutoff = datetime.fromisoformat(rank_date_cutoff.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopeError("REF01 malformed rank date cutoff") from exc
    if cutoff.tzinfo is None or cutoff.utcoffset().total_seconds() != 0:
        raise ScopeError("REF01 cutoff must be exact UTC")
    spec = SPECS[plan.route]
    previous = plan.cursor
    witnessed: list[dict[str, Any]] = []
    def json_primitive(value: Any) -> Any:
        if isinstance(value, (date, datetime, UUID, Decimal)):
            return str(value) if isinstance(value, (UUID, Decimal)) else value.isoformat()
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        if isinstance(value, (tuple, list)):
            return [json_primitive(v) for v in value]
        if isinstance(value, Mapping):
            if any(not isinstance(k, str) for k in value):
                raise ScopeError("REF01 source JSON has non-string key")
            return {k: json_primitive(v) for k, v in value.items()}
        raise ScopeError("REF01 source contains unsupported native metadata type")
    window = 0
    available = 0
    late = 0
    for row in rows:
        if any(field not in row for field in spec.selected_fields):
            raise ScopeError("REF01 source native column missing; do not infer value")
        key = _cursor(spec, tuple(row[f] for f in spec.key_fields))
        if key is None or (previous is not None and key <= previous):
            raise ScopeError("REF01 source page duplicate or unordered key")
        previous = key
        observed_window = False
        if spec.window_field:
            scoped = set(plan.params[0])
            if (row.get("composite_figi") not in scoped
                    and row.get("share_class_figi") not in scoped):
                raise ScopeError("Massive row not joined to the accepted cohort FIGIs")
            if (row.get("row_hash") is not None
                    and (not isinstance(row["row_hash"], str)
                         or not _SHA.fullmatch(row["row_hash"]))):
                raise ScopeError("Massive row native hash invalid")
            raw_date = row.get(spec.window_field)
            if isinstance(raw_date, date) and not isinstance(raw_date, datetime):
                raw_date = raw_date.isoformat()
            if not isinstance(raw_date, str):
                raise ScopeError("Massive requested_as_of must be a date")
            try:
                d = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ScopeError("invalid Massive as-of date") from exc
            if not (date.fromisoformat(WINDOW_START) <= d <
                    date.fromisoformat(WINDOW_END_EXCLUSIVE)):
                raise ScopeError("source returned an out-of-window observation")
            observed_window = True
            window += 1
            # source_observed_at and loaded_at are NOT historical publication.
            raw_availability = row.get("research_available_at")
            if isinstance(raw_availability, datetime):
                dt = raw_availability
            elif isinstance(raw_availability, str):
                try:
                    dt = datetime.fromisoformat(raw_availability.replace("Z", "+00:00"))
                except ValueError:
                    dt = None
            else:
                dt = None
            if (dt is not None and dt.tzinfo is not None
                    and dt.utcoffset().total_seconds() == 0 and dt <= cutoff):
                available += 1
            else:
                late += 1
        else:
            late += 1
        # Do not include provider raw_payload, prices or secrets in the receipt.
        # A canonical hash of projected metadata is not a source-provider seal.
        witnessed.append({field: json_primitive(row[field])
                          for field in spec.selected_fields})
    return RoutePageEvidence(
        plan.route, len(rows), previous,
        sha256_text(canonical({"route": plan.route,
                               "snapshot": source_snapshot_sha256,
                               "cursor": plan.cursor,
                               "rows": witnessed})),
        window, available, late,
    )
