(() => {
  const STYLE_ID = 'or-score-v2-styles';
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .or-model-score { min-width:250px; }
      .or-score-primary { font-size:22px; font-weight:900; line-height:1.1; letter-spacing:-.02em; }
      .or-score-name { color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.08em; font-weight:800; }
      .or-model-status { display:inline-block; margin-top:5px; padding:2px 7px; border:1px solid #506070; border-radius:999px; color:#bed2e6; font-size:10px; font-weight:800; }
      .or-components { display:grid; grid-template-columns:repeat(2,minmax(92px,1fr)); gap:4px 9px; margin-top:8px; font-size:10px; }
      .or-component { display:flex; justify-content:space-between; gap:8px; color:var(--muted); }
      .or-component strong { color:var(--text); }
      .or-damage strong { color:#ff9a9a; }
      .or-score-explanation { margin-top:7px; max-width:300px; color:#c4ced8; font-size:10px; line-height:1.35; }
      .or-score-details { margin-top:8px; }
      .or-score-details summary { cursor:pointer; color:var(--accent); font-size:10px; font-weight:800; }
      .or-detail-body { margin-top:8px; min-width:380px; max-width:560px; padding:10px; border:1px solid var(--line); border-radius:8px; background:#0c1116; font-size:11px; line-height:1.42; }
      .or-detail-section { margin-bottom:9px; }
      .or-detail-section:last-child { margin-bottom:0; }
      .or-detail-section b { display:block; margin-bottom:2px; color:#dce7f1; }
      .or-calc { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; color:#b8c5d0; }
      .or-danger { color:#ff9a9a; }
      .or-model-banner { margin-top:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
      .or-diagnostics-button { padding:5px 9px; font-size:11px; }
      #or-model-dialog { width:min(900px,92vw); max-height:85vh; overflow:auto; border:1px solid #44515d; border-radius:12px; background:#11171d; color:var(--text); padding:18px; }
      #or-model-dialog::backdrop { background:rgba(0,0,0,.72); }
      .or-diag-grid { display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:8px; margin:12px 0; }
      .or-diag-card { padding:10px; border:1px solid var(--line); border-radius:8px; background:#0d1217; }
      .or-diag-card strong { display:block; margin-top:3px; font-size:18px; }
      .or-diag-table { width:100%; min-width:0; margin-top:10px; font-size:11px; }
      .or-diag-table th,.or-diag-table td { padding:6px; }
      @media(max-width:900px){ .or-diag-grid{grid-template-columns:repeat(2,minmax(120px,1fr));} }
    `;
    document.head.appendChild(style);
  }

  const html = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (value, digits = 0) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
  const listText = (values, fallback) => Array.isArray(values) && values.length ? values.map(html).join('<br>') : html(fallback);

  function visibleCandidates() {
    if (typeof state === 'undefined' || !Array.isArray(state.candidates)) return [];
    const q = document.getElementById('search')?.value.trim().toLowerCase() || '';
    const triage = document.getElementById('triage')?.value || '';
    return state.candidates.filter(c => {
      const hay = `${c.symbol} ${c.name ?? ''}`.toLowerCase();
      return (!q || hay.includes(q)) && (!triage || c.triage_label === triage);
    });
  }

  function scoreCell(c) {
    if (c.reversion_score == null || c.model_run_id == null) {
      return `<div class="or-model-score"><div class="or-score-name">Legacy result</div><div class="or-score-primary">${html(c.heuristic_score ?? '—')}</div><span class="or-model-status">Model v2 unavailable</span><div class="or-score-explanation">Historic record preserved. No point-in-time v2 Evidence Snapshot was manufactured retrospectively.</div></div>`;
    }
    const a = c.catalyst_analysis || {};
    const trace = c.calculation_trace || {};
    const finalTrace = trace.final || {};
    const supporting = a.supporting_evidence || [];
    const contradictory = a.contradictory_evidence || [];
    const flags = a.red_flags || c.risk_flags || [];
    const missing = c.missing_inputs || [];
    const confirmation = trace.confirmation || {};
    const analyst = a.analyst_reaction || {};
    const versions = `${c.scoring_model_version || '—'} / ${c.scoring_config_version || '—'}`;
    const calc = [
      `Core = ${num(c.core_score,2)}`,
      `Confidence-adjusted = ${num(c.confidence_adjusted_score,2)}`,
      `Damage penalty = -${num(c.damage_penalty,2)}`,
      `Damage cap = ${num(c.damage_cap,0)}`,
      c.hard_veto ? `Hard veto = YES (${c.hard_veto_reason || 'unspecified'})` : 'Hard veto = no',
      `Final = ${num(c.reversion_score,1)} (${c.model_verdict || '—'})`,
    ].join('\n');
    return `<div class="or-model-score">
      <div class="or-score-name">Reversion Score</div>
      <div class="or-score-primary">${num(c.reversion_score,1)}</div>
      <span class="or-model-status">Model status: ${html(c.model_status === 'calibrated' ? 'Calibrated' : 'Uncalibrated')}</span>
      <div class="or-components">
        <div class="or-component"><span>Setup</span><strong>${num(c.setup_score,0)}</strong></div>
        <div class="or-component"><span>Catalyst</span><strong>${num(c.catalyst_score,0)}</strong></div>
        <div class="or-component"><span>Resilience</span><strong>${num(c.resilience_score,0)}</strong></div>
        <div class="or-component or-damage"><span>Damage</span><strong>${num(c.damage_risk,0)}</strong></div>
        <div class="or-component"><span>Confirmation</span><strong>${num(c.confirmation_score,0)}</strong></div>
        <div class="or-component"><span>Confidence</span><strong>${num(c.evidence_confidence,0)}</strong></div>
      </div>
      <div class="or-score-explanation">${html(c.explanation || '')}</div>
      <details class="or-score-details"><summary>Scoring breakdown</summary><div class="or-detail-body">
        <div class="or-detail-section"><b>Reversion thesis</b>${html(c.explanation || 'No thesis summary available.')}</div>
        <div class="or-detail-section"><b>Primary catalyst</b>${html(a.primary_catalyst || c.catalyst_summary || 'Unknown')}</div>
        <div class="or-detail-section"><b>Why it may be temporary</b>${listText(supporting, 'No strong supporting evidence retained.')}</div>
        <div class="or-detail-section"><b>Damage risks</b><span class="or-danger">${listText(flags, 'No explicit red flags retained.')}</span></div>
        <div class="or-detail-section"><b>Contradictory evidence</b>${listText(contradictory, 'No contradictory evidence retained.')}</div>
        <div class="or-detail-section"><b>Confirmation at cutoff</b>Session-range position ${num(confirmation.session_range_position,0)}; return from open ${num(confirmation.return_from_open_pct,2)}%; relative volume ${num(confirmation.relative_volume,2)}.</div>
        <div class="or-detail-section"><b>Evidence confidence</b>${num(c.evidence_confidence,0)}/100. Missing: ${missing.length ? missing.map(html).join(', ') : 'none flagged'}.</div>
        <div class="or-detail-section"><b>Analyst evidence</b>${html(analyst.direction || 'unavailable')}; post-event retained events: ${Array.isArray(analyst.post_event_updates) ? analyst.post_event_updates.length : 0}. Consensus is not a standalone score.</div>
        <div class="or-detail-section"><b>Exact scoring calculation</b><div class="or-calc">${html(calc)}</div></div>
        <div class="or-detail-section"><b>Point-in-time evidence</b>Signal ${html(c.signal_timestamp || '—')} at ${html(c.signal_price == null ? '—' : '$'+Number(c.signal_price).toFixed(2))}; cutoff ${html(c.evidence_cutoff || '—')}; snapshot ${html(c.evidence_snapshot_id || '—')}.</div>
        <div class="or-detail-section"><b>Versions</b>${html(versions)} · catalyst schema ${html(c.catalyst_schema_version || '—')} · target ${html(c.target_definition || '—')}</div>
      </div></details>
    </div>`;
  }

  function enhanceRows() {
    const tbody = document.getElementById('rows');
    if (!tbody) return;
    const candidates = visibleCandidates();
    [...tbody.querySelectorAll(':scope > tr')].forEach((tr, index) => {
      const c = candidates[index];
      if (!c || !tr.cells[6]) return;
      const key = `${c.id}:${c.model_run_id || 'legacy'}:${c.reversion_score ?? c.heuristic_score}`;
      if (tr.dataset.scoreV2Key === key) return;
      tr.dataset.scoreV2Key = key;
      tr.dataset.candidateId = c.id;
      tr.cells[6].innerHTML = scoreCell(c);
      tr.cells[6].className = 'score or-model-score-cell';
    });
    const th = document.querySelector('thead th:nth-child(7)');
    if (th && th.dataset.scoreV2 !== '1') {
      th.dataset.scoreV2 = '1';
      th.innerHTML = 'Reversion<span class="th-hint">model score</span>';
      th.title = 'Uncalibrated 0–100 Reversion Score until empirical calibration quality gates pass.';
    }
  }

  function addBannerAndDiagnostics() {
    const notice = document.querySelector('.notice');
    if (!notice || document.getElementById('or-model-banner')) return;
    const banner = document.createElement('div');
    banner.id = 'or-model-banner';
    banner.className = 'or-model-banner';
    banner.innerHTML = `<span class="or-model-status">Model status: Uncalibrated</span><span class="muted">Target: +5% from signal price within 6 weeks. No % probability is shown until calibration passes.</span><button class="or-diagnostics-button" id="or-open-diagnostics">Model diagnostics</button>`;
    notice.appendChild(banner);
    document.getElementById('or-open-diagnostics')?.addEventListener('click', openDiagnostics);
  }

  function ensureDialog() {
    let dialog = document.getElementById('or-model-dialog');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'or-model-dialog';
    dialog.innerHTML = `<div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><h2 style="margin:0">Model diagnostics</h2><button id="or-close-diagnostics">Close</button></div><div id="or-diagnostics-body" class="muted" style="margin-top:12px">Loading…</div>`;
    document.body.appendChild(dialog);
    dialog.querySelector('#or-close-diagnostics').addEventListener('click', () => dialog.close());
    return dialog;
  }

  function diagnosticTable(rows) {
    if (!Array.isArray(rows) || !rows.length) return '<div class="muted">No scored buckets yet.</div>';
    return `<table class="or-diag-table"><thead><tr><th>Score</th><th>Signals</th><th>Matured eligible</th><th>Hits</th><th>Hit rate</th></tr></thead><tbody>${rows.map(r => `<tr><td>${html(r.range)}</td><td>${html(r.sample_count)}</td><td>${html(r.matured_count)}</td><td>${html(r.hit_count)}</td><td>${r.hit_rate == null ? '—' : num(r.hit_rate,1)+'%'}</td></tr>`).join('')}</tbody></table>`;
  }

  async function openDiagnostics() {
    const dialog = ensureDialog();
    const body = document.getElementById('or-diagnostics-body');
    if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open','');
    body.textContent = 'Loading diagnostics…';
    try {
      const res = await fetch('/api/oversold/diagnostics', {cache:'no-store'});
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      const s = d.summary || {};
      body.innerHTML = `<div><strong>Calibration status: ${html(d.calibration_status)}</strong></div>
        <div class="or-diag-grid">
          <div class="or-diag-card">Scored signals<strong>${html(s.scored_signals || 0)}</strong></div>
          <div class="or-diag-card">Matured outcomes<strong>${html(s.matured_outcomes || 0)}</strong></div>
          <div class="or-diag-card">Calibration eligible<strong>${html(s.calibration_eligible_matured || 0)}</strong></div>
          <div class="or-diag-card">Missing-news cases<strong>${html(s.missing_news_count || 0)}</strong></div>
        </div>
        <div><b>Why probability is not enabled</b><br>${listText(d.calibration_reasons, 'Configured calibration gates have passed.')}</div>
        <div style="margin-top:12px"><b>Performance by score bucket</b>${diagnosticTable(d.score_buckets)}</div>
        <div style="margin-top:12px"><b>Current versions</b><br>${html(d.contract?.versions?.scoring_model_version || '—')} · ${html(d.contract?.versions?.scoring_config_version || '—')}</div>
        <div style="margin-top:8px"><b>Catalyst backend</b><br>${html(d.catalyst_backend || '—')}. ${html(d.calibration_guard || '')}</div>`;
    } catch (error) {
      body.textContent = `Diagnostics failed: ${error.message}`;
    }
  }

  addBannerAndDiagnostics();
  enhanceRows();
  const tbody = document.getElementById('rows');
  if (tbody) new MutationObserver(enhanceRows).observe(tbody, {childList:true, subtree:true});
  document.getElementById('search')?.addEventListener('input', () => setTimeout(enhanceRows, 0));
  document.getElementById('triage')?.addEventListener('change', () => setTimeout(enhanceRows, 0));
})();
