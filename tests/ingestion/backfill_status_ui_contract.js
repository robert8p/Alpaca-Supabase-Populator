"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.hidden = false; this.className = ""; this.dataset = {}; this.classList = {add() {}}; this._text = ""; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(" "); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ""; this.children = children; }
  addEventListener() {}
}
const html = fs.readFileSync("astra_ingestion/static/index.html", "utf8");
const nodes = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], new Node("div")]));
const document = {hidden: true, getElementById(id) { assert(nodes.has(id), "Unknown DOM id: " + id); return nodes.get(id); },
  createElement: tag => new Node(tag), querySelectorAll: () => [], addEventListener() {}};
const context = vm.createContext({document, console, setInterval() {}, fetch() { throw new Error("Unexpected automatic request"); }});
vm.runInContext(fs.readFileSync("astra_ingestion/static/app.js", "utf8"), context);
const text = id => nodes.get(id).textContent;
const report = {observed_at:"2026-10-30T08:00:00Z", runs:[
  {id:"paused-old",status:"PAUSED"},
  {id:"current-existing-run",status:"ACTIVE",members:3000,pages_committed:24,records_committed:3492,requests_reserved:24,
   last_progress_at:"2026-10-30T07:59:00Z",metadata:{planning_complete:false,planner_next_selection_order:7,planner_phase:"MEMBERS"},
   provider_dependencies:[{provider:"Massive",state:"BLOCKED_EXTERNAL",code:"MISSING_PROVIDER_CREDENTIAL",dependency:"MASSIVE_WORKER_CREDENTIAL"}]}],
  delivery:{runs:[{run_id:"paused-old",families:[{family:"N01",committed_records:999999}]},
  {run_id:"current-existing-run",planning_complete:false,required_readbacks_remaining:0,families:[
   {family:"N01",work_completion:"IN_PROGRESS",planned_units:10,terminal_units:2,committed_records:25,
    archived_pages:2,verified_pages:2,pending_units:8,running_units:0,retry_wait_units:0,operational_error_units:0,blocked_units:0}]}]}};

async function run() {
  context.renderBackfill(report);
  assert.match(text("backfill-run"), /current-existing-run/);
  assert.equal(nodes.get("backfill-body").children.length, 16);
  const news = nodes.get("backfill-body").children[9];
  assert.equal(news.children[2].textContent, "2 / 10");
  assert.equal(news.children[3].textContent, "25");
  assert.doesNotMatch(text("backfill-body"), /999999/);
  assert.equal(text("backfill-coverage-state"), "Not established");
  assert.equal(text("backfill-readbacks"), "0");
  assert.match(text("backfill-planner"), /6 \/ 3,000 fixed members/);
  assert.match(text("backfill-planner"), /denominator is unknown/);
  assert.match(text("backfill-dependencies"), /Massive: worker credential unavailable/);
  assert.match(text("backfill-limits"), /not additive/);
  assert.match(text("backfill-limits"), /Planner movement is not useful data progress/);

  const detailed = JSON.parse(JSON.stringify(report));
  detailed.runs[1].identity_refresh_pending_count = 3;
  detailed.runs[1].identity_refresh_next_retry_at = "2026-10-30T08:01:00Z";
  detailed.runs[1].identity_recalculation_pending_tasks = 5;
  detailed.delivery.runs[1].families[0].nonminute_coverage = {
    physical_receipt_records: 30, selected_derived_records: 0,
    source_count_basis: "PHYSICAL_PROVIDER_RECORD_OCCURRENCES_NOT_GLOBAL_UNIQUE_EVENTS",
    fields: [{field: "headline", period: "TARGET", observed_field_slots: 30, usable_values: 29,
      missing_values: 1, null_or_unusable_reasons: {FIELD_NOT_RETURNED: 1}}]
  };
  context.renderBackfill(detailed);
  assert.match(text("backfill-planner"), /3 identity updates await recalculation admission/);
  assert.match(text("backfill-planner"), /5 affected calculations are queued or running/);
  assert.match(text("backfill-body"), /Field availability/);
  assert.match(text("backfill-body"), /29 usable \/ 30 observed; 1 missing/);
  assert.match(text("backfill-body"), /repeated appearances/);
  assert.equal(text("backfill-coverage-state"), "Not established");

  const shared = JSON.parse(JSON.stringify(detailed));
  const sharedCoverage = shared.delivery.runs[1].families[0].nonminute_coverage;
  sharedCoverage.source_count_basis = "PROVIDER_RECORD_KEYS_DEDUPLICATED_WITH_EXPLICIT_CONTENT_FALLBACKS_NO_CROSS_PROVIDER_MATCHING";
  sharedCoverage.shared_records = {unique_articles: 2, article_security_links: 4,
    verified_source_occurrences: 3, source_versions: 2, conflicting_records: 1,
    projection_pending_verified_pages: 5, cross_provider_matching: "NOT_ASSERTED"};
  sharedCoverage.fields[0].record_type = "ARTICLE";
  shared.delivery.runs[1].families.push({family: "CTX02", committed_records: 120,
    nonminute_coverage: {shared_records: {unique_contract_references: 5, unique_contract_session_bars: 120, non_session_option_bar_records: 2,
      verified_source_occurrences: 126, source_versions: 125, cross_provider_matching: "NOT_ASSERTED",
      contract_work: {registered_contract_windows: 5, unreconciled_verified_enumeration_pages: 3,
        existing_overlap_contract_links: 2, expected_contract_population: null}}}});
  shared.delivery.runs[1].families.push({family: "N03", nonminute_coverage: {
    shared_records: {boundary_support_events: 2, shared_action_workflows: {open_units: 7}}}});
  context.renderBackfill(shared);
  assert.match(text("backfill-body"), /2 unique provider articles · 4 article\/security links/);
  assert.match(text("backfill-body"), /3 verified source appearances · 2 retained versions/);
  assert.match(text("backfill-body"), /5 contract references · 120 contract\/session daily bars/);
  assert.match(text("backfill-body"), /2 option bar records have no verified market date/);
  assert.match(text("backfill-body"), /5 registered contract\/windows · 3 verified enumeration pages await successor admission/);
  assert.match(text("backfill-body"), /Earlier overlapping requests remain executable/);
  assert.match(text("backfill-body"), /5 verified pages await deduplicated counts/);
  assert.match(text("backfill-body"), /1 records have conflicting provider versions/);
  assert.match(text("backfill-body"), /7 open shared corporate-action units/);
  assert.match(text("backfill-body"), /2 events support the target window/);
  assert.match(text("backfill-body"), /Field availability for unique provider records/);
  assert.match(text("backfill-body"), /Records from different providers retain separate identities/);
  assert.doesNotMatch(nodes.get("backfill-body").children[14].textContent, /Historical article attribution/);
  assert.equal(text("backfill-coverage-state"), "Not established");

  context.renderBackfill({runs:[{id:"minimal-run",status:"ACTIVE"}]});
  assert.equal(nodes.get("backfill-body").children.length, 16);
  assert.equal(text("backfill-plan-state"), "Unknown");
  assert.equal(text("backfill-readbacks"), "Unknown");
  assert.match(text("backfill-progress"), /Unknown physical pages/);
  assert.equal(nodes.get("backfill-body").children[9].children[2].textContent, "Unknown / Unknown");
  assert.match(text("backfill-dependencies"), /Massive: configuration unknown/);

  context.renderBackfill({runs:[]});
  assert.equal(text("backfill-state"), "No recorded run");
  assert.equal(nodes.get("backfill-body").children.length, 16);
  assert.equal(text("backfill-plan-state"), "Unknown");

  context.renderBackfill(report);
  const calls = [];
  document.hidden = false;
  context.fetch = async (path, options) => {
    calls.push({path, method:options.method || "GET"});
    return path === "/api/backfill/status" ? {ok:false,json:async () => ({error:"Status storage unavailable."})} : {ok:true,json:async () => ({jobs:[]})};
  };
  await context.refresh();
  assert(calls.some(call => call.path === "/api/jobs"));
  assert(calls.every(call => call.method === "GET"));
  assert.equal(text("connection-label"), "Partially updated");
  assert.equal(text("metric-total"), "0");
  assert.equal(nodes.get("backfill-error").hidden, false);
  assert.match(text("backfill-error"), /may be stale/);
  assert.equal(nodes.get("backfill-body").children[9].children[3].textContent, "25");

  context.fetch = async path => ({ok:true,json:async () => path === "/api/backfill/status" ? report : {jobs:[]}});
  await context.refresh();
  assert.equal(text("connection-label"), "Connected");
  assert.equal(nodes.get("backfill-error").hidden, true);
  console.log("replacement UI contract passed");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
