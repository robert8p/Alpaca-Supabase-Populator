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