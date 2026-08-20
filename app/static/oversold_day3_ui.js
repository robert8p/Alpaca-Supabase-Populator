(() => {
  const STYLE_ID = 'or-day3-fundamentals-style';
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .or-note,.or-early { display:none !important; }
      .or-current-table { min-width:2180px !important; }
      .or-current-table td:nth-child(5) .or-meta,
      .or-current-table td:nth-child(6) .or-meta { display:none !important; }
      .or-fundamentals { min-width:118px; }
      .or-fund-grade { display:inline-block; padding:2px 7px; border:1px solid var(--line); border-radius:999px; font-weight:900; font-size:11px; white-space:nowrap; }
      .or-fund-grade.a,.or-fund-grade.b { color:var(--good); border-color:#2b6b4a; }
      .or-fund-grade.c { color:var(--warn); border-color:#755d27; }
      .or-fund-grade.d,.or-fund-grade.e { color:var(--bad); border-color:#783838; }
      .or-fund-grade.na { color:var(--muted); }
    `;
    document.head.appendChild(style);
  }

  const escHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = value => value == null ? '—' : Number(value).toLocaleString(undefined, {style:'currency',currency:'USD',maximumFractionDigits:2});
  const shortDt = value => value ? new Date(value).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';

  function percent(value) {
    if (value == null || !Number.isFinite(Number(value))) return null;
    return `${(Number(value) * 100).toFixed(1)}%`;
  }

  function fundamentalsRating(candidate) {
    const analysis = candidate?.catalyst_analysis || {};
    const trace = analysis.fundamental_trace || {};
    const raw = trace.raw_metrics || {};
    const score = Number(candidate?.resilience_score);
    if (!trace.available || !Number.isFinite(score)) {
      return {grade:'N/A', label:'Unavailable', score:null, css:'na', title:'No cutoff-valid filing fundamentals available'};
    }
    let grade, label, css;
    if (score >= 75) [grade,label,css] = ['A','Strong','a'];
    else if (score >= 60) [grade,label,css] = ['B','Good','b'];
    else if (score >= 45) [grade,label,css] = ['C','Mixed','c'];
    else if (score >= 30) [grade,label,css] = ['D','Weak','d'];
    else [grade,label,css] = ['E','Fragile','e'];

    const details = [
      ['Revenue YoY', percent(raw.revenue_yoy)],
      ['Net margin', percent(raw.net_margin)],
      ['Cash/assets', percent(raw.cash_to_assets)],
      ['Liabilities/assets', percent(raw.liabilities_to_assets)],
      ['Equity/assets', percent(raw.equity_to_assets)],
      ['Diluted shares YoY', percent(raw.diluted_shares_yoy)],
    ].filter(([,value]) => value != null).map(([name,value]) => `${name}: ${value}`);
    return {grade,label,score,css,title:details.join(' · ') || 'Point-in-time filing fundamentals'};
  }

  function enhanceScannerFundamentals() {
    const table = document.querySelector('.table-wrap table');
    const header = table?.querySelector('thead tr');
    if (!table || !header) return;
    if (!header.querySelector('.or-fundamentals-head')) {
      const scoreHead = header.children[6];
      if (scoreHead) {
        const th = document.createElement('th');
        th.className = 'or-fundamentals-head';
        th.textContent = 'Fundamentals';
        scoreHead.insertAdjacentElement('afterend', th);
      }
    }

    document.querySelectorAll('#rows > tr').forEach(tr => {
      if (tr.querySelector('.or-fundamentals')) return;
      const symbol = tr.querySelector('.symbol')?.textContent?.trim();
      const candidate = typeof state !== 'undefined' && Array.isArray(state.candidates)
        ? state.candidates.find(item => String(item.symbol) === symbol)
        : null;
      if (!candidate || !tr.children[6]) return;
      const rating = fundamentalsRating(candidate);
      const td = document.createElement('td');
      td.className = 'or-fundamentals';
      td.title = rating.title;
      td.innerHTML = `<span class="or-fund-grade ${rating.css}">${escHtml(rating.grade)} · ${escHtml(rating.label)}</span>${rating.score == null ? '' : `<div class="muted" style="margin-top:4px">${rating.score.toFixed(0)}/100</div>`}`;
      tr.children[6].insertAdjacentElement('afterend', td);
    });
  }

  function checkpointMap(track) {
    const map = {};
    for (const cp of track?.checkpoints || []) map[`${cp.session_no}:${cp.checkpoint_kind}`] = cp;
    return map;
  }

  function checkpointCell(cp, tracked) {
    const td = document.createElement('td');
    td.className = 'or-check';
    if (!tracked) {
      td.classList.add('or-pending');
      td.textContent = 'Not tracked';
      return td;
    }
    if (!cp) {
      td.classList.add('or-pending');
      td.textContent = '—';
      return td;
    }
    if (cp.status === 'captured') {
      const value = Number(cp.return_pct || 0);
      const klass = value > 0.005 ? 'or-return-positive' : value < -0.005 ? 'or-return-negative' : 'or-return-flat';
      td.innerHTML = `<div class="or-check-price">${money(cp.price)}</div><div class="${klass}">${value > 0 ? '+' : ''}${value.toFixed(2)}%</div><div class="or-meta">${shortDt(cp.bar_ts)}</div>`;
      return td;
    }
    if (cp.status === 'missed' || cp.status === 'error') {
      td.classList.add('or-missed');
      td.innerHTML = `${escHtml(cp.status)}${cp.error ? `<div class="or-meta">${escHtml(cp.error)}</div>` : ''}`;
      return td;
    }
    td.classList.add('or-pending');
    td.innerHTML = `Pending<div class="or-meta">${shortDt(cp.scheduled_at)}</div>`;
    return td;
  }

  let boardCache = null;
  let historyCache = null;
  let dataInFlight = false;

  async function refreshDecisionData() {
    if (dataInFlight) return;
    dataInFlight = true;
    try {
      const [boardResponse, trackedResponse] = await Promise.all([
        fetch('/api/oversold/decision-board', {cache:'no-store'}),
        fetch('/api/oversold/tracked', {cache:'no-store'}),
      ]);
      if (boardResponse.ok) boardCache = await boardResponse.json();
      if (trackedResponse.ok) historyCache = await trackedResponse.json();
      enhanceDay3Current();
      enhanceDay3Scorecard();
    } catch (_) {
      // Existing tracking UI owns user-visible request errors.
    } finally {
      dataInFlight = false;
    }
  }

  function ensureDay3Headers() {
    const header = document.querySelector('.or-current-table thead tr');
    if (!header || header.querySelector('.or-day3-head')) return;
    const commentary = header.lastElementChild;
    for (const label of ['Day 3 · +1h','Day 3 · midpoint','Day 3 · close']) {
      const th = document.createElement('th');
      th.className = 'or-day3-head';
      th.textContent = label;
      header.insertBefore(th, commentary);
    }
  }

  function enhanceDay3Current() {
    ensureDay3Headers();
    if (!boardCache) return;
    const active = document.querySelector('.or-tab.active')?.dataset?.orTab;
    if (!['investigate','watch','pass','reject'].includes(active)) return;
    const rows = boardCache[active] || [];
    const bySymbol = new Map(rows.map(row => [String(row.symbol), row]));
    document.querySelectorAll('#or-current-rows > tr').forEach(tr => {
      if (tr.querySelector('.or-day3-cell')) return;
      const symbol = tr.querySelector('.or-symbol')?.textContent?.trim();
      const row = bySymbol.get(symbol);
      if (!row || !tr.lastElementChild) return;
      const track = row.tracking;
      const cp = checkpointMap(track);
      const tracked = Boolean(track && (active === 'investigate' || active === 'pass'));
      for (const key of ['3:open_plus_1h','3:mid_session','3:close']) {
        const td = checkpointCell(cp[key], tracked);
        td.classList.add('or-day3-cell');
        tr.insertBefore(td, tr.lastElementChild);
      }
    });
  }

  function median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a,b) => a-b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function statsFor(decision, key) {
    const values = [];
    for (const track of historyCache?.[decision] || []) {
      const cp = checkpointMap(track)[key];
      if (cp?.status === 'captured' && Number.isFinite(Number(cp.return_pct))) values.push(Number(cp.return_pct));
    }
    if (!values.length) return {n:0,median:null,mean:null,positive:null};
    return {
      n: values.length,
      median: median(values),
      mean: values.reduce((a,b) => a + b, 0) / values.length,
      positive: values.filter(value => value > 0).length / values.length * 100,
    };
  }

  const pct = value => value == null || !Number.isFinite(value) ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;

  function enhanceDay3Scorecard() {
    const body = document.getElementById('or-score-rows');
    if (!body || !historyCache || body.querySelector('.or-day3-score-row')) return;
    const definitions = [
      ['3:open_plus_1h','Day 3 · +1h'],
      ['3:mid_session','Day 3 · midpoint'],
      ['3:close','Day 3 · close'],
    ];
    for (const [key,label] of definitions) {
      const inv = statsFor('investigate', key);
      const pass = statsFor('pass', key);
      const separation = inv.median != null && pass.median != null ? inv.median - pass.median : null;
      const tr = document.createElement('tr');
      tr.className = 'or-day3-score-row';
      tr.innerHTML = `<td>${escHtml(label)}</td><td>${inv.n}</td><td>${pct(inv.median)}</td><td>${pct(inv.mean)}</td><td>${inv.positive == null ? '—' : inv.positive.toFixed(0)+'%'}</td><td>${pass.n}</td><td>${pct(pass.median)}</td><td>${pct(pass.mean)}</td><td>${pass.positive == null ? '—' : pass.positive.toFixed(0)+'%'}</td><td>${pct(separation)}</td>`;
      body.appendChild(tr);
    }
  }

  let scheduled = false;
  function enhanceAll() {
    scheduled = false;
    enhanceScannerFundamentals();
    ensureDay3Headers();
    enhanceDay3Current();
    enhanceDay3Scorecard();
  }
  function scheduleEnhance() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(enhanceAll, 0);
  }

  new MutationObserver(scheduleEnhance).observe(document.body, {childList:true, subtree:true});
  scheduleEnhance();
  refreshDecisionData();
  setInterval(refreshDecisionData, 30000);
})();
