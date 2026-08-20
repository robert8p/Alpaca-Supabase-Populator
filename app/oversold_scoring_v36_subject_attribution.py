from __future__ import annotations

"""Oversold Reversion Score v3.6: subject-aware causal event semantics.

The v3.5 robust ensemble is retained in full. This layer fixes two classes of
high-cost false positives discovered in live point-in-time acceptance testing:

* a candidate was treated as bankrupt because its filing mentioned a vendor's
  Chapter 11; and
* a primary operating update was treated as analyst-only because SEC boilerplate
  referred generically to market analysts.

The patch narrows existential and analyst signals to direct event language,
ignores third-party insolvency references, and recognises explicit seasonal
curtailment as temporary operating evidence. The version is advanced because
these changes alter causal classification and therefore score semantics.
"""

from copy import deepcopy
import re
from typing import Any

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_6"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v8"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3_6"
SUBJECT_ATTRIBUTION_VERSION = "subject_attribution_v1"

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_EXISTENTIAL_TOKEN_RE = re.compile(
    r"\b(?:bankrupt(?:cy)?|chapter\s+(?:7|11)|insolven(?:t|cy)|going concern|"
    r"payment default|debt default|liquidat(?:e|ed|ion)|unable to continue)\b",
    re.IGNORECASE,
)
_THIRD_PARTY_MARKERS = (
    "vendor", "supplier", "customer", "tenant", "borrower", "counterparty",
    "portfolio company", "investee", "distributor", "franchisee",
    "independently owned", "third party", "third-party", "service provider",
)
_DIRECT_COMPANY_SUBJECT_RE = re.compile(
    r"\b(?:the company|the registrant|the issuer|we|our company|our business)\b"
    r".{0,100}\b(?:filed?|filing|petition(?:ed|s)?|commenc(?:e|ed|es)|"
    r"enter(?:ed|s)?|default(?:ed|s)?|is|was|became|faces|seeks?)\b",
    re.IGNORECASE | re.DOTALL,
)
_DIRECT_EXISTENTIAL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:filed?|filing|petition(?:ed|s)?|commenc(?:e|ed|es)|enter(?:ed|s)?|seeks?|sought)\b.{0,100}\b(?:chapter\s+(?:7|11)|bankruptcy(?: protection)?|insolvency proceedings?|liquidation)\b",
        r"\b(?:chapter\s+(?:7|11)|bankruptcy|insolvency)\b.{0,100}\b(?:filing|petition|proceeding|protection|restructuring)\b",
        r"\bsubstantial doubt\b.{0,160}\b(?:continue|continuing) as a going concern\b",
        r"\bunable to continue as a going concern\b",
        r"\bgoing concern (?:opinion|qualification|warning)\b",
        r"\b(?:payment|debt|loan|bond|interest) default\b",
        r"\bdefaulted on\b.{0,100}\b(?:debt|payment|loan|bond|interest)\b",
        r"\b(?:failed|unable) to (?:make|meet)\b.{0,80}\b(?:debt|interest|principal|payment)\b",
        r"\b(?:liquidation|wind[- ]?down|winding up) (?:plan|proceeding|process)\b",
        r"\b(?:is|was|became) insolvent\b",
    )
)
_ANALYST_ACTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:downgrad(?:e|ed|es)|upgrad(?:e|ed|es))\b",
        r"\b(?:raises?|raised|lowers?|lowered|cuts?|cut|boosts?|boosted|trims?|trimmed|reduces?|reduced)\b.{0,35}\bprice target\b",
        r"\bprice target\b.{0,35}\b(?:raised|lowered|cut|boosted|increased|reduced|to)\b",
        r"\bmaintains?\b.{0,35}\b(?:buy|sell|hold|neutral|overweight|underweight|outperform|underperform|equal[- ]weight)\b",
        r"\breiterates?\b.{0,35}\b(?:buy|sell|hold|neutral|overweight|underweight|outperform|underperform|equal[- ]weight)\b",
        r"\binitiates?\b.{0,35}\b(?:coverage|buy|sell|hold|neutral|overweight|underweight|outperform|underperform)\b",
        r"\b(?:analyst|broker|research firm)\b.{0,80}\b(?:raises?|lowers?|cuts?|maintains?|upgrades?|downgrades?|initiates?|reiterates?)\b",
    )
)
_SEASONAL_CURTAILMENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bseasonal(?:ly)?\b.{0,100}\b(?:heat[- ]related )?curtailment\b",
        r"\b(?:heat[- ]related |weather[- ]related )?curtailment\b.{0,120}\b(?:seasonal|typical for this time of year)\b",
        r"\bseasonal heat[- ]related\b.{0,80}\b(?:production|curtailment|disruption)\b",
    )
)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(str(text or "")) if part.strip()]


def _third_party_reference(sentence: str) -> bool:
    lower = sentence.lower()
    return any(marker in lower for marker in _THIRD_PARTY_MARKERS)


def _direct_existential_event(text: str, risk_flags: list[str]) -> bool:
    if "solvency" in {str(flag).lower() for flag in (risk_flags or [])}:
        return True
    for sentence in _sentences(text):
        if not _EXISTENTIAL_TOKEN_RE.search(sentence):
            continue
        # Mentions of a vendor/customer/counterparty bankruptcy are relevant
        # operating context, but they are not evidence that the candidate itself
        # is insolvent. Preserve the sentence only when it explicitly attributes
        # the filing/default to the registrant/company.
        if _third_party_reference(sentence) and not _DIRECT_COMPANY_SUBJECT_RE.search(sentence):
            continue
        if any(pattern.search(sentence) for pattern in _DIRECT_EXISTENTIAL_PATTERNS):
            return True
    return False


def _direct_analyst_action(text: str) -> bool:
    return any(pattern.search(text) for pattern in _ANALYST_ACTION_PATTERNS)


def _seasonal_temporary_event(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SEASONAL_CURTAILMENT_PATTERNS)


def _subject_aware_event_signals(original: Any):
    def event_signals(text: str, risk_flags: list[str], sector_hint: str) -> dict[str, bool]:
        signals = dict(original(text, risk_flags, sector_hint))
        analyst = _direct_analyst_action(text)
        existential = _direct_existential_event(text, risk_flags)
        temporary = bool(signals.get("temporary_operational")) or _seasonal_temporary_event(text)

        signals["analyst_action"] = analyst
        signals["analyst_target_cut"] = bool(signals.get("analyst_target_cut")) and analyst
        signals["analyst_target_raise"] = bool(signals.get("analyst_target_raise")) and analyst
        signals["existential_or_solvency"] = existential
        signals["temporary_operational"] = temporary
        signals["catastrophic_financing"] = bool(signals.get("dilution_or_financing")) and existential

        operating_material = any(
            bool(signals.get(name))
            for name in (
                "guidance_cut",
                "earnings_miss",
                "dilution_or_financing",
                "primary_endpoint_failure",
                "fda_rejection_or_crl",
                "clinical_hold",
                "safety_signal",
                "existential_or_solvency",
                "fraud_or_accounting_credibility",
                "structural_impairment",
                "major_customer_loss",
                "security_breach",
                "legal_or_regulatory",
            )
        )
        signals["analyst_only"] = analyst and not operating_material
        return signals

    return event_signals


def patch_module(module: Any) -> None:
    if getattr(module, "_v36_subject_attribution_installed", False):
        return

    legacy = getattr(module, "_legacy", None)
    original_event_signals = getattr(legacy, "_event_signals", None) or getattr(module, "_event_signals")
    patched_event_signals = _subject_aware_event_signals(original_event_signals)
    module._event_signals = patched_event_signals
    if legacy is not None:
        legacy._event_signals = patched_event_signals

    original_score = module.score_candidate
    original_contract = module.public_scoring_contract

    module.SCORING_MODEL_VERSION = SCORING_MODEL_VERSION
    module.SCORING_CONFIG_VERSION = SCORING_CONFIG_VERSION
    module.CATALYST_SCHEMA_VERSION = CATALYST_SCHEMA_VERSION
    module.CALIBRATION_MODEL_VERSION = None
    module.MODEL_STATUS = "uncalibrated"
    module.SCORING_CONFIG = deepcopy(module.SCORING_CONFIG)
    module.SCORING_CONFIG.setdefault("versions", {}).update(
        {
            "scoring_model_version": SCORING_MODEL_VERSION,
            "scoring_config_version": SCORING_CONFIG_VERSION,
            "catalyst_schema_version": CATALYST_SCHEMA_VERSION,
            "calibration_model_version": None,
        }
    )
    module.SCORING_CONFIG["v3_6_subject_attribution"] = {
        "version": SUBJECT_ATTRIBUTION_VERSION,
        "existential_rule": "direct candidate-subject event language; third-party insolvency references do not create a candidate hard veto",
        "analyst_rule": "explicit rating/target action required; generic analyst boilerplate is ignored",
        "temporary_rule": "explicit seasonal heat/weather curtailment is recognised as potentially temporary",
    }

    def score_candidate(candidate, articles, catalyst_class, risk_flags):
        result = original_score(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        analysis["subject_attribution_version"] = SUBJECT_ATTRIBUTION_VERSION
        analysis["analysis_method"] = "rules_v3_6_subject_attributed_point_in_time_robust_ensemble"
        analysis["subject_attribution_rules"] = deepcopy(module.SCORING_CONFIG["v3_6_subject_attribution"])
        trace = result.setdefault("calculation_trace", {})
        trace["v3_6_subject_attribution"] = {
            "version": SUBJECT_ATTRIBUTION_VERSION,
            "event_signals": deepcopy(analysis.get("event_signals") or {}),
            "rule": "candidate-subject attribution before economic profile, downside scenarios and v3.5 robust ensemble",
        }
        result["scoring_model_version"] = SCORING_MODEL_VERSION
        result["scoring_config_version"] = SCORING_CONFIG_VERSION
        result["catalyst_schema_version"] = CATALYST_SCHEMA_VERSION
        result["calibration_model_version"] = None
        result["model_status"] = "uncalibrated"
        result["explanation"] = (
            f"{result.get('explanation') or ''} Subject-attributed v3.6 event semantics applied."
        ).strip()
        return result

    def public_scoring_contract() -> dict[str, Any]:
        contract = deepcopy(original_contract())
        contract["versions"] = deepcopy(module.SCORING_CONFIG["versions"])
        contract["subject_attribution"] = deepcopy(module.SCORING_CONFIG["v3_6_subject_attribution"])
        contract["ranking_rule"] = (
            "rank by the v3.5 robust lower-quartile ensemble after v3.6 subject-aware causal classification"
        )
        return contract

    module.score_candidate = score_candidate
    module.public_scoring_contract = public_scoring_contract
    module._v36_subject_attribution_installed = True
