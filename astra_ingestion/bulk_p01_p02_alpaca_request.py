"""Fail-closed provider request shape for September P01/P02; never submits.

The original retained P01/P02 sources have no September rows. These immutable
request candidates require independently established historical issuer/listing
identity, contract, calendar and source entitlement. Constructing a plan does
NOT reserve resources or authorize provider submission. The deployed worker
must first enforce a sealed full-family manifest, cumulative request/record/cost
reservations, deadline, stop/fence and per-partition retry policy.

The Alpaca historical-bar connector parameters are exact: 1Min/SIP/raw/USD,
one verified symbol/session per request, explicit asof identity date. The
provider response is not proof of a no-trade state or strict historical PIT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Mapping
from types import MappingProxyType
import re

from .bulk_scope import ScopeError

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TICKER = re.compile(r"[A-Za-z][A-Za-z0-9./^-]{0,15}\Z")
CONTRACTS = {
    "P01": "9eda239c37522ec884e090279220fd701b41f6140bf0a66674b2a3a4798fe387",
    "P02": "ba96c9a04d15e88f0674278dd9ea789d61a7e62cd2e10da754d2c3426655c8bb",
}
SEP_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEP_END = datetime(2026, 10, 1, tzinfo=timezone.utc)
MAX_RECORDS_PER_REQUEST = 1000


def _date_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ScopeError("Alpaca request requires explicit Zulu UTC timestamps")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopeError("Alpaca request timestamp invalid") from exc
    if stamp.utcoffset() != timedelta(0) or stamp.second or stamp.microsecond:
        raise ScopeError("Alpaca session must be minute-aligned exact UTC")
    return stamp


def _sha(value: str) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


@dataclass(frozen=True)
class AlpacaSIPRequestPlan:
    family: str
    instrument_key: int
    symbol: str
    session_day: date
    request: Mapping[str, str | int]
    manifest_sha256: str
    contract_sha256: str
    identity_receipt_sha256: str
    calendar_receipt_sha256: str
    entitlement_receipt_sha256: str
    reserved_request_count: int
    reserved_record_count: int
    original_job_deadline: str
    status: str = "REQUEST_CANDIDATE_NOT_RESERVED_NOT_AUTHORIZED"

    @property
    def provider_submission_authorized(self) -> bool:
        return False

    @property
    def worker_admission_authorized(self) -> bool:
        return False


def plan_september_alpaca_sip(
    family: str,
    *,
    instrument_key: int,
    dated_symbol: str,
    session_day: str,
    session_start_utc: str,
    session_end_utc: str,
    original_job_deadline: str,
    manifest_sha256: str,
    contract_sha256: str,
    identity_receipt_sha256: str,
    calendar_receipt_sha256: str,
    entitlement_receipt_sha256: str,
    reserved_request_count: int,
    reserved_record_count: int,
) -> AlpacaSIPRequestPlan:
    """Construct a request candidate; never use this result as a spend token.

    Actual admission must atomically reserve finite cumulative budgets in the
    deployed ledger, check real entitlement, and confirm independent PIT and
    lifecycle evidence. An arbitrary 64-hex string is not evidence of that.
    """
    if family not in CONTRACTS or contract_sha256 != CONTRACTS[family]:
        raise ScopeError("Alpaca price family/contract not pinned to original source")
    if type(instrument_key) is not int or instrument_key < 0:
        raise ScopeError("invalid historical instrument key")
    if not isinstance(dated_symbol, str) or not _TICKER.fullmatch(dated_symbol):
        raise ScopeError("unverified or unsafe dated Alpaca symbol")
    if not all(map(_sha, (
        manifest_sha256, contract_sha256, identity_receipt_sha256,
        calendar_receipt_sha256, entitlement_receipt_sha256,
    ))):
        raise ScopeError("missing immutable source/contract/calendar/identity/entitlement binding")
    if type(reserved_request_count) is not int or reserved_request_count != 1:
        raise ScopeError("each candidate requires a single finite request reservation")
    if (type(reserved_record_count) is not int
            or not 1 <= reserved_record_count <= MAX_RECORDS_PER_REQUEST):
        raise ScopeError("record reservation exceeds finite single-partition budget")
    try:
        day = date.fromisoformat(session_day)
    except (TypeError, ValueError) as exc:
        raise ScopeError("historical symbol date invalid") from exc
    start, end = _date_utc(session_start_utc), _date_utc(session_end_utc)
    deadline = _date_utc(original_job_deadline)
    if (not SEP_START <= start < end <= SEP_END
            or end - start > timedelta(days=1)
            or day != start.date()):
        raise ScopeError("session window is outside September or calendar day")
    if deadline <= end:
        raise ScopeError("new finite job deadline must follow its source window")
    # Must be separately checked at runtime; this is not a synthetic lease.
    # The connector's end may be inclusive: a response must be filtered
    # against [start,end) and independently checked against calendar minutes.
    request = {
        "symbols": dated_symbol,
        "timeframe": "1Min",
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
        "limit": reserved_record_count,
        "adjustment": "raw",
        "feed": "sip",
        "currency": "USD",
        "sort": "asc",
        "asof": day.isoformat(),
    }
    return AlpacaSIPRequestPlan(
        family, instrument_key, dated_symbol, day, MappingProxyType(request),
        manifest_sha256, contract_sha256, identity_receipt_sha256,
        calendar_receipt_sha256, entitlement_receipt_sha256,
        reserved_request_count, reserved_record_count,
        original_job_deadline,
    )
