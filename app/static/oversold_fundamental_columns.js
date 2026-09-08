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
    const technical = candidate?.technical_inputs?.fundamentals;
    const trace = candidate?.catalyst_analysis?.fundamental_trace?.raw_metrics;
    return technical && typeof technical === 'object' ? technical : trace && typeof trace === 'object' ? trace : {};
  }

  function visibleCandidates() {
    if (typeof state === 'undefined' || !Array.isArray(state.candidates)) return [];
    const q = document.getElementById('search')?.value.trim().toLowerCase() || '';
    const triage = document.getElementById('triage')?.value || '';
    return state.candidates.filter(candidate => {
      const hay = `${candidate.symbol} ${candidate.name ?? ''}`.toLowerCase();
      return (!q || hay.includes(q)) && (!triage || candidate.triage_label === triage);
    });
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

  function ensureHeaders() {
    const header = document.querySelector('.table-wrap table thead tr');
    if (!header || header.querySelector('th[data-research-metric]')) return;
    const cells = [...header.cells];
    const score = cells.find(cell => /^(score|reversion)/i.test(cell.textContent.trim()));
    if (!score) return;
    let anchor = score;
    for (const [label, key, title] of columns) {
      const th = document.createElement('th');
      th.dataset.researchMetric = key;
      th.textContent = label;
      th.title = title;
      anchor.insertAdjacentElement('afterend', th);
      anchor = th;
    }
    const table = header.closest('table');
    if (table) table.style.minWidth = '2240px';
  }

  function enhanceRows() {
    ensureHeaders();
    const tbody = document.getElementById('rows');
    if (!tbody) return;
    const candidates = visibleCandidates();
    [...tbody.querySelectorAll(':scope > tr')].forEach((tr, index) => {
      const candidate = candidates[index];
      if (!candidate || tr.querySelector('td[data-research-metric]') || !tr.cells[6]) return;
      const metrics = metricsFor(candidate);
      let anchor = tr.cells[6];
      for (const [, key] of columns) {
        const td = document.createElement('td');
        td.dataset.researchMetric = key;
        td.className = 'research-metric-cell';
        td.innerHTML = `<strong>${esc(displayValue(key, metrics))}</strong>`;
        td.title = cellTitle(key, metrics);
        anchor.insertAdjacentElement('afterend', td);
        anchor = td;
      }
    });
  }

  const style = document.createElement('style');
  style.textContent = '.research-metric-cell{white-space:nowrap;min-width:84px}.research-metric-cell strong{font-variant-numeric:tabular-nums}th[data-research-metric]{min-width:84px}';
  document.head.appendChild(style);

  enhanceRows();
  const tbody = document.getElementById('rows');
  if (tbody) new MutationObserver(() => queueMicrotask(enhanceRows)).observe(tbody, {childList:true, subtree:false});
  document.getElementById('search')?.addEventListener('input', () => setTimeout(enhanceRows, 0));
  document.getElementById('triage')?.addEventListener('change', () => setTimeout(enhanceRows, 0));
})();
