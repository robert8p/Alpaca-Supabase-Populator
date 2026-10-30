# ASTRA ingestion — replacement checkpoint v70

**Checkpoint cutoff:2026-10-30T11:12:47Z.** The same fixed-cohort mission/controller continues. The status rewrite and summary index are installed, internal combined status SQL is faster, and useful worker progress is independently verified after maintenance. The earlier normal-claim timeout remains retained for conditional recovery. No authenticated endpoint-latency, clean-log, sustained-health or mission-completion claim is made. The unchanged relay package remains held.

## Current progress and ownership

At11:12:47.371590Z the run recorded **3,943 committed pages,476,704 physical records/pointers,1,945 reservations,410,287,589 source bytes and3,943 independent readbacks**, with **zero unread pages**. Last useful progress was11:12:45.881062Z; planner next member position is **1,984**, with planning incomplete. Worker `b1ae8fda-aa18-4d34-be11-1fdc97c3f649` had heartbeat11:12:44.989694Z on the existing947 source/service. Compared with the premaintenance report, this verifies **+27pages,+3,588records/pointers and+15reservations after maintenance**. Counts overlap; they are not unique observations or full coverage. [Exact progress receipt](../evidence/replacement-independent-progress-1112-v70.json).

The postmaintenance SQL-log lookup returned **Connector Internal Server Error**. Fresh SQL-error absence is therefore unavailable, not established. Progress proves useful work resumed; it does not prove sustained reliability or removal of every earlier failure.

Owner remains `root-replacement-20261030T042603Z`, lease through **11:30UTC**, renewed10:51:18Z/audit18. Same enabled hourly automation `6ae2a4c96bbc819182133e17e9b7f779` was updated **11:02:21Z** with the then-current diagnosis; this prompt carries the later outcome into its existing continuation. The schedule, full original mission and controller are unchanged. Reconcile owner/lease before implementation; no competing task/controller or owner release is recorded.

Publishedv69 was ref-verified at `3f8698b9c35b7a26ff60970bab9555c477cab1ae` and recorded by audit17 at10:50:44Z. Exact history remains in [v69 checkpoint](history/INGESTION_COMPLETION_STATE_v69.md) and [v69 automation prompt](history/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT_v69.md). The current source base is **`9577b25fa6fdddbf509795b6c93571233485626d`**, tree `64b52b304aa8cd0bba027336d659007658b86ae7`, following status-rewrite release `d63a7142dd2f6395b230b4907199d925951176cc`. Both exact heads passed all four intended CI workflows/jobs on attempt1.

## Status rewrite and installed index

The status rewrite materializes task groups and distinct pending kinds, reducing repeated worker-capability checks in the report branch. It was applied once10:52:02Z. Readback10:52:51Z preserved private function OID16040232, owner,ACL/configuration and the entire non-status/claim tail. It added no helper, role or grant.

| Installed proof | Exact value |
| --- | --- |
| Rewrite SQL SHA256 | `3dbb59fb016f3838f6bbbfe5942674b8cba61cb9a02f474bfd37317e6340c9e7` |
| Private `backfill_dispatch_v2` definition SHA256 | `136871b8ca305ae69c661541d9c2684e71b1d5e6fe84a6ec9b8b594b1da56d02` |
| Status marker | `backfill_runtime_status_asof_v2`, text position3099 |
| Unchanged non-status/claim tail SHA256 | `836360913257d69e02692ff6d7b9e9856c3aaa14d522031661af76a538040c09` |
| Unchanged outer authenticated definition SHA256 | `0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96` |
| Successful maintenance SQL SHA256 | `d690b72cfea50dfa0696eca54e0ae3870649f31cba44bf41a9dd08afe218113f` |
| Installed summary index | `backfill_tasks_runtime_summary_v2`, OID16422385, valid/ready, nonunique,5,734,400bytes |
| Exact seven keys | `run_id,family,kind,provider,status,records_committed,last_progress_at` |

**Reporting freshness has an explicit boundary change:** capabilities are evaluated at the report's returned `observed_at`/`v_now`. A worker fresh then but expiring mid-report remains fresh for that report; old repeated`clock_timestamp()` checks could change its classification during execution. Strict`>` cutoff, JSONB membership, future timestamps and every live-clock **claim/admission** guard remain unchanged. Ordinary output values, grouping/numeric/NULL behavior and metadata were qualified; equivalence at an expiry crossing is not claimed. [Five-case qualification,66.100seconds](../evidence/replacement-runtime-status-performance-qualification-v2.json).

The initial combined internal report measured **6,848.010ms at10:54:07Z**. Two8-second ordinary index builds then timed out during CREATE INDEX; authoritative readbacks at10:55:04Z and10:56:58Z found the index absent and authentication unchanged. Those failed attempts are retained and exhausted; they are not replayed.

A separately qualified ordinary-maintenance variant changed only the single DO execution budget to **20seconds**, retaining the3-second lock limit, exact index definition and source/schema/name guards. Three actual PostgreSQL tests passed in25.761seconds, including blocked-build and whole-DO rollback. The root applied this variant **once**, success observed11:06:19Z. Independent readback11:06:53.699006Z verified the exact ready/valid index and unchanged status/auth definitions. [Maintenance qualification](../evidence/replacement-runtime-summary-maintenance-qualification-v2.json); [complete live reconciliation](../evidence/replacement-runtime-status-live-v70.json).

The maintenance advisory lock and ordinary CREATE INDEX could pause shared RPCs/task writers. **20seconds was the DO budget, not a guaranteed wall-clock lock-release bound**; commit/rollback and cleanup can add time. All routine RPC/provider/relay deadlines remained unchanged. The index now exists. **Do not reapply either the8-second or20-second index migration.** Reconcile actual presence/validity before any future recovery action.

## What the timing proves

| Measurement | Before index | After index |
| --- | ---: | ---: |
| Combined internal runtime summary plus16-family delivery SQL |6,848.010ms at10:54:07Z |**2,105.451ms at11:06:56.840155Z** |
| Statement/lock limits |8s/3s |8s/3s |
| Outer authenticated RPC measured |No |No |
| Outer advisory-lock hold measured |No |No |

Both calls were read-only and used the same combined internal branch; they made no provider request. The observed improvement is real for that measured SQL path. It is **not an authenticated application-latency or outer-lock-duration proof**. The filtered Render lookup for GET`/api/backfill/status`, HTTP200,10:52–10:56:59 returned zero entries; that is no proof of traffic absence, successful authentication or latency. Do not block this checkpoint waiting for inaccessible credentials, and do not invent that proof. [Exact timing probe](../evidence/replacement-combined-status-timing-probe-v2.sql); [observations and limits](../evidence/replacement-runtime-status-live-v70.json).

The latest independently verified progress occurs after maintenance, as recorded above. The earlier CI receipt embeds a pre-progress production snapshot; its observation-time hash and then-unverified progress are retained as historical evidence. The updated live receipt and11:12 progress receipt supply the later verified outcome.

## Prior worker failure: normal claim candidate, not attributed to the UI

Safe PostgreSQL logs place SQLSTATE57014 at **10:53:28.600Z** in private dispatch **line123**, matching Render's10:53:28.617 RpcPersistenceError and exit1 at10:53:31. Live line-number reconciliation identifies the **normal fairness claim-candidate SELECT**, not the status branch. This failure **preceded both index-build attempts**. Neither status polling nor index maintenance is established as its cause. Automatic restart/backoff was observed. [Exact safe error, function lines and parameters](../evidence/replacement-claim-timeout-reconciliation-v70.json).

The root executed one **plain generic EXPLAIN**, read-only, with no actual query/claim/lock execution. It used the historical11:00:49 parameter snapshot. The resulting plan retains the family-turn index and LockRows; the new summary index was not chosen. Actual failed family, execution duration and worker cached-plan selection remain unknown. This estimate is not a claim-performance measurement or repair. [Saved generic plan](../evidence/replacement-claim-normal-generic-live-plan-v70.json).

Prepared [generic probe](../evidence/replacement-claim-normal-generic-plan-probe-v70.sql), [family-specific custom probes](../evidence/replacement-claim-normal-custom-plan-probes-v70.json) and [runbook](../evidence/replacement-claim-plan-probes-v70.md) preserve the original dependency, reuse-gap, breadth, cohort-count, fence, priority and lease guards. Local qualification covered17 nonexecuting plans in0.860seconds; it made no production claim and provides no live execution timing. [Preparation qualification](../evidence/replacement-claim-plan-probe-qualification-v70.json).

**Current action is to keep the existing worker and automatic recovery active.** Investigate the exact current claim family/workload only if a **fresh error or substantive progress stall recurs**, using then-current evidence and bounded diagnostics. Do not run all16 family probes merely because they exist, infer the failed family from the later turn snapshot, weaken guards or install a speculative claim rewrite. No claim rewrite was applied by this checkpoint.

## Exact-head validation and deployments

All four workflows/jobs passed on attempt1 for source9577:

| Gate | Run / job | Result |
| --- | --- | --- |
| Ingestion push |41045597684 /124028784431 |579passed,278.401s; syntax passed |
| Ingestion PR |41045607606 /124028817555 |579passed,278.118s; syntax passed |
| Repository release push |41045597727 /124028784299 |675passed,294skipped,one warning,10.89s |
| Repository release PR |41045607646 /124028817356 |675passed,294skipped,one warning,12.39s |

The earlierd63 head also passed all four intended gates,576tests in each ingestion run. Strict existing performance/correctness gates remain intact. [Latest9577 receipt](../evidence/replacement-9577-release-gates-v2.json); [d63 receipt, already published with9577](../evidence/replacement-d63-release-gates-v2.json).

Web remains the previously verified LIVE `dep-dbi6h1rbc2fs73a8fk00` on testedbf69. Worker service remains `dep-dbi4gvrbc2fs73a3b2fg`/source947, worker file SHA256 `90d048a6c535f7f768050c25e396a923e0e4e211457016757e30af16daface3e`. The new source releases contain SQL/tests/evidence and do not imply new web or worker deployments. Fresh browser end-to-end verification and sustained-health/clean-log claims remain unavailable.

## Fixed mission, retained work and relay boundary

The [original ten-section instruction](REPLACEMENT_BACKFILL_MISSION_20261030.md), SHA256 `62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45`, and complete automation mission tail are byte-identical. Continue run `fixed3000-20250901-20260731-v1-20261030`, fence1, all3,000 frozen members/all16families, existing providers/plans, target2025-09-01–2026-07-31 New York exchange dates and required support/formulas. Snapshot `content->companies` SHA256 `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`, acceptance event24407 and exact membership/order remain controlling. **Never invoke `ref01_practical_material_v1`, rerank, substitute, shrink or restart the cohort.**

All earlier planning/reuse/cache/fairness/identity/derived/shared/registry/readback work and immutable receipts remain retained. Keep one complete member per planner transaction and unchanged breadth. Legacy canary234records/3requests and old-scope closure remain unchanged. Counts overlap; planning, pagination/enumeration, identity and field-level coverage are still incomplete. Full prior chronology and16-family accounting remain in [v69 history](history/INGESTION_COMPLETION_STATE_v69.md).

Relay state remains **`HELD_APPROVAL_EXPIRED_TRANSPORT_MISMATCH`**. Original09:53 approval/ref`Sentinel_2bd8b52631f081918ab63db69e720cb5` expired10:08 after one pre-DDL rejection. Scope `7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe`, SQL `4be1c6d145949f4cda35a1cef7772da93137e3f102f045f1a7507ea66a16652d`, all19 reviewed payloads, outer authentication and worker pins remain unchanged. No relay installation, approval redating/extension, validator/package edit, secret export or new trust relationship occurred. [Expired approval/hold](../evidence/replacement-managed-relay-expired-approval-receipt-v2.json).

Native transport preparation remains locally qualified but **production_ready=false**, with no activation runner or verified production channel. Only proof through a confirmed pre-existing authorized transport and unchanged-package renewal preparation may continue. Renew only after actual transport readiness; renewal alone cannot fix compatibility. [Read-only runbook](../review/relay-transport-v2/README.md); [qualification](../evidence/replacement-managed-relay-native-probe-qualification-v2.json). Massive's external runtime dependency remains unresolved.

## Durable executable continuation

1. Reconcile current owner/lease11:30, source/deployments, installed rewrite/index definitions and uncertain writes. Never replay installed maintenance or discard retained work.
2. Keep the same worker/recovery and hourly task active. Record independent useful commits/readbacks; verify future progress without claiming clean logs from the failed lookup.
3. If a fresh claim error or substantive stall recurs, reconcile that exact family/workload and cached-plan evidence using bounded diagnostics. Preserve every existing guard; qualify a narrowly demonstrated repair only if needed. No speculative claim change or full16-probe sweep.
4. Continue all fixed3,000/16-family planning, historical acquisition/reuse, pagination/enumeration, identity/support/alias resolution, derived/shared/registry refresh and final field accounting. Planning and coverage remain incomplete.
5. Preserve the exact relay hold and original expired approval. Only existing-authorized read-only transport readiness/preparation; request renewed approval only when the unchanged package is executable.
6. Record actual progress, limits and next executable work in the same existing automatic continuation. No new controller, task, artificial programme expiry or claim of full mission completion.
