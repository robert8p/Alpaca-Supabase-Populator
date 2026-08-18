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
    .or-track-table { width:100%; min-width:1420px; border-collapse:collapse; }
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
  `;
  document.head.appendChild(style);

  const cards = document.querySelector('section.cards');
  const notice = document.querySelector('.notice');
  const toolbar = document.querySelector('.toolbar');
  const scannerTable = document.querySelector('.table-wrap');
  if (!toolbar || !scannerTable) return;

  const tabs = document.createElement('div');
  tabs.className = 'or-tabs';
  tabs.innerHTML = `
    <button class="or-tab active" data-or-tab="scanner">Scanner</button>
    <button class="or-tab" data-or-tab="investigate">Investigate <span class="or-tab-count" id="or-investigate-count">0</span></button>
    <button class="or-tab" data-or-tab="pass">Pass <span class="or-tab-count" id="or-pass-count">0</span></button>
  `;
  toolbar.parentNode.insertBefore(tabs, toolbar);

  const panel = document.createElement('section');
  panel.className = 'or-track-panel';
  panel.innerHTML = `
    <div class="or-track-note" id="or-track-note"></div>
    <div class="or-track-wrap">
      <table class="or-track-table">
        <thead><tr>
          <th>Company</th><th>Decision baseline</th><th>Selected</th>
          <th>Day 1 · +1h</th><th>Day 1 · midpoint</th><th>Day 1 · close</th>
          <th>Day 2 · +1h</th><th>Day 2 · midpoint</th><th>Day 2 · close</th>
          <th>Commentary</th>
        </tr></thead>
        <tbody id="or-track-rows"></tbody>
      </table>
      <div class="or-empty" id="or-track-empty" hidden>No tracked stocks in this tab.</div>
    </div>
  `;
  scannerTable.parentNode.insertBefore(panel, scannerTable.nextSibling);

  let activeTab = 'scanner';
  let tracked = { investigate: [], pass: [] };
  let loading = false;

  const money = (value) => value == null ? '—' : Number(value).toLocaleString(undefined, { style:'currency', currency:'USD', maximumFractionDigits:2 });
  const dt = (value) => value ? new Date(value).toLocaleString() : '—';
  const shortDt = (value) => value ? new Date(value).toLocaleString(undefined, { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '—';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));

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

  function renderTracked() {
    document.getElementById('or-investigate-count').textContent = tracked.investigate?.length || 0;
    document.getElementById('or-pass-count').textContent = tracked.pass?.length || 0;
    if (activeTab === 'scanner') return;

    const rows = tracked[activeTab] || [];
    const body = document.getElementById('or-track-rows');
    const empty = document.getElementById('or-track-empty');
    const note = document.getElementById('or-track-note');
    note.innerHTML = activeTab === 'investigate'
      ? '<strong>Investigate outcomes.</strong> Results are measured from the live SIP price captured when Investigate was selected.'
      : '<strong>Pass outcomes.</strong> This is the counterfactual set: what happened after the stock was passed?';

    body.innerHTML = rows.map(track => {
      const cp = checkpointMap(track);
      return `<tr>
        <td><div class="or-track-symbol">${esc(track.symbol)}</div><div class="or-track-name">${esc(track.name || '')}</div></td>
        <td><div class="or-baseline">${money(track.selected_price)}</div><div class="or-track-meta">SIP decision-time price</div></td>
        <td>${dt(track.selected_at)}<div class="or-track-meta">Day 1: ${esc(track.session1_date)} · Day 2: ${esc(track.session2_date)}</div></td>
        ${checkpointCell(cp['1:open_plus_1h'])}
        ${checkpointCell(cp['1:mid_session'])}
        ${checkpointCell(cp['1:close'])}
        ${checkpointCell(cp['2:open_plus_1h'])}
        ${checkpointCell(cp['2:mid_session'])}
        ${checkpointCell(cp['2:close'])}
        <td>${track.review_notes ? esc(track.review_notes) : '<span class="or-pending">—</span>'}</td>
      </tr>`;
    }).join('');
    empty.hidden = rows.length > 0;
  }

  async function loadTracked() {
    if (loading) return;
    loading = true;
    try {
      const res = await fetch('/api/oversold/tracked', { cache:'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      tracked = await res.json();
      renderTracked();
    } catch (error) {
      if (activeTab !== 'scanner') {
        document.getElementById('or-track-note').textContent = `Outcome tracking failed to load: ${error.message}`;
      }
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
    if (!scanner) loadTracked();
  }

  tabs.addEventListener('click', event => {
    const button = event.target.closest('[data-or-tab]');
    if (button) activate(button.dataset.orTab);
  });

  document.addEventListener('click', event => {
    if (event.target.closest('.decision-button')) setTimeout(loadTracked, 1800);
  }, true);

  loadTracked();
  setInterval(loadTracked, 60000);
})();
