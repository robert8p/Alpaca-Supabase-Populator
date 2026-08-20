'use strict';

const assert = require('node:assert/strict');
const prompt = require('../static_intraday/prompt.js');

const scan = {
  status: 'completed',
  evidence_cutoff: '2026-08-20T17:41:57Z',
  horizon_end: '2026-08-20T19:41:57Z',
};
const candidates = Array.from({ length: 10 }, (_, index) => ({
  rank: index + 1,
  symbol: `TEST${index + 1}`,
  name: `Test company ${index + 1}`,
  direction: index % 2 ? 'SHORT' : 'LONG',
  setup_type: 'CONTINUATION',
  profitability_score: 80 - index,
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
  liquidity_score: 90,
  opportunity_score: 80,
  directional_score: 79,
  confirmation_score: 76,
  execution_score: 92,
  initial_view: 'INVESTIGATE',
  rationale: 'Strong orderly trend with robust liquidity and no late chase.',
  evidence: { edge_to_cost_ratio: 30, bars_used: 120, data_quality_score: 98 },
}));

const compact = prompt.buildCompactPrompt(scan, candidates);
const full = prompt.buildFullPrompt(scan, candidates);
const target = new URL(prompt.chatGptUrl(compact));

assert.ok(compact.length <= prompt.COMPACT_LIMIT, 'compact prompt exceeds prefill budget');
assert.equal(target.hostname, 'chatgpt.com');
assert.ok(target.searchParams.has('q'), 'ChatGPT URL has no populated q parameter');
assert.ok(target.searchParams.get('q').includes('TEST1'));
assert.ok(target.searchParams.get('q').includes('TEST10'));
assert.ok(full.includes('TEST10'));
assert.ok(full.includes('Shared evidence cutoff:'));
assert.throws(() => prompt.chatGptUrl(''), /empty/i);

console.log(`Prompt handoff verified: compact=${compact.length}, full=${full.length}, URL=${target.toString().length}`);
