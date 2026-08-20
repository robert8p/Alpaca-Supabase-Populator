(() => {
  if (window.__orPrimaryEvidenceUiInstalled) return;
  window.__orPrimaryEvidenceUiInstalled = true;

  const style = document.createElement('style');
  style.textContent = `
    .or-primary-badge { color:#d7f0ff; border-color:#477691; background:#142b38; }
    .or-primary-list { display:grid; gap:7px; }
    .or-primary-item { padding:8px 9px; border:1px solid var(--line); border-radius:7px; background:#0b1116; }
    .or-primary-item a { color:var(--accent); text-decoration:none; font-weight:800; }
    .or-primary-item a:hover { text-decoration:underline; }
    .or-primary-meta { margin-top:3px; color:var(--muted); font-size:10px; }
    .or-primary-empty { color:var(--muted); }
  `;
  document.head.appendChild(style);

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#039;'
  }[char]));

  function candidateForRow(row) {
    const id = Number(row.dataset.candidateId || 0);
    if (id) {
      const found = window.state?.candidates?.find(item => Number(item.id) === id);
      if (found) return found;
    }
    const symbol = row.querySelector('.symbol')?.textContent?.trim();
    return window.state?.candidates?.find(item => String(item.symbol) === symbol) || null;
  }

  function items(candidate) {
    const retained = candidate?.catalyst_analysis?.primary_event_evidence_items;
    if (Array.isArray(retained) && retained.length) return retained;
    const evidence = Array.isArray(candidate?.evidence_news)
      ? candidate.evidence_news
      : (Array.isArray(candidate?.headlines) ? candidate.headlines : []);
    return evidence.filter(item => item?.is_primary_evidence).map(item => {
      const record = item.primary_evidence || {};
      return {
        source_kind:item.source_kind || record.source_kind,
        source_authority:item.source_authority || record.source_authority,
        external_id:record.external_id || item.id,
        headline:item.headline,
        available_at:record.available_at || item.created_at,
        source_url:record.source_url || item.url,
        content_hash:record.content_hash,
        point_in_time_rule:record.metadata?.point_in_time_rule,
      };
    });
  }

  function itemHtml(item) {
    const href = esc(item.source_url || '#');
    const title = esc(item.headline || item.external_id || 'Primary evidence');
    return `<div class="or-primary-item">
      <a href="${href}" target="_blank" rel="noopener">${title}</a>
      <div class="or-primary-meta">${esc(item.source_authority || item.source_kind || 'Primary source')} · available ${esc(item.available_at || 'unknown')} · ID ${esc(item.external_id || 'unknown')}</div>
      ${item.point_in_time_rule ? `<div class="or-primary-meta">${esc(item.point_in_time_rule)}</div>` : ''}
    </div>`;
  }

  function enhanceRow(row) {
    const candidate = candidateForRow(row);
    const cell = row.querySelector('.or-model-score-cell');
    if (!candidate || !cell) return;
    const retained = items(candidate);
    const key = `${candidate.id}:${candidate.model_run_id || ''}:${retained.length}:${retained.map(item => item.content_hash || item.external_id || '').join('|')}`;
    if (cell.dataset.primaryEvidenceKey === key) return;
    cell.dataset.primaryEvidenceKey = key;

    const badges = cell.querySelector('.or-model-badges');
    if (badges) {
      badges.querySelectorAll('.or-primary-badge').forEach(element => element.remove());
      const badge = document.createElement('span');
      badge.className = 'or-mini-badge or-primary-badge';
      badge.textContent = retained.length ? `Primary evidence ${retained.length}` : 'No primary record';
      badge.title = retained.length
        ? 'Cutoff-valid SEC, trial-registry or FDA evidence retained in the immutable signal snapshot'
        : 'No cutoff-valid primary event record was retained';
      badges.appendChild(badge);
    }

    const body = cell.querySelector('.or-detail-body');
    if (!body) return;
    let section = body.querySelector('.or-primary-evidence-section');
    if (!section) {
      section = document.createElement('div');
      section.className = 'or-detail-section or-primary-evidence-section';
      const sourceSection = [...body.querySelectorAll('.or-detail-section')].find(element =>
        element.querySelector('b')?.textContent?.trim() === 'Source-quality hierarchy'
      );
      if (sourceSection) sourceSection.insertAdjacentElement('beforebegin', section);
      else body.appendChild(section);
    }
    section.innerHTML = `<b>Primary event evidence</b>${retained.length
      ? `<div class="or-primary-list">${retained.map(itemHtml).join('')}</div>`
      : '<span class="or-primary-empty">No cutoff-valid SEC event filing, exact trial registry record or exact FDA application record was retained.</span>'}`;
  }

  function enhance() {
    document.querySelectorAll('#rows > tr').forEach(enhanceRow);
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      enhance();
    });
  }

  enhance();
  const rows = document.getElementById('rows');
  if (rows) new MutationObserver(schedule).observe(rows, {childList:true, subtree:true});
})();
