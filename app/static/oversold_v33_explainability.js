(() => {
  if (window.__orV33ExplainabilityInstalled) return;
  window.__orV33ExplainabilityInstalled = true;

  const style = document.createElement('style');
  style.textContent = `
    .or-model-score .or-components { display:none; }
    .or-v33-score-grid { grid-template-columns:repeat(3,minmax(92px,1fr)) !important; }
    .or-v33-formula { margin-top:6px; white-space:pre-wrap; color:#b8c5d0; }
    @media(max-width:900px){ .or-v33-score-grid{grid-template-columns:repeat(2,minmax(92px,1fr)) !important;} }
  `;
  document.head.appendChild(style);

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'
  }[c]));
  const num = (value, digits=0) => value == null || Number.isNaN(Number(value))
    ? '—'
    : Number(value).toFixed(digits);

  function candidateForRow(row) {
    const id = Number(row.dataset.candidateId || 0);
    if (id) {
      const candidate = window.state?.candidates?.find(item => Number(item.id) === id);
      if (candidate) return candidate;
    }
    const symbol = row.querySelector('.symbol')?.textContent?.trim();
    return window.state?.candidates?.find(item => String(item.symbol) === symbol) || null;
  }

  function metric(label, value, risk=false) {
    return `<div class="or-v33-metric"><span>${esc(label)}</span><strong class="${risk ? 'or-danger' : ''}">${num(value,0)}</strong></div>`;
  }

  function currentFormula(candidate) {
    const trace = candidate.calculation_trace?.v3_3 || {};
    const caps = Array.isArray(trace.caps_applied)
      ? trace.caps_applied.map(item => `${item.type}:${item.cap}`).join(', ')
      : 'none';
    return [
      `Weighted geometric opportunity = ${num(trace.raw_opportunity_quality,2)}`,
      `Evidence-confidence multiplier = ${num(trace.confidence_multiplier,4)}`,
      `Confidence-adjusted opportunity = ${num(trace.confidence_adjusted_opportunity,2)}`,
      `Tail-risk penalty = -${num(trace.tail_risk_penalty,2)}`,
      `Pre-cap score = ${num(trace.pre_cap_score,2)}`,
      `Final economic/risk cap = ${num(trace.final_cap,1)}`,
      `Caps applied = ${caps}`,
      `Final Opportunity Score = ${num(candidate.reversion_score,1)} (${candidate.model_verdict || '—'})`,
    ].join('\n');
  }

  function enhanceRow(row) {
    const candidate = candidateForRow(row);
    const cell = row.querySelector('.or-model-score-cell');
    if (!candidate || !cell) return;
    const analysis = candidate.catalyst_analysis || {};
    const trace = candidate.calculation_trace?.v3_3 || {};
    const key = [
      candidate.id,
      candidate.model_run_id,
      candidate.reversion_score,
      analysis.overreaction_quality_score,
      analysis.survivability_score,
      candidate.evidence_confidence,
    ].join(':');
    if (cell.dataset.v33ExplainabilityKey === key) return;
    cell.dataset.v33ExplainabilityKey = key;

    const name = cell.querySelector('.or-score-name');
    if (name && candidate.model_status !== 'calibrated') name.textContent = 'Opportunity Score';

    const grid = cell.querySelector('.or-v33-score-grid');
    if (grid) {
      grid.innerHTML = [
        metric('Overreaction', analysis.overreaction_quality_score),
        metric('Reversibility', analysis.reversibility_score ?? candidate.catalyst_score),
        metric('Survivability', analysis.survivability_score),
        metric('3-session fit', analysis.three_session_fit_score),
        metric('Tail risk', analysis.tail_risk_score, true),
        metric('Evidence', candidate.evidence_confidence),
      ].join('');
    }

    const detailSections = [...cell.querySelectorAll('.or-detail-section')];
    const exact = detailSections.find(section =>
      section.querySelector('b')?.textContent?.trim() === 'Exact scoring calculation'
    );
    if (exact) {
      const heading = exact.querySelector('b');
      if (heading) heading.textContent = 'Current v3.3 calculation';
      let formula = exact.querySelector('.or-calc');
      if (!formula) {
        formula = document.createElement('div');
        formula.className = 'or-calc';
        exact.appendChild(formula);
      }
      formula.textContent = currentFormula(candidate);
    }

    const versions = detailSections.find(section =>
      section.querySelector('b')?.textContent?.trim() === 'Versions'
    );
    if (versions && !versions.querySelector('.or-v33-formula')) {
      const methodology = document.createElement('div');
      methodology.className = 'or-v33-formula';
      methodology.textContent = candidate.calculation_trace?.formula ||
        'v3.3 opportunity quality with one-way confidence, tail-risk penalties and hard gates.';
      versions.appendChild(methodology);
    }
  }

  function enhance() {
    document.querySelectorAll('#rows > tr').forEach(enhanceRow);
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      enhance();
    });
  }

  enhance();
  const rows = document.getElementById('rows');
  if (rows) new MutationObserver(schedule).observe(rows, {childList:true, subtree:true});
})();
