(() => {
  const rows = document.getElementById('rows');
  const notice = document.getElementById('notice');
  const scanBtn = document.getElementById('scanBtn');
  const chatBtn = document.getElementById('chatBtn');
  const lastScan = document.getElementById('lastScan');
  const screened = document.getElementById('screened');
  const count = document.getElementById('count');
  const cutoff = document.getElementById('cutoff');
  let currentScanId = null;
  let pollTimer = null;

  const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt = (value, digits = 1) => value == null ? '—' : Number(value).toFixed(digits);
  const when = (value) => value ? new Date(value).toLocaleString() : '—';
  const scoreClass = (value) => Number(value) >= 70 ? 'good' : Number(value) >= 55 ? 'mid' : 'bad';
  const initialViewClass = (value) => {
    const view = String(value || '').trim().toLowerCase();
    if (view === 'pass') return 'good';
    if (view === 'watch') return 'mid';
    if (view === 'fail') return 'bad';
    return '';
  };

  function setNotice(text, isError = false) {
    notice.textContent = text;
    notice.className = isError ? 'notice error' : 'notice';
  }

  function explanation(row) {
    const risk = (row.risk_flags || []).join(', ') || 'no major rule-based risk flags';
    return `D ${fmt(row.dislocation_score,0)} · F ${fmt(row.fundamental_survivability,0)} · R ${fmt(row.catalyst_reversibility,0)} · Damage ${fmt(row.impairment_risk,0)} · Conf ${fmt(row.confidence,0)}. ${risk}.`;
  }

  function render(payload) {
    const scan = payload.scan;
    const candidates = payload.candidates || [];
    currentScanId = scan?.id || null;
    lastScan.textContent = when(scan?.completed_at || scan?.started_at);
    screened.textContent = scan?.asset_count ?? '—';
    count.textContent = scan?.candidate_count ?? candidates.length;
    cutoff.textContent = when(scan?.evidence_cutoff);
    chatBtn.disabled = !(scan?.status === 'completed' && candidates.length);

    if (!scan) {
      rows.innerHTML = '<tr><td colspan="8" class="empty">No Oversold V2 scan yet. Run the first scan.</td></tr>';
      setNotice('No scan has been run yet.');
      return;
    }
    if (scan.status === 'running') {
      rows.innerHTML = '<tr><td colspan="8" class="empty">Scan running…</td></tr>';
      setNotice('Scanning Alpaca US equities and enriching the largest losers with point-in-time news and fundamentals…');
      schedulePoll();
      return;
    }
    if (scan.status === 'failed') {
      rows.innerHTML = '<tr><td colspan="8" class="empty">Scan failed.</td></tr>';
      setNotice(scan.error || 'Scan failed.', true);
      return;
    }

    setNotice(`Completed. ${candidates.length} candidates ranked by oversold potential.`);
    rows.innerHTML = candidates.length ? candidates.map(row => `
      <tr>
        <td>${esc(row.rank)}</td>
        <td><div class="ticker">${esc(row.symbol)}</div><div class="muted">${esc(row.name || '')}</div></td>
        <td class="bad">${fmt(row.drop_pct)}%</td>
        <td><span class="score ${scoreClass(row.oversold_score)}">${fmt(row.oversold_score)}</span><div class="muted">/100</div></td>
        <td><span class="pill">${esc(row.fundamental_quality)}</span></td>
        <td class="details"><strong>${esc(row.catalyst_class)}</strong><div class="muted">${esc(row.catalyst_summary)}</div></td>
        <td><span class="pill ${initialViewClass(row.initial_view)}">${esc(row.initial_view)}</span></td>
        <td class="details muted">${esc(explanation(row))}</td>
      </tr>`).join('') : '<tr><td colspan="8" class="empty">No qualifying losers in this scan.</td></tr>';
  }

  async function loadLatest() {
    try {
      const response = await fetch('/api/oversold-v2/latest', {cache: 'no-store'});
      if (!response.ok) throw new Error(await response.text());
      render(await response.json());
    } catch (error) {
      setNotice(`Could not load latest scan: ${error.message}`, true);
    }
  }

  async function loadScan(id) {
    try {
      const response = await fetch(`/api/oversold-v2/scans/${encodeURIComponent(id)}`, {cache: 'no-store'});
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      render(payload);
      return payload;
    } catch (error) {
      setNotice(`Could not refresh scan: ${error.message}`, true);
      return null;
    }
  }

  function schedulePoll() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      if (currentScanId) await loadScan(currentScanId);
      else await loadLatest();
    }, 2500);
  }

  scanBtn.addEventListener('click', async () => {
    scanBtn.disabled = true;
    chatBtn.disabled = true;
    setNotice('Starting scan…');
    try {
      const response = await fetch('/api/oversold-v2/run', {method: 'POST'});
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      currentScanId = payload.scan_id;
      setNotice('Scan started.');
      schedulePoll();
    } catch (error) {
      setNotice(`Could not start scan: ${error.message}`, true);
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
      if (!response.ok) throw new Error(await response.text());
      const {prompt} = await response.json();
      try { await navigator.clipboard.writeText(prompt); } catch (_) {}
      const target = `https://chatgpt.com/?q=${encodeURIComponent(prompt)}`;
      if (popup) popup.location.replace(target); else window.open(target, '_blank');
      setNotice('Top 10 prompt opened in ChatGPT and copied to the clipboard as a fallback.');
    } catch (error) {
      if (popup) popup.close();
      setNotice(`Could not prepare ChatGPT analysis: ${error.message}`, true);
    } finally {
      chatBtn.disabled = false;
    }
  });

  loadLatest();
})();
