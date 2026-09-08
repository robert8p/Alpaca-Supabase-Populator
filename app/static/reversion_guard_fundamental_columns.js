(() => {
  'use strict';
  if (window.__reversionGuardFundamentalColumnsInstalled) return;
  window.__reversionGuardFundamentalColumnsInstalled = true;

  const columns = [
    ['PEG', 'peg_ratio', 'Forward PEG = scan-time forward P/E divided by positive expected EPS growth (%). Display-only; unavailable when forward consensus was not captured with the original scan.'],
    ['Forward P/E', 'forward_pe', 'Scan-time forward P/E consensus retained with the original signal when available.'],
    ['FCF yield', 'fcf_yield_pct', 'Cutoff-valid TTM free cash flow divided by signal-time market capitalisation.'],
    ['ROIC', 'roic_pct', 'Estimated cutoff-valid TTM NOPAT divided by invested capital.'],
    ['Balance sheet', 'balance_sheet_strength_score', 'Uncalibrated 0–100 balance-sheet-strength index from cutoff-valid filing ratios.'],
    ['EPS growth', 'expected_eps_growth_pct', 'Expected EPS growth from scan-time forward EPS versus trailing-twelve-month EPS; not historical EPS growth.'],
  ];

  const finite = value => value != null && Number.isFinite(Number(value));
  const fmt = (value, digits, suffix = '') => finite(value) ? `${Number(value).toFixed(digits)}${suffix}` : '—';

  function displayValue(key, metrics) {
    if (key === 'peg_ratio') return fmt(metrics[key], 2);
    if (key === 'forward_pe') return fmt(metrics[key], 1, '×');
    if (key === 'balance_sheet_strength_score') return finite(metrics[key]) ? `${Number(metrics[key]).toFixed(0)}/100` : '—';
    return fmt(metrics[key], 1, '%');
  }

  function metricsFor(candidate) {
    const technical = candidate?.technical_inputs?.fundamentals;
    const projected = candidate?.fundamentals;
    const trace = candidate?.catalyst_analysis?.fundamental_trace?.raw_metrics;
    return technical && typeof technical === 'object'
      ? technical
      : projected && typeof projected === 'object'
      ? projected
      : trace && typeof trace === 'object'
      ? trace
      : {};
  }

  function tooltip(key, metrics) {
    if (key === 'peg_ratio' || key === 'forward_pe' || key === 'expected_eps_growth_pct') {
      return `${metrics.forward_estimate_source || 'forward consensus unavailable'} · ${metrics.forward_estimate_captured_at || 'capture time unavailable'}`;
    }
    if (key === 'fcf_yield_pct') return metrics.fcf_yield_method || 'TTM FCF yield basis unavailable';
    if (key === 'roic_pct') return metrics.roic_method || 'ROIC basis unavailable';
    if (key === 'balance_sheet_strength_score') return metrics.balance_sheet_strength_method || 'Balance-sheet basis unavailable';
    return '';
  }

  function ensureHeaders() {
    const header = document.querySelector('.candidate-table thead tr');
    if (!header || header.querySelector('th[data-research-metric]')) return;
    const guardScore = [...header.cells].find(cell => /^guard score$/i.test(cell.textContent.trim()));
    if (!guardScore) return;
    let anchor = guardScore;
    for (const [label, key, title] of columns) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.dataset.researchMetric = key;
      th.textContent = label;
      th.title = title;
      anchor.insertAdjacentElement('afterend', th);
      anchor = th;
    }
    header.closest('table')?.style.setProperty('min-width', '1780px');
  }

  function insertCells(row, candidate) {
    if (!row || row.querySelector('td[data-research-metric]') || !row.cells[3]) return;
    const metrics = metricsFor(candidate || {});
    let anchor = row.cells[3];
    for (const [label, key] of columns) {
      const td = document.createElement('td');
      td.dataset.label = label;
      td.dataset.researchMetric = key;
      td.className = 'research-metric-cell';
      const strong = document.createElement('strong');
      strong.textContent = displayValue(key, metrics);
      td.appendChild(strong);
      td.title = tooltip(key, metrics);
      anchor.insertAdjacentElement('afterend', td);
      anchor = td;
    }
  }

  let busy = false;
  let queued = false;

  async function refreshColumns() {
    if (busy) {
      queued = true;
      return;
    }
    busy = true;
    try {
      ensureHeaders();
      const response = await fetch('/api/reversion-guard/latest', {cache: 'no-store'});
      if (!response.ok) return;
      const payload = await response.json();
      const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
      const byId = new Map(candidates.map(candidate => [String(candidate.id), candidate]));
      document.querySelectorAll('#candidateRows > tr[data-candidate-id]').forEach(row => {
        const candidate = byId.get(String(row.dataset.candidateId));
        // Never borrow current metrics for an unmatched/historical signal.
        insertCells(row, candidate || {});
      });
    } catch (_) {
      // These are optional research columns; Guard's risk/entry workflow must remain usable.
    } finally {
      busy = false;
      if (queued) {
        queued = false;
        setTimeout(refreshColumns, 80);
      }
    }
  }

  const style = document.createElement('style');
  style.textContent = '.candidate-table .research-metric-cell{white-space:nowrap;min-width:88px}.candidate-table .research-metric-cell strong{font-variant-numeric:tabular-nums;font-size:13px}.candidate-table th[data-research-metric]{min-width:88px}';
  document.head.appendChild(style);

  ensureHeaders();
  refreshColumns();
  const tbody = document.getElementById('candidateRows');
  if (tbody) new MutationObserver(() => setTimeout(refreshColumns, 0)).observe(tbody, {childList:true, subtree:false});
})();
