"""Provider-free REF01 cohort-to-Alpaca ticker candidate reconciliation.

Only the accepted 3,000-company capture and the ORIGINAL REF01-declared
Alpaca fixed-window instrument source may be read. A ticker match is neither
a date-valid security/listing episode nor identity/PIT verification. No
provider calls, raw payloads, acceptance, acquisition or production mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import re
from typing import Any, Mapping, Sequence

from .bulk_ref01_route_probe import SPECS
from .bulk_scope import CAPTURE_KEY, ScopeError, canonical

_SOURCE = "reference.alpaca_fixed_window_instruments_v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_TICKER = re.compile(r"[A-Z][A-Z0-9./^-]{0,15}\Z")
_MAX = 128
if _SOURCE not in SPECS:
    raise RuntimeError("original REF01 source route is not pinned")


@dataclass(frozen=True)
class Ref01TickerPage:
    sql: str
    params: tuple[object, ...]
    snapshot_sha256: str
    after_company_key: str | None
    page_limit: int
    status: str = "READ_ONLY_CANDIDATE_QUERY_NOT_IDENTITY_CERTIFICATION"


@dataclass(frozen=True)
class Ref01TickerCandidate:
    company_key: str
    accepted_company_receipt_sha256: str
    ticker: str
    matching_source_rows: int
    instrument_key: int | None
    alpaca_asset_id: str | None
    classification_observed_at: str | None
    evidence_sha256: str
    status: str = "SOURCE_CANDIDATE_HISTORICAL_LIFECYCLE_UNVERIFIED"

    @property
    def identity_certified(self) -> bool:
        return False


@dataclass(frozen=True)
class Ref01TickerPageEvidence:
    page_sha256: str
    snapshot_sha256: str
    source_rows: int
    exact_one_match: int
    unmatched: int
    ambiguous: int
    next_company_key: str | None
    candidates: tuple[Ref01TickerCandidate, ...]
    status: str = "SOURCE_MATCH_COUNTS_NOT_COMPLETE_REF01_UNIVERSE"

    @property
    def coverage_certified(self) -> bool:
        return False

    @property
    def worker_admission_authorized(self) -> bool:
        return False


def plan_ticker_projection(
    source_snapshot_sha256: str, *, after_company_key: str | None = None,
    page_limit: int = 128,
) -> Ref01TickerPage:
    """A page has exactly one row per retained company, including missing ones.

    The lateral aggregate prevents a nonunique source ticker from silently
    being selected or skipped by company-key pagination. A snapshot ID is an
    externally supplied binding, NOT proof a transaction is snapshot-isolated.
    """
    if not isinstance(source_snapshot_sha256, str) or not _SHA.fullmatch(source_snapshot_sha256):
        raise ScopeError("REF01 ticker projection requires pinned original source snapshot")
    if after_company_key is not None and (
            not isinstance(after_company_key, str)
            or not _KEY.fullmatch(after_company_key)):
        raise ScopeError("REF01 invalid accepted company cursor")
    if type(page_limit) is not int or not 1 <= page_limit <= _MAX:
        raise ScopeError("REF01 ticker source pages must contain at most 128 companies")
    query = """WITH company_page AS (
 SELECT evidence_key,source_sha256,source_text
 FROM astra_ingestion_v1.bulk_scope_evidence_v1
 WHERE capture_key=%s AND kind='company'
 AND (%s::text IS NULL OR evidence_key>%s::text)
 ORDER BY evidence_key LIMIT %s
)
SELECT c.evidence_key AS company_key,
 c.source_sha256 AS accepted_company_receipt_sha256,
 c.source_text::jsonb->>'anchor_ticker' AS ticker,
 matches.match_count AS matching_source_rows,
 matches.instrument_key, matches.alpaca_asset_id, matches.classification_observed_at
FROM company_page c
CROSS JOIN LATERAL (
 SELECT count(*)::integer AS match_count,
 CASE WHEN count(*)=1 THEN max(i.instrument_key) ELSE NULL END AS instrument_key,
 CASE WHEN count(*)=1 THEN max(i.alpaca_asset_id::text) ELSE NULL END AS alpaca_asset_id,
 CASE WHEN count(*)=1 THEN max(i.classification_observed_at) ELSE NULL END AS classification_observed_at
 FROM reference.alpaca_fixed_window_instruments_v1 i
 WHERE i.symbol=c.source_text::jsonb->>'anchor_ticker'
) matches ORDER BY c.evidence_key"""
    return Ref01TickerPage(
        query, (CAPTURE_KEY, after_company_key, after_company_key, page_limit),
        source_snapshot_sha256, after_company_key, page_limit,
    )


def inspect_ticker_projection_page(
    plan: Ref01TickerPage, rows: Sequence[Mapping[str, Any]],
) -> Ref01TickerPageEvidence:
    """Bound source observations; never use current status as historical PIT."""
    if not isinstance(plan, Ref01TickerPage) or not _SHA.fullmatch(plan.snapshot_sha256):
        raise ScopeError("REF01 exact source page query plan required")
    if not isinstance(rows, (tuple, list)) or len(rows) > plan.page_limit:
        raise ScopeError("unbounded REF01 ticker page")
    seen = plan.after_company_key
    candidates = []
    counts = [0, 0, 0]
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "company_key", "accepted_company_receipt_sha256", "ticker",
            "matching_source_rows", "instrument_key", "alpaca_asset_id",
            "classification_observed_at",
        }:
            raise ScopeError("REF01 missing or additional source projection fields")
        key = row["company_key"]
        ticker = row["ticker"]
        src = row["accepted_company_receipt_sha256"]
        n = row["matching_source_rows"]
        if (not isinstance(key, str) or not _KEY.fullmatch(key)
                or seen is not None and key <= seen
                or not isinstance(ticker, str) or not _TICKER.fullmatch(ticker)
                or not isinstance(src, str) or not _SHA.fullmatch(src)
                or type(n) is not int or not 0 <= n <= 1_000_000):
            raise ScopeError("REF01 source company/alias invalid or nonadvancing")
        seen = key
        instrument = row["instrument_key"]
        asset = row["alpaca_asset_id"]
        observed = row["classification_observed_at"]
        if n != 1:
            if instrument is not None or asset is not None or observed is not None:
                raise ScopeError("ambiguous or unmatched source cannot provide a selected security")
        else:
            if type(instrument) is not int or instrument < 0:
                raise ScopeError("single ticker source match lacks stable instrument key")
            if asset is not None and (
                    not isinstance(asset, str) or len(asset) > 128):
                raise ScopeError("REF01 malformed native asset id")
            if isinstance(observed, datetime):
                if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
                    raise ScopeError("REF01 source observation timestamp is not UTC")
                observed = observed.isoformat()
            elif observed is not None:
                raise ScopeError("REF01 source timestamp must be database datetime")
        counts[0 if n == 1 else (1 if n == 0 else 2)] += 1
        footprint = {
            "company": key, "company_receipt": src, "ticker": ticker,
            "matching_source_rows": n, "instrument_key": instrument,
            "asset_id": asset, "classification_observed_at": observed,
            "snapshot": plan.snapshot_sha256,
        }
        candidates.append(Ref01TickerCandidate(
            key, src, ticker, n, instrument, asset, observed,
            sha256(canonical(footprint).encode("utf-8")).hexdigest(),
        ))
    page_digest = sha256(canonical({
        "source": _SOURCE, "snapshot": plan.snapshot_sha256,
        "after": plan.after_company_key,
        "candidate_sha256": [c.evidence_sha256 for c in candidates],
    }).encode("utf-8")).hexdigest()
    return Ref01TickerPageEvidence(
        page_digest, plan.snapshot_sha256, len(rows), *counts, seen,
        tuple(candidates),
    )
