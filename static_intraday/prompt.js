(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.IPPrompt = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const COMPACT_LIMIT = 6800;
  const n = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
  const signed = (value, digits = 2) => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%`;
  const px = (value) => value == null || Number.isNaN(Number(value)) ? '—' : `$${Number(value).toFixed(Number(value) < 10 ? 3 : 2)}`;
  const money = (value) => {
    if (value == null || Number.isNaN(Number(value))) return '—';
    const x = Number(value);
    if (x >= 1e9) return `$${(x / 1e9).toFixed(1)}b`;
    if (x >= 1e6) return `$${(x / 1e6).toFixed(1)}m`;
    if (x >= 1e3) return `$${(x / 1e3).toFixed(0)}k`;
    return `$${x.toFixed(0)}`;
  };

  function assertScan(scan) {
    if (!scan || scan.status !== 'completed') throw new Error('No completed scan is selected.');
  }

  function auditLines(audit) {
    if (!audit) return [
      'Model audit status is unavailable. Treat every app direction and score as unvalidated and research-only.',
    ];
    const findings = audit.findings || {};
    return [
      `Model audit: ${audit.status}; version ${audit.model_version}.`,
      `Point-in-time audit states: ${Number(findings.total_point_in_time_states || 0).toLocaleString()} across ${findings.trading_days || 'unknown'} trading days; external holdout ${audit.holdout_start} to ${audit.holdout_end}.`,
      `Frozen robustness gate: ${audit.robust_candidates_passed}/${audit.registered_robust_candidates} registered candidates passed. Large-sample generic rules passed: ${audit.large_sample_generic_rules_passed}.`,
      'Therefore the app score is ANALYSIS PRIORITY only—not probability, expected return, or evidence of a profitable generic trading rule. The app trade gate is blocked.',
    ];
  }

  function buildFullPrompt(scan, rawCandidates, audit = null, tracking = null) {
    assertScan(scan);
    const candidates = (rawCandidates || []).slice(0, 10);
    const lines = [
      'Audit these Intraday Opportunity candidates as ORIGINAL point-in-time hypotheses. Do not use hindsight.',
      `Shared evidence cutoff: ${scan.evidence_cutoff}. Fixed research horizon ends: ${scan.horizon_end}.`,
      'Use only facts, filings, announcements, news and market information published on or before the evidence cutoff.',
      ...auditLines(audit),
      tracking ? `Prospective calibration coverage: ${tracking.total_candidates_tracked || 0} ranked candidates tracked; ${tracking.horizon_matured || 0} have a matured two-hour outcome.` : '',
      '',
      'Your role is to determine whether contemporaneous company-specific evidence creates an independent catalyst-led opportunity that the failed generic heuristic could not establish.',
      'For each stock: identify the contemporaneous catalyst; test whether the proposed direction and continuation/reversion label are justified; assess contradictory evidence, borrowability where relevant, spread/slippage, further adverse excursion and time remaining; estimate P(positive NET directional return from an executable entry over the next 120 regular-session minutes); give a realistic net return range and invalidation condition.',
      'Return a best-to-worst table with: rank, ticker, independent direction, P(net profitable), expected net return range, catalyst confidence, execution quality, strongest contradiction, and verdict TRADE LONG / TRADE SHORT / WATCH / PASS.',
      'A TRADE verdict may not be based on the app score. It requires strong independent, cutoff-compliant catalyst evidence, credible execution and favourable asymmetry. Explicitly identify every disagreement with the app. Do not manufacture precision.',
      '',
    ].filter(Boolean);

    candidates.forEach((row) => {
      const evidence = row.evidence || {};
      lines.push(
        `${row.rank}. ${row.symbol} (${row.name || row.symbol})`,
        `App hypothesis: ${row.direction} ${row.setup_type} | analysis priority ${n(row.profitability_score, 1)}/100 | disposition ${row.initial_view} | reliability ${evidence.reliability_label || 'UNVALIDATED'} | trade gate ${evidence.trade_gate || 'BLOCKED'}`,
        `Executable reference ${px(row.last_price)} (${evidence.reference_price_definition || 'quote-side reference'}) | observed trade ${px(evidence.observed_trade_price)} | day ${signed(row.day_move_pct)} | spread ${n(row.spread_bps, 1)} bps | estimated round-trip cost ${n(row.cost_estimate_bps, 1)} bps`,
        `Movement capacity ${n(row.move_capacity_120m_pct, 2)}% | capacity/cost ${n(evidence.edge_to_cost_ratio, 1)}x | direction evidence ${n(evidence.directional_evidence_score, 0)}/100 | movement opportunity ${n(evidence.movement_opportunity_score, 0)}/100 | execution quality ${n(evidence.execution_quality_score, 0)}/100 | data quality ${n(evidence.data_quality_score, 0)}/100`,
        `Returns: 5m ${signed(row.return_5m_pct)}, 15m ${signed(row.return_15m_pct)}, 30m ${signed(row.return_30m_pct)}, 60m ${signed(row.return_60m_pct)} | 15m vs SPY ${signed(row.relative_return_15m_pct)}`,
        `Liquidity: previous-day ${money(row.prev_dollar_volume)}; current ${money(row.current_dollar_volume)}; volume pace ${n(row.relative_volume_pace, 2)}x; bars ${evidence.bars_used ?? 'unknown'}`,
        `Matching historical family: ${evidence.historical_setup_status || 'unsupported'}; holdout n=${evidence.historical_holdout_n ?? 0}; holdout hit rate=${evidence.historical_holdout_hit_rate == null ? '—' : n(Number(evidence.historical_holdout_hit_rate) * 100, 1) + '%'}; holdout mean net=${signed(evidence.historical_holdout_mean_net_pct)}`,
        `App rationale: ${row.rationale}`,
        '',
      );
    });
    lines.push(
      'Finish with: strongest independent catalyst-led candidate; strongest reason not to trade it; every candidate that should be rejected despite high movement capacity; and the single most important fact to verify before risking capital.',
      'This is analysis, not a guarantee or an instruction to trade.',
    );
    return lines.join('\n');
  }

  function buildCompactPrompt(scan, rawCandidates, audit = null, tracking = null) {
    assertScan(scan);
    const candidates = (rawCandidates || []).slice(0, 10);
    const auditSummary = audit
      ? `${Number((audit.findings || {}).total_point_in_time_states || 0).toLocaleString()} historical states; ${audit.robust_candidates_passed}/${audit.registered_robust_candidates} robust candidates passed; generic large-sample rules passed ${audit.large_sample_generic_rules_passed}.`
      : 'Audit unavailable; generic edge unvalidated.';
    const lines = [
      `Independently audit these original intraday hypotheses. Cutoff ${scan.evidence_cutoff}; horizon ${scan.horizon_end}. Use no information published after the cutoff. ${auditSummary}`,
      `The score is analysis priority only; the app trade gate is blocked. ${tracking ? `${tracking.horizon_matured || 0}/${tracking.total_candidates_tracked || 0} prospective two-hour outcomes have matured.` : ''}`,
      'For each, investigate the contemporaneous catalyst and contradictions; assess execution and borrowability; estimate P(positive net directional return over 120 regular-session minutes), expected net range and invalidation. Verdict TRADE LONG/SHORT only with strong independent catalyst evidence; otherwise WATCH/PASS. Rerank and flag disagreements.',
    ];
    candidates.forEach((row) => {
      const e = row.evidence || {};
      lines.push(`${row.rank} ${row.symbol} ${row.direction} ${row.setup_type}; priority ${n(row.profitability_score,1)}; reliability ${e.reliability_label || 'UNVALIDATED'}; px ${n(row.last_price,3)}; day ${n(row.day_move_pct,2)}%; r5/15/30/60 ${n(row.return_5m_pct,2)}/${n(row.return_15m_pct,2)}/${n(row.return_30m_pct,2)}/${n(row.return_60m_pct,2)}%; rel15 ${n(row.relative_return_15m_pct,2)}%; spread/cost ${n(row.spread_bps,1)}/${n(row.cost_estimate_bps,1)}bp; capacity ${n(row.move_capacity_120m_pct,2)}%; dir/opp/exec ${n(e.directional_evidence_score,0)}/${n(e.movement_opportunity_score,0)}/${n(e.execution_quality_score,0)}; historical ${e.historical_setup_status || 'unsupported'} n=${e.historical_holdout_n || 0}, mean ${n(e.historical_holdout_mean_net_pct,3)}%.`);
    });
    lines.push('Finish with strongest catalyst-led candidate, strongest counterargument, false positives, and the most important fact to verify.');
    let compact = lines.join('\n');
    if (compact.length > COMPACT_LIMIT) compact = compact.slice(0, COMPACT_LIMIT - 130) + '\nPrompt compacted to fit the populated ChatGPT handoff. Audit every complete candidate listed above.';
    return compact;
  }

  function chatGptUrl(compactPrompt) {
    const text = String(compactPrompt || '').trim();
    if (!text) throw new Error('The compact ChatGPT prompt is empty.');
    const target = new URL('https://chatgpt.com/');
    target.searchParams.set('prompt', text);
    return target.toString();
  }

  return { COMPACT_LIMIT, buildFullPrompt, buildCompactPrompt, chatGptUrl };
});
