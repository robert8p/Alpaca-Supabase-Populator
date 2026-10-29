"""Bounded P01/P02 retained Alpaca SIP source probe, NOT an ingestion/admission route.

Original 24-family contracts are preserved. P01 expects eligible security-session-
minute/bar-field units and P02 extended-session equivalents. Source row existence
is neither an independent expected minute calendar nor evidence of a no-trade
publication. August parent rows stop at 2026-08-31 in the retained relation;
the September window has no rows there, and the original enriched view is
derived from the SAME parent and cannot serve as an independent alternative.

A separately authenticated, read-only PostgreSQL client may execute these fixed
parameterized plans under an independently pinned snapshot. The implementation
cannot acquire licensed data, certify coverage, authorize a worker or spend funds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import isfinite
from typing import Any, Mapping, Sequence
import re

from .bulk_scope import ScopeError, canonical

SOURCE = "market_fixed_20250901_20260831.alpaca_sip_bars_1m"
DERIVED_VIEW = "market_fixed_20250901_20260831.us_equities_bars_1m"
FAMILY_SOURCE_ROUTES = {
    "P01": frozenset((SOURCE, DERIVED_VIEW)),
    "P02": frozenset((SOURCE,)),
}
FIELDS = (
    "instrument_key", "bar_ts", "session_label", "open", "high",
    "low", "close", "volume", "trade_count", "vwap",
    "loaded_by_job_id", "source_loaded_at",
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_KEYS = 128
MAX_PAGE = 128
MIN_WINDOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
END_WINDOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
LABELS = {
    "P01": frozenset(("regular",)),
    "P02": frozenset(("premarket", "postmarket", "overnight")),
}


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ScopeError("source timestamp must be valid UTC") from exc
    else:
        raise ScopeError("source timestamp must be valid UTC")
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ScopeError("source timestamp must be exact UTC")
    if result.second != 0 or result.microsecond != 0:
        raise ScopeError("source timestamp must align to an exact minute")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class PricePagePlan:
    family: str
    route: str
    query: str
    instrument_keys: tuple[int, ...]
    start: datetime
    end: datetime
    limit: int
    after: tuple[int, datetime] | None
    source_snapshot_sha256: str
    status: str = "READ_ONLY_RETAINED_SOURCE_NOT_ADMISSION"

    @property
    def params(self) -> tuple[Any, ...]:
        """Return fresh driver parameters; no mutable array persists in the sealed plan."""
        values: list[Any] = [list(self.instrument_keys), self.start, self.end]
        if self.after is not None:
            values.extend(self.after)
        values.append(self.limit)
        return tuple(values)

    @property
    def worker_admission_authorized(self) -> bool:
        return False


def plan_price_page(
    family: str,
    *,
    route: str = SOURCE,
    instrument_keys: tuple[int, ...],
    start_utc: str | datetime,
    end_utc: str | datetime,
    source_snapshot_sha256: str,
    after: tuple[int, str | datetime] | None = None,
    limit: int = MAX_PAGE,
) -> PricePagePlan:
    """A finite one-day or shorter fixed-schema indexed-keyset source query.

    The original P01 view is rejected as an independent read because it merely
    joins the same base table against current instrument metadata. The caller
    must independently evidence security lifetime and calendar eligibility.
    Returned August/September timestamps are observed rows only.
    """
    if family not in FAMILY_SOURCE_ROUTES or route not in FAMILY_SOURCE_ROUTES[family]:
        raise ScopeError("P01/P02 route not in the original contract")
    if route != SOURCE:
        raise ScopeError("P01 enriched view is not an independent price source")
    if (not isinstance(instrument_keys, tuple)
            or not 1 <= len(instrument_keys) <= MAX_KEYS
            or any(type(key) is not int or key < 0 for key in instrument_keys)
            or tuple(sorted(set(instrument_keys))) != instrument_keys):
        raise ScopeError("source instruments must be bounded sorted unique identifiers")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise ScopeError("source page limit must be 1-128")
    if not isinstance(source_snapshot_sha256, str) or not _SHA.fullmatch(source_snapshot_sha256):
        raise ScopeError("retained source requires pinned snapshot hash")
    start, end = _utc(start_utc), _utc(end_utc)
    if not (MIN_WINDOW <= start < end <= END_WINDOW) or end - start > timedelta(days=1):
        raise ScopeError("source read outside bounded original target window")
    cursor = None
    if after is not None:
        if (not isinstance(after, tuple) or len(after) != 2
                or type(after[0]) is not int or after[0] < 0):
            raise ScopeError("invalid source keyset cursor")
        cursor = (after[0], _utc(after[1]))
        if cursor[0] not in instrument_keys or not start <= cursor[1] < end:
            raise ScopeError("keyset cursor outside selected source partition")
    where = "instrument_key = ANY(%s) AND bar_ts >= %s AND bar_ts < %s"
    if cursor is not None:
        where += " AND (instrument_key,bar_ts) > (%s,%s)"
    # Never substitute user-supplied SQL identifiers, never include raw payloads.
    query = (
        "SELECT " + ",".join(FIELDS) + " FROM " + SOURCE + " WHERE "
        + where + " ORDER BY instrument_key,bar_ts LIMIT %s"
    )
    return PricePagePlan(family, route, query, instrument_keys,
                         start, end, limit, cursor, source_snapshot_sha256)


@dataclass(frozen=True)
class PricePageEvidence:
    family: str
    source: str
    page_rows: int
    page_sha256: str
    next_cursor: tuple[int, datetime] | None
    labelled_regular: int
    labelled_extended: int
    status: str = "OBSERVED_BARS_NOT_EXPECTED_CALENDAR_OR_PIT"

    @property
    def worker_admission_authorized(self) -> bool:
        return False

    @property
    def coverage_certified(self) -> bool:
        return False


def inspect_price_page(plan: PricePagePlan, rows: Sequence[Mapping[str, Any]]) -> PricePageEvidence:
    """Validate synthetic or genuine source rows without returning licensed values.

    Loaded-at times are ingestion evidence, not historical publication times.
    Gaps, empty pages and a missing September partition remain UNKNOWN coverage.
    An independent source/calendar witness must supply eligible minute units.
    """
    if not isinstance(plan, PricePagePlan) or plan.route != SOURCE:
        raise ScopeError("invalid price source plan")
    if (not isinstance(rows, (tuple, list)) or len(rows) > plan.limit
            or any(not isinstance(row, Mapping) for row in rows)):
        raise ScopeError("price response missing or unbounded")
    last = plan.after
    witnessed = []
    regular = extended = 0
    for row in rows:
        if any(field not in row for field in FIELDS):
            raise ScopeError("price row missing native required source field")
        key = row["instrument_key"]
        timestamp = _utc(row["bar_ts"])
        if type(key) is not int or key not in plan.instrument_keys:
            raise ScopeError("price row outside pinned source instruments")
        if not plan.start <= timestamp < plan.end:
            raise ScopeError("price row outside pinned source date window")
        current = (key, timestamp)
        if last is not None and current <= last:
            raise ScopeError("duplicate or out-of-order source keyset row")
        last = current
        label = row["session_label"]
        if label not in LABELS[plan.family]:
            raise ScopeError("price bar in wrong original session family")
        def positive(field: str) -> float:
            val = row[field]
            if type(val) not in (int, float) or not isfinite(val) or val <= 0:
                raise ScopeError("invalid numeric OHLCV source field")
            return float(val)
        opening, high, low, close = (positive(k) for k in ("open", "high", "low", "close"))
        vwap = positive("vwap")
        if not (low <= min(opening, close, high) and high >= max(opening, close, low)):
            raise ScopeError("invalid source OHLC relationship")
        if (type(row["volume"]) is not int or row["volume"] < 0
                or type(row["trade_count"]) is not int or row["trade_count"] < 0):
            raise ScopeError("invalid source volume or trade count")
        if label == "regular":
            regular += 1
        else:
            extended += 1
        # Hash source content only. Do not put licensed values in repository reports.
        witnessed.append((
            key, timestamp.isoformat(), label, opening, high, low, close,
            row["volume"], row["trade_count"], vwap, str(row["loaded_by_job_id"]),
            str(row["source_loaded_at"]),
        ))
    digest = sha256(canonical({
        "source": plan.route, "snapshot": plan.source_snapshot_sha256,
        "family": plan.family, "bounds": (plan.start.isoformat(), plan.end.isoformat()),
        "instruments": plan.instrument_keys, "after": (
            (plan.after[0], plan.after[1].isoformat()) if plan.after else None
        ), "records": witnessed,
    }).encode("utf-8")).hexdigest()
    return PricePageEvidence(plan.family, SOURCE, len(rows), digest, last, regular, extended)
