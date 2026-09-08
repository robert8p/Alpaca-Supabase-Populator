/* Shared, read-only calibration status for both reversion apps. */
(function (root) {
  'use strict';
  const ENDPOINT = '/api/oversold/calibration/status';
  const count = value => typeof value === 'number' && Number.isFinite(value) ? String(value) : 'Unavailable';
  const date = value => {
    if (!value) return 'Not yet known';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? 'Not yet known' : parsed.toLocaleString();
  };
  function viewModel(data) {
    if (!data || data.version !== 'calibration_pipeline_health_v1' || !data.counts || !data.readiness || !Array.isArray(data.reasons)) {
      throw new Error('Calibration service returned an unsupported status response');
    }
    const c = data.counts;
    const r = data.readiness;
    const q = r.requirements || {};
    const calibrated = data.model_status === 'calibrated';
    return {
      title: `Calibration: ${data.label || 'Status unavailable'}`,
      summary: `${count(c.scored_signals)} current-model original signals · ${count(c.independent_eligible_samples)} / ${count(q.minimum_matured_signals)} independent eligible outcomes`,
      probability: calibrated ? 'A passed target-touch mapping is active; it is not a net-profit probability.' : 'The research score remains uncalibrated. It is not a probability.',
      reasons: data.reasons,
      rows: [
        ['Completed three-session outcomes', `${count(c.matured_outcomes)} / ${count(c.scored_signals)}`],
        ['Independent eligible signal days', `${count(c.independent_eligible_days)} / ${count(q.minimum_independent_signal_days)}`],
        ['Positive outcomes', `${count(c.positive_count)} / ${count(q.minimum_positives)}`],
        ['Negative outcomes', `${count(c.negative_count)} / ${count(q.minimum_negatives)}`],
        ['Purged holdout observations', `${count(r.holdout_count)} / ${count(q.minimum_temporal_holdout)}`],
        ['Training observations after purge', `${count(r.training_count)} / ${count(q.minimum_training_after_purge)}`],
        ['Outcome / review errors', `${count(c.outcome_errors)} / ${count(c.review_errors)}`],
        ['Corporate-action reviews due', count(c.reviews_due)],
        ['Older-model original signals excluded', count(c.older_model_originals_excluded)],
        ['Historical rescore runs excluded', count(c.historical_rescore_runs_excluded)],
        ['Next target window end', date(data.next_target_window_end)],
        [`Next review milestone (retained ${count(data.corporate_action_review_lag_days)}-day policy)`, date(data.next_policy_review_at)],
        ['Last scheduled calibration check', data.last_scheduled_check ? `${date(data.last_scheduled_check.checked_at)} · ${data.last_scheduled_check.result?.status || 'unknown'}` : 'No scheduled check recorded yet'],
      ],
      version: `${data.scoring_model_version} / ${data.scoring_config_version}`,
      note: 'Review dates are processing milestones, not promised calibration activation dates. Only original, same-model scores and non-overlapping outcomes count. Statistical quality gates remain required.',
    };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {viewModel};
  if (!root.document) return;
  function boot() {
    const doc = root.document;
    if (doc.getElementById('or-calibration-panel')) return;
    const anchor = doc.querySelector('.notice');
    if (!anchor) return;
    const style = doc.createElement('style');
    style.textContent = '#or-calibration-panel{border:1px solid var(--line,#324257);border-radius:10px;padding:14px;margin:12px 0;background:var(--panel,#101923);color:var(--text,#e8edf3);font-size:13px;line-height:1.5}#or-calibration-panel header{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}#or-calibration-panel h3{margin:0;font-size:15px}#or-calibration-panel button{border:1px solid #506070;border-radius:7px;padding:7px 11px;background:#17202b;color:inherit;cursor:pointer}#or-calibration-panel button:disabled{opacity:.6;cursor:wait}#or-calibration-panel button:focus-visible,#or-calibration-panel summary:focus-visible{outline:2px solid #a5ceff;outline-offset:3px}#or-calibration-panel p{margin:7px 0}#or-calibration-panel dl{display:grid;grid-template-columns:minmax(140px,1fr) minmax(100px,1fr);gap:5px 14px;margin:12px 0}#or-calibration-panel dt,#or-calibration-panel dd{margin:0;overflow-wrap:anywhere}#or-calibration-panel dd{text-align:right}#or-calibration-panel summary{cursor:pointer}#or-calibration-panel .or-calibration-note{color:var(--muted,#aab8c8);overflow-wrap:anywhere}';
    doc.head.appendChild(style);
    const panel = doc.createElement('section');
    panel.id = 'or-calibration-panel';
    panel.setAttribute('aria-label', 'Calibration status');
    const header = doc.createElement('header');
    const title = doc.createElement('h3'); title.textContent = 'Calibration: checking readiness…';
    const button = doc.createElement('button'); button.type = 'button'; button.textContent = 'Refresh calibration status';
    header.append(title, button);
    const content = doc.createElement('div'); content.setAttribute('aria-live', 'polite');
    panel.append(header, content); anchor.insertAdjacentElement('afterend', panel);
    let busy = false;
    async function refresh() {
      if (busy) return;
      busy = true; button.disabled = true; panel.setAttribute('aria-busy', 'true');
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await root.fetch(ENDPOINT, {cache:'no-store', signal:controller.signal});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const view = viewModel(await response.json());
        title.textContent = view.title;
        content.replaceChildren();
        for (const text of [view.summary, view.probability, view.reasons[0]].filter(Boolean)) {
          const p = doc.createElement('p'); p.textContent = text; content.appendChild(p);
        }
        const details = doc.createElement('details');
        const summary = doc.createElement('summary'); summary.textContent = 'Evidence, blocking checks and next milestones'; details.appendChild(summary);
        const list = doc.createElement('dl');
        for (const [label, value] of view.rows) {
          const term = doc.createElement('dt'); const definition = doc.createElement('dd');
          term.textContent = label; definition.textContent = value; list.append(term, definition);
        }
        details.appendChild(list);
        for (const text of [...view.reasons.slice(1), view.version, view.note]) {
          const p = doc.createElement('p'); p.className = 'or-calibration-note'; p.textContent = text; details.appendChild(p);
        }
        content.appendChild(details);
      } catch (error) {
        title.textContent = 'Calibration: status unavailable';
        content.textContent = `Could not check calibration (${error.name === 'AbortError' ? 'request timed out' : error.message}). This is not evidence of calibration success or failure. Use Refresh to retry.`;
      } finally {
        clearTimeout(timeout); busy = false; button.disabled = false; panel.removeAttribute('aria-busy');
      }
    }
    button.addEventListener('click', refresh);
    refresh();
  }
  function loadResearchColumns() {
    if (root.location?.pathname !== '/oversold' || root.document.getElementById('or-research-columns-script')) return;
    const script = root.document.createElement('script');
    script.id = 'or-research-columns-script';
    script.src = '/static/oversold_fundamental_columns.js?v=1';
    script.defer = true;
    root.document.head.appendChild(script);
  }
  if (root.document.readyState === 'loading') {
    root.document.addEventListener('DOMContentLoaded', boot, {once:true});
    root.document.addEventListener('DOMContentLoaded', loadResearchColumns, {once:true});
  } else {
    boot();
    loadResearchColumns();
  }
})(typeof window === 'undefined' ? globalThis : window);
