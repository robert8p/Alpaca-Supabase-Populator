from __future__ import annotations

"""Exact-match regulator evidence beyond filing identifiers.

This additive layer expands the primary-evidence pipeline without fuzzy entity
matching. It only retains FDA enforcement and ClinicalTrials.gov sponsor records
when the issuer name (or an SEC-reported former name) matches the regulator record
exactly after conservative corporate-suffix normalization. Date-only records must
strictly predate the signal date.
"""

import concurrent.futures
import json
import re
from datetime import UTC, datetime, time as dt_time
from typing import Any

import httpx

PRIMARY_EVIDENCE_VERSION = "primary_event_evidence_v2"
FDA_DRUG_ENFORCEMENT_URL = "https://api.fda.gov/drug/enforcement.json"
FDA_DEVICE_ENFORCEMENT_URL = "https://api.fda.gov/device/enforcement.json"
CLINICAL_TRIAL_SEARCH_URL = "https://clinicaltrials.gov/api/v2/studies"

REGULATED_TERMS = re.compile(
    r"\b(?:biotech|biopharma|pharma|pharmaceutical|therapeutic|medical|medtech|"
    r"device|drug|clinical|trial|fda|recall|diagnostic|healthcare|oncology|vaccine)\b",
    re.IGNORECASE,
)
CORPORATE_SUFFIXES = re.compile(
    r"\b(?:incorporated|inc|corporation|corp|company|co|limited|ltd|plc|llc|lp|"
    r"holdings?|group|ordinary shares?|common stock|class [a-z])\b",
    re.IGNORECASE,
)


def _normalise_name(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = CORPORATE_SUFFIXES.sub(" ", text)
    return " ".join(text.split())


def _issuer_aliases(submissions: dict[str, Any], fallback: str) -> list[str]:
    aliases = [str(submissions.get("name") or ""), fallback]
    former = submissions.get("formerNames") if isinstance(submissions.get("formerNames"), list) else []
    aliases.extend(str(item.get("name") or "") for item in former if isinstance(item, dict))
    output: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        clean = _normalise_name(alias)
        if len(clean) < 4 or clean in seen:
            continue
        seen.add(clean)
        output.append(alias.strip())
    return output[:8]


def _regulated_candidate(symbol: str, aliases: list[str], articles: list[dict[str, Any]]) -> bool:
    text = "\n".join(
        [symbol, *aliases]
        + [f"{item.get('headline') or ''} {item.get('summary') or ''}" for item in articles if isinstance(item, dict)]
    )
    return bool(REGULATED_TERMS.search(text))


def _date_from_yyyymmdd(module: Any, value: Any):
    text = str(value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%Y%m%d").date()
        except ValueError:
            return None
    return module._parse_date(value)


def _enforcement_article(
    module: Any,
    *,
    symbol: str,
    source_kind: str,
    authority: str,
    row: dict[str, Any],
    cutoff: datetime,
    aliases: list[str],
) -> dict[str, Any] | None:
    recalling_firm = str(row.get("recalling_firm") or "").strip()
    if not recalling_firm:
        return None
    alias_set = {_normalise_name(alias) for alias in aliases}
    if _normalise_name(recalling_firm) not in alias_set:
        return None
    report_date = _date_from_yyyymmdd(module, row.get("report_date"))
    if report_date is None or report_date >= cutoff.date():
        return None
    available_at = datetime.combine(report_date, dt_time.min, tzinfo=UTC)
    recall_number = str(row.get("recall_number") or row.get("event_id") or "").strip()
    if not recall_number:
        recall_number = module._sha256(json.dumps(row, sort_keys=True, default=str))[:20]
    classification = str(row.get("classification") or "not stated")
    status = str(row.get("status") or "not stated")
    reason = str(row.get("reason_for_recall") or "not stated")
    product = str(row.get("product_description") or row.get("product_type") or "not stated")
    initiation = str(row.get("recall_initiation_date") or "not stated")
    summary = (
        f"{authority} enforcement record {recall_number}. Recalling firm: {recalling_firm}. "
        f"Classification: {classification}. Status: {status}. Report date: {report_date.isoformat()}. "
        f"Recall initiation: {initiation}. Product: {product}. Reason: {reason}."
    )
    endpoint = FDA_DRUG_ENFORCEMENT_URL if source_kind == "fda_drug_enforcement" else FDA_DEVICE_ENFORCEMENT_URL
    record = {
        "version": PRIMARY_EVIDENCE_VERSION,
        "source_kind": source_kind,
        "source_authority": authority,
        "external_id": recall_number,
        "available_at": available_at.isoformat(),
        "evidence_cutoff": cutoff.isoformat(),
        "title": f"{authority} recall {recall_number}",
        "source_url": endpoint,
        "summary": summary,
        "content_excerpt": summary,
        "content_hash": module._sha256(json.dumps(row, sort_keys=True, default=str)),
        "documents": [],
        "metadata": {
            "recalling_firm": recalling_firm,
            "classification": classification,
            "status": status,
            "report_date": report_date.isoformat(),
            "recall_initiation_date": row.get("recall_initiation_date"),
            "reason_for_recall": reason,
            "product_description": product,
            "exact_issuer_match": True,
            "date_granularity": "date",
            "point_in_time_rule": "FDA report_date must strictly predate cutoff date",
        },
    }
    return {
        "id": f"{source_kind}:{recall_number}",
        "headline": record["title"],
        "summary": summary,
        "source": authority,
        "created_at": available_at.isoformat(),
        "updated_at": available_at.isoformat(),
        "url": endpoint,
        "symbols": [symbol],
        "is_primary_evidence": True,
        "source_kind": source_kind,
        "source_authority": authority,
        "primary_evidence": record,
    }


def _fetch_enforcement(
    module: Any,
    *,
    symbol: str,
    aliases: list[str],
    cutoff: datetime,
    endpoint: str,
    source_kind: str,
    authority: str,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    articles: list[dict[str, Any]] = []
    requests = 0
    errors: list[str] = []
    seen: set[str] = set()
    api_key = module.os.getenv("OPENFDA_API_KEY", "").strip()
    for alias in aliases[:4]:
        params: dict[str, Any] = {"search": f'recalling_firm:"{alias}"', "limit": 20}
        if api_key:
            params["api_key"] = api_key
        try:
            payload, count = module._cached_json(endpoint, params=params)
            requests += count
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                errors.append(f"{source_kind}/{alias}: {exc}")
            continue
        except Exception as exc:
            errors.append(f"{source_kind}/{alias}: {exc}")
            continue
        rows = payload.get("results") if isinstance(payload.get("results"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            article = _enforcement_article(
                module,
                symbol=symbol,
                source_kind=source_kind,
                authority=authority,
                row=row,
                cutoff=cutoff,
                aliases=aliases,
            )
            key = str((article or {}).get("id") or "")
            if article and key not in seen:
                seen.add(key)
                articles.append(article)
    articles.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return articles[:6], requests, errors


def _trial_sponsor_article(
    module: Any,
    *,
    symbol: str,
    aliases: list[str],
    study: dict[str, Any],
    cutoff: datetime,
) -> dict[str, Any] | None:
    protocol = study.get("protocolSection") if isinstance(study.get("protocolSection"), dict) else {}
    identification = protocol.get("identificationModule") if isinstance(protocol.get("identificationModule"), dict) else {}
    status = protocol.get("statusModule") if isinstance(protocol.get("statusModule"), dict) else {}
    sponsor_module = protocol.get("sponsorCollaboratorsModule") if isinstance(protocol.get("sponsorCollaboratorsModule"), dict) else {}
    design = protocol.get("designModule") if isinstance(protocol.get("designModule"), dict) else {}
    lead = sponsor_module.get("leadSponsor") if isinstance(sponsor_module.get("leadSponsor"), dict) else {}
    lead_name = str(lead.get("name") or "").strip()
    if _normalise_name(lead_name) not in {_normalise_name(alias) for alias in aliases}:
        return None
    first_post = module._parse_date(((status.get("studyFirstPostDateStruct") or {}).get("date")))
    last_update = module._parse_date(((status.get("studyLastUpdatePostDateStruct") or {}).get("date")))
    if first_post is None or last_update is None or first_post >= cutoff.date() or last_update >= cutoff.date():
        return None
    nct_id = str(identification.get("nctId") or "").upper().strip()
    if not re.fullmatch(r"NCT\d{8}", nct_id):
        return None
    available_at = datetime.combine(last_update, dt_time.min, tzinfo=UTC)
    title = str(identification.get("briefTitle") or identification.get("officialTitle") or nct_id)
    phases = design.get("phases") if isinstance(design.get("phases"), list) else []
    overall_status = str(status.get("overallStatus") or "not stated")
    summary = (
        f"ClinicalTrials.gov exact sponsor record {nct_id}. Lead sponsor: {lead_name}. "
        f"Title: {title}. Phase: {', '.join(str(item) for item in phases) or 'not stated'}. "
        f"Status: {overall_status}. First posted: {first_post.isoformat()}. "
        f"Last update posted: {last_update.isoformat()}."
    )
    url = f"https://clinicaltrials.gov/study/{nct_id}"
    record = {
        "version": PRIMARY_EVIDENCE_VERSION,
        "source_kind": "clinical_trial_sponsor_match",
        "source_authority": "ClinicalTrials.gov / U.S. National Library of Medicine",
        "external_id": nct_id,
        "available_at": available_at.isoformat(),
        "evidence_cutoff": cutoff.isoformat(),
        "title": f"{nct_id}: {title}",
        "source_url": url,
        "summary": summary,
        "content_excerpt": summary,
        "content_hash": module._sha256(json.dumps(study, sort_keys=True, default=str)),
        "documents": [],
        "metadata": {
            "nct_id": nct_id,
            "lead_sponsor": lead_name,
            "exact_issuer_match": True,
            "overall_status": overall_status,
            "phase": phases,
            "first_post_date": first_post.isoformat(),
            "last_update_post_date": last_update.isoformat(),
            "context_only": True,
            "date_granularity": "date",
            "point_in_time_rule": "first and last registry posting dates must strictly predate cutoff date",
        },
    }
    return {
        "id": f"ctgov-sponsor:{nct_id}",
        "headline": f"ClinicalTrials.gov exact sponsor match {nct_id}: {title}",
        "summary": summary,
        "source": "ClinicalTrials.gov sponsor record",
        "created_at": available_at.isoformat(),
        "updated_at": available_at.isoformat(),
        "url": url,
        "symbols": [symbol],
        "is_primary_evidence": True,
        "source_kind": "clinical_trial_sponsor_match",
        "source_authority": record["source_authority"],
        "primary_evidence": record,
    }


def _fetch_sponsor_trials(
    module: Any,
    *,
    symbol: str,
    aliases: list[str],
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    articles: list[dict[str, Any]] = []
    requests = 0
    errors: list[str] = []
    seen: set[str] = set()
    for alias in aliases[:3]:
        try:
            payload, count = module._cached_json(
                CLINICAL_TRIAL_SEARCH_URL,
                params={"query.spons": alias, "pageSize": 10, "format": "json"},
            )
            requests += count
        except Exception as exc:
            errors.append(f"clinical sponsor/{alias}: {exc}")
            continue
        studies = payload.get("studies") if isinstance(payload.get("studies"), list) else []
        for study in studies:
            if not isinstance(study, dict):
                continue
            article = _trial_sponsor_article(
                module,
                symbol=symbol,
                aliases=aliases,
                study=study,
                cutoff=cutoff,
            )
            key = str((article or {}).get("id") or "")
            if article and key not in seen:
                seen.add(key)
                articles.append(article)
    articles.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return articles[:6], requests, errors


def patch_module(module: Any) -> None:
    if getattr(module, "_regulatory_evidence_v2_installed", False):
        return
    original_batch = module.fetch_primary_evidence_batch
    module.PRIMARY_EVIDENCE_VERSION = PRIMARY_EVIDENCE_VERSION

    def fetch_primary_evidence_batch(
        *,
        symbols: list[str],
        existing_news_map: dict[str, list[dict[str, Any]]],
        cutoff: datetime,
        max_workers: int = module.PRIMARY_MAX_WORKERS,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        primary_map, stats = original_batch(
            symbols=symbols,
            existing_news_map=existing_news_map,
            cutoff=cutoff,
            max_workers=max_workers,
        )
        stats = dict(stats)
        stats["version"] = PRIMARY_EVIDENCE_VERSION
        stats.update(
            {
                "fda_drug_enforcement_records": 0,
                "fda_device_enforcement_records": 0,
                "clinical_trial_sponsor_records": 0,
                "regulator_exact_match_requests": 0,
            }
        )
        try:
            cik_map = module._ticker_map()
        except Exception as exc:
            stats["regulator_alias_error"] = str(exc)[:500]
            return primary_map, stats

        def worker(symbol: str):
            cik = cik_map.get(symbol)
            if not cik:
                return symbol, [], {"requests": 0, "errors": []}
            try:
                submissions, submission_requests = module._submissions(cik)
            except Exception as exc:
                return symbol, [], {"requests": 0, "errors": [str(exc)]}
            aliases = _issuer_aliases(submissions, symbol)
            current = [*(primary_map.get(symbol) or []), *(existing_news_map.get(symbol) or [])]
            if not _regulated_candidate(symbol, aliases, current):
                return symbol, [], {"requests": submission_requests, "errors": []}
            all_articles: list[dict[str, Any]] = []
            errors: list[str] = []
            requests = submission_requests
            drug, count, issues = _fetch_enforcement(
                module,
                symbol=symbol,
                aliases=aliases,
                cutoff=cutoff,
                endpoint=FDA_DRUG_ENFORCEMENT_URL,
                source_kind="fda_drug_enforcement",
                authority="U.S. FDA drug enforcement",
            )
            all_articles.extend(drug); requests += count; errors.extend(issues)
            device, count, issues = _fetch_enforcement(
                module,
                symbol=symbol,
                aliases=aliases,
                cutoff=cutoff,
                endpoint=FDA_DEVICE_ENFORCEMENT_URL,
                source_kind="fda_device_enforcement",
                authority="U.S. FDA device enforcement",
            )
            all_articles.extend(device); requests += count; errors.extend(issues)
            trials, count, issues = _fetch_sponsor_trials(
                module,
                symbol=symbol,
                aliases=aliases,
                cutoff=cutoff,
            )
            all_articles.extend(trials); requests += count; errors.extend(issues)
            return symbol, all_articles, {
                "requests": requests,
                "errors": errors,
                "drug": len(drug),
                "device": len(device),
                "trials": len(trials),
            }

        selected = [str(symbol).upper().strip() for symbol in symbols if symbol]
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(worker, symbol): symbol for symbol in selected}
            for future in concurrent.futures.as_completed(futures):
                symbol = futures[future]
                try:
                    _, additions, detail = future.result()
                except Exception as exc:
                    stats.setdefault("errors_by_symbol", {})[symbol] = [str(exc)[:500]]
                    stats["error_count"] = int(stats.get("error_count") or 0) + 1
                    continue
                stats["regulator_exact_match_requests"] += int(detail.get("requests") or 0)
                stats["fda_drug_enforcement_records"] += int(detail.get("drug") or 0)
                stats["fda_device_enforcement_records"] += int(detail.get("device") or 0)
                stats["clinical_trial_sponsor_records"] += int(detail.get("trials") or 0)
                if detail.get("errors"):
                    stats.setdefault("errors_by_symbol", {})[symbol] = detail["errors"][:8]
                    stats["error_count"] = int(stats.get("error_count") or 0) + len(detail["errors"])
                if not additions:
                    continue
                seen = {
                    str(item.get("id") or item.get("url") or "")
                    for item in (primary_map.get(symbol) or [])
                    if isinstance(item, dict)
                }
                for article in additions:
                    key = str(article.get("id") or article.get("url") or "")
                    if key and key not in seen:
                        primary_map.setdefault(symbol, []).append(article)
                        seen.add(key)
                        stats["primary_evidence_items"] = int(stats.get("primary_evidence_items") or 0) + 1
                primary_map[symbol].sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
                primary_map[symbol] = primary_map[symbol][:12]
        stats["request_count"] = int(stats.get("request_count") or 0) + int(stats["regulator_exact_match_requests"])
        stats["symbols_with_primary_evidence"] = sum(1 for symbol in selected if primary_map.get(symbol))
        return primary_map, stats

    module.fetch_primary_evidence_batch = fetch_primary_evidence_batch
    module._regulatory_evidence_v2_installed = True
