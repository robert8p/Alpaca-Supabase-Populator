from __future__ import annotations

"""ClinicalTrials.gov sponsor-search compatibility and scope controls.

The official v2 API supports ``query.spons``. Some data-centre requests receive a
403 from the search endpoint even though exact NCT retrieval remains available.
This layer retries with an equivalent fielded ``query.term`` expression and a
normal browser-compatible identification header. If both forms are denied, the
source is marked unavailable rather than silently interpreted as no matching
study.
"""

import re
from datetime import datetime
from typing import Any

import httpx

EXPLICIT_REGULATED_TERMS = re.compile(
    r"\b(?:NCT\d{8}|clinical\s+trial|phase\s*(?:1|2|3|I|II|III)\b|FDA\b|"
    r"biotech|biopharma|pharma(?:ceutical)?|therapeutic|medical\s+device|"
    r"diagnostic|vaccine|oncology|drug\s+(?:candidate|product|approval))\b",
    re.IGNORECASE,
)
CT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OversoldReversion/1.0; contact=robert8p@gmail.com)",
    "Accept": "application/json",
    "Referer": "https://clinicaltrials.gov/",
}


def _precise_regulated_candidate(symbol: str, aliases: list[str], articles: list[dict[str, Any]]) -> bool:
    issuer_text = "\n".join([symbol, *aliases])
    if EXPLICIT_REGULATED_TERMS.search(issuer_text):
        return True
    evidence_text = "\n".join(
        f"{item.get('headline') or ''} {item.get('summary') or ''}"
        for item in articles
        if isinstance(item, dict)
    )
    return bool(EXPLICIT_REGULATED_TERMS.search(evidence_text))


def _fielded_sponsor_query(alias: str) -> str:
    escaped = str(alias).replace('"', "").strip()
    return f'AREA[LeadSponsorName]"{escaped}"'


def _request_studies(alias: str, timeout_seconds: float) -> tuple[dict[str, Any] | None, int, str | None]:
    attempts = [
        {"query.spons": alias, "pageSize": 10},
        {"query.term": _fielded_sponsor_query(alias), "pageSize": 10},
    ]
    request_count = 0
    last_error: str | None = None
    with httpx.Client(
        headers=CT_HEADERS,
        timeout=httpx.Timeout(timeout_seconds, connect=4.0),
        follow_redirects=True,
    ) as client:
        for params in attempts:
            request_count += 1
            try:
                response = client.get("https://clinicaltrials.gov/api/v2/studies", params=params)
            except Exception as exc:
                last_error = f"request failed: {exc}"
                continue
            if response.status_code == 200:
                payload = response.json()
                return (payload if isinstance(payload, dict) else {}), request_count, None
            if response.status_code in {403, 429}:
                last_error = f"HTTP {response.status_code} from ClinicalTrials.gov sponsor search"
                continue
            if response.status_code == 404:
                return {}, request_count, None
            last_error = f"HTTP {response.status_code} from ClinicalTrials.gov sponsor search"
    return None, request_count, last_error


def patch_module(module: Any) -> None:
    if getattr(module, "_clinicaltrials_search_compat_installed", False):
        return

    module._regulated_candidate = _precise_regulated_candidate

    def fetch_sponsor_trials(
        primary_module: Any,
        *,
        symbol: str,
        aliases: list[str],
        cutoff: datetime,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        articles: list[dict[str, Any]] = []
        request_count = 0
        errors: list[str] = []
        seen: set[str] = set()
        access_denied = False
        for alias in aliases[:3]:
            payload, requests, error = _request_studies(
                alias,
                float(getattr(primary_module, "PRIMARY_TIMEOUT_SECONDS", 8.0)),
            )
            request_count += requests
            if payload is None:
                if error:
                    errors.append(
                        f"ClinicalTrials.gov sponsor search unavailable for {alias}: {error}; "
                        "exact NCT retrieval remains active"
                    )
                if error and "HTTP 403" in error:
                    access_denied = True
                    break
                continue
            studies = payload.get("studies") if isinstance(payload.get("studies"), list) else []
            for study in studies:
                if not isinstance(study, dict):
                    continue
                article = module._trial_sponsor_article(
                    primary_module,
                    symbol=symbol,
                    aliases=aliases,
                    study=study,
                    cutoff=cutoff,
                )
                key = str((article or {}).get("id") or "")
                if article and key and key not in seen:
                    seen.add(key)
                    articles.append(article)
        articles.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        if access_denied:
            errors = errors[:1]
        return articles[:6], request_count, errors

    module._fetch_sponsor_trials = fetch_sponsor_trials
    module._clinicaltrials_search_compat_installed = True
