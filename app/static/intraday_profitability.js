(() => {
  const $ = (id) => document.getElementById(id);
  const rows = $('rows');
  const notice = $('notice');
  const scanBtn = $('scanBtn');
  const chatBtn = $('chatBtn');
  const promptBtn = $('promptBtn');
  const modal = $('promptModal');
  const promptText = $('promptText');
  const promptMeta = $('promptMeta');
  let currentScanId = null;
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
    notice.textContent = text;
    notice.className = `notice${state ? ` ${state}` : ''}`;
  }

  function setActions(enabled, running = false) {
    scanBtn.disabled = running;
    chatBtn.disabled = !enabled || running;
    promptBtn.disabled = !enabled || running;
  }

  function components(row) {
    return [
      ['Liq', row.liquidity_score],
      ['Opp', row.opportunity_score],
      ['Dir', row.directional_score],
      ['Conf', row.confirmation_score],
      ['Exec', row.execution_score],
    ].map(([label, value]) => `<div class="component"><b>${num(value,0)}</b><span>${label}</span></div>`).join('');
  }

  function render(payload) {
    const scan = payload.scan;
    const candidates = payload.candidates || [];
    currentScanId = scan?.id || null;
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
      schedulePoll();
      return;
    }
    if (scan.status === 'failed') {
      rows.innerHTML = '<tr><td colspan="11" class="empty">The scan did not produce a ranking.</td></tr>';
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
        <td class="number"><b>$${num(row.last_price, row.last_price < 10 ? 3 : 2)}</b><div class="${Number(row.day_move_pct) >= 0 ? 'good' : 'bad'}">${signed(row.day_move_pct)}</div></td>
        <td class="number"><div>5m ${signed(row.return_5m_pct)}</div><div>15m ${signed(row.return_15m_pct)}</div><div>30m ${signed(row.return_30m_pct)}</div><div class="tiny">vs SPY ${signed(row.relative_return_15m_pct)}</div></td>
        <td class="number"><div>${money(row.prev_dollar_volume)} prior</div><div>${money(row.current_dollar_volume)} now</div><div class="tiny">${num(row.relative_volume_pace,2)}x pace · ${num(row.spread_bps,1)} bps</div></td>
        <td class="number"><div><b>${num(row.move_capacity_120m_pct,2)}%</b> capacity</div><div>${num(row.cost_estimate_bps,1)} bps cost</div><div class="tiny">${num((row.evidence || {}).edge_to_cost_ratio,1)}x capacity/cost</div></td>
        <td><div class="components">${components(row)}</div></td>
        <td><span class="pill ${viewClass}">${esc(row.initial_view)}</span></td>
        <td class="rationale">${esc(row.rationale)}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="11" class="empty">No stocks had enough clean data to survive all gates.</td></tr>';
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {cache:'no-store', credentials:'same-origin', ...options});
    if (!response.ok) {
      let message = await response.text();
      try { message = JSON.parse(message).detail || message; } catch (_) {}
      throw new Error(message);
    }
    return response.json();
  }

  async function loadLatest() {
    try { render(await api('/api/intraday-profitability/latest')); }
    catch (error) { setNotice(`Could not load the latest scan: ${error.message}`, 'error'); }
  }

  async function loadScan(id) {
    try {
      const payload = await api(`/api/intraday-profitability/scans/${encodeURIComponent(id)}`);
      render(payload);
      return payload;
    } catch (error) {
      setNotice(`Could not refresh the scan: ${error.message}`, 'error');
      setActions(false, false);
      return null;
    }
  }

  function schedulePoll() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      if (currentScanId) await loadScan(currentScanId); else await loadLatest();
    }, 2500);
  }

  function scanQuery() {
    const params = new URLSearchParams({
      direction: $('direction').value,
      min_price: $('minPrice').value,
      min_prev_dollar_volume: $('prevDv').value,
      min_current_dollar_volume: $('currentDv').value,
      max_spread_bps: $('spread').value,
      prefilter_limit: $('prefilter').value,
      candidate_limit: '50',
    });
    return params.toString();
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

  async function preparePrompt() {
    if (!currentScanId) throw new Error('No completed scan is selected.');
    const data = await api(`/api/intraday-profitability/chatgpt-prompt?scan_id=${encodeURIComponent(currentScanId)}`);
    currentPrompt = data.prompt;
    promptText.value = currentPrompt;
    promptMeta.textContent = `${data.candidate_count} candidates · evidence cutoff ${when(data.evidence_cutoff)} · horizon ${when(data.horizon_end)} · ${data.prompt_characters.toLocaleString()} characters`;
    return data;
  }

  function openModal() { modal.classList.add('open'); document.body.style.overflow = 'hidden'; }
  function closeModal() { modal.classList.remove('open'); document.body.style.overflow = ''; }

  async function openChatGPT() {
    // Open synchronously inside the click gesture so mobile and strict desktop browsers do not block it.
    const popup = window.open('about:blank', '_blank');
    if (popup) {
      try { popup.opener = null; } catch (_) {}
    }
    try {
      if (!currentPrompt) await preparePrompt();
      const copied = await copyText(currentPrompt);
      // Best-effort prefill for compact prompts; clipboard + visible prompt is the reliable fallback.
      const target = currentPrompt.length <= 7600
        ? `https://chatgpt.com/?q=${encodeURIComponent(currentPrompt)}`
        : 'https://chatgpt.com/';
      if (popup) popup.location.replace(target);
      openModal();
      setNotice(popup
        ? `ChatGPT opened${copied ? ' and the frozen prompt was copied to your clipboard' : ''}. Paste the visible prompt if it was not prefilled.`
        : 'The browser blocked the new tab. The prompt is visible here and has been copied where permitted.', popup ? 'success' : 'error');
    } catch (error) {
      if (popup) popup.close();
      throw error;
    }
  }

  scanBtn.addEventListener('click', async () => {
    setActions(false, true);
    setNotice('Starting the SIP scan…');
    try {
      const payload = await api(`/api/intraday-profitability/run?${scanQuery()}`, {method:'POST'});
      currentScanId = payload.scan_id;
      currentPrompt = '';
      setNotice(payload.duplicate ? 'An existing scan is still running; following it now.' : 'Scan started.');
      schedulePoll();
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

  promptBtn.addEventListener('click', async () => {
    promptBtn.disabled = true;
    try { await preparePrompt(); openModal(); }
    catch (error) { setNotice(`Could not prepare the prompt: ${error.message}`, 'error'); }
    finally { promptBtn.disabled = false; }
  });

  $('closePrompt').addEventListener('click', closeModal);
  modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeModal(); });
  $('copyPrompt').addEventListener('click', async () => {
    const copied = await copyText(promptText.value);
    setNotice(copied ? 'Prompt copied to the clipboard.' : 'Clipboard access was blocked; select and copy the visible prompt.', copied ? 'success' : 'error');
  });
  $('openChat').addEventListener('click', openChatGPT);

  loadLatest();
})();
