(() => {
  if (window.__orV35RobustnessUiInstalled) return;
  window.__orV35RobustnessUiInstalled = true;

  const style = document.createElement('style');
  style.textContent = `
    .or-robust-badge { color:#dff5e7; border-color:#4f8061; background:#15291c; }
    .or-robust-warn { color:#ffe6ae; border-color:#8e6a2b; background:#332714; }
    .or-robust-risk { color:#ffd0d0; border-color:#8c4242; background:#351919; }
    .or-robust-grid { display:grid; grid-template-columns:repeat(4,minmax(105px,1fr)); gap:6px; margin-top:7px; }
    .or-robust-metric { border:1px solid var(--line); border-radius:6px; padding:7px; background:#0b1116; }
    .or-robust-metric span { display:block; color:var(--muted); font-size:9px; text-transform:uppercase; }
    .or-robust-metric strong { display:block; margin-top:2px; font-size:14px; }
    .or-cluster-list { display:grid; gap:5px; margin-top:7px; }
    .or-cluster-row { padding:6px 7px; border:1px solid var(--line); border-radius:6px; background:#0b1116; font-size:10px; }
    @media(max-width:900px){ .or-robust-grid{grid-template-columns:repeat(2,minmax(105px,1fr));} }
  `;
  document.head.appendChild(style);

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'
  }[char]));
  const num = (value,digits=1) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);

  function candidateForRow(row) {
    const id=Number(row.dataset.candidateId || 0);
    if (id) {
      const candidate=window.state?.candidates?.find(item=>Number(item.id)===id);
      if (candidate) return candidate;
    }
    const symbol=row.querySelector('.symbol')?.textContent?.trim();
    return window.state?.candidates?.find(item=>String(item.symbol)===symbol) || null;
  }

  function metric(label,value,suffix='') {
    return `<div class="or-robust-metric"><span>${esc(label)}</span><strong>${esc(value)}${suffix}</strong></div>`;
  }

  function clusterRows(provenance) {
    return (provenance.clusters || []).map(cluster =>
      `<div class="or-cluster-row"><strong>Cluster ${esc(cluster.cluster_id)}</strong> · ${cluster.is_primary ? 'primary' : 'secondary'} · authority ${num(cluster.maximum_authority,1)} · age ${num(cluster.minimum_age_hours,1)}h<br><span class="or-meta">${esc((cluster.sources || []).join(', ') || 'unknown source')} · ${esc((cluster.headlines || []).join(' | '))}</span></div>`
    ).join('') || '<div class="or-meta">No causal provenance cluster retained.</div>';
  }

  function enhanceRow(row) {
    const candidate=candidateForRow(row);
    const cell=row.querySelector('.or-model-score-cell');
    const robustness=candidate?.catalyst_analysis?.robustness_assessment;
    if (!candidate || !cell || !robustness) return;
    const ensemble=robustness.ensemble || {};
    const provenance=robustness.evidence_provenance || {};
    const alignment=robustness.event_alignment || {};
    const fundamentals=robustness.fundamental_data_quality || {};
    const key=[candidate.id,candidate.model_run_id,candidate.reversion_score,ensemble.ensemble_median,provenance.causal_cluster_count].join(':');
    if (cell.dataset.v35RobustnessKey===key) return;
    cell.dataset.v35RobustnessKey=key;

    const name=cell.querySelector('.or-score-name');
    if (name && candidate.model_status!=='calibrated') name.textContent='Robust Opportunity';

    const badges=cell.querySelector('.or-model-badges');
    if (badges) {
      badges.querySelectorAll('[data-v35-badge]').forEach(element=>element.remove());
      const badgesData=[
        [`Median ${num(ensemble.ensemble_median,1)}`,'or-robust-badge'],
        [`Weights ${num(ensemble.weight_stability_score,0)}`,Number(ensemble.weight_stability_score)>=70?'or-robust-badge':'or-robust-warn'],
        [`Causal roots ${provenance.causal_cluster_count ?? 0}`,Number(provenance.causal_cluster_count)>=2?'or-robust-badge':'or-robust-warn'],
        [`Alignment ${num(alignment.score,0)}`,Number(alignment.score)>=60?'or-robust-badge':'or-robust-warn'],
        [`Fund. quality ${num(fundamentals.score,0)}`,Number(fundamentals.score)>=60?'or-robust-badge':'or-robust-warn'],
      ];
      for (const [text,klass] of badgesData) {
        const badge=document.createElement('span');
        badge.dataset.v35Badge='true';
        badge.className=`or-mini-badge ${klass}`;
        badge.textContent=text;
        badges.appendChild(badge);
      }
    }

    const body=cell.querySelector('.or-detail-body');
    if (!body) return;
    let section=body.querySelector('.or-v35-robustness-section');
    if (!section) {
      section=document.createElement('div');
      section.className='or-detail-section or-v35-robustness-section';
      body.insertAdjacentElement('afterbegin',section);
    }
    section.innerHTML=`
      <b>v3.5 robust ensemble</b>
      <div class="or-robust-grid">
        ${metric('Robust lower score',num(ensemble.robust_lower_score,1))}
        ${metric('Ensemble median',num(ensemble.ensemble_median,1))}
        ${metric('Ensemble p10',num(ensemble.ensemble_p10,1))}
        ${metric('Worst member',num(ensemble.ensemble_minimum,1))}
        ${metric('Weight stability',num(ensemble.weight_stability_score,0))}
        ${metric('Component dependency',num(ensemble.maximum_component_dependency,1))}
        ${metric('Causal roots',provenance.causal_cluster_count ?? 0)}
        ${metric('Source dependency risk',num(provenance.single_cluster_dependency_risk,0))}
        ${metric('Event alignment',num(alignment.score,0))}
        ${metric('Nearest causal evidence',num(alignment.nearest_causal_age_hours,1),'h')}
        ${metric('Fundamental quality',num(fundamentals.score,0))}
        ${metric('Robust evidence',num(robustness.robust_evidence_confidence,0))}
      </div>
      <div class="or-meta" style="margin-top:7px">${esc(ensemble.method || '')}</div>
      <div class="or-meta">Required financial coverage: ${esc((fundamentals.available_required_metrics || []).join(', ') || 'none retained')} / ${esc((fundamentals.required_metrics || []).join(', ') || 'not applicable')}</div>
      <div class="or-cluster-list">${clusterRows(provenance)}</div>
      ${(robustness.score_caps || []).length ? `<div class="or-meta" style="margin-top:7px">Robustness caps: ${esc(robustness.score_caps.map(item=>`${item.type}:${item.cap}`).join(', '))}</div>` : ''}
    `;
  }

  function enhance(){document.querySelectorAll('#rows > tr').forEach(enhanceRow);}
  let scheduled=false;
  function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;enhance();});}
  enhance();
  const rows=document.getElementById('rows');
  if(rows)new MutationObserver(schedule).observe(rows,{childList:true,subtree:true});
})();
