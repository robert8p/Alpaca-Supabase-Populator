(() => {
  const clamp = value => Math.max(0, Math.min(100, Number(value)));
  const pct = value => value == null || !Number.isFinite(Number(value)) ? null : `${(Number(value) * 100).toFixed(1)}%`;

  function rating(candidate) {
    const analysis = candidate?.catalyst_analysis || {};
    const trace = analysis.fundamental_trace || {};
    const raw = trace.raw_metrics || {};
    const signals = analysis.event_signals || {};
    const dilution = analysis.dilution_analysis || {};
    const resilience = Number.isFinite(Number(candidate?.resilience_score)) ? Number(candidate.resilience_score) : 45;
    const damage = Number.isFinite(Number(candidate?.damage_risk)) ? Number(candidate.damage_risk) : 50;

    let score = clamp(0.65 * resilience + 0.35 * (100 - damage));
    if (!trace.available) score = Math.min(score, 60);

    if (signals.existential_or_solvency || dilution.classification === 'capital_distress') score = Math.min(score, 15);
    else if (signals.primary_endpoint_failure || signals.structural_impairment || damage >= 80) score = Math.min(score, 25);
    else if (dilution.classification === 'material_dilution') score = Math.min(score, 40);

    let grade, label, css;
    if (score >= 75) [grade,label,css] = ['A','Strong','a'];
    else if (score >= 60) [grade,label,css] = ['B','Good','b'];
    else if (score >= 45) [grade,label,css] = ['C','Mixed','c'];
    else if (score >= 30) [grade,label,css] = ['D','Weak','d'];
    else [grade,label,css] = ['E','Fragile','e'];

    const details = [
      `Resilience: ${resilience.toFixed(0)}/100`,
      `Damage: ${damage.toFixed(0)}/100`,
      ['Revenue YoY', pct(raw.revenue_yoy)],
      ['Net margin', pct(raw.net_margin)],
      ['Cash/assets', pct(raw.cash_to_assets)],
      ['Liabilities/assets', pct(raw.liabilities_to_assets)],
      ['Equity/assets', pct(raw.equity_to_assets)],
      ['Diluted shares YoY', pct(raw.diluted_shares_yoy)],
    ].flatMap(item => Array.isArray(item) ? (item[1] == null ? [] : [`${item[0]}: ${item[1]}`]) : [item]);
    if (dilution.classification && dilution.classification !== 'not_applicable') details.push(`Financing: ${dilution.classification}`);
    details.push(trace.available ? 'Evidence: cutoff-valid filing + event data' : 'Evidence: limited; event/scanner data only');
    return {grade,label,css,score,title:details.join(' · '),limited:!trace.available};
  }

  function enhance() {
    if (typeof state === 'undefined' || !Array.isArray(state.candidates)) return;
    document.querySelectorAll('#rows > tr').forEach(tr => {
      const cell = tr.querySelector('.or-fundamentals');
      const symbol = tr.querySelector('.symbol')?.textContent?.trim();
      const candidate = state.candidates.find(item => String(item.symbol) === symbol);
      if (!cell || !candidate) return;
      const value = rating(candidate);
      const key = `${value.grade}:${value.score.toFixed(1)}:${value.limited}`;
      if (cell.dataset.ratingKey === key) return;
      cell.dataset.ratingKey = key;
      cell.title = value.title;
      cell.innerHTML = `<span class="or-fund-grade ${value.css}">${value.grade} · ${value.label}</span><div class="muted" style="margin-top:4px">${value.score.toFixed(0)}/100${value.limited ? ' · limited data' : ''}</div>`;
    });
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

  new MutationObserver(schedule).observe(document.body, {childList:true, subtree:true});
  enhance();
})();
