"use strict";
const $ = (id) => document.getElementById(id);
let jobs = [], selectedId = null, refreshing = false, pendingSubmission = null;
const activeStates = new Set(["queued", "pending", "running", "fetching", "downloading", "loading", "retry_wait", "verifying"]);
const badStates = new Set(["blocked", "failed", "held"]);
const finishedStates = new Set(["completed", "verified", "cancelled", "failed", "blocked"]);

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function pretty(value) { return String(value || "pending").replaceAll("_", " "); }
function number(value) { return Number(value || 0).toLocaleString(); }
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
  if (!rows.length) { const row = element("tr"), cell = element("td", "No jobs yet. Create a bounded workload above to begin.", "empty"); cell.colSpan = 5; row.append(cell); rows.push(row); }
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
async function selectJob(id) {
  selectedId = id; renderJobs();
  try { renderDetail((await api("/api/jobs/" + encodeURIComponent(id))).job); } catch (error) { notice(error.message); }
}
async function refresh() {
  if (refreshing || document.hidden) return;
  refreshing = true;
  try {
    jobs = (await api("/api/jobs")).jobs || [];
    if (!selectedId && jobs.length) selectedId = jobs[0].id;
    renderJobs();
    if (selectedId) renderDetail((await api("/api/jobs/" + encodeURIComponent(selectedId))).job);
    $("connection-dot").className = "ready"; $("connection-label").textContent = "Connected";
    $("last-refresh").textContent = "Updated " + timestamp(Date.now() / 1000);
  } catch (error) {
    $("connection-dot").className = "error"; $("connection-label").textContent = "Connection interrupted"; notice(error.message);
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
