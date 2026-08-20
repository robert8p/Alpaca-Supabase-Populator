(() => {
  const STYLE_ID = 'or-score-v3-styles';
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .or-model-score { min-width:285px; }
      .or-score-primary { font-size:22px; font-weight:900; line-height:1.1; letter-spacing:-.02em; }
      .or-score-secondary { margin-top:2px; color:var(--muted); font-size:10px; font-weight:700; }
      .or-score-name { color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.08em; font-weight:800; }
      .or-model-status { display:inline-block; margin-top:5px; padding:2px 7px; border:1px solid #506070; border-radius:999px; color:#bed2e6; font-size:10px; font-weight:800; }
      .or-model-badges { display:flex; gap:4px; flex-wrap:wrap; margin-top:5px; }
      .or-mini-badge { display:inline-block; padding:2px 6px; border:1px solid #44515d; border-radius:999px; color:#b8c5d0; font-size:9px; font-weight:800; }
      .or-mini-badge.risk { color:#ffb0b0; border-color:#754848; }
      .or-mini-badge.good { color:#94e7b8; border-color:#37634a; }
      .or-components { display:grid; grid-template-columns:repeat(2,minmax(96px,1fr)); gap:4px 9px; margin-top:8px; font-size:10px; }
      .or-component { display:flex; justify-content:space-between; gap:8px; color:var(--muted); }
      .or-component strong { color:var(--text); }
      .or-damage strong,.or-danger { color:#ff9a9a; }
      .or-score-explanation { margin-top:7px; max-width:340px; color:#c4ced8; font-size:10px; line-height:1.35; }
      .or-score-details { margin-top:8px; }
      .or-score-details summary { cursor:pointer; color:var(--accent); font-size:10px; font-weight:800; }
      .or-detail-body { margin-top:8px; min-width:440px; max-width:720px; padding:10px; border:1px solid var(--line); border-radius:8px; background:#0c1116; font-size:11px; line-height:1.45; }
      .or-detail-section { margin-bottom:10px; }
      .or-detail-section:last-child { margin-bottom:0; }
      .or-detail-section b { display:block; margin-bottom:3px; color:#dce7f1; }
      .or-calc { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; color:#b8c5d0; }
      .or-evidence-grid { display:grid; grid-template-columns:repeat(2,minmax(150px,1fr)); gap:4px 12px; }
      .or-evidence-grid span { color:var(--muted); }
      .or-evidence-grid strong { color:var(--text); float:right; margin-left:8px; }
      .or-gates { display:grid; grid-template-columns:repeat(2,minmax(180px,1fr)); gap:3px 10px; }
      .or-gate-pass { color:#72dc9e; }
      .or-gate-fail { color:#ff9a9a; }
      .or-model-banner { margin-top:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
      .or-diagnostics-button { padding:5px 9px; font-size:11px; }
      #or-model-dialog { width:min(950px,92vw); max-height:85vh; overflow:auto; border:1px solid #44515d; border-radius:12px; background:#11171d; color:var(--text); padding:18px; }
      #or-model-dialog::backdrop { background:rgba(0,0,0,.72); }
      .or-diag-grid { display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:8px; margin:12px 0; }
      .or-diag-card { padding:10px; border:1px solid var(--line); border-radius:8px; background:#0d1217; }
      .or-diag-card strong { display:block; margin-top:3px; font-size:18px; }
      .or-diag-table { width:100%; min-width:0; margin-top:10px; font-size:11px; }
      .or-diag-table th,.or-diag-table td { padding:6px; }
      @media(max-width:900px){ .or-diag-grid{grid-template-columns:repeat(2,minmax(120px,1fr));} .or-evidence-grid,.or-gates{grid-template-columns:1fr;} }
    `;
    document.head.appendChild(style);
  }

  const html = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (value, digits = 0) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
  const pct = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(digits)}%`;
  const listText = (values, fallback) => Array.isArray(values) && values.length ? values.map(html).join('<br>') : html(fallback);

  async function fetchWithTimeout(url, options={}, timeoutMs=12000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try { return await fetch(url, {...options, signal:controller.signal}); }
    catch (error) { if (error?.name === 'AbortError') throw new Error('Request timed out'); throw error; }
    finally { clearTimeout(timer); }
  }

  function visibleCandidates() {
    if (typeof state === 'undefined' || !Array.isArray(state.candidates)) return [];
    const q = document.getElementById('search')?.value.trim().toLowerCase() || '';
    const triage = document.getElementById('triage')?.value || '';
    return state.candidates.filter(c => {
      const hay = `${c.symbol} ${c.name ?? ''}`.toLowerCase();
      return (!q || hay.includes(q)) && (!triage || c.triage_label === triage);
    });
  }

  function metric(label, value, formatter = num) {
    return `<span>${html(label)} <strong>${formatter(value)}</strong></span>`;
  }

  function gatesHtml(gates) {
    if (!gates || typeof gates !== 'object' || !Object.keys(gates).length) return '<span class="muted">Legacy model: explicit eligibility gates unavailable.</span>';
    return `<div class="or-gates">${Object.entries(gates).map(([name, passed]) => `<span class="${passed ? 'or-gate-pass' : 'or-gate-fail'}">${passed ? '✓' : '✕'} ${html(name.replaceAll('_',' '))}</span>`).join('')}</div>`;
  }

  function sourceHierarchyHtml(items) {
    if (!Array.isArray(items) || !items.length) return '<span class="muted">No source hierarchy items retained.</span>';
    return items.slice(0,6).map(item => `${html(item.source_type || 'unknown')} ${html(item.source_quality_score ?? '—')}/100 · relevance ${html(item.ticker_relevance ?? '—')} · ${html(item.source || 'unknown source')}`).join('<br>');
  }

  function scoreCell(c) {
    if (c.reversion_score == null || c.model_run_id == null) {
      return `<div class="or-model-score"><div class="or-score-name">Legacy result</div><div class="or-score-primary">${html(c.heuristic_score ?? '—')}</div><span class="or-model-status">Current model unavailable</span><div class="or-score-explanation">Historic record preserved. No point-in-time Evidence Snapshot was manufactured retrospectively.</div></div>`;
    }
    const a = c.catalyst_analysis || {};
    const trace = c.calculation_trace || {};
    const v32 = trace.v3_2 || {};
    const setup = trace.setup || {};
    const tech = setup.technical_features || {};
    const confirmation = trace.confirmation || {};
    const confirmTech = confirmation.technical_features || {};
    const fundamentals = a.fundamental_trace || {};
    const rawFund = fundamentals.raw_metrics || {};
    const quality = a.evidence_quality_trace || {};
    const supporting = a.supporting_evidence || [];
    const contradictory = a.contradictory_evidence || [];
    const flags = a.red_flags || c.risk_flags || [];
    const missing = c.missing_inputs || [];
    const analyst = a.analyst_reaction || {};
    const spike = a.spike_adjustment || v32.price_path || {};
    const dilution = a.dilution_analysis || v32.financing || {};
    const gates = a.eligibility_gates || v32.eligibility_gates || {};
    const causeStatus = a.cause_verification_status || (a.cause_verified ? 'VERIFIED' : 'UNVERIFIED');
    const damageClass = a.economic_damage_class || (Number(c.damage_risk) >= 80 ? 'STRUCTURAL_OR_EXISTENTIAL' : Number(c.damage_risk) >= 55 ? 'HIGH' : Number(c.damage_risk) >= 30 ? 'MODERATE' : 'LOW');
    const isCalibrated = c.model_status === 'calibrated' && c.calibrated_probability != null;
    const probabilityPct = isCalibrated ? Number(c.calibrated_probability) * 100 : null;
    const versions = `${c.scoring_model_version || '—'} / ${c.scoring_config_version || '—'}`;
    const penalties = v32.penalties || {};
    const calc = [
      `Core = ${num(c.core_score,2)}`,
      `Confidence-adjusted = ${num(c.confidence_adjusted_score,2)}`,
      `Damage penalty = -${num(c.damage_penalty,2)}`,
      `Post-spike penalty = -${num(penalties.post_spike ?? trace.final?.post_spike_penalty,2)}`,
      `Dilution penalty = -${num(penalties.dilution ?? trace.final?.dilution_penalty,2)}`,
      `Damage cap = ${num(c.damage_cap,0)}`,
      c.hard_veto ? `Hard veto = YES (${c.hard_veto_reason || 'unspecified'})` : 'Hard veto = no',
      `Raw final score = ${num(c.reversion_score,1)} (${c.model_verdict || '—'})`,
      isCalibrated ? `Calibrated probability = ${num(probabilityPct,1)}% (${c.calibration_model_version || '—'})` : 'Calibrated probability = unavailable',
    ].join('\n');
    const technicalGrid = [
      metric('Shock z', tech.shock_z, v => num(v,2)),
      metric('ATR move', tech.atr_move_multiple, v => v == null ? '—' : `${num(v,2)}×`),
      metric('RSI14', tech.rsi14, v => num(v,1)),
      metric('SMA20 dist', tech.sma20_distance_pct, v => pct(v,1)),
      metric('SMA50 dist', tech.sma50_distance_pct, v => pct(v,1)),
      metric('60d drawdown', tech.drawdown_from_60d_high_pct, v => pct(v,1)),
      metric('Rel volume', tech.relative_volume20, v => v == null ? '—' : `${num(v,2)}×`),
      metric('SPY relative', tech.market_relative_move_pct, v => pct(v,1)),
      metric(`${tech.sector_benchmark || 'Sector'} relative`, tech.sector_relative_move_pct, v => pct(v,1)),
      metric('History completeness', tech.technical_history_completeness, v => pct(v,0)),
    ].join('');
    const confirmationGrid = [
      metric('Range position', confirmTech.session_range_position ?? tech.session_range_position, v => pct(v,0)),
      metric('From open', confirmTech.return_from_open_pct ?? tech.return_from_open_pct, v => pct(v,1)),
      metric('Gap reclaim', confirmTech.gap_reclaim_pct ?? tech.gap_reclaim_pct, v => pct(v,0)),
      metric('Low reclaim', confirmTech.low_reclaim_pct ?? tech.low_reclaim_pct, v => pct(v,0)),
      metric('VWAP distance', confirmTech.vwap_distance_pct ?? tech.vwap_distance_pct, v => pct(v,1)),
    ].join('');
    const fundamentalText = fundamentals.available
      ? `<div class="or-evidence-grid">
          ${metric('Revenue YoY', rawFund.revenue_yoy == null ? null : Number(rawFund.revenue_yoy) * 100, v => pct(v,1))}
          ${metric('Net margin', rawFund.net_margin == null ? null : Number(rawFund.net_margin) * 100, v => pct(v,1))}
          ${metric('Shares YoY', rawFund.diluted_shares_yoy == null ? null : Number(rawFund.diluted_shares_yoy) * 100, v => pct(v,1))}
          ${metric('Cash/assets', rawFund.cash_to_assets == null ? null : Number(rawFund.cash_to_assets) * 100, v => pct(v,1))}
          ${metric('Liabilities/assets', rawFund.liabilities_to_assets == null ? null : Number(rawFund.liabilities_to_assets) * 100, v => pct(v,1))}
          ${metric('Equity/assets', rawFund.equity_to_assets == null ? null : Number(rawFund.equity_to_assets) * 100, v => pct(v,1))}
        </div><div class="muted" style="margin-top:4px">${html(fundamentals.form || 'filing')} · available ${html(fundamentals.available_from || '—')} · ${html(fundamentals.metric_coverage_count ?? 0)} metrics</div>`
      : `<span class="muted">No cutoff-valid periodic filing fundamentals were available. Resilience is intentionally conservative and Confidence records the missing evidence.</span>`;
    const spikeText = spike.post_spike_unwind
      ? `<div class="or-evidence-grid">${metric('Max prior run-up', spike.max_prior_runup_pct, v => pct(v,1))}${metric('Run-up window', spike.runup_window_sessions, v => v == null ? '—' : `${num(v,0)} sessions`)}${metric('Pre-spike baseline', spike.pre_spike_baseline_price, v => v == null ? '—' : '$'+num(v,2))}${metric('Current vs baseline', spike.current_vs_pre_spike_baseline_pct, v => pct(v,1))}${metric('Spike retraced', spike.spike_retraced_pct, v => pct(v,0))}${metric('Penalty', spike.penalty, v => '-'+num(v,0))}</div><span class="muted">${listText(spike.reasons, 'No spike-specific reason retained.')}</span>`
      : '<span class="muted">No qualifying speculative run-up detected in the configured pre-signal windows.</span>';
    const dilutionText = dilution.is_financing_event
      ? `<div class="or-evidence-grid">${metric('Classification', dilution.classification, html)}${metric('Severity', dilution.severity_score, v => `${num(v,0)}/100`)}${metric('Offer discount', dilution.discount_to_previous_close_pct, v => pct(v,1))}${metric('Shares YoY', dilution.diluted_shares_yoy == null ? null : Number(dilution.diluted_shares_yoy)*100, v => pct(v,1))}${metric('Penalty', dilution.penalty, v => '-'+num(v,0))}${metric('Hard veto', dilution.hard_veto, v => v ? 'yes' : 'no')}</div><span class="muted">${listText(dilution.reasons, 'No severity reasons retained.')}</span>`
      : '<span class="muted">No financing/dilution event identified in cutoff-valid evidence.</span>';

    return `<div class="or-model-score">
      <div class="or-score-name">${isCalibrated ? 'Reversion Probability' : 'Reversion Score'}</div>
      <div class="or-score-primary">${isCalibrated ? num(probabilityPct,1)+'%' : num(c.reversion_score,1)}</div>
      ${isCalibrated ? `<div class="or-score-secondary">Raw Reversion Score ${num(c.reversion_score,1)}</div>` : ''}
      <span class="or-model-status">Model status: ${html(isCalibrated ? 'Calibrated' : 'Uncalibrated')}</span>
      <div class="or-model-badges"><span class="or-mini-badge ${causeStatus === 'VERIFIED' ? 'good' : 'risk'}">Cause ${html(causeStatus)}</span><span class="or-mini-badge ${damageClass === 'LOW' || damageClass === 'MODERATE' ? '' : 'risk'}">Damage ${html(damageClass)}</span><span class="or-mini-badge">${html(a.event_profile || 'unknown')}</span></div>
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
        <div class="or-detail-section"><b>Cause / event / damage</b>${html(a.primary_catalyst || c.catalyst_summary || 'Unknown')}<br><span class="muted">event ${html(a.event_profile || a.catalyst_type || 'unknown')} · cause ${html(causeStatus)} · economic damage ${html(damageClass)}</span></div>
        <div class="or-detail-section"><b>Pre-signal price path / spike adjustment</b>${spikeText}</div>
        <div class="or-detail-section"><b>Financing / dilution severity</b>${dilutionText}</div>
        <div class="or-detail-section"><b>INVESTIGATE eligibility gates</b>${gatesHtml(gates)}</div>
        <div class="or-detail-section"><b>Why it may be temporary</b>${listText(supporting, 'No strong supporting evidence retained.')}</div>
        <div class="or-detail-section"><b>Damage risks</b><span class="or-danger">${listText(contradictory.length ? contradictory : flags, 'No explicit damage evidence retained.')}</span></div>
        <div class="or-detail-section"><b>Technical dislocation at cutoff</b><div class="or-evidence-grid">${technicalGrid}</div></div>
        <div class="or-detail-section"><b>Price confirmation at cutoff</b><div class="or-evidence-grid">${confirmationGrid}</div></div>
        <div class="or-detail-section"><b>Point-in-time fundamentals</b>${fundamentalText}</div>
        <div class="or-detail-section"><b>Source-quality hierarchy</b>${sourceHierarchyHtml(a.source_quality_items)}</div>
        <div class="or-detail-section"><b>Evidence quality</b>${num(c.evidence_confidence,0)}/100 · ${html(quality.independent_source_count ?? '—')} independent source(s) · authoritative/direct source: ${quality.authoritative_source_present ? 'yes' : 'no'} · freshest ${quality.freshest_age_hours == null ? '—' : num(quality.freshest_age_hours,1)+'h'}<br><span class="muted">Missing: ${missing.length ? missing.map(html).join(', ') : 'none flagged'}</span></div>
        <div class="or-detail-section"><b>Analyst evidence</b>${html(analyst.direction || 'unavailable')}; retained cutoff-valid analyst items: ${Array.isArray(analyst.post_event_updates) ? analyst.post_event_updates.length : 0}. Consensus is not a standalone score.</div>
        <div class="or-detail-section"><b>Exact scoring calculation</b><div class="or-calc">${html(calc)}</div></div>
        <div class="or-detail-section"><b>Point-in-time evidence</b>Signal ${html(c.signal_timestamp || '—')} at ${html(c.signal_price == null ? '—' : '$'+Number(c.signal_price).toFixed(2))}; cutoff ${html(c.evidence_cutoff || '—')}; snapshot ${html(c.evidence_snapshot_id || '—')}.</div>
        <div class="or-detail-section"><b>Versions</b>${html(versions)} · catalyst schema ${html(c.catalyst_schema_version || '—')} · calibration ${html(c.calibration_model_version || 'not active at signal time')} · target ${html(c.target_definition || '—')}</div>
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
      const key = `${c.id}:${c.model_run_id || 'legacy'}:${c.reversion_score ?? c.heuristic_score}:${c.calibrated_probability ?? 'raw'}:${c.scoring_model_version || ''}`;
      if (tr.dataset.scoreModelKey === key) return;
      tr.dataset.scoreModelKey = key;
      tr.dataset.candidateId = c.id;
      tr.cells[6].innerHTML = scoreCell(c);
      tr.cells[6].className = 'score or-model-score-cell';
    });
    const th = document.querySelector('thead th:nth-child(7)');
    if (th) {
      const calibrated = candidates.some(c => c.model_status === 'calibrated' && c.calibrated_probability != null);
      th.innerHTML = `Reversion<span class="th-hint">${calibrated ? 'probability / score' : 'model score'}</span>`;
      th.title = calibrated ? 'Calibrated probability for eligible new signals; raw score remains in the breakdown.' : 'Uncalibrated 0–100 Reversion Score until empirical calibration quality gates pass.';
    }
  }

  async function refreshModelBanner() {
    const status = document.getElementById('or-banner-status');
    const text = document.getElementById('or-banner-text');
    if (!status || !text) return;
    try {
      const res = await fetchWithTimeout('/api/oversold/diagnostics', {cache:'no-store'});
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      const calibrated = d.model_status === 'calibrated';
      status.textContent = `Model status: ${calibrated ? 'Calibrated' : 'Uncalibrated'}`;
      text.textContent = calibrated ? 'Target: +5% from signal price within 6 weeks. New signals receive the passed empirical probability mapping.' : 'Target: +5% from signal price within 6 weeks. Score v3.2 uses explicit cause, spike, dilution and structural-risk gates; no % probability is shown until calibration quality gates pass.';
    } catch (_) {
      status.textContent = 'Model status: unavailable';
      text.textContent = 'Target: +5% from signal price within 6 weeks.';
    }
  }

  function addBannerAndDiagnostics() {
    const notice = document.querySelector('.notice');
    if (!notice || document.getElementById('or-model-banner')) return;
    const banner = document.createElement('div');
    banner.id = 'or-model-banner';
    banner.className = 'or-model-banner';
    banner.innerHTML = `<span class="or-model-status" id="or-banner-status">Model status: Checking…</span><span class="muted" id="or-banner-text">Target: +5% from signal price within 6 weeks.</span><button class="or-diagnostics-button" id="or-open-diagnostics">Model diagnostics</button>`;
    notice.appendChild(banner);
    document.getElementById('or-open-diagnostics')?.addEventListener('click', openDiagnostics);
    refreshModelBanner();
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
      const res = await fetchWithTimeout('/api/oversold/diagnostics', {cache:'no-store'});
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      const s = d.summary || {};
      const calibrated = d.model_status === 'calibrated';
      body.innerHTML = `<div><strong>Calibration status: ${html(d.calibration_status)}</strong></div>
        <div class="or-diag-grid">
          <div class="or-diag-card">Scored signals<strong>${html(s.scored_signals || 0)}</strong></div>
          <div class="or-diag-card">Matured outcomes<strong>${html(s.matured_outcomes || 0)}</strong></div>
          <div class="or-diag-card">Calibration eligible<strong>${html(s.calibration_eligible_matured || 0)}</strong></div>
          <div class="or-diag-card">CA exclusions<strong>${html(s.corporate_action_exclusions || 0)}</strong></div>
          <div class="or-diag-card">CA unchecked<strong>${html(s.corporate_action_unchecked || 0)}</strong></div>
          <div class="or-diag-card">Missing news<strong>${html(s.missing_news_count || 0)}</strong></div>
          <div class="or-diag-card">Missing fundamentals<strong>${html(s.missing_fundamentals_count || 0)}</strong></div>
          <div class="or-diag-card">Enrichment failures<strong>${html(s.enrichment_failure_count || 0)}</strong></div>
        </div>
        <div><b>${calibrated ? 'Calibration state' : 'Why probability is not enabled'}</b><br>${listText(d.calibration_reasons, calibrated ? 'A passed calibration is active for new signals.' : 'Configured calibration gates have passed.')}</div>
        <div style="margin-top:12px"><b>Performance by score bucket</b>${diagnosticTable(d.score_buckets)}</div>
        <div style="margin-top:12px"><b>Current versions</b><br>${html(d.contract?.versions?.scoring_model_version || '—')} · ${html(d.contract?.versions?.scoring_config_version || '—')} · calibration ${html(d.active_calibration_model_version || 'not active')}</div>
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