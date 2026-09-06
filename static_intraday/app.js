(() => {
  'use strict';

  const API_URL = 'https://oxzabweahkoimtevbbny.supabase.co/functions/v1/intraday-profitability-api';
  const CURRENT_MODEL = 'ip-reliability-v3.0';
  const $ = (id) => document.getElementById(id);
  const rows = $('rows');
  const selectedRows = $('selectedRows');
  const notice = $('notice');
  const noticeText = $('noticeText');
  const backendDot = $('backendDot');
  const scanBtn = $('scanBtn');
  const chatBtn = $('chatBtn');
  const promptBtn = $('promptBtn');
  const promptModal = $('promptModal');
  const promptText = $('promptText');
  const promptMeta = $('promptMeta');

  let currentScan = null;
  let currentCandidates = [];
  let currentSelections = [];
  let currentAudit = null;
  let currentTracking = null;
  let selectedCandidateIds = new Set();
  let currentRequestId = null;
  let currentPrompt = '';
  let currentCompactPrompt = '';
  let pollTimer = null;
  let selectionTimer = null;

  const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[char]));
  const number = (value) => {
    if (value == null || Number.isNaN(Number(value))) return null;
    return Number(value);
  };
  const num = (value, digits = 1) => number(value) == null ? '—' : Number(value).toFixed(digits);
  const signed = (value, digits = 2) => number(value) == null ? '—' : `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%`;
  const price = (value) => number(value) == null ? '—' : `$${Number(value).toFixed(Number(value) < 10 ? 3 : 2)}`;
  const money = (value) => {
    if (number(value) == null) return '—';
    const amount = Number(value);
    if (amount >= 1e9) return `$${(amount / 1e9).toFixed(1)}b`;
    if (amount >= 1e6) return `$${(amount / 1e6).toFixed(1)}m`;
    if (amount >= 1e3) return `$${(amount / 1e3).toFixed(0)}k`;
    return `$${amount.toFixed(0)}`;
  };
  const when = (value) => value ? new Date(value).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' }) : '—';
  const timeOnly = (value) => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
  const compactDate = (value) => value ? new Date(`${value}T00:00:00Z`).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }) : '—';
  const priorityClass = (value) => Number(value) >= 55 ? 'mid' : 'bad';

  function setNotice(text, state = '') {
    noticeText.textContent = text;
    notice.className = `notice${state ? ` ${state}` : ''}`;
    backendDot.className = `status-dot${state === 'success' ? ' ok' : ''}`;
  }

  function setActions(enabled, running = false) {
    scanBtn.disabled = running;
    chatBtn.disabled = !enabled || running;
    promptBtn.disabled = !enabled || running;
  }

  function switchTab(panelId) {
    document.querySelectorAll('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.panel === panelId));
    document.querySelectorAll('.panel').forEach((panel) => panel.classList.toggle('active', panel.id === panelId));
    if (panelId === 'selectedPanel') loadSelections({ quiet: true });
  }

  function updateAudit(audit = currentAudit, tracking = currentTracking) {
    currentAudit = audit || currentAudit;
    currentTracking = tracking || currentTracking;
    const active = currentAudit;
    const coverage = currentTracking || {};
    const findings = active?.findings || {};
    $('auditStatus').textContent = active
      ? `${active.status}: no validated generic trading edge`
      : 'Model audit unavailable — treat all rankings as unvalidated';
    $('auditSummary').textContent = active?.summary
      || 'The app will not display trade-quality claims until the frozen validation and external-holdout gates support them.';
    $('auditStates').textContent = active ? Number(findings.total_point_in_time_states || 0).toLocaleString() : '—';
    $('auditRobust').textContent = active
      ? `${active.robust_candidates_passed ?? 0}/${active.registered_robust_candidates ?? 0}`
      : '—';
    $('auditHoldout').textContent = active
      ? `${compactDate(active.holdout_start)} – ${compactDate(active.holdout_end)}`
      : '—';
    $('auditTracking').textContent = Number(coverage.horizon_matured || 0).toLocaleString();
    $('trackedCount').textContent = Number(coverage.total_candidates_tracked || 0).toLocaleString();
    $('trackingErrors').textContent = Number(coverage.tracking_errors || 0).toLocaleString();
  }

  function evidenceComponents(row) {
    const evidence = row.evidence || {};
    return [
      ['Dir', evidence.directional_evidence_score],
      ['Move', evidence.movement_opportunity_score],
      ['Exec', evidence.execution_quality_score],
      ['Data', evidence.data_quality_score],
    ].map(([label, value]) => `<div class="component"><b>${num(value, 0)}</b><span>${label}</span></div>`).join('');
  }

  function updateSelectButtons() {
    document.querySelectorAll('[data-select-candidate]').forEach((button) => {
      const selected = selectedCandidateIds.has(Number(button.dataset.selectCandidate));
      button.disabled = selected;
      button.classList.toggle('selected', selected);
      button.textContent = selected ? 'Selected' : 'Select';
    });
  }

  function scanIsCurrent(scan) {
    return scan?.scoring_version === CURRENT_MODEL || scan?.metadata?.model_audit_version === CURRENT_MODEL;
  }

  function render(payload) {
    const scan = payload?.scan || null;
    const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
    currentScan = scan;
    currentCandidates = candidates;
    currentPrompt = '';
    currentCompactPrompt = '';
    updateAudit(payload?.model_audit, payload?.tracking_summary);

    $('lastScan').textContent = when(scan?.completed_at || scan?.started_at);
    $('screened').textContent = scan?.asset_count ?? '—';
    $('liquid').textContent = scan?.liquid_count ?? '—';
    $('enriched').textContent = scan?.enriched_count ?? '—';
    $('cutoff').textContent = timeOnly(scan?.evidence_cutoff);
    $('horizon').textContent = timeOnly(scan?.horizon_end);

    if (!scan) {
      rows.innerHTML = '<tr><td colspan="13" class="empty">No completed scan exists yet. Run a SIP scan during the US regular session while a complete two-hour horizon remains.</td></tr>';
      setNotice('No scan has been run yet. The reliability audit is active, but a current-session ranking is not available.');
      setActions(false, false);
      return;
    }
    if (scan.status === 'running') {
      rows.innerHTML = '<tr><td colspan="13" class="empty">Scanning the SIP universe, validating market data and building research hypotheses…</td></tr>';
      setNotice('Scan running: executable liquidity gate → feature validation → reliability policy → all-candidate tracking enrolment.');
      setActions(false, true);
      return;
    }
    if (scan.status === 'failed') {
      rows.innerHTML = '<tr><td colspan="13" class="empty">The latest scan did not produce a ranking.</td></tr>';
      setNotice(scan.error || 'The scan failed.', 'error');
      setActions(false, false);
      return;
    }

    const currentModel = scanIsCurrent(scan);
    setActions(candidates.length > 0, false);
    if (currentModel) {
      setNotice(`Reliability-v3 scan complete: ${scan.asset_count ?? 0} equities screened, ${scan.liquid_count ?? 0} passed liquidity and ${candidates.length} research hypotheses were ranked and enrolled for unbiased outcome tracking.`, 'success');
    } else {
      setNotice(`The displayed scan predates reliability v3 (${scan.scoring_version || 'unknown model'}). It remains visible for continuity, but its scores are legacy research values. Run a new scan during the next eligible US session.`, 'error');
    }

    rows.innerHTML = candidates.length ? candidates.map((row) => {
      const evidence = row.evidence || {};
      const directionClass = row.direction === 'LONG' ? 'long' : 'short';
      const dispositionClass = row.initial_view === 'PASS' ? 'bad' : 'mid';
      const isSelected = selectedCandidateIds.has(Number(row.id));
      const legacy = !currentModel || evidence.model_audit_version !== CURRENT_MODEL;
      const reliabilityLabel = legacy ? 'LEGACY / UNAUDITED' : (evidence.reliability_label || 'NO VALIDATED EDGE');
      const historicalMean = evidence.historical_holdout_mean_net_pct;
      const historicalN = evidence.historical_holdout_n;
      const referenceDefinition = evidence.reference_price_definition || (legacy ? 'legacy last trade reference' : 'quote-side executable reference');
      return `<tr>
        <td><button class="btn small ${isSelected ? 'selected' : ''}" data-select-candidate="${esc(row.id)}" ${isSelected ? 'disabled' : ''}>${isSelected ? 'Selected' : 'Select'}</button></td>
        <td class="rank">${esc(row.rank)}</td>
        <td><div class="ticker">${esc(row.symbol)}</div><div class="company" title="${esc(row.name || '')}">${esc(row.name || '')}</div><div class="tiny">${esc(row.exchange || '')}</div></td>
        <td><span class="pill ${directionClass}">${esc(row.direction)}</span><div class="tiny" style="margin-top:6px">${esc(row.setup_type)} hypothesis</div></td>
        <td><div class="score ${priorityClass(row.profitability_score)}">${num(row.profitability_score)}</div><div class="tiny">/100 analysis priority</div></td>
        <td><span class="pill bad">${esc(reliabilityLabel)}</span><div class="tiny" style="margin-top:7px">Trade gate ${esc(evidence.trade_gate || 'BLOCKED')}</div><div class="tiny">Holdout n=${historicalN ?? '—'} · mean ${signed(historicalMean, 3)}</div></td>
        <td class="number"><b>${price(row.last_price)}</b><div class="${Number(row.day_move_pct) >= 0 ? 'good' : 'bad'}">${signed(row.day_move_pct)}</div><div class="tiny">${esc(referenceDefinition)}</div></td>
        <td class="number"><div>5m ${signed(row.return_5m_pct)}</div><div>15m ${signed(row.return_15m_pct)}</div><div>30m ${signed(row.return_30m_pct)}</div><div>60m ${signed(row.return_60m_pct)}</div><div class="tiny">15m vs SPY ${signed(row.relative_return_15m_pct)}</div></td>
        <td class="number"><div>${money(row.prev_dollar_volume)} prior</div><div>${money(row.current_dollar_volume)} now</div><div class="tiny">${num(row.relative_volume_pace, 2)}x pace · ${num(row.spread_bps, 1)} bps spread</div></td>
        <td class="number"><div><b>${num(row.move_capacity_120m_pct, 2)}%</b> estimated movement</div><div>${num(row.cost_estimate_bps, 1)} bps estimated cost</div><div class="tiny">${num(evidence.edge_to_cost_ratio, 1)}x capacity/cost — not expected return</div></td>
        <td><div class="components">${evidenceComponents(row)}</div></td>
        <td><span class="pill ${dispositionClass}">${esc(legacy ? 'LEGACY' : row.initial_view)}</span></td>
        <td class="rationale">${esc(row.rationale)}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="13" class="empty">No stocks had enough clean data to survive all gates.</td></tr>';
    updateSelectButtons();
  }

  function directionalMove(selection, value, baseValue = null) {
    const base = number(baseValue) ?? number(selection.entry_price) ?? number(selection.scan_price);
    const target = number(value);
    if (base == null || target == null || base <= 0) return null;
    const raw = (target / base - 1) * 100;
    return selection.direction === 'SHORT' ? -raw : raw;
  }

  function renderSelections(selections, audit = null, tracking = null) {
    currentSelections = Array.isArray(selections) ? selections : [];
    selectedCandidateIds = new Set(currentSelections.map((row) => Number(row.candidate_id)));
    $('selectionCount').textContent = String(currentSelections.length);
    updateAudit(audit, tracking);
    if (!currentSelections.length) {
      selectedRows.innerHTML = '<tr><td colspan="13" class="empty">No stocks have been selected. Every ranked candidate is still tracked automatically; this tab contains only the signals you explicitly select for review.</td></tr>';
      updateSelectButtons();
      return;
    }
    selectedRows.innerHTML = currentSelections.map((row) => {
      const directionClass = row.direction === 'LONG' ? 'long' : 'short';
      const base = number(row.entry_price) ?? number(row.scan_price);
      const bestMove = directionalMove(row, row.favourable_extreme_price, base);
      const horizonMove = directionalMove(row, row.horizon_price, base);
      const closeMove = directionalMove(row, row.close_price, base);
      const statusClass = row.status === 'closed' && row.horizon_status === 'matured' ? 'good' : row.refresh_error ? 'bad' : 'mid';
      const bestLabel = row.direction === 'LONG' ? 'Highest high' : 'Lowest low';
      return `<tr>
        <td><div>${when(row.user_selected_at || row.selected_at)}</div><div class="tiny">Scan ${when(row.scan_at)}</div></td>
        <td><div class="ticker">${esc(row.symbol)}</div><div class="company">${esc(row.name || '')}</div></td>
        <td><span class="pill ${directionClass}">${esc(row.direction)}</span><div class="tiny" style="margin-top:6px">${esc(row.setup_type)}</div></td>
        <td class="number"><b>#${esc(row.selected_rank)}</b><div>${num(row.profitability_score, 1)}/100 priority</div></td>
        <td class="number"><b>${price(row.scan_price)}</b><div class="tiny">Quote-side reference at cutoff</div></td>
        <td class="number"><b>${price(row.entry_price)}</b><div class="tiny">${row.entry_at ? timeOnly(row.entry_at) : 'Awaiting first full minute'}</div></td>
        <td class="number"><b>${price(row.favourable_extreme_price)}</b><div class="tiny">${bestLabel}${row.favourable_extreme_at ? ` · ${timeOnly(row.favourable_extreme_at)}` : ''}</div></td>
        <td class="number"><b>${price(row.horizon_price)}</b><div class="tiny">${row.horizon_at ? timeOnly(row.horizon_at) : 'Pending fixed horizon'}</div></td>
        <td class="number"><b>${price(row.close_price)}</b><div class="tiny">${row.close_at ? timeOnly(row.close_at) : 'Pending close'}</div></td>
        <td class="number ${number(bestMove) != null && Number(bestMove) >= 0 ? 'good' : 'bad'}"><b>${signed(bestMove)}</b></td>
        <td class="number ${number(horizonMove) != null && Number(horizonMove) >= 0 ? 'good' : 'bad'}"><b>${signed(horizonMove)}</b></td>
        <td class="number ${number(closeMove) != null && Number(closeMove) >= 0 ? 'good' : 'bad'}"><b>${signed(closeMove)}</b></td>
        <td><span class="pill ${statusClass}">${esc(row.horizon_status || 'pending')} 2h</span><div class="tiny" style="margin-top:6px">Close: ${esc(row.status)}</div><div class="tiny">${row.last_refreshed_at ? `Refreshed ${when(row.last_refreshed_at)}` : 'Awaiting refresh'}</div>${row.refresh_error ? `<div class="tiny bad">${esc(row.refresh_error)}</div>` : ''}</td>
      </tr>`;
    }).join('');
    updateSelectButtons();
  }

  async function api(action, { method = 'GET', body = null, params = {} } = {}) {
    const url = new URL(API_URL);
    url.searchParams.set('action', action);
    Object.entries(params).forEach(([key, value]) => {
      if (value != null && value !== '') url.searchParams.set(key, String(value));
    });
    const response = await fetch(url, {
      method,
      cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: body == null ? null : JSON.stringify(body),
    });
    const text = await response.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch (_) { payload = { detail: text }; }
    if (!response.ok) {
      const retry = payload?.retry_after_seconds ? ` Try again in about ${payload.retry_after_seconds} seconds.` : '';
      throw new Error(`${payload?.detail || payload?.error || `Request failed (${response.status})`}${retry}`);
    }
    return payload;
  }

  async function loadSelections({ quiet = false } = {}) {
    try {
      const payload = await api('selections');
      renderSelections(payload?.selections || [], payload?.model_audit, payload?.tracking_summary);
      if (!quiet) setNotice(`Loaded ${currentSelections.length} selected signal${currentSelections.length === 1 ? '' : 's'}; ${Number(payload?.tracking_summary?.total_candidates_tracked || 0).toLocaleString()} ranked candidates are tracked automatically.`, 'success');
    } catch (error) {
      if (!quiet) setNotice(`Could not load selected outcomes: ${error.message}`, 'error');
    }
  }

  async function loadInitialState() {
    const [latest, selections] = await Promise.all([api('latest'), api('selections')]);
    renderSelections(selections?.selections || [], selections?.model_audit, selections?.tracking_summary);
    render(latest);
    if (latest.active_request?.id) {
      currentRequestId = latest.active_request.id;
      scheduleRequestPoll();
    }
    scheduleSelectionRefresh();
  }

  function scheduleRequestPoll() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(pollRequest, 2500);
  }

  function scheduleSelectionRefresh() {
    if (selectionTimer) clearTimeout(selectionTimer);
    selectionTimer = setTimeout(async () => {
      await loadSelections({ quiet: true });
      scheduleSelectionRefresh();
    }, 30000);
  }

  async function pollRequest() {
    if (!currentRequestId) return;
    try {
      const payload = await api('request', { params: { request_id: currentRequestId } });
      const request = payload.request || {};
      if (payload.scan) render(payload);
      updateAudit(payload?.model_audit, payload?.tracking_summary);
      if (request.status === 'queued') {
        setNotice('Scan request queued on the Alpaca worker.');
        setActions(false, true);
        scheduleRequestPoll();
      } else if (request.status === 'running') {
        setNotice(payload.scan?.status === 'running' ? 'SIP scan and reliability processing are running…' : 'The worker has claimed the scan request.');
        setActions(false, true);
        scheduleRequestPoll();
      } else if (request.status === 'completed') {
        currentRequestId = null;
        render(payload);
        await loadSelections({ quiet: true });
      } else if (request.status === 'failed') {
        currentRequestId = null;
        render(payload);
        setNotice(request.error || payload.scan?.error || 'The scan request failed.', 'error');
        setActions(false, false);
      }
    } catch (error) {
      setNotice(`Could not refresh the scan request: ${error.message}`, 'error');
      scheduleRequestPoll();
    }
  }

  function scanBody() {
    return {
      direction: $('direction').value,
      min_price: Number($('minPrice').value),
      min_prev_dollar_volume: Number($('prevDv').value),
      min_current_dollar_volume: Number($('currentDv').value),
      max_spread_bps: Number($('spread').value),
      prefilter_limit: Number($('prefilter').value),
      candidate_limit: 50,
    };
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); return true; } catch (_) {}
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(area);
    return copied;
  }

  function preparePrompt() {
    currentPrompt = window.IPPrompt.buildFullPrompt(currentScan, currentCandidates, currentAudit, currentTracking);
    currentCompactPrompt = window.IPPrompt.buildCompactPrompt(currentScan, currentCandidates, currentAudit, currentTracking);
    promptText.value = currentPrompt;
    promptMeta.textContent = `${Math.min(10, currentCandidates.length)} candidates · cutoff ${when(currentScan.evidence_cutoff)} · ${currentAudit?.status || 'audit unavailable'} · full ${currentPrompt.length.toLocaleString()} chars · populated handoff ${currentCompactPrompt.length.toLocaleString()} chars`;
    return currentPrompt;
  }

  function openPromptModal() {
    promptModal.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closePromptModal() {
    promptModal.classList.remove('open');
    document.body.style.overflow = '';
  }

  function openChatGPT() {
    if (!currentPrompt || !currentCompactPrompt) preparePrompt();
    const target = window.IPPrompt.chatGptUrl(currentCompactPrompt);
    const opened = window.open(target, '_blank', 'noopener,noreferrer');
    copyText(currentPrompt).then((copied) => {
      setNotice(`${opened === null ? 'ChatGPT launch was handed to the browser' : 'ChatGPT opened with the populated reliability-aware prompt'}${copied ? '; the full evidence prompt was also copied' : ''}.`, 'success');
    });
    openPromptModal();
    return target;
  }

  async function selectCandidate(candidateId, button) {
    button.disabled = true;
    button.textContent = 'Selecting…';
    try {
      const payload = await api('select', { method: 'POST', body: { candidate_id: Number(candidateId) } });
      await loadSelections({ quiet: true });
      button.classList.add('selected');
      button.textContent = 'Selected';
      switchTab('selectedPanel');
      setNotice(payload?.duplicate ? 'That signal was already selected; its tracked outcomes are open.' : 'Signal added to your selected view. It was already enrolled in the unbiased all-candidate outcome tracker.', 'success');
    } catch (error) {
      button.disabled = false;
      button.textContent = 'Select';
      setNotice(`Could not select the signal: ${error.message}`, 'error');
    }
  }

  rows.addEventListener('click', (event) => {
    const button = event.target.closest('[data-select-candidate]');
    if (button) selectCandidate(button.dataset.selectCandidate, button);
  });
  document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => switchTab(tab.dataset.panel)));
  $('refreshSelections').addEventListener('click', () => loadSelections());
  scanBtn.addEventListener('click', async () => {
    setActions(false, true);
    setNotice('Submitting the SIP scan request to the reliability-first worker…');
    try {
      const payload = await api('run', { method: 'POST', body: scanBody() });
      currentRequestId = payload.request?.id || null;
      currentPrompt = '';
      currentCompactPrompt = '';
      setNotice(payload.duplicate ? 'An existing scan request is already active; following it now.' : 'Scan request accepted. Every resulting ranked candidate will be tracked automatically.');
      scheduleRequestPoll();
    } catch (error) {
      setNotice(`Could not start the scan: ${error.message}`, 'error');
      setActions(false, false);
    }
  });
  chatBtn.addEventListener('click', () => {
    try { openChatGPT(); } catch (error) { setNotice(`Could not prepare the ChatGPT analysis: ${error.message}`, 'error'); }
  });
  promptBtn.addEventListener('click', () => {
    try { preparePrompt(); openPromptModal(); } catch (error) { setNotice(`Could not prepare the prompt: ${error.message}`, 'error'); }
  });
  $('closePrompt').addEventListener('click', closePromptModal);
  promptModal.addEventListener('click', (event) => { if (event.target === promptModal) closePromptModal(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && promptModal.classList.contains('open')) closePromptModal(); });
  $('copyPrompt').addEventListener('click', async () => {
    const copied = await copyText(promptText.value);
    setNotice(copied ? 'Full reliability-aware prompt copied to the clipboard.' : 'Clipboard access was blocked; select and copy the visible prompt.', copied ? 'success' : 'error');
  });
  $('openChat').addEventListener('click', () => {
    try { openChatGPT(); } catch (error) { setNotice(`Could not open ChatGPT: ${error.message}`, 'error'); }
  });

  async function bootstrap() {
    setNotice('Loading the latest scan, reliability audit and prospective outcome coverage…');
    try {
      const health = await fetch(`${API_URL}?action=health`, { cache: 'no-store' });
      if (!health.ok) throw new Error(`health ${health.status}`);
      backendDot.classList.add('ok');
      await loadInitialState();
    } catch (error) {
      setNotice(`The public scanner API is not ready: ${error.message}`, 'error');
      setActions(false, false);
    }
  }

  window.__IP_TEST__ = {
    buildCompactPrompt: () => window.IPPrompt.buildCompactPrompt(currentScan, currentCandidates, currentAudit, currentTracking),
    buildFullPrompt: () => window.IPPrompt.buildFullPrompt(currentScan, currentCandidates, currentAudit, currentTracking),
    openChatGPT: () => openChatGPT(),
    compactLimit: window.IPPrompt.COMPACT_LIMIT,
    currentModel: () => CURRENT_MODEL,
  };

  bootstrap();
})();
