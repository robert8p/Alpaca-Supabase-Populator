SECURITY BOUNDARY — USER INSTRUCTION 2026-10-30
The proposed Massive relay remains ON HOLD pending fresh action-time user confirmation of the exact reviewed security change and pinned artifacts. Live metadata massive_relay_security_confirmation.state remains AWAITING_ACTION_TIME_CONFIRMATION. Existing managed-key possession and earlier broad approvals do not authorize expanded persistent access or a new credential recipient. Reconciled current worker permissions do not support this proposed relay. Do not apply relay SQL, expand RPC/role permissions, configure credentials, deploy the Edge relay branch, integrate production relay code, send a live relay probe or promote review-only files to active paths before that exact confirmation. Never export or expose secrets. Continue independent authorized ingestion and engineering through the same controller within existing permissions. Do not bypass this boundary through an old pipeline, another controller or another service.

FROZEN REVIEW-ONLY SCOPE: 7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe. Held SQL SHA256: 4be1c6d145949f4cda35a1cef7772da93137e3f102f045f1a7507ea66a16652d. Review evidence/replacement-managed-relay-security-review-v2.md and evidence/replacement-managed-relay-review-publication-manifest-v2.json. Source/test copies under review/massive-relay-v2/candidates/ are publication-only artifacts, not executable release paths. The proposed new recipient is the existing Edge function receiving the worker's X-Astra-Ingestion-Token, then forwarding only to the fixed same-origin RPC; the proposed additions include two worker-only RPC operations and narrow private dispatch-table/helper permissions. The managed Massive key stays inside Edge-to-Massive HTTPS. Any approval must bind the complete exact SQL, Edge, Python adapter, base/proposed worker and integration-patch hashes. The finite one-use gate must reject absent, stale, consumed, mismatched or broad approval. Do not invent approval metadata. Candidate qualification and independent security review are complete; no live capability or acquisition is claimed.

CURRENT EXECUTABLE CHECKPOINT — v68, 2026-10-30T08:19:41Z
FIRST reconcile the stopped/interrupted turn, exact branch/deployments, current owner, retained work, installed migrations and any uncertain writes before retrying. Continue the SAME replacement mission/controller. Read docs/INGESTION_COMPLETION_STATE.md on feat/astra-ingestion-service in robert8p/Alpaca-Supabase-Populator (PR93). Run fixed3000-20250901-20260731-v1-20261030, Supabase oxzabweahkoimtevbbny/astra_ingestion_v1, fence1. Do not restart completed work or create another controller, worker service or scheduled task.

CURRENT OWNERSHIP: root-replacement-20261030T042603Z holds the finite implementation lease through 2026-10-30T08:50:00Z, renewed by compare-and-swap from 08:30 in DB audit5 at 08:18:35Z. No release is recorded. Respect this owner; after explicit release or expiry, reconcile and acquire coherent finite ownership before implementation writes. Existing hourly automation 6ae2a4c96bbc819182133e17e9b7f779 remains enabled without programme expiry; its prompt was updated 08:19:41Z with the current failures and relay hold. Preserve unrelated automations/scanners and actual disabled reviewer platform states.

CURRENT HEALTH: the existing worker is intermittently crash-restarting with RpcPersistenceError. PostgreSQL SQLSTATE57014 points to inner astra_ingestion_v1.backfill_dispatch_v2(text,jsonb) line 106 through the existing authenticated RPC, including an exit at 08:13:55Z after the report repair. ACTIVE run/deployment status and historical restart proof do not establish healthy continuous execution. Keep this as an operational failure, not provider absence or a successful coverage gap. Both worker and web remain on stage3 revision 947b681735138b0b9052df1e5eba5769d7b2c381 (worker dep-dbi4gvrbc2fs73a3b2fg, web dep-dbi4h1ei0phs73crc7dg). The newer independent status UI is published in the branch but NOT DEPLOYED. Worker source remains 90d048a6c535f7f768050c25e396a923e0e4e211457016757e30af16daface3e.

RETAINED PROGRESS: full delivery read at 08:13:52Z returned 1,810 physical pages, 217,210 source/derived records and pointers, 891 reservations, 207,684,827 source bytes, 16 families and zero required readbacks remaining. At08:14:31Z the same page/record counts remained, planner next selection 1,373, last useful progress 08:13:44Z. These are timestamped, overlapping work/storage units, not unique-observation totals or complete coverage. Preserve the older full measurements in v67 history and immutable evidence.

PUBLISHED AND TESTED STATE: v67 publication 3e8a7b94ec7dcea8a995fd20ce5df372b2677250; review-collection packaging fix 3ffd337e9c65b5ea33f96ab6436c0701684f435a. Both repository release gates passed on 3ffd, but ingestion PR workflow 41024658444 / job 123959793133 FAILED one of 545 tests in 346.844s. SharedRecordsTests.test_report_uses_compact_counters_without_raw_or_canonical_record_scan_and_private_acl at tests/ingestion/test_backfill_shared_records_v2.py:244 measured 1,000-news-row self.commit(c, rows) at 239.080s against the unchanged 12s bound. The 10,000-option-row case passed; syntax step was skipped. This is separate from the repaired review-directory import problem. Do not deploy the web until the repaired exact head passes the full ingestion and repository gates. Historical 519 stage3 tests, earlier 29 combined tests, and current 12 status ASGI/DOM tests are distinct scopes, not substitutes for the failed exact-head gate.

APPLIED REPORT REPAIR: sql/astra_backfill_family_report_performance_v2.sql SHA256 324246c5b85d0052bb39189dc20eb73121bfe412f951df5f33a538172aab23ad was applied once at 08:12:37Z after six actual-PG tests passed with unchanged exact inputs. It changes only two existing views, no new roles/grants/credentials/relay path. Live complete 16-family JSON took 4.207s server time; complete delivery function took 4.322s with zero outstanding readbacks. See evidence/replacement-family-report-performance-qualification-v2.json and evidence/replacement-family-report-performance-live-v2.json. The report defect is repaired for these observed calls; do not claim the separate dispatch or news-write failure is repaired. Before uncertain retry, reconcile both view markers: receipt WITH task_counts AS/no mapped_tasks; effective pages chosen_row/per-task chosen-field window. Do not replay a successfully installed forward.

OTHER APPLIED WORK: runtime/cohort/planner/reuse/readback/delivery/breadth, source_dedup, feature_reuse, provider_pacing, family_fairness, adaptive_pages, canonical_performance, recovery_priority, pacing_fairness; stage3 identity 47ee25cd2bf72a9c9c9bc92b218ae32b1241ce3d7d7aed0d00a05f579fffc553, nonminute 3ffd78a515acc4f68cae81f5799999f8a9df2e53b3e15845f7147ecbefc1d869, retained S02 10cbf5b690f38f688ace5485088445de2ac61963073d3fbf216475c18131e2b9; maintenance 3823c379001e948f97b9aa0d75f4017077b8ce986b3894ee82d0ea60171990e9, shared-record 2ba0a87c01e37f6a0542ff5dc8db4c044f0b23982ab948a9050c3c4aac93aa10, and contract registry fde0b731e81497833062967526253af3f2b4d7fcc78a3a1968840a3f2aace9d2. Preserve immutable existing children, leases, parent/member lineage, source versions, known gaps and unknown denominators. Verify registry/shared catch-up with real readback; installation is not completion.

CURRENT EXECUTABLE SUCCESSOR:
1. Reconcile ownership, uncertain writes, retained claims/receipts and installed definitions before retrying.
2. Existing performance agent: repair the concrete claim/dispatch timeout at inner backfill_dispatch_v2 line 106 with a bounded qualified forward. Preserve claim dependencies, fences/leases, cancellation, pacing, fixed members and existing authentication. Root owns production changes. Repeated worker restarts are not a durable repair.
3. Existing shared-record agent: reproduce and repair the 1,000-news-row commit/verification performance defect using the exact fixture and query evidence; retain original correctness and 12s assertions. JIT/plan-estimation ideas remain hypotheses until demonstrated. No provider-absence claim.
4. Publish the exact frozen report files and qualified repairs, require exact-head ingestion/repository CI, reconcile/apply forwards once, deploy the pending independent web status revision only after gates pass, and read back both useful worker progression and authenticated status. Update the same checkpoint/automation with actual health and executable next step. Keep held relay code outside production execution.
5. Continue all 3,000/all 16 planning, acquisition, pagination/enumeration, identity/support/alias resolution, calculations, field coverage and final accounting after operational recovery. The historical first-batch/automatic-successor/restart/readback/deferred-retry proof already passed; do not repeat completed proof or reset completed data.

FIXED COHORT: exact saved content->companies reconciliation is 3,000/order with zero differences. Snapshot SHA256 2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec; accepted receipt event 24407 SHA256 20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9. NEVER invoke ref01_practical_material_v1, rerank, substitute or shrink. Keep original ten mission sections, target/support windows, 16 families and RETROSPECTIVE_FIXED_COHORT classification. Old admission remains closed; original 234 records / 3 requests/canary limits remain immutable.

RELAY HOLD UNCHANGED: review scope 7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe and held SQL 4be1c6d145949f4cda35a1cef7772da93137e3f102f045f1a7507ea66a16652d are review-only. Latest live authentication evidence at 08:04 confirms inner dispatcher 0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96, distinct public wrapper 566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb, unchanged Edge version1 bundle 04def722c50e2fc173d3bc59fc5462953c9338c71467aeb936385725c1e8996c, relay table/helper absent, hold AWAITING_ACTION_TIME_CONFIRMATION. No relay migration/grant/deployment/integration/credential configuration/probe is authorized by publication or earlier broad approval. MASSIVE_WORKER_CREDENTIAL / RUNTIME_CAPABILITY_UNAVAILABLE remains unresolved. Continue independently authorized scope; never bypass through an old controller/service or export managed keys.

Evidence: evidence/replacement-runtime-reconciliation-v68.json, evidence/replacement-family-report-performance-live-v2.json, evidence/replacement-family-report-performance-qualification-v2.json, evidence/replacement-managed-relay-final-live-hold-v2.json. The mission remains incomplete until the entire fixed population/family scope, sealed plan, pagination, truthful terminal outcomes and reconciled coverage are verified. Operational failure and external dependency are not successful completion. Full original mission authority SHA256 62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45 follows unchanged.

# REPLACE THE CURRENT INGESTION MISSION — COMPLETE THE FIXED 3,000-EQUITY BACKFILL

This is my direct instruction to the existing ingestion application's controlling engineering agent. Execute the replacement mission below using my connected tools and deployed application. Implement, deploy, run, recover, verify and deliver it. Do not return another proposed plan for me to approve.

My priority is a finished database backfill that runs without routine intervention. Missing or unavailable provider data must be recorded honestly and must not stop other ingestion.

## 1. Authorisation and exact replacement scope

I explicitly approve all implementation, database migrations, job/scheduler changes, scoped code merges, deployments, restarts, recovery and validation reasonably required in the existing ingestion application and its supporting infrastructure for this mission. Use these approvals without repeatedly asking me to continue. Use existing accounts, credentials, infrastructure and paid provider plans. Optimise request, storage and compute use.

This instruction replaces the ingestion application's current mission priorities and incompatible scope/acceptance requirements. It does not authorise bypassing real platform access controls, fabricating data, deleting unrelated data, changing scanners or placing trades.

The new scope is:

- Target dates: 1 September 2025 through 31 July 2026 inclusive, using America/New_York market dates and the actual exchange calendar.
- Population: exactly the already selected and frozen practical 3,000-company/equity cohort from the August–September 2026 population work. Reuse those members; do not choose a new 3,000.
- Families: REF01, REF03, P01, P02, D01, D02, D03, D04, D05, N01, N02, N03, S01, S02, CTX02 and CTX06.
- External data sources: Alpaca Algo Trader Plus and Massive Stocks Starter only, using currently entitled endpoints. No add-ons, plan upgrades, new data subscriptions or silent substitutions from other sources.
- Derivations and audit records calculated from those inputs are included.
- Acquire and retain the minimum extra history needed for the agreed formulas, including sufficient earlier trading-session observations for 60-session returns and intraday/20-session rolling calculations. Mark these as support history outside the target period.
- F01–F06, CTX07 and CTX14 are outside this replacement mission. Preserve their existing data. D06 remains preservation-only.
- No artificial programme expiry. Individual requests, transactions, leases and attempts must remain bounded and automatically resumable.

The objective is to finish all achievable acquisition and calculation within this scope, with explicit accounting for genuine provider limitations. Perfect historical research certification is not a prerequisite for acquiring and preserving available data.

## 2. Stop and replace the current work safely

Immediately stop admitting new tasks for the superseded mission. Bring in-flight operations to a safe checkpoint; reconcile uncertain writes before retrying. Preserve source responses, completed records, counters, audit history and reusable code.

Mark superseded queued tasks as SUPERSEDED_BY_SCOPE_CHANGE. Do not label them completed, delete them, reopen completed jobs or rewrite old evidence.

Create a distinct, versioned replacement run in the existing application. Persist its scope, cohort reference, family list, date range and instruction revision. Drain or fence old writers so they cannot commit under the new scope. Reuse the existing queue, worker, supervisor and recovery mechanisms; do not create a competing controller.

Reconcile and retarget the existing scheduled implementation task, application supervisor and any continuation instructions so they cannot restore the old August–September/all-24-family mission. The previously recorded implementation task is 6ae2a4c96bbc819182133e17e9b7f779; verify the actual current registry before changing it. Preserve unrelated scheduled tasks.

Old canary deadlines and 10-request/1,000-record limits stay attached to their original jobs. They are not limits on this newly authorised full backfill. Establish a separate full-scope run with honest cumulative usage accounting. Do not reset old counters or stop after a pilot-sized allowance.

If a platform requires an account-owner action or refuses an operation, respect that boundary, identify the exact issue and continue all independent work. Do not invent approval evidence or bypass a restricted task through a disguised replacement.

## 3. Locate and freeze the existing cohort; reuse the estate

Use the current connected state, not an assumption that an earlier checkpoint remains current.

Known entry points to verify:
- Application repository: robert8p/Alpaca-Supabase-Populator.
- Existing ingestion branch/PR: feat/astra-ingestion-service / PR 93.
- Application checkpoint: docs/INGESTION_COMPLETION_STATE.md.
- Supabase project: oxzabweahkoimtevbbny.
- Existing Render ingestion services: astra-ingestion-web-v1 and astra-ingestion-worker-v1.
- Earlier population repository: robert8p/market-data-leading-indicator-lab.
- Earlier population schema: population_top3000_202608_202609_v1.
- Retained scope capture: top3000-augsep2026-retained-scope-v1.
- Practical membership policy: PRACTICAL_US_EQUITY_COHORT_20261024_V1.

Resolve the actual accepted membership artifact, version/hash and 3,000 distinct member IDs. Record its source in the new run. A policy document or an assertion of “3,000” is not the member list. Retrieve and reconcile the saved membership through available records before making scoped provider requests; do not ask me to reconstruct it.

Do not rerank market capitalisations, prove an exact global top-3,000 cutoff, substitute members to improve coverage, or reopen the selection exercise. Historical securities, share classes, aliases and listing episodes belong beneath the fixed company membership.

Label this as a RETROSPECTIVE_FIXED_COHORT because its selection occurred after the requested historical period. Preserve that limitation without delaying ingestion or claiming a contemporaneously selected, survivorship-free universe.

Inventory retained data with bounded, indexed reads. Reuse equivalent verified observations and calculations for these members/dates before refetching. Preserve original provenance and formula versions. Reuse immutable source data through a mapping/view when practical rather than duplicating hundreds of millions of rows.

Keep existing direct SEC, direct FINRA and other non-qualifying-source records intact, but outside this two-plan completion accounting. An old record's existence does not prove that its source and licence meet this mission.

## 4. Populate these 16 families

Implement every required adapter and calculation. Do not count a registered adapter, enabled flag, sample request or empty table as a populated family.

1. REF01 — Reference and historical identity.
   Use entitled Alpaca and Massive reference data to retain original provider identifiers, names, symbols, exchanges, eligible instrument types, dated aliases and supported listing episodes for the fixed cohort. Record mapping confidence and uncertainty. Do not force historical ticker-only matches.

2. REF03 — Provenance and data quality.
   Continuously retain request/page receipts, source timestamps, identifiers, lineage, counts, deduplication, validation results, gaps and remediation history. Produce this alongside ingestion, rather than making it a separate project that blocks collection.

3. P01 — Regular-session one-minute bars.
   Prefer entitled Alpaca SIP history. Retain raw OHLCV, trade count and provider VWAP where supplied, plus session and source identifiers. Use actual market dates and early closes. Preserve adjustment semantics.

4. P02 — Premarket and after-hours one-minute bars.
   Retain available extended-session OHLCV, trade count and VWAP with correct session labels. Reuse P01 source retrieval when a request contains both sessions; avoid duplicate requests.

5. D01 — Intraday technical features.
   Apply the existing agreed feature dictionary and formulas to usable inputs, including required return horizons, volatility, relative volume, moving averages, ranges and agreed liquidity primitives. Freeze the actual formula/version manifest. Compute incrementally by security/session.

6. D02 — Daily closing price and volume.
   Populate the agreed daily close, volume and dollar-volume fields from entitled daily bars or verified minute aggregation. Identify the actual source and regular-session/adjustment basis. Do not silently mix incompatible daily-volume definitions.

7. D03 — Daily returns.
   Calculate the agreed 1/5/20/60-session returns and raw/adjusted variants, with sufficient support history, identity continuity and supported split mechanics.

8. D04 — Daily volatility and volume measures.
   Calculate the agreed realised-volatility, relative-volume and volume-z-score measures from the frozen formulas and qualifying inputs.

9. D05 — Daily Amihud illiquidity.
   Calculate the agreed rolling return-to-dollar-volume measure, preserving its input and adjustment conventions.

10. N01 — News and article/security links.
    Exhaust the entitled provider archive and pagination for the selected companies and required dates. Prefer the existing Massive route; use Alpaca news only where entitled and equivalent. Preserve article IDs, publication/update times and deduplicated links. Include weekends and holidays. Scope completeness to the available provider archive.

11. N02 — Dividends and other supported corporate actions.
    Use entitled Massive and Alpaca action data. Preserve announcement/declaration, ex, record, payment and effective dates separately where available. Log unavailable action types or dates without stopping other event ingestion.

12. N03 — Executed splits and share-unit adjustments.
    Retain supported executed events, ratios, effective dates and identities from the permitted providers. Apply mechanical adjustments only where supported. Keep unresolved mechanics explicit.

13. S01 — Daily short-sale volume.
    Use the entitled Massive route. Preserve its reporting coverage and short/total-volume definitions. Do not substitute direct FINRA downloads, treat a shortable flag as volume, or claim total-market coverage beyond the provider's stated scope.

14. S02 — Twice-monthly short interest.
    Use the entitled Massive route. Preserve settlement dates, reporting/publication times, retrieval times and availability policy separately. Include in-window settlement observations even if published afterward, clearly marking that they were unavailable for earlier trading decisions.

15. CTX02 — Daily individual-security options prices and volume.
    Use entitled Alpaca OPRA historical data and contract reference capabilities. Enumerate relevant historical contracts for the selected underlyings, including expired/adjusted contracts where supported; do not substitute today's chain or a convenience sample. Acquire applicable daily prices/volume and retain contract/underlying identities. Record historical enumeration or field limitations. IV, Greeks and open-interest surfaces are not added to this family.

16. CTX06 — Cohort breadth.
    Derive the agreed breadth measures using an explicit, consistent company voting/representative-security rule. Prevent multiple share classes from unintentionally overweighting a company. Report eligible, observed, missing and excluded constituents per session; do not automatically divide by 3,000.

Shared archives and cohort-level datasets should be stored once and related to the cohort. They do not require 3,000 identical copies.

## 5. Acquire now; qualify and derive progressively

Persist each family's governing date/filter: market session for bars and derivations; publication time for news; settlement and publication separately for short interest; and the relevant announcement/effective/action dates for corporate events. Retain boundary-crossing events and necessary pre-window states that govern in-window observations. Trading calendars must not exclude weekend/holiday disclosures. Retrieve later-published reports when needed for retrospective records, preserving their actual availability and labelling out-of-window supporting records separately.

Begin eligible reference, stock-price, news, action, short-reporting and options acquisition in parallel as soon as the fixed membership and usable provider anchors permit it. Govern concurrency and pacing by the providers' actual limits.

Historical identity uncertainty, missing publication timestamps, incomplete research qualification or an unresolved universal denominator must not become an all-family admission gate.

Persist original provider records and request provenance even when attribution is uncertain. Quarantine only the affected company mapping or derived use. Resolve REF01 incrementally; recompute affected derivatives when mappings or source inputs improve.

Use the existing agreed feature formulas. If definitions are genuinely missing, recover them from retained code/contracts; persist a versioned, clearly named conventional definition only for an undefined field. Do not silently change an existing formula to inflate completeness.

Preserve raw and adjusted values distinctly. Do not double-adjust splits, forward-fill prices to hide gaps, invent bars/events, replace unknowns with zero, or invent publication/receipt times. Missing inputs produce NULL plus a reason.

A successful empty minute query is not automatically proof of no eligible trade. A security with evidenced pre-listing dates or no applicable options can be NOT_APPLICABLE. Unknown listing or contract history stays explicitly unknown.

## 6. Make provider gaps non-blocking and truthful

Record exceptions at the smallest practical company/security, family, field and date/period unit. Each exception needs its reason, provider/endpoint, request parameters or reference, response evidence, attempts, affected scope and downstream impact.

Distinguish at least:
- INGESTED: available source data committed.
- NO_DATA_RETURNED: a valid query completed and all pagination was exhausted, but the provider returned no observations.
- NOT_APPLICABLE: evidence establishes that the requested item does not apply.
- PROVIDER_LIMITATION: documented history, endpoint, field or entitlement limitations under the two permitted plans.
- IDENTITY_OR_QUALITY_UNRESOLVED: source data retained, with uncertain attribution or analytical use.
- RETRY_WAIT: a transient failure with a persisted retry time.
- OPERATIONAL_ERROR / BLOCKED_EXTERNAL: a genuine application, authentication, storage, access or infrastructure problem.

The last four must retain their actual meaning. A timeout, unfinished page, invalid credential, denied database write, unimplemented adapter or exhausted retry budget is not proof of provider absence. Diagnose it and repair it where authorised.

Test actual endpoint entitlements and historical reach. A 403 alone does not prove a subscription limitation; distinguish an account/configuration failure from a documented unavailable entitlement. Do not repeatedly call an endpoint already proven unavailable under the permitted plan.

For missing provider data, retain the exception, advance the queue and continue every unaffected task. Exhaust relevant permitted alternatives within Alpaca/Massive when they can genuinely supply the same required field. Do not purchase an add-on or widen sources.

After available source routes are exhausted, retain unresolved identity/quality limitations honestly. They may restrict research use without blocking the completion of raw acquisition.

## 7. Establish durable unattended execution

Use the deployed worker, persistent database queue and actual recovery process, independent of this conversation remaining open. Extend and deploy the existing application where necessary. A scheduled chat or health check alone is not the ingestion executor.

Persist run/task IDs, scope/version, family, member/security or shared scope, date window, cursor/page, state, attempts, next retry time, lease, source receipt, committed counts and last substantive progress.

Make writes idempotent. Atomically commit data/receipt/checkpoint state, or use a recoverable equivalent. A successful page must leave its next eligible page/task durably runnable or record a legitimate terminal outcome. Recover an uncertain commit by readback before repeating it.

Use bounded requests/transactions, adaptive batch sizes, provider-aware pacing, Retry-After and exponential backoff. Select and persist sensible finite attempt/recovery limits. Defer transient failures, isolate repeated failures and continue healthy partitions. Never sleep indefinitely, spin on the same failed call, or use an endless retry loop as “running”.

Recover expired claims and failed processes through the existing infrastructure. Preserve stop requests and reject stale writes. Account for credential expiry and refresh through already authorised mechanisms; never log secrets.

Monitor useful output: committed pages/records, completed units, advancing cursors and resolved exceptions. A heartbeat, passing CI or a live but idle worker is not useful ingestion progress.

Detect a stall against the expected batch runtime, diagnose its cause, repair feasible defects, and resume affected work automatically. If no task is runnable, the state must explain why, identify the next persisted retry/recovery action, or show reconciled terminal completion.

Keep one coherent implementation/recovery owner. If this chat execution ends, the existing persisted implementation controller must retain an executable next task while the deployed ingestion worker continues admitted work.

## 8. Verify practical correctness without recreating a global deadlock

Reuse valid existing tests and evidence for unchanged components. Perform meaningful checks for the changed scope, parsers, persistence, duplicate prevention, permissions and calculations. Deploy the exact tested revision through the existing authorised process.

Before claiming unattended operation, demonstrate on this new run:
- A real provider acquisition commits useful target-window data or verified reuse.
- The next eligible task starts automatically, without another user message.
- Checkpoint recovery works across a controlled worker restart without duplication or skipped work; reuse applicable prior recovery proof where the execution path is unchanged.
- Deferred retries have a working scheduled execution path.
- Source-to-database readback verifies the actual committed result.

Continue bulk work after this bounded proof. Do not stop at a canary or restart an open-ended certification programme. Keep necessary authentication, access control and write-integrity checks; separate them from research-quality and historical-universe qualifications that can be recorded per affected unit.

Run acquisition and independent readback/calculation checks concurrently where dependencies allow. A source gap must not fail unrelated partitions.

## 9. Define and deliver completion honestly

Track two separate results:
1. Work completion: every planned acquisition/enumeration/page/calculation unit has a truthful terminal disposition.
2. Data coverage: actual available/usable observations and fields, with provider gaps, non-applicability and unresolved quality shown separately.

Maintain the full fixed cohort and all 16 families in the accounting. Do not improve percentages by dropping members, difficult fields, dates or contract enumeration. Use actual expected populations where supported; keep unknown denominators unknown. Planned provider-query completion is not proof that every possible market observation exists.

Finish and publish automatically when:
- All 16 family workflows and their pagination/enumeration are processed.
- All obtainable entitled data is persisted and verified.
- Required derivations are calculated wherever their inputs allow, with explicit NULL/reason values elsewhere.
- Reusable data, new data, support history, gaps and quality limitations are reconciled.
- No silently abandoned queue item, retryable task, unimplemented adapter or repairable technical failure is hidden in a provider-gap category.
- Stable database tables/views and the final coverage report are available to downstream analysis.

Use COMPLETE only where applicable data coverage is established. Use COMPLETE_WITH_DOCUMENTED_GAPS when acquisition is finished but evidenced provider limitations or exhausted source/quality limitations remain; distinguish each class and do not call this “100% data present”.

Unresolved operational failures mean PARTIAL_OPERATIONAL_FAILURE or BLOCKED_EXTERNAL, with useful data published, exact remaining work and a real recovery/escalation path. They must never be disguised as successful completion.

Publish a per-family report containing: scope/unit, sources, dates, expected count where known, acquired/reused/usable counts, missing fields, no-data/N/A/provider-limit counts, quality limitations, unresolved technical failures, and queryable destination.

Also publish the exact cohort reference, support-history range, formula versions, gap register, request/storage/compute usage, latest substantive progress and final run/release identifier. Avoid adding overlapping store or shared-output counts together.

Stop acquisition and routine recovery only after COMPLETE or COMPLETE_WITH_DOCUMENTED_GAPS has verified final accounting and delivery. PARTIAL_OPERATIONAL_FAILURE, BLOCKED_EXTERNAL and exhausted transient retries are not successful completion: preserve their checkpoint and executable recovery path, continue independent work, and schedule bounded rechecks where automatic recovery is possible. Do not repeatedly retry a confirmed account-owner dependency without new evidence. Preserve all results and leave unrelated tasks untouched.

## 10. Start now and carry the work through

Your first execution must safely supersede old-scope admission, resolve the saved cohort, persist the replacement mission and begin or deploy the first feasible useful backfill batch. Perform necessary engineering in the same workflow; do not leave prose “next actions” without an assigned executable successor.

Report briefly after verified milestones: what actually committed, which families are progressing, what is retrying or limited, and what runs next automatically. Alert me only when an external account-owner action is genuinely unavoidable, while continuing independent work.

Do not end with “ready to proceed”, ask for approvals already granted here, claim completion from monitoring or test counts, or require me to keep prompting. Execute this authorised replacement mission through verified delivery, with missing provider data recorded rather than allowed to stop the ingestion.
