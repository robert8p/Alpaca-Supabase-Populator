from __future__ import annotations

from app import oversold_scoring
from app.oversold_scoring_v37_local_attribution import direct_candidate_existential_event


def signals(text: str) -> dict[str, bool]:
    return oversold_scoring._event_signals(text.lower(), [], "consumer")


def test_model_version_advances_for_local_clause_attribution() -> None:
    assert oversold_scoring.SCORING_MODEL_VERSION == "oversold_reversion_score_v3_8"
    assert oversold_scoring.SCORING_CONFIG_VERSION == "or_score_config_2026_09_06_v10"


def test_realistic_long_aap_excerpt_does_not_attribute_vendor_bankruptcy_to_candidate() -> None:
    text = (
        "The Company reaffirmed full year sales, adjusted operating income margin and free cash flow guidance. "
        "The Company repurchased and retired approximately $30 million of principal outstanding debt and was "
        "in compliance with its covenants related to the ABL Facility in all periods presented. Other items "
        "included a non-cash charge for expected future credit losses related to vendor receivables due from "
        "a vendor that filed voluntary petitions for Chapter 11 bankruptcy protection. The charge is excluded "
        "to provide a clearer understanding of the Company's ongoing non-GAAP tax rate and earnings."
    )
    assert direct_candidate_existential_event(text, []) is False
    result = signals(text)
    assert result["existential_or_solvency"] is False
    assert result["catastrophic_financing"] is False


def test_flattened_excerpt_with_distant_company_reference_still_rejects_third_party_event() -> None:
    text = (
        "All statements about the Company strategic initiatives revenue earnings cash flow liquidity debt capital "
        "structure operational plans and objectives are forward looking and subject to risk. "
        + ("ordinary disclosure text " * 20)
        + "expected future credit losses on vendor receivables due from a vendor that filed petitions for "
        "Chapter 11 bankruptcy protection on September 28 2025."
    )
    assert direct_candidate_existential_event(text, []) is False


def test_direct_candidate_chapter_11_is_still_existential() -> None:
    text = "The Company filed a voluntary petition for Chapter 11 bankruptcy protection today."
    assert direct_candidate_existential_event(text, []) is True
    assert signals(text)["existential_or_solvency"] is True


def test_direct_headline_style_bankruptcy_filing_is_still_detected() -> None:
    text = "Issuer files for Chapter 11 bankruptcy protection after failing to secure financing."
    assert direct_candidate_existential_event(text, []) is True


def test_hypothetical_or_negated_default_is_not_an_event() -> None:
    hypothetical = "If liquidity declines, the company could face a debt default in a future period."
    compliant = "The Company was in compliance with all debt covenants and no event of default occurred."
    assert direct_candidate_existential_event(hypothetical, []) is False
    assert direct_candidate_existential_event(compliant, []) is False


def test_explicit_going_concern_warning_remains_existential() -> None:
    text = "Management concluded there is substantial doubt about the Company's ability to continue as a going concern."
    assert direct_candidate_existential_event(text, []) is True


def test_high_confidence_fundamental_solvency_flag_remains_authoritative() -> None:
    assert direct_candidate_existential_event("No text event was retained.", ["solvency"]) is True
