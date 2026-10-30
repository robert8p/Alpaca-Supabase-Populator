# ASTRA ingestion — replacement checkpoint v68

## Current execution and ownership

Updated **2026-10-30T08:19:41Z**. Status: **ACTIVE — OPERATIONAL REPAIR IN PROGRESS; FULL DELIVERY INCOMPLETE**.

The existing worker is **intermittently crashing and restarting with `RpcPersistenceError`**. The database run remains ACTIVE and retained progress is intact, but this does not establish healthy continuous execution. The family-report performance repair has succeeded; the separate claim/dispatch timeout and the failed 1,000-news-row qualification still require repair.

**First reconcile the interrupted turn, current ownership, retained files, installed forwards and any uncertain writes before retrying or changing anything.** Continue the same run `fixed3000-20250901-20260731-v1-20261030`, fence1, through the existing worker, queue and controller. Do not restart completed work or create a competing controller.

Owner `root-replacement-20261030T042603Z` retains the finite implementation lease through **2026-10-30T08:50:00Z**. Database audit5 records its compare-and-swap renewal from 08:30 to 08:50 at **08:18:35Z**. No release is recorded. The same hourly automation `6ae2a4c96bbc819182133e17e9b7f779` remains enabled without programme expiry; the root updated its prompt at **08:19:41Z** with the current failures, ownership and relay hold. It must respect this lease. After explicit release or expiry, reconcile and acquire coherent ownership before implementation writes.

Existing PR93/branch `feat/astra-ingestion-service`, repository `robert8p/Alpaca-Supabase-Populator`. Published v67 commit: `3e8a7b94ec7dcea8a995fd20ce5df372b2677250`. Packaging-fix revision at this reconciliation: `3ffd337e9c65b5ea33f96ab6436c0701684f435a`. [Runtime, CI and ownership evidence](../evidence/replacement-runtime-reconciliation-v68.json).

## Fixed authority and cohort

All ten sections of [the replacement instruction](REPLACEMENT_BACKFILL_MISSION_20261030.md) remain active, SHA256 `62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45`.

Target: 2025-09-01–2026-07-31, America/New_York exchange dates. Families: REF01, REF03, P01, P02, D01, D02, D03, D04, D05, N01, N02, N03, S01, S02, CTX02, CTX06. Sources: existing Alpaca Algo Trader Plus and Massive Stocks Starter only. F01–F06/CTX07/CTX14 preserved outside acquisition; D06 preservation-only. No programme expiry; bounded calls, transactions, task leases and attempts.

The accepted saved snapshot `population_top3000_202608_202609_v1.ref01_practical_snapshot_v1.content->companies` was directly reconciled with frozen membership and selection order at06:19:01Z: **3000 saved, 3000 frozen, zero differences**. Root acceptance event24407 governs membership. The immutable snapshot's older false acceptance flag does not supersede the later accepted receipt.

- Snapshot SHA256: `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`.
- Acceptance receipt SHA256: `20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9`.
- Ordered member-ID SHA256: `a83310df6a6465ce8d37ffd5352095f6e38d91a3204afd8807fff39092cfd85e`.
- Evidence: [saved cohort reconciliation](../evidence/replacement-saved-cohort-reconciliation.json).
- Never invoke `ref01_practical_material_v1`; never rerank, substitute or shrink members.
- Classification remains RETROSPECTIVE_FIXED_COHORT, not contemporaneous or survivorship-free.

Actual calendar:230 target sessions; daily60-session support starts2025-06-05; intraday20-session support starts2025-08-04. Formula manifest SHA256 `e0b0835ad53ef7b71d072184bbb1576b3cd8f514c523361fa31865f71a0c8a65`.

## Deployed revision, retained progress and runtime failure

Both existing services still use tested stage3 executable revision **`947b681735138b0b9052df1e5eba5769d7b2c381`**. Its historical qualification passed 519 actual PostgreSQL tests and all four GitHub checks. That result does not qualify the newer branch revision or establish current worker health.

| Existing service | Deployment | Became live (2026-10-30 UTC) |
| --- | --- | --- |
| Worker `srv-dbh9fko473hc739an8m0` | `dep-dbi4gvrbc2fs73a3b2fg` | 07:35:03 |
| Web `srv-dbh85vl9fdbs7387rucg` | `dep-dbi4h1ei0phs73crc7dg` | 07:35:11 |

The newer shared-record/contract-work status UI is published in the branch but **has not been deployed**. Do not deploy it until the exact-head ingestion and release gates pass. Worker source remains SHA256 `90d048a6c535f7f768050c25e396a923e0e4e211457016757e30af16daface3e`.

At **08:13:52Z**, the complete delivery read returned:

| Measure | Recorded value |
| --- | ---: |
| Physical committed pages | 1,810 |
| Physical source/derived records and pointers | 217,210 |
| Provider reservations | 891 |
| Source bytes | 207,684,827 |
| Required readbacks remaining | 0 |
| Families returned | 16 |

The **08:14:31Z** runtime read still showed 1,810 pages and 217,210 physical records/pointers, planner next selection order **1,373**, and last useful progress at **08:13:44Z**. These timestamps are retained observations, not a promise of later progress. Physical records, pointers, reused observations and logical source occurrences have different overlapping units; do not add them into a unique-observation count or infer final coverage. The fuller earlier 07:49 and 08:03 measurements remain in [v67 history](history/INGESTION_COMPLETION_STATE_v67.md) and their original evidence files.

Sanitized service logs show repeated `RpcPersistenceError` exits and automatic restarts, including an exit at **08:13:55Z**, after the report repair. PostgreSQL reports **SQLSTATE `57014`**, “canceling statement due to statement timeout,” at **`astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)` line106**, through the existing authenticated RPC path. The current executable defect is this claim/dispatch timeout. Do not classify it as provider absence or a successful terminal gap, and do not claim the worker is healthy merely because the deployment or run status says ACTIVE.

Evidence: [stage3 exact deployment](../evidence/replacement-stage3-publish-and-deploy-v2.json), [report-performance live readback](../evidence/replacement-family-report-performance-live-v2.json), and [sanitized worker/SQL failure plus lease reconciliation](../evidence/replacement-runtime-reconciliation-v68.json).

## Applied forwards and repaired family report

All previously installed cohort, runtime, bounded planning, source reuse, delivery/readback, breadth, source deduplication, feature-cache reuse, provider/family pacing, adaptive page, canonical encoding and retry-priority work remains retained. Additional installed forwards include:

| Forward | Exact SHA256 | Application state |
| --- | --- | --- |
| Progressive historical identity | `47ee25cd2bf72a9c9c9bc92b218ae32b1241ce3d7d7aed0d00a05f579fffc553` | Applied in stage3 |
| Non-minute field projection | `3ffd78a515acc4f68cae81f5799999f8a9df2e53b3e15845f7147ecbefc1d869` | Applied in stage3 |
| Retained S02 overlay | `10cbf5b690f38f688ace5485088445de2ac61963073d3fbf216475c18131e2b9` | Applied in stage3 |
| Maintenance fairness | `3823c379001e948f97b9aa0d75f4017077b8ce986b3894ee82d0ea60171990e9` | Applied approximately 07:46Z |
| Shared-record delivery | `2ba0a87c01e37f6a0542ff5dc8db4c044f0b23982ab948a9050c3c4aac93aa10` | Applied approximately 07:55Z |
| Contract-work registry | `fde0b731e81497833062967526253af3f2b4d7fcc78a3a1968840a3f2aace9d2` | Applied approximately 08:02:25Z |
| Family-report performance | `324246c5b85d0052bb39189dc20eb73121bfe412f951df5f33a538172aab23ad` | **Applied once at approximately 08:12:37Z** |

The report forward changes two existing views, preserving their relation identity and ACLs, outer report composition, immutable receipts, task states/scopes/leases, revision selection and identity invalidation semantics. It adds no role, grant, credential or relay path. The local qualification passed **six actual PostgreSQL tests**, with no failure, error or skip, and exact input hashes unchanged. It includes a 200,000-task synthetic workload under the actual stage3/shared/registry schema; the synthetic timing is separate from production evidence. [Full qualification and plans](../evidence/replacement-family-report-performance-qualification-v2.json).

Live verification produced the complete **16-family JSON in 4.207 seconds** of server statement time at 08:13:02Z, and the **complete delivery function in 4.322 seconds** at 08:13:52Z with zero required readbacks remaining. These reads establish that the report repair worked for the recorded live calls. They do not resolve the later dispatch timeout or the separate shared-news performance failure. [Application and live timing evidence](../evidence/replacement-family-report-performance-live-v2.json).

Reconcile both installed view definitions before any uncertain retry: the receipt view contains `WITH task_counts AS` and no `mapped_tasks` materialization; the effective-page view contains `chosen_row` and the per-task chosen-field window. The two changes were atomic. Do not replay the forward solely because a chat or tool response was interrupted.

## Exact-head qualification: current release blocked

Both repository release-gate checks passed for revision **`3ffd337e9c65b5ea33f96ab6436c0701684f435a`**, including the narrow review-directory pytest collection boundary. The ingestion PR qualification **failed**, so the overall release gate is not satisfied.

[Ingestion workflow 41024658444](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/41024658444), job `123959793133`, ran **545 tests in 346.844 seconds with one failure**. The failed test is `SharedRecordsTests.test_report_uses_compact_counters_without_raw_or_canonical_record_scan_and_private_acl`, at line244 of `tests/ingestion/test_backfill_shared_records_v2.py`. Its **1,000-news-row `self.commit(c, rows)` took 239.080 seconds against the existing 12-second assertion**. The application-syntax step was skipped after the failure. The 10,000-option-row projection case passed. This is a concrete commit/verification performance failure, not the earlier archived-review import error.

The earlier local shared-record qualification and 29-test combined suite remain historical evidence; they do not supersede the failed exact-head result. The latest four status files separately passed **12 exact-current ASGI/DOM tests in 0.298 seconds**, but that focused result is not a substitute for the complete ingestion gate. Do not combine overlapping suite totals or claim the newer status UI has been deployed. Preserve the original correctness and timing assertions while repairing the demonstrated cause.

Evidence: [runtime/CI reconciliation](../evidence/replacement-runtime-reconciliation-v68.json), [exact-current status qualification](../evidence/replacement-shared-status-release-qualification-v2.json), and [narrow review collection boundary](../evidence/replacement-review-pytest-boundary-v67.json).

## Current executable step and durable successor

Continue in `/workspace/scratch/a1eb25e9f187/replacement-run` under the same owner and existing hourly successor:

1. **Reconcile before retrying.** Read the latest branch, exact deployed revision, owner lease, installed function/view markers and retained receipts/counters. Reconcile any uncertain claim, commit or migration write. Preserve completed pages and task generations; do not create a second controller or reset the run.
2. **Repair the live claim/dispatch timeout.** The existing performance agent is diagnosing SQLSTATE57014 at inner `backfill_dispatch_v2` line106. Implement and qualify the smallest bounded forward while preserving dependencies, leases/fences, cancellation, provider pacing, fixed cohort and existing authentication. The root owns production application. This step is not yet completed; repeated worker restarts are not a durable fix.
3. **Repair the reproduced CI shared-news bottleneck.** The existing shared-record agent owns diagnosis of the 1,000-news-row commit/verification path. Compare the exact failing fixture and relevant query plans, retain the original assertions and immutable evidence, and qualify the concrete forward. The cause remains under investigation; do not label an unverified JIT or planner hypothesis as established.
4. **Qualify and release the exact repaired head.** Publish the retained report forward and the qualified repairs; require exact-head ingestion and repository gates. Reconcile/apply each new forward once. Deploy the pending independent web status revision only after those gates pass, then read back authenticated status and useful worker progress across the repaired path. Keep relay source outside executable publication. Record the new exact head, actual health/progress and next concrete action in this checkpoint and the same hourly automation.
5. **Continue all remaining acquisition and delivery.** Once the operational path is repaired, resume the full frozen-member plan, pagination/contract enumeration, identity/support/alias work, retained S02 reuse, calculations and truthful field-coverage/final accounting. Verify registry catch-up and shared projection progress; do not infer completion from installation or raw counters. Preserve historical missing evidence and unknown denominators.

The original acquisition/automatic-successor/restart/readback/deferred-retry proof remains valid historical evidence. It is not evidence that today's worker is continuously healthy. Do not rerun that completed proof or restart completed data work. Original legacy canary/restart jobs remain 234 records/3 requests with their original limits and evidence, outside new-run accounting. Old-scope admission remains closed.

## Massive relay: exact review package held for action-time confirmation

The current worker's existing permissions do **not** authorize the proposed managed-key relay. Live run metadata `massive_relay_security_confirmation` remains `AWAITING_ACTION_TIME_CONFIRMATION`, with independent ingestion continuing within existing permissions. This boundary supersedes earlier broad approval for this proposed security change.

At 07:51Z the existing `population-top3000-news-v1` Edge function was still version1, ACTIVE, `verify_jwt=false`, with one 15,606-character `index.ts`. Its unchanged bundle SHA256 is `04def722c50e2fc173d3bc59fc5462953c9338c71467aeb936385725c1e8996c`. The old handler accepts its own attempt/token protocol and calls the earlier N01 news claim path; it does not support the current replacement worker's capability. No relay migration, grant, credential configuration, Edge deployment, production worker integration or live relay probe has been performed. The [final live security reconciliation](../evidence/replacement-managed-relay-final-live-hold-v2.json) at 08:03:50–08:04:11Z confirmed the relay table/helper remain absent and the hold is unchanged after shared-record and registry application. The inner authenticated dispatcher remains `0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96`; the distinct public SQL wrapper remains `566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb`. The Edge version1 bundle is unchanged. These are separate function hashes, not a baseline mismatch.

The candidate is available solely as a review package. Its executable source and tests are copied byte-for-byte under `review/massive-relay-v2/candidates/`; those copies are not active source paths. Publication of this review package is not activation.

- Reviewed security scope SHA256: `7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe`.
- Held SQL SHA256: `4be1c6d145949f4cda35a1cef7772da93137e3f102f045f1a7507ea66a16652d`.
- [Exact security review](../evidence/replacement-managed-relay-security-review-v2.md), [existing versus proposed RPC authorization diff](../evidence/replacement-managed-relay-rpc-auth.diff), [Edge handler diff](../evidence/replacement-managed-relay-edge-handler.diff), and [review-only publication manifest](../evidence/replacement-managed-relay-review-publication-manifest-v2.json).

The concrete proposed change would send the worker's existing `X-Astra-Ingestion-Token` to the existing Edge function as a **new credential recipient**, forward it only to the fixed same-origin RPC, add two worker-only RPC operations and narrowly scoped private dispatch-table/helper permissions, deploy the bounded Edge branch, and enable the reviewed worker adapter. The managed Massive key would remain inside the Edge-to-Massive HTTPS path. The review includes exact artifact hashes, mission-scope limits, one-dispatch reservation guards, revocation and rollback requirements. Local qualification passed 33 focused Python-suite tests, including 15 actual PostgreSQL tests, and 16 direct Node handler cases; independent security review found no remaining blocking issue within the frozen scope. This establishes candidate qualification only, not runtime capability or provider entitlement.

**Do not apply or activate any part of that relay without the user's fresh action-time confirmation of the exact reviewed change and pinned artifacts.** Do not promote review copies to active paths, add persistent access, send a live probe, change credentials, deploy the relay Edge branch or wire it into production. The finite one-use installation gate must remain fail-closed and must bind the exact reviewed scope and artifact hashes; do not fabricate approval fields or use earlier broad approval. Any changed candidate needs a new review scope and confirmation.

Until a later approved authenticated capability probe and real acquisition verify the relay, `MASSIVE_WORKER_CREDENTIAL / RUNTIME_CAPABILITY_UNAVAILABLE` remains an external dependency. Continue Alpaca, retained evidence and calculations within the existing permissions. Do not bypass this boundary through an old controller, different service, exported key or plan purchase.

## Completion and checkpoint history

The mission remains incomplete: the 3,000-member plan is unsealed, historical pagination and contract enumeration remain open, identity/support/alias and coverage work remain, and current operational failures require repair. COMPLETE or COMPLETE_WITH_DOCUMENTED_GAPS requires the full mission's verified terminal accounting. Repairable technical failures remain operational.

Published v67 at `3e8a7b94ec7dcea8a995fd20ce5df372b2677250` is preserved byte-for-byte in [checkpoint history](history/INGESTION_COMPLETION_STATE_v67.md) and [automation prompt history](history/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT_v67.md). The packaging fix is `3ffd337e9c65b5ea33f96ab6436c0701684f435a`. Existing ownership and the same hourly task continue; this checkpoint creates no new controller or authorization for the held relay.
