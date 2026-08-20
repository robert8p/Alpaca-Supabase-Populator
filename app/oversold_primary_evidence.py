from __future__ import annotations

"""Point-in-time primary event evidence for Oversold Reversion.

The module deliberately favours deterministic, auditable sources over broad web
scraping:

* SEC EDGAR submissions, filing documents and selected exhibits;
* ClinicalTrials.gov records only when an exact NCT identifier is present; and
* FDA Drugs@FDA records only when an exact application identifier is present.

Every retained item must have an availability timestamp/date that is strictly no
later than the original signal cutoff. Date-only sources are excluded when their
reported date equals the cutoff date because the publication time is unknowable.
"""

import concurrent.futures
import hashlib
import html
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time as dt_time, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin

import httpx

from app.oversold_sec_fundamentals import SEC_USER_AGENT, _ticker_map

logger = logging.getLogger(__name__)

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_ROOT = "https://www.sec.gov"
CLINICAL_TRIAL_URL = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"
FDA_DRUGS_URL = "https://api.fda.gov/drug/drugsfda.json"

PRIMARY_EVIDENCE_VERSION = "primary_event_evidence_v1"
PRIMARY_LOOKBACK_DAYS = max(2, min(30, int(os.getenv("OVERSOLD_PRIMARY_LOOKBACK_DAYS", "10"))))
PRIMARY_MAX_SYMBOLS = max(10, min(200, int(os.getenv("OVERSOLD_PRIMARY_MAX_SYMBOLS", "120"))))
PRIMARY_MAX_WORKERS = max(1, min(6, int(os.getenv("OVERSOLD_PRIMARY_MAX_WORKERS", "4"))))
PRIMARY_MAX_FILINGS_PER_SYMBOL = max(1, min(8, int(os.getenv("OVERSOLD_PRIMARY_MAX_FILINGS", "4"))))
PRIMARY_MAX_DOCUMENT_BYTES = max(250_000, min(3_000_000, int(os.getenv("OVERSOLD_PRIMARY_MAX_DOCUMENT_BYTES", "1250000"))))
PRIMARY_TIMEOUT_SECONDS = float(os.getenv("OVERSOLD_PRIMARY_TIMEOUT_SECONDS", "8"))
PRIMARY_CACHE_SECONDS = 30 * 60
SEC_MIN_REQUEST_INTERVAL_SECONDS = 0.13  # below the SEC's published 10 requests/second ceiling

EVENT_FORMS = {
    "8-K", "8-K/A", "6-K", "6-K/A",
    "10-Q", "10-Q/A", "10-K", "10-K/A",
    "20-F", "20-F/A", "40-F", "40-F/A",
    "S-1", "S-1/A", "S-3", "S-3/A", "F-1", "F-1/A", "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4", "424B5", "424B7",
    "EFFECT", "25-NSE", "NT 10-K", "NT 10-Q", "SC 13D", "SC 13D/A",
    "SC 13G", "SC 13G/A", "425", "DEFA14A",
}
SHORT_WINDOW_FORMS = {
    "10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A",
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "425", "DEFA14A",
}
EXHIBIT_PREFIXES = ("EX-99", "EX-10", "EX-4", "EX-2", "EX-1")
DOCUMENT_EXTENSIONS = (".htm", ".html", ".txt")
NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
FDA_APPLICATION_RE = re.compile(r"\b(NDA|ANDA|BLA)\s*[-#: ]?\s*(\d{5,6})\b", re.IGNORECASE)

EVENT_KEYWORDS = (
    "bankruptcy", "chapter 11", "going concern", "default", "covenant", "liquidity",
    "offering", "registered direct", "private placement", "warrant", "convertible", "dilution",
    "guidance", "forecast", "outlook", "revenue", "sales", "earnings", "margin", "impairment",
    "clinical trial", "phase 3", "phase iii", "primary endpoint", "secondary endpoint", "safety",
    "fda", "complete response letter", "clinical hold", "approval", "recall",
    "investigation", "subpoena", "lawsuit", "material weakness", "restatement", "fraud",
    "resign", "termination", "customer", "contract", "production", "outage", "disruption",
    "delisting", "listing deficiency", "reverse split", "merger", "acquisition",
)

_cache_lock = threading.Lock()
_submissions_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_text_cache: dict[str, tuple[float, str]] = {}
_json_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_sec_rate_lock = threading.Lock()
_last_sec_request_at = 0.0


@dataclass
class SymbolEvidenceResult:
    symbol: str
    articles: list[dict[str, Any]] = field(default_factory=list)
    request_count: int = 0
    errors: list[str] = field(default_factory=list)
    sec_filings: int = 0
    trial_records: int = 0
    fda_records: int = 0
    excluded_after_cutoff: int = 0


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{14}", text):
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def _sec_headers() -> dict[str, str]:
    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json,text/html,text/plain,*/*",
    }


def _generic_headers() -> dict[str, str]:
    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def _throttle_sec() -> None:
    global _last_sec_request_at
    with _sec_rate_lock:
        now = time.monotonic()
        pause = SEC_MIN_REQUEST_INTERVAL_SECONDS - (now - _last_sec_request_at)
        if pause > 0:
            time.sleep(pause)
        _last_sec_request_at = time.monotonic()


def _cached_json(url: str, *, sec: bool = False, params: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
    cache_key = f"{url}?{json.dumps(params or {}, sort_keys=True)}"
    now = time.monotonic()
    with _cache_lock:
        cached = _json_cache.get(cache_key)
        if cached and now - cached[0] <= PRIMARY_CACHE_SECONDS:
            return dict(cached[1]), 0
    if sec:
        _throttle_sec()
    with httpx.Client(
        headers=_sec_headers() if sec else _generic_headers(),
        timeout=httpx.Timeout(PRIMARY_TIMEOUT_SECONDS, connect=4.0),
        follow_redirects=True,
    ) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    value = payload if isinstance(payload, dict) else {}
    with _cache_lock:
        _json_cache[cache_key] = (now, value)
    return dict(value), 1


def _cached_text(url: str, *, sec: bool = False) -> tuple[str, int]:
    now = time.monotonic()
    with _cache_lock:
        cached = _text_cache.get(url)
        if cached and now - cached[0] <= PRIMARY_CACHE_SECONDS:
            return cached[1], 0
    if sec:
        _throttle_sec()
    chunks: list[bytes] = []
    total = 0
    with httpx.Client(
        headers=_sec_headers() if sec else _generic_headers(),
        timeout=httpx.Timeout(PRIMARY_TIMEOUT_SECONDS, connect=4.0),
        follow_redirects=True,
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            encoding = response.encoding or "utf-8"
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                remaining = PRIMARY_MAX_DOCUMENT_BYTES - total
                if remaining <= 0:
                    break
                chunks.append(chunk[:remaining])
                total += min(len(chunk), remaining)
                if total >= PRIMARY_MAX_DOCUMENT_BYTES:
                    break
    text = b"".join(chunks).decode(encoding, errors="replace")
    with _cache_lock:
        _text_cache[url] = (now, text)
    return text, 1


def _submissions(cik: str) -> tuple[dict[str, Any], int]:
    now = time.monotonic()
    with _cache_lock:
        cached = _submissions_cache.get(cik)
        if cached and now - cached[0] <= PRIMARY_CACHE_SECONDS:
            return dict(cached[1]), 0
    payload, requests = _cached_json(SEC_SUBMISSIONS_URL.format(cik=cik), sec=True)
    with _cache_lock:
        _submissions_cache[cik] = (now, payload)
    return payload, requests


def _columnar_rows(recent: dict[str, Any]) -> list[dict[str, Any]]:
    accessions = recent.get("accessionNumber") if isinstance(recent.get("accessionNumber"), list) else []
    rows: list[dict[str, Any]] = []
    for index, accession in enumerate(accessions):
        if not accession:
            continue
        row: dict[str, Any] = {}
        for key, values in recent.items():
            if isinstance(values, list) and index < len(values):
                row[key] = values[index]
        rows.append(row)
    return rows


def _filing_available_at(row: dict[str, Any]) -> datetime | None:
    accepted = _parse_ts(row.get("acceptanceDateTime"))
    if accepted is not None:
        return accepted
    filed = _parse_date(row.get("filingDate"))
    if filed is None:
        return None
    # Conservative fallback for rare rows without an acceptance timestamp.
    return datetime.combine(filed + timedelta(days=1), dt_time.min, tzinfo=UTC)


def _select_filing_rows(submissions: dict[str, Any], cutoff: datetime) -> tuple[list[dict[str, Any]], int]:
    recent = ((submissions.get("filings") or {}).get("recent") or {}) if isinstance(submissions, dict) else {}
    rows = _columnar_rows(recent) if isinstance(recent, dict) else []
    start = cutoff - timedelta(days=PRIMARY_LOOKBACK_DAYS)
    selected: list[dict[str, Any]] = []
    excluded = 0
    for row in rows:
        form = str(row.get("form") or "").upper().strip()
        if form not in EVENT_FORMS:
            continue
        available_at = _filing_available_at(row)
        if available_at is None or available_at > cutoff:
            excluded += 1
            continue
        form_start = cutoff - timedelta(days=4 if form in SHORT_WINDOW_FORMS else PRIMARY_LOOKBACK_DAYS)
        if available_at < max(start, form_start):
            continue
        row = dict(row)
        row["_available_at"] = available_at
        selected.append(row)
    selected.sort(key=lambda row: row["_available_at"], reverse=True)
    return selected[:PRIMARY_MAX_FILINGS_PER_SYMBOL], excluded


class _DocumentTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self.cell_text: list[str] = []
        self.cell_href: str | None = None
        self.cells: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower == "tr":
            self.in_row = True
            self.cells = []
        elif lower in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.cell_text = []
            self.cell_href = None
        elif lower == "a" and self.in_cell:
            for name, value in attrs:
                if name.lower() == "href" and value:
                    self.cell_href = value

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"td", "th"} and self.in_cell:
            self.cells.append({"text": " ".join(self.cell_text).strip(), "href": self.cell_href})
            self.in_cell = False
        elif lower == "tr" and self.in_row:
            self.in_row = False
            if len(self.cells) >= 4 and self.cells[0]["text"].strip().isdigit():
                self.rows.append(
                    {
                        "sequence": self.cells[0]["text"].strip(),
                        "description": self.cells[1]["text"].strip(),
                        "document": self.cells[2]["text"].strip(),
                        "href": self.cells[2].get("href"),
                        "type": self.cells[3]["text"].strip().upper(),
                        "size": self.cells[4]["text"].strip() if len(self.cells) > 4 else None,
                    }
                )


def _filing_paths(cik: str, accession: str) -> tuple[str, str]:
    cik_path = str(int(cik))
    compact = accession.replace("-", "")
    base = f"{SEC_ARCHIVES_ROOT}/Archives/edgar/data/{cik_path}/{compact}/"
    index_url = f"{SEC_ARCHIVES_ROOT}/Archives/edgar/data/{cik_path}/{accession}-index.html"
    return base, index_url


def _parse_filing_documents(index_html: str) -> list[dict[str, Any]]:
    parser = _DocumentTableParser()
    parser.feed(index_html)
    return parser.rows


def _document_is_textual(row: dict[str, Any]) -> bool:
    name = str(row.get("document") or "").lower()
    return name.endswith(DOCUMENT_EXTENSIONS) and not any(
        token in name for token in (".xml", ".xsd", ".jpg", ".jpeg", ".png", ".gif")
    )


def _select_documents(
    rows: list[dict[str, Any]],
    *,
    primary_document: str | None,
    form: str,
) -> list[dict[str, Any]]:
    textual = [row for row in rows if _document_is_textual(row)]
    selected: list[dict[str, Any]] = []
    primary = next(
        (
            row for row in textual
            if primary_document and str(row.get("document") or "").lower() == primary_document.lower()
        ),
        None,
    )
    if primary is not None:
        selected.append(primary)
    elif textual:
        selected.append(textual[0])

    exhibits = [
        row for row in textual
        if any(str(row.get("type") or "").startswith(prefix) for prefix in EXHIBIT_PREFIXES)
    ]
    exhibit_priority = {"EX-99": 0, "EX-10": 1, "EX-4": 2, "EX-2": 3, "EX-1": 4}
    exhibits.sort(
        key=lambda row: (
            min(
                (rank for prefix, rank in exhibit_priority.items() if str(row.get("type") or "").startswith(prefix)),
                default=9,
            ),
            str(row.get("sequence") or ""),
        )
    )
    max_documents = 4 if form.startswith(("8-K", "6-K")) else 2
    for row in exhibits:
        if row not in selected:
            selected.append(row)
        if len(selected) >= max_documents:
            break
    return selected


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", value)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|tr|li|h[1-6])>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\t\r ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _focused_excerpt(text: str, *, limit: int = 8000) -> str:
    clean = _html_to_text(text)
    if len(clean) <= limit:
        return clean
    snippets: list[str] = [clean[:1400]]
    lower = clean.lower()
    locations: list[int] = []
    for keyword in EVENT_KEYWORDS:
        start = 0
        while len(locations) < 14:
            index = lower.find(keyword, start)
            if index < 0:
                break
            locations.append(index)
            start = index + len(keyword)
        if len(locations) >= 14:
            break
    for index in sorted(set(locations))[:14]:
        start = max(0, index - 300)
        end = min(len(clean), index + 650)
        snippet = clean[start:end].strip()
        if snippet and all(snippet[:120] not in existing for existing in snippets):
            snippets.append(snippet)
    output = "\n…\n".join(snippets)
    return output[:limit]


def _filing_article(
    *,
    symbol: str,
    cik: str,
    company_name: str,
    investor_website: str | None,
    row: dict[str, Any],
    cutoff: datetime,
) -> tuple[dict[str, Any] | None, int, list[str]]:
    accession = str(row.get("accessionNumber") or "").strip()
    if not accession:
        return None, 0, ["SEC filing missing accession number"]
    form = str(row.get("form") or "").upper().strip()
    primary_document = str(row.get("primaryDocument") or "").strip() or None
    accepted_at = row.get("_available_at") if isinstance(row.get("_available_at"), datetime) else _filing_available_at(row)
    if accepted_at is None or accepted_at > cutoff:
        return None, 0, [f"{accession}: filing was not available by cutoff"]

    base_url, index_url = _filing_paths(cik, accession)
    request_count = 0
    errors: list[str] = []
    documents: list[dict[str, Any]] = []
    try:
        index_html, requests = _cached_text(index_url, sec=True)
        request_count += requests
        document_rows = _parse_filing_documents(index_html)
    except Exception as exc:
        document_rows = []
        errors.append(f"{accession}: filing index unavailable: {exc}")

    if not document_rows and primary_document:
        document_rows = [
            {
                "sequence": "1",
                "description": row.get("primaryDocDescription") or f"Form {form}",
                "document": primary_document,
                "href": primary_document,
                "type": form,
                "size": None,
            }
        ]

    for document in _select_documents(document_rows, primary_document=primary_document, form=form):
        href = str(document.get("href") or document.get("document") or "").strip()
        if not href:
            continue
        document_url = urljoin(base_url, href)
        try:
            raw, requests = _cached_text(document_url, sec=True)
            request_count += requests
            excerpt = _focused_excerpt(raw)
        except Exception as exc:
            errors.append(f"{accession}/{document.get('document')}: {exc}")
            continue
        documents.append(
            {
                "sequence": document.get("sequence"),
                "description": document.get("description"),
                "document": document.get("document"),
                "document_type": document.get("type"),
                "url": document_url,
                "excerpt": excerpt,
                "content_hash": _sha256(excerpt),
            }
        )

    if not documents:
        return None, request_count, errors or [f"{accession}: no textual filing document retained"]

    items = str(row.get("items") or "").strip()
    descriptions = [
        str(document.get("description") or document.get("document_type") or "document")
        for document in documents
    ]
    combined = "\n\n".join(
        f"[{document.get('document_type') or form} — {document.get('description') or document.get('document')}]\n{document.get('excerpt') or ''}"
        for document in documents
    )
    summary_prefix = (
        f"SEC filing accepted {accepted_at.isoformat()}. Form {form}. "
        + (f"Items: {items}. " if items else "")
        + f"Retained documents: {', '.join(descriptions)}."
    )
    summary = f"{summary_prefix}\n{combined}"[:9000]
    includes_company_release = any(
        str(document.get("document_type") or "").startswith("EX-99") for document in documents
    )
    source = "SEC filing / Company IR exhibit" if includes_company_release else "SEC filing"
    title = f"{company_name or symbol} filed Form {form}"
    if items:
        title += f" — Items {items}"

    record = {
        "version": PRIMARY_EVIDENCE_VERSION,
        "source_kind": "sec_filing",
        "source_authority": "SEC EDGAR",
        "external_id": accession,
        "accession_number": accession,
        "form": form,
        "accepted_at": accepted_at.isoformat(),
        "filed_date": row.get("filingDate"),
        "available_at": accepted_at.isoformat(),
        "evidence_cutoff": cutoff.isoformat(),
        "title": title,
        "source_url": index_url,
        "summary": summary_prefix,
        "content_excerpt": combined[:16000],
        "content_hash": _sha256(combined),
        "documents": [{key: value for key, value in document.items() if key != "excerpt"} for document in documents],
        "metadata": {
            "items": items,
            "primary_document": primary_document,
            "primary_doc_description": row.get("primaryDocDescription"),
            "investor_website": investor_website,
            "includes_company_release_exhibit": includes_company_release,
            "point_in_time_rule": "SEC acceptance timestamp must be no later than evidence cutoff",
            "retrieval_errors": errors,
        },
    }
    article = {
        "id": f"sec:{accession}",
        "headline": title,
        "summary": summary,
        "source": source,
        "created_at": accepted_at.isoformat(),
        "updated_at": accepted_at.isoformat(),
        "url": index_url,
        "symbols": [symbol],
        "is_primary_evidence": True,
        "source_kind": "sec_filing",
        "source_authority": "SEC EDGAR",
        "primary_evidence": record,
    }
    return article, request_count, errors


def _sec_evidence_for_symbol(
    symbol: str,
    cik: str,
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], int, list[str], int]:
    request_count = 0
    errors: list[str] = []
    try:
        submissions, requests = _submissions(cik)
        request_count += requests
    except Exception as exc:
        return [], request_count, [f"SEC submissions unavailable: {exc}"], 0

    company_name = str(submissions.get("name") or symbol)
    investor_website = str(submissions.get("investorWebsite") or "").strip() or None
    selected, excluded = _select_filing_rows(submissions, cutoff)
    articles: list[dict[str, Any]] = []
    for row in selected:
        article, requests, filing_errors = _filing_article(
            symbol=symbol,
            cik=cik,
            company_name=company_name,
            investor_website=investor_website,
            row=row,
            cutoff=cutoff,
        )
        request_count += requests
        errors.extend(filing_errors)
        if article:
            articles.append(article)
    return articles, request_count, errors, excluded


def _evidence_text(articles: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{article.get('headline') or ''}\n{article.get('summary') or ''}"
        for article in articles
        if isinstance(article, dict)
    )


def extract_exact_identifiers(articles: list[dict[str, Any]]) -> dict[str, list[str]]:
    text = _evidence_text(articles)
    nct_ids = sorted({match.upper() for match in NCT_RE.findall(text)})
    applications = sorted(
        {f"{prefix.upper()}{int(number):06d}" for prefix, number in FDA_APPLICATION_RE.findall(text)}
    )
    return {"nct_ids": nct_ids, "fda_applications": applications}


def _trial_article_from_payload(
    *,
    symbol: str,
    nct_id: str,
    payload: dict[str, Any],
    cutoff: datetime,
) -> dict[str, Any] | None:
    protocol = payload.get("protocolSection") if isinstance(payload.get("protocolSection"), dict) else {}
    identification = protocol.get("identificationModule") if isinstance(protocol.get("identificationModule"), dict) else {}
    status = protocol.get("statusModule") if isinstance(protocol.get("statusModule"), dict) else {}
    design = protocol.get("designModule") if isinstance(protocol.get("designModule"), dict) else {}
    outcomes = protocol.get("outcomesModule") if isinstance(protocol.get("outcomesModule"), dict) else {}
    sponsor_module = protocol.get("sponsorCollaboratorsModule") if isinstance(protocol.get("sponsorCollaboratorsModule"), dict) else {}
    last_update = _parse_date(((status.get("studyLastUpdatePostDateStruct") or {}).get("date")))
    if last_update is None or last_update >= cutoff.date():
        return None
    available_at = datetime.combine(last_update, dt_time.min, tzinfo=UTC)
    title = str(identification.get("briefTitle") or identification.get("officialTitle") or nct_id)
    phases = design.get("phases") if isinstance(design.get("phases"), list) else []
    primary_outcomes = outcomes.get("primaryOutcomes") if isinstance(outcomes.get("primaryOutcomes"), list) else []
    primary_measures = [
        str(item.get("measure") or "").strip()
        for item in primary_outcomes[:5]
        if isinstance(item, dict) and item.get("measure")
    ]
    lead_sponsor = sponsor_module.get("leadSponsor") if isinstance(sponsor_module.get("leadSponsor"), dict) else {}
    overall_status = status.get("overallStatus")
    completion = ((status.get("primaryCompletionDateStruct") or {}).get("date"))
    has_results = bool(payload.get("resultsSection"))
    summary = (
        f"ClinicalTrials.gov record {nct_id}. Title: {title}. "
        f"Phase: {', '.join(str(value) for value in phases) or 'not stated'}. "
        f"Status: {overall_status or 'not stated'}. Lead sponsor: {lead_sponsor.get('name') or 'not stated'}. "
        f"Primary completion: {completion or 'not stated'}. Results posted: {'yes' if has_results else 'no'}. "
        f"Primary outcomes: {', '.join(primary_measures) or 'not stated'}. "
        f"Registry last-update posting date: {last_update.isoformat()}."
    )
    url = f"https://clinicaltrials.gov/study/{nct_id}"
    record = {
        "version": PRIMARY_EVIDENCE_VERSION,
        "source_kind": "clinical_trial_registry",
        "source_authority": "ClinicalTrials.gov / U.S. National Library of Medicine",
        "external_id": nct_id,
        "available_at": available_at.isoformat(),
        "evidence_cutoff": cutoff.isoformat(),
        "title": f"{nct_id}: {title}",
        "source_url": url,
        "summary": summary,
        "content_excerpt": summary,
        "content_hash": _sha256(json.dumps(payload, sort_keys=True, default=str)),
        "documents": [],
        "metadata": {
            "nct_id": nct_id,
            "phase": phases,
            "overall_status": overall_status,
            "lead_sponsor": lead_sponsor.get("name"),
            "primary_outcomes": primary_measures,
            "has_results": has_results,
            "date_granularity": "date",
            "point_in_time_rule": "registry last-update posting date must be strictly before cutoff date",
            "context_only": not has_results,
        },
    }
    return {
        "id": f"ctgov:{nct_id}",
        "headline": f"ClinicalTrials.gov {nct_id}: {title}",
        "summary": summary,
        "source": "ClinicalTrials.gov registry",
        "created_at": available_at.isoformat(),
        "updated_at": available_at.isoformat(),
        "url": url,
        "symbols": [symbol],
        "is_primary_evidence": True,
        "source_kind": "clinical_trial_registry",
        "source_authority": record["source_authority"],
        "primary_evidence": record,
    }


def _clinical_trial_evidence(
    symbol: str,
    nct_ids: list[str],
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    articles: list[dict[str, Any]] = []
    requests = 0
    errors: list[str] = []
    for nct_id in nct_ids[:4]:
        try:
            payload, count = _cached_json(CLINICAL_TRIAL_URL.format(nct_id=quote(nct_id)))
            requests += count
            article = _trial_article_from_payload(symbol=symbol, nct_id=nct_id, payload=payload, cutoff=cutoff)
            if article:
                articles.append(article)
        except Exception as exc:
            errors.append(f"{nct_id}: ClinicalTrials.gov unavailable: {exc}")
    return articles, requests, errors


def _fda_article_from_payload(
    *,
    symbol: str,
    application: str,
    payload: dict[str, Any],
    cutoff: datetime,
) -> dict[str, Any] | None:
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    if not results:
        return None
    record = next(
        (item for item in results if str(item.get("application_number") or "").upper() == application),
        results[0],
    )
    submissions = record.get("submissions") if isinstance(record.get("submissions"), list) else []
    eligible: list[dict[str, Any]] = []
    for submission in submissions:
        if not isinstance(submission, dict):
            continue
        status_date = _parse_date(submission.get("submission_status_date"))
        if status_date is not None and status_date < cutoff.date():
            eligible.append({**submission, "_status_date": status_date})
    if not eligible:
        return None
    eligible.sort(key=lambda item: item["_status_date"], reverse=True)
    latest = eligible[0]
    available_at = datetime.combine(latest["_status_date"], dt_time.min, tzinfo=UTC)
    products = record.get("products") if isinstance(record.get("products"), list) else []
    product_names = sorted(
        {
            str(product.get("brand_name") or product.get("active_ingredients") or "").strip()
            for product in products
            if isinstance(product, dict) and (product.get("brand_name") or product.get("active_ingredients"))
        }
    )
    sponsor = record.get("sponsor_name")
    statuses = [
        f"{item.get('_status_date').isoformat()}: {item.get('submission_type') or ''} "
        f"{item.get('submission_status') or ''} {item.get('submission_public_notes') or ''}".strip()
        for item in eligible[:6]
    ]
    summary = (
        f"FDA Drugs@FDA record {application}. Sponsor: {sponsor or 'not stated'}. "
        f"Products: {', '.join(product_names) or 'not stated'}. "
        f"Cutoff-valid submission history: {' | '.join(statuses)}."
    )
    url = f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={application[-6:]}"
    evidence_record = {
        "version": PRIMARY_EVIDENCE_VERSION,
        "source_kind": "fda_regulatory_record",
        "source_authority": "U.S. Food and Drug Administration / Drugs@FDA",
        "external_id": application,
        "available_at": available_at.isoformat(),
        "evidence_cutoff": cutoff.isoformat(),
        "title": f"FDA record {application}",
        "source_url": url,
        "summary": summary,
        "content_excerpt": summary,
        "content_hash": _sha256(json.dumps(eligible, sort_keys=True, default=str)),
        "documents": [],
        "metadata": {
            "application_number": application,
            "sponsor_name": sponsor,
            "products": product_names,
            "eligible_submissions": [
                {key: value for key, value in item.items() if key != "_status_date"}
                for item in eligible[:10]
            ],
            "date_granularity": "date",
            "point_in_time_rule": "FDA submission status date must be strictly before cutoff date",
            "context_only": True,
        },
    }
    return {
        "id": f"fda:{application}",
        "headline": f"FDA Drugs@FDA record for {application}",
        "summary": summary,
        "source": "FDA Drugs@FDA",
        "created_at": available_at.isoformat(),
        "updated_at": available_at.isoformat(),
        "url": url,
        "symbols": [symbol],
        "is_primary_evidence": True,
        "source_kind": "fda_regulatory_record",
        "source_authority": evidence_record["source_authority"],
        "primary_evidence": evidence_record,
    }


def _fda_evidence(
    symbol: str,
    applications: list[str],
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    articles: list[dict[str, Any]] = []
    requests = 0
    errors: list[str] = []
    api_key = os.getenv("OPENFDA_API_KEY", "").strip()
    for application in applications[:4]:
        params: dict[str, Any] = {
            "search": f'application_number:"{application}"',
            "limit": 5,
        }
        if api_key:
            params["api_key"] = api_key
        try:
            payload, count = _cached_json(FDA_DRUGS_URL, params=params)
            requests += count
            article = _fda_article_from_payload(
                symbol=symbol,
                application=application,
                payload=payload,
                cutoff=cutoff,
            )
            if article:
                articles.append(article)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                errors.append(f"{application}: FDA API unavailable: {exc}")
        except Exception as exc:
            errors.append(f"{application}: FDA API unavailable: {exc}")
    return articles, requests, errors


def fetch_primary_evidence_for_symbol(
    *,
    symbol: str,
    cik: str | None,
    existing_articles: list[dict[str, Any]],
    cutoff: datetime,
) -> SymbolEvidenceResult:
    result = SymbolEvidenceResult(symbol=symbol)
    sec_articles: list[dict[str, Any]] = []
    if cik:
        sec_articles, requests, errors, excluded = _sec_evidence_for_symbol(symbol, cik, cutoff)
        result.request_count += requests
        result.errors.extend(errors)
        result.excluded_after_cutoff += excluded
        result.sec_filings = len(sec_articles)
        result.articles.extend(sec_articles)

    identifiers = extract_exact_identifiers([*existing_articles, *sec_articles])
    trial_articles, requests, errors = _clinical_trial_evidence(
        symbol,
        identifiers["nct_ids"],
        cutoff,
    )
    result.request_count += requests
    result.errors.extend(errors)
    result.trial_records = len(trial_articles)
    result.articles.extend(trial_articles)

    fda_articles, requests, errors = _fda_evidence(
        symbol,
        identifiers["fda_applications"],
        cutoff,
    )
    result.request_count += requests
    result.errors.extend(errors)
    result.fda_records = len(fda_articles)
    result.articles.extend(fda_articles)

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for article in sorted(result.articles, key=lambda item: str(item.get("created_at") or ""), reverse=True):
        key = str(article.get("id") or article.get("url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    result.articles = deduped[:8]
    return result


def fetch_primary_evidence_batch(
    *,
    symbols: list[str],
    existing_news_map: dict[str, list[dict[str, Any]]],
    cutoff: datetime,
    max_workers: int = PRIMARY_MAX_WORKERS,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    clean = [str(symbol).upper().strip() for symbol in symbols if symbol]
    selected = list(dict.fromkeys(clean))[:PRIMARY_MAX_SYMBOLS]
    output: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in clean}
    stats: dict[str, Any] = {
        "version": PRIMARY_EVIDENCE_VERSION,
        "requested_symbols": len(clean),
        "selected_symbols": len(selected),
        "completed_symbols": 0,
        "primary_evidence_items": 0,
        "sec_filings": 0,
        "clinical_trial_records": 0,
        "fda_records": 0,
        "request_count": 0,
        "error_count": 0,
        "excluded_after_cutoff": 0,
        "symbols_with_primary_evidence": 0,
        "errors_by_symbol": {},
        "point_in_time_policy": (
            "SEC accepted_at <= cutoff; date-only registry/regulatory records must predate cutoff date; "
            "no historical backfill from current source state"
        ),
    }
    try:
        cik_map = _ticker_map()
    except Exception as exc:
        cik_map = {}
        stats["ticker_map_error"] = str(exc)[:500]

    def worker(symbol: str) -> SymbolEvidenceResult:
        return fetch_primary_evidence_for_symbol(
            symbol=symbol,
            cik=cik_map.get(symbol),
            existing_articles=existing_news_map.get(symbol, []),
            cutoff=cutoff,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(worker, symbol): symbol for symbol in selected}
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                stats["error_count"] += 1
                stats["errors_by_symbol"][symbol] = [str(exc)[:500]]
                continue
            output[symbol] = result.articles
            stats["completed_symbols"] += 1
            stats["primary_evidence_items"] += len(result.articles)
            stats["sec_filings"] += result.sec_filings
            stats["clinical_trial_records"] += result.trial_records
            stats["fda_records"] += result.fda_records
            stats["request_count"] += result.request_count
            stats["excluded_after_cutoff"] += result.excluded_after_cutoff
            if result.articles:
                stats["symbols_with_primary_evidence"] += 1
            if result.errors:
                stats["error_count"] += len(result.errors)
                stats["errors_by_symbol"][symbol] = result.errors[:8]

    return output, stats
