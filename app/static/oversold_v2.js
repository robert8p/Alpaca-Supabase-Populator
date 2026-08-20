(() => {
  const rows = document.getElementById('rows');
  const notice = document.getElementById('notice');
  const scanBtn = document.getElementById('scanBtn');
  const chatBtn = document.getElementById('chatBtn');
  const lastScan = document.getElementById('lastScan');
  const screened = document.getElementById('screened');
  const count = document.getElementById('count');
  const cutoff = document.getElementById('cutoff');
  const modelStatus = document.getElementById('modelStatus');
  let currentScanId = null;
  let pollTimer = null;

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt = (value, digits = 1) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits);
  const when = value => value ? new Date(value).toLocaleString() : '—';
  const scoreClass = value => Number(value) >= 72 ? 'good' : Number(value) >= 48 ? 'mid' : 'bad';
  const initialViewClass = value => {
    const view = String(value || '').trim().toLowerCase();
    if (view === 'pass') return 'good';
    if (view === 'watch') return 'mid';
    if (view === 'fail' || view === 'investigate') return 'bad';
    return 'neutral';
  };
  const causeStatusClass = value => String(value || '').toUpperCase().includes('VERIFIED') && !String(value || '').toUpperCase().includes('UNVERIFIED') ? 'verified' : 'unverified';

  function setNotice(text, isError = false) {
    notice.textContent = text;
    notice.className = isError ? 'notice error' : 'notice';
  }

  async function errorText(response) {
    try {
      const payload = await response.json();
      return payload.detail || JSON.stringify(payload);
    } catch (_) {
      return response.text();
    }
  }

  function explanation(row) {
    const failed = Array.isArray(row.failed_gates) ? row.failed_gates : [];
    const friction = row.execution_friction_pct == null ? '—' : `${fmt(row.execution_friction_pct, 2)}%`;
    return `Setup ${fmt(row.setup_score,0)} · Overreaction ${fmt(row.dislocation_score,0)} · Survival ${fmt(row.fundamental_survivability,0)} · Reversal ${fmt(row.catalyst_reversibility,0)} · Confirm ${fmt(row.confirmation_score,0)} · Damage ${fmt(row.impairment_risk,0)} · Conf ${fmt(row.confidence,0)}. ${failed.length} failed gate${failed.length === 1 ? '' : 's'} · friction ${friction}.`;
  }

  function moveCell(row) {
    const session = String(row.price_session || 'unknown').replaceAll('_', ' ');
    const latest = Number(row.latest_move_pct);
    const day = Number(row.drop_pct);
    const different = Number.isFinite(latest) && Number.isFinite(day) && Math.abs(latest - day) >= 0.1;
    return `<span class="bad">${fmt(row.drop_pct)}%</span><div class="muted micro">${esc(session)}${different ? ` · latest ${fmt(latest)}%` : ''}</div>`;
  }

  function render(payload) {
    const scan = payload.scan;
    const candidates = payload.candidates || [];
    currentScanId = scan?.id || null;
    lastScan.textContent = when(scan?.completed_at || scan?.started_at);
    screened.textContent = scan?.asset_count ?? '—';
    count.textContent = scan?.candidate_count ?? candidates.length;
    cutoff.textContent = when(scan?.evidence_cutoff);
    modelStatus.textContent = scan?.model_status ? String(scan.model_status).replaceAll('_', ' ') : '—';
    chatBtn.disabled = !(scan?.status === 'completed' && candidates.length);

    if (!scan) {
      rows.innerHTML = '<tr><td colspan="8" class="empty">No completed or active scan exists. Run the first scan.</td></tr>';
      setNotice('No scan has been run yet.');
      return;
    }
    if (scan.status === 'running') {
      rows.innerHTML = '<tr><td colspan="8" class="empty">Canonical point-in-time scan running…</td></tr>';
      setNotice('Scanning the broad US loser universe, verifying causal evidence and applying robust downside analysis. Full enrichment can take several minutes.');
      schedulePoll();
      return;
    }
    if (scan.status === 'failed') {
      rows.innerHTML = '<tr><td colspan="8" class="empty">The latest scan failed. The previous completed scan remains in history.</td></tr>';
      setNotice(scan.error || 'Scan failed.', true);
      return;
    }

    const exclusions = Number(scan.excluded_non_operating_count || 0);
    const calibration = String(scan.model_status || '').toLowerCase() === 'calibrated' ? '' : ' The score is uncalibrated and must not be read as a probability.';
    setNotice(`Completed. ${candidates.length} researchable candidates ranked by the canonical robust model${exclusions ? `; ${exclusions} shell/non-operating instrument${exclusions === 1 ? '' : 's'} removed` : ''}.${calibration}`);
    rows.innerHTML = candidates.length ? candidates.map(row => `
      <tr>
        <td>${esc(row.rank)}</td>
        <td><div class="ticker">${esc(row.symbol)}</div><div class="muted">${esc(row.name || '')}</div></td>
        <td>${moveCell(row)}</td>
        <td><span class="score ${scoreClass(row.oversold_score)}">${fmt(row.oversold_score)}</span><div class="muted micro">robust /100</div></td>
        <td><span class="pill neutral">${esc(row.fundamental_quality)}</span><div class="muted micro">${esc(row.fundamental_metadata?.form || '')}${row.fundamental_metadata?.age_calendar_days != null ? ` · ${esc(row.fundamental_metadata.age_calendar_days)}d old` : ''}</div></td>
        <td class="details"><strong>${esc(row.catalyst_class)}</strong><span class="cause-status ${causeStatusClass(row.cause_status)}">${esc(row.cause_status)}</span><div class="muted">${esc(row.catalyst_summary)}</div></td>
        <td><span class="pill ${initialViewClass(row.initial_view)}">${esc(row.initial_view)}</span>${row.hard_veto ? '<div class="bad micro">hard veto</div>' : ''}</td>
        <td class="details muted">${esc(explanation(row))}</td>
      </tr>`).join('') : '<tr><td colspan="8" class="empty">No researchable qualifying losers in this scan.</td></tr>';
  }

  async function loadLatest() {
    try {
      const response = await fetch('/api/oversold-v2/latest', {cache: 'no-store'});
      if (!response.ok) throw new Error(await errorText(response));
      render(await response.json());
    } catch (error) {
      setNotice(`Could not load the latest scan: ${error.message}`, true);
    }
  }

  async function loadScan(id) {
    try {
      const response = await fetch(`/api/oversold-v2/scans/${encodeURIComponent(id)}`, {cache: 'no-store'});
      if (!response.ok) throw new Error(await errorText(response));
      const payload = await response.json();
      render(payload);
      return payload;
    } catch (error) {
      setNotice(`Could not refresh the scan: ${error.message}`, true);
      return null;
    }
  }

  function schedulePoll() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      const payload = currentScanId ? await loadScan(currentScanId) : await loadLatest();
      if (payload?.scan?.status === 'running') schedulePoll();
    }, 3000);
  }

  scanBtn.addEventListener('click', async () => {
    scanBtn.disabled = true;
    chatBtn.disabled = true;
    setNotice('Starting the canonical point-in-time scan…');
    try {
      const response = await fetch('/api/oversold-v2/run', {method: 'POST'});
      if (!response.ok) throw new Error(await errorText(response));
      const payload = await response.json();
      currentScanId = payload.scan_id;
      setNotice(payload.duplicate ? 'A recent scan already exists; loading it instead of creating a duplicate.' : 'Scan started.');
      await loadScan(currentScanId);
    } catch (error) {
      setNotice(`Could not start the scan: ${error.message}`, true);
    } finally {
      scanBtn.disabled = false;
    }
  });

  chatBtn.addEventListener('click', async () => {
    if (!currentScanId) return;
    const popup = window.open('about:blank', '_blank');
    chatBtn.disabled = true;
    setNotice('Preparing the independent Top 10 ChatGPT audit…');
    try {
      const response = await fetch(`/api/oversold-v2/chatgpt-prompt?scan_id=${encodeURIComponent(currentScanId)}`, {cache: 'no-store'});
      if (!response.ok) throw new Error(await errorText(response));
      const payload = await response.json();
      const fullPrompt = payload.prompt;
      const launchPrompt = payload.launch_prompt || fullPrompt;
      let copied = false;
      try {
        await navigator.clipboard.writeText(fullPrompt);
        copied = true;
      } catch (_) {}
      const target = `https://chatgpt.com/?q=${encodeURIComponent(launchPrompt)}`;
      if (popup) popup.location.replace(target); else window.open(target, '_blank', 'noopener,noreferrer');
      setNotice(`Top 10 audit opened in ChatGPT${copied ? '; the fuller evidence prompt was also copied to the clipboard' : ''}.`);
    } catch (error) {
      if (popup) popup.close();
      setNotice(`Could not prepare the ChatGPT analysis: ${error.message}`, true);
    } finally {
      chatBtn.disabled = false;
    }
  });

  loadLatest();
})();
