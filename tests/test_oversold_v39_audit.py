from copy import deepcopy
from itertools import permutations
from pathlib import Path
import json
from types import SimpleNamespace

import pytest
from app import oversold_scoring
from app.oversold_scoring_v35 import SCENARIO_NAMES, WEIGHT_SETS
from app.oversold_scoring_v39 import (ALIASES, audited_ensemble, execution_audit,
    event_context, number, provenance_clusters, quantile)
from test_oversold_v35_robustness import candidate, strong_evidence, relevance_for


def result_fixture(cap=100, friction=.2, conf=90, values=None):
    values = values or dict(overreaction=95, reversibility=88, survivability=90,
                           three_session_fit=90, confirmation=75, technical_exhaustion=30)
    scenarios = {name: {"values": {key: max(0, value-i) for key, value in values.items()}, "confidence": conf, "tail": 30}
                 for i, name in enumerate(SCENARIO_NAMES)}
    return {"damage_risk": 10, "hard_veto": False, "catalyst_analysis": {
        "cause_verification_status": "VERIFIED", "fundamental_trace": {"available": True},
        "robustness_assessment": {"robust_evidence_confidence": conf, "final_score_cap": cap},
        "reliability_assessment": {"external_cap": 100, "scenarios": scenarios,
            "execution_friction": {"estimated_round_trip_friction_pct": friction}}}}


PURE = SimpleNamespace(_geometric=oversold_scoring._geometric,
                       _cap_score=lambda value, **kwargs: (value, 100, []))


@pytest.mark.parametrize('cap', [0, 25, 60, 100])
@pytest.mark.parametrize('friction', [0, .2, 1.97, 10.99, 121.80])
def test_all_displayed_percentiles_share_cost_cap_basis(cap, friction):
    data = audited_ensemble(PURE, result_fixture(cap, friction))
    assert data['ensemble_minimum'] <= data['ensemble_p10'] <= data['robust_lower_score'] <= data['ensemble_median'] <= data['ensemble_p75'] <= data['ensemble_maximum']
    assert data['robust_lower_score'] == round(quantile([row['score'] for row in data['members']], .25), 1)
    assert data['cost_stress_q25']['2x'] <= data['cost_stress_q25']['1.5x'] <= data['cost_stress_q25']['1x']


def test_capped_zero_does_not_report_perfect_stability():
    result = audited_ensemble(PURE, result_fixture(cap=0))
    assert result['weight_stability_score'] is None
    assert result['weight_sensitivity_status'] == 'CENSORED_BY_FLOOR_OR_CAP'
    assert result['base_weight_range'] > 0
    assert result['maximum_component_dependency'] > 0


def test_zero_confidence_is_not_replaced_by_positive_fallback():
    zero, high = result_fixture(conf=0), result_fixture(conf=90)
    assert audited_ensemble(PURE, zero)['ensemble_median'] < audited_ensemble(PURE, high)['ensemble_median']
    assert number(0, 100) == 0
    assert number(float('nan'), None) is None
    assert number(True, None) is None


def test_missing_scenario_never_gets_singleton_stability():
    row = result_fixture()
    del row['catalyst_analysis']['reliability_assessment']['scenarios']['joint_downside']
    result = audited_ensemble(PURE, row)
    assert result['complete'] is False
    assert result['weight_stability_score'] is None
    assert result['scenario_policy_pass_rate'] is None


def test_stress_fraction_is_a_real_numerator_and_denominator():
    result = audited_ensemble(PURE, result_fixture())
    assert result['scenario_policy_denominator'] == 35
    assert result['scenario_policy_pass_count'] == sum(row['scenario_policy_pass'] for row in result['members'])
    assert result['scenario_policy_pass_rate'] == result['scenario_policy_pass_count']/35


@pytest.mark.parametrize('spread', [None, -1, float('inf'), 121.8])
def test_bad_execution_inputs_are_not_free_or_tradeable(spread):
    row = candidate(); row['spread_pct'] = spread
    result = execution_audit(row, {'estimated_round_trip_friction_pct': 121.8 if spread == 121.8 else .5})
    assert result['scoring_inputs_valid'] is False
    assert result['live_execution_verified'] is False


def test_future_crossed_stale_and_unit_mismatched_quotes():
    row = candidate()
    row['raw_snapshot']['latestQuote'] = {'bp': 10, 'ap': 9, 't': row['evidence_cutoff']}
    assert execution_audit(row, {'estimated_round_trip_friction_pct': .5})['status'] == 'INVALID'
    row['raw_snapshot']['latestQuote'] = {'bp': 10, 'ap': 10.02, 't': '2026-08-21T19:00:00Z'}
    assert 'quote_after_cutoff' in execution_audit(row, {'estimated_round_trip_friction_pct': .5})['reasons']
    row['raw_snapshot']['latestQuote']['t'] = '2026-08-19T19:00:00Z'
    assert execution_audit(row, {'estimated_round_trip_friction_pct': .5})['status'] == 'STALE_QUOTE'
    row['raw_snapshot']['latestQuote']['t'] = row['evidence_cutoff']
    row['spread_pct'] = 2
    assert 'spread_units_or_quote_mismatch' in execution_audit(row, {'estimated_round_trip_friction_pct': .5})['reasons']


def test_common_declared_roots_are_transitive_and_order_independent():
    rows = strong_evidence()
    rows[0]['provenance_root_id'] = 'shared-root'
    rows[1]['provenance_root_id'] = 'shared-root'
    rows[1]['origin_url'] = 'common-origin'
    rows[2]['origin_url'] = 'common-origin'
    for perm in permutations(rows):
        result = provenance_clusters(list(perm), relevance_for(rows))
        assert result['causal_cluster_count'] == 1
        assert result['single_cluster_dependency_risk'] is None


def test_current_positive_control_is_not_an_always_reject_system():
    result = oversold_scoring.score_candidate(candidate(), strong_evidence(), 'B', [])
    assert result['verdict'] == 'INVESTIGATE'
    assert all(result['catalyst_analysis']['eligibility_gates'].values())
    assert result['catalyst_analysis']['allocation_status'] == 'INDEPENDENT_REVIEW_REQUIRED'


def test_source_removal_actually_reruns_and_does_not_change_inputs(monkeypatch):
    row, articles = candidate(), strong_evidence()
    original = deepcopy((row, articles))
    # Any extra enrichment/network request is a test failure.
    import app.oversold_live_enrichment as enrichment
    monkeypatch.setattr(enrichment, '_fetch_history', lambda *a, **k: pytest.fail('unexpected network'))
    monkeypatch.setattr(enrichment, '_fetch_intraday_evidence', lambda *a, **k: pytest.fail('unexpected network'))
    result = oversold_scoring.score_candidate(row, articles, 'B', [])
    removal = result['catalyst_analysis']['source_removal']
    assert removal['status'] == 'COMPLETE'
    assert removal['baseline_reproduced'] is True
    assert removal['replayed_clusters'] == len(removal['cases']) >= 2
    assert removal['worst_score'] == min(case['score'] for case in removal['cases'])
    assert len(removal['frozen_input_hash']) == 64
    assert (row, articles) == original
    assert not set(ALIASES) & set(result['catalyst_analysis']['failed_eligibility_gates'])
    assert 'stress_gate_pass_rate' not in result['catalyst_analysis']['eligibility_gates']


def test_identical_syndication_cannot_improve_current_score():
    articles = strong_evidence()
    first = oversold_scoring.score_candidate(candidate(), articles, 'B', [])
    duplicates = [dict(articles[2], id='copy-'+str(i)) for i in range(8)]
    second = oversold_scoring.score_candidate(candidate(), articles+duplicates, 'B', [])
    assert first['final_score'] == second['final_score']
    assert first['verdict'] == second['verdict']
    assert second['catalyst_analysis']['evidence_integrity']['duplicate_articles']


def test_unknown_event_timing_and_financial_impact_are_not_inferred_from_accounts():
    context = event_context(candidate(), strong_evidence(), 'earnings')
    assert context['timing_status'] == 'UNKNOWN'
    assert context['event_financial_status'] == 'NOT_QUANTIFIED'
    row = candidate(); row.update(event_timestamp='2026-08-21T19:00:00Z', selloff_onset_timestamp=row['evidence_cutoff'])
    assert event_context(row, [], 'earnings')['timing_status'] == 'CONTRADICTORY_TIMESTAMPS'


def test_prompt_contains_critical_cutoff_and_allocation_constraints():
    root = Path(__file__).resolve().parents[1]
    rules = (root/'app/static/oversold_audit_rules.txt').read_text()
    assert 'Missing cutoff/source version' in rules
    assert 'dated source required' in rules
    assert '3 EXCHANGE trading sessions' in rules
    assert 'No Buy-or-better robust INVESTIGATE candidates; no allocation.' in rules
    assert 'Unknown mandatory facts imply 0%' in rules
    assert 'not 35 independent observations' in rules
    for script in ['oversold_chatgpt_v35.js', '../oversold_v2.py']:
        assert 'oversold_audit_rules.txt' in (root/'app/static'/script).read_text()


def test_json_output_contains_no_nonfinite_numbers():
    result = oversold_scoring.score_candidate(candidate(), strong_evidence(), 'B', [])
    json.dumps(result['catalyst_analysis']['robustness_assessment'], allow_nan=False, default=str)


def test_browser_prompt_builder_preserves_cutoffs_and_unknowns():
    import subprocess
    script = r'''
const fs=require('fs'), vm=require('vm');
const rules=fs.readFileSync('app/static/oversold_audit_rules.txt','utf8');
const context={window:{},document:{getElementById:()=>null},fetch:async()=>({ok:true,text:async()=>rules}),setTimeout:()=>{},console};
vm.createContext(context);
vm.runInContext(fs.readFileSync('app/static/oversold_chatgpt_v35.js','utf8'),context);
(async()=>{
  await Promise.resolve();await Promise.resolve();await Promise.resolve();await Promise.resolve();
  const output=context.window.buildOversoldComparisonPrompt([{symbol:'TEST',evidence_cutoff:'2026-09-04T20:00:00Z',scoring_model_version:'v3_9'}, {symbol:'MISS'}]);
  for(const required of ['2026-09-04T20:00:00Z','cutoff=MISSING','NOT VERIFIED IN EXPORT','No Buy-or-better robust INVESTIGATE candidates; no allocation.']){
    if(!output.includes(required))throw Error('missing '+required);
  }
  console.log('browser-prompt-ok');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    completed = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert 'browser-prompt-ok' in completed.stdout


def test_authoritative_single_root_does_not_claim_false_independence():
    rows = strong_evidence()
    for row in rows:
        row['provenance_root_id'] = 'one-shared-release'
    result = oversold_scoring.score_candidate(candidate(), rows, 'B', [])
    assert result['verdict'] != 'INVESTIGATE'
    assert result['catalyst_analysis']['robustness_assessment']['declared_origin_provenance']['primary_fact_status'] == 'PRIMARY_PRESENT'
