(() => {
  const style = document.createElement('style');
  style.textContent = `
    .or-tabs { display:flex; gap:8px; margin:14px 0; flex-wrap:wrap; }
    .or-tab { padding:8px 13px; border:1px solid var(--line); background:#11171d; color:var(--muted); font-weight:800; }
    .or-tab.active { color:var(--text); border-color:#66788a; background:#202a34; box-shadow:0 0 0 1px #66788a inset; }
    .or-tab-count { display:inline-block; min-width:20px; margin-left:5px; padding:0 5px; border-radius:999px; background:#2b3540; color:var(--text); font-size:11px; text-align:center; }
    .or-track-panel { display:none; margin-top:4px; }
    .or-track-panel.active { display:block; }
    .or-track-note { margin:10px 0 14px; padding:10px 12px; border:1px solid var(--line); border-radius:9px; background:#10151a; color:var(--muted); }
    .or-track-wrap { overflow:auto; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
    .or-track-table { width:100%; min-width:1680px; border-collapse:collapse; }
    .or-track-table th,.or-track-table td { padding:10px 9px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }
    .or-track-table th { background:#171c22; color:#b9c3cc; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
    .or-track-table tr:last-child td { border-bottom:0; }
    .or-track-symbol { font-size:15px; font-weight:900; }
    .or-track-name,.or-track-meta { color:var(--muted); font-size:11px; }
    .or-baseline { font-weight:800; }
    .or-check { min-width:145px; }
    .or-check-price { font-weight:800; }
    .or-return-positive { color:var(--good); font-weight:900; }
    .or-return-negative { color:var(--bad); font-weight:900; }
    .or-return-flat { color:var(--muted); font-weight:900; }
    .or-pending { color:var(--muted); }
    .or-missed { color:var(--warn); }
    .or-empty { padding:36px; text-align:center; color:var(--muted); }
    .or-state { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 7px; font-size:11px; white-space:nowrap; }
    .or-state.current { color:var(--good); border-color:#2b6b4a; }
    .or-state.archived { color:var(--muted); }
    .or-state.complete { color:var(--accent); border-color:#3a5f82; }
    .or-context { min-width:220px; max-width:300px; }
    .or-score-view { display:none; }
    .or-score-view.active { display:block; }
    .or-track-view { display:none; }
    .or-track-view.active { display:block; }
    .or-score-cards { display:grid; grid-template-columns:repeat(5,minmax(150px,1fr)); gap:10px; margin:10px 0 14px; }
    .or-score-card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:13px 14px; min-height:82px; }
    .or-score-label { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
    .or-score-value { margin-top:5px; font-size:20px; font-weight:800; }
    .or-progress { height:7px; margin-top:9px; border-radius:999px; overflow:hidden; background:#252e37; }
    .or-progress > div { height:100%; background:currentColor; color:var(--accent); }
    .or-score-table { width:100%; min-width:1100px; border-collapse:collapse; }
    .or-score-table th,.or-score-table td { padding:9px; border-bottom:1px solid var(--line); text-align:right; }
    .or-score-table th:first-child,.or-score-table td:first-child { text-align:left; }
    .or-score-table th { background:#171c22; color:#b9c3cc; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
    .or-early { color:var(--warn); font-size:11px; margin-top:7px; }
    .or-history-select { min-width:280px; max-width:440px; }
    @media (max-width:900px) { .or-score-cards { grid-template-columns:repeat(2,minmax(140px,1fr)); } }
  `;
  document.head.appendChild(style);

  const cards = document.querySelector('section.cards');
  const notice = document.querySelector('.notice');
  const toolbar = document.querySelector('.toolbar');
  const scannerTable = document.querySelector('.table-wrap');
  const runButton = document.getElementById('run');
  if (!toolbar || !scannerTable) return;

  const scanSelect = document.createElement('select');
  scanSelect.id = 'or-scan-history';
  scanSelect.className = 'or-history-select';
  scanSelect.title = 'Open a previous scan without losing its recorded decisions';
  scanSelect.innerHTML = '<option value="">Latest scan</option>';

  const decisionFilter = document.createElement('select');
  decisionFilter.id = 'or-decision-filter';
  decisionFilter.title = 'Filter the current scan by review decision';
  decisionFilter.innerHTML = `
    <option value="">All decisions</option>
    <option value="unreviewed">Unreviewed only</option>
    <option value="investigate">Investigate</option>
    <option value="watch">Watch</option>
    <option value="pass">Pass</option>
    <option value="traded">Traded</option>
  `;
  toolbar.insertBefore(decisionFilter, toolbar.firstChild);
  toolbar.insertBefore(scanSelect, toolbar.firstChild);

  const originalRenderRows = renderRows;
  const originalLoad = load;
  let selectedScanId = '';

  renderRows = function enhancedRenderRows() {
    const allCandidates = state.candidates || [];
    const decision = decisionFilter.value;
    if (decision) state.candidates = allCandidates.filter(c => (c.decision || 'unreviewed') === decision);
    try {
      originalRenderRows();
    } finally {
      state.candidates = allCandidates;
    }
  };

  load = async function enhancedLoad() {
    if (!selectedScanId) return originalLoad();
    try {
      const res = await fetch(`/api/oversold/scans/${selectedScanId}`, { cache:'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state = await res.json();
      renderMeta();
      renderRows();
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      if (runButton) {
        runButton.disabled = false;
        runButton.textContent = 'Run scan now';
      }
      const status = document.getElementById('status-line');
      if (status && state.scan) status.textContent += ' · historical scan view';
    } catch (error) {
      document.getElementById('status-line').textContent = `Historical scan load failed: ${error.message}`;
    }
  };

  async function loadScanHistory() {
    try {
      const res = await fetch('/api/oversold/scans?limit=30', { cache:'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const scans = await res.json();
      const current = selectedScanId;
      scanSelect.innerHTML = '<option value="">Latest scan</option>' + scans.map(s => {
        const started = new Date(s.started_at).toLocaleString();
        const unreviewed = Number(s.unreviewed_count || 0);
        const label = `${started} · ${s.trigger_source} · ${s.candidate_count ?? 0} candidates · ${unreviewed} unreviewed`;
        return `<option value="${s.id}">${esc(label)}</option>`;
      }).join('');
      scanSelect.value = current;
    } catch (error) {
      console.warn('Scan history failed to load', error);
    }
  }

  scanSelect.addEventListener('change', () => {
    selectedScanId = scanSelect.value;
    load();
  });
  decisionFilter.addEventListener('change', renderRows);
  if (runButton) {
    runButton.addEventListener('click', () => {
      selectedScanId = '';
      scanSelect.value = '';
    }, true);
  }

  const tabs = document.createElement('div');
  tabs.className = 'or-tabs';
  tabs.innerHTML = `
    <button class="or-tab active" data-or-tab="scanner">Scanner</button>
    <button class="or-tab" data-or-tab="investigate">Investigate <span class="or-tab-count" id="or-investigate-count">0</span></button>
    <button class="or-tab" data-or-tab="pass">Pass <span class="or-tab-count" id="or-pass-count">0</span></button>
    <button class="or-tab" data-or-tab="scorecard">Scorecard</button>
  `;
  toolbar.parentNode.insertBefore(tabs, toolbar);

  const panel = document.createElement('section');
  panel.className = 'or-track-panel';
  panel.innerHTML = `
    <div class="or-track-view" id="or-track-view">
      <div class="or-track-note" id="or-track-note"></div>
      <div class="or-track-wrap">
        <table class="or-track-table">
          <thead><tr>
            <th>Company</th><th>Episode</th><th>Context at decision</th><th>Decision baseline</th><th>Selected</th>
            <th>Day 1 · +1h</th><th>Day 1 · midpoint</th><th>Day 1 · close</th>
            <th>Day 2 · +1h</th><th>Day 2 · midpoint</th><th>Day 2 · close</th>
            <th>Decision notes</th>
          </tr></thead>
          <tbody id="or-track-rows"></tbody>
        </table>
        <div class="or-empty" id="or-track-empty" hidden>No tracked decision episodes in this tab.</div>
      </div>
    </div>
    <div class="or-score-view" id="or-score-view">
      <div class="or-track-note">
        <strong>Decision scorecard.</strong> This compares the forward returns of Investigate versus Pass episodes. Treat small samples as descriptive only; the target is 25 completed, documented cases before recalibration.
      </div>
      <div class="or-score-cards" id="or-score-cards"></div>
      <div class="or-track-wrap">
        <table class="or-score-table">
          <thead><tr>
            <th>Checkpoint</th>
            <th>Inv. n</th><th>Inv. median</th><th>Inv. mean</th><th>Inv. positive</th>
            <th>Pass n</th><th>Pass median</th><th>Pass mean</th><th>Pass positive</th>
            <th>Median separation</th>
          </tr></thead>
          <tbody id="or-score-rows"></tbody>
        </table>
      </div>
      <div class="or-early" id="or-score-warning"></div>
    </div>
  `;
  scannerTable.parentNode.insertBefore(panel, scannerTable.nextSibling);

  let activeTab = 'scanner';
  let tracked = { investigate: [], pass: [] };
  let loading = false;

  const money = (value) => value == null ? '—' : Number(value).toLocaleString(undefined, { style:'currency', currency:'USD', maximumFractionDigits:2 });
  const dt = (value) => value ? new Date(value).toLocaleString() : '—';
  const shortDt = (value) => value ? new Date(value).toLocaleString(undefined, { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '—';

  function checkpointMap(track) {
    const map = {};
    for (const cp of track.checkpoints || []) map[`${cp.session_no}:${cp.checkpoint_kind}`] = cp;
    return map;
  }

  function checkpointCell(cp) {
    if (!cp) return '<td class="or-check or-pending">—</td>';
    if (cp.status === 'captured') {
      const r = Number(cp.return_pct || 0);
      const klass = r > 0.005 ? 'or-return-positive' : r < -0.005 ? 'or-return-negative' : 'or-return-flat';
      const sign = r > 0 ? '+' : '';
      return `<td class="or-check"><div class="or-check-price">${money(cp.price)}</div><div class="${klass}">${sign}${r.toFixed(2)}%</div><div class="or-track-meta">${shortDt(cp.bar_ts)}</div></td>`;
    }
    if (cp.status === 'missed' || cp.status === 'error') {
      return `<td class="or-check or-missed">${esc(cp.status)}<div class="or-track-meta">${esc(cp.error || '')}</div></td>`;
    }
    return `<td class="or-check or-pending">Pending<div class="or-track-meta">due ${shortDt(cp.scheduled_at)}</div></td>`;
  }

  function episodeState(track) {
    if (track.active && track.completed_at) return ['Current · complete', 'current complete'];
    if (track.active) return ['Current · measuring', 'current'];
    if (track.completed_at) return ['Archived · complete', 'archived complete'];
    return ['Archived · measuring', 'archived'];
  }

  function contextCell(track) {
    const c = track.context_snapshot || {};
    const flags = (c.risk_flags || []).map(flag => `<span class="pill">${esc(flag)}</span>`).join('');
    return `<td class="or-context">
      <div><span class="pill">${esc(c.catalyst_class || 'U')}</span> <strong>${c.heuristic_score == null ? '—' : esc(c.heuristic_score)}/100</strong></div>
      <div class="or-track-meta">${esc(c.triage_label || '')}</div>
      <div class="or-track-meta" style="margin-top:4px">${esc(c.catalyst_summary || '')}</div>
      <div class="flags">${flags}</div>
    </td>`;
  }

  function renderTracked() {
    document.getElementById('or-investigate-count').textContent = tracked.investigate?.length || 0;
    document.getElementById('or-pass-count').textContent = tracked.pass?.length || 0;
    if (activeTab !== 'investigate' && activeTab !== 'pass') return;

    const rows = tracked[activeTab] || [];
    const body = document.getElementById('or-track-rows');
    const empty = document.getElementById('or-track-empty');
    const note = document.getElementById('or-track-note');
    note.innerHTML = activeTab === 'investigate'
      ? '<strong>Investigate episodes.</strong> The decision-time context is frozen. If you later change the decision, the old episode remains here and continues collecting its scheduled outcomes.'
      : '<strong>Pass episodes.</strong> This is the counterfactual set. Historical pass episodes remain measurable even if you later revisit the stock.';

    body.innerHTML = rows.map(track => {
      const cp = checkpointMap(track);
      const [stateLabel, stateClass] = episodeState(track);
      return `<tr>
        <td><div class="or-track-symbol">${esc(track.symbol)}</div><div class="or-track-name">${esc(track.name || '')}</div></td>
        <td><span class="or-state ${stateClass}">${esc(stateLabel)}</span><div class="or-track-meta">episode #${esc(track.id)}</div></td>
        ${contextCell(track)}
        <td><div class="or-baseline">${money(track.selected_price)}</div><div class="or-track-meta">SIP decision-time price</div></td>
        <td>${dt(track.selected_at)}<div class="or-track-meta">Day 1: ${esc(track.session1_date)} · Day 2: ${esc(track.session2_date)}</div>${track.ended_at ? `<div class="or-track-meta">ended ${shortDt(track.ended_at)}</div>` : ''}</td>
        ${checkpointCell(cp['1:open_plus_1h'])}
        ${checkpointCell(cp['1:mid_session'])}
        ${checkpointCell(cp['1:close'])}
        ${checkpointCell(cp['2:open_plus_1h'])}
        ${checkpointCell(cp['2:mid_session'])}
        ${checkpointCell(cp['2:close'])}
        <td>${track.decision_notes ? esc(track.decision_notes) : '<span class="or-pending">—</span>'}</td>
      </tr>`;
    }).join('');
    empty.hidden = rows.length > 0;
  }

  function median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a,b) => a-b);
    const mid = Math.floor(sorted.length/2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid-1] + sorted[mid]) / 2;
  }

  function statsFor(decision, key) {
    const values = [];
    for (const track of tracked[decision] || []) {
      const cp = checkpointMap(track)[key];
      if (cp?.status === 'captured' && Number.isFinite(Number(cp.return_pct))) values.push(Number(cp.return_pct));
    }
    if (!values.length) return { n:0, median:null, mean:null, positive:null };
    const mean = values.reduce((a,b) => a+b,0) / values.length;
    const positive = values.filter(v => v > 0).length / values.length * 100;
    return { n:values.length, median:median(values), mean, positive };
  }

  function pct(value) {
    if (value == null || !Number.isFinite(value)) return '—';
    const sign = value > 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  }

  function renderScorecard() {
    const all = [...(tracked.investigate || []), ...(tracked.pass || [])];
    const completed = all.filter(t => t.completed_at).length;
    const current = all.filter(t => t.active).length;
    let pending = 0, captured = 0, missed = 0;
    for (const track of all) {
      for (const cp of track.checkpoints || []) {
        if (cp.status === 'pending') pending++;
        else if (cp.status === 'captured') captured++;
        else if (cp.status === 'missed' || cp.status === 'error') missed++;
      }
    }
    const progress = Math.min(100, (completed / 25) * 100);
    document.getElementById('or-score-cards').innerHTML = `
      <div class="or-score-card"><div class="or-score-label">Completed sample</div><div class="or-score-value">${completed} / 25</div><div class="or-progress"><div style="width:${progress}%"></div></div></div>
      <div class="or-score-card"><div class="or-score-label">Decision episodes</div><div class="or-score-value">${all.length}</div><div class="or-track-meta">${tracked.investigate.length} investigate · ${tracked.pass.length} pass</div></div>
      <div class="or-score-card"><div class="or-score-label">Current decisions</div><div class="or-score-value">${current}</div><div class="or-track-meta">append-only history retained</div></div>
      <div class="or-score-card"><div class="or-score-label">Captured checkpoints</div><div class="or-score-value">${captured}</div><div class="or-track-meta">${pending} pending</div></div>
      <div class="or-score-card"><div class="or-score-label">Capture misses</div><div class="or-score-value">${missed}</div><div class="or-track-meta">should normally remain zero</div></div>
    `;

    const checkpoints = [
      ['1:open_plus_1h', 'Day 1 · +1h'],
      ['1:mid_session', 'Day 1 · midpoint'],
      ['1:close', 'Day 1 · close'],
      ['2:open_plus_1h', 'Day 2 · +1h'],
      ['2:mid_session', 'Day 2 · midpoint'],
      ['2:close', 'Day 2 · close'],
    ];
    let smallestSide = Infinity;
    document.getElementById('or-score-rows').innerHTML = checkpoints.map(([key,label]) => {
      const inv = statsFor('investigate', key);
      const pass = statsFor('pass', key);
      if (inv.n || pass.n) smallestSide = Math.min(smallestSide, inv.n || Infinity, pass.n || Infinity);
      const separation = inv.median != null && pass.median != null ? inv.median - pass.median : null;
      return `<tr>
        <td>${esc(label)}</td>
        <td>${inv.n}</td><td>${pct(inv.median)}</td><td>${pct(inv.mean)}</td><td>${inv.positive == null ? '—' : inv.positive.toFixed(0)+'%'}</td>
        <td>${pass.n}</td><td>${pct(pass.median)}</td><td>${pct(pass.mean)}</td><td>${pass.positive == null ? '—' : pass.positive.toFixed(0)+'%'}</td>
        <td>${pct(separation)}</td>
      </tr>`;
    }).join('');
    const warning = document.getElementById('or-score-warning');
    if (!captured) {
      warning.textContent = 'No checkpoint outcomes have matured yet. The scorecard will populate automatically as the scheduled observations are captured.';
    } else if (smallestSide < 10) {
      warning.textContent = 'Early sample: do not recalibrate the scanner from these percentages yet. Separation becomes more informative as both decision groups accumulate observations.';
    } else {
      warning.textContent = '';
    }
  }

  async function loadTracked() {
    if (loading) return;
    loading = true;
    try {
      const res = await fetch('/api/oversold/tracked', { cache:'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      tracked = await res.json();
      renderTracked();
      renderScorecard();
    } catch (error) {
      if (activeTab !== 'scanner') document.getElementById('or-track-note').textContent = `Outcome tracking failed to load: ${error.message}`;
    } finally {
      loading = false;
    }
  }

  function activate(tab) {
    activeTab = tab;
    tabs.querySelectorAll('.or-tab').forEach(button => button.classList.toggle('active', button.dataset.orTab === tab));
    const scanner = tab === 'scanner';
    if (cards) cards.style.display = scanner ? '' : 'none';
    if (notice) notice.style.display = scanner ? '' : 'none';
    toolbar.style.display = scanner ? '' : 'none';
    scannerTable.style.display = scanner ? '' : 'none';
    panel.classList.toggle('active', !scanner);
    document.getElementById('or-track-view').classList.toggle('active', tab === 'investigate' || tab === 'pass');
    document.getElementById('or-score-view').classList.toggle('active', tab === 'scorecard');
    if (!scanner) loadTracked();
  }

  tabs.addEventListener('click', event => {
    const button = event.target.closest('[data-or-tab]');
    if (button) activate(button.dataset.orTab);
  });

  document.addEventListener('click', event => {
    if (event.target.closest('.decision-button')) {
      setTimeout(() => {
        loadTracked();
        loadScanHistory();
      }, 1800);
    }
  }, true);

  loadScanHistory();
  loadTracked();
  setInterval(() => {
    loadTracked();
    loadScanHistory();
  }, 60000);
})();
