(() => {
  const fmtScore = (value, digits = 2) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  const moneyScore = (value) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
  const compactMoneyScore = (value) => {
    if (value == null) return 'unknown';
    const n = Number(value);
    const a = Math.abs(n);
    if (a >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (a >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
    return `$${n.toFixed(0)}`;
  };

  function buildOptimizedChatGPTPrompt(c) {
    const news = (c.headlines || []).map((article, index) => {
      const parts = [`${index + 1}. ${article.headline || 'Untitled'}`];
      if (article.source) parts.push(`Source: ${article.source}`);
      if (article.created_at) parts.push(`Published: ${article.created_at}`);
      if (article.summary) parts.push(`Summary: ${article.summary}`);
      if (article.url) parts.push(`URL: ${article.url}`);
      return parts.join('\n   ');
    }).join('\n\n') || 'No recent company-specific news was retained by the scanner.';

    const flags = (c.risk_flags || []).length ? c.risk_flags.join(', ') : 'none flagged';
    const commentary = c.review_notes
      ? `\n- Reviewer commentary (treat as a hypothesis, not evidence): ${c.review_notes}`
      : '';

    return `Independently score ${c.name || c.symbol} (${c.symbol}) as a short-horizon Oversold Reversion candidate.

SCANNER CONTEXT
- Current move versus previous close: ${fmtScore(c.drop_pct, 2)}%
- Last price: ${moneyScore(c.last_price)}
- Previous close: ${moneyScore(c.prev_close)}
- Bid/ask spread: ${c.spread_pct == null ? 'unknown' : fmtScore(c.spread_pct, 2) + '%'}
- Previous-day dollar volume: ${compactMoneyScore(c.prev_dollar_volume)}
- Scanner catalyst class: ${c.catalyst_class || 'U'}
- Scanner heuristic score: ${c.heuristic_score ?? 'unknown'}/100
- Scanner triage: ${c.triage_label || 'unknown'}
- Risk flags: ${flags}
- Scanner summary: ${c.catalyst_summary || 'none'}${commentary}

RECENT SCANNER NEWS
${news}

RESEARCH RULES
- Use current web research before scoring. Verify the actual reason and timing of the price fall; do not infer the catalyst from the scanner headline alone.
- Prioritise primary sources: company investor relations, SEC filings, regulators, court records and trial registries where relevant. Use reputable secondary sources to fill gaps.
- Treat the scanner class, heuristic score and triage as context only. They MUST NOT anchor or mechanically influence your score.
- Distinguish confirmed facts, reasonable inference and unverified claims.
- Analyst ratings are one confirmation signal, not an eligibility gate. Prefer rating/price-target changes published AFTER the catalyst. Stale pre-event consensus gets little evidential weight.
- If reliable current analyst coverage is unavailable, say "unavailable", give the Analyst Reaction component a neutral 5/10, and reduce Evidence Confidence if that missing evidence matters. Never invent coverage.
- Do not double-count one fact across multiple components. Technical oversold conditions do not prove that a catalyst is temporary.

SCORE OUT OF 100
1. Catalyst reversibility / transience: 0–25
   High = clearly temporary, operational, technical or timing-related. Low = durable thesis impairment, terminal asset failure or existential event.
2. Price dislocation vs justified intrinsic-value impairment: 0–20
   High = observed fall materially exceeds plausible permanent value damage. Low = price move broadly matches or understates fundamental damage.
3. Fundamental resilience: 0–15
   Balance sheet, cash runway, financing need, dilution, solvency, business concentration and ability to absorb the shock.
4. Evidence quality & causal attribution: 0–10
   Primary-source confirmation, clear timeline and confidence that the identified event actually caused the fall.
5. Post-event analyst reaction: 0–10
   High = analysts explicitly reiterate constructive views/targets after reviewing the event. Low = downgrades or material target cuts. Stale consensus alone is weak evidence.
6. Technical / execution quality: 0–10
   Liquidity, spread, tradability and evidence of a genuine dislocation. Do not reward illiquidity merely because the percentage fall is large.
7. Near-term reversion path: 0–10
   Credible mechanism for recovery within roughly 1–3 trading sessions, or a clearly identified short-term event that can resolve uncertainty.

The seven component scores MUST sum exactly to the Reversion Score / 100.

DECISION RULES
- INVESTIGATE: Reversion Score >=75, Evidence Confidence >=60%, and no hard veto.
- WATCH: Reversion Score 55–74; OR score >=75 but Evidence Confidence <60%; OR a key fact remains unresolved.
- PASS: Reversion Score <55 or a hard veto applies.
- If the cause of the fall cannot be independently verified, cap Reversion Score at 60 and the verdict at WATCH.
- Hard-veto PASS examples: durable thesis-breaking impairment whose magnitude broadly explains the fall; acute going-concern/solvency risk; near-term financing/dilution risk that dominates the reversion case; fraud/regulatory/existential event; terminal failure of the core value driver without a credible recovery path.
- Do not convert a failed short-term reversion into a long-term investment thesis.

OUTPUT
1. Verified cause: one sentence with event date/time where available.
2. A markdown scorecard with columns Component | Score | Evidence, listing all seven components.
3. Reversion Score: X/100.
4. Evidence Confidence: X%.
5. Analyst Reaction: explicitly separate post-event changes from stale pre-event consensus; state unavailable if necessary.
6. Strongest evidence FOR reversion and strongest evidence AGAINST it.
7. Verdict: INVESTIGATE / WATCH / PASS, followed by the key reason.
8. Expected reversion window and the single most important invalidator.

Keep it concise, source-backed and auditable. This is research, not an instruction to trade.`;
  }

  window.buildChatGPTPrompt = buildOptimizedChatGPTPrompt;

  function relabelRowButtons() {
    document.querySelectorAll('#rows .chatgpt-button').forEach((button) => {
      button.textContent = 'Score ↗';
      button.title = 'Open ChatGPT to independently score this stock with the evidence-weighted Oversold Reversion rubric';
      const helper = button.parentElement && button.parentElement.querySelector('.muted');
      if (helper) helper.textContent = 'web + score';
    });
  }

  relabelRowButtons();
  const rows = document.getElementById('rows');
  if (rows) {
    new MutationObserver(relabelRowButtons).observe(rows, { childList: true, subtree: true });
  }
})();
