(() => {
  const runButton = document.getElementById('run');
  if (!runButton) return;
  const statusLine = () => document.getElementById('status-line');
  const fmt = (value, digits = 2) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  const money = (value) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch (_) {
      try {
        const el = document.createElement('textarea'); el.value = text; el.setAttribute('readonly','');
        el.style.position='fixed'; el.style.opacity='0'; document.body.appendChild(el); el.select();
        const ok = document.execCommand('copy'); document.body.removeChild(el); return ok;
      } catch (_) { return false; }
    }
  }

  function evidenceNews(candidate) {
    const articles = Array.isArray(candidate.evidence_news) ? candidate.evidence_news : (candidate.headlines || []);
    return articles.slice(0,10).map((article, idx) => {
      const parts = [`${idx+1}. ${article.headline || 'Untitled'}`];
      if (article.source) parts.push(`source: ${article.source}`);
      if (article.created_at || article.published_at) parts.push(`published: ${article.created_at || article.published_at}`);
      if (article.summary) parts.push(`summary: ${article.summary}`);
      if (article.url) parts.push(`url: ${article.url}`);
      return parts.join(' | ');
    }).join('\n') || 'No company-specific news retained in the point-in-time Evidence Snapshot.';
  }

  function technicalBrief(c) {
    const trace = c.calculation_trace || {};
    const tech = (trace.setup || {}).technical_features || {};
    const confirm = (trace.confirmation || {}).technical_features || {};
    return `- Technical evidence: shock z ${fmt(tech.shock_z,2)} | ATR move ${fmt(tech.atr_move_multiple,2)}x | RSI14 ${fmt(tech.rsi14,1)} | SMA20 ${fmt(tech.sma20_distance_pct,1)}% | SMA50 ${fmt(tech.sma50_distance_pct,1)}% | 60d drawdown ${fmt(tech.drawdown_from_60d_high_pct,1)}% | rel-volume ${fmt(tech.relative_volume20,2)}x | SPY-relative ${fmt(tech.market_relative_move_pct,1)}% | ${tech.sector_benchmark || 'sector'}-relative ${fmt(tech.sector_relative_move_pct,1)}%\n` +
      `- Confirmation evidence: range position ${fmt(confirm.session_range_position ?? tech.session_range_position,1)}% | gap reclaim ${fmt(confirm.gap_reclaim_pct ?? tech.gap_reclaim_pct,1)}% | low reclaim ${fmt(confirm.low_reclaim_pct ?? tech.low_reclaim_pct,1)}% | VWAP distance ${fmt(confirm.vwap_distance_pct ?? tech.vwap_distance_pct,1)}%`;
  }

  function fundamentalBrief(c) {
    const a = c.catalyst_analysis || {};
    const f = a.fundamental_trace || {};
    const raw = f.raw_metrics || {};
    if (!f.available) return '- Point-in-time fundamentals: unavailable; Resilience must remain conservative and this is explicit uncertainty.';
    return `- Point-in-time fundamentals (${f.form || 'filing'}, available ${f.available_from || 'unknown'}): revenue YoY ${raw.revenue_yoy == null ? 'unknown' : fmt(Number(raw.revenue_yoy)*100,1)+'%'} | net margin ${raw.net_margin == null ? 'unknown' : fmt(Number(raw.net_margin)*100,1)+'%'} | diluted shares YoY ${raw.diluted_shares_yoy == null ? 'unknown' : fmt(Number(raw.diluted_shares_yoy)*100,1)+'%'} | cash/assets ${raw.cash_to_assets == null ? 'unknown' : fmt(Number(raw.cash_to_assets)*100,1)+'%'} | liabilities/assets ${raw.liabilities_to_assets == null ? 'unknown' : fmt(Number(raw.liabilities_to_assets)*100,1)+'%'}`;
  }

  function evidenceQuality(c) {
    const a = c.catalyst_analysis || {};
    const q = a.evidence_quality_trace || {};
    return `- Evidence quality: ${q.independent_source_count ?? 'unknown'} independent source(s) | authoritative/direct source ${q.authoritative_source_present ? 'yes' : 'no'} | freshest ${q.freshest_age_hours == null ? 'unknown' : fmt(q.freshest_age_hours,1)+'h'} | conflict ${q.conflicting_evidence ? 'yes' : 'no'} | missing ${(c.missing_inputs || []).join(', ') || 'none flagged'}`;
  }

  function candidateContext(c, index) {
    const flags = (c.risk_flags || []).length ? c.risk_flags.join(', ') : 'none flagged';
    const legacy = c.model_run_id == null;
    const a = c.catalyst_analysis || {};
    const isCalibrated = c.model_status === 'calibrated' && c.calibrated_probability != null;
    const scoreLine = isCalibrated
      ? `- Reversion Probability: ${fmt(Number(c.calibrated_probability)*100,1)}% | raw score ${fmt(c.reversion_score,1)}/100\n`
      : `- Reversion Score: ${fmt(c.reversion_score,1)}/100 (UNCALIBRATED; not a probability)\n`;
    return `${index+1}. ${c.name || c.symbol} (${c.symbol})\n` +
      `- App rank: ${c.rank ?? index+1}\n` +
      `- Signal timestamp / evidence cutoff: ${c.signal_timestamp || c.created_at || 'unknown'} / ${c.evidence_cutoff || c.created_at || 'unknown'}\n` +
      `- Signal price: ${c.signal_price == null ? money(c.last_price) : money(c.signal_price)}\n` +
      `- Move vs previous close: ${fmt(c.drop_pct,2)}% | spread ${c.spread_pct == null ? 'unknown' : fmt(c.spread_pct,2)+'%'}\n` +
      (legacy
        ? `- Legacy row only: heuristic score ${c.heuristic_score ?? 'unknown'}; current component history unavailable and must not be invented.\n`
        : scoreLine +
          `- Components: Setup ${fmt(c.setup_score,1)} | Catalyst ${fmt(c.catalyst_score,1)} | Resilience ${fmt(c.resilience_score,1)} | Damage ${fmt(c.damage_risk,1)} | Confirmation ${fmt(c.confirmation_score,1)} | Confidence ${fmt(c.evidence_confidence,1)}\n` +
          `- App verdict: ${c.model_verdict || 'unknown'} | hard veto: ${c.hard_veto ? 'yes - '+(c.hard_veto_reason || 'unspecified') : 'no'}\n` +
          `- Event profile: ${a.event_profile || a.catalyst_type || 'unknown'} | cause verified: ${a.cause_verified ? 'yes' : 'no'}\n` +
          `- Model/config: ${c.scoring_model_version || 'unknown'} / ${c.scoring_config_version || 'unknown'}\n` +
          `${technicalBrief(c)}\n${fundamentalBrief(c)}\n${evidenceQuality(c)}\n`) +
      `- Catalyst class / summary: ${c.catalyst_class || 'U'} / ${c.catalyst_summary || 'none'}\n` +
      `- Risk flags: ${flags}\n` +
      `- Point-in-time news:\n${evidenceNews(c)}`;
  }

  function buildPrompt(candidates) {
    const context = candidates.map(candidateContext).join('\n\n');
    return `Audit and compare these ${candidates.length} Oversold Reversion candidates using the SAME canonical scoring contract and SAME point-in-time evidence window as the app.

STRATEGY TARGET
Ground truth is whether each stock subsequently trades at least +5% above its stored signal price within six weeks. A raw Reversion Score is not a probability unless a passed calibration was already active at that signal time.

STRICT EVIDENCE RULE
For EACH stock, use only information available on or before that stock's stated evidence cutoff. Do not use later news, later price action, later analyst revisions, later filings, or knowledge of the eventual outcome to judge the original signal. If later information is known to you, ignore it. Do not browse for post-cutoff evidence.

CANDIDATES / STORED EVIDENCE
${context}

CANONICAL APP CONTRACT
Core = 0.25×Setup + 0.35×Catalyst + 0.15×Fundamental Resilience + 0.25×Confirmation.
ConfidenceAdjusted = 50 + ((Core - 50) × EvidenceConfidence / 100). Confidence is reliability, not attractiveness.
DamagePenalty = min(15, max(0, DamageRisk - 25) × 0.20).
Damage caps: 0–29→100; 30–49→85; 50–69→65; 70–84→40; 85–100→20.
Unverified principal cause: Catalyst cap 35, final cap 60, verdict max WATCH.
Verified existential/solvency/core-thesis failure may hard-veto to PASS.
INVESTIGATE: final score >=75 with verified cause and no hard veto. WATCH: score >=55 or unresolved evidence. PASS: score <55 or hard veto.
Analyst consensus is supporting evidence only; post-event analyst action may inform Catalyst evidence but ratings are not a standalone score.

V3 COMPONENT MEANINGS
- Setup: point-in-time statistical dislocation using raw decline, volatility shock, ATR move, RSI, moving-average deviation, recent-high drawdown, volume anomaly, market/sector-relative move and tradability. Larger crash alone is not better.
- Catalyst: verified event economics and six-week reversibility, not sentiment; guidance resets, financing, trial/FDA outcomes and solvency are differentiated explicitly.
- Fundamental Resilience: cutoff-valid periodic filing evidence where available; missing fundamentals are uncertainty rather than a neutral-high default.
- Confirmation: range position, intraday reversal, gap reclaim, VWAP, volume and spread at the cutoff.
- Damage Risk: structural/economic impairment; asymmetric gate.
- Evidence Confidence: independent-source quality/freshness plus market/fundamental evidence completeness. Repeated stories from one publisher are not independent evidence.

TASK
1. For each stock, state whether the app's primary-cause attribution is VERIFIED or UNVERIFIED using cutoff-valid evidence only.
2. Audit each component as AGREE / TOO HIGH / TOO LOW / INSUFFICIENT EVIDENCE. Do not invent missing inputs.
3. Explicitly audit the volatility-adjusted Setup and the fundamental-data gap/strength, not just the headline narrative.
4. Identify the strongest evidence for and against reversion.
5. State whether the app verdict is defensible.
6. Rank the candidates by the quality of the ORIGINAL six-week +5% reversion setup, not by hindsight.

OUTPUT
Return one concise markdown table sorted by audited attractiveness with columns:
- Stock (app rank)
- App Reversion metric
- Cause status + cause (max 20 words)
- Component disagreement (max 25 words)
- Damage assessment
- Evidence confidence assessment
- App verdict defensible? yes/no
- Audited verdict: INVESTIGATE / WATCH / PASS
- Allocated position
- Key invalidator (max 15 words)

ALLOCATION RULES
- Only stocks that remain INVESTIGATE-grade under the canonical rules may receive a non-zero allocation.
- WATCH/PASS receive 0%.
- If at least one qualifies, allocate exactly 100.0% across qualifying stocks, risk-weighted rather than automatically equal.
- If none qualify, allocate 0% to all and state: "No INVESTIGATE-grade candidates; no allocation."
- Do not use analyst consensus as an allocation gate.

After the table, list only material app-vs-audit disagreements and the cutoff-valid evidence causing them. This is research, not an instruction to trade.`;
  }

  async function analyseTop(limit, button) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = `Preparing Top ${limit}…`;
    try {
      const response = await fetch('/api/oversold/latest', {cache:'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const candidates = [...(data.candidates || [])]
        .sort((a,b) => Number(a.rank ?? 999999) - Number(b.rank ?? 999999))
        .slice(0,limit);
      if (!candidates.length) throw new Error('No candidates are available in the latest scan');
      const prompt = buildPrompt(candidates);
      const copied = await copyText(prompt);
      window.open(`https://chatgpt.com/?q=${encodeURIComponent(prompt)}`, '_blank', 'noopener');
      const status = statusLine();
      if (status) status.textContent = copied ? `Top ${candidates.length}: point-in-time v3 audit prompt copied; ChatGPT opened.` : `Top ${candidates.length}: ChatGPT opened. If the prompt is not prefilled, copy the scanner context manually.`;
    } catch (error) {
      const status = statusLine(); if (status) status.textContent = `Top ${limit} analysis failed: ${error.message}`;
    } finally { button.disabled=false; button.textContent=originalText; }
  }

  function addButton(limit, afterElement) {
    const id = `analyse-top${limit}`;
    if (document.getElementById(id)) return afterElement;
    const button = document.createElement('button');
    button.id=id; button.className='chatgpt-button'; button.style.marginLeft='8px';
    button.textContent=`Audit Top ${limit} in ChatGPT ↗`;
    button.title=`Audit the latest top ${limit} against their stored v3 Evidence Snapshots and the canonical app scoring contract`;
    afterElement.insertAdjacentElement('afterend',button);
    button.addEventListener('click',()=>analyseTop(limit,button));
    return button;
  }
  const top5Button=addButton(5,runButton);
  addButton(10,top5Button);
})();