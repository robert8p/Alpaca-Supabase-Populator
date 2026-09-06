from copy import deepcopy
from datetime import UTC, datetime

import pytest

from app import oversold_scoring
from app.oversold_scoring_v38_evidence_integrity import prepare_evidence, validate_fundamentals

CUTOFF = datetime(2026, 9, 6, 19, 45, tzinfo=UTC)


def candidate():
    return {
        "symbol": "TEST", "name": "Test Issuer", "evidence_cutoff": CUTOFF.isoformat(),
        "latest_trade_ts": CUTOFF.isoformat(), "last_price": 8, "prev_close": 10,
        "drop_pct": -20, "prev_dollar_volume": 20_000_000, "spread_pct": 0.1,
        "history_bars": [], "benchmark_context": {}, "_sec_prefetch_complete": True,
        "raw_snapshot": {"prevDailyBar": {"c": 10, "v": 2_000_000},
                         "dailyBar": {"o": 7, "h": 8.2, "l": 6.5, "c": 8, "v": 6_000_000}},
    }


def article(headline, summary="", **kwargs):
    return {"id": headline, "headline": headline, "summary": summary,
            "source": "Reuters", "created_at": "2026-09-06T12:00:00Z", "symbols": ["TEST"],
            "url": "https://example.test/evidence", **kwargs}


def score(articles, row=None):
    return oversold_scoring.score_candidate(row or candidate(), articles, "U", [])


def test_future_edited_and_undated_articles_never_enter_scorer():
    base = article("TEST analyst raises price target to $40")
    rejected = [dict(base, id="future", created_at="2026-09-07T12:00:00Z"),
                dict(base, id="edited", updated_at="2026-09-06T22:00:00Z"),
                dict(base, id="undated", created_at=None),
                dict(base, id="date-only", created_at="2026-09-06")]
    clean, kept, audit = prepare_evidence(candidate(), rejected)
    assert kept == []
    assert len(audit["excluded_articles"]) == 4
    empty = score([])
    actual = score(rejected)
    assert actual["final_score"] == empty["final_score"]
    assert actual["catalyst_analysis"]["cause_verified"] is False


def test_primary_availability_overrides_earlier_publication_timestamp():
    row = article("Test Issuer reports earnings", is_primary_evidence=True,
                  primary_evidence={"available_at": "2026-09-06T21:00:00Z"})
    _, kept, audit = prepare_evidence(candidate(), [row])
    assert kept == []
    assert audit["excluded_articles"][0]["reason"] == "article_version_after_cutoff"


def test_no_input_snapshot_mutation():
    row = candidate()
    evidence = [article("Test Issuer files Form 8-K — Items 2.02,9.01", is_primary_evidence=True)]
    original = deepcopy((row, evidence))
    score(evidence, row)
    assert (row, evidence) == original


def test_generic_sec_filing_is_not_verified_analyst_catalyst():
    evidence = [article("Test Issuer filed Form 8-K — Items 2.02,9.01",
                        "Our analysts may lower their price target if results differ materially.",
                        is_primary_evidence=True, source="SEC filing", source_kind="sec_filing")]
    result = score(evidence)
    analysis = result["catalyst_analysis"]
    assert analysis["event_signals"]["analyst_only"] is False
    assert analysis["event_signals"]["analyst_action"] is False
    assert analysis["cause_verification_status"] != "VERIFIED"
    assert analysis["reversibility_score"] < 80
    assert result["verdict"] != "INVESTIGATE"
    assert analysis["evidence_integrity"]["context_only_article_ids"]


def test_analyst_reaction_after_results_is_not_analyst_only():
    result = score([article("Test Issuer filed Form 8-K — Items 2.02,9.01", is_primary_evidence=True, source="SEC filing"),
                    article("UBS analyst raises TEST price target to $20", source="Benzinga")])
    analysis = result["catalyst_analysis"]
    assert analysis["event_signals"]["analyst_action"] is True
    assert analysis["event_signals"]["analyst_only"] is False
    assert analysis["reversibility_score"] < 80
    assert analysis["cause_verification_status"] != "VERIFIED"


def test_target_direction_does_not_treat_destination_price_as_raise():
    signals = oversold_scoring._event_signals("UBS analyst cuts TEST price target to $20 from $40.", [], "consumer")
    assert signals["analyst_target_cut"] is True
    assert signals["analyst_target_raise"] is False
    signals = oversold_scoring._event_signals("UBS analyst raises TEST price target to $40 from $20.", [], "consumer")
    assert signals["analyst_target_raise"] is True
    assert signals["analyst_target_cut"] is False


def test_hypothetical_downgrade_is_not_realized_action():
    signals = oversold_scoring._event_signals("Analysts may downgrade our shares or lower our price target if results disappoint.", [], "consumer")
    assert signals["analyst_action"] is False
    assert signals["analyst_only"] is False


def test_vendor_bankruptcy_cannot_bypass_subject_attribution_through_news_flags():
    text = "A vendor filed for Chapter 11 bankruptcy protection. Test Issuer recorded a receivable loss."
    flags = oversold_scoring.direct_news_risk_flags(text)
    assert "solvency" not in flags
    result = score([article("Test Issuer reports vendor receivable charge", text)])
    assert result["catalyst_analysis"]["event_signals"]["existential_or_solvency"] is False
    assert result["hard_veto"] is False


def test_candidate_bankruptcy_still_hard_vetoes_through_full_pipeline():
    result = score([article("Test Issuer files for Chapter 11 bankruptcy protection", "The company filed for bankruptcy protection today.")])
    assert result["catalyst_analysis"]["event_signals"]["existential_or_solvency"] is True
    assert result["hard_veto"] is True
    assert result["verdict"] == "PASS"


@pytest.mark.parametrize("text", [
    "The company warned it may be unable to continue as a going concern.",
    "The issuer cautioned that there may be substantial doubt about its ability to continue as a going concern.",
    "Management disclosed substantial doubt about the company's ability to continue as a going concern.",
])
def test_observed_issuer_warning_survives_uncertain_future_wording(text):
    signals = oversold_scoring._event_signals(text, [], "consumer")
    assert signals["existential_or_solvency"] is True
    result = score([article("Test Issuer provides financial update", text)])
    assert result["catalyst_analysis"]["event_signals"]["existential_or_solvency"] is True
    assert result["hard_veto"] is True
    assert result["verdict"] == "PASS"


@pytest.mark.parametrize("text", [
    "The company may warn that it is unable to continue as a going concern in a future period.",
    "The company warned that its vendor may be unable to continue as a going concern.",
    "The company disclosed no substantial doubt about its ability to continue as a going concern.",
    "The company concluded it has the ability to continue as a going concern.",
    "If losses persist we might be unable to continue as a going concern.",
])
def test_hypothetical_third_party_and_negated_warnings_do_not_become_issuer_events(text):
    result = score([article("Test Issuer publishes disclosure", text)])
    assert result["catalyst_analysis"]["event_signals"]["existential_or_solvency"] is False
    assert result["hard_veto"] is False


@pytest.mark.parametrize("available", [None, "2026-09-07", "2026-09-06", "2026-09-06T21:00:00Z", "bad-date"])
def test_unavailable_fundamentals_cannot_support_survivability(available):
    facts = {"source": "SEC", "available_from": available, "report_period_end": "2026-06-30",
             "metric_coverage_count": 12, "cash_to_assets": .5, "liabilities_to_assets": .2,
             "equity_to_assets": .8, "net_margin": .3, "cash_runway_months": 60}
    clean, audit = validate_fundamentals(facts, CUTOFF)
    assert clean is None
    assert audit["status"] == "REJECTED"
    row = candidate()
    row["fundamentals"] = facts
    result = score([], row)
    assert result["point_in_time_enrichment"]["fundamentals"] is None
    assert result["catalyst_analysis"]["fundamental_evidence_state"] == "UNAVAILABLE"


def test_actual_earlier_financial_timestamp_is_valid_and_age_recomputed():
    facts = {"source": "SEC", "available_from": "2026-09-06T14:00:00Z", "age_calendar_days": -99}
    clean, audit = validate_fundamentals(facts, CUTOFF)
    assert audit["status"] == "VERIFIED_POINT_IN_TIME"
    assert clean["age_calendar_days"] == 0
    assert facts["age_calendar_days"] == -99


def test_new_version_does_not_claim_calibrated_probability():
    result = score([])
    assert result["scoring_model_version"] == "oversold_reversion_score_v3_8"
    assert result["model_status"] == "uncalibrated"
    assert result["calibration_model_version"] is None
    assert "not survival probability" in result["catalyst_analysis"]["score_semantics"]["survivability"]
