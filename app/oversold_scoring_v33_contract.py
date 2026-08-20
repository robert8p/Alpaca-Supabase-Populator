from __future__ import annotations

"""Current public contract for the purpose-aligned v3.3 opportunity model."""

from copy import deepcopy
from typing import Any


CURRENT_INVESTIGATE_GATES: dict[str, Any] = {
    "minimum_opportunity_score": 72.0,
    "minimum_evidence_confidence": 65.0,
    "minimum_overreaction_quality": 60.0,
    "minimum_survivability": 55.0,
    "minimum_three_session_fit": 55.0,
    "maximum_damage_risk": 60.0,
    "maximum_tail_risk": 60.0,
    "minimum_previous_dollar_volume": 2_000_000.0,
    "maximum_spread_pct": 3.0,
    "cause_requirement": "VERIFIED or PARTIALLY_VERIFIED with confidence at least 75",
    "critical_fundamentals_required": True,
    "regular_session_confirmation_required": True,
    "capital_distress_allowed": False,
    "material_dilution_allowed": False,
    "dominant_post_spike_normalisation_allowed": False,
}


def patch_module(module: Any) -> None:
    if getattr(module, "_v33_public_contract_installed", False):
        return
    original = module.public_scoring_contract

    def public_scoring_contract() -> dict[str, Any]:
        contract = deepcopy(original())
        architecture = deepcopy(module.SCORING_CONFIG["v3_3"])

        # Retain the still-used technical subfeature definitions, but move the old
        # v3.2 linear top-level semantics out of the current-contract namespace.
        legacy_feature_context = {
            "setup_feature_weights": contract.get("setup_feature_weights"),
            "confirmation_feature_weights": contract.get("confirmation_feature_weights"),
            "economic_damage_input_bands": contract.get("damage"),
            "cause_evidence_caps": contract.get("cause_verification"),
            "post_spike_detection": contract.get("post_spike"),
            "financing_classification": contract.get("financing"),
        }

        contract.update(
            {
                "weights": deepcopy(architecture["weights"]),
                "confidence": {
                    "role": "assessment reliability, separate from opportunity quality",
                    "score_multiplier": architecture["confidence_multiplier"],
                    "minimum_multiplier": 0.35,
                    "maximum_multiplier": 1.0,
                    "rule": "missing or weak evidence can only reduce the score; it never raises a candidate",
                },
                "investigate_gates": deepcopy(CURRENT_INVESTIGATE_GATES),
                "score_semantics": {
                    "name": "Opportunity Score",
                    "range": "0-100",
                    "calibrated_probability": False,
                    "aggregation": architecture["aggregation"],
                    "meaning": (
                        "Expected quality of a three-session reversion opportunity after "
                        "survivability, evidence and asymmetric-loss controls."
                    ),
                },
                "risk_treatment": {
                    "tail_risk": "asymmetric penalty plus hard ceilings",
                    "structural_damage": "score ceiling or PASS rather than a small linear deduction",
                    "capital_distress": "PASS gate",
                    "material_dilution": "INVESTIGATE gate failure",
                    "unknown_cause": "confidence/cause cap; absence of evidence is never bullish",
                },
                "legacy_feature_context": legacy_feature_context,
            }
        )
        # These names described the superseded v3.2 final-score architecture and
        # were materially misleading when left beside the v3.3 contract.
        contract.pop("cause_unknown", None)
        return contract

    module.public_scoring_contract = public_scoring_contract
    module._v33_public_contract_installed = True
