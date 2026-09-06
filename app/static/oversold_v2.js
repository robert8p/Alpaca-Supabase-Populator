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
  const modelVersion = document.getElementById('modelVersion');
  let currentScanId = null;
  let pollTimer = null;

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt = (value, digits = 1) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits);
  const when = value => value && !Number.isNaN(new Date(value).getTime()) ? new Date(value).toLocaleString() : 'Not retained';
  const initialViewClass = value => {
    const view = String(value || '').trim().toLowerCase();
    if (view === 'pass') return 'good';
    if (view === 'watch') return 'mid';
    if (view === 'fail' || view === 'investigate') return 'bad';
    return 'neutral';
  };
  const causeStatusClass = row => row.cause_verified === true && String(row.cause_status).toUpperCase() === 'VERIFIED' ? 'verified' : 'unverified';
  const items = value => Array.isArray(value) ? value : [];
  const human = value => String(value || '').replaceAll('_', ' ');

  function sourceLink(claim) {
    const label = `${claim.source || 'Source'} · ${claim.headline || 'Evidence'} · ${when(claim.published_at)}`;
    try {
      const url = new URL(claim.url);
      if (url.protocol === 'https:' || url.protocol === 'http:') return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
    } catch (_) {}
    return esc(label);
  }

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
    const failed = items(row.failed_gates);
    const integrity = row.evidence_integrity || {};
    const issues = [...items(integrity.issues), ...items(integrity.fundamentals?.reasons), ...items(row.missing_inputs), ...items(row.risk_flags)];
    const uniqueIssues = [...new Set(issues.map(human))];
    const probability = row.calibrated_probability == null ? 'Profit probability: unavailable' : `Calibrated target probability: ${fmt(Number(row.calibrated_probability) * 100)}% · ${row.target_definition || 'target not retained'}`;
    return `<div>${esc(probability)}</div>
      <details class="evidence"><summary>Scores, risks and evidence</summary>
        <p>Uncalibrated indices /100: setup ${fmt(row.setup_score, 0)} · overreaction ${fmt(row.dislocation_score, 0)} · financial strength ${fmt(row.fundamental_survivability, 0)} · event reversibility ${fmt(row.catalyst_reversibility, 0)} · confirmation ${fmt(row.confirmation_score, 0)} · damage ${fmt(row.impairment_risk, 0)} · evidence confidence ${fmt(row.confidence, 0)}. These are not probabilities.</p>
        <p>Model: ${esc(row.scoring_model_version || 'Not retained')} · config: ${esc(row.scoring_config_version || 'Not retained')}</p>
        <p>Original signal: ${esc(when(row.signal_timestamp))} · price $${fmt(row.signal_price, 2)}<br>Evidence cutoff: ${esc(when(row.evidence_cutoff))}<br>Price timestamp: ${esc(when(row.latest_trade_ts))}</p>
        <p>${failed.length ? `Unmet model criteria: ${esc(failed.map(human).join('; '))}` : 'No unmet model criteria reported; this does not establish profitability.'}</p>
        ${row.hard_veto ? `<p class="bad">Veto reason: ${esc(row.hard_veto_reason || 'Not retained')}</p>` : ''}
        <p>Evidence checks: ${esc(integrity.version || 'Not retained for this original model run')}${integrity.retained_article_count != null ? ` · ${esc(integrity.retained_article_count)} usable articles` : ''}${items(integrity.excluded_articles).length ? ` · ${items(integrity.excluded_articles).length} excluded` : ''}</p>
        ${uniqueIssues.length ? `<ul>${uniqueIssues.map(issue => `<li>${esc(issue)}</li>`).join('')}</ul>` : ''}
        ${items(row.source_claims).length ? `<ul>${items(row.source_claims).map(claim => `<li>${sourceLink(claim)}</li>`).join('')}</ul>` : '<p>No retained source claims.</p>'}
      </details>`;
  }

  function executionCell(row) {
    return `<div>Round-trip friction: ${row.execution_friction_pct == null ? 'unavailable' : `${fmt(row.execution_friction_pct, 2)}% estimated`}</div>
      <div class="micro">Spread ${row.spread_pct == null ? 'unavailable' : `${fmt(row.spread_pct, 2)}%`} · prior volume ${row.prev_dollar_volume == null ? 'unavailable' : `$${fmt(Number(row.prev_dollar_volume) / 1000000, 1)}m`}</div>
      <div class="micro mid">Net reward/risk: unestablished</div>
      <details class="evidence"><summary>What is missing?</summary><ul>${items(row.opportunity_gaps).map(gap => `<li>${esc(gap)}</li>`).join('')}</ul></details>`;
  }

  function moveCell(row) {
    const session = String(row.price_session || 'unknown').replaceAll('_', ' ');
    const latest = row.latest_move_pct == null ? NaN : Number(row.latest_move_pct);
    const day = row.drop_pct == null ? NaN : Number(row.drop_pct);
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
    modelVersion.textContent = scan?.scoring_model_version || 'Version not retained';
    chatBtn.disabled = !(scan?.status === 'completed' && candidates.length);

    if (!scan) {
      rows.innerHTML = '<tr><td colspan="9" class="empty">No completed or active scan exists. Run the first scan.</td></tr>';
      setNotice('No scan has been run yet.');
      return;
    }
    if (scan.status === 'running') {
      rows.innerHTML = '<tr><td colspan="9" class="empty">Point-in-time scan running…</td></tr>';
      setNotice('Scanning the broad US loser universe, verifying causal evidence and applying robust downside analysis. Full enrichment can take several minutes.');
      schedulePoll();
      return;
    }
    if (scan.status === 'failed') {
      rows.innerHTML = '<tr><td colspan="9" class="empty">The latest scan failed. The previous completed scan remains in history.</td></tr>';
      setNotice(scan.error || 'Scan failed.', true);
      return;
    }

    const exclusions = Number(scan.excluded_non_operating_count || 0);
    const calibration = String(scan.model_status || '').toLowerCase() === 'calibrated' ? '' : ' The score is uncalibrated and must not be read as a probability.';
    setNotice(`Saved scan completed ${when(scan.completed_at)}. ${candidates.length} researchable candidates${exclusions ? `; ${exclusions} shell/non-operating instrument${exclusions === 1 ? '' : 's'} removed` : ''}.${calibration} Prices and evidence are from the original scan; run a fresh scan for a new decision.`);
    rows.innerHTML = candidates.length ? candidates.map(row => `
      <tr>
        <td>${esc(row.rank)}</td>
        <td><div class="ticker">${esc(row.symbol)}</div><div class="muted">${esc(row.name || '')}</div></td>
        <td>${moveCell(row)}</td>
        <td><span class="score">${row.model_missing ? '—' : fmt(row.oversold_score)}</span><div class="muted micro">priority /100<br>not a probability</div></td>
        <td><span class="pill neutral">${esc(row.fundamental_quality)}</span><div class="muted micro">Financial-strength index<br>${esc(row.fundamental_metadata?.form || 'Filing unavailable')}${row.fundamental_metadata?.age_calendar_days != null ? ` · ${esc(row.fundamental_metadata.age_calendar_days)}d old at signal` : ''}</div></td>
        <td class="details"><strong>${esc(row.catalyst_class)}</strong><span class="cause-status ${causeStatusClass(row)}">${esc(human(row.cause_status))}</span><div class="muted">${esc(row.catalyst_summary)}</div></td>
        <td><span class="pill ${initialViewClass(row.initial_view)}">${esc(row.initial_view)}</span>${row.hard_veto ? '<div class="bad micro">hard veto</div>' : ''}</td>
        <td class="details muted">${executionCell(row)}</td>
        <td class="details muted">${explanation(row)}</td>
      </tr>`).join('') : '<tr><td colspan="9" class="empty">No researchable qualifying losers in this scan.</td></tr>';
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
