"use strict";
const $ = (id) => document.getElementById(id);
let jobs = [], selectedId = null, refreshing = false, pendingSubmission = null;
let lastBackfillRead = null, refreshFailed = false;
const activeStates = new Set(["queued", "pending", "running", "fetching", "downloading", "loading", "retry_wait", "verifying"]);
const badStates = new Set(["blocked", "failed", "held"]);
const finishedStates = new Set(["completed", "verified", "cancelled", "failed", "blocked", "SUPERSEDED_BY_SCOPE_CHANGE"]);

const replacementFamilies = ["REF01","REF03","P01","P02","D01","D02","D03","D04","D05","N01","N02","N03","S01","S02","CTX02","CTX06"];
const familyTitles = {REF01:"Identity and reference",REF03:"Lineage and quality audit",P01:"Regular-session minute bars",P02:"Extended-session minute bars",D01:"Intraday features",D02:"Daily price and volume",D03:"Daily returns",D04:"Daily volatility and volume",D05:"Daily illiquidity",N01:"News",N02:"Corporate actions",N03:"Splits",S01:"Short-sale volume",S02:"Short interest",CTX02:"Options",CTX06:"Fixed-cohort breadth"};
const terminalBackfillStates = new Set(["INGESTED","NO_DATA_RETURNED","NOT_APPLICABLE","PROVIDER_LIMITATION","IDENTITY_OR_QUALITY_UNRESOLVED"]);

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function pretty(value) { return String(value || "pending").replaceAll("_", " "); }
function number(value) { return Number(value || 0).toLocaleString(); }
function knownCount(value) { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null; }
function observedCount(value) { const count = knownCount(value); return count === null ? "Unknown" : number(count); }
function timestamp(value) {
  if (!value) return "—";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("en-GB", {timeZone: "UTC", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit"}) + " UTC";
}
function badge(state) {
  const value = String(state || "pending");
  const category = ["passed", "verified"].includes(value) ? "good" : badStates.has(value) ? "bad" : value === "paused" || value === "retry_wait" ? "warning" : activeStates.has(value) ? "active" : "";
  return element("span", pretty(value), "badge " + category);
}
function notice(message, success = false) {
  $("notice").textContent = message;
  $("notice").className = "notice" + (success ? " success" : "");
  $("notice").hidden = !message;
}
async function api(path, options = {}) {
  const response = await fetch(path, {credentials: "same-origin", cache: "no-store", ...options});
  let body;
  try { body = await response.json(); } catch (_) { throw new Error("The service returned an unreadable response."); }
  if (!response.ok) throw new Error(body.error || "The service is temporarily unavailable.");
  return body;
}
function facts(items) {
  $("detail-facts").replaceChildren(...items.map(([label, value]) => {
    const row = element("div"); row.append(element("dt", label), element("dd", value)); return row;
  }));
}
function renderJobs() {
  $("metric-total").textContent = number(jobs.length);
  $("metric-active").textContent = number(jobs.filter(j => activeStates.has(j.status)).length);
  $("metric-verified").textContent = number(jobs.filter(j => ["passed", "verified"].includes(j.verification_status)).length);
  $("metric-attention").textContent = number(jobs.filter(j => badStates.has(j.status) || badStates.has(j.verification_status)).length);
  const rows = jobs.map(job => {
    const row = element("tr"); if (job.id === selectedId) row.classList.add("selected");
    const title = element("td"), button = element("button", job.name || job.spec?.name || "Ingestion job", "job-link");
    button.type = "button"; button.addEventListener("click", () => selectJob(job.id));
    title.append(button, element("span", (job.spec?.symbols || []).join(", ") || job.id, "subline"));
    const execution = element("td"), verification = element("td");
    execution.append(badge(job.status)); verification.append(badge(job.verification_status));
    row.append(title, execution, verification, element("td", number(job.record_count)), element("td", timestamp(job.last_progress_at)));
    return row;
  });
  if (!rows.length) { const row = element("tr"), cell = element("td", "No original qualification jobs are recorded.", "empty"); cell.colSpan = 5; row.append(cell); rows.push(row); }
  $("jobs-body").replaceChildren(...rows);
}
function renderDetail(job) {
  $("detail").hidden = false;
  $("detail-title").textContent = job.name || job.spec?.name || "Ingestion job";
  $("detail-subtitle").textContent = [job.id, job.spec?.timeframe, "SIP / raw"].filter(Boolean).join(" · ");
  $("detail-error").textContent = job.error || ""; $("detail-error").hidden = !job.error;
  facts([["Execution", pretty(job.status)], ["Verification", pretty(job.verification_status)], ["Stored records", number(job.record_count)], ["Source requests", number(job.request_count)], ["Start", timestamp(job.spec?.start)], ["End, exclusive", timestamp(job.spec?.end)], ["Last durable progress", timestamp(job.last_progress_at)], ["Created", timestamp(job.created_at)]]);
  $("scope-hash").textContent = job.scope_hash || "—";
  document.querySelectorAll("[data-control]").forEach(button => {
    const action = button.dataset.control;
    button.disabled = action === "resume" ? job.status !== "paused" : action === "pause" ? finishedStates.has(job.status) || job.status === "paused" : finishedStates.has(job.status);
  });
  const partitions = (job.partitions || []).map(part => {
    const row = element("tr"), name = element("td", part.symbol || "—");
    name.append(element("span", `${timestamp(part.start_at || part.start || part.window_start)} → ${timestamp(part.end_at || part.end || part.window_end)}`, "subline"));
    const execution = element("td"), verification = element("td"), retry = element("td"); execution.append(badge(part.status)); verification.append(badge(part.verification_status));
    retry.append(element("span", part.error || (part.next_attempt_at ? "Next attempt: " + timestamp(part.next_attempt_at) : "—")), element("span", "Retries: " + number(part.retry_count), "subline"));
    row.append(name, execution, verification, element("td", `${number(part.page_count)} / ${number(part.record_count)}`), retry); return row;
  });
  if (!partitions.length) { const row = element("tr"), cell = element("td", "No partition details are available.", "empty"); cell.colSpan = 5; row.append(cell); partitions.push(row); }
  $("partitions-body").replaceChildren(...partitions);
  $("events").replaceChildren(...(job.events || []).map(event => {
    const row = element("li"); row.append(element("time", timestamp(event.timestamp || event.created_at)), element("span", pretty(event.event || event.kind), "event-name"), element("span", typeof event.detail === "object" ? JSON.stringify(event.detail) : event.detail || "", "event-detail")); return row;
  }));
}
function renderBackfill(snapshot) {
  if (!snapshot || !Array.isArray(snapshot.runs)) throw new Error("The replacement status report is incomplete.");
  const run = snapshot.runs.find(row => row.status === "ACTIVE") || snapshot.runs[0];
  const delivery = run ? (snapshot.delivery?.runs || []).find(row => row.run_id === run.id) : null;
  const metadata = run?.metadata || {};
  const sealed = delivery?.planning_complete ?? metadata.planning_complete;
  lastBackfillRead = snapshot.observed_at || Date.now() / 1000;
  $("backfill-error").hidden = true;
  $("backfill-state").textContent = run ? pretty(delivery?.run_status || run.status || "UNKNOWN") : "No recorded run";
  $("backfill-run").textContent = run ? `Run ${run.id || "unknown"} · Status read ${timestamp(lastBackfillRead)}` : `No replacement run was returned at ${timestamp(lastBackfillRead)}.`;
  $("backfill-progress").textContent = run ? `${observedCount(run.members)} fixed members · ${observedCount(run.pages_committed)} physical pages committed · ${observedCount(run.records_committed)} committed source, derived and audit records · ${observedCount(run.requests_reserved)} provider reservations` : "Work and coverage are unknown until an existing run is reported.";
  $("backfill-useful-progress").textContent = run?.last_progress_at ? timestamp(run.last_progress_at) : run && "last_progress_at" in run ? "No useful progress recorded" : "Unknown";
  $("backfill-plan-state").textContent = sealed === true ? "Full plan sealed" : sealed === false ? "Still planning" : "Unknown";
  $("backfill-coverage-state").textContent = metadata.applicable_data_coverage_established === true ? "Coverage evidence reported" : "Not established";
  $("backfill-readbacks").textContent = observedCount(delivery?.required_readbacks_remaining);
  const nextMember = knownCount(metadata.planner_next_selection_order);
  const planner = [];
  if (nextMember !== null && nextMember >= 1) planner.push(`${number(nextMember - 1)} / ${observedCount(run?.members)} fixed members admitted to the plan`);
  if (metadata.planner_phase) planner.push(`Phase: ${pretty(metadata.planner_phase)}`);
  if (metadata.planner_last_progress_at) planner.push(`Planner last advanced ${timestamp(metadata.planner_last_progress_at)}`);
  planner.push(sealed === true ? "The static plan is sealed; source pagination and discovered child work can add units." : "The full work denominator is unknown until the plan is sealed; current family totals can grow.");
  if (run?.next_retry_at) planner.push(`Next persisted retry: ${timestamp(run.next_retry_at)}.`);
  $("backfill-planner").textContent = planner.join(" · ");
  const dependencies = run?.provider_dependencies || delivery?.provider_dependencies || [];
  $("backfill-dependencies").replaceChildren(...["Alpaca","Massive"].map(provider => {
    const dependency = dependencies.find(row => row.provider === provider);
    let message = "configuration unknown; no provider readiness report";
    let className = "provider-unknown";
    if (dependency?.state === "AVAILABLE") { message = "worker credential available; data access and coverage remain separately assessed"; className = "provider-ready"; }
    if (dependency?.state === "BLOCKED_EXTERNAL") {
      message = dependency.code === "MISSING_PROVIDER_CREDENTIAL" || dependency.dependency?.endsWith("_WORKER_CREDENTIAL") ? "worker credential unavailable; this provider's work is blocked" : "external dependency blocks this provider's work";
      className = "provider-blocked";
    }
    const row = element("li", `${provider}: ${message}.`, className);
    if (dependency?.observed_at) row.append(element("span", `Last reported ${timestamp(dependency.observed_at)}`, "subline"));
    return row;
  }));
  const familyRows = new Map((delivery?.families || []).map(row => [row.family, row]));
  const rows = replacementFamilies.map(family => {
    const f = familyRows.get(family);
    const tasks = (run?.tasks || []).filter(task => task.family === family);
    const countTasks = predicate => tasks.length && tasks.every(task => knownCount(task.tasks) !== null) ? tasks.filter(predicate).reduce((sum,task) => sum + task.tasks, 0) : null;
    const planned = f?.planned_units ?? countTasks(() => true);
    const terminal = f?.terminal_units ?? countTasks(task => terminalBackfillStates.has(task.status));
    const retry = f?.retry_wait_units ?? countTasks(task => task.status === "RETRY_WAIT");
    const technical = f ? (knownCount(f.operational_error_units) !== null && knownCount(f.blocked_units) !== null ? f.operational_error_units + f.blocked_units : null) : countTasks(task => ["OPERATIONAL_ERROR","BLOCKED_EXTERNAL"].includes(task.status));
    const pending = f?.pending_units ?? countTasks(task => task.status === "PENDING");
    const running = f?.running_units ?? countTasks(task => task.status === "RUNNING");
    const row = element("tr"), label = element("td", family), state = element("td", pretty(f?.work_completion || "FAMILY_REPORT_PENDING"));
    label.append(element("span", familyTitles[family], "subline"));
    const records = element("td", observedCount(f?.committed_records));
    if (knownCount(f?.referenced_existing_records) > 0) records.append(element("span", `${number(f.referenced_existing_records)} existing source references`, "subline"));
    if (knownCount(f?.support_records) > 0) records.append(element("span", `${number(f.support_records)} support-history records`, "subline"));
    const issues = element("td", `${observedCount(pending)} pending · ${observedCount(running)} running`);
    issues.append(element("span", `${observedCount(retry)} retry · ${observedCount(technical)} technical / blocked`, "subline"));
    if (knownCount(f?.no_data_units) > 0 || knownCount(f?.provider_limited_units) > 0 || knownCount(f?.unresolved_units) > 0) issues.append(element("span", `${observedCount(f.no_data_units)} no data · ${observedCount(f.provider_limited_units)} provider limits · ${observedCount(f.unresolved_units)} unresolved`, "subline"));
    row.append(label, state, element("td", `${observedCount(terminal)} / ${observedCount(planned)}`), records, element("td", `${observedCount(f?.verified_pages)} / ${observedCount(f?.archived_pages)}`), issues);
    return row;
  });
  $("backfill-body").replaceChildren(...rows);
  const unsupported = run?.unsupported_pending_kinds || [];
  $("backfill-limits").textContent = "Finished units include documented no-data, not-applicable, provider-limit and unresolved outcomes. Observed counts and retained-source references are not additive across families and do not certify coverage of every security and date. Planner movement is not useful data progress. Cohort selection is retrospective." + (unsupported.length ? " Worker capabilities not currently advertised: " + unsupported.join(", ") + "." : "");
}
function backfillUnavailable(error) {
  $("backfill-state").textContent = "Status unavailable";
  $("backfill-error").textContent = "Replacement status could not be refreshed. " + (lastBackfillRead ? `Displayed values are from ${timestamp(lastBackfillRead)} and may be stale. ` : "No current values are available. ") + error.message;
  $("backfill-error").hidden = false;
}
async function selectJob(id) {
  selectedId = id; renderJobs();
  try { renderDetail((await api("/api/jobs/" + encodeURIComponent(id))).job); } catch (error) { notice(error.message); }
}
async function refresh() {
  if (refreshing || document.hidden) return;
  refreshing = true;
  async function refreshJobs() {
    jobs = (await api("/api/jobs")).jobs || [];
    if (!selectedId && jobs.length) selectedId = jobs[0].id;
    renderJobs();
    if (selectedId) renderDetail((await api("/api/jobs/" + encodeURIComponent(selectedId))).job);
    $("last-refresh").textContent = "Updated " + timestamp(Date.now() / 1000);
  }
  try {
    const [backfill, history] = await Promise.allSettled([api("/api/backfill/status").then(renderBackfill), refreshJobs()]);
    if (backfill.status === "rejected") backfillUnavailable(backfill.reason);
    if (history.status === "rejected") notice("Original jobs could not be refreshed. " + history.reason.message);
    const failures = [backfill, history].filter(result => result.status === "rejected").length;
    $("connection-dot").className = failures === 0 ? "ready" : failures === 1 ? "warning" : "error";
    $("connection-label").textContent = failures === 0 ? "Connected" : failures === 1 ? "Partially updated" : "Connection interrupted";
    if (failures === 0 && refreshFailed) notice("");
    refreshFailed = failures > 0;
  } finally { refreshing = false; }
}
$("job-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("submit-job"); button.disabled = true;
  try {
    const spec = {name: $("job-name").value.trim(), symbols: $("symbols").value.split(/[\s,]+/).filter(Boolean).map(s => s.toUpperCase()), start: new Date($("start").value + "Z").toISOString(), end: new Date($("end").value + "Z").toISOString(), timeframe: $("timeframe").value, feed: "sip", adjustment: "raw"};
    const body = JSON.stringify({spec});
    if (!pendingSubmission || pendingSubmission.body !== body) pendingSubmission = {body, key: crypto.randomUUID()};
    const result = await api("/api/jobs", {method: "POST", headers: {"Content-Type": "application/json", "X-Ingestion-Control": "1", "Idempotency-Key": pendingSubmission.key}, body});
    selectedId = result.job.id; pendingSubmission = null;
    notice("Job recorded. Its progress and verification will appear below.", true); await refresh();
  } catch (error) { notice(error.message); } finally { button.disabled = false; }
});
document.querySelectorAll("[data-control]").forEach(button => button.addEventListener("click", async () => {
  if (!selectedId) return; button.disabled = true;
  try {
    await api(`/api/jobs/${encodeURIComponent(selectedId)}/${button.dataset.control}`, {method: "POST", headers: {"Content-Type": "application/json", "X-Ingestion-Control": "1"}, body: "{}"});
    notice("Job control recorded.", true); await refresh();
  } catch (error) { notice(error.message); await refresh(); }
}));
$("refresh").addEventListener("click", refresh);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
setInterval(refresh, 10000);
refresh();

