(() => {
  if (window.__orExecutionQuoteUiInstalled) return;
  window.__orExecutionQuoteUiInstalled = true;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'
  }[char]));
  const num = (value,digits=2) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);

  function candidateForRow(row) {
    const id=Number(row.dataset.candidateId || 0);
    if (id) {
      const candidate=window.state?.candidates?.find(item => Number(item.id)===id);
      if (candidate) return candidate;
    }
    const symbol=row.querySelector('.symbol')?.textContent?.trim();
    return window.state?.candidates?.find(item => String(item.symbol)===symbol) || null;
  }

  function enhanceRow(row) {
    const candidate=candidateForRow(row);
    const cell=row.querySelector('.or-model-score-cell');
    const friction=candidate?.catalyst_analysis?.reliability_assessment?.execution_friction;
    if (!candidate || !cell || !friction) return;
    const key=[friction.quote_state,friction.observed_quoted_spread_pct,friction.effective_spread_pct].join(':');
    if (cell.dataset.executionQuoteKey===key) return;
    cell.dataset.executionQuoteKey=key;
    const section=cell.querySelector('.or-v34-reliability-section');
    if (!section) return;
    let note=section.querySelector('.or-execution-quote-note');
    if (!note) {
      note=document.createElement('div');
      note.className='or-meta or-execution-quote-note';
      note.style.marginTop='6px';
      section.appendChild(note);
    }
    if (friction.quote_state==='off_hours_liquidity_proxy') {
      note.innerHTML=`Observed off-hours spread <strong>${esc(num(friction.observed_quoted_spread_pct))}%</strong>; ranking uses a conservative regular-session liquidity proxy of <strong>${esc(num(friction.effective_spread_pct))}%</strong>. A live spread/liquidity recheck is required before trading.`;
    } else {
      note.innerHTML=`Execution estimate uses the regular-session quoted spread of <strong>${esc(num(friction.effective_spread_pct))}%</strong>.`;
    }
  }

  function enhance(){ document.querySelectorAll('#rows > tr').forEach(enhanceRow); }
  let scheduled=false;
  function schedule(){ if(scheduled)return; scheduled=true; queueMicrotask(()=>{scheduled=false;enhance();}); }
  enhance();
  const rows=document.getElementById('rows');
  if(rows) new MutationObserver(schedule).observe(rows,{childList:true,subtree:true});
})();
