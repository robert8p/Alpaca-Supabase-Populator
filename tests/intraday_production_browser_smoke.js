'use strict';

const { chromium } = require('playwright');
const assert = (condition, message) => { if (!condition) throw new Error(message); };

(async () => {
  const site = process.env.SITE_URL || 'https://alpaca-intraday-profitability-app.onrender.com';
  const api = process.env.API_URL || 'https://mnmkxjirpwbptdnvjmpw.supabase.co/functions/v1/intraday-profitability-api';
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1680, height: 1100 } });
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: site });

  const audit = {
    model_version: 'ip-reliability-v3.0',
    active: true,
    status: 'RESEARCH_ONLY',
    holdout_start: '2026-06-05',
    holdout_end: '2026-08-03',
    registered_robust_candidates: 23,
    robust_candidates_passed: 0,
    large_sample_generic_rules_passed: 0,
    findings: { total_point_in_time_states: 551445, trading_days: 270 },
    summary: 'No generic long/short continuation or reversal family demonstrated a robust positive net two-hour edge.',
  };
  const trackingSummary = {
    total_candidates_tracked: 50,
    user_selected: 0,
    horizon_matured: 12,
    close_matured: 10,
    entry_observed: 50,
    tracking_errors: 0,
    population: 'all persisted ranked candidates',
  };
  const candidates = Array.from({ length: 10 }, (_, index) => ({
    id: 1001 + index,
    rank: index + 1,
    symbol: `SMOKE${index + 1}`,
    name: `Reliability browser smoke candidate ${index + 1}`,
    exchange: index % 2 ? 'NYSE' : 'NASDAQ',
    direction: index % 3 ? 'SHORT' : 'LONG',
    setup_type: 'CONTINUATION',
    profitability_score: 60 - index,
    initial_view: index < 3 ? 'ANALYSE ONLY' : 'LOW PRIORITY',
    last_price: 100.02 + index,
    bid: 99.99 + index,
    ask: 100.02 + index,
    spread_bps: 3 + index / 10,
    prev_close: 99 + index,
    day_move_pct: index % 2 ? -1.2 : 1.1,
    prev_dollar_volume: 500000000 + index * 1000000,
    current_dollar_volume: 100000000 + index * 1000000,
    return_5m_pct: index % 2 ? -0.4 : 0.4,
    return_15m_pct: index % 2 ? -0.8 : 0.8,
    return_30m_pct: index % 2 ? -1.1 : 1.1,
    return_60m_pct: index % 2 ? -1.4 : 1.4,
    relative_volume_pace: 2.5,
    relative_return_15m_pct: index % 2 ? -0.6 : 0.6,
    move_capacity_120m_pct: 1.25,
    cost_estimate_bps: 7.5,
    rationale: 'Research hypothesis only; the matching generic family has no validated positive net two-hour edge.',
    evidence: {
      scoring_version: 'ip-reliability-v3.0',
      model_audit_version: 'ip-reliability-v3.0',
      score_interpretation: 'analysis priority, not probability or expected return',
      edge_to_cost_ratio: 16.7,
      bars_used: 120,
      data_quality_score: 98,
      directional_evidence_score: 78,
      movement_opportunity_score: 80,
      execution_quality_score: 92,
      reliability_label: 'NO VALIDATED EDGE',
      trade_gate: 'BLOCKED',
      reference_price_definition: index % 3 ? 'current SIP bid; next-minute open tracked separately' : 'current SIP ask; next-minute open tracked separately',
      observed_trade_price: 100 + index,
      historical_setup_status: 'FAILED_EXTERNAL_HOLDOUT',
      historical_holdout_n: index % 3 ? 6885 : 6311,
      historical_holdout_hit_rate: index % 3 ? 0.4688 : 0.4204,
      historical_holdout_mean_net_pct: index % 3 ? -0.0283 : -0.1340,
    },
  }));
  const scan = {
    id: '0f17ebc8-9b9c-4656-a7f7-266013fe8d0e',
    status: 'completed',
    scoring_version: 'ip-reliability-v3.0',
    metadata: { model_audit_version: 'ip-reliability-v3.0' },
    asset_count: 6357,
    snapshot_count: 6356,
    liquid_count: 1320,
    enriched_count: 300,
    candidate_count: 50,
    evidence_cutoff: '2026-08-20T17:41:57.596801Z',
    horizon_end: '2026-08-20T19:41:57.596801Z',
    market_close: '2026-08-20T20:00:00Z',
    started_at: '2026-08-20T17:41:54.304539Z',
    completed_at: '2026-08-20T17:42:03.408579Z',
  };
  let selections = [];

  const assertCredentialFree = (route) => {
    const headers = route.request().headers();
    assert(!headers['x-app-user'], 'Browser unexpectedly sent an app username.');
    assert(!headers['x-app-key'], 'Browser unexpectedly sent an app access key.');
    assert(!headers.authorization, 'Browser unexpectedly sent an authorization credential.');
  };

  await context.route(`${api}?action=latest`, async (route) => {
    assertCredentialFree(route);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        scan,
        candidates,
        active_request: null,
        selected_candidate_ids: selections.map((row) => row.candidate_id),
        model_audit: audit,
        tracking_summary: { ...trackingSummary, user_selected: selections.length },
      }),
    });
  });
  await context.route(`${api}?action=selections`, async (route) => {
    assertCredentialFree(route);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        selections,
        model_audit: audit,
        tracking_summary: { ...trackingSummary, user_selected: selections.length },
      }),
    });
  });
  await context.route(`${api}?action=select`, async (route) => {
    assertCredentialFree(route);
    const body = route.request().postDataJSON();
    const candidate = candidates.find((row) => row.id === body.candidate_id);
    assert(candidate, 'Select endpoint received an unknown candidate.');
    const selection = {
      id: '11111111-1111-4111-8111-111111111111',
      candidate_id: candidate.id,
      scan_id: scan.id,
      symbol: candidate.symbol,
      name: candidate.name,
      exchange: candidate.exchange,
      direction: candidate.direction,
      setup_type: candidate.setup_type,
      selected_rank: candidate.rank,
      profitability_score: candidate.profitability_score,
      scan_price: candidate.last_price,
      scan_at: scan.evidence_cutoff,
      market_close_at: scan.market_close,
      horizon_end_at: scan.horizon_end,
      user_selected: true,
      user_selected_at: '2026-08-20T17:42:10Z',
      selected_at: '2026-08-20T17:42:03Z',
      entry_price: 100.10,
      entry_at: '2026-08-20T17:42:00Z',
      favourable_extreme_price: candidate.direction === 'SHORT' ? 98.50 : 103.00,
      favourable_extreme_at: '2026-08-20T18:20:00Z',
      horizon_price: candidate.direction === 'SHORT' ? 99.00 : 102.00,
      horizon_at: '2026-08-20T19:41:00Z',
      horizon_status: 'matured',
      close_price: candidate.direction === 'SHORT' ? 99.40 : 101.60,
      close_at: '2026-08-20T19:59:00Z',
      status: 'closed',
      tracking_version: 'ip-tracking-v3',
    };
    selections = [selection];
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ selection, duplicate: false }) });
  });
  await context.route('https://chatgpt.com/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>ChatGPT reliability handoff smoke</title>' });
  });

  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto(site, { waitUntil: 'domcontentloaded', timeout: 60000 });
  assert((await page.locator('#loginModal').count()) === 0, 'A login modal is still present.');
  await page.waitForFunction(() => document.querySelectorAll('#rows tr').length === 10);

  assert((await page.title()).includes('Opportunity Research'), 'Reliability-first title is missing.');
  assert((await page.locator('#auditStatus').innerText()).includes('RESEARCH_ONLY'), 'Audit status was not rendered.');
  assert((await page.locator('#auditStates').innerText()).includes('551,445'), 'Historical audit state count was not rendered.');
  assert((await page.locator('#auditRobust').innerText()) === '0/23', 'Frozen robustness failure was not rendered.');
  assert((await page.locator('body').innerText()).includes('Trade gate blocked'), 'Blocked trade gate is not visible.');
  assert((await page.locator('#rows').innerText()).includes('NO VALIDATED EDGE'), 'Candidate reliability warning is missing.');
  assert((await page.locator('#rows').innerText()).includes('analysis priority'), 'Score is not labelled as analysis priority.');
  assert((await page.locator('[data-select-candidate]').count()) === 10, 'Select column did not render.');
  assert(!(await page.locator('#scanBtn').isDisabled()), 'Scan button did not become available.');

  await page.locator('[data-select-candidate="1001"]').click();
  await page.locator('#selectedPanel.active').waitFor({ state: 'visible' });
  const selectedText = await page.locator('#selectedRows').innerText();
  assert(selectedText.includes('SMOKE1'), 'Selected signal did not move to tracker tab.');
  assert(selectedText.includes('$100.02'), 'Price at scan was not displayed.');
  assert(selectedText.includes('$100.10'), 'Next-minute entry was not displayed.');
  assert(selectedText.includes('$102.00'), 'Fixed two-hour price was not displayed.');
  assert(selectedText.includes('matured 2h'), 'Two-hour maturity status was not displayed.');

  await page.locator('#scannerTab').click();
  await page.locator('#promptBtn').click();
  const fullPrompt = await page.locator('#promptText').inputValue();
  assert(fullPrompt.includes('SMOKE10'), 'Full prompt omitted the tenth candidate.');
  assert(fullPrompt.includes('0/23 registered candidates passed'), 'Full prompt omitted the frozen robustness failure.');
  assert(fullPrompt.includes('app trade gate is blocked'), 'Full prompt omitted the blocked trade gate.');
  const popupPromise = context.waitForEvent('page');
  await page.locator('#openChat').click();
  const popup = await popupPromise;
  await popup.waitForURL((url) => url.hostname === 'chatgpt.com', { timeout: 10000 });
  const populated = new URL(popup.url()).searchParams.get('prompt');
  assert(populated && populated.includes('SMOKE1') && populated.includes('SMOKE10'), 'ChatGPT new chat was not populated with all Top 10 candidates.');
  assert(populated.includes('trade gate is blocked'), 'Compact ChatGPT prompt omitted the reliability safeguard.');
  await popup.close();

  await page.screenshot({ path: 'intraday-profitability-production-smoke.png', fullPage: true });
  assert(errors.length === 0, `Browser errors: ${errors.join(' | ')}`);
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
