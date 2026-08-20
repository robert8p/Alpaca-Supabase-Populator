(() => {
  'use strict';

  const API_URL = 'https://mnmkxjirpwbptdnvjmpw.supabase.co/functions/v1/intraday-profitability-api';
  const $ = (id) => document.getElementById(id);
  const rows = $('rows');
  const notice = $('notice');
  const noticeText = $('noticeText');
  const backendDot = $('backendDot');
  const scanBtn = $('scanBtn');
  const chatBtn = $('chatBtn');
  const promptBtn = $('promptBtn');
  const loginModal = $('loginModal');
  const promptModal = $('promptModal');
  const promptText = $('promptText');
  const promptMeta = $('promptMeta');

  let credentials = null;
  let currentScan = null;
  let currentCandidates = [];
  let currentRequestId = null;
  let currentPrompt = '';
  let pollTimer = null;

  const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const num = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
  const signed = (value, digits = 2) => value == null ? '—' : `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%`;
  const money = (value) => {
    if (value == null) return '—';
    const number = Number(value);
    if (number >= 1e9) return `$${(number / 1e9).toFixed(1)}b`;
    if (number >= 1e6) return `$${(number / 1e6).toFixed(1)}m`;
    if (number >= 1e3) return `$${(number / 1e3).toFixed(0)}k`;
    return `$${number.toFixed(0)}`;
  };
  const when = (value) => value ? new Date(value).toLocaleString([], {dateStyle:'short', timeStyle:'medium'}) : '—';
  const timeOnly = (value) => value ? new Date(value).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}) : '—';
  const scoreClass = (value) => Number(value) >= 75 ? 'good' : Number(value) >= 63 ? 'mid' : 'bad';

  function setNotice(text, state = '') {
    noticeText.textContent = text;
    notice.className = `notice${state ? ` ${state}` : ''}`;
    backendDot.className = `status-dot${state === 'success' ? ' ok' : ''}`;
  }

  function setActions(enabled, running = false) {
    scanBtn.disabled = !credentials || running;
    chatBtn.disabled = !credentials || !enabled || running;
    promptBtn.disabled = !credentials || !enabled || running;
  }

  function components(row) {
    return [
      ['Liq', row.liquidity_score],
      ['Opp', row.opportunity_score],
      ['Dir', row.directional_score],
      ['Conf', row.confirmation_score],
      ['Exec', row.execution_score],
    ].map(([label, value]) => `<div class="component"><b>${num(value, 0)}</b><span>${label}</span></div>`).join('');
  }

  function render(payload) {
    const scan = payload?.scan || null;
    const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
    currentScan = scan;
    currentCandidates = candidates;
    currentPrompt = '';
    $('lastScan').textContent = when(scan?.completed_at || scan?.started_at);
    $('screened').textContent = scan?.asset_count ?? '—';
    $('liquid').textContent = scan?.liquid_count ?? '—';
    $('enriched').textContent = scan?.enriched_count ?? '—';
    $('cutoff').textContent = timeOnly(scan?.evidence_cutoff);
    $('horizon').textContent = timeOnly(scan?.horizon_end);

    if (!scan) {
      rows.innerHTML = '<tr><td colspan="11" class="empty">No intraday profitability scan exists yet. Run the first SIP scan during the US regular session.</td></tr>';
      setNotice('No scan has been run yet. A full two-hour horizon must remain before the closing bell.');
      setActions(false, false);
      return;
    }
    if (scan.status === 'running') {
      rows.innerHTML = '<tr><td colspan="11" class="empty">Scanning the SIP universe and enriching the strongest liquid stocks with minute bars…</td></tr>';
      setNotice('Scan running: liquidity gate → minute-bar enrichment → long/short setup scoring → cost-adjusted ranking.');
      setActions(false, true);
      return;
    }
    if (scan.status === 'failed') {
      rows.innerHTML = '<tr><td colspan="11" class="empty">The latest scan did not produce a ranking.</td></tr>';
      setNotice(scan.error || 'The scan failed.', 'error');
      setActions(false, false);
      return;
    }

    setActions(candidates.length > 0, false);
    setNotice(`Completed: ${scan.asset_count ?? 0} equities screened, ${scan.liquid_count ?? 0} passed the liquidity gate and ${candidates.length} ranked.`, 'success');
    rows.innerHTML = candidates.length ? candidates.map((row) => {
      const directionClass = row.direction === 'LONG' ? 'long' : 'short';
      const viewClass = row.initial_view === 'INVESTIGATE' ? 'good' : row.initial_view === 'WATCH' ? 'mid' : 'bad';
      return `<tr>
        <td class="rank">${esc(row.rank)}</td>
        <td><div class="ticker">${esc(row.symbol)}</div><div class="company" title="${esc(row.name || '')}">${esc(row.name || '')}</div><div class="tiny">${esc(row.exchange || '')}</div></td>
        <td><span class="pill ${directionClass}">${esc(row.direction)}</span><div class="tiny" style="margin-top:6px">${esc(row.setup_type)}</div></td>
        <td><div class="score ${scoreClass(row.profitability_score)}">${num(row.profitability_score)}</div><div class="tiny">/100 research score</div></td>
        <td class="number"><b>$${num(row.last_price, Number(row.last_price) < 10 ? 3 : 2)}</b><div class="${Number(row.day_move_pct) >= 0 ? 'good' : 'bad'}">${signed(row.day_move_pct)}</div></td>
        <td class="number"><div>5m ${signed(row.return_5m_pct)}</div><div>15m ${signed(row.return_15m_pct)}</div><div>30m ${signed(row.return_30m_pct)}</div><div class="tiny">vs SPY ${signed(row.relative_return_15m_pct)}</div></td>
        <td class="number"><div>${money(row.prev_dollar_volume)} prior</div><div>${money(row.current_dollar_volume)} now</div><div class="tiny">${num(row.relative_volume_pace, 2)}x pace · ${num(row.spread_bps, 1)} bps</div></td>
        <td class="number"><div><b>${num(row.move_capacity_120m_pct, 2)}%</b> capacity</div><div>${num(row.cost_estimate_bps, 1)} bps cost</div><div class="tiny">${num((row.evidence || {}).edge_to_cost_ratio, 1)}x capacity/cost</div></td>
        <td><div class="components">${components(row)}</div></td>
        <td><span class="pill ${viewClass}">${esc(row.initial_view)}</span></td>
        <td class="rationale">${esc(row.rationale)}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="11" class="empty">No stocks had enough clean data to survive all gates.</td></tr>';
  }

  async function api(action, {method = 'GET', body = null, params = {}} = {}) {
    if (!credentials) throw new Error('The app is locked.');
    const url = new URL(API_URL);
    url.searchParams.set('action', action);
    Object.entries(params).forEach(([key, value]) => {
      if (value != null && value !== '') url.searchParams.set(key, String(value));
    });
    const response = await fetch(url, {
      method,
      cache: 'no-store',
      headers: {
        'content-type': 'application/json',
        'x-app-user': credentials.user,
        'x-app-key': credentials.key,
      },
      body: body == null ? null : JSON.stringify(body),
    });
    let payload = null;
    const text = await response.text();
    try { payload = text ? JSON.parse(text) : null; } catch (_) { payload = {detail: text}; }
    if (response.status === 401) {
      lockApp('The credentials were rejected.');
      throw new Error('Unauthorised');
    }
    if (!response.ok) throw new Error(payload?.detail || payload?.error || `Request failed (${response.status})`);
    return payload;
  }

  async function testCredentials() {
    const payload = await api('latest');
    render(payload);
    if (payload.active_request?.id) {
      currentRequestId = payload.active_request.id;
      scheduleRequestPoll();
    }
  }

  function openLogin(message = '') {
    $('loginError').textContent = message;
    loginModal.classList.add('open');
    document.body.style.overflow = 'hidden';
    setTimeout(() => $('loginKey').focus(), 0);
  }

  function closeLogin() {
    loginModal.classList.remove('open');
    document.body.style.overflow = '';
  }

  function lockApp(message = '') {
    credentials = null;
    sessionStorage.removeItem('ip_user');
    sessionStorage.removeItem('ip_key');
    currentRequestId = null;
    currentScan = null;
    currentCandidates = [];
    currentPrompt = '';
    if (pollTimer) clearTimeout(pollTimer);
    setActions(false, false);
    openLogin(message);
  }

  async function unlock() {
    const user = $('loginUser').value.trim();
    const key = $('loginKey').value;
    if (!user || !key) {
      $('loginError').textContent = 'Enter the username and access key.';
      return;
    }
    credentials = {user, key};
    $('loginBtn').disabled = true;
    $('loginError').textContent = 'Checking credentials…';
    try {
      await testCredentials();
      sessionStorage.setItem('ip_user', user);
      sessionStorage.setItem('ip_key', key);
      $('loginKey').value = '';
      closeLogin();
    } catch (error) {
      credentials = null;
      $('loginError').textContent = error.message === 'Unauthorised' ? 'Incorrect username or access key.' : `Could not reach the API: ${error.message}`;
    } finally {
      $('loginBtn').disabled = false;
    }
  }

  function scheduleRequestPoll() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(pollRequest, 2500);
  }

  async function pollRequest() {
    if (!currentRequestId || !credentials) return;
    try {
      const payload = await api('request', {params: {request_id: currentRequestId}});
      const request = payload.request || {};
      if (payload.scan) render(payload);
      if (request.status === 'queued') {
        setNotice('Scan request queued on the existing Alpaca worker.');
        setActions(false, true);
        scheduleRequestPoll();
      } else if (request.status === 'running') {
        setNotice(payload.scan?.status === 'running' ? 'SIP scan running on the existing Alpaca worker…' : 'The worker has claimed the scan request.');
        setActions(false, true);
        scheduleRequestPoll();
      } else if (request.status === 'completed') {
        currentRequestId = null;
        render(payload);
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

  function buildPrompt() {
    if (!currentScan || currentScan.status !== 'completed') throw new Error('No completed scan is selected.');
    const candidates = currentCandidates.slice(0, 10);
    const lines = [
      'Audit these Intraday Profitability candidates as ORIGINAL signals. Do not use hindsight.',
      `Shared evidence cutoff: ${currentScan.evidence_cutoff}. Target horizon ends: ${currentScan.horizon_end}.`,
      'Use only facts, filings, announcements, news and market information published on or before the evidence cutoff.',
      'The app ranking is a transparent, unvalidated quantitative research heuristic. Independently challenge it; do not assume its direction, setup or order is correct.',
      '',
      'For each stock: identify the live catalyst and why it is moving; judge whether that catalyst supports continuation, reversal or rejection of the app setup; assess liquidity and execution risk; identify contradictory evidence; estimate the probability of a positive NET directional return over the next 120 regular-session minutes; give a realistic return range and the main invalidation condition.',
      'Return a best-to-worst table with: rank, ticker, independent direction, P(net profitable), expected net return range, catalyst confidence, key risk, and verdict TRADE LONG / TRADE SHORT / WATCH / PASS.',
      'Explicitly call out every material disagreement with the app. Do not manufacture precision, and do not describe any outcome as certain.',
      '',
    ];
    candidates.forEach((row) => {
      const evidence = row.evidence || {};
      lines.push(
        `${row.rank}. ${row.symbol} (${row.name || row.symbol})`,
        `App: ${row.direction} ${row.setup_type} | Potential-profitability score ${num(row.profitability_score, 1)}/100 | Initial view ${row.initial_view}`,
        `Price $${num(row.last_price, 4)} | Day ${signed(row.day_move_pct)} | Spread ${num(row.spread_bps, 1)} bps | Est. round-trip cost ${num(row.cost_estimate_bps, 1)} bps | 2h move capacity ${num(row.move_capacity_120m_pct, 2)}%`,
        `Returns: 5m ${signed(row.return_5m_pct)}, 15m ${signed(row.return_15m_pct)}, 30m ${signed(row.return_30m_pct)}, 60m ${signed(row.return_60m_pct)} | 15m vs SPY ${signed(row.relative_return_15m_pct)}`,
        `Liquidity: previous-day $${Number(row.prev_dollar_volume || 0).toLocaleString()}; current $${Number(row.current_dollar_volume || 0).toLocaleString()}; volume pace ${num(row.relative_volume_pace, 2)}x; bars used ${evidence.bars_used ?? 'unknown'}`,
        `Components: liquidity ${num(row.liquidity_score, 1)}, opportunity ${num(row.opportunity_score, 1)}, direction ${num(row.directional_score, 1)}, confirmation ${num(row.confirmation_score, 1)}, execution ${num(row.execution_score, 1)}.`,
        `App rationale: ${row.rationale}`,
        '',
      );
    });
    lines.push(
      'Finish with: strongest candidate; strongest reason not to trade it; any candidate that should be rejected despite its app score; and the single most important fact to verify before risking capital.',
      'This is analysis, not a guarantee or an instruction to trade.',
    );
    return lines.join('\n');
  }

  function preparePrompt() {
    currentPrompt = buildPrompt();
    promptText.value = currentPrompt;
    promptMeta.textContent = `${Math.min(10, currentCandidates.length)} candidates · evidence cutoff ${when(currentScan.evidence_cutoff)} · horizon ${when(currentScan.horizon_end)} · ${currentPrompt.length.toLocaleString()} characters`;
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

  async function openChatGPT() {
    const popup = window.open('about:blank', '_blank');
    if (popup) {
      try { popup.opener = null; } catch (_) {}
    }
    try {
      if (!currentPrompt) preparePrompt();
      const copied = await copyText(currentPrompt);
      const target = currentPrompt.length <= 7600 ? `https://chatgpt.com/?q=${encodeURIComponent(currentPrompt)}` : 'https://chatgpt.com/';
      if (popup) popup.location.replace(target);
      openPromptModal();
      setNotice(popup ? `ChatGPT opened${copied ? ' and the frozen prompt was copied to your clipboard' : ''}. Paste the visible prompt if it was not prefilled.` : 'The browser blocked the new tab. The prompt is visible here.', popup ? 'success' : 'error');
    } catch (error) {
      if (popup) popup.close();
      throw error;
    }
  }

  scanBtn.addEventListener('click', async () => {
    setActions(false, true);
    setNotice('Submitting the SIP scan request to the existing Alpaca worker…');
    try {
      const payload = await api('run', {method: 'POST', body: scanBody()});
      currentRequestId = payload.request?.id || null;
      currentPrompt = '';
      setNotice(payload.duplicate ? 'An existing scan request is already active; following it now.' : 'Scan request accepted by the queue.');
      scheduleRequestPoll();
    } catch (error) {
      setNotice(`Could not start the scan: ${error.message}`, 'error');
      setActions(false, false);
    }
  });

  chatBtn.addEventListener('click', async () => {
    chatBtn.disabled = true;
    setNotice('Preparing the point-in-time Top 10 audit prompt…');
    try { await openChatGPT(); }
    catch (error) { setNotice(`Could not prepare the ChatGPT analysis: ${error.message}`, 'error'); }
    finally { chatBtn.disabled = false; }
  });

  promptBtn.addEventListener('click', () => {
    promptBtn.disabled = true;
    try { preparePrompt(); openPromptModal(); }
    catch (error) { setNotice(`Could not prepare the prompt: ${error.message}`, 'error'); }
    finally { promptBtn.disabled = false; }
  });

  $('loginBtn').addEventListener('click', unlock);
  $('loginKey').addEventListener('keydown', (event) => { if (event.key === 'Enter') unlock(); });
  $('logoutBtn').addEventListener('click', () => lockApp());
  $('closePrompt').addEventListener('click', closePromptModal);
  promptModal.addEventListener('click', (event) => { if (event.target === promptModal) closePromptModal(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && promptModal.classList.contains('open')) closePromptModal(); });
  $('copyPrompt').addEventListener('click', async () => {
    const copied = await copyText(promptText.value);
    setNotice(copied ? 'Prompt copied to the clipboard.' : 'Clipboard access was blocked; select and copy the visible prompt.', copied ? 'success' : 'error');
  });
  $('openChat').addEventListener('click', openChatGPT);

  async function bootstrap() {
    try {
      const health = await fetch(`${API_URL}?action=health`, {cache: 'no-store'});
      if (!health.ok) throw new Error(`health ${health.status}`);
      backendDot.classList.add('ok');
    } catch (_) {
      setNotice('The API health check is not responding.', 'error');
    }
    const user = sessionStorage.getItem('ip_user');
    const key = sessionStorage.getItem('ip_key');
    if (user && key) {
      credentials = {user, key};
      try {
        await testCredentials();
        closeLogin();
        return;
      } catch (_) {
        credentials = null;
        sessionStorage.removeItem('ip_user');
        sessionStorage.removeItem('ip_key');
      }
    }
    openLogin();
  }

  bootstrap();
})();
