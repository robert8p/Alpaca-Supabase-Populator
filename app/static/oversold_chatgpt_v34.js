(() => {
  if (window.__orV34ChatGPTInstalled) return;
  window.__orV34ChatGPTInstalled = true;

  const CHATGPT = 'https://chatgpt.com/?q=';
  const oldBuilder = window.buildChatGPTPrompt;
  const fmt = (value,digits=1) => value == null || Number.isNaN(Number(value)) ? 'unknown' : Number(value).toFixed(digits);
  const clip = (value,max=180) => {
    const text = String(value ?? '').replace(/\s+/g,' ').trim();
    return text.length <= max ? text : `${text.slice(0,max-1)}…`;
  };

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch (_) {
      try {
        const area=document.createElement('textarea'); area.value=text; area.style.position='fixed'; area.style.opacity='0';
        document.body.appendChild(area); area.select(); const ok=document.execCommand('copy'); area.remove(); return ok;
      } catch (_) { return false; }
    }
  }

  function reliabilityBlock(c) {
    const r = c.catalyst_analysis?.reliability_assessment || {};
    const relevance = r.evidence_relevance || {};
    const contradiction = r.contradictions || {};
    const friction = r.execution_friction || {};
    const scenarioText = Object.entries(r.scenarios || {}).map(([name,item]) =>
      `${name}: score=${fmt(item.score)} evidence=${fmt(item.confidence,0)} tail=${fmt(item.tail,0)}`
    ).join('\n') || 'No reliability scenarios retained.';
    const unresolved = (contradiction.unresolved || []).map(item =>
      `${item.family}: positive=${clip(item.positive?.[0]?.headline || 'unknown')} | negative=${clip(item.negative?.[0]?.headline || 'unknown')}`
    ).join('\n') || 'none';
    return `V3.4 RELIABILITY — INDEPENDENTLY CHALLENGE THESE ASSUMPTIONS
Base v3.3 score=${fmt(r.base_v33_score)}; conservative score=${fmt(r.conservative_score)}; stability=${fmt(r.stability_score,0)}; stress gate pass rate=${fmt(Number(r.stress_gate_pass_rate || 0)*100,0)}%; score range=${fmt(r.scenario_score_range)}
Adjusted evidence confidence=${fmt(r.adjusted_evidence_confidence,0)}; confidence cap=${fmt(r.evidence_confidence_cap,0)}; primary causal evidence=${relevance.causal_primary_count ?? 0}; independent causal sources=${relevance.causal_independent_sources ?? 0}; high-quality sources=${relevance.high_quality_independent_sources ?? 0}
Contradiction severity=${fmt(contradiction.severity,0)}; unresolved contradictions=${contradiction.unresolved_count ?? 0}; resolved claim sequences=${contradiction.resolved_sequence_count ?? 0}
Estimated round-trip friction=${fmt(friction.estimated_round_trip_friction_pct,2)}%; spread=${fmt(friction.spread_pct,2)}%; one-way slippage proxy=${fmt(friction.one_way_slippage_proxy_pct,2)}%; market cap=${friction.market_cap ?? 'unknown'}
Scenarios:
${scenarioText}
Unresolved contradiction details:
${unresolved}`;
  }

  function buildPrompt(c) {
    const base = typeof oldBuilder === 'function'
      ? oldBuilder(c)
      : `Audit ${c.symbol} as an original Oversold Reversion signal.`;
    return `${base}

${reliabilityBlock(c)}

ADDITIONAL RELIABILITY QUESTIONS
16. Which retained source is actually causal, and which primary records are merely context?
17. Are any apparently contradictory claims genuine conflicts, stale claims or a resolved event sequence?
18. Which downside scenario is most plausible, and is the app's conservative score still too optimistic?
19. Are the spread/slippage and micro-cap assumptions sufficient for a real trade?
20. Would the verdict change if survivability, reversibility or three-session timing were one uncertainty band worse?

Treat the conservative score as a stress-tested ranking—not a forecast or probability. State explicitly when the app is overconfident, underconfident or relying on non-causal evidence.`;
  }

  function openPrompt(prompt,label) {
    const opened=window.open(`${CHATGPT}${encodeURIComponent(prompt)}`,'_blank','noopener');
    copy(prompt).then(copied => {
      const status=document.getElementById('status-line');
      if (status) status.textContent=`${label}: ChatGPT ${opened ? 'opened with the v3.4 reliability prompt' : 'popup was blocked'}${copied ? '; prompt copied.' : '.'}`;
    });
  }

  window.buildChatGPTPrompt=buildPrompt;
  window.analyseInChatGPT=function analyseV34(id) {
    const c=window.state?.candidates?.find(item => Number(item.id)===Number(id));
    if (c) openPrompt(buildPrompt(c),c.symbol);
  };
  window.analyseInChatGPTPrefilled=window.analyseInChatGPT;

  function topPrompt(candidates) {
    const rows=candidates.map((c,index) => {
      const a=c.catalyst_analysis || {};
      const r=a.reliability_assessment || {};
      return `${index+1}. ${c.symbol} ${clip(c.name,55)} | rank=${c.rank ?? index+1} | move=${fmt(c.drop_pct)}% | conservative=${fmt(c.reversion_score)} | base=${fmt(r.base_v33_score)} | verdict=${c.model_verdict || 'unknown'} | stability=${fmt(r.stability_score,0)} | stress_pass=${fmt(Number(r.stress_gate_pass_rate || 0)*100,0)}% | conflict=${fmt(r.contradictions?.severity,0)} | friction=${fmt(r.execution_friction?.estimated_round_trip_friction_pct,2)}% | primary_causal=${r.evidence_relevance?.causal_primary_count ?? 0} | independent_sources=${r.evidence_relevance?.causal_independent_sources ?? 0} | survivability=${fmt(a.survivability_score,0)} | tail=${fmt(a.tail_risk_score,0)} | failed=${(a.failed_eligibility_gates || []).join(',') || 'none'}`;
    }).join('\n');
    return `Independently compare these ${candidates.length} Oversold Reversion candidates using only evidence available at each stored cutoff. The displayed score is a conservative v3.4 scenario score, not a probability.

${rows}

For each stock give: precise decrease cause; causal-vs-context evidence; unresolved contradictions; economic damage; survivability; realistic round-trip execution risk; most plausible downside scenario; analyst consensus with freshness/coverage caveat; INVESTIGATE/WATCH/PASS; and holding period no longer than 3 trading sessions unless the original thesis explicitly supports less.

Only candidates with Buy-or-better analyst consensus AND an independent INVESTIGATE verdict AND acceptable stability/execution may receive allocation. Allocate exactly 100.0% across qualifying stocks; all others 0%. If none qualify, state: No Buy-or-better robust INVESTIGATE candidates; no allocation. Keep the response concise and explain the strongest reason not to trade each candidate.`;
  }

  async function analyseTop(limit,button) {
    const original=button.textContent; button.disabled=true; button.textContent=`Preparing Top ${limit}…`;
    const popup=window.open('about:blank','_blank');
    try {
      const response=await fetch('/api/oversold/latest',{cache:'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data=await response.json();
      const candidates=[...(data.candidates || [])].sort((a,b)=>Number(a.rank ?? 999999)-Number(b.rank ?? 999999)).slice(0,limit);
      if (!candidates.length) throw new Error('No candidates available');
      const prompt=topPrompt(candidates); await copy(prompt);
      if (popup) popup.location.replace(`${CHATGPT}${encodeURIComponent(prompt)}`);
      else window.open(`${CHATGPT}${encodeURIComponent(prompt)}`,'_blank','noopener');
      const status=document.getElementById('status-line');
      if (status) status.textContent=`Top ${candidates.length}: ChatGPT opened with the v3.4 reliability comparison.`;
    } catch (error) {
      popup?.close(); const status=document.getElementById('status-line');
      if (status) status.textContent=`Top ${limit} analysis failed: ${error.message}`;
    } finally { button.disabled=false; button.textContent=original; }
  }

  function replace(limit) {
    const existing=document.getElementById(`analyse-top${limit}`);
    if (!existing || existing.dataset.v34==='true') return;
    const replacement=existing.cloneNode(true); replacement.dataset.v34='true';
    replacement.title=`Open ChatGPT with the stress-tested Top ${limit} comparison`;
    existing.replaceWith(replacement); replacement.addEventListener('click',()=>analyseTop(limit,replacement));
  }
  replace(5); replace(10); setTimeout(()=>{replace(5);replace(10);},700);
})();
