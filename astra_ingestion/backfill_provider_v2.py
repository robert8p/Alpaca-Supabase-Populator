"""Fixed-cohort acquisition adapters. No runtime imports start provider work.

The authenticated durable queue supplies each immutable task. A request must be
reserved immediately before this client is called. Original responses are kept
even if identity or field validation prevents analytical use. Provider absence
is never inferred from an HTTP error or an unfinished page chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import json
import math
import re
import ssl
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

VERSION = "fixed3000-provider-v2.2"
MAX_BODY_BYTES = 3 * 1024 * 1024
MAX_PARTIAL_BODY_BYTES = 16 * 1024
REQUEST_TIMEOUT_SECONDS = 25
NY = ZoneInfo("America/New_York")
SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,63}\Z")
KINDS = (
    "alpaca_reference", "alpaca_stock_bars", "alpaca_news", "alpaca_actions",
    "alpaca_option_contracts", "alpaca_option_bars", "massive_reference",
    "massive_news", "massive_dividends", "massive_splits", "massive_short_volume",
    "massive_short_interest",
)

PAGE_LIMIT_CAPS = {
    "alpaca_stock_bars": 10000, "alpaca_option_bars": 10000,
    "alpaca_option_contracts": 1000, "alpaca_actions": 1000,
    "alpaca_news": 50, "massive_news": 1000, "massive_dividends": 1000,
    "massive_splits": 1000, "massive_short_volume": 1000,
    "massive_short_interest": 1000,
}


def _page_limit(task):
    cap = PAGE_LIMIT_CAPS.get(task.get("kind"))
    if cap is None:
        return None
    value = task.get("page_limit")
    if value is None:
        return cap
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProviderProblem("INVALID_EXECUTION_LIMIT", "Durable source page limit must be a positive integer")
    return min(value, cap)


def _retry_delay(headers):
    value = headers.get("Retry-After", "30")
    try:
        return max(1, int(value))
    except ValueError:
        try:
            due = parsedate_to_datetime(value)
            return max(1, math.ceil((due - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return 30


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProviderProblem(Exception):
    def __init__(self, code, message, *, retryable=False, retry_after=0, evidence=None):
        super().__init__(message)
        self.code, self.retryable, self.retry_after = code, retryable, retry_after
        self.evidence = evidence or {}


@dataclass(frozen=True)
class ProviderPage:
    raw_body: str = field(repr=False)
    body_sha256: str
    http_status: int
    request_id: str | None
    fetched_at: str
    request: dict = field(repr=False)
    records: tuple = field(repr=False)
    next_cursor: str | None = field(repr=False)
    quality: tuple = ()
    headers: dict = field(default_factory=dict)

    def payload(self):
        return {"raw_body": self.raw_body, "body_sha256": self.body_sha256,
                "http_status": self.http_status, "request_id": self.request_id,
                "fetched_at": self.fetched_at, "request": self.request,
                "records": list(self.records), "next_cursor": self.next_cursor,
                "quality": list(self.quality), "headers": self.headers,
                "adapter_version": VERSION}


def _symbols(scope):
    values = scope.get("symbols") or ([scope["symbol"]] if scope.get("symbol") else [])
    if not isinstance(values, list) or not values or len(values) > 100:
        raise ProviderProblem("INVALID_TASK_SCOPE", "Task requires one to 100 provider anchors")
    if len(set(values)) != len(values) or any(not isinstance(s, str) or not SYMBOL.fullmatch(s) for s in values):
        raise ProviderProblem("INVALID_TASK_SCOPE", "Invalid or repeated provider symbol")
    return values


def _bounded_date(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ProviderProblem("INVALID_TASK_SCOPE", "An explicit bounded date is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ProviderProblem("INVALID_TASK_SCOPE", "Invalid date bound") from None
    if not 1900 <= parsed.year <= 2100:
        raise ProviderProblem("INVALID_TASK_SCOPE", "Date outside supported source range")
    return value


def request_for(task, *, paper=True):
    """Only fixed read-only endpoints; never accepts an arbitrary provider URL."""
    kind, scope = task.get("kind"), task.get("scope", {})
    if kind not in KINDS:
        raise ProviderProblem("UNIMPLEMENTED_ADAPTER", "No executable acquisition adapter for task kind")
    symbols = _symbols(scope)
    cursor = task.get("cursor", task.get("next_cursor"))
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 8192 or any(ord(c) < 32 for c in cursor)):
        raise ProviderProblem("INVALID_CURSOR", "Invalid durable continuation")
    host, params = "data.alpaca.markets", {}
    if kind == "alpaca_stock_bars":
        path = "/v2/stocks/bars"
        tf, adjustment = scope.get("timeframe", "1Min"), scope.get("adjustment", "raw")
        if tf not in ("1Min", "1Day") or adjustment not in ("raw", "split", "all"):
            raise ProviderProblem("INVALID_TASK_SCOPE", "Unsupported bar basis")
        params = {"symbols": ",".join(symbols), "timeframe": tf,
                  "start": _bounded_date(scope["start"]), "end": _bounded_date(scope["end"]),
                  "adjustment": adjustment, "feed": "sip", "sort": "asc", "limit": 10000,
                  "asof": scope.get("asof", "2026-08-03"), "currency": "USD"}
    elif kind == "alpaca_option_bars":
        path = "/v1beta1/options/bars"
        params = {"symbols": ",".join(symbols), "timeframe": "1Day",
                  "start": _bounded_date(scope["start"]), "end": _bounded_date(scope["end"]),
                  "limit": 10000, "sort": "asc"}
    elif kind == "alpaca_option_contracts":
        host = "paper-api.alpaca.markets" if paper else "api.alpaca.markets"
        path = "/v2/options/contracts"
        status = scope.get("status")
        if status not in ("active", "inactive"):
            raise ProviderProblem("INVALID_TASK_SCOPE", "Historical enumeration requires an explicit contract status")
        # Override the provider's default upcoming-weekend upper bound. Contracts
        # expiring after the target window may still have traded within it.
        params = {"underlying_symbols": ",".join(symbols), "status": status,
                  "expiration_date_gte": _bounded_date(scope.get("expiration_start", "2025-09-01")),
                  "expiration_date_lte": _bounded_date(scope.get("expiration_end", "2099-12-31")),
                  "show_deliverables": "true", "limit": 1000}
    elif kind == "alpaca_reference":
        if len(symbols) != 1:
            raise ProviderProblem("INVALID_TASK_SCOPE", "Asset lookup requires a single anchor")
        host = "paper-api.alpaca.markets" if paper else "api.alpaca.markets"
        path = "/v2/assets/" + quote(symbols[0], safe="")
    elif kind == "alpaca_news":
        path = "/v1beta1/news"
        params = {"symbols": ",".join(symbols), "start": _bounded_date(scope["start"]),
                  "end": _bounded_date(scope["end"]), "limit": 50, "sort": "asc",
                  "include_content": "true", "exclude_contentless": "false"}
    elif kind == "alpaca_actions":
        path = "/v1/corporate-actions"
        params = {"symbols": ",".join(symbols), "start": _bounded_date(scope["start"]),
                  "end": _bounded_date(scope["end"]), "limit": 1000, "sort": "asc",
                  "region": "all"}
    else:
        host = "api.massive.com"
        ticker = symbols[0]
        if kind == "massive_reference":
            if len(symbols) != 1:
                raise ProviderProblem("INVALID_TASK_SCOPE", "Historical reference lookup requires a single anchor")
            path = "/v3/reference/tickers/" + quote(ticker, safe="")
            params = {"date": _bounded_date(scope["asof"])}
        elif kind == "massive_news":
            if len(symbols) != 1:
                raise ProviderProblem("INVALID_TASK_SCOPE", "News archive lookup requires a single provider anchor")
            path = "/v2/reference/news"
            params = {"ticker": ticker, "published_utc.gte": _bounded_date(scope["start"]),
                      "published_utc.lte": _bounded_date(scope["end"]), "limit": 1000,
                      "sort": "published_utc", "order": "asc"}
        elif kind in ("massive_dividends", "massive_splits"):
            path = "/stocks/v1/" + ("dividends" if kind.endswith("dividends") else "splits")
            params = {"ticker.any_of": ",".join(symbols), "limit": 1000, "sort": "ticker.asc"}
            # No ex-date-only filter: declaration/ex/record/payment can cross
            # the target boundary. Original events remain source observations.
        elif kind == "massive_short_volume":
            path = "/stocks/v1/short-volume"
            params = {"ticker.any_of": ",".join(symbols), "date.gte": _bounded_date(scope["start"]),
                      "date.lte": _bounded_date(scope["end"]), "limit": 1000, "sort": "ticker.asc"}
        else:
            path = "/stocks/v1/short-interest"
            params = {"ticker.any_of": ",".join(symbols), "settlement_date.gte": _bounded_date(scope["start"]),
                      "settlement_date.lte": _bounded_date(scope["end"]), "limit": 1000, "sort": "ticker.asc"}
    if cursor:
        params["cursor" if kind.startswith("massive_") else "page_token"] = cursor
    limit = _page_limit(task)
    if limit is not None:
        params["limit"] = limit
    return {"provider": "Massive" if kind.startswith("massive_") else "Alpaca",
            "host": host, "path": path, "params": params, "method": "GET"}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _parse(raw):
    def invalid(_):
        raise ValueError("non-finite JSON")
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=invalid)


def _stamp(value):
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            raise ValueError("naive")
        return d
    except (ValueError, TypeError, AttributeError):
        return None


def _bar(row, symbol, scope, *, option=False):
    problems = []
    ts = _stamp(row.get("t"))
    if ts is None:
        problems.append("INVALID_OR_MISSING_TIMESTAMP")
    for key in ("o", "h", "l", "c", "v"):
        v = row.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            problems.append("INVALID_OR_MISSING_" + key.upper())
    if not problems and (row["h"] < max(row["o"], row["c"], row["l"]) or row["l"] > min(row["o"], row["c"], row["h"])):
        problems.append("INVALID_OHLC_RELATION")
    local = ts.astimezone(NY) if ts else None
    day = local.date().isoformat() if local else None
    session = "DAILY" if option or scope.get("timeframe") == "1Day" else "UNKNOWN"
    if session == "UNKNOWN" and local:
        calendar = {r["date"]: r for r in scope.get("calendar", [])}
        entry = calendar.get(day)
        if entry:
            minute = local.strftime("%H:%M")
            op, cl = entry["open"][:5], entry["close"][:5]
            session = ("PRE" if "04:00" <= minute < op else "RTH" if op <= minute < cl
                       else "POST" if cl <= minute < "20:00" else "OUTSIDE_SUPPORTED_SESSION")
        else:
            problems.append("SESSION_CALENDAR_MISSING")
    if ts:
        start, end = _stamp(scope.get("start")), _stamp(scope.get("end"))
        if start and end and not start <= ts <= end:
            problems.append("SOURCE_TIMESTAMP_OUTSIDE_QUERY")
    basis = scope.get("adjustment", "raw") if not option else "PROVIDER_OPTION_CONTRACT"
    return {"symbol": symbol, "timestamp": row.get("t"), "market_date": day,
            "session": session, "timeframe": "1Day" if option else scope.get("timeframe", "1Min"),
            "adjustment": basis, "feed": "opra" if option else "sip", "source": row,
            "missing_fields": [k for k in ("n", "vw") if row.get(k) is None],
            "quality_reasons": problems, "support_history": bool(day and day < "2025-09-01"),
            "identity_status": scope.get("identity_status", "UNRESOLVED_PROVIDER_ANCHOR")}


def parse_response(task, request, raw):
    body = _parse(raw)
    kind, scope = task["kind"], task["scope"]
    if not isinstance(body, dict):
        raise ValueError("provider response is not an object")
    records, quality = [], []
    if kind in ("alpaca_stock_bars", "alpaca_option_bars"):
        if "bars" not in body or "next_page_token" not in body or not isinstance(body["bars"], (dict, type(None))):
            raise ValueError("source bar or pagination envelope missing")
        allowed = set(_symbols(scope))
        for symbol, rows in (body["bars"] or {}).items():
            if not isinstance(rows, list):
                raise ValueError("invalid source bar collection")
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("invalid source bar record")
                record = _bar(row, symbol, scope, option=kind == "alpaca_option_bars")
                if symbol not in allowed:
                    record["quality_reasons"].append("UNREQUESTED_PROVIDER_SYMBOL")
                records.append(record)
    elif kind == "alpaca_reference":
        if "id" not in body or "symbol" not in body:
            raise ValueError("asset reference envelope missing")
        records = [{"symbol": body["symbol"], "source": body,
                    "reference_asof_policy": "CURRENT_RETRIEVAL_NOT_HISTORICAL_PROOF"}]
    elif kind == "alpaca_option_contracts":
        if "option_contracts" not in body or "next_page_token" not in body:
            raise ValueError("contract enumeration envelope missing")
        for row in body["option_contracts"] or []:
            records.append({"symbol": row.get("symbol"), "source": row,
                            "underlying_symbol": row.get("underlying_symbol"),
                            "enumeration_status": scope["status"],
                            "historical_listing_completeness": "UNKNOWN_PROVIDER_REFERENCE_COVERAGE"})
    elif kind == "alpaca_news":
        if "news" not in body or "next_page_token" not in body:
            raise ValueError("news envelope missing")
        for row in body["news"] or []:
            records.append({"provider_id": str(row.get("id")), "published_at": row.get("created_at"),
                            "updated_at": row.get("updated_at"), "symbols": row.get("symbols", []), "source": row})
    elif kind == "alpaca_actions":
        if "corporate_actions" not in body or "next_page_token" not in body:
            raise ValueError("corporate action envelope missing")
        for action_type, rows in (body["corporate_actions"] or {}).items():
            for row in rows:
                records.append({"provider_id": row.get("id"), "action_type": action_type,
                                "source": row, "governing_date": row.get("process_date"),
                                "governing_date_basis": "ALPACA_PROCESS_DATE"})
    else:
        if "results" not in body or str(body.get("status", "")).upper() not in ("OK", "DELAYED"):
            raise ValueError("Massive results/status envelope missing")
        rows = body["results"]
        rows = [rows] if isinstance(rows, dict) else rows or []
        if not isinstance(rows, list):
            raise ValueError("invalid Massive result collection")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid Massive source record")
            record = {"symbol": row.get("ticker"), "source": row}
            if kind == "massive_news":
                record.update(provider_id=row.get("id"), symbols=row.get("tickers", []),
                              published_at=row.get("published_utc"), updated_at=row.get("updated_utc"))
            elif kind == "massive_short_interest":
                record.update(settlement_date=row.get("settlement_date"),
                              publication_time=row.get("published_at", row.get("publication_date")),
                              availability_policy="RETRIEVAL_UPPER_BOUND_PUBLICATION_UNKNOWN_IF_ABSENT")
            elif kind == "massive_short_volume":
                record.update(market_date=row.get("date"),
                              reporting_scope="MASSIVE_FINRA_OFF_EXCHANGE_REPORTING_NOT_TOTAL_MARKET")
            elif kind == "massive_reference":
                record.update(reference_date=scope["asof"], identity_status="PROVIDER_DATED_REFERENCE_REQUIRES_MEMBER_MATCH")
            records.append(record)
    if len(records) > 10000:
        raise ValueError("source record count exceeds request bound")
    next_cursor = body.get("next_page_token")
    if kind.startswith("massive_"):
        next_url = body.get("next_url")
        if next_url:
            u = urlsplit(next_url)
            # Accept the provider's legacy hostname solely as a token container;
            # the next HTTP request is rebuilt for the fixed current origin.
            if u.scheme != "https" or u.netloc not in ("api.massive.com", "api.polygon.io") or u.path != request["path"] or u.fragment:
                raise ValueError("untrusted source continuation URL")
            q = parse_qs(u.query, strict_parsing=True)
            if len(q.get("cursor", [])) != 1:
                raise ValueError("source continuation lacks a unique cursor")
            next_cursor = q["cursor"][0]
    if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 8192):
        raise ValueError("invalid source continuation")
    if next_cursor and next_cursor == task.get("cursor"):
        raise ValueError("provider repeated source continuation")
    reason_counts = {}
    missing_counts = {}
    for record in records:
        for reason in record.get("quality_reasons", []):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        for name in record.get("missing_fields", []):
            missing_counts[name] = missing_counts.get(name, 0) + 1
    quality.extend({"state": "IDENTITY_OR_QUALITY_UNRESOLVED", "reason": reason,
                    "affected_records": count, "scope": "affected_source_records_only"}
                   for reason, count in sorted(reason_counts.items()))
    quality.extend({"state": "IDENTITY_OR_QUALITY_UNRESOLVED", "reason": "PROVIDER_FIELD_NOT_SUPPLIED",
                    "field": name, "affected_records": count, "scope": "field_only"}
                   for name, count in sorted(missing_counts.items()))
    if kind == "massive_short_interest":
        missing_publication = sum(r["publication_time"] is None for r in records)
        if missing_publication:
            quality.append({"state": "IDENTITY_OR_QUALITY_UNRESOLVED", "reason": "PUBLICATION_TIMESTAMP_NOT_SUPPLIED",
                            "field": "publication_time", "affected_records": missing_publication,
                            "downstream_impact": "Retrospective settlement values retained; availability before retrieval remains unknown"})
    if kind == "alpaca_option_contracts" and next_cursor is None:
        quality.append({"state": "IDENTITY_OR_QUALITY_UNRESOLVED", "reason": "HISTORICAL_ENUMERATION_COMPLETENESS_UNKNOWN",
                        "scope": "contract_inventory", "evidence": "Explicit active/inactive reference query exhausted; reference response does not establish every historical listing episode"})
    return tuple(records), next_cursor, tuple(quality)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class BackfillProvider:
    def __init__(self, api_key, secret_key, massive_key="", *, paper=True, opener=None):
        self._api_key, self._secret_key, self._massive_key = api_key, secret_key, massive_key
        self.paper = paper
        self.opener = opener or build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())

    def require_credentials(self, task):
        if task["kind"].startswith("alpaca_"):
            if not self._api_key or not self._secret_key:
                raise ProviderProblem("BLOCKED_EXTERNAL", "Existing Alpaca worker credential is unavailable",
                                      evidence={"dependency": "ALPACA_WORKER_CREDENTIAL"})
        else:
            if not self._massive_key:
                raise ProviderProblem("BLOCKED_EXTERNAL", "Existing Massive credential is not configured on this worker",
                                      evidence={"dependency": "MASSIVE_WORKER_CREDENTIAL", "not_a_provider_limitation": True})

    def supported_kinds(self):
        return tuple(kind for kind in KINDS if (kind.startswith("alpaca_") and self._api_key and self._secret_key)
                     or (kind.startswith("massive_") and self._massive_key))

    def fetch(self, task):
        plan = request_for(task, paper=self.paper)
        self.require_credentials(task)
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if plan["provider"] == "Alpaca":
            headers.update({"APCA-API-KEY-ID": self._api_key, "APCA-API-SECRET-KEY": self._secret_key})
        else:
            headers["Authorization"] = "Bearer " + self._massive_key
        url = "https://" + plan["host"] + plan["path"] + ("?" + urlencode(plan["params"]) if plan["params"] else "")
        request = Request(url, headers=headers, method="GET")
        deadline = monotonic() + REQUEST_TIMEOUT_SECONDS
        try:
            response = self.opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
        except HTTPError as exc:
            response = exc
        except (URLError, OSError, TimeoutError):
            raise ProviderProblem("SOURCE_TRANSPORT_ERROR", "Bounded provider request failed", retryable=True, retry_after=30,
                                  evidence={"request": plan}) from None
        with response:
            status = response.status if hasattr(response, "status") else response.code
            safe_headers = {k: response.headers[k] for k in ("X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After") if response.headers.get(k)}
            raw = bytearray()
            while len(raw) <= MAX_BODY_BYTES:
                if monotonic() >= deadline:
                    raise ProviderProblem("SOURCE_READ_TIMEOUT", "Provider response exceeded its bounded read time", retryable=True, retry_after=30,
                                          evidence={"request": plan, "http_status": status})
                part = response.read1(min(65536, MAX_BODY_BYTES + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            if len(raw) > MAX_BODY_BYTES:
                # This is a bounded prefix, not an original complete response
                # and not an exhausted page. No continuation is guessed from it.
                prefix = bytes(raw[:MAX_PARTIAL_BODY_BYTES])
                partial = {"request": plan, "http_status": status, "headers": safe_headers,
                           "fetched_at": utc_now(), "adapter_version": VERSION,
                           "response_complete": False, "read_limit_bytes": MAX_BODY_BYTES,
                           "observed_prefix_bytes": len(raw),
                           "observed_prefix_sha256": sha256(bytes(raw)).hexdigest(),
                           "partial_body_base64": base64.b64encode(prefix).decode("ascii"),
                           "partial_body_bytes": len(prefix),
                           "partial_body_sha256": sha256(prefix).hexdigest(),
                           "cursor_controls_page_size": plan["provider"] == "Massive" and bool(plan["params"].get("cursor"))}
                if response.geturl() != url or response.headers.get("Content-Encoding", "identity") not in ("", "identity"):
                    raise ProviderProblem("UNEXPECTED_SOURCE_TRANSPORT", "Redirect or compressed response refused", evidence=partial)
                if status != 200:
                    code = "SOURCE_RATE_LIMIT" if status == 429 else "BLOCKED_EXTERNAL" if status in (401, 403) else "SOURCE_HTTP_ERROR"
                    raise ProviderProblem(code, "Provider request returned HTTP " + str(status),
                                          retryable=status in (408, 425, 429, 500, 502, 503, 504),
                                          retry_after=_retry_delay(safe_headers), evidence=partial)
                raise ProviderProblem("SOURCE_PAGE_TOO_LARGE", "Response exceeds the bounded body size; retry only at a smaller durable page limit",
                                      retryable=(plan["params"].get("limit", 1) > 1 and not partial["cursor_controls_page_size"]),
                                      retry_after=_retry_delay(safe_headers) if "Retry-After" in safe_headers else 2,
                                      evidence=partial)
            raw_text = bytes(raw).decode("utf-8", errors="replace")
            evidence = {"request": plan, "http_status": status, "raw_body": raw_text,
                        "body_sha256": sha256(bytes(raw)).hexdigest(), "headers": safe_headers, "fetched_at": utc_now()}
            if response.geturl() != url or response.headers.get("Content-Encoding", "identity") not in ("", "identity"):
                raise ProviderProblem("UNEXPECTED_SOURCE_TRANSPORT", "Redirect or compressed response refused", evidence=evidence)
            if status != 200:
                retry = status in (408, 425, 429, 500, 502, 503, 504)
                delay = _retry_delay(safe_headers)
                code = "SOURCE_RATE_LIMIT" if status == 429 else "BLOCKED_EXTERNAL" if status in (401, 403) else "SOURCE_HTTP_ERROR"
                raise ProviderProblem(code, "Provider request returned HTTP " + str(status), retryable=retry, retry_after=delay, evidence=evidence)
            try:
                records, next_cursor, quality = parse_response(task, plan, raw_text)
            except (ValueError, KeyError, TypeError, RecursionError) as exc:
                evidence["parser_error_type"] = type(exc).__name__
                raise ProviderProblem("SOURCE_PARSE_ERROR", "Source retained but parsing requires repair", evidence=evidence) from None
            return ProviderPage(raw_text, evidence["body_sha256"], status, safe_headers.get("X-Request-ID"),
                                evidence["fetched_at"], plan, records, next_cursor, quality, safe_headers)
