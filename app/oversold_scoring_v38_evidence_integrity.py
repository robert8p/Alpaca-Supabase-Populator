from __future__ import annotations

"""Validate evidence before the versioned economic scorer consumes it.

This is an evidence-correctness release, not a fitted trading model. No weights,
return targets or decision thresholds are optimized here. Existing snapshots and
the v3.1--v3.7 implementation files remain untouched.
"""

from copy import deepcopy
from datetime import UTC, date, datetime, time
import re
from typing import Any

from app.oversold_fundamentals import fundamental_risk_flags
from app.oversold_live_enrichment import _runtime_fetch_enabled
from app.oversold_scoring_v37_local_attribution import direct_candidate_existential_event

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_8"
SCORING_CONFIG_VERSION = "or_score_config_2026_09_06_v10"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3_8"
EVIDENCE_INTEGRITY_VERSION = "evidence_integrity_v1"

_SENTENCES = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_CONDITIONAL = re.compile(r"\b(?:may|might|could|if|risk that|risk of|in the event)\b", re.I)
_ANALYST_CONTEXT = re.compile(r"\b(?:analysts?|broker(?:age)?|research|coverage|stock|shares?|equity|price target|buy|sell|hold|neutral|overweight|underweight|outperform|underperform)\b", re.I)
_ANALYST_ACTION = re.compile(r"\b(?:upgrad(?:e|ed|es)|downgrad(?:e|ed|es)|maintain(?:s|ed)?|reiterat(?:e|es|ed)|initiat(?:e|es|ed)|rais(?:e|es|ed)|lower(?:s|ed)?|cut(?:s)?|boost(?:s|ed)?|trim(?:s|med)?|reduc(?:e|es|ed))\b", re.I)
_TARGET_UP = re.compile(r"\b(?:rais(?:e|es|ed)|boost(?:s|ed)?|increas(?:e|es|ed))\b.{0,45}\bprice target\b|\bprice target\b.{0,45}\b(?:raised|boosted|increased)\b", re.I)
_TARGET_DOWN = re.compile(r"\b(?:lower(?:s|ed)?|cut(?:s)?|trim(?:s|med)?|reduc(?:e|es|ed))\b.{0,45}\bprice target\b|\bprice target\b.{0,45}\b(?:lowered|cut|trimmed|reduced)\b", re.I)
_EARNINGS_RELEASE = re.compile(
    r"\bitems?\s*(?:[:\-—]\s*)?2\.02\b|\bresults of operations and financial condition\b|"
    r"\b(?:reports?|reported|announces?|announced|releases?|released)\b.{0,65}\b(?:earnings|financial results|quarter(?:ly)? results)\b|"
    r"\b(?:earnings|financial results)\b.{0,35}\b(?:release|announcement|reported)\b", re.I)
_GUIDANCE_CUT = re.compile(
    r"\b(?:cuts?|lower(?:s|ed)?|reduc(?:es|ed)?|withdraw(?:s|n)?)\s+"
    r"(?:(?:its|the|full.year|annual|quarterly|revenue|earnings|eps|profit|sales)\s+){0,4}"
    r"(?:guidance|outlook|forecast)\b|\b(?:guidance|outlook|forecast)\s+"
    r"(?:(?:was|is|has|been)\s+){0,3}(?:cut|lowered|reduced|withdrawn)\b", re.I)
_FILING_HEADLINE = re.compile(r"\b(?:filed|files)\s+(?:a\s+)?form\s+(?:8-k|10-[qk]|6-k|20-f)\b", re.I)
_METADATA_BODY = re.compile(
    r"^(?:\s*(?:SEC filing accepted [0-9T:+Z-]+\.?|Form [A-Z0-9/-]+\.?|"
    r"Items?: [0-9., ]+|Results of operations and financial condition\.?|"
    r"Financial statements and exhibits\.?|https?://\S+))*\s*$", re.I)
_ISSUER_WARNING = re.compile(
    r"\b(?:the company|the registrant|the issuer|management|we)\s+"
    r"(?:(?:has|have|had)\s+)?(?:warned|cautioned|disclosed|concluded)\b"
    r"(?P<claim>[^.!?\n]{0,260})\bgoing concern\b", re.I)
_THIRD_PARTY_WARNING = re.compile(
    r"\b(?:vendor|supplier|customer|counterparty|tenant|borrower|investee|third.party)\b", re.I)


def asserted_issuer_solvency_warning(text: str) -> bool:
    """The warning is an observed fact even when future survival is uncertain."""
    for match in _ISSUER_WARNING.finditer(str(text or "")):
        claim = match.group("claim")
        if _THIRD_PARTY_WARNING.search(claim):
            continue
        if re.search(r"\b(?:no|not|without)\s+(?:any\s+)?substantial doubt\b|\bnot\s+unable\b", claim, re.I):
            continue
        if re.search(r"\b(?:unable to continue|substantial doubt)\b", claim, re.I):
            return True
    return False


def _timestamp(value: Any, *, date_at_end: bool = False) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        try:
            day = value if isinstance(value, date) else date.fromisoformat(str(value))
            return datetime.combine(day, time.max if date_at_end else time.min, UTC)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def validate_fundamentals(fundamentals: Any, cutoff: datetime | None) -> tuple[dict | None, dict]:
    if not isinstance(fundamentals, dict) or not fundamentals:
        return None, {"status": "UNAVAILABLE", "reasons": []}
    reasons: list[str] = []
    available = _timestamp(fundamentals.get("available_from"), date_at_end=True)
    if not fundamentals.get("source"):
        reasons.append("fundamental_source_missing")
    if available is None:
        reasons.append("fundamental_availability_missing")
    elif cutoff is None or available > cutoff:
        reasons.append("fundamental_not_available_at_cutoff")
    period = _timestamp(fundamentals.get("report_period_end"))
    if period is not None and cutoff is not None and period > cutoff:
        reasons.append("fundamental_report_period_after_cutoff")
    if reasons:
        return None, {"status": "REJECTED", "reasons": reasons}
    clean = deepcopy(fundamentals)
    clean["age_calendar_days"] = (cutoff.date() - available.date()).days
    # Recompute rather than trust flags that may have come from another snapshot.
    clean["derived_risk_flags"] = fundamental_risk_flags(clean)
    return clean, {"status": "VERIFIED_POINT_IN_TIME", "reasons": [], "available_from": available.isoformat()}


def _safe_analyst_clauses(text: str) -> list[str]:
    return [clause for clause in _SENTENCES.split(str(text or ""))
            if not _CONDITIONAL.search(clause)
            and _ANALYST_CONTEXT.search(clause) and _ANALYST_ACTION.search(clause)]


def _strip_hypothetical_disclosure(text: Any) -> str:
    # Generic risk disclosure describes possible events, not realized catalysts.
    # Retain affirmative clauses even when adjacent boilerplate is excluded.
    return " ".join(clause for clause in _SENTENCES.split(str(text or ""))
                    if asserted_issuer_solvency_warning(clause) or not (_CONDITIONAL.search(clause) and re.search(
                        r"\b(?:analysts?|downgrad(?:e|es|ed)|bankruptcy|going concern|default|lawsuits?|fraud|"
                        r"security breach|dilution|adversely affect|actual results|differ materially)\b", clause, re.I)))


def prepare_evidence(candidate: dict, articles: list[dict]) -> tuple[dict, list[dict], dict]:
    """Copy inputs and reject unavailable article versions before any score pass."""
    clean = deepcopy(candidate)
    cutoff = _timestamp(clean.get("evidence_cutoff")) or _timestamp(clean.get("latest_trade_ts"))
    audit: dict[str, Any] = {
        "version": EVIDENCE_INTEGRITY_VERSION,
        "cutoff": cutoff.isoformat() if cutoff else None,
        "retained_article_count": 0, "excluded_articles": [],
        "context_only_article_ids": [], "issues": [],
    }
    if cutoff is None:
        audit["issues"].append("signal_cutoff_missing")
    retained: list[dict] = []
    for original in articles:
        if not isinstance(original, dict):
            continue
        article = deepcopy(original)
        primary = article.get("primary_evidence") if isinstance(article.get("primary_evidence"), dict) else {}
        # updated_at bounds the text version actually supplied. A pre-cutoff
        # publication timestamp cannot legitimize a later edited article body.
        raw_dates = [article.get("created_at"), primary.get("available_at"), article.get("updated_at")]
        supplied = [value for value in raw_dates if value is not None and value != ""]
        dates = [_timestamp(value, date_at_end=True) for value in supplied]
        reason = None
        if not dates or any(value is None for value in dates):
            reason = "article_availability_missing_or_invalid"
        elif cutoff is None or max(dates) > cutoff:
            reason = "article_version_after_cutoff"
        if reason:
            audit["excluded_articles"].append({"id": article.get("id"), "headline": article.get("headline"), "reason": reason})
            continue
        article["created_at"] = max(dates).isoformat()
        article["summary"] = _strip_hypothetical_disclosure(article.get("summary"))
        for key in ("summary", "content_excerpt"):
            if key in primary:
                primary[key] = _strip_hypothetical_disclosure(primary[key])
        if primary:
            article["primary_evidence"] = primary
        body = " ".join(str(value or "") for value in (article.get("summary"), primary.get("summary"), primary.get("content_excerpt"))).strip()
        metadata_only = bool(_FILING_HEADLINE.search(str(article.get("headline") or "")) and (not body or _METADATA_BODY.fullmatch(body)))
        if metadata_only or (primary.get("metadata") or {}).get("context_only"):
            article.setdefault("primary_evidence", {}).setdefault("metadata", {})["context_only"] = True
            audit["context_only_article_ids"].append(article.get("id"))
        retained.append(article)
    audit["retained_article_count"] = len(retained)
    clean["fundamentals"], audit["fundamentals"] = validate_fundamentals(clean.get("fundamentals"), cutoff)
    if "_sec_fundamentals" in clean:
        clean["_sec_fundamentals"], sec_audit = validate_fundamentals(clean.get("_sec_fundamentals"), cutoff)
        if audit["fundamentals"]["status"] == "UNAVAILABLE":
            audit["fundamentals"] = sec_audit
    if audit["excluded_articles"]:
        audit["issues"].append("unavailable_article_versions_excluded")
    audit["issues"].extend(audit["fundamentals"].get("reasons") or [])
    clean["_v38_evidence_integrity"] = audit
    return clean, retained, audit


def patch_module(module: Any) -> None:
    if getattr(module, "_v38_evidence_integrity_installed", False):
        return
    legacy = getattr(module, "_legacy", module)
    original_signals = legacy._event_signals
    original_flags = legacy.direct_news_risk_flags
    original_quality = legacy._source_evidence_quality
    original_enrichment = legacy.load_runtime_enrichment
    original_score = module.score_candidate
    original_contract = module.public_scoring_contract

    def direct_news_risk_flags(text):
        flags = original_flags(text)
        # The previous flow silently promoted a keyword-derived flag to a
        # filing-verified solvency assertion, bypassing subject attribution.
        if "solvency" in flags and not (direct_candidate_existential_event(text, []) or asserted_issuer_solvency_warning(text)):
            flags.remove("solvency")
        return flags

    def event_signals(text, risk_flags, sector_hint):
        signals = dict(original_signals(text, risk_flags, sector_hint))
        if asserted_issuer_solvency_warning(text):
            signals["existential_or_solvency"] = True
            signals["catastrophic_financing"] = bool(signals.get("dilution_or_financing"))
            signals["analyst_only"] = False
        clauses = _safe_analyst_clauses(text)
        analyst = bool(clauses)
        signals["analyst_action"] = analyst
        signals["analyst_target_raise"] = any(_TARGET_UP.search(clause) for clause in clauses)
        signals["analyst_target_cut"] = any(_TARGET_DOWN.search(clause) for clause in clauses)
        signals["analyst_only"] = bool(signals.get("analyst_only") and analyst and not _EARNINGS_RELEASE.search(text))
        # New numeric guidance direction and event-specific earnings outcomes
        # take precedence over analyst reactions to those outcomes.
        if _GUIDANCE_CUT.search(text):
            signals["guidance_cut"] = True
            signals["analyst_only"] = False
        return signals

    def source_evidence_quality(candidate, articles, *, cause_recognised, conflicting):
        causal = [article for article in articles if not ((article.get("primary_evidence") or {}).get("metadata") or {}).get("context_only")]
        return original_quality(candidate, causal, cause_recognised=cause_recognised, conflicting=conflicting)

    def load_runtime_enrichment(candidate, sector_hint):
        # The SEC fallback historically ignored the shared enrichment switch,
        # causing isolated scoring/replays to make unexpected remote requests.
        if not _runtime_fetch_enabled():
            candidate["_sec_prefetch_complete"] = True
        result = deepcopy(original_enrichment(candidate, sector_hint))
        candidate["_v38_intraday_bars"] = result.get("intraday_bars") or []
        cutoff = _timestamp(candidate.get("evidence_cutoff")) or _timestamp(candidate.get("latest_trade_ts"))
        valid, financial_audit = validate_fundamentals(result.get("fundamentals"), cutoff)
        result["fundamentals"] = valid
        audit = candidate.get("_v38_evidence_integrity")
        if isinstance(audit, dict):
            if financial_audit["status"] != "UNAVAILABLE" or audit["fundamentals"]["status"] != "REJECTED":
                audit["fundamentals"] = financial_audit
            audit["issues"] = sorted(set(audit["issues"] + financial_audit.get("reasons", [])))
        return result

    for name, function in (("_event_signals", event_signals), ("direct_news_risk_flags", direct_news_risk_flags),
                           ("_source_evidence_quality", source_evidence_quality), ("load_runtime_enrichment", load_runtime_enrichment)):
        setattr(legacy, name, function)
        setattr(module, name, function)

    config = {
        "version": EVIDENCE_INTEGRITY_VERSION,
        "point_in_time_rule": "all supplied article-version timestamps and financial availability must precede or equal the signal cutoff; date-only evidence must be from a prior date",
        "causality_rule": "filing metadata establishes disclosure existence only; an earnings release prevents analyst reactions being labeled analyst-only",
        "solvency_rule": "news requires a locally asserted issuer event; financial flags require validated dated financial evidence",
        "probability_status": "uncalibrated; no verified profitable-stock probability or improvement claim",
        "historical_policy": "new versioned runs only; original evidence snapshots remain immutable",
    }
    module.SCORING_MODEL_VERSION = SCORING_MODEL_VERSION
    module.SCORING_CONFIG_VERSION = SCORING_CONFIG_VERSION
    module.CATALYST_SCHEMA_VERSION = CATALYST_SCHEMA_VERSION
    module.SCORING_CONFIG = deepcopy(module.SCORING_CONFIG)
    module.SCORING_CONFIG["versions"].update(scoring_model_version=SCORING_MODEL_VERSION, scoring_config_version=SCORING_CONFIG_VERSION, catalyst_schema_version=CATALYST_SCHEMA_VERSION, calibration_model_version=None)
    module.SCORING_CONFIG["v3_8_evidence_integrity"] = config

    def score_candidate(candidate, articles, catalyst_class, risk_flags):
        clean, retained, audit = prepare_evidence(candidate, articles)
        result = original_score(clean, retained, catalyst_class, list(risk_flags or []))
        result.setdefault("point_in_time_enrichment", {})["intraday_bars"] = deepcopy(clean.get("_v38_intraday_bars") or [])
        analysis = result.setdefault("catalyst_analysis", {})
        analysis["evidence_integrity"] = deepcopy(audit)
        analysis["analysis_method"] = "rules_v3_8_point_in_time_evidence_integrity_robust_ensemble"
        analysis["score_semantics"] = {
            "survivability": "uncalibrated financial-strength index; not survival probability",
            "reversibility": "uncalibrated event-reversibility index; not return probability",
            "evidence_confidence": "evidence-coverage index; not forecast accuracy",
        }
        result.setdefault("calculation_trace", {})["v3_8_evidence_integrity"] = deepcopy(audit)
        result.update(scoring_model_version=SCORING_MODEL_VERSION, scoring_config_version=SCORING_CONFIG_VERSION,
                      catalyst_schema_version=CATALYST_SCHEMA_VERSION, calibration_model_version=None, model_status="uncalibrated")
        result["explanation"] = (str(result.get("explanation") or "") + " Evidence availability and causal attribution validated by v3.8; component scores are uncalibrated indices.").strip()
        return result

    def public_scoring_contract():
        contract = deepcopy(original_contract())
        contract["versions"] = deepcopy(module.SCORING_CONFIG["versions"])
        contract["evidence_integrity"] = deepcopy(config)
        return contract

    module.score_candidate = score_candidate
    module.public_scoring_contract = public_scoring_contract
    module._v38_evidence_integrity_installed = True
