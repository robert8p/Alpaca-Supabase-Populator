(() => {
  const style = document.createElement('style');
  style.textContent = `
    .or-tabs { display:flex; gap:8px; margin:14px 0; flex-wrap:wrap; }
    .or-tab { padding:8px 13px; border:1px solid var(--line); background:#11171d; color:var(--muted); font-weight:800; }
    .or-tab.active { color:var(--text); border-color:#66788a; background:#202a34; box-shadow:0 0 0 1px #66788a inset; }
    .or-tab.or-reject-tab { color:#aeb6bf; border-color:#59636e; }
    .or-tab.or-reject-tab.active { color:#fff; border-color:#8c97a3; background:#555f69; box-shadow:0 0 0 1px #8c97a3 inset; }
    .or-tab-count { display:inline-block; min-width:20px; margin-left:5px; padding:0 5px; border-radius:999px; background:#2b3540; color:var(--text); font-size:11px; text-align:center; }
    .or-tab.or-reject-tab .or-tab-count { background:#69737e; color:#fff; }
    .decision-button.selected-reject { color:#fff; border-color:#89939e; background:#5b6570; }
    .or-panel { display:none; margin-top:4px; }
    .or-panel.active { display:block; }
    .or-note { margin:10px 0 14px; padding:10px 12px; border:1px solid var(--line); border-radius:9px; background:#10151a; color:var(--muted); }
    .or-wrap { overflow:auto; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
    .or-current-table { width:100%; min-width:1760px; border-collapse:collapse; }
    .or-current-table th,.or-current-table td { padding:10px 9px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }
    .or-current-table th { background:#171c22; color:#b9c3cc; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
    .or-current-table tr:last-child td { border-bottom:0; }
    .or-symbol { font-size:15px; font-weight:900; }
    .or-name,.or-meta { color:var(--muted); font-size:11px; }
    .or-context { min-width:220px; max-width:300px; }
    .or-baseline { font-weight:800; }
    .or-check { min-width:140px; }
    .or-check-price { font-weight:800; }
    .or-return-positive { color:var(--good); font-weight:900; }
    .or-return-negative { color:var(--bad); font-weight:900; }
    .or-return-flat { color:var(--muted); font-weight:900; }
    .or-pending { color:var(--muted); }
    .or-missed { color:var(--warn); }
    .or-empty { padding:36px; text-align:center; color:var(--muted); }
    .or-decision-badge { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:3px 8px; font-size:11px; font-weight:900; white-space:nowrap; }
    .or-decision-badge.investigate { color:#fff; border-color:#dc5757; background:#7a2424; }
    .or-decision-badge.watch { color:#171109; border-color:#f4bd4f; background:#f4bd4f; }
    .or-decision-badge.pass { color:#07140c; border-color:#53d18b; background:#53d18b; }
    .or-decision-badge.reject { color:#fff; border-color:#89939e; background:#5b6570; }
    .or-current-view,.or-score-view { display:none; }
    .or-current-view.active,.or-score-view.active { display:block; }
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
  if (!toolbar || !scannerTable || typeof renderRows !== 'function' || typeof load !== 'function') return;

  const decisionLabel = decision => ({
    investigate:'Investigate', watch:'Watch', pass:'Pass', reject:'Reject', traded:'Traded', unreviewed:'Unreviewed'
  }[decision] || decision || '');

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
    <option value="reject">Reject</option>
    <option value="traded">Traded</option>
  `;
  toolbar.insertBefore(decisionFilter, toolbar.firstChild);
  toolbar.insertBefore(scanSelect, toolbar.firstChild);

  function enhanceRejectControls() {
    for (const candidate of state.candidates || []) {
      const textarea = document.getElementById(`commentary-${candidate.id}`);
      const row = textarea?.closest('tr');
      const group = row?.querySelector('.decision');
      if (!row || !group) continue;
      let reject = group.querySelector('[data-decision="reject"]');
      if (!reject) {
        reject = document.createElement('button');
        reject.className = 'decision-button';
        reject.dataset.decision = 'reject';
        reject.onclick = () => setDecision(candidate.id, 'reject');
        group.appendChild(reject);
      }
      const selected = candidate.decision === 'reject';
      reject.className = `decision-button ${selected ? 'selected-reject' : ''}`;
      reject.setAttribute('aria-pressed', String(selected));
      reject.textContent = `${selected ? '✓ ' : ''}Reject`;
      if (selected) {
        const label = row.querySelector('.decision-label');
        const help = row.querySelector('.decision-help');
        if (label) {
          label.classList.remove('unselected');
          label.textContent = 'Selected: Reject';
        }
        if (help) help.textContent = 'Saved choice — select another button to change it.';
      }
    }
  }

  const baseRenderRows = renderRows;
  renderRows = function exclusiveRenderRows() {
    const allCandidates = state.candidates || [];
    const decision = decisionFilter.value;
    if (decision) state.candidates = allCandidates.filter(c => (c.decision || 'unreviewed') === decision);
    try {
      baseRenderRows();
      enhanceRejectControls();
    } finally {
      state.candidates = allCandidates;
    }
  };

  const baseSetDecision = setDecision;
  setDecision = async function exclusiveSetDecision(id, decision) {
    if (decision !== 'reject') return baseSetDecision(id, decision);
    const candidate = state.candidates.find(item => Number(item.id) === Number(id));
    const previous = candidate?.decision;
    if (candidate) {
      candidate.decision = 'reject';
      renderRows();
      document.getElementById('status-line').textContent = `${candidate.symbol}: saving Reject decision…`;
    }
    try {
      const response = await fetch(`/api/oversold/candidates/${id}`, {
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({decision:'reject', review_notes:candidate?.review_notes || ''})
      });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try { detail = (await response.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }
      await load();
      if (candidate) document.getElementById('status-line').textContent = `${candidate.symbol}: decision saved as Reject.`;
    } catch (error) {
      if (candidate) {
        candidate.decision = previous;
        renderRows();
      }
      document.getElementById('status-line').textContent = `Decision save failed: ${error.message}`;
    }
  };

  const baseLoad = load;
  let selectedScanId = '';
  load = async function enhancedLoad() {
    if (!selectedScanId) return baseLoad();
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
      scanSelect.innerHTML = '<option value="">Latest scan</option>' + scans.map(scan => {
        const started = new Date(scan.started_at).toLocaleString();
        const label = `${started} · ${scan.trigger_source} · ${scan.candidate_count ?? 0} candidates · ${Number(scan.unreviewed_count || 0)} unreviewed`;
        return `<option value="${scan.id}">${esc(label)}</option>`;
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
    <button class="or-tab" data-or-tab="watch">Watch <span class="or-tab-count" id="or-watch-count">0</span></button>
    <button class="or-tab" data-or-tab="pass">Pass <span class="or-tab-count" id="or-pass-count">0</span></button>
    <button class="or-tab or-reject-tab" data-or-tab="reject">Reject <span class="or-tab-count" id="or-reject-count">0</span></button>
    <button class="or-tab" data-or-tab="scorecard">Scorecard</button>
  `;
  toolbar.parentNode.insertBefore(tabs, toolbar);

  const panel = document.createElement('section');
  panel.className = 'or-panel';
  panel.innerHTML = `
    <div class="or-current-view" id="or-current-view">
      <div class="or-note" id="or-current-note"></div>
      <div class="or-wrap">
        <table class="or-current-table">
          <thead><tr>
            <th>Company</th><th>Current decision</th><th>Context</th><th>Scanner move</th><th>Decision baseline / price</th><th>Reviewed</th>
            <th>Day 1 · +1h</th><th>Day 1 · midpoint</th><th>Day 1 · close</th>
            <th>Day 2 · +1h</th><th>Day 2 · midpoint</th><th>Day 2 · close</th><th>Commentary</th>
          </tr></thead>
          <tbody id="or-current-rows"></tbody>
        </table>
        <div class="or-empty" id="or-current-empty" hidden>No stocks currently in this tab.</div>
      </div>
    </div>
    <div class="or-score-view" id="or-score-view">
      <div class="or-note">
        <strong>Decision scorecard.</strong> Historical Investigate and Pass episodes remain here even after a stock changes tab. The visible decision tabs themselves show only the latest current state per symbol.
      </div>
      <div class="or-score-cards" id="or-score-cards"></div>
      <div class="or-wrap">
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
  let board = { investigate:[], watch:[], pass:[], reject:[] };
  let history = { investigate:[], pass:[] };
  let loading = false;

  const money = value => value == null ? '—' : Number(value).toLocaleString(undefined, { style:'currency', currency:'USD', maximumFractionDigits:2 });
  const dt = value => value ? new Date(value).toLocaleString() : '—';
  const shortDt = value => value ? new Date(value).toLocaleString(undefined, { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '—';

  function checkpointMap(track) {
    const map = {};
    for (const cp of track?.checkpoints || []) map[`${cp.session_no}:${cp.checkpoint_kind}`] = cp;
    return map;
  }

  function checkpointCell(cp, trackedDecision) {
    if (!trackedDecision) return '<td class="or-check or-pending">Not tracked</td>';
    if (!cp) return '<td class="or-check or-pending">—</td>';
    if (cp.status === 'captured') {
      const value = Number(cp.return_pct || 0);
      const klass = value > 0.005 ? 'or-return-positive' : value < -0.005 ? 'or-return-negative' : 'or-return-flat';
      const sign = value > 0 ? '+' : '';
      return `<td class="or-check"><div class="or-check-price">${money(cp.price)}</div><div class="${klass}">${sign}${value.toFixed(2)}%</div><div class="or-meta">${shortDt(cp.bar_ts)}</div></td>`;
    }
    if (cp.status === 'missed' || cp.status === 'error') {
      return `<td class="or-check or-missed">${esc(cp.status)}<div class="or-meta">${esc(cp.error || '')}</div></td>`;
    }
    return `<td class="or-check or-pending">Pending<div class="or-meta">due ${shortDt(cp.scheduled_at)}</div></td>`;
  }

  function contextCell(row) {
    const flags = (row.risk_flags || []).map(flag => `<span class="pill">${esc(flag)}</span>`).join('');
    return `<td class="or-context">
      <div><span class="pill">${esc(row.catalyst_class || 'U')}</span> <strong>${row.heuristic_score == null ? '—' : esc(row.heuristic_score)}/100</strong></div>
      <div class="or-meta">${esc(row.triage_label || '')}</div>
      <div class="or-meta" style="margin-top:4px">${esc(row.catalyst_summary || '')}</div>
      <div class="flags">${flags}</div>
    </td>`;
  }

  function renderCurrent() {
    for (const decision of ['investigate','watch','pass','reject']) {
      document.getElementById(`or-${decision}-count`).textContent = board[decision]?.length || 0;
    }
    if (!['investigate','watch','pass','reject'].includes(activeTab)) return;

    const rows = board[activeTab] || [];
    const body = document.getElementById('or-current-rows');
    const empty = document.getElementById('or-current-empty');
    const note = document.getElementById('or-current-note');
    const noteText = {
      investigate:'<strong>Investigate.</strong> Current stocks only. Outcome checkpoints are measured from the decision-time SIP baseline.',
      watch:'<strong>Watch.</strong> Current watchlist only. Watch stocks do not create new outcome checkpoints unless moved to Investigate or Pass.',
      pass:'<strong>Pass.</strong> Current pass decisions only. Historical Pass/Investigate episodes remain in the Scorecard after a stock changes state.',
      reject:'<strong>Reject.</strong> Current rejected stocks only. Reject is a terminal review bucket for the current state and is shown in grey.'
    };
    note.innerHTML = `${noteText[activeTab]} <strong>Each symbol can appear in only one current decision tab; the latest explicit decision wins.</strong>`;

    body.innerHTML = rows.map(row => {
      const track = row.tracking;
      const cp = checkpointMap(track);
      const trackedDecision = Boolean(track && (activeTab === 'investigate' || activeTab === 'pass'));
      const price = track?.selected_price ?? row.last_price;
      const priceLabel = track ? 'SIP decision-time baseline' : 'scanner snapshot price';
      return `<tr>
        <td><div class="or-symbol">${esc(row.symbol)}</div><div class="or-name">${esc(row.name || '')}</div><div class="or-meta">${esc(row.exchange || '')}</div></td>
        <td><span class="or-decision-badge ${esc(activeTab)}">${esc(decisionLabel(activeTab))}</span></td>
        ${contextCell(row)}
        <td><strong>${row.drop_pct == null ? '—' : Number(row.drop_pct).toFixed(1)+'%'}</strong><div class="or-meta">spread ${row.spread_pct == null ? '—' : Number(row.spread_pct).toFixed(2)+'%'}</div></td>
        <td><div class="or-baseline">${money(price)}</div><div class="or-meta">${priceLabel}</div></td>
        <td>${dt(row.reviewed_at)}<div class="or-meta">latest explicit decision for symbol</div></td>
        ${checkpointCell(cp['1:open_plus_1h'], trackedDecision)}
        ${checkpointCell(cp['1:mid_session'], trackedDecision)}
        ${checkpointCell(cp['1:close'], trackedDecision)}
        ${checkpointCell(cp['2:open_plus_1h'], trackedDecision)}
        ${checkpointCell(cp['2:mid_session'], trackedDecision)}
        ${checkpointCell(cp['2:close'], trackedDecision)}
        <td>${row.review_notes ? esc(row.review_notes) : '<span class="or-pending">—</span>'}</td>
      </tr>`;
    }).join('');
    empty.hidden = rows.length > 0;
  }

  function median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a,b) => a-b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid-1] + sorted[mid]) / 2;
  }

  function statsFor(decision, key) {
    const values = [];
    for (const track of history[decision] || []) {
      const cp = checkpointMap(track)[key];
      if (cp?.status === 'captured' && Number.isFinite(Number(cp.return_pct))) values.push(Number(cp.return_pct));
    }
    if (!values.length) return { n:0, median:null, mean:null, positive:null };
    const mean = values.reduce((a,b) => a+b, 0) / values.length;
    return { n:values.length, median:median(values), mean, positive:values.filter(v => v > 0).length / values.length * 100 };
  }

  function pct(value) {
    if (value == null || !Number.isFinite(value)) return '—';
    return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  }

  function renderScorecard() {
    const all = [...(history.investigate || []), ...(history.pass || [])];
    const completed = all.filter(track => track.completed_at).length;
    const current = (board.investigate?.length || 0) + (board.pass?.length || 0);
    let pending = 0, captured = 0, missed = 0;
    for (const track of all) {
      for (const cp of track.checkpoints || []) {
        if (cp.status === 'pending') pending++;
        else if (cp.status === 'captured') captured++;
        else if (cp.status === 'missed' || cp.status === 'error') missed++;
      }
    }
    const progress = Math.min(100, completed / 25 * 100);
    document.getElementById('or-score-cards').innerHTML = `
      <div class="or-score-card"><div class="or-score-label">Completed sample</div><div class="or-score-value">${completed} / 25</div><div class="or-progress"><div style="width:${progress}%"></div></div></div>
      <div class="or-score-card"><div class="or-score-label">Historical episodes</div><div class="or-score-value">${all.length}</div><div class="or-meta">${history.investigate.length} investigate · ${history.pass.length} pass</div></div>
      <div class="or-score-card"><div class="or-score-label">Current tracked stocks</div><div class="or-score-value">${current}</div><div class="or-meta">exclusive current state</div></div>
      <div class="or-score-card"><div class="or-score-label">Captured checkpoints</div><div class="or-score-value">${captured}</div><div class="or-meta">${pending} pending</div></div>
      <div class="or-score-card"><div class="or-score-label">Capture misses</div><div class="or-score-value">${missed}</div><div class="or-meta">should normally remain zero</div></div>
    `;

    const checkpoints = [
      ['1:open_plus_1h','Day 1 · +1h'],['1:mid_session','Day 1 · midpoint'],['1:close','Day 1 · close'],
      ['2:open_plus_1h','Day 2 · +1h'],['2:mid_session','Day 2 · midpoint'],['2:close','Day 2 · close']
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
    if (!captured) warning.textContent = 'No checkpoint outcomes have matured yet. The scorecard will populate automatically as scheduled observations are captured.';
    else if (smallestSide < 10) warning.textContent = 'Early sample: do not recalibrate from these percentages yet. Wait for a larger sample on both sides.';
    else warning.textContent = '';
  }

  async function loadDecisionData() {
    if (loading) return;
    loading = true;
    try {
      const trackedResponse = await fetch('/api/oversold/tracked', { cache:'no-store' });
      if (!trackedResponse.ok) throw new Error(`Tracked HTTP ${trackedResponse.status}`);
      history = await trackedResponse.json();

      const boardResponse = await fetch('/api/oversold/decision-board', { cache:'no-store' });
      if (!boardResponse.ok) throw new Error(`Board HTTP ${boardResponse.status}`);
      board = await boardResponse.json();
      renderCurrent();
      renderScorecard();
    } catch (error) {
      if (activeTab !== 'scanner') document.getElementById('or-current-note').textContent = `Decision tabs failed to load: ${error.message}`;
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
    document.getElementById('or-current-view').classList.toggle('active', ['investigate','watch','pass','reject'].includes(tab));
    document.getElementById('or-score-view').classList.toggle('active', tab === 'scorecard');
    if (!scanner) {
      renderCurrent();
      renderScorecard();
      loadDecisionData();
    }
  }

  tabs.addEventListener('click', event => {
    const button = event.target.closest('[data-or-tab]');
    if (button) activate(button.dataset.orTab);
  });

  document.addEventListener('click', event => {
    if (event.target.closest('.decision-button')) {
      setTimeout(() => {
        loadDecisionData();
        loadScanHistory();
      }, 1800);
    }
  }, true);

  loadScanHistory();
  loadDecisionData();
  setInterval(() => {
    loadDecisionData();
    loadScanHistory();
  }, 60000);
})();
