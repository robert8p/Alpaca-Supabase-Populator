(() => {
  if (window.__orV35ChatGPTInstalled) return;
  window.__orV35ChatGPTInstalled = true;

  const CHATGPT='https://chatgpt.com/?q=';
  const oldBuilder=window.buildChatGPTPrompt;
  const fmt=(value,digits=1)=>value==null||Number.isNaN(Number(value))?'unknown':Number(value).toFixed(digits);
  const clip=(value,max=180)=>{const text=String(value??'').replace(/\s+/g,' ').trim();return text.length<=max?text:`${text.slice(0,max-1)}…`;};

  async function copy(text){
    try{await navigator.clipboard.writeText(text);return true;}
    catch(_){try{const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();const ok=document.execCommand('copy');area.remove();return ok;}catch(_){return false;}}
  }

  function clusterText(provenance){
    return (provenance.clusters||[]).map(cluster=>
      `cluster ${cluster.cluster_id}: primary=${cluster.is_primary?'yes':'no'} authority=${fmt(cluster.maximum_authority,1)} age=${fmt(cluster.minimum_age_hours,1)}h sources=${(cluster.sources||[]).join(',')||'unknown'} headlines=${(cluster.headlines||[]).map(item=>clip(item,90)).join(' | ')}`
    ).join('\n') || 'No causal provenance clusters retained.';
  }

  function robustnessBlock(c){
    const a=c.catalyst_analysis||{};
    const r=a.robustness_assessment||{};
    const e=r.ensemble||{};
    const p=r.evidence_provenance||{};
    const alignment=r.event_alignment||{};
    const f=r.fundamental_data_quality||{};
    const dependencies=Object.entries(e.component_leave_one_out_drops||{}).sort((x,y)=>Number(y[1])-Number(x[1])).map(([name,value])=>`${name}=${fmt(value,1)}`).join(', ')||'none';
    return `V3.5 ROBUSTNESS — CHALLENGE THE LOWER-BOUND MODEL
Robust score=${fmt(c.reversion_score)}; ensemble median=${fmt(e.ensemble_median)}; p10=${fmt(e.ensemble_p10)}; minimum=${fmt(e.ensemble_minimum)}; maximum=${fmt(e.ensemble_maximum)}; members=${e.ensemble_member_count??0}
Weight stability=${fmt(e.weight_stability_score,0)}; base-weight range=${fmt(e.base_weight_range)}; maximum component dependency=${fmt(e.maximum_component_dependency)}; leave-one-component drops=${dependencies}
Causal provenance clusters=${p.causal_cluster_count??0}; primary clusters=${p.primary_causal_cluster_count??0}; high-quality clusters=${p.high_quality_causal_cluster_count??0}; source dependency risk=${fmt(p.single_cluster_dependency_risk,0)}; leave-one-cluster-out minimum=${p.leave_one_cluster_out_minimum??0}
Event alignment=${fmt(alignment.score,0)}; nearest causal evidence=${fmt(alignment.nearest_causal_age_hours,1)} hours before cutoff
Fundamental-data quality=${fmt(f.score,0)}; source=${f.source||'unknown'}; age=${fmt(f.age_calendar_days,0)} days; required coverage=${fmt(Number(f.required_coverage_ratio||0)*100,0)}%; required available=${(f.available_required_metrics||[]).join(',')||'none'}
Robust evidence confidence=${fmt(r.robust_evidence_confidence,0)}; score caps=${(r.score_caps||[]).map(item=>`${item.type}:${item.cap}`).join(',')||'none'}
Provenance clusters:
${clusterText(p)}`;
  }

  function buildPrompt(c){
    const base=typeof oldBuilder==='function'?oldBuilder(c):`Audit ${c.symbol} as an original Oversold Reversion signal.`;
    return `${base}

${robustnessBlock(c)}

ADDITIONAL V3.5 ROBUSTNESS QUESTIONS
21. Which apparently independent sources are actually copies of one press release or filing root?
22. Does the causal evidence align closely enough to the signal timestamp to explain this specific sell-off?
23. Are the financial metrics relevant to this event, sufficiently current, and internally coherent?
24. Does the verdict survive reasonable changes in economic component weights, or is it model-weight dependent?
25. Does the thesis collapse when the strongest evidence cluster or strongest model component is removed?
26. Is the lower-quartile ensemble still too optimistic or unnecessarily pessimistic given the facts?

Do not treat repeated syndication as independent confirmation. Treat the score as an uncalibrated robust ranking, not a probability. Explicitly state the strongest provenance, timing, financial-quality and model-dependence objection.`;
  }

  function openPrompt(prompt,label){
    const opened=window.open(`${CHATGPT}${encodeURIComponent(prompt)}`,'_blank','noopener');
    copy(prompt).then(copied=>{const status=document.getElementById('status-line');if(status)status.textContent=`${label}: ChatGPT ${opened?'opened with the v3.5 robustness prompt':'popup was blocked'}${copied?'; prompt copied.':'.'}`;});
  }

  window.buildChatGPTPrompt=buildPrompt;
  window.analyseInChatGPT=function analyseV35(id){const c=window.state?.candidates?.find(item=>Number(item.id)===Number(id));if(c)openPrompt(buildPrompt(c),c.symbol);};
  window.analyseInChatGPTPrefilled=window.analyseInChatGPT;

  function topPrompt(candidates){
    const rows=candidates.map((c,index)=>{
      const a=c.catalyst_analysis||{};
      const r=a.robustness_assessment||{};
      const e=r.ensemble||{};
      const p=r.evidence_provenance||{};
      const f=r.fundamental_data_quality||{};
      return `${index+1}. ${c.symbol} ${clip(c.name,50)} | rank=${c.rank??index+1} | move=${fmt(c.drop_pct)}% | robust=${fmt(c.reversion_score)} | median=${fmt(e.ensemble_median)} | p10=${fmt(e.ensemble_p10)} | verdict=${c.model_verdict||'unknown'} | weight_stability=${fmt(e.weight_stability_score,0)} | component_dependency=${fmt(e.maximum_component_dependency)} | causal_roots=${p.causal_cluster_count??0} | source_dependency=${fmt(p.single_cluster_dependency_risk,0)} | event_alignment=${fmt(r.event_alignment?.score,0)} | fundamental_quality=${fmt(f.score,0)} | evidence=${fmt(c.evidence_confidence,0)} | friction=${fmt(a.estimated_round_trip_friction_pct,2)}% | tail=${fmt(a.tail_risk_score,0)} | failed=${(a.failed_eligibility_gates||[]).join(',')||'none'}`;
    }).join('\n');
    return `Independently compare these ${candidates.length} Oversold Reversion candidates using only evidence available at each stored cutoff. The displayed metric is a v3.5 lower-quartile robustness score, not a probability.

${rows}

For each stock give: precise decrease cause; provenance clusters rather than raw source count; event-to-signal timing; economic damage; event-specific financial-data quality; survivability; source-removal and weight-sensitivity risk; realistic execution friction; INVESTIGATE/WATCH/PASS; and a holding period no longer than 3 trading sessions.

Only candidates with Buy-or-better analyst consensus AND an independent INVESTIGATE verdict AND acceptable provenance, event alignment, financial quality, weight stability and execution may receive allocation. Allocate exactly 100.0% across qualifying stocks; all others 0%. If none qualify, state: No Buy-or-better robust INVESTIGATE candidates; no allocation. Keep the response concise and identify the strongest reason not to trade each candidate.`;
  }

  async function analyseTop(limit,button){
    const original=button.textContent;button.disabled=true;button.textContent=`Preparing Top ${limit}…`;const popup=window.open('about:blank','_blank');
    try{const response=await fetch('/api/oversold/latest',{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);const data=await response.json();const candidates=[...(data.candidates||[])].sort((a,b)=>Number(a.rank??999999)-Number(b.rank??999999)).slice(0,limit);if(!candidates.length)throw new Error('No candidates available');const prompt=topPrompt(candidates);await copy(prompt);if(popup)popup.location.replace(`${CHATGPT}${encodeURIComponent(prompt)}`);else window.open(`${CHATGPT}${encodeURIComponent(prompt)}`,'_blank','noopener');const status=document.getElementById('status-line');if(status)status.textContent=`Top ${candidates.length}: ChatGPT opened with the v3.5 robustness comparison.`;}
    catch(error){popup?.close();const status=document.getElementById('status-line');if(status)status.textContent=`Top ${limit} analysis failed: ${error.message}`;}
    finally{button.disabled=false;button.textContent=original;}
  }

  function replace(limit){const existing=document.getElementById(`analyse-top${limit}`);if(!existing||existing.dataset.v35==='true')return;const replacement=existing.cloneNode(true);replacement.dataset.v35='true';replacement.title=`Open ChatGPT with the robust Top ${limit} comparison`;existing.replaceWith(replacement);replacement.addEventListener('click',()=>analyseTop(limit,replacement));}
  replace(5);replace(10);setTimeout(()=>{replace(5);replace(10);},700);
})();
