(() => {
  'use strict';
  if (window.__oversoldFundamentalColumnsInstalled) return;
  window.__oversoldFundamentalColumnsInstalled = true;

  const columns = [
    ['PEG', 'peg_ratio', 'Forward PEG = scan-time forward P/E divided by positive expected EPS growth (%). Display-only; unavailable when forward consensus cannot be captured.'],
    ['Forward P/E', 'forward_pe', 'Scan-time forward P/E consensus. Display-only and persisted with new signals when available.'],
    ['FCF yield', 'fcf_yield_pct', 'Cutoff-valid TTM free cash flow divided by signal-time market capitalisation.'],
    ['ROIC', 'roic_pct', 'Estimated cutoff-valid TTM NOPAT divided by invested capital. Uses effective tax where available and a 21% normalized fallback.'],
    ['Balance sheet', 'balance_sheet_strength_score', 'Uncalibrated 0–100 balance-sheet strength index from cash/assets, equity/assets, liabilities/assets, current ratio and debt/assets.'],
    ['EPS growth', 'expected_eps_growth_pct', 'Expected EPS growth from scan-time forward EPS versus trailing-twelve-month EPS. Display-only; not historical EPS growth.'],
  ];

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const finite = value => value != null && Number.isFinite(Number(value));
  const fmt = (value, digits, suffix = '') => finite(value) ? `${Number(value).toFixed(digits)}${suffix}` : '—';

  function metricsFor(candidate) {
    const projected = candidate?.fundamentals;
    const technical = candidate?.technical_inputs?.fundamentals;
    const trace = candidate?.catalyst_analysis?.fundamental_trace?.raw_metrics;
    return projected && typeof projected === 'object'
      ? projected
      : technical && typeof technical === 'object'
      ? technical
      : trace && typeof trace === 'object'
      ? trace
      : {};
  }

  function displayValue(key, metrics) {
    if (key === 'peg_ratio') return fmt(metrics[key], 2);
    if (key === 'forward_pe') return fmt(metrics[key], 1, '×');
    if (key === 'balance_sheet_strength_score') return finite(metrics[key]) ? `${Number(metrics[key]).toFixed(0)}/100` : '—';
    return fmt(metrics[key], 1, '%');
  }

  function cellTitle(key, metrics) {
    if (key === 'peg_ratio' || key === 'forward_pe' || key === 'expected_eps_growth_pct') {
      const source = metrics.forward_estimate_source || 'forward consensus unavailable';
      const captured = metrics.forward_estimate_captured_at || 'capture time unavailable';
      return `${source} · ${captured}`;
    }
    if (key === 'fcf_yield_pct') return metrics.fcf_yield_method || 'TTM FCF yield basis unavailable';
    if (key === 'roic_pct') return metrics.roic_method || 'ROIC basis unavailable';
    if (key === 'balance_sheet_strength_score') return metrics.balance_sheet_strength_method || 'Balance-sheet basis unavailable';
    return '';
  }

  function insertHeaders(anchor, table) {
    let current = anchor;
    for (const [label, key, title] of columns) {
      const th = document.createElement('th');
      th.dataset.researchMetric = key;
      th.textContent = label;
      th.title = title;
      current.insertAdjacentElement('afterend', th);
      current = th;
    }
    if (table) table.style.minWidth = '2240px';
  }

  function insertCells(tr, anchor, candidate) {
    const metrics = metricsFor(candidate);
    let current = anchor;
    for (const [, key] of columns) {
      const td = document.createElement('td');
      td.dataset.researchMetric = key;
      td.className = 'research-metric-cell';
      td.innerHTML = `<strong>${esc(displayValue(key, metrics))}</strong>`;
      td.title = cellTitle(key, metrics);
      current.insertAdjacentElement('afterend', td);
      current = td;
    }
  }

  function visibleMainCandidates() {
    if (typeof state === 'undefined' || !Array.isArray(state.candidates)) return [];
    const q = document.getElementById('search')?.value.trim().toLowerCase() || '';
    const triage = document.getElementById('triage')?.value || '';
    return state.candidates.filter(candidate => {
      const hay = `${candidate.symbol} ${candidate.name ?? ''}`.toLowerCase();
      return (!q || hay.includes(q)) && (!triage || candidate.triage_label === triage);
    });
  }

  function ensureMainHeaders() {
    const header = document.querySelector('.table-wrap table thead tr');
    if (!header || header.querySelector('th[data-research-metric]')) return;
    const score = [...header.cells].find(cell => /^(score|reversion)/i.test(cell.textContent.trim()));
    if (score) insertHeaders(score, header.closest('table'));
  }

  function enhanceMainRows() {
    ensureMainHeaders();
    const tbody = document.getElementById('rows');
    if (!tbody) return;
    const candidates = visibleMainCandidates();
    [...tbody.querySelectorAll(':scope > tr')].forEach((tr, index) => {
      const candidate = candidates[index];
      if (!candidate || tr.querySelector('td[data-research-metric]') || !tr.cells[6]) return;
      insertCells(tr, tr.cells[6], candidate);
    });
  }

  let v2Busy = false;
  let v2Queued = false;

  function ensureV2Headers() {
    const header = document.querySelector('.table-wrap table thead tr');
    if (!header || header.querySelector('th[data-research-metric]')) return;
    const fundamental = [...header.cells].find(cell => /^fundamental evidence/i.test(cell.textContent.trim()));
    if (fundamental) insertHeaders(fundamental, header.closest('table'));
  }

  async function enhanceV2Rows() {
    if (v2Busy) {
      v2Queued = true;
      return;
    }
    v2Busy = true;
    try {
      ensureV2Headers();
      const response = await fetch('/api/oversold-v2/latest', {cache:'no-store'});
      if (!response.ok) return;
      const payload = await response.json();
      const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
      const tbody = document.getElementById('rows');
      if (!tbody) return;
      const trs = [...tbody.querySelectorAll(':scope > tr')];
      for (const tr of trs) {
        if (tr.cells.length === 1 && tr.cells[0]) tr.cells[0].colSpan = 15;
      }
      trs.forEach((tr, index) => {
        const candidate = candidates[index];
        if (!candidate || tr.querySelector('td[data-research-metric]') || !tr.cells[4]) return;
        insertCells(tr, tr.cells[4], candidate);
      });
    } catch (_) {
      // Metrics are optional research context; the core table must remain usable.
    } finally {
      v2Busy = false;
      if (v2Queued) {
        v2Queued = false;
        setTimeout(enhanceV2Rows, 50);
      }
    }
  }

  const style = document.createElement('style');
  style.textContent = '.research-metric-cell{white-space:nowrap;min-width:84px}.research-metric-cell strong{font-variant-numeric:tabular-nums}th[data-research-metric]{min-width:84px}';
  document.head.appendChild(style);

  const pathname = window.location.pathname;
  const tbody = document.getElementById('rows');
  if (pathname === '/oversold') {
    enhanceMainRows();
    if (tbody) new MutationObserver(() => queueMicrotask(enhanceMainRows)).observe(tbody, {childList:true, subtree:false});
    document.getElementById('search')?.addEventListener('input', () => setTimeout(enhanceMainRows, 0));
    document.getElementById('triage')?.addEventListener('change', () => setTimeout(enhanceMainRows, 0));
  } else if (pathname === '/oversold-v2') {
    enhanceV2Rows();
    if (tbody) new MutationObserver(() => setTimeout(enhanceV2Rows, 0)).observe(tbody, {childList:true, subtree:false});
  }
})();
