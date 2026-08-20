(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.IPPrompt = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const COMPACT_LIMIT = 6800;
  const n = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
  const signed = (value, digits = 2) => value == null ? '—' : `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%`;
  const px = (value) => value == null ? '—' : `$${Number(value).toFixed(Number(value) < 10 ? 3 : 2)}`;
  const money = (value) => {
    if (value == null) return '—';
    const x = Number(value);
    if (x >= 1e9) return `$${(x / 1e9).toFixed(1)}b`;
    if (x >= 1e6) return `$${(x / 1e6).toFixed(1)}m`;
    if (x >= 1e3) return `$${(x / 1e3).toFixed(0)}k`;
    return `$${x.toFixed(0)}`;
  };

  function assertScan(scan) {
    if (!scan || scan.status !== 'completed') throw new Error('No completed scan is selected.');
  }

  function buildFullPrompt(scan, rawCandidates) {
    assertScan(scan);
    const candidates = (rawCandidates || []).slice(0, 10);
    const lines = [
      'Audit these Intraday Profitability candidates as ORIGINAL signals. Do not use hindsight.',
      `Shared evidence cutoff: ${scan.evidence_cutoff}. Target horizon ends: ${scan.horizon_end}.`,
      'Use only facts, filings, announcements, news and market information published on or before the evidence cutoff.',
      'The app score is an unvalidated, transparent heuristic. Independently challenge its direction, setup classification and order.',
      '',
      'For each stock: identify the contemporaneous catalyst; judge continuation versus reversal; assess contradictory evidence, liquidity and execution risk; estimate P(positive NET directional return over the next 120 regular-session minutes); give a realistic return range and invalidation condition.',
      'Return a best-to-worst table with: rank, ticker, independent direction, P(net profitable), expected net return range, catalyst confidence, key risk, and verdict TRADE LONG / TRADE SHORT / WATCH / PASS.',
      'Explicitly identify every material disagreement with the app. Do not manufacture precision or describe any outcome as certain.',
      '',
    ];
    candidates.forEach((row) => {
      const evidence = row.evidence || {};
      lines.push(
        `${row.rank}. ${row.symbol} (${row.name || row.symbol})`,
        `App: ${row.direction} ${row.setup_type} | score ${n(row.profitability_score, 1)}/100 | initial view ${row.initial_view}`,
        `Price ${px(row.last_price)} | day ${signed(row.day_move_pct)} | spread ${n(row.spread_bps, 1)} bps | round-trip cost ${n(row.cost_estimate_bps, 1)} bps | 2h capacity ${n(row.move_capacity_120m_pct, 2)}% | capacity/cost ${n(evidence.edge_to_cost_ratio, 1)}x`,
        `Returns: 5m ${signed(row.return_5m_pct)}, 15m ${signed(row.return_15m_pct)}, 30m ${signed(row.return_30m_pct)}, 60m ${signed(row.return_60m_pct)} | 15m vs SPY ${signed(row.relative_return_15m_pct)}`,
        `Liquidity: previous-day ${money(row.prev_dollar_volume)}; current ${money(row.current_dollar_volume)}; volume pace ${n(row.relative_volume_pace, 2)}x; bars ${evidence.bars_used ?? 'unknown'}; data quality ${n(evidence.data_quality_score, 0)}/100`,
        `Components: liquidity ${n(row.liquidity_score, 1)}, opportunity ${n(row.opportunity_score, 1)}, direction ${n(row.directional_score, 1)}, confirmation ${n(row.confirmation_score, 1)}, execution ${n(row.execution_score, 1)}.`,
        `App rationale: ${row.rationale}`,
        '',
      );
    });
    lines.push('Finish with the strongest candidate, strongest reason not to trade it, any candidate that should be rejected despite its score, and the single most important fact to verify before risking capital.', 'This is analysis, not a guarantee or an instruction to trade.');
    return lines.join('\n');
  }

  function buildCompactPrompt(scan, rawCandidates) {
    assertScan(scan);
    const candidates = (rawCandidates || []).slice(0, 10);
    const lines = [
      `Independently audit these original intraday signals. Evidence cutoff ${scan.evidence_cutoff}; horizon ${scan.horizon_end}. Use no information published after the cutoff. The app score is an unvalidated heuristic: challenge direction and ranking.`,
      'For each, investigate the contemporaneous catalyst and contradictions; assess execution risk; estimate P(positive net directional return over the next 120 regular-session minutes), expected net range, invalidation, and verdict TRADE LONG/TRADE SHORT/WATCH/PASS. Return a best-to-worst table and explicitly flag disagreements.',
    ];
    candidates.forEach((row) => {
      const evidence = row.evidence || {};
      lines.push(`${row.rank} ${row.symbol} ${row.direction} ${row.setup_type}; score ${n(row.profitability_score,1)}; px ${n(row.last_price,3)}; day ${n(row.day_move_pct,2)}%; r5/15/30/60 ${n(row.return_5m_pct,2)}/${n(row.return_15m_pct,2)}/${n(row.return_30m_pct,2)}/${n(row.return_60m_pct,2)}%; rel15 ${n(row.relative_return_15m_pct,2)}%; spread/cost ${n(row.spread_bps,1)}/${n(row.cost_estimate_bps,1)}bp; capacity ${n(row.move_capacity_120m_pct,2)}%; vol pace ${n(row.relative_volume_pace,2)}x; cap/cost ${n(evidence.edge_to_cost_ratio,1)}x; view ${row.initial_view}.`);
    });
    lines.push('Finish with strongest candidate, strongest counterargument, any false positive, and the most important fact to verify.');
    let compact = lines.join('\n');
    if (compact.length > COMPACT_LIMIT) compact = compact.slice(0, COMPACT_LIMIT - 120) + '\nPrompt compacted to fit the populated ChatGPT handoff. Audit every complete candidate listed above.';
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
