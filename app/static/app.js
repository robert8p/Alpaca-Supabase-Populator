const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const state = { dashboard: null, universeMode: 'all_active', activeView: 'overview' };

function fmtNum(value) {
  const n = Number(value || 0);
  return new Intl.NumberFormat('en-GB', { notation: n >= 1_000_000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(n);
}
function fmtBytes(value) {
  let n = Number(value || 0); const units = ['B','KB','MB','GB','TB']; let i=0;
  while (n >= 1024 && i < units.length-1) { n/=1024; i++; }
  return `${n.toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}
function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value); if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-GB', { dateStyle:'medium', timeStyle:'short' });
}
function escapeHtml(value='') {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function toast(message, error=false) {
  const el = $('#toast'); el.textContent = message; el.className = error ? 'show error' : 'show';
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.className = '', 3500);
}
async function api(path, options={}) {
  const response = await fetch(path, { headers: {'Content-Type':'application/json', ...(options.headers||{})}, ...options });
  const text = await response.text(); let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = {detail:text}; }
  if (!response.ok) throw new Error(data?.detail || data?.error || `HTTP ${response.status}`);
  return data;
}
function badge(status='unknown') { return `<span class="badge ${escapeHtml(status)}">${escapeHtml(status.replaceAll('_',' '))}</span>`; }

const viewMeta = {
  overview: ['Overview','High-throughput, resumable market-data ingestion.'],
  'new-load': ['New ingestion load','Choose exactly what Alpaca data is retained in Supabase.'],
  jobs: ['Jobs','Inspect progress, errors and resume state.'],
  inventory: ['Inventory','A lightweight ledger of data loaded into partitioned tables.'],
  system: ['System','Connection checks, worker heartbeat and deployment guidance.']
};
function setView(name) {
  state.activeView = name;
  $$('.view').forEach(v => v.classList.toggle('active', v.id === `view-${name}`));
  $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  $('#page-title').textContent = viewMeta[name][0]; $('#page-subtitle').textContent = viewMeta[name][1];
  window.scrollTo({top:0, behavior:'smooth'});
}
$$('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
$$('[data-jump]').forEach(b => b.addEventListener('click', () => setView(b.dataset.jump)));

function renderJobCard(job) {
  const pct = Number(job.progress_pct || 0);
  return `<div class="job-card">
    <div class="job-card-top"><h3>${escapeHtml(job.name)}</h3>${badge(job.status)}</div>
    <div class="job-card-meta"><span>${fmtNum(job.symbol_count)} symbols</span><span>${fmtNum(job.rows_loaded)} rows loaded</span><span>${fmtNum(job.api_requests)} requests</span></div>
    <div class="progress"><i style="width:${Math.min(100,pct)}%"></i></div>
    <div class="progress-row"><span>${fmtNum(job.completed_tasks)} / ${fmtNum(job.total_tasks)} tasks</span><button class="text-btn inspect-job" data-id="${job.id}">${pct}%</button></div>
  </div>`;
}
function jobActions(job) {
  const actions = ['inspect'];
  if (['running','planning'].includes(job.status)) actions.push('pause','cancel');
  if (job.status === 'paused') actions.push('resume','cancel');
  if (['queued','pause_requested'].includes(job.status)) actions.push('cancel');
  if (['failed','cancelled'].includes(job.status)) actions.push('retry','delete');
  if (job.status === 'completed') actions.push('delete');
  return actions.map(a => `<button data-action="${a}" data-id="${job.id}">${a}</button>`).join('');
}
function renderJobs(jobs=[]) {
  $('#recent-jobs').innerHTML = jobs.length ? jobs.slice(0,6).map(renderJobCard).join('') : '<div class="empty">No jobs yet.</div>';
  $('#jobs-table').innerHTML = jobs.length ? jobs.map(job => `<tr>
    <td><div class="table-job"><strong>${escapeHtml(job.name)}</strong><span>${escapeHtml(String(job.id).slice(0,8))} · ${fmtNum(job.symbol_count)} symbols</span></div></td>
    <td>${badge(job.status)}</td>
    <td><div class="progress"><i style="width:${Math.min(100,Number(job.progress_pct||0))}%"></i></div><small>${job.progress_pct || 0}% · ${fmtNum(job.completed_tasks)}/${fmtNum(job.total_tasks)}</small></td>
    <td>${fmtNum(job.rows_loaded)}<br><small>${fmtBytes(job.bytes_staged)} staged</small></td>
    <td>${fmtNum(job.api_requests)}</td><td>${fmtDate(job.created_at)}</td>
    <td><div class="row-actions">${jobActions(job)}</div></td>
  </tr>`).join('') : '<tr><td colspan="7" class="empty">No jobs yet.</td></tr>';
}
function renderInventory(items=[]) {
  $('#inventory-table').innerHTML = items.length ? items.map(i => `<tr><td><strong>${escapeHtml(i.timeframe)}</strong></td><td>${escapeHtml(i.feed)}</td><td>${escapeHtml(i.adjustment)}</td><td>${fmtNum(i.rows_loaded)}</td><td>${fmtDate(i.min_bar_ts)}</td><td>${fmtDate(i.max_bar_ts)}</td><td>${fmtNum(i.loads_completed)}</td><td>${fmtDate(i.last_loaded_at)}</td></tr>`).join('') : '<tr><td colspan="8" class="empty">No data has been loaded.</td></tr>';
}
function renderWorkers(workers=[]) {
  const newest = workers[0]; const dot = $('#worker-dot');
  if (!newest) { dot.className='status-dot bad'; $('#worker-label').textContent='No worker'; $('#worker-age').textContent='No heartbeat received'; }
  else {
    const age = Number(newest.heartbeat_age_seconds || 0); dot.className = `status-dot ${age < 30 ? 'ok' : age < 180 ? 'warn' : 'bad'}`;
    $('#worker-label').textContent = `Worker ${newest.status}`; $('#worker-age').textContent = `${age}s since heartbeat`;
  }
  $('#worker-list').innerHTML = workers.length ? workers.map(w => `<div class="worker-line"><div><strong>${escapeHtml(w.worker_id)}</strong><span>${escapeHtml(w.status)} · v${escapeHtml(w.version)}</span></div><span>${Number(w.heartbeat_age_seconds||0)}s ago · ${w.current_task_ids?.length || 0} task(s)</span></div>`).join('') : '<div class="empty">No worker has registered.</div>';
}
function renderDashboard(data) {
  state.dashboard = data;
  $('#metric-active').textContent = fmtNum(data.metrics.active_jobs);
  $('#metric-rows').textContent = fmtNum(data.metrics.total_rows_loaded);
  $('#metric-requests').textContent = fmtNum(data.metrics.total_api_requests);
  $('#metric-completed').textContent = fmtNum(data.metrics.completed_jobs);
  renderJobs(data.jobs); renderInventory(data.inventory); renderWorkers(data.workers);
}
async function refresh() {
  try { renderDashboard(await api('/api/dashboard')); }
  catch (e) { toast(`Dashboard refresh failed: ${e.message}`, true); }
}
$('#refresh-btn').addEventListener('click', refresh);

function selectedValues(selector) { return $$(selector).filter(x => x.checked).map(x => x.value); }
function splitSymbols(text) { return [...new Set(text.toUpperCase().split(/[\s,;]+/).map(s=>s.trim()).filter(Boolean))]; }
function timeValue(id) { return $(id).value || undefined; }
function buildConfig() {
  const timeframes = selectedValues('#timeframe-chips input');
  const symbols = splitSymbols($('#symbols').value);
  const limitRaw = $('#symbol-limit').value;
  return {
    name: $('#job-name').value.trim(), start_date: $('#start-date').value, end_date: $('#end-date').value,
    timeframes, feed: $('#feed').value, adjustment: $('#adjustment').value, asof: $('#asof').value || null,
    universe: {
      mode: state.universeMode, symbols,
      exchanges: selectedValues('#exchange-chips input'), tradable_only: $('#tradable-only').checked,
      fractionable_only: $('#fractionable-only').checked, marginable_only: $('#marginable-only').checked,
      shortable_only: $('#shortable-only').checked, easy_to_borrow_only: $('#etb-only').checked,
      overnight_tradable_only: $('#overnight-only').checked,
      include_regex: $('#include-regex').value || null, exclude_regex: $('#exclude-regex').value || null,
      symbol_limit: limitRaw ? Number(limitRaw) : null
    },
    session: { mode: $('#session-mode').value, custom_start: $('#custom-start').value, custom_end: $('#custom-end').value, weekdays_only: $('#weekdays-only').checked },
    performance: {
      symbol_batch_size: Number($('#batch-size').value), date_chunk_days: Number($('#chunk-days').value),
      page_limit: Number($('#page-limit').value), concurrency: Number($('#concurrency').value),
      target_rpm: Number($('#target-rpm').value), max_retries: Number($('#max-retries').value),
      retry_backoff_seconds: Number($('#backoff').value)
    },
    storage: {
      conflict_policy: $('#conflict-policy').value, keep_staging_files: $('#keep-staging').checked,
      generate_daily_features: $('#generate-features').checked, feature_session: $('#feature-session').value
    }
  };
}
function validateConfig(config) {
  if (!config.name || config.name.length < 3) throw new Error('Enter a job name of at least three characters.');
  if (!config.start_date || !config.end_date) throw new Error('Select both dates.');
  if (config.timeframes.length === 0) throw new Error('Select at least one candle interval.');
  if (config.universe.mode === 'explicit' && config.universe.symbols.length === 0) throw new Error('Enter at least one explicit symbol.');
  if (config.feed === 'boats' && config.session.mode === 'regular') throw new Error('BOATS is overnight data; choose All or Custom session.');
}
function setLoading(button, on, text) { button.disabled=on; if (on) { button.dataset.label=button.textContent; button.textContent=text; } else if (button.dataset.label) button.textContent=button.dataset.label; }
async function estimateLoad() {
  const button=$('#estimate-btn'), message=$('#form-message');
  try {
    const config=buildConfig(); validateConfig(config); setLoading(button,true,'Estimating…'); message.textContent='Resolving the current Alpaca asset universe…'; message.className='form-message';
    const result=await api('/api/estimate',{method:'POST',body:JSON.stringify({config})});
    $('#est-symbols').textContent=`${fmtNum(result.symbol_count)} symbols`; $('#est-tasks').textContent=fmtNum(result.task_count);
    $('#est-rows').textContent=fmtNum(result.estimated_rows); $('#est-storage').textContent=`${result.estimated_compressed_staging_gb} GB`;
    message.textContent=`Sample: ${result.sample_symbols.slice(0,10).join(', ') || 'none'} · ${result.note}`; message.className='form-message success';
  } catch(e) { message.textContent=e.message; message.className='form-message error'; }
  finally { setLoading(button,false); }
}
$('#estimate-btn').addEventListener('click', estimateLoad);
$('#load-form').addEventListener('submit', async e => {
  e.preventDefault(); const button=$('#create-btn'), message=$('#form-message');
  try {
    const config=buildConfig(); validateConfig(config); setLoading(button,true,'Queuing…');
    const result=await api('/api/jobs',{method:'POST',body:JSON.stringify({config})});
    message.textContent=`Job ${String(result.id).slice(0,8)} queued successfully.`; message.className='form-message success'; toast('Ingestion job queued.');
    await refresh(); setView('jobs');
  } catch(e) { message.textContent=e.message; message.className='form-message error'; }
  finally { setLoading(button,false); }
});

$$('.chip input').forEach(input => input.addEventListener('change', () => input.closest('.chip').classList.toggle('selected', input.checked)));
$('#add-minute').addEventListener('click', () => {
  const n=Number($('#custom-minute').value); if (!Number.isInteger(n)||n<1||n>59) return toast('Enter a whole number from 1 to 59.',true);
  const value=`${n}Min`; const existing=$(`#timeframe-chips input[value="${value}"]`);
  if (existing) { existing.checked=true; existing.closest('.chip').classList.add('selected'); }
  else {
    const label=document.createElement('label'); label.className='chip selected'; label.innerHTML=`<input type="checkbox" value="${value}" checked>${n} min`;
    label.querySelector('input').addEventListener('change',ev=>label.classList.toggle('selected',ev.target.checked)); $('#timeframe-chips').appendChild(label);
  }
  $('#custom-minute').value='';
});
$$('[data-universe]').forEach(button=>button.addEventListener('click',()=>{
  state.universeMode=button.dataset.universe; $$('[data-universe]').forEach(b=>b.classList.toggle('active',b===button));
  $('#universe-filtered').hidden=state.universeMode!=='all_active'; $('#universe-explicit').hidden=state.universeMode!=='explicit';
}));
$('#session-mode').addEventListener('change',e=>$('#custom-session').hidden=e.target.value!=='custom');
$('#backoff').addEventListener('input',e=>$('#backoff-output').textContent=`${e.target.value}s`);
$('#symbol-file').addEventListener('change', async e => { const file=e.target.files[0]; if (file) $('#symbols').value=await file.text(); });

function selectTimeframes(values) {
  $$('#timeframe-chips input').forEach(i=>{ i.checked=values.includes(i.value); i.closest('.chip').classList.toggle('selected',i.checked); });
}
function setUniverse(mode) { const button=$(`[data-universe="${mode}"]`); if(button) button.click(); }
function isoDate(d){ return d.toISOString().slice(0,10); }
function applyPreset(name) {
  const end=new Date(); end.setDate(end.getDate()-1); let start=new Date(end);
  if(name==='breadth') { start.setFullYear(start.getFullYear()-1); selectTimeframes(['5Min']); setUniverse('all_active'); $('#symbol-limit').value=''; $('#batch-size').value=20; $('#chunk-days').value=10; $('#concurrency').value=8; $('#job-name').value='Rapid breadth — 5 minute'; }
  if(name==='precision') { start.setDate(start.getDate()-89); selectTimeframes(['1Min']); setUniverse('explicit'); $('#symbols').value='AAPL, MSFT, NVDA, TSLA, META, AMZN, GOOGL, AMD'; $('#batch-size').value=8; $('#chunk-days').value=3; $('#concurrency').value=6; $('#job-name').value='Event precision — 1 minute'; }
  if(name==='baseline') { start.setFullYear(start.getFullYear()-5); selectTimeframes(['1Day']); setUniverse('all_active'); $('#symbol-limit').value=''; $('#batch-size').value=50; $('#chunk-days').value=90; $('#concurrency').value=8; $('#job-name').value='Daily baseline — 5 years'; }
  $('#start-date').value=isoDate(start); $('#end-date').value=isoDate(end); toast('Preset applied. Review the estimate before queuing.');
}
$$('[data-preset]').forEach(b=>b.addEventListener('click',()=>applyPreset(b.dataset.preset)));

async function handleJobAction(action,id) {
  if(action==='inspect') return openJob(id);
  if(action==='delete' && !confirm('Delete this job record and its tasks/events? Loaded bars remain in Supabase.')) return;
  try { await api(`/api/jobs/${id}/actions/${action}`,{method:'POST'}); toast(`Job action requested: ${action}`); await refresh(); }
  catch(e){ toast(e.message,true); }
}
document.addEventListener('click',e=>{
  const inspect=e.target.closest('.inspect-job'); if(inspect) return openJob(inspect.dataset.id);
  const action=e.target.closest('[data-action][data-id]'); if(action) handleJobAction(action.dataset.action,action.dataset.id);
});
async function openJob(id) {
  const dialog=$('#job-dialog'); $('#job-detail').innerHTML='Loading…'; dialog.showModal();
  try {
    const data=await api(`/api/jobs/${id}`), j=data.job; $('#dialog-title').textContent=j.name; $('#dialog-subtitle').textContent=`${j.id} · ${j.status}`;
    const summaries=data.task_summary.map(s=>`<span class="badge ${s.status}">${s.status}: ${fmtNum(s.tasks)}</span>`).join(' ');
    const events=data.events.map(ev=>`<div class="event ${ev.level}"><strong>${escapeHtml(ev.message)}</strong><span>${escapeHtml(ev.event_type)} · ${fmtDate(ev.created_at)}</span></div>`).join('') || '<div class="empty">No events.</div>';
    $('#job-detail').innerHTML=`
      <div class="detail-grid"><div><span>Status</span><strong>${j.status}</strong></div><div><span>Progress</span><strong>${fmtNum(j.completed_tasks)} / ${fmtNum(j.total_tasks)}</strong></div><div><span>Rows loaded</span><strong>${fmtNum(j.rows_loaded)}</strong></div><div><span>API requests</span><strong>${fmtNum(j.api_requests)}</strong></div></div>
      <p>${summaries}</p>${j.error?`<div class="callout warning"><strong>Error</strong><span>${escapeHtml(j.error)}</span></div>`:''}
      <h3>Configuration</h3><pre class="config">${escapeHtml(JSON.stringify(j.config,null,2))}</pre>
      <h3>Latest events</h3><div class="event-list">${events}</div>`;
  } catch(e) { $('#job-detail').innerHTML=`<div class="empty">${escapeHtml(e.message)}</div>`; }
}
$('#dialog-close').addEventListener('click',()=>$('#job-dialog').close());

$('#test-deps').addEventListener('click', async e => {
  setLoading(e.target,true,'Testing…'); $('#dependency-results').textContent='Running direct checks…';
  try { const d=await api('/api/dependencies'); $('#dependency-results').innerHTML=`<div class="health-line"><strong>Supabase Postgres</strong><span>${d.database.ok?'Connected':'Failed: '+escapeHtml(d.database.error||'')}</span></div><div class="health-line"><strong>Alpaca APIs</strong><span>${d.alpaca.ok?`${fmtNum(d.alpaca.asset_count)} active assets returned`:'Failed: '+escapeHtml(d.alpaca.error||'')}</span></div>${d.auth_warning?'<div class="callout warning"><strong>Security</strong><span>APP_PASSWORD still uses the default placeholder.</span></div>':''}`; }
  catch(err){ $('#dependency-results').innerHTML=`<div class="empty">${escapeHtml(err.message)}</div>`; }
  finally { setLoading(e.target,false); }
});

(function initDates(){ const end=new Date(); end.setDate(end.getDate()-1); const start=new Date(end); start.setFullYear(start.getFullYear()-1); $('#start-date').value=isoDate(start); $('#end-date').value=isoDate(end); })();
refresh(); setInterval(()=>{ if(!document.hidden) refresh(); },5000);
