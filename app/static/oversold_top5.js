(() => {
  const runButton = document.getElementById('run');
  if (!runButton) return;

  const statusLine = () => document.getElementById('status-line');
  const fmt = (value, digits = 2) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  const money = (value) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
  const compactMoney = (value) => {
    if (value == null) return 'unknown';
    const n = Number(value);
    const a = Math.abs(n);
    if (a >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (a >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
    return `$${n.toFixed(0)}`;
  };

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      try {
        const el = document.createElement('textarea');
        el.value = text;
        el.setAttribute('readonly', '');
        el.style.position = 'fixed';
        el.style.opacity = '0';
        document.body.appendChild(el);
        el.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(el);
        return ok;
      } catch (_) {
        return false;
      }
    }
  }

  function candidateContext(candidate, index) {
    const flags = (candidate.risk_flags || []).length ? candidate.risk_flags.join(', ') : 'none flagged';
    const news = (candidate.headlines || []).slice(0, 3).map((article, newsIndex) => {
      const parts = [`${newsIndex + 1}. ${article.headline || 'Untitled'}`];
      if (article.source) parts.push(`source: ${article.source}`);
      if (article.created_at) parts.push(`published: ${article.created_at}`);
      if (article.url) parts.push(`url: ${article.url}`);
      return parts.join(' | ');
    }).join('\n') || 'No recent scanner news retained.';

    return `${index + 1}. ${candidate.name || candidate.symbol} (${candidate.symbol})\n` +
      `- Scanner rank: ${candidate.rank ?? index + 1}\n` +
      `- Move vs previous close: ${fmt(candidate.drop_pct, 2)}%\n` +
      `- Last price / previous close: ${money(candidate.last_price)} / ${money(candidate.prev_close)}\n` +
      `- Spread: ${candidate.spread_pct == null ? 'unknown' : fmt(candidate.spread_pct, 2) + '%'}\n` +
      `- Previous-day dollar volume: ${compactMoney(candidate.prev_dollar_volume)}\n` +
      `- Scanner catalyst class / score / triage: ${candidate.catalyst_class || 'U'} / ${candidate.heuristic_score ?? 'unknown'} / ${candidate.triage_label || 'unknown'}\n` +
      `- Risk flags: ${flags}\n` +
      `- Scanner summary: ${candidate.catalyst_summary || 'none'}\n` +
      `- Recent scanner news:\n${news}`;
  }

  function buildPrompt(candidates) {
    const context = candidates.map(candidateContext).join('\n\n');
    return `Independently score and rank these ${candidates.length} Oversold Reversion candidates for a short-horizon mean-reversion strategy.

SCANNER CONTEXT
${context}

RESEARCH RULES
- Use current web research before scoring every stock. Verify the actual reason and timing of the price fall; do not infer the catalyst from the scanner headline alone.
- Prioritise primary sources: company investor relations, SEC filings, regulators, court records and trial registries where relevant. Use reputable secondary sources to fill gaps.
- Treat the scanner rank, class, heuristic score and triage as context only. They MUST NOT anchor or mechanically influence your score.
- Distinguish confirmed facts, reasonable inference and unverified claims.
- Analyst ratings are one confirmation signal, not an eligibility gate. Prefer rating/price-target changes published AFTER the catalyst. Stale pre-event consensus gets little evidential weight.
- If reliable current analyst coverage is unavailable, say "unavailable", give the Analyst Reaction component a neutral 5/10, and reduce Evidence Confidence if that missing evidence matters. Never invent coverage.
- Do not double-count one fact across multiple components. Technical oversold conditions do not prove that a catalyst is temporary.

SCORE EACH STOCK OUT OF 100
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
First return one concise markdown table, sorted by Reversion Score descending, with:
1. Stock (include original scanner rank)
2. Verified cause — max 20 words
3. Reversion Score — X/100
4. Evidence Confidence — X%
5. Analyst Reaction — max 18 words, emphasising post-event changes
6. Verdict — INVESTIGATE / WATCH / PASS
7. Allocated position
8. Holding period — e.g. intraday, 1–2 sessions, 2–3 sessions
9. Key invalidator — max 15 words

ALLOCATION RULES
- Only INVESTIGATE stocks meeting score >=75, confidence >=60%, and no hard veto may receive a non-zero allocation.
- WATCH and PASS receive 0%.
- If at least one stock qualifies, allocate exactly 100.0% in total across qualifying stocks.
- If one qualifies, allocate 100.0%. If several qualify, risk-weight using Reversion Score, Evidence Confidence, liquidity/spread, balance-sheet risk and downside-tail severity; do not automatically split equally.
- If none qualify, allocate 0% to every stock and state immediately below the table: "No INVESTIGATE-grade candidates; no allocation."
- Analyst consensus by itself must never determine eligibility or allocation.

After the table, show the seven-component score breakdown only for the top three stocks, one line per stock, so the ranking is auditable. Keep the answer concise and source-backed. This is research, not an instruction to trade.`;
  }

  async function analyseTop(limit, button) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = `Preparing Top ${limit}…`;
    try {
      const response = await fetch('/api/oversold/latest', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const candidates = [...(data.candidates || [])]
        .sort((a, b) => Number(a.rank ?? 999999) - Number(b.rank ?? 999999))
        .slice(0, limit);
      if (!candidates.length) throw new Error('No candidates are available in the latest scan');

      const prompt = buildPrompt(candidates);
      const copied = await copyText(prompt);
      window.open(`https://chatgpt.com/?q=${encodeURIComponent(prompt)}`, '_blank', 'noopener');
      const status = statusLine();
      if (status) {
        status.textContent = copied
          ? `Top ${candidates.length}: scoring prompt copied; ChatGPT opened in a new tab.`
          : `Top ${candidates.length}: ChatGPT opened. If the prompt is not prefilled, copy the scanner context manually.`;
      }
    } catch (error) {
      const status = statusLine();
      if (status) status.textContent = `Top ${limit} analysis failed: ${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  function addButton(limit, afterElement) {
    const id = `analyse-top${limit}`;
    if (document.getElementById(id)) return afterElement;
    const button = document.createElement('button');
    button.id = id;
    button.className = 'chatgpt-button';
    button.style.marginLeft = '8px';
    button.textContent = `Score Top ${limit} in ChatGPT ↗`;
    button.title = `Open ChatGPT to independently score the latest top ${limit} with the evidence-weighted Oversold Reversion rubric`;
    afterElement.insertAdjacentElement('afterend', button);
    button.addEventListener('click', () => analyseTop(limit, button));
    return button;
  }

  const top5Button = addButton(5, runButton);
  addButton(10, top5Button);
})();
