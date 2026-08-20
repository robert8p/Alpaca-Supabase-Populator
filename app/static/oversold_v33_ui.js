(() => {
  if (window.__orV33UiInstalled) return;
  window.__orV33UiInstalled = true;

  const PURPOSE = 'Prioritise liquid US sell-offs where verified price damage appears materially greater than justified economic damage, the business can survive, and a reversion within three trading sessions offers favourable asymmetric risk.';
  const STYLE_ID = 'or-v33-purpose-ui-style';
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .or-v33-purpose { display:flex; gap:9px; align-items:center; flex-wrap:wrap; }
      .or-v33-purpose-text { flex:1 1 520px; color:var(--text); font-weight:750; }
      .or-v33-chip { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:3px 8px; color:var(--muted); font-size:10px; font-weight:850; white-space:nowrap; }
      .or-v33-chip.good { color:var(--good); border-color:#2b6b4a; }
      .or-v33-chip.warn { color:var(--warn); border-color:#755d27; }
      .or-v33-chip.bad { color:var(--bad); border-color:#783838; }
      .or-v33-score-grid { display:grid; grid-template-columns:repeat(4,minmax(92px,1fr)); gap:5px; margin-top:7px; }
      .or-v33-metric { border:1px solid #323d48; border-radius:7px; padding:5px 6px; background:#0f1419; }
      .or-v33-metric span { display:block; color:var(--muted); font-size:8px; text-transform:uppercase; letter-spacing:.05em; }
      .or-v33-metric strong { display:block; margin-top:1px; font-size:12px; }
      .or-v33-failed { margin-top:5px; color:var(--bad); font-size:9px; line-height:1.3; }
      .or-v33-source { margin-top:4px; color:var(--muted); font-size:9px; }
      .or-v33-extended { color:var(--warn); font-size:10px; font-weight:800; }
      #or-quality-filter { min-width:185px; }
      @media(max-width:900px){ .or-v33-score-grid{grid-template-columns:repeat(2,minmax(92px,1fr));} }
    `;
    document.head.appendChild(style);
  }

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (value, digits=0) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);

  function analysis(c) { return c?.catalyst_analysis || {}; }
  function v33(c) { return c?.calculation_trace?.v3_3 || {}; }
  function fundamentalsAvailable(c) { return Boolean(analysis(c)?.fundamental_trace?.available); }
  function eligible(c) {
    const gates = analysis(c).eligibility_gates || v33(c).eligibility_gates || {};
    return Object.keys(gates).length > 0 && Object.values(gates).every(Boolean);
  }

  function qualityMatches(c, filter) {
    if (!filter) return true;
    const a = analysis(c);
    if (filter === 'eligible') return eligible(c);
    if (filter === 'verified') return ['VERIFIED','STRONGLY_INFERRED'].includes(a.assessment_confidence_state || a.cause_verification_status);
    if (filter === 'fundamentals') return fundamentalsAvailable(c);
    if (filter === 'limited') return !fundamentalsAvailable(c) || ['UNKNOWN','WEAKLY_INFERRED','CONFLICTING'].includes(a.assessment_confidence_state);
    return true;
  }

  function ensureQualityFilter() {
    const toolbar = document.querySelector('.toolbar');
    if (!toolbar || document.getElementById('or-quality-filter')) return;
    const select = document.createElement('select');
    select.id = 'or-quality-filter';
    select.innerHTML = `
      <option value="">All evidence states</option>
      <option value="eligible">INVESTIGATE eligible</option>
      <option value="verified">Verified / strong evidence</option>
      <option value="fundamentals">Primary fundamentals available</option>
      <option value="limited">Limited / uncertain evidence</option>
    `;
    toolbar.insertBefore(select, toolbar.querySelector('#search') || toolbar.firstChild);
    select.addEventListener('change', () => window.renderRows?.());
  }

  function installRenderFilter() {
    if (window.__orV33RenderWrapped || typeof window.renderRows !== 'function') return;
    window.__orV33RenderWrapped = true;
    const previous = window.renderRows;
    window.renderRows = function v33RenderRows() {
      const all = Array.isArray(window.state?.candidates) ? window.state.candidates : [];
      const filter = document.getElementById('or-quality-filter')?.value || '';
      if (filter) window.state.candidates = all.filter(c => qualityMatches(c, filter));
      try { return previous(); }
      finally {
        window.state.candidates = all;
        queueMicrotask(enhance);
      }
    };
  }

  function candidateForRow(tr) {
    const id = Number(tr.dataset.candidateId || 0);
    if (id) {
      const found = window.state?.candidates?.find(c => Number(c.id) === id);
      if (found) return found;
    }
    const symbol = tr.querySelector('.symbol')?.textContent?.trim();
    return window.state?.candidates?.find(c => String(c.symbol) === symbol) || null;
  }

  function metric(label, value, risk=false) {
    return `<div class="or-v33-metric"><span>${esc(label)}</span><strong class="${risk ? 'or-danger' : ''}">${num(value,0)}</strong></div>`;
  }

  function decorateScore(tr, c) {
    const cell = tr.querySelector('.or-model-score-cell') || tr.children[6];
    if (!cell || !c) return;
    const a = analysis(c);
    const trace = v33(c);
    const key = `${c.id}:${c.model_run_id}:${c.reversion_score}:${a.overreaction_quality_score}:${a.survivability_score}`;
    if (cell.dataset.v33Key === key) return;
    cell.dataset.v33Key = key;
    cell.querySelector('.or-v33-summary')?.remove();
    const gates = a.eligibility_gates || trace.eligibility_gates || {};
    const failed = a.failed_eligibility_gates || trace.failed_eligibility_gates || Object.entries(gates).filter(([,ok]) => !ok).map(([name]) => name);
    const session = a.price_session_context || trace.price_session_context || {};
    const summary = document.createElement('div');
    summary.className = 'or-v33-summary';
    summary.innerHTML = `
      <div class="or-model-badges">
        <span class="or-mini-badge ${c.model_verdict === 'INVESTIGATE' ? 'good' : c.model_verdict === 'PASS' ? 'risk' : ''}">${esc(c.model_verdict || '—')}</span>
        <span class="or-mini-badge">${esc(a.cause_verification_status || 'UNKNOWN')}</span>
        <span class="or-mini-badge">${esc(a.fundamental_evidence_state || 'UNAVAILABLE')}</span>
        ${session.extended_hours_only ? '<span class="or-mini-badge risk">EXTENDED-HOURS ONLY</span>' : ''}
      </div>
      <div class="or-v33-score-grid">
        ${metric('Overreaction', a.overreaction_quality_score)}
        ${metric('Survivability', a.survivability_score)}
        ${metric('3-session fit', a.three_session_fit_score)}
        ${metric('Tail risk', a.tail_risk_score, true)}
      </div>
      ${failed.length ? `<div class="or-v33-failed">Failed: ${failed.slice(0,4).map(x => esc(String(x).replaceAll('_',' '))).join(' · ')}</div>` : '<div class="or-v33-source">All INVESTIGATE eligibility gates passed.</div>'}
    `;
    const primary = cell.querySelector('.or-score-primary');
    if (primary?.parentElement) primary.parentElement.insertBefore(summary, primary.nextSibling);
    else cell.prepend(summary);
  }

  function decoratePrice(tr, c) {
    const a = analysis(c);
    const context = a.price_session_context || v33(c).price_session_context || {};
    if (!context.extended_hours_only || !tr.children[3] || tr.children[3].querySelector('.or-v33-extended')) return;
    const line = document.createElement('div');
    line.className = 'or-v33-extended';
    line.textContent = `Extended-hours-only trigger · regular move ${num(context.regular_session_move_pct,1)}%`;
    tr.children[3].appendChild(line);
  }

  function updatePurpose() {
    const notice = document.querySelector('.notice');
    if (!notice || !window.state) return;
    const candidates = window.state.candidates || [];
    const primary = candidates.filter(fundamentalsAvailable).length;
    const verified = candidates.filter(c => ['VERIFIED','STRONGLY_INFERRED'].includes(analysis(c).assessment_confidence_state || analysis(c).cause_verification_status)).length;
    const eligibleCount = candidates.filter(eligible).length;
    const completed = window.state.scan?.completed_at ? new Date(window.state.scan.completed_at).toLocaleString() : '—';
    const key = `${candidates.length}:${primary}:${verified}:${eligibleCount}:${completed}`;
    if (notice.dataset.v33Key === key) return;
    notice.dataset.v33Key = key;
    notice.innerHTML = `<div class="or-v33-purpose">
      <div class="or-v33-purpose-text">${esc(PURPOSE)}</div>
      <span class="or-v33-chip">3-session target</span>
      <span class="or-v33-chip ${primary ? 'good' : 'warn'}">Primary fundamentals ${primary}/${candidates.length}</span>
      <span class="or-v33-chip ${verified ? 'good' : 'warn'}">Verified/strong ${verified}</span>
      <span class="or-v33-chip ${eligibleCount ? 'good' : ''}">Eligible ${eligibleCount}</span>
      <span class="or-v33-chip">As of ${esc(completed)}</span>
    </div>`;
    document.querySelector('header .sub')?.replaceChildren(document.createTextNode('Price damage vs economic damage · survivability · evidence · three-session reversion'));
  }

  function simplifyColumns() {
    const table = document.querySelector('.table-wrap table');
    const header = table?.querySelector('thead tr');
    if (!header) return;
    [...header.children].forEach((th, index) => {
      const label = th.textContent.trim().toLowerCase();
      if (label === 'class' || label === 'triage') {
        th.style.display = 'none';
        document.querySelectorAll('#rows > tr').forEach(tr => {
          if (tr.children[index]) tr.children[index].style.display = 'none';
        });
      }
      if (label.startsWith('score') || label.startsWith('reversion')) {
        th.innerHTML = 'Opportunity<span class="th-hint">quality / evidence / gates</span>';
      }
      if (label === 'why') th.textContent = 'Catalyst thesis';
    });
  }

  function enhance() {
    ensureQualityFilter();
    installRenderFilter();
    updatePurpose();
    simplifyColumns();
    document.querySelectorAll('#rows > tr').forEach(tr => {
      const c = candidateForRow(tr);
      decorateScore(tr, c);
      decoratePrice(tr, c);
    });
  }

  let queued = false;
  const schedule = () => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      enhance();
    });
  };

  enhance();
  const rows = document.getElementById('rows');
  if (rows) new MutationObserver(schedule).observe(rows, {childList:true, subtree:true});
  setInterval(() => {
    if (document.visibilityState === 'visible') enhance();
  }, 15000);
})();
