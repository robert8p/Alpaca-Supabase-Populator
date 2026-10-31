"""Bounded, immutable P01/P02 September Alpaca 1Min/SIP/raw response witness.

Never calls a provider, submits a continuation, writes production rows, consumes
a budget or certifies historical PIT, security eligibility or completeness.
The response is untrusted until an independently authenticated runtime verifies
provider transport, an atomic cumulative reservation and original job deadline.
No observed bars or empty page can stand in for the eligible-minute calendar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Mapping
import re

from .bulk_p01_p02_alpaca_request import (
    AlpacaSIPRequestPlan, plan_september_alpaca_sip,
)
from .bulk_scope import ScopeError, canonical

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_.~+/=-]{1,1024}\Z")
_REQUIRED_BAR_FIELDS = frozenset(("t", "o", "h", "l", "c", "v", "n", "vw"))
_MAX_BARS = 1000


@dataclass(frozen=True)
class ObservedSIPBar:
    timestamp_utc: str
    open: str
    high: str
    low: str
    close: str
    volume: int
    trade_count: int
    vwap: str
    record_sha256: str


@dataclass(frozen=True)
class SIPResponseWitness:
    family: str
    symbol: str
    instrument_key: int
    manifest_sha256: str
    contract_sha256: str
    page_no: int
    prior_page_sha256: str | None
    page_sha256: str
    bars: tuple[ObservedSIPBar, ...]
    next_page_token: str | None
    continuation_required: bool
    excluded_end_bar_count: int
    excluded_end_bar_sha256: str | None
    status: str = "OBSERVED_UNTRUSTED_NOT_COMMITTED_NOT_CALENDAR_COMPLETE"

    @property
    def worker_admission_authorized(self) -> bool:
        return False

    @property
    def coverage_certified(self) -> bool:
        return False

    @property
    def provider_submission_authorized(self) -> bool:
        return False


def _minute(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ScopeError("provider timestamp must use explicit Z UTC")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopeError("provider timestamp invalid") from exc
    if (stamp.tzinfo is None or stamp.utcoffset() != timedelta(0)
            or stamp.second != 0 or stamp.microsecond != 0):
        raise ScopeError("provider bar timestamp must be an exact UTC minute")
    return stamp.astimezone(timezone.utc)


def _price(value: Any) -> str:
    if type(value) not in (int, float, Decimal):
        raise ScopeError("provider price must be a finite numeric value")
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ScopeError("provider price invalid") from exc
    if not d.is_finite() or d <= 0 or d > Decimal("1000000000000"):
        raise ScopeError("provider price invalid or outside bounded range")
    if abs(d.as_tuple().exponent) > 18 or len(d.as_tuple().digits) > 25:
        raise ScopeError("provider numeric precision outside bounded range")
    return format(d.normalize(), "f")


def _count(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= (2**63 - 1):
        raise ScopeError("provider volume/trade count invalid")
    return value


def _original_plan(plan: Any) -> AlpacaSIPRequestPlan:
    if not isinstance(plan, AlpacaSIPRequestPlan):
        raise ScopeError("verified original September request candidate required")
    try:
        req = dict(plan.request)
        checked = plan_september_alpaca_sip(
            plan.family, instrument_key=plan.instrument_key,
            dated_symbol=plan.symbol, session_day=plan.session_day.isoformat(),
            session_start_utc=req["start"], session_end_utc=req["end"],
            original_job_deadline=plan.original_job_deadline,
            manifest_sha256=plan.manifest_sha256,
            contract_sha256=plan.contract_sha256,
            identity_receipt_sha256=plan.identity_receipt_sha256,
            calendar_receipt_sha256=plan.calendar_receipt_sha256,
            entitlement_receipt_sha256=plan.entitlement_receipt_sha256,
            reserved_request_count=plan.reserved_request_count,
            reserved_record_count=plan.reserved_record_count,
        )
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise ScopeError("malformed candidate provider request") from exc
    if (req != dict(checked.request) or plan.status != checked.status
            or plan.provider_submission_authorized or plan.worker_admission_authorized):
        raise ScopeError("request parameters or candidate authority changed after validation")
    return checked


def inspect_sip_response(
    plan: AlpacaSIPRequestPlan,
    response: Mapping[str, Any],
    *,
    page_no: int = 0,
    prior_page_sha256: str | None = None,
    prior_bar_timestamp_utc: str | None = None,
) -> SIPResponseWitness:
    """Prepare source-observation hashes only; never issue a provider request.

    Continuation requires a NEW separately authorised request reservation.
    A nonnull token or empty page does not mean that the expected eligible
    calendar has been populated. Even a terminal page is NOT data acceptance.
    """
    checked = _original_plan(plan)
    if (type(page_no) is not int or not 0 <= page_no <= 1024
            or (page_no == 0) != (prior_page_sha256 is None)
            or (page_no == 0) != (prior_bar_timestamp_utc is None)):
        raise ScopeError("invalid finite page chain")
    if page_no > 0 and (not isinstance(prior_page_sha256, str)
                        or not _SHA.fullmatch(prior_page_sha256)):
        raise ScopeError("prior source page must have an immutable receipt")
    prior_stamp = _minute(prior_bar_timestamp_utc) if prior_bar_timestamp_utc else None
    if not isinstance(response, Mapping):
        raise ScopeError("provider response is not a JSON object")
    if set(response) - {"bars", "next_page_token", "currency"}:
        raise ScopeError("unexpected provider response keys")
    if "bars" not in response or "next_page_token" not in response:
        raise ScopeError("provider response lacks bars or pagination state")
    if "currency" in response and response["currency"] != "USD":
        raise ScopeError("provider currency does not match the USD contract")
    token = response["next_page_token"]
    if token is not None and (not isinstance(token, str)
                              or not _TOKEN.fullmatch(token)):
        raise ScopeError("invalid or unbounded provider continuation token")
    bars = response["bars"]
    if (not isinstance(bars, Mapping) or
            set(bars) - {checked.symbol}):
        raise ScopeError("provider returned an unrequested security")
    native = bars.get(checked.symbol, [])
    if (not isinstance(native, list) or len(native) > _MAX_BARS
            or len(native) > checked.reserved_record_count):
        raise ScopeError("response exceeds finite record reservation")
    start = _minute(checked.request["start"])
    end = _minute(checked.request["end"])
    if prior_stamp is not None and not start <= prior_stamp < end:
        raise ScopeError("previous page cursor outside original session")
    last = prior_stamp
    observed: list[ObservedSIPBar] = []
    excluded_end: list[str] = []
    for raw in native:
        if not isinstance(raw, Mapping) or set(raw) != _REQUIRED_BAR_FIELDS:
            raise ScopeError("source bar missing or introducing unqualified fields")
        stamp = _minute(raw["t"])
        # Alpaca documents an inclusive provider `end`; the original
        # independently eligible minute calendar remains [start, end).
        # Validate/fingerprint exactly the end boundary but never credit it.
        if not start <= stamp <= end:
            raise ScopeError("source bar outside bounded provider session")
        if last is not None and stamp <= last:
            raise ScopeError("duplicate, reordered or replayed source minute")
        last = stamp
        opening, high, low, closing, vwap = (
            Decimal(_price(raw[field])) for field in ("o", "h", "l", "c", "vw")
        )
        if not (low <= opening <= high and low <= closing <= high
                and low <= vwap <= high):
            raise ScopeError("provider OHLC/VWAP price relationship invalid")
        volume, trade_count = _count(raw["v"]), _count(raw["n"])
        values = {
            "instrument_key": checked.instrument_key, "symbol": checked.symbol,
            "family": checked.family, "timestamp": stamp.isoformat(),
            "o": format(opening, "f"), "h": format(high, "f"),
            "l": format(low, "f"), "c": format(closing, "f"),
            "v": volume, "n": trade_count, "vw": format(vwap, "f"),
        }
        row_sha = sha256(canonical(values).encode("utf-8")).hexdigest()
        if stamp == end:
            excluded_end.append(row_sha)
            continue
        observed.append(ObservedSIPBar(
            stamp.isoformat().replace("+00:00", "Z"),
            values["o"], values["h"], values["l"], values["c"],
            volume, trade_count, values["vw"], row_sha,
        ))
    # Bind to the complete request and inherited source identity/calendar
    # evidence; no record values or continuation token go into public reports.
    fingerprint = {
        "manifest": checked.manifest_sha256,
        "contract": checked.contract_sha256,
        "identity": checked.identity_receipt_sha256,
        "calendar": checked.calendar_receipt_sha256,
        "entitlement": checked.entitlement_receipt_sha256,
        "instrument_key": checked.instrument_key, "request": dict(checked.request),
        "page_no": page_no, "prior_page_sha256": prior_page_sha256,
        "prior_bar_timestamp_utc": prior_bar_timestamp_utc,
        "record_sha256": [bar.record_sha256 for bar in observed],
        "provider_inclusive_end_excluded_sha256": excluded_end,
        "continuation_token_sha256": (
            sha256(token.encode("ascii")).hexdigest() if token else None
        ),
    }
    return SIPResponseWitness(
        checked.family, checked.symbol, checked.instrument_key,
        checked.manifest_sha256, checked.contract_sha256, page_no,
        prior_page_sha256,
        sha256(canonical(fingerprint).encode("utf-8")).hexdigest(),
        tuple(observed), token, token is not None,
        len(excluded_end), excluded_end[0] if excluded_end else None,
    )
