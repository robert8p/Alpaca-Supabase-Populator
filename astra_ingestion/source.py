"""Bounded Alpaca request and strict, lossless normalization of source receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import socket
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import IngestionSpec, TIMEFRAMES, canonical_timestamp, parse_timestamp

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"


class SourceError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False, retry_after: float = 0):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class FetchResult:
    raw_text: str
    request_id: str | None


@dataclass(frozen=True)
class ParsedPage:
    records: tuple[dict[str, str], ...]
    next_page_token: str | None
    response_sha256: str


def record_key(record: dict[str, Any]) -> str:
    if not isinstance(record.get("symbol"), str) or not isinstance(record.get("timestamp"), str):
        raise ValueError("Record is missing its symbol or timestamp key")
    return record["symbol"] + "|" + record["timestamp"]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON object key")
        value[key] = item
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("Non-finite JSON number")


def _number(value: Any, field: str, *, positive: bool = False, integer: bool = False) -> tuple[Decimal, str]:
    if type(value) is not int and not isinstance(value, Decimal):
        raise ValueError(f"{field} must be a JSON number")
    number = Decimal(value)
    if not number.is_finite() or (number <= 0 if positive else number < 0):
        raise ValueError(f"{field} must be finite and {'positive' if positive else 'nonnegative'}")
    if number and (abs(number.adjusted()) > 30 or len(number.as_tuple().digits) > 40):
        raise ValueError(f"{field} exceeds the supported numeric precision")
    if integer and (number != number.to_integral_value() or number > 2**63 - 1):
        raise ValueError(f"{field} must be a nonnegative 64-bit integer")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return number, "0" if number == 0 else text


def parse_page(raw_text: str, *, symbol: str, start: datetime | str, end: datetime | str, timeframe: str) -> ParsedPage:
    """Normalize all returned rows; no row or symbol is silently discarded."""
    try:
        if not isinstance(raw_text, str) or len(raw_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("Response exceeds the two MiB receipt limit")
        if timeframe not in TIMEFRAMES:
            raise ValueError("Unsupported timeframe")
        beginning, ending = parse_timestamp(start), parse_timestamp(end)
        if beginning >= ending:
            raise ValueError("Partition has an invalid interval")
        body = json.loads(raw_text, parse_float=Decimal, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        if not isinstance(body, dict) or not isinstance(body.get("bars"), dict):
            raise ValueError("Response must contain a bars object")
        if any(key != symbol for key in body["bars"]):
            raise ValueError("Response contains an out-of-scope symbol")
        rows = body["bars"].get(symbol, [])
        if not isinstance(rows, list) or len(rows) > 1_000:
            raise ValueError("Response bars must be a list of at most 1000 rows")
        token = body.get("next_page_token")
        if token is not None and (not isinstance(token, str) or not 1 <= len(token) <= 4096):
            raise ValueError("Invalid next_page_token")
        records: dict[str, dict[str, str]] = {}
        for row in rows:
            if not isinstance(row, dict) or not {"t", "o", "h", "l", "c", "v", "n", "vw"} <= set(row):
                raise ValueError("Bar is missing a required field")
            instant = parse_timestamp(row["t"])
            if not beginning <= instant < ending:
                raise ValueError("Bar timestamp lies outside its admitted interval")
            values: dict[str, str] = {"symbol": symbol, "timestamp": canonical_timestamp(instant)}
            numbers: dict[str, Decimal] = {}
            for short, name in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume"), ("n", "trade_count"), ("vw", "vwap")):
                number, text = _number(row[short], name, positive=short in {"o", "h", "l", "c", "vw"}, integer=short == "n")
                numbers[short], values[name] = number, text
            if not numbers["l"] <= numbers["o"] <= numbers["h"] or not numbers["l"] <= numbers["c"] <= numbers["h"]:
                raise ValueError("Bar violates OHLC price ordering")
            key = record_key(values)
            if key in records and records[key] != values:
                raise ValueError("Source contains conflicting duplicate bars")
            records[key] = values
        return ParsedPage(tuple(records[key] for key in sorted(records)), token, hashlib.sha256(raw_text.encode("utf-8")).hexdigest())
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise SourceError("invalid_source", str(exc)) from exc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward provider authentication to a redirect destination.
        return None


def _retry_delay(headers: Any, status: int) -> float:
    minimum = 60 if status == 429 else 2
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return float(minimum)
    try:
        delay = float(raw)
        if not math.isfinite(delay):
            return float(minimum)
    except (ValueError, TypeError):
        try:
            due = parsedate_to_datetime(raw)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            delay = (due - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return float(minimum)
    return float(max(minimum, math.ceil(delay)))


class AlpacaSource:
    def __init__(self, api_key: str, secret_key: str, opener: Callable[..., Any] | Any | None = None):
        for value in (api_key, secret_key):
            if not isinstance(value, str) or not value or any(ord(c) < 33 or ord(c) > 126 for c in value):
                raise ValueError("Provider credentials are missing or invalid")
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key, "Accept": "application/json"}
        self._open = build_opener(_NoRedirect()).open if opener is None else (opener.open if hasattr(opener, "open") else opener)

    def fetch_page(self, spec: IngestionSpec, partition: dict[str, Any], page_token: str | None = None) -> FetchResult:
        symbol = partition.get("symbol")
        start, end = parse_timestamp(partition.get("start")), parse_timestamp(partition.get("end"))
        if symbol not in spec.symbols or not spec.start <= start < end <= spec.end or end - start > timedelta(days=1):
            raise SourceError("invalid_scope", "Partition does not belong to the admitted scope")
        if page_token is not None and (not isinstance(page_token, str) or not 1 <= len(page_token) <= 4096):
            raise SourceError("invalid_scope", "Invalid pagination token")
        params = {"symbols": symbol, "timeframe": spec.timeframe, "start": canonical_timestamp(start),
                  "end": canonical_timestamp(end - timedelta(microseconds=1)), "feed": spec.feed,
                  "adjustment": spec.adjustment, "limit": 1000, "sort": "asc"}
        if page_token is not None:
            params["page_token"] = page_token
        request = Request(ENDPOINT + "?" + urlencode(params), headers=self._headers, method="GET")
        try:
            with self._open(request, timeout=20) as response:
                if getattr(response, "status", 200) != 200:
                    status = int(response.status)
                    raise SourceError("provider_http", f"Provider returned HTTP {status}", status == 429 or 500 <= status < 600, _retry_delay(response.headers, status))
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError("response_too_large", "Provider response exceeds the two MiB receipt limit")
                try:
                    raw_text = content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SourceError("invalid_source", "Provider response is not valid UTF-8") from exc
                request_id = response.headers.get("x-request-id")
                return FetchResult(raw_text, str(request_id)[:256] if request_id else None)
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            raise SourceError("provider_http", f"Provider returned HTTP {exc.code}", retryable, _retry_delay(exc.headers, exc.code) if retryable else 0) from exc
        except (URLError, TimeoutError, socket.timeout, OSError) as exc:
            # The original exception can include URL and environment details.
            raise SourceError("provider_transport", "Provider request failed or timed out", True, 2) from exc
