# ASTRA ingestion — replacement checkpoint v67

## Current execution and ownership

Updated from root-verified observations through **2026-10-30T08:04:11Z**. Status: **ACTIVE — USEFUL BULK BACKFILL RUNNING; FULL DELIVERY INCOMPLETE**.

The same owner `root-replacement-20261030T042603Z` holds the finite implementation lease through **2026-10-30T08:30:00Z**. Database audit4 records the compare-and-swap renewal from 08:00 to 08:30 at approximately 07:52:41Z. No release has been reported. The existing implementation automation `6ae2a4c96bbc819182133e17e9b7f779` remains enabled with its original hourly recurrence and no expiry; its prompt was updated at 07:52:51Z with the relay security boundary first. It must respect the current root lease. The existing 08:00 hourly execution completed a read-only reconciliation and respected the active owner. No competing controller or scheduled task was created.

Run: `fixed3000-20250901-20260731-v1-20261030`, fence1. Existing PR93/branch `feat/astra-ingestion-service`, repository `robert8p/Alpaca-Supabase-Populator`. Retain completed work and reconcile uncertain writes before retrying. The worker continues through the existing queue and existing services.

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

## Exact tested deployment and genuine progress

Executable revision **`947b681735138b0b9052df1e5eba5769d7b2c381`** passed all four GitHub push/pull-request ingestion qualification and release-gate checks. Stage3 local qualification passed **519 actual PostgreSQL tests** with zero failures, errors or skips. The exact release qualification also records its no-DSN and syntax checks. Relay, shared-record and contract-registry candidates were excluded from this release.

| Existing service | Exact deployment | Live at (2026-10-30 UTC) |
| --- | --- | --- |
| Worker `srv-dbh9fko473hc739an8m0` | `dep-dbi4gvrbc2fs73a3b2fg` | 07:35:03 |
| Web `srv-dbh85vl9fdbs7387rucg` | `dep-dbi4h1ei0phs73crc7dg` | 07:35:11 |

Both selected revision `947b681735138b0b9052df1e5eba5769d7b2c381`. Workspace `tea-d562ma4hg0os73aejnfg`; one existing ingestion worker instance.

At **07:49:42Z**, root verified:

| Measure | Recorded value |
| --- | ---: |
| Run state | ACTIVE |
| Physical committed pages | 1,635 |
| Physical records/pointers | 195,785 |
| Provider reservations | 810 |
| Recorded readbacks | 1,635 |
| Retained S02 occurrences | 857 |
| Next retained S02 page | 7 |
| OPERATIONAL_ERROR tasks | 0 |
| Planner next selection order | 1,173 |

These are execution and storage measurements, not a count of distinct market observations or completed family coverage. Retained pointers, shared observations, cached feature rows and article/contract occurrences have different units and may overlap. Planning is still incomplete, and historical pagination/enumeration remains open. The 07:49:42 figures are a timestamped checkpoint, not a claim that progress stopped then.

Newer reconciliations show **1,758 committed pages, 210,856 physical records/pointers and 1,758 readbacks at 07:57:42Z** in the existing automation's read-only execution. At **08:02:09Z**, the root observed **1,792 committed pages and 214,624 physical records/pointers**, with last useful progress at **08:02:06Z**. The earlier 07:49:42 table remains unchanged because it contains additional measures not refreshed in those later reads. At **08:03:00Z**, the root's fuller readback showed **1,793 committed pages, 215,444 physical records/pointers, 885 reservations and 1,793 independent readbacks**, with **1,869 retained S02 occurrences**, next retained S02 page **15**, planner next selection order **1,343**, and **zero OPERATIONAL_ERROR tasks**. Last useful progress in that receipt was 08:02:10Z. The newly installed registry was at its initial state: `seed_complete=false` and zero registered windows/links; installation alone is not evidence that its catch-up has progressed.

Evidence: [stage3 publication and exact deployments](../evidence/replacement-stage3-publish-and-deploy-v2.json), [07:49:42 live measurement](../evidence/replacement-live-progress-v67.json), [later progress and applied-forward reconciliation](../evidence/replacement-live-progress-v67-supplement.json), [08:03 live progress and registry application receipt](../evidence/replacement-independent-forward-live-v67.json), [stage3 exact release qualification](../evidence/replacement-stage3-release-qualification-v2.json), [PostgreSQL qualification](../evidence/replacement-stage3-pg-qualification-v2.json), [no-DSN qualification](../evidence/replacement-stage3-no-dsn-qualification-v2.json), [syntax qualification](../evidence/replacement-stage3-syntax-qualification-v2.json), and [first useful batch](../evidence/replacement-first-useful-batch.json).

## Verified unattended execution path

The new run has demonstrated actual provider acquisition/verified reuse, automatic subsequent tasks, source-to-database readback, controlled restart and deferred retry. Continue bulk work after this proof.

Controlled restart `dep-dbi3ki4s728c73c8fnrg` on13ae became LIVE06:34:28Z. All75 prior page keys/hashes stayed unchanged, zero duplicates, and34 pages committed after the old worker's final heartbeat by06:37:23Z. [Restart proof](../evidence/replacement-controlled-restart-proof.json).

A controlled30-second application pacing deadline—not a fabricated provider429—put five actual tasks in RETRY_WAIT withzero reservations. Four resumed and committed verified data by06:54. The fifth, AAPL options task `backfill-plan-44b5d8cb87119b6edef0f9fdfffffd9ac10633c40e6b51cf5c46bb3aab645e6a`, committed1000 verified contracts07:05:44Z and retained its next cursor. [Initial four-task retry proof](../evidence/replacement-deferred-retry-proof-v2.json); the fifth readback is in v66 live evidence.

The live check exposed two application defects and both were repaired:

- Eligible retries could be starved by fresh PENDING work. Per-family due-recovery priority now selects eligible deferred/expired claims first.
- A normal one-second provider pacing refusal could hand the next turn to another family. The bounded short-pacing fairness forward retains that family's turn when the remaining delay is at most one second. Longer Retry-After deadlines remain intact and other families/providers continue. Six actual-PG tests include an exact starvation reproduction and successful next reservation.
- News pages hit the existing10-second RPC deadline in the old character-by-character JSON encoder. The linear encoding forward preserves old bytes/hashes (104 Unicode comparisons), and a1,208,635-byte authenticated test commit completed in0.158seconds with idempotence/readback/successor verification. Actual50-article pages are now committing. No provider-absence inference was made.

## Applied changes and retained work

Runtime, cohort, bounded planner, retained-source commits/readback, stable delivery views/finalizer, breadth material, source deduplication, compact D01 cache reuse, provider pacing, family fairness, adaptive execution page limits, canonical encoding and due-recovery priority are installed. Cache reuse and replacement-run app status remain deployed.

The following additional forwards are confirmed APPLIED; reconcile installed markers and exact definitions before any retry:

| Forward | SHA256 | Status |
| --- | --- | --- |
| Short provider-pacing fairness | `edce51c13dc11bb38a28cd6c68b144d0a5d87dcbb2d33b436a15333daf19107c` | Applied before v66; normal delays at most one second preserve the eligible family turn |
| Progressive historical identity | `47ee25cd2bf72a9c9c9bc92b218ae32b1241ce3d7d7aed0d00a05f579fffc553` | Applied; included in stage3 |
| Non-minute per-field projection | `3ffd78a515acc4f68cae81f5799999f8a9df2e53b3e15845f7147ecbefc1d869` | Applied; included in stage3 |
| Bounded retained S02 overlay | `10cbf5b690f38f688ace5485088445de2ac61963073d3fbf216475c18131e2b9` | Applied; included in stage3 |
| Maintenance fairness | `3823c379001e948f97b9aa0d75f4017077b8ce986b3894ee82d0ea60171990e9` | Applied approximately 07:46Z; three actual PostgreSQL concurrency tests passed |
| Shared-record delivery | `2ba0a87c01e37f6a0542ff5dc8db4c044f0b23982ab948a9050c3c4aac93aa10` | Applied approximately 07:55Z; 14 dedicated PostgreSQL tests and the earlier 29-test combined qualification |
| Contract-work registry | `fde0b731e81497833062967526253af3f2b4d7fcc78a3a1968840a3f2aace9d2` | Applied approximately 08:02:25Z after live absence, shared prerequisite and ownership reconciliation; seven PostgreSQL tests and accepted independent static review |

Maintenance fairness changes `backfill_maintain` only, with no ACL change. The authenticated dispatcher baseline remains SHA256 `0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96`.

Historical identity uses retained original-byte evidence and exact dated identifiers. Missing support dates or unresolved historical aliases remain explicit; do not infer continuity from a ticker alone. Derivative refreshes use immutable successor work. The retained S02 overlay is partial reuse and does not retire full-history Massive tasks.

Original legacy canary/restart jobs retain 234 records/3 requests. Their counters, limits, evidence and completed states remain outside new-run accounting. Old-scope admission stays closed. No old evidence was rewritten.

## Qualification scope for this publication

| Qualification | Result and applicable bytes |
| --- | --- |
| Stage3 full release | 519 actual PostgreSQL tests; all four GitHub checks passed for `947b681735138b0b9052df1e5eba5769d7b2c381`, already deployed |
| Maintenance fairness | Three actual PostgreSQL concurrency tests for SQL `3823c379…` |
| Shared-record SQL | 14 dedicated PostgreSQL tests for SQL `2ba0a87c…`; the earlier combined 29-test suite also includes this same SQL and the maintenance forward |
| Contract registry | Seven actual PostgreSQL tests for SQL `fde0b731…`; independent static review accepted the same bytes |
| Earlier combined shared/status suite | 29 passed; its four status-file hashes are now superseded and must not be presented as coverage of the latest status files |
| Latest four status files | 12 exact-current ASGI/DOM tests passed in 0.298 seconds; the new status qualification receipt pins all four latest files, and exact-head GitHub release checks are still required |

These overlapping suite counts are not additive. See [the exact-current status qualification](../evidence/replacement-shared-status-release-qualification-v2.json) and [the publication qualification map](../evidence/replacement-v67-publication-qualification-map.json) for exact artifact hashes and the status-file mismatch with the earlier combined suite. The status UI remains unpublished and undeployed at this checkpoint. The inherited family-report performance forward remains pending independently.

## Current executable step and durable successor

Continue in the retained working directory `/workspace/scratch/a1eb25e9f187/replacement-run` under the same ownership. The ingestion worker continues acquisition, reuse and calculations while independent engineering proceeds.

1. **Repair the inherited family-report query performance.** The current investigation found an eight-second timeout with approximately 388,000 planned task rows being materialized. This is a status/query performance defect; it does not establish provider absence or terminal coverage. Preserve exact family accounting, existing visibility and permissions. Qualify a bounded forward using the local fixture, then have the root reconcile and apply it once.
2. **Retain and read back the applied shared-record forward; finish its public status release.** `sql/astra_backfill_shared_records_v2.sql`, SHA256 `2ba0a87c01e37f6a0542ff5dc8db4c044f0b23982ab948a9050c3c4aac93aa10`, was applied successfully by the root at approximately 07:55Z after 29 focused PostgreSQL/status tests. Do not replay it. The additional contract-work status sanitizer and UI passed **12 exact-current ASGI/DOM tests in 0.298 seconds**, recorded in the [status release qualification](../evidence/replacement-shared-status-release-qualification-v2.json), which pins all four latest files. That public status code is **not yet published or deployed**. The earlier 29-test combined qualification pins older hashes for all four status files and does **not** qualify their latest bytes. Exact-head GitHub checks remain the release gate for the current four-file status change. See [shared-delivery qualification](../evidence/replacement-shared-delivery-forward-qualification-v2.json). Preserve physical work versus coverage accounting and explicit unknown denominators.
3. **Retain and read back the applied contract-work registry.** SQL SHA256 `fde0b731e81497833062967526253af3f2b4d7fcc78a3a1968840a3f2aace9d2` was applied successfully at approximately 08:02:25Z after the root reconciled its absence, the installed shared-record prerequisite and ownership. Seven PostgreSQL tests passed, and the [independent static review](../evidence/replacement-contract-registry-independent-static-review-v2.json) accepted the exact candidate. Preserve existing immutable tasks and running leases, all parent/member lineage and bounded activation catch-up. Existing overlapping children remain executable. Verify real registry progress; do not replay the installed forward.
4. **Publish the independent forwards and status code, then deploy the tested web revision.** Reconcile uncertain writes, qualify exact files, pass exact-head CI, reconcile the still-pending performance forward before its one-time application, deploy the tested web revision once and read back real effects. The existing stage3 worker keeps running; its source hash remains `90d048a6c535f7f768050c25e396a923e0e4e211457016757e30af16daface3e`. Keep the relay review-only files out of executable source publication. Record updated progress and the next concrete step in this checkpoint and the same hourly automation.
5. **Continue the complete mission.** Advance the remaining frozen-member plan, historical acquisition and pagination, identity/support/alias work, calculations, field coverage and truthful terminal accounting. Continue after first-batch/restart/retry proof; do not repeat completed proof or stop at a small useful sample.

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

## Completion remains unverified

Full delivery remains incomplete: the 3,000-member plan is unsealed, pagination and contract enumeration are still running, and identity/support/alias and coverage reconciliation remain. Use final COMPLETE or COMPLETE_WITH_DOCUMENTED_GAPS only after the mission's full verified terminal accounting. Repairable technical failures remain operational.

The preceding published checkpoint v66 at commit `2dbe666c86b3eeb0080bf6dd24ecc3b1fcb4fe2b` is preserved byte-for-byte in [checkpoint history](history/INGESTION_COMPLETION_STATE_v66.md); see [v66 publication evidence](../evidence/replacement-published-checkpoint-v66.json). The earlier automation prompt is also retained in [prompt history](history/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT_v66.md).
