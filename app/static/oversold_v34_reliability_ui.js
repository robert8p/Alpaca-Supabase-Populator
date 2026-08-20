(() => {
  if (window.__orV34ReliabilityUiInstalled) return;
  window.__orV34ReliabilityUiInstalled = true;

  const style = document.createElement('style');
  style.textContent = `
    .or-reliability-badge { color:#d9e9ff; border-color:#526f9e; background:#17253a; }
    .or-reliability-warn { color:#ffe1a6; border-color:#8e6a2b; background:#332714; }
    .or-reliability-risk { color:#ffd0d0; border-color:#8c4242; background:#351919; }
    .or-scenario-table { width:100%; min-width:0; margin-top:6px; border-collapse:collapse; }
    .or-scenario-table th,.or-scenario-table td { padding:5px 7px; border-bottom:1px solid var(--line); font-size:10px; }
    .or-scenario-table th { position:static; text-transform:none; letter-spacing:0; }
    .or-reliability-grid { display:grid; grid-template-columns:repeat(4,minmax(100px,1fr)); gap:6px; margin-top:7px; }
    .or-reliability-metric { border:1px solid var(--line); border-radius:6px; padding:7px; background:#0b1116; }
    .or-reliability-metric span { display:block; color:var(--muted); font-size:9px; text-transform:uppercase; }
    .or-reliability-metric strong { display:block; margin-top:2px; font-size:14px; }
    @media(max-width:900px){ .or-reliability-grid{grid-template-columns:repeat(2,minmax(100px,1fr));} }
  `;
  document.head.appendChild(style);

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'
  }[char]));
  const num = (value, digits=1) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);

  function candidateForRow(row) {
    const id = Number(row.dataset.candidateId || 0);
    if (id) {
      const candidate = window.state?.candidates?.find(item => Number(item.id) === id);
      if (candidate) return candidate;
    }
    const symbol = row.querySelector('.symbol')?.textContent?.trim();
    return window.state?.candidates?.find(item => String(item.symbol) === symbol) || null;
  }

  function metric(label, value, suffix='') {
    return `<div class="or-reliability-metric"><span>${esc(label)}</span><strong>${esc(value)}${suffix}</strong></div>`;
  }

  function scenarioRows(reliability) {
    const labels = {
      base_reliable:'Evidence-adjusted base',
      evidence_downside:'Evidence downside',
      financial_downside:'Financial downside',
      timing_downside:'Timing downside',
      joint_downside:'Joint downside',
      modest_upside:'Modest upside',
    };
    return Object.entries(reliability.scenarios || {}).map(([key, scenario]) =>
      `<tr><td>${esc(labels[key] || key)}</td><td>${num(scenario.score,1)}</td><td>${num(scenario.confidence,0)}</td><td>${num(scenario.tail,0)}</td></tr>`
    ).join('');
  }

  function evidenceSummary(reliability) {
    const relevance = reliability.evidence_relevance || {};
    const contradiction = reliability.contradictions || {};
    return [
      `Primary causal: ${relevance.causal_primary_count ?? 0}`,
      `Independent causal sources: ${relevance.causal_independent_sources ?? 0}`,
      `Unresolved contradictions: ${contradiction.unresolved_count ?? 0}`,
      `Resolved sequences: ${contradiction.resolved_sequence_count ?? 0}`,
    ].join(' · ');
  }

  function enhanceRow(row) {
    const candidate = candidateForRow(row);
    const cell = row.querySelector('.or-model-score-cell');
    const reliability = candidate?.catalyst_analysis?.reliability_assessment;
    if (!candidate || !cell || !reliability) return;
    const key = [candidate.id,candidate.model_run_id,candidate.reversion_score,reliability.stability_score,reliability.scenario_score_range].join(':');
    if (cell.dataset.v34ReliabilityKey === key) return;
    cell.dataset.v34ReliabilityKey = key;

    const name = cell.querySelector('.or-score-name');
    if (name && candidate.model_status !== 'calibrated') name.textContent = 'Conservative Opportunity';

    const badges = cell.querySelector('.or-model-badges');
    if (badges) {
      badges.querySelectorAll('[data-v34-badge]').forEach(element => element.remove());
      const badgeData = [
        [`Base ${num(reliability.base_v33_score,1)}`, 'or-reliability-badge'],
        [`Stability ${num(reliability.stability_score,0)}`, reliability.stability_score >= 70 ? 'or-reliability-badge' : 'or-reliability-warn'],
        [`Friction ${num(reliability.execution_friction?.estimated_round_trip_friction_pct,2)}%`, reliability.execution_friction?.estimated_round_trip_friction_pct <= 1.5 ? 'or-reliability-badge' : 'or-reliability-warn'],
        [`Conflict ${num(reliability.contradictions?.severity,0)}`, reliability.contradictions?.severity < 50 ? 'or-reliability-badge' : 'or-reliability-risk'],
      ];
      for (const [text,klass] of badgeData) {
        const badge = document.createElement('span');
        badge.dataset.v34Badge = 'true';
        badge.className = `or-mini-badge ${klass}`;
        badge.textContent = text;
        badges.appendChild(badge);
      }
    }

    const body = cell.querySelector('.or-detail-body');
    if (!body) return;
    let section = body.querySelector('.or-v34-reliability-section');
    if (!section) {
      section = document.createElement('div');
      section.className = 'or-detail-section or-v34-reliability-section';
      body.insertAdjacentElement('afterbegin',section);
    }
    section.innerHTML = `
      <b>v3.4 reliability stress test</b>
      <div class="or-reliability-grid">
        ${metric('Conservative score',num(reliability.conservative_score,1))}
        ${metric('Base v3.3',num(reliability.base_v33_score,1))}
        ${metric('Stability',num(reliability.stability_score,0))}
        ${metric('Stress pass rate',num(Number(reliability.stress_gate_pass_rate || 0)*100,0),'%')}
        ${metric('Score range',num(reliability.scenario_score_range,1))}
        ${metric('Adjusted evidence',num(reliability.adjusted_evidence_confidence,0))}
        ${metric('Round-trip friction',num(reliability.execution_friction?.estimated_round_trip_friction_pct,2),'%')}
        ${metric('Contradiction severity',num(reliability.contradictions?.severity,0))}
      </div>
      <div class="or-meta" style="margin-top:7px">${esc(evidenceSummary(reliability))}</div>
      <table class="or-scenario-table"><thead><tr><th>Scenario</th><th>Score</th><th>Evidence</th><th>Tail</th></tr></thead><tbody>${scenarioRows(reliability)}</tbody></table>
      <div class="or-meta" style="margin-top:6px">Method: mean of the two lowest base/downside scenario scores, less estimated execution friction. It is deliberately a lower-confidence ranking, not a probability.</div>
    `;
  }

  function enhance() {
    document.querySelectorAll('#rows > tr').forEach(enhanceRow);
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; enhance(); });
  }
  enhance();
  const rows = document.getElementById('rows');
  if (rows) new MutationObserver(schedule).observe(rows,{childList:true,subtree:true});
})();
