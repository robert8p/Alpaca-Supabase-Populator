'use strict';

const assert = require('node:assert/strict');
const prompt = require('../static_intraday/prompt.js');

const scan = {
  status: 'completed',
  evidence_cutoff: '2026-08-20T17:41:57Z',
  horizon_end: '2026-08-20T19:41:57Z',
};
const audit = {
  model_version: 'ip-reliability-v3.0',
  status: 'RESEARCH_ONLY',
  holdout_start: '2026-06-05',
  holdout_end: '2026-08-03',
  registered_robust_candidates: 23,
  robust_candidates_passed: 0,
  large_sample_generic_rules_passed: 0,
  findings: { total_point_in_time_states: 551445, trading_days: 270 },
};
const tracking = { total_candidates_tracked: 50, horizon_matured: 12 };
const candidates = Array.from({ length: 10 }, (_, index) => ({
  rank: index + 1,
  symbol: `TEST${index + 1}`,
  name: `Test company ${index + 1}`,
  direction: index % 2 ? 'SHORT' : 'LONG',
  setup_type: 'CONTINUATION',
  profitability_score: 60 - index,
  last_price: 100 + index,
  day_move_pct: 1.2,
  spread_bps: 2,
  cost_estimate_bps: 4,
  move_capacity_120m_pct: 1.2,
  return_5m_pct: 0.2,
  return_15m_pct: 0.4,
  return_30m_pct: 0.7,
  return_60m_pct: 1.0,
  relative_return_15m_pct: 0.3,
  prev_dollar_volume: 500_000_000,
  current_dollar_volume: 100_000_000,
  relative_volume_pace: 2,
  opportunity_score: 80,
  initial_view: 'ANALYSE ONLY',
  rationale: 'Research hypothesis for independent catalyst review only.',
  evidence: {
    edge_to_cost_ratio: 30,
    bars_used: 120,
    data_quality_score: 98,
    directional_evidence_score: 78,
    movement_opportunity_score: 80,
    execution_quality_score: 92,
    reliability_label: 'NO VALIDATED EDGE',
    trade_gate: 'BLOCKED',
    historical_setup_status: 'FAILED_EXTERNAL_HOLDOUT',
    historical_holdout_n: 6311,
    historical_holdout_hit_rate: 0.4204,
    historical_holdout_mean_net_pct: -0.134,
    reference_price_definition: 'current SIP ask',
    observed_trade_price: 100 + index,
  },
}));

const compact = prompt.buildCompactPrompt(scan, candidates, audit, tracking);
const full = prompt.buildFullPrompt(scan, candidates, audit, tracking);
const target = new URL(prompt.chatGptUrl(compact));

assert.ok(compact.length <= prompt.COMPACT_LIMIT, 'compact prompt exceeds prefill budget');
assert.equal(target.hostname, 'chatgpt.com');
assert.ok(target.searchParams.has('prompt'), 'ChatGPT URL has no populated prompt parameter');
assert.ok(target.searchParams.get('prompt').includes('TEST1'));
assert.ok(target.searchParams.get('prompt').includes('TEST10'));
assert.ok(target.searchParams.get('prompt').includes('trade gate is blocked'));
assert.equal(target.searchParams.has('q'), false, 'legacy q parameter should not be used');
assert.ok(full.includes('TEST10'));
assert.ok(full.includes('Shared evidence cutoff:'));
assert.ok(full.includes('0/23 registered candidates passed'));
assert.ok(full.includes('ANALYSIS PRIORITY only'));
assert.ok(full.includes('TRADE verdict may not be based on the app score'));
assert.ok(full.includes('Prospective calibration coverage: 50 ranked candidates tracked; 12 have a matured two-hour outcome.'));
assert.throws(() => prompt.chatGptUrl(''), /empty/i);

console.log(`Reliability-aware prompt verified: compact=${compact.length}, full=${full.length}, URL=${target.toString().length}`);
