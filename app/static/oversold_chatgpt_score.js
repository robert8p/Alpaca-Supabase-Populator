(() => {
  const fmtScore = (value, digits = 2) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  const moneyScore = (value) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
  const pct = (value, digits = 2) => value == null ? 'unknown' : `${fmtScore(value, digits)}%`;

  function pointInTimeNews(c) {
    const source = Array.isArray(c.evidence_news) ? c.evidence_news : (Array.isArray(c.headlines) ? c.headlines : []);
    return source.map((article, index) => {
      const parts = [`${index + 1}. ${article.headline || 'Untitled'}`];
      if (article.source) parts.push(`Source: ${article.source}`);
      if (article.created_at || article.published_at) parts.push(`Published: ${article.created_at || article.published_at}`);
      if (article.summary) parts.push(`Summary: ${article.summary}`);
      if (article.url) parts.push(`URL: ${article.url}`);
      return parts.join('\n   ');
    }).join('\n\n') || 'No company-specific news was retained in the point-in-time Evidence Snapshot.';
  }

  function technicalEvidence(c) {
    const trace = c.calculation_trace || {};
    const setup = trace.setup || {};
    const tech = setup.technical_features || {};
    const confirmation = trace.confirmation || {};
    const confirmationTech = confirmation.technical_features || {};
    const values = [
      `- Historical daily bars available: ${tech.history_count ?? 'unknown'}`,
      `- Volatility-adjusted shock z-score: ${fmtScore(tech.shock_z, 2)}`,
      `- ATR20 move multiple: ${fmtScore(tech.atr_move_multiple, 2)}`,
      `- RSI14 at cutoff: ${fmtScore(tech.rsi14, 1)}`,
      `- Distance from SMA20: ${pct(tech.sma20_distance_pct, 2)}`,
      `- Distance from SMA50: ${pct(tech.sma50_distance_pct, 2)}`,
      `- Drawdown from prior 60-day high: ${pct(tech.drawdown_from_60d_high_pct, 2)}`,
      `- Relative volume vs 20-session mean: ${fmtScore(tech.relative_volume20, 2)}x`,
      `- Volume z-score: ${fmtScore(tech.volume_z20, 2)}`,
      `- Move relative to SPY: ${pct(tech.market_relative_move_pct, 2)}`,
      `- Sector benchmark: ${tech.sector_benchmark || 'unavailable'}`,
      `- Move relative to sector benchmark: ${pct(tech.sector_relative_move_pct, 2)}`,
      `- Gap from previous close: ${pct(confirmationTech.gap_pct ?? tech.gap_pct, 2)}`,
      `- Session range position: ${pct(confirmationTech.session_range_position ?? tech.session_range_position, 1)}`,
      `- Gap reclaim: ${pct(confirmationTech.gap_reclaim_pct ?? tech.gap_reclaim_pct, 1)}`,
      `- Low-to-prev-close reclaim: ${pct(confirmationTech.low_reclaim_pct ?? tech.low_reclaim_pct, 1)}`,
      `- Distance from session VWAP: ${pct(confirmationTech.vwap_distance_pct ?? tech.vwap_distance_pct, 2)}`,
      `- Technical-history completeness: ${pct(tech.technical_history_completeness, 1)}`,
    ];
    return values.join('\n');
  }

  function fundamentalEvidence(c) {
    const analysis = c.catalyst_analysis || {};
    const trace = analysis.fundamental_trace || {};
    const raw = trace.raw_metrics || {};
    if (!trace.available) {
      return '- Point-in-time periodic filing fundamentals: unavailable at the evidence cutoff. Treat resilience as uncertain, not favourable evidence.';
    }
    return [
      `- Filing source/form: ${trace.source || 'unknown'} / ${trace.form || 'unknown'}`,
      `- Filing available from: ${trace.available_from || 'unknown'}; report period: ${trace.report_period_end || 'unknown'}; age: ${trace.age_calendar_days ?? 'unknown'} days`,
      `- Fundamental metric coverage count: ${trace.metric_coverage_count ?? 'unknown'}`,
      `- Revenue YoY: ${pct(raw.revenue_yoy == null ? null : Number(raw.revenue_yoy) * 100, 1)}`,
      `- Net margin: ${pct(raw.net_margin == null ? null : Number(raw.net_margin) * 100, 1)}`,
      `- Net-margin YoY delta: ${pct(raw.net_margin_yoy_delta == null ? null : Number(raw.net_margin_yoy_delta) * 100, 1)}`,
      `- Diluted shares YoY: ${pct(raw.diluted_shares_yoy == null ? null : Number(raw.diluted_shares_yoy) * 100, 1)}`,
      `- Cash / assets: ${pct(raw.cash_to_assets == null ? null : Number(raw.cash_to_assets) * 100, 1)}`,
      `- Liabilities / assets: ${pct(raw.liabilities_to_assets == null ? null : Number(raw.liabilities_to_assets) * 100, 1)}`,
      `- Equity / assets: ${pct(raw.equity_to_assets == null ? null : Number(raw.equity_to_assets) * 100, 1)}`,
      `- Fundamental scoring contributions: ${JSON.stringify(trace.contributions || {})}`,
    ].join('\n');
  }

  function evidenceQuality(c) {
    const analysis = c.catalyst_analysis || {};
    const q = analysis.evidence_quality_trace || {};
    const sourceQuality = c.source_quality || {};
    return [
      `- Independent retained sources: ${q.independent_source_count ?? 'unknown'} (${Array.isArray(q.sources) ? q.sources.join(', ') : 'unknown'})`,
      `- Authoritative/direct source present: ${q.authoritative_source_present == null ? 'unknown' : q.authoritative_source_present ? 'yes' : 'no'}`,
      `- Freshest retained source age: ${q.freshest_age_hours == null ? 'unknown' : `${fmtScore(q.freshest_age_hours,1)}h`}`,
      `- Contradictory evidence detected: ${q.conflicting_evidence == null ? 'unknown' : q.conflicting_evidence ? 'yes' : 'no'}`,
      `- App enrichment errors: ${Array.isArray(sourceQuality.enrichment_errors) && sourceQuality.enrichment_errors.length ? sourceQuality.enrichment_errors.join('; ') : 'none retained'}`,
    ].join('\n');
  }

  function buildOptimizedChatGPTPrompt(c) {
    const flags = (c.risk_flags || []).length ? c.risk_flags.join(', ') : 'none flagged';
    const commentary = c.review_notes ? `\n- Reviewer commentary (human hypothesis only, not ground truth): ${c.review_notes}` : '';
    const evidenceCutoff = c.evidence_cutoff || c.signal_timestamp || c.created_at || 'unknown';
    const legacy = c.model_run_id == null;
    const evidence = pointInTimeNews(c);
    const analysis = c.catalyst_analysis || {};
    const isCalibrated = c.model_status === 'calibrated' && c.calibrated_probability != null;
    const primaryMetric = isCalibrated
      ? `- App Reversion Probability: ${fmtScore(Number(c.calibrated_probability) * 100,1)}% (raw Reversion Score ${fmtScore(c.reversion_score,1)})`
      : `- App Reversion Score: ${fmtScore(c.reversion_score,1)}/100 (UNCALIBRATED ranking score, not a probability)`;
    const componentLine = legacy
      ? `- This is a legacy row with no valid current model run. Legacy heuristic score: ${c.heuristic_score ?? 'unknown'}. Do not manufacture missing historic features.`
      : `${primaryMetric}\n- Setup: ${fmtScore(c.setup_score,1)}\n- Catalyst: ${fmtScore(c.catalyst_score,1)}\n- Fundamental Resilience: ${fmtScore(c.resilience_score,1)}\n- Confirmation: ${fmtScore(c.confirmation_score,1)}\n- Damage Risk: ${fmtScore(c.damage_risk,1)}\n- Evidence Confidence: ${fmtScore(c.evidence_confidence,1)}\n- App verdict: ${c.model_verdict || 'unknown'}\n- Model/config: ${c.scoring_model_version || 'unknown'} / ${c.scoring_config_version || 'unknown'}\n- Event profile: ${analysis.event_profile || 'unknown'}\n- Event signals: ${JSON.stringify(analysis.event_signals || {})}`;

    return `Audit ${c.name || c.symbol} (${c.symbol}) as the ORIGINAL Oversold Reversion signal. Your job is to assess whether the app's point-in-time score is defensible and identify component-level disagreements. Do not overwrite the app model and do not treat your answer as ground truth.

STRATEGY TARGET
The eventual ground-truth outcome is whether the stock trades at least +5% above the stored signal price within six weeks.

STRICT POINT-IN-TIME RULE
Evidence cutoff: ${evidenceCutoff}
Signal timestamp: ${c.signal_timestamp || evidenceCutoff}
Signal price: ${c.signal_price == null ? moneyScore(c.last_price) : moneyScore(c.signal_price)}

Use ONLY information that was available on or before the evidence cutoff above when judging whether the ORIGINAL signal was sound. Do NOT use later news, later price action, later analyst revisions, later filings, or knowledge of what ultimately happened. If you know later information, explicitly ignore it. Do not browse for post-cutoff facts when judging the original signal.

APP / SCANNER CONTEXT
- Move versus previous close: ${fmtScore(c.drop_pct,2)}%
- Last/signal-area price: ${moneyScore(c.last_price)}
- Previous close: ${moneyScore(c.prev_close)}
- Spread: ${c.spread_pct == null ? 'unknown' : fmtScore(c.spread_pct,2)+'%'}
- Scanner catalyst class: ${c.catalyst_class || 'U'}
- Risk flags: ${flags}
- Scanner summary: ${c.catalyst_summary || 'none'}${commentary}
${componentLine}

POINT-IN-TIME TECHNICAL EVIDENCE USED BY THE APP
${technicalEvidence(c)}

POINT-IN-TIME FUNDAMENTAL EVIDENCE USED BY THE APP
${fundamentalEvidence(c)}

POINT-IN-TIME SOURCE / EVIDENCE QUALITY
${evidenceQuality(c)}

POINT-IN-TIME NEWS / EVIDENCE RETAINED BY THE APP
${evidence}

CANONICAL APP SCORING CONTRACT
The app's deterministic score uses:
Core = 0.25×Setup + 0.35×Catalyst + 0.15×Fundamental Resilience + 0.25×Confirmation.
Confidence is reliability, not attractiveness: ConfidenceAdjusted = 50 + ((Core - 50) × EvidenceConfidence / 100).
Damage penalty = min(15, max(0, DamageRisk - 25) × 0.20).
Damage caps: 0–29→100; 30–49→85; 50–69→65; 70–84→40; 85–100→20.
If the principal cause cannot be verified, Catalyst is capped at 35, final score at 60, and verdict at WATCH.
Verified existential/solvency/core-thesis failure can hard-veto to PASS.
Analyst consensus is supporting evidence only. Post-event analyst reaction may inform Catalyst evidence, but ratings are not a standalone scoring component.

V3 COMPONENT DEFINITIONS
- Setup: point-in-time statistical dislocation using raw decline, volatility shock, ATR move, RSI, moving-average deviation, recent-high drawdown, volume anomaly, market/sector-relative move and tradability. A bigger fall alone is not better.
- Catalyst: likelihood the verified event is temporary, reversible, survivable or over-discounted within six weeks. Event profile and damage signals matter more than generic sentiment.
- Fundamental Resilience: capacity to absorb the event using cutoff-valid filing metrics where genuinely available. Missing filings are uncertainty, not a favourable assumption.
- Confirmation: point-in-time exhaustion/stabilisation via range position, intraday reversal, gap reclaim, VWAP relationship, volume and spread.
- Damage Risk: structural/economic impairment risk; asymmetric penalty/cap and possible veto.
- Evidence Confidence: independent-source quality/freshness + market-data completeness + fundamental-evidence completeness. Repeated headlines from one publisher are not independent evidence.

AUDIT TASK
1. State the verified primary cause using only cutoff-valid evidence, or say UNVERIFIED.
2. For each of Setup, Catalyst, Resilience, Confirmation, Damage and Confidence, say AGREE / TOO HIGH / TOO LOW / INSUFFICIENT EVIDENCE and explain briefly.
3. Pay special attention to whether missing historical/fundamental information is being mistaken for favourable evidence.
4. For analyst material, distinguish cutoff-valid post-event changes from stale pre-event consensus; if no reliable analyst evidence is in the snapshot, say unavailable.
5. Identify the strongest point-in-time evidence FOR the reversion thesis and AGAINST it.
6. State whether the app's INVESTIGATE / WATCH / PASS conclusion is defensible under the canonical rules.
7. Name the single most important cutoff-valid evidence item that would have improved the original assessment.

OUTPUT
Return a concise markdown component-audit table followed by: App-score assessment, strongest for/against evidence, and key missing evidence. Keep facts separate from inference. This is research, not an instruction to trade.`;
  }

  window.buildChatGPTPrompt = buildOptimizedChatGPTPrompt;

  function relabelRowButtons() {
    document.querySelectorAll('#rows .chatgpt-button').forEach((button) => {
      if (button.textContent !== 'Audit ↗') button.textContent = 'Audit ↗';
      const title = 'Open ChatGPT to audit this exact point-in-time Evidence Snapshot against the same scoring contract';
      if (button.title !== title) button.title = title;
      const helper = button.parentElement && button.parentElement.querySelector('.muted');
      if (helper && helper.textContent !== 'same cutoff') helper.textContent = 'same cutoff';
    });
  }

  relabelRowButtons();
  const rows = document.getElementById('rows');
  if (rows) {
    let relabelScheduled = false;
    new MutationObserver(() => {
      if (relabelScheduled) return;
      relabelScheduled = true;
      queueMicrotask(() => {
        relabelScheduled = false;
        relabelRowButtons();
      });
    }).observe(rows, { childList: true, subtree: true });
  }

  let latestRefreshInFlight = false;
  async function refreshLatestView() {
    if (document.visibilityState !== 'visible' || latestRefreshInFlight || typeof load !== 'function') return;
    if (typeof state !== 'undefined' && state.scan?.status === 'running') return;
    latestRefreshInFlight = true;
    try {
      await load();
    } catch (error) {
      console.warn('Periodic latest-scan refresh failed', error);
    } finally {
      latestRefreshInFlight = false;
    }
  }

  setInterval(refreshLatestView, 30000);
})();