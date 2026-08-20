(() => {
  if (window.__orV33ChatGPTInstalled) return;
  window.__orV33ChatGPTInstalled = true;

  const CHATGPT = 'https://chatgpt.com/?q=';
  const escText = value => String(value ?? '').replace(/\s+/g, ' ').trim();
  const fmt = (value, digits=1) => value == null || Number.isNaN(Number(value)) ? 'unknown' : Number(value).toFixed(digits);
  const money = value => value == null || Number.isNaN(Number(value)) ? 'unknown' : Number(value).toLocaleString(undefined,{style:'currency',currency:'USD',maximumFractionDigits:2});
  const clip = (value, max=260) => {
    const text = escText(value);
    return text.length <= max ? text : `${text.slice(0,max-1)}…`;
  };

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch (_) {
      try {
        const area = document.createElement('textarea');
        area.value = text;
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        const ok = document.execCommand('copy');
        area.remove();
        return ok;
      } catch (_) { return false; }
    }
  }

  function news(c, limit=6) {
    const items = Array.isArray(c.evidence_news) ? c.evidence_news : (Array.isArray(c.headlines) ? c.headlines : []);
    return items.slice(0,limit).map((a,index) => [
      `${index+1}. ${clip(a.headline || 'Untitled',180)}`,
      a.source ? `source=${clip(a.source,60)}` : null,
      a.created_at || a.published_at ? `published=${a.created_at || a.published_at}` : null,
      a.summary ? `summary=${clip(a.summary,300)}` : null,
      a.url ? `url=${a.url}` : null,
    ].filter(Boolean).join(' | ')).join('\n') || 'No ticker-specific evidence was retained.';
  }

  function sourceHierarchy(c) {
    const items = c.catalyst_analysis?.source_quality_items || [];
    return items.slice(0,6).map(item =>
      `${item.source_type || 'unknown'} ${item.source_quality_score ?? '—'}/100 | ${clip(item.source || '',50)} | ${clip(item.headline || '',160)}`
    ).join('\n') || 'No source hierarchy retained.';
  }

  function fundamentals(c) {
    const trace = c.catalyst_analysis?.fundamental_trace || {};
    const raw = trace.raw_metrics || {};
    if (!trace.available) return 'Primary financial evidence: UNAVAILABLE. Do not infer financial health from absence of data.';
    const values = [
      `source/form=${trace.source || 'unknown'} / ${trace.form || 'unknown'}`,
      `available_from=${trace.available_from || 'unknown'}; report_period=${trace.report_period_end || 'unknown'}; age_days=${trace.age_calendar_days ?? 'unknown'}`,
      `coverage=${trace.metric_coverage_count ?? 'unknown'}`,
      `revenue_yoy=${raw.revenue_yoy == null ? 'unknown' : fmt(Number(raw.revenue_yoy)*100)+'%'}`,
      `net_margin=${raw.net_margin == null ? 'unknown' : fmt(Number(raw.net_margin)*100)+'%'}`,
      `cash/assets=${raw.cash_to_assets == null ? 'unknown' : fmt(Number(raw.cash_to_assets)*100)+'%'}`,
      `liabilities/assets=${raw.liabilities_to_assets == null ? 'unknown' : fmt(Number(raw.liabilities_to_assets)*100)+'%'}`,
      `debt/assets=${raw.debt_to_assets == null ? 'unknown' : fmt(Number(raw.debt_to_assets)*100)+'%'}`,
      `current_ratio=${fmt(raw.current_ratio,2)}`,
      `cash_runway_months=${fmt(raw.cash_runway_months,1)}`,
      `diluted_shares_yoy=${raw.diluted_shares_yoy == null ? 'unknown' : fmt(Number(raw.diluted_shares_yoy)*100)+'%'}`,
      `market_cap=${money(raw.market_cap)}`,
      `price_to_sales=${fmt(raw.price_to_sales,2)}`,
    ];
    return values.join('\n');
  }

  function technical(c) {
    const tech = c.calculation_trace?.setup?.technical_features || {};
    const confirm = c.calculation_trace?.confirmation?.technical_features || {};
    return [
      `shock_z=${fmt(tech.shock_z,2)}; ATR_multiple=${fmt(tech.atr_move_multiple,2)}; RSI14=${fmt(tech.rsi14,1)}`,
      `SMA20_distance=${fmt(tech.sma20_distance_pct,1)}%; SMA50_distance=${fmt(tech.sma50_distance_pct,1)}%; 60d_drawdown=${fmt(tech.drawdown_from_60d_high_pct,1)}%`,
      `relative_volume=${fmt(tech.relative_volume20,2)}x; SPY_relative=${fmt(tech.market_relative_move_pct,1)}%; sector_relative=${fmt(tech.sector_relative_move_pct,1)}%`,
      `range_position=${fmt(confirm.session_range_position ?? tech.session_range_position,1)}%; gap_reclaim=${fmt(confirm.gap_reclaim_pct ?? tech.gap_reclaim_pct,1)}%; VWAP_distance=${fmt(confirm.vwap_distance_pct ?? tech.vwap_distance_pct,1)}%`,
    ].join('\n');
  }

  function appAssessment(c) {
    const a = c.catalyst_analysis || {};
    const v = c.calculation_trace?.v3_3 || {};
    const gates = a.eligibility_gates || v.eligibility_gates || {};
    const failed = a.failed_eligibility_gates || v.failed_eligibility_gates || [];
    const session = a.price_session_context || v.price_session_context || {};
    return [
      `Opportunity Score=${fmt(c.reversion_score,1)}/100 (uncalibrated unless explicitly labelled otherwise); app verdict=${c.model_verdict || 'unknown'}`,
      `Overreaction=${fmt(a.overreaction_quality_score)}; reversibility=${fmt(a.reversibility_score)}; survivability=${fmt(a.survivability_score)}; 3-session fit=${fmt(a.three_session_fit_score)}; confirmation=${fmt(c.confirmation_score)}; tail risk=${fmt(a.tail_risk_score)}; evidence confidence=${fmt(c.evidence_confidence)}`,
      `Cause status=${a.cause_verification_status || 'UNKNOWN'}; assessment state=${a.assessment_confidence_state || 'UNKNOWN'}; fundamental evidence=${a.fundamental_evidence_state || 'UNAVAILABLE'}`,
      `Event=${a.event_taxonomy_primary || a.event_profile || 'unknown'}; damage=${fmt(c.damage_risk)}; financing=${a.dilution_analysis?.classification || 'not_applicable'}`,
      `Price session=${session.price_session || 'unknown'}; current move=${fmt(session.current_move_pct ?? c.drop_pct,2)}%; regular-session move=${fmt(session.regular_session_move_pct,2)}%; extended-hours-only=${session.extended_hours_only ? 'yes' : 'no'}`,
      `Failed gates=${failed.length ? failed.join(', ') : 'none'}; all gates=${JSON.stringify(gates)}`,
    ].join('\n');
  }

  function buildPrompt(c) {
    const cutoff = c.evidence_cutoff || c.signal_timestamp || c.created_at || 'unknown';
    const commentary = c.review_notes ? `\nHUMAN COMMENTARY (hypothesis, not evidence)\n${c.review_notes}` : '';
    return `Independently audit ${c.name || c.symbol} (${c.symbol}) as an Oversold Reversion candidate.

PURPOSE
Identify whether the sell-off exceeds justified economic damage, the company can survive, and a credible reversion can occur within 3 trading sessions. A cheap or technically oversold stock is not automatically an opportunity.

POINT-IN-TIME CONTROL
Evidence cutoff: ${cutoff}
Signal timestamp: ${c.signal_timestamp || cutoff}
Signal price: ${money(c.signal_price ?? c.last_price)}
Use only facts available at or before the cutoff when judging the original signal. Separate FACT, INFERENCE and UNKNOWN. Do not use later price action or later disclosures as evidence that the original thesis was correct.

MARKET CONTEXT
move=${fmt(c.drop_pct,2)}%; previous_close=${money(c.prev_close)}; last=${money(c.last_price)}; spread=${fmt(c.spread_pct,2)}%; previous_day_dollar_volume=${money(c.prev_dollar_volume)}
${technical(c)}

APP ASSESSMENT — CHALLENGE IT; DO NOT RESTATE IT
${appAssessment(c)}

POINT-IN-TIME FUNDAMENTALS
${fundamentals(c)}

SOURCE QUALITY
${sourceHierarchy(c)}

RETAINED EVIDENCE
${news(c)}
${commentary}

QUESTIONS
1. What precisely caused the sell-off?
2. What evidence confirms that cause, and how authoritative/fresh is it?
3. Is the catalyst temporary, permanent, mixed or genuinely unknown?
4. How much underlying economic value appears impaired?
5. Is the share-price decline proportionate to that impairment?
6. Can the company financially survive the event, using cash, debt, burn, runway and dilution evidence?
7. Are bankruptcy, default, delisting, fraud, pivotal-failure or other asymmetric risks material?
8. What evidence supports a rebound?
9. What evidence contradicts the rebound thesis?
10. What would invalidate the trade?
11. What could catalyse recovery?
12. Can reversion plausibly occur within 3 trading sessions?
13. Is expected upside attractive relative to downside and execution risk?
14. Is this a genuine mispricing or merely a stock that became cheaper?
15. What single additional evidence item would most change the conclusion?

OUTPUT
Return a compact table: Cause; evidence state; economic damage; survivability; overreaction; tail risk; 3-session fit; upside/downside asymmetry; verdict INVESTIGATE/WATCH/PASS; confidence 0–100. Then give strongest evidence for, strongest evidence against, invalidator, plausible holding period, and the most valuable missing evidence. This is research, not an instruction to trade.`;
  }

  function buildTopPrompt(candidates) {
    const rows = candidates.map((c,index) => {
      const a = c.catalyst_analysis || {};
      return `${index+1}. ${c.symbol} ${clip(c.name || '',60)} | rank=${c.rank ?? index+1} | move=${fmt(c.drop_pct,1)}% | opportunity=${fmt(c.reversion_score ?? c.heuristic_score,1)} | app=${c.model_verdict || c.triage_label || 'unknown'} | cause=${a.cause_verification_status || 'UNKNOWN'} | event=${a.event_taxonomy_primary || a.event_profile || 'unknown'} | overreaction=${fmt(a.overreaction_quality_score)} | survivability=${fmt(a.survivability_score)} | damage=${fmt(c.damage_risk)} | tail=${fmt(a.tail_risk_score)} | fit3=${fmt(a.three_session_fit_score)} | confidence=${fmt(c.evidence_confidence)} | fundamentals=${a.fundamental_evidence_state || 'UNAVAILABLE'} | failed=${(a.failed_eligibility_gates || []).join(',') || 'none'} | headline=${clip((c.evidence_news || c.headlines || [])[0]?.headline || 'none',150)}`;
    }).join('\n');

    return `Compare the following ${candidates.length} current Oversold Reversion candidates. Independently verify current information, prioritising company filings/IR, SEC, regulators and high-quality financial reporting. The objective is mispricing quality within 3 trading sessions—not decline magnitude.

${rows}

For each candidate answer briefly:
- precise reason for decrease;
- current analyst consensus/prediction, with freshness and coverage caveat;
- economic damage vs observed decline;
- survivability and asymmetric-risk assessment;
- INVESTIGATE/WATCH/PASS;
- recommended holding period, never longer than the evidence-supported reversion thesis;
- key invalidator.

ALLOCATION RULE
Only candidates whose current analyst consensus is Buy/Strong Buy/Outperform/Overweight or equivalent AND whose independent verdict is INVESTIGATE may receive allocation. Every other candidate receives 0%. Allocate exactly 100.0% across qualifying candidates, risk-weighted for liquidity, spread, survivability, dilution/default risk, evidence quality and conviction. If none qualify, allocate 0% to all and state: No Buy-or-better INVESTIGATE candidates; no allocation.

Return one concise markdown table, then no more than five sentences of portfolio-level commentary. This is research, not an instruction to trade.`;
  }

  function openPrompt(prompt, label) {
    const url = `${CHATGPT}${encodeURIComponent(prompt)}`;
    const opened = window.open(url, '_blank', 'noopener');
    copy(prompt).then(copied => {
      const status = document.getElementById('status-line');
      if (status) status.textContent = `${label}: ChatGPT ${opened ? 'opened with a premade prompt' : 'popup was blocked'}${copied ? '; prompt copied.' : '.'}`;
    });
  }

  window.buildChatGPTPrompt = buildPrompt;
  window.analyseInChatGPT = function analyseV33(id) {
    const c = window.state?.candidates?.find(item => Number(item.id) === Number(id));
    if (c) openPrompt(buildPrompt(c), c.symbol);
  };
  window.analyseInChatGPTPrefilled = window.analyseInChatGPT;

  async function analyseTop(limit, button) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = `Preparing Top ${limit}…`;
    const popup = window.open('about:blank', '_blank');
    try {
      const response = await fetch('/api/oversold/latest', {cache:'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const candidates = [...(data.candidates || [])]
        .sort((a,b) => Number(a.rank ?? 999999)-Number(b.rank ?? 999999))
        .slice(0,limit);
      if (!candidates.length) throw new Error('No candidates available');
      const prompt = buildTopPrompt(candidates);
      await copy(prompt);
      if (popup) popup.location.replace(`${CHATGPT}${encodeURIComponent(prompt)}`);
      else window.open(`${CHATGPT}${encodeURIComponent(prompt)}`, '_blank', 'noopener');
      const status = document.getElementById('status-line');
      if (status) status.textContent = `Top ${candidates.length}: ChatGPT opened with the v3.3 comparison prompt.`;
    } catch (error) {
      popup?.close();
      const status = document.getElementById('status-line');
      if (status) status.textContent = `Top ${limit} analysis failed: ${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function replaceTopButton(limit) {
    const existing = document.getElementById(`analyse-top${limit}`);
    if (!existing || existing.dataset.v33 === 'true') return;
    const replacement = existing.cloneNode(true);
    replacement.dataset.v33 = 'true';
    replacement.title = `Open ChatGPT with the purpose-aligned Top ${limit} evidence comparison`;
    existing.replaceWith(replacement);
    replacement.addEventListener('click', () => analyseTop(limit,replacement));
  }

  replaceTopButton(5);
  replaceTopButton(10);
  setTimeout(() => { replaceTopButton(5); replaceTopButton(10); }, 500);
})();
