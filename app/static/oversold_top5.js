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

  function candidateContext(c, index) {
    const flags = (c.risk_flags || []).length ? c.risk_flags.join(', ') : 'none flagged';
    const legacy = c.model_run_id == null;
    return `${index+1}. ${c.name || c.symbol} (${c.symbol})\n` +
      `- App rank: ${c.rank ?? index+1}\n` +
      `- Signal timestamp / evidence cutoff: ${c.signal_timestamp || c.created_at || 'unknown'} / ${c.evidence_cutoff || c.created_at || 'unknown'}\n` +
      `- Signal price: ${c.signal_price == null ? money(c.last_price) : money(c.signal_price)}\n` +
      `- Move vs previous close: ${fmt(c.drop_pct,2)}%\n` +
      `- Spread: ${c.spread_pct == null ? 'unknown' : fmt(c.spread_pct,2)+'%'}\n` +
      (legacy
        ? `- Legacy row only: heuristic score ${c.heuristic_score ?? 'unknown'}; v2 component history unavailable and must not be invented.\n`
        : `- Reversion Score: ${fmt(c.reversion_score,1)}/100 (UNCALIBRATED; not a probability)\n` +
          `- Components: Setup ${fmt(c.setup_score,1)} | Catalyst ${fmt(c.catalyst_score,1)} | Resilience ${fmt(c.resilience_score,1)} | Damage ${fmt(c.damage_risk,1)} | Confirmation ${fmt(c.confirmation_score,1)} | Confidence ${fmt(c.evidence_confidence,1)}\n` +
          `- App verdict: ${c.model_verdict || 'unknown'} | hard veto: ${c.hard_veto ? 'yes - '+(c.hard_veto_reason || 'unspecified') : 'no'}\n` +
          `- Model/config: ${c.scoring_model_version || 'unknown'} / ${c.scoring_config_version || 'unknown'}\n`) +
      `- Catalyst class / summary: ${c.catalyst_class || 'U'} / ${c.catalyst_summary || 'none'}\n` +
      `- Risk flags: ${flags}\n` +
      `- Point-in-time evidence:\n${evidenceNews(c)}`;
  }

  function buildPrompt(candidates) {
    const context = candidates.map(candidateContext).join('\n\n');
    return `Audit and compare these ${candidates.length} Oversold Reversion candidates using the SAME canonical scoring contract and SAME point-in-time evidence window as the app.

STRATEGY TARGET
Ground truth is whether each stock subsequently trades at least +5% above its stored signal price within six weeks. App scores shown below are currently UNCALIBRATED ranking scores, not probabilities.

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

COMPONENT MEANINGS
- Setup: point-in-time market dislocation/tradability; a larger crash is not automatically better.
- Catalyst: likelihood the cause is temporary, misunderstood, survivable or materially over-discounted within six weeks.
- Fundamental Resilience: ability to absorb the event without destroying equity value.
- Confirmation: point-in-time selling exhaustion/stabilisation/reversal.
- Damage Risk: permanent structural impairment; asymmetric gate.
- Evidence Confidence: completeness/reliability of evidence.

TASK
1. For each stock, state whether the app's primary-cause attribution is VERIFIED or UNVERIFIED using cutoff-valid evidence only.
2. Audit each component as AGREE / TOO HIGH / TOO LOW / INSUFFICIENT EVIDENCE. Do not invent missing inputs.
3. Identify the strongest evidence for and against reversion.
4. State whether the app verdict is defensible.
5. Rank the candidates by the quality of the ORIGINAL six-week +5% reversion setup, not by hindsight.

OUTPUT
Return one concise markdown table sorted by your audited attractiveness with columns:
- Stock (app rank)
- App Reversion Score
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

After the table, list only material app-vs-audit disagreements and the evidence causing them. This is research, not an instruction to trade.`;
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
      if (status) status.textContent = copied ? `Top ${candidates.length}: point-in-time audit prompt copied; ChatGPT opened.` : `Top ${candidates.length}: ChatGPT opened. If the prompt is not prefilled, copy the scanner context manually.`;
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
    button.title=`Audit the latest top ${limit} against their stored Evidence Snapshots and the canonical app scoring contract`;
    afterElement.insertAdjacentElement('afterend',button);
    button.addEventListener('click',()=>analyseTop(limit,button));
    return button;
  }
  const top5Button=addButton(5,runButton);
  addButton(10,top5Button);
})();
