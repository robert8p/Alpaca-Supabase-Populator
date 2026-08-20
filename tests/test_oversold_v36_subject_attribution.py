from __future__ import annotations

from types import SimpleNamespace

from app import oversold_scoring
from app.oversold_v2_session_filter import patch_module as patch_v2_session_filter


def signals(text: str, *, sector: str = "consumer") -> dict[str, bool]:
    return oversold_scoring._event_signals(text.lower(), [], sector)


def test_model_version_advances_for_subject_attribution_semantics() -> None:
    assert oversold_scoring.SCORING_MODEL_VERSION == "oversold_reversion_score_v3_6"
    assert oversold_scoring.SCORING_CONFIG_VERSION == "or_score_config_2026_08_20_v8"


def test_vendor_chapter_11_does_not_hard_veto_candidate() -> None:
    text = (
        "Other items included a charge for expected future credit losses related to "
        "vendor receivables due from a vendor that filed petitions for Chapter 11 "
        "bankruptcy protection. The company remained in compliance with its covenants."
    )
    result = signals(text)
    assert result["existential_or_solvency"] is False
    assert result["catastrophic_financing"] is False


def test_direct_candidate_chapter_11_remains_existential() -> None:
    result = signals("The company filed a voluntary petition for Chapter 11 bankruptcy protection today.")
    assert result["existential_or_solvency"] is True


def test_generic_market_analyst_boilerplate_is_not_an_analyst_event() -> None:
    text = (
        "Our results may not meet the expectations of public market analysts or investors "
        "and may vary from period to period."
    )
    result = signals(text)
    assert result["analyst_action"] is False
    assert result["analyst_only"] is False


def test_explicit_rating_and_target_action_remains_analyst_event() -> None:
    result = signals("UBS maintains Neutral on Moderna and raises its price target to $150.")
    assert result["analyst_action"] is True
    assert result["analyst_only"] is True
    assert result["analyst_target_raise"] is True


def test_seasonal_heat_curtailment_is_recognised_as_temporary() -> None:
    text = (
        "July production reflected seasonal heat-related curtailment at the sites, "
        "which is typical for this time of year."
    )
    result = signals(text, sector="industrials")
    assert result["temporary_operational"] is True
    assert result["analyst_only"] is False


def test_day_loser_view_excludes_after_hours_only_qualifiers() -> None:
    module = SimpleNamespace(_is_researchable_equity=lambda row: True)
    patch_v2_session_filter(module)
    after_hours_only = {
        "catalyst_analysis": {
            "price_session_context": {
                "price_session": "after_hours",
                "regular_session_move_pct": -14.4,
                "current_move_pct": -16.1,
                "extended_hours_only": True,
            }
        }
    }
    regular_loser = {
        "catalyst_analysis": {
            "price_session_context": {
                "price_session": "after_hours",
                "regular_session_move_pct": -18.4,
                "current_move_pct": -19.1,
                "extended_hours_only": False,
            }
        }
    }
    assert module._is_researchable_equity(after_hours_only) is False
    assert module._is_researchable_equity(regular_loser) is True
