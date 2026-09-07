(() => {
  if (window.__orV39ChatGPTInstalled) return;
  window.__orV39ChatGPTInstalled = true;
  const CHATGPT='https://chatgpt.com/?q=';
  const RULES='/static/oversold_audit_rules.txt?v=39';
  const fmt=(v,d=1)=>v==null||!Number.isFinite(Number(v))?'unknown':Number(v).toFixed(d);
  const clip=(v,n=220)=>String(v??'unknown').replace(/\s+/g,' ').slice(0,n);
  const fallback='Audit original signals only at each stated cutoff. If cutoff or dated evidence is missing, do not reconstruct facts. Scores are uncalibrated, not probabilities. Require independently verified Buy-or-better as-of consensus, INVESTIGATE, provenance, event timing, financial impact, stability and execution before hypothetical allocation. Unknowns get 0%. Maximum hold 3 exchange trading sessions. If none qualify: No Buy-or-better robust INVESTIGATE candidates; no allocation.';
  let rules=fallback;
  const ready=fetch(RULES,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.text();}).then(text=>{rules=text;}).catch(()=>{});
  const analysis=c=>c.catalyst_analysis||{};
  function row(c,index){
    const a=analysis(c),r=a.robustness_assessment||{},e=r.ensemble||{},p=r.declared_origin_provenance||r.evidence_provenance||{};
    const source=r.source_removal||{},execution=a.execution_audit||{};
    const cutoff=c.evidence_cutoff||c.evidence_snapshot?.evidence_cutoff||a.evidence_integrity?.cutoff||'MISSING';
    return `${index+1}. ${c.symbol} ${clip(c.name,50)} | model=${c.scoring_model_version||'unknown'} | snapshot=${c.evidence_snapshot_id||'unknown'} | cutoff=${cutoff} | signal=${c.signal_timestamp||'unknown'}\n`+
      `move=${fmt(c.drop_pct)}%; score=${fmt(c.reversion_score??c.final_score)}; p10=${fmt(e.ensemble_p10)}; p25=${fmt(e.robust_lower_score)}; median=${fmt(e.ensemble_median)}; basis=${e.quantile_basis||'LEGACY MIXED / UNVERIFIED'}; app=${c.model_verdict||c.verdict||'unknown'}\n`+
      `weights=${fmt(e.weight_stability_score,0)} (${e.weight_sensitivity_status||'legacy clipped proxy'}); raw range=${fmt(e.base_weight_range)}; component adverse drop=${fmt(e.maximum_component_dependency)}; stress=${e.scenario_policy_pass_count??'untested'}/${e.scenario_policy_denominator??'unknown'}; source test=${source.status||'NOT RUN'} worst=${fmt(source.worst_score)} max loss=${fmt(source.maximum_score_drop)}\n`+
      `article recency index=${fmt(r.event_alignment?.score,0)}; event timing=${JSON.stringify(a.event_context||{timing_status:'UNKNOWN'})}; accounts coverage=${fmt(r.fundamental_data_quality?.score,0)}; financial-strength index=${fmt(a.survivability_score)}; tail=${fmt(a.tail_risk_score)}\n`+
      `friction proxy=${fmt(a.estimated_round_trip_friction_pct,2)}%; execution=${JSON.stringify(execution)}; as-of analyst consensus=NOT VERIFIED IN EXPORT; unique model failures=${[...new Set(a.failed_eligibility_gates||[])].join(',')||'none reported'}\n`+
      `Provenance: ${JSON.stringify(p.clusters||[])}\nRetained claims: ${JSON.stringify((a.source_claims||[]).slice(0,8))}`;
  }
  function build(candidates){return `${rules}\n\n${candidates.map(row).join('\n\n')}`;}
  window.buildChatGPTPrompt=c=>build([c]);
  window.buildOversoldComparisonPrompt=build;
  async function copy(text){
    try{await navigator.clipboard.writeText(text);return true;}catch(_){
      try{const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();let ok=false;try{ok=document.execCommand('copy');}finally{area.remove();}return ok;}catch(_){return false;}
    }
  }
  async function launch(candidates,popup){
    await ready;
    const full=build(candidates),copied=await copy(full);
    // Never silently delete cutoffs/gates merely to fit a deep link.
    const compact=`${fallback}\nThis is a compact handoff; the full frozen-evidence audit was copied. Do not invent missing evidence.\n`+candidates.map((c,i)=>`${i+1}. ${c.symbol}; model=${c.scoring_model_version||'unknown'}; cutoff=${c.evidence_cutoff||c.evidence_snapshot?.evidence_cutoff||analysis(c).evidence_integrity?.cutoff||'MISSING'}; score=${fmt(c.reversion_score??c.final_score)}; verdict=${c.model_verdict||c.verdict||'unknown'}`).join('\n');
    const sent=full.length<=12000?full:compact;
    if(popup){popup.opener=null;popup.location.replace(CHATGPT+encodeURIComponent(sent));}
    const status=document.getElementById('status-line');
    if(status)status.textContent=sent===full?`Point-in-time audit ${popup?'opened':'copied; popup blocked'}.`:`Compact handoff opened. ${copied?'Full evidence copied: paste it into the chat before analysis.':'Clipboard unavailable; use the exported evidence before analysis.'}`;
  }
  window.analyseInChatGPT=function(id){const c=window.state?.candidates?.find(x=>Number(x.id)===Number(id));if(c){const popup=window.open('about:blank','_blank');launch([c],popup).catch(error=>{popup?.close();const status=document.getElementById('status-line');if(status)status.textContent=`Audit export failed: ${error.message}`;});}};
  window.analyseInChatGPTPrefilled=window.analyseInChatGPT;
  function replace(limit){
    const old=document.getElementById(`analyse-top${limit}`);if(!old||old.dataset.v39)return;
    const button=old.cloneNode(true);button.dataset.v39='true';button.dataset.v35='true';old.replaceWith(button);
    button.addEventListener('click',async()=>{
      const popup=window.open('about:blank','_blank');button.disabled=true;
      try{const response=await fetch('/api/oversold/latest',{cache:'no-store'});if(!response.ok)throw Error(`HTTP ${response.status}`);const data=await response.json();const candidates=[...(data.candidates||[])].sort((a,b)=>Number(a.rank??999999)-Number(b.rank??999999)).slice(0,limit);if(!candidates.length)throw Error('No candidates');await launch(candidates,popup);}
      catch(error){popup?.close();const status=document.getElementById('status-line');if(status)status.textContent=`Audit export failed: ${error.message}`;}finally{button.disabled=false;}
    });
  }
  replace(5);replace(10);setTimeout(()=>{replace(5);replace(10);},700);
})();
