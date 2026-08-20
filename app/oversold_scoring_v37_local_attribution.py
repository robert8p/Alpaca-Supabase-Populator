from __future__ import annotations

"""Oversold Reversion Score v3.7: local-clause causal attribution.

The v3.6 subject-aware model correctly removed generic analyst boilerplate but
live acceptance testing exposed one remaining failure mode: flattened SEC text
can place an unrelated ``the Company`` reference hundreds of characters from a
vendor bankruptcy clause. A broad sentence-level rule can then attribute the
vendor's Chapter 11 filing to the candidate.

This additive layer retains the entire v3.5 robust ensemble and v3.6 analyst /
seasonality semantics, but replaces company-level existential detection with
locally asserted event clauses. Third-party, hypothetical and negated clauses
cannot create a bankruptcy/solvency hard veto.
"""

from copy import deepcopy
import re
from typing import Any

SCORING_MODEL_VERSION = "oversold_reversion_score_v3_7"
SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v9"
CATALYST_SCHEMA_VERSION = "catalyst_schema_v3_7"
LOCAL_ATTRIBUTION_VERSION = "local_clause_attribution_v1"

_THIRD_PARTY_ENTITY = (
    r"(?:vendor|supplier|customer|tenant|borrower|counterparty|portfolio company|"
    r"investee|distributor|franchisee|independently[- ]owned store|service provider|"
    r"joint venture partner|licensee|lessee|guarant(?:ee|or) customer)"
)
_EXISTENTIAL_EVENT = (
    r"(?:chapter\s+(?:7|11)|bankruptcy(?: protection| proceeding| filing)?|"
    r"insolvenc(?:y|e proceedings?)|liquidation|wind[- ]?down|winding up|"
    r"going concern|debt default|payment default|loan default|covenant default)"
)

_THIRD_PARTY_BEFORE_EVENT_RE = re.compile(
    rf"\b{_THIRD_PARTY_ENTITY}\b.{{0,220}}\b(?:filed?|files?|petition(?:ed|s)?|"
    rf"entered|commenced|defaulted|faces?|seeks?|sought|{_EXISTENTIAL_EVENT})\b",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_BEFORE_THIRD_PARTY_RE = re.compile(
    rf"\b{_EXISTENTIAL_EVENT}\b.{{0,140}}\b{_THIRD_PARTY_ENTITY}\b",
    re.IGNORECASE | re.DOTALL,
)
_NEGATED_EVENT_RE = re.compile(
    rf"\b(?:no|not|never|without|neither)\b.{{0,55}}\b{_EXISTENTIAL_EVENT}\b|"
    rf"\b{_EXISTENTIAL_EVENT}\b.{{0,55}}\b(?:did not occur|has not occurred|"
    r"was not triggered|does not exist|none)\b",
    re.IGNORECASE | re.DOTALL,
)
_HYPOTHETICAL_EVENT_RE = re.compile(
    rf"\b(?:may|might|could|would|if|unless|potential(?:ly)?|possible|risk of|"
    rf"in the event of|upon an event of|subject to)\b.{{0,90}}\b{_EXISTENTIAL_EVENT}\b",
    re.IGNORECASE | re.DOTALL,
)
_COMPLIANCE_RE = re.compile(
    r"\b(?:was|were|remained|is|are) in compliance with\b.{0,120}\b(?:covenants?|facility|debt|agreement)\b|"
    r"\bno (?:event of )?default\b",
    re.IGNORECASE | re.DOTALL,
)

_DIRECT_BANKRUPTCY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:the company|the registrant|the issuer|we|our company|our business)\b.{0,80}"
        r"\b(?:filed?|files?|has filed|petitioned|commenced|entered|seeks?|sought)\b.{0,100}"
        r"\b(?:a voluntary petition|chapter\s+(?:7|11)|bankruptcy(?: protection| proceedings?)?|"
        r"insolvency proceedings?|liquidation|wind[- ]?down)\b",
        r"\b(?:filed?|files?|has filed|petitioned|commenced|entered|seeks?|sought)\b.{0,90}"
        r"\b(?:a voluntary petition|chapter\s+(?:7|11)|bankruptcy(?: protection| proceedings?)?|"
        r"insolvency proceedings?|liquidation|wind[- ]?down)\b",
        r"\b(?:approved|adopted|commenced|initiated)\b.{0,60}\b(?:a )?(?:plan|process|proceeding) of "
        r"(?:liquidation|wind[- ]?down|winding up)\b",
    )
)
_DIRECT_GOING_CONCERN_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bsubstantial doubt\b.{0,180}\b(?:continue|continuing) as a going concern\b",
        r"\bunable to continue as a going concern\b",
        r"\bgoing concern (?:opinion|qualification|warning)\b",
        r"\b(?:auditor|independent registered public accounting firm)\b.{0,120}\bgoing concern\b",
    )
)
_DIRECT_DEFAULT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:the company|the registrant|the issuer|we|our company|our business)\b.{0,90}"
        r"\b(?:defaulted on|is in default|was in default|received (?:a )?notice of default|"
        r"failed to (?:make|meet)|was unable to (?:make|meet))\b.{0,100}"
        r"\b(?:debt|loan|bond|note|interest|principal|payment|covenant)\b",
        r"\b(?:defaulted on|received (?:a )?notice of default|failed to (?:make|meet)|"
        r"unable to (?:make|meet))\b.{0,100}\b(?:debt|loan|bond|note|interest|principal|payment)\b",
        r"\b(?:is|was|became) insolvent\b",
    )
)


def _window(text: str, start: int, end: int, *, before: int = 260, after: int = 160) -> str:
    return text[max(0, start - before) : min(len(text), end + after)]


def _third_party_controls(window: str) -> bool:
    return bool(_THIRD_PARTY_BEFORE_EVENT_RE.search(window) or _EVENT_BEFORE_THIRD_PARTY_RE.search(window))


def _invalid_event_context(window: str) -> bool:
    return bool(
        _third_party_controls(window)
        or _NEGATED_EVENT_RE.search(window)
        or _HYPOTHETICAL_EVENT_RE.search(window)
        or _COMPLIANCE_RE.search(window)
    )


def direct_candidate_existential_event(text: str, risk_flags: list[str] | None = None) -> bool:
    """Return true only for a locally asserted candidate solvency event.

    A high-confidence filing-derived ``solvency`` flag remains authoritative.
    Text evidence must otherwise match a direct action/assertion whose local
    clause is neither third-party, hypothetical, negated nor compliance
    boilerplate.
    """
    if "solvency" in {str(flag).strip().lower() for flag in (risk_flags or [])}:
        return True

    source = str(text or "")
    for pattern in (*_DIRECT_BANKRUPTCY_PATTERNS, *_DIRECT_GOING_CONCERN_PATTERNS, *_DIRECT_DEFAULT_PATTERNS):
        for match in pattern.finditer(source):
            local = _window(source, match.start(), match.end())
            if not _invalid_event_context(local):
                return True
    return False


def _local_event_signals(original: Any):
    def event_signals(text: str, risk_flags: list[str], sector_hint: str) -> dict[str, bool]:
        signals = dict(original(text, risk_flags, sector_hint))
        existential = direct_candidate_existential_event(text, risk_flags)
        signals["existential_or_solvency"] = existential
        signals["catastrophic_financing"] = bool(signals.get("dilution_or_financing")) and existential
        return signals

    return event_signals


def patch_module(module: Any) -> None:
    if getattr(module, "_v37_local_attribution_installed", False):
        return

    legacy = getattr(module, "_legacy", None)
    original_event_signals = getattr(legacy, "_event_signals", None) or getattr(module, "_event_signals")
    patched_event_signals = _local_event_signals(original_event_signals)
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
    module.SCORING_CONFIG["v3_7_local_attribution"] = {
        "version": LOCAL_ATTRIBUTION_VERSION,
        "rule": "existential hard veto requires a locally asserted candidate event",
        "excluded_contexts": ["third_party", "hypothetical", "negated", "compliance_boilerplate"],
        "preserved_engine": "v3.5 robust ensemble plus v3.6 analyst and seasonal-event semantics",
    }

    def score_candidate(candidate, articles, catalyst_class, risk_flags):
        result = original_score(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        analysis["local_attribution_version"] = LOCAL_ATTRIBUTION_VERSION
        analysis["analysis_method"] = "rules_v3_7_local_clause_point_in_time_robust_ensemble"
        analysis["local_attribution_rules"] = deepcopy(module.SCORING_CONFIG["v3_7_local_attribution"])
        trace = result.setdefault("calculation_trace", {})
        trace["v3_7_local_attribution"] = {
            "version": LOCAL_ATTRIBUTION_VERSION,
            "event_signals": deepcopy(analysis.get("event_signals") or {}),
            "rule": "local candidate-subject assertion precedes economic profile, scenarios and robust ensemble",
        }
        result["scoring_model_version"] = SCORING_MODEL_VERSION
        result["scoring_config_version"] = SCORING_CONFIG_VERSION
        result["catalyst_schema_version"] = CATALYST_SCHEMA_VERSION
        result["calibration_model_version"] = None
        result["model_status"] = "uncalibrated"
        result["explanation"] = (
            f"{result.get('explanation') or ''} Local-clause v3.7 attribution applied."
        ).strip()
        return result

    def public_scoring_contract() -> dict[str, Any]:
        contract = deepcopy(original_contract())
        contract["versions"] = deepcopy(module.SCORING_CONFIG["versions"])
        contract["local_attribution"] = deepcopy(module.SCORING_CONFIG["v3_7_local_attribution"])
        contract["ranking_rule"] = (
            "rank by the v3.5 robust lower-quartile ensemble after v3.7 local-clause causal attribution"
        )
        return contract

    module.score_candidate = score_candidate
    module.public_scoring_contract = public_scoring_contract
    module._v37_local_attribution_installed = True
