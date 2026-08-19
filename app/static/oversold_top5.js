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
    return `Briefly analyse these top ${candidates.length} Oversold Reversion candidates from the current scanner.\n\n${context}\n\nUse current web research before answering. Verify the reason for each price fall using reliable sources, prioritising company investor relations, SEC filings and regulators where relevant. For analyst prediction, use the current analyst consensus / price-target direction and recent rating changes; if reliable current analyst coverage is unavailable, say so rather than guessing.\n\nReturn a concise markdown table with one row per stock and these columns:\n1. Stock\n2. Reason for decrease — max 20 words\n3. Analyst prediction — max 20 words; state the current consensus using labels such as Strong Buy, Buy, Hold, Sell, or a clearly equivalent broker-consensus label\n4. Allocated position — % of the total 100% allocation\n5. Recommended holding period — give a specific short-term period such as intraday, 1–2 sessions, or 3–5 sessions\n\nALLOCATION RULES — follow these exactly:\n- Only stocks whose current analyst consensus is Buy or better may receive a non-zero allocation. Treat Strong Buy, Buy, Outperform, Overweight, or a directly equivalent positive consensus as Buy-or-better.\n- Hold/Neutral/Market Perform, Underperform, Sell, or stocks without reliable current analyst consensus must receive 0%.\n- Allocate exactly 100.0% in total across the qualifying Buy-or-better stocks. The non-zero percentages must sum to exactly 100.0%.\n- If one stock qualifies, allocate it 100.0%. If several qualify, use risk-weighted percentages rather than automatically splitting equally.\n- Weight qualifying stocks using catalyst severity, liquidity, spread, dilution/solvency risk, analyst conviction and confidence in the reversion case.\n- If no stocks qualify as Buy-or-better, assign 0% to every analysed stock and state immediately below the table: No Buy-or-better candidates; no allocation.\n\nDo not allocate anything to a stock merely because it is in the scanner ranking. Do not turn a failed short-term reversion into a long-term hold. Keep the entire answer brief and clearly distinguish facts from uncertain analyst expectations.`;
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
          ? `Top ${candidates.length}: brief analysis prompt copied; ChatGPT opened in a new tab.`
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
    button.textContent = `Analyse Top ${limit} in ChatGPT ↗`;
    button.title = `Open ChatGPT to analyse the latest top ${limit} and allocate 100% across Buy-or-better candidates`;
    afterElement.insertAdjacentElement('afterend', button);
    button.addEventListener('click', () => analyseTop(limit, button));
    return button;
  }

  const top5Button = addButton(5, runButton);
  addButton(10, top5Button);
})();
