# ASTRA ingestion — replacement checkpoint v66

## Current execution and ownership

Updated 2026-10-30T07:08Z (02:08 America/Cancun). Status: **ACTIVE — USEFUL BULK BACKFILL RUNNING; FULL DELIVERY INCOMPLETE**.

The same owner `root-replacement-20261030T042603Z` holds a finite implementation lease through **2026-10-30T08:00:00Z**. Database audit2 records the renewal at07:07:08Z. The existing implementation automation `6ae2a4c96bbc819182133e17e9b7f779` remains enabled with its original hourly recurrence and no expiry; its prompt was updated07:08:16Z. An implementation wake-up was recorded in progress for07:00, started07:05:18; this is not a second ingestion executor or evidence of a completed result. It must respect the current root lease.

Run: `fixed3000-20250901-20260731-v1-20261030`, fence1. Existing PR93/branch `feat/astra-ingestion-service`, repository `robert8p/Alpaca-Supabase-Populator`. No completed work was restarted, and no competing controller or paid service was created.

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

Executable revision **`2d67c06ee1a19084a61d7cc1145de16bc68ca0cd`** passed all four GitHub push/pull-request ingestion-qualification and release-gate checks. Local stage2 qualification:479/479 actual PostgreSQL tests, zero skipped/failures/errors;90 Python files compile and both JavaScript syntax checks pass.

Existing worker `srv-dbh9fko473hc739an8m0` deploy `dep-dbi41c2fngtc73c81gg0` became LIVE07:02:37Z. Existing web `srv-dbh85vl9fdbs7387rucg` deploy `dep-dbi41eetlv9c738pvjvg` became LIVE07:02:48Z. Both selected exact revision2d67. Latest observed worker `c9c2b861-b697-4f69-bc02-f24161d45051` advertises that revision. Workspace `tea-d562ma4hg0os73aejnfg`; one existing worker instance.

At07:05:50Z the active run held694 physical committed pages,69006 physical records/pointers and343 provider reservations; last useful progress07:05:46Z. The bounded planner had advanced to selection order223, with planning_complete=false.

At07:06:14Z independent readback showed:

- 705 verified pages; all705 stored/readback hashes match.
- 1,598,231 retained minute observations referenced, provenance-qualified and source-usable.
- 10 retained D01 feature pointers referencing3900 verified usable feature rows. The deployed worker is using the cache path; these are not3900 duplicated full arrays.
- 2500 committed news article occurrences in50 pages.
- 7000 committed option-contract occurrences in7 pages; historical enumeration/pagination remains open.
- Corporate actions, daily raw/split series and D03/D04/D05 calculations continue. No OPERATIONAL_ERROR task was present in this readback.
- These measurements have different timestamps and units. Never add physical records/pointers, raw/split variants, shared P01/P02 observations, cached features and article/contract occurrences into one unique-observation count.

Evidence: [live readbacks and deployments](../evidence/replacement-live-progress-v66.json), [stage2 qualification](../evidence/replacement-stage2-release-qualification-v2.json), [first useful batch](../evidence/replacement-first-useful-batch.json).

## Verified unattended execution path

The new run has demonstrated actual provider acquisition/verified reuse, automatic subsequent tasks, source-to-database readback, controlled restart and deferred retry. Continue bulk work after this proof.

Controlled restart `dep-dbi3ki4s728c73c8fnrg` on13ae became LIVE06:34:28Z. All75 prior page keys/hashes stayed unchanged, zero duplicates, and34 pages committed after the old worker's final heartbeat by06:37:23Z. [Restart proof](../evidence/replacement-controlled-restart-proof.json).

A controlled30-second application pacing deadline—not a fabricated provider429—put five actual tasks in RETRY_WAIT withzero reservations. Four resumed and committed verified data by06:54. The fifth, AAPL options task `backfill-plan-44b5d8cb87119b6edef0f9fdfffffd9ac10633c40e6b51cf5c46bb3aab645e6a`, committed1000 verified contracts07:05:44Z and retained its next cursor. [Initial four-task retry proof](../evidence/replacement-deferred-retry-proof-v2.json); the fifth readback is in v66 live evidence.

The live check exposed two application defects and both were repaired:

- Eligible retries could be starved by fresh PENDING work. Per-family due-recovery priority now selects eligible deferred/expired claims first.
- A normal one-second provider pacing refusal could hand the next turn to another family. The bounded short-pacing fairness forward retains that family's turn when the remaining delay is at most one second. Longer Retry-After deadlines remain intact and other families/providers continue. Six actual-PG tests include an exact starvation reproduction and successful next reservation.
- News pages hit the existing10-second RPC deadline in the old character-by-character JSON encoder. The linear encoding forward preserves old bytes/hashes (104 Unicode comparisons), and a1,208,635-byte authenticated test commit completed in0.158seconds with idempotence/readback/successor verification. Actual50-article pages are now committing. No provider-absence inference was made.

## Applied changes and retained work

Runtime, cohort, bounded planner, retained-source commits/readback, stable delivery views/finalizer, breadth material, source deduplication, compact D01 cache reuse, provider pacing, family fairness, adaptive execution page limits, canonical encoding and due-recovery priority are installed. Stage2 worker cache wiring and replacement app status are deployed.

The additional short-pacing forward is already APPLIED successfully:
`sql/astra_backfill_pacing_fairness_v2.sql`, SHA256 `edce51c13dc11bb38a28cd6c68b144d0a5d87dcbb2d33b436a15333daf19107c`.
Reconcile function marker `backfill_short_pacing_fairness_v2` and metadata `family_scheduling_policy.short_pacing_applied_at` before any retry. Do not reapply an installed forward because a chat result was interrupted.

Original legacy canary/restart jobs retain234 records/3requests; their counters, limits, evidence and completed states are outside new-run accounting. Old-scope admission stays closed. No old evidence was rewritten.

## Current executable step and durable successor

The same root is completing stage3 in the retained working directory `/workspace/scratch/a1eb25e9f187/replacement-run`. Preserve these in-progress files and reconcile before resuming:

1. Finish and integrate progressive historical identity using original retained Massive gzip responses with independently checked compressed/original hashes. Resolve exact dated CIK+composite-FIGI+share-class-FIGI matches only. Preserve missing support dates and historical aliases; respect Alpaca's documented explicit asof symbol mapping only when the actual receipt and fixed dated identifiers support it; otherwise keep mismatched historical aliases unresolved. Keep raw data available. Recompute affected daily/breadth outputs by immutable successor tasks; expose current D01 attribution through a view without copying its large numerical cache.
2. Install the tested non-minute per-field projection after identity's output-validity view. Select the latest complete derivative version, retain source variants separately, record NULL/unusable reasons and unknown denominators, and expose pending identity refresh timing in status.
3. Complete bounded S02 retained-page references. Verified old chain135 pages hasno gaps/continuation mismatches and one terminal page. Candidate frozen-anchor July15/July31 records are2989/2999 unique business keys, pages1–45. Stored response hashes/bytes/normalized rows match. Retain the declared credential-redaction representation and late retrieval; no exact-original-wire or historical ticker-attribution claim. This partial reuse does not retire the full historical Massive tasks.
4. Resolve the Massive runtime dependency using the existing server-side route if its actual capability verifies. The deployed `population-top3000-news-v1` Edge function already uses managed Massive credentials for the earlier archive. A narrow authenticated, bounded relay extension is being implemented in this same function, preserving its original handler and keeping the existing worker/queue as sole executor. Never export a managed/connector key. Validate run/claim/reservation/request, one dispatch per reservation, allowlisted read-only endpoints, real response evidence and subsequent commit/readback.
5. Exact candidate tests, exact-head GitHub CI, one-time forward migrations, exact tested deployment, real capability/source/identity/readback verification, then continue full planning/acquisition/calculation and finalization. Update this checkpoint and the same automation; do not create a replacement controller or stop at proof.

Until an actual capability probe and acquisition succeed, `MASSIVE_WORKER_CREDENTIAL / RUNTIME_CAPABILITY_UNAVAILABLE` remains BLOCKED_EXTERNAL. The existing worker continues Alpaca, reuse and calculations. If the managed route is genuinely unavailable, retain the exact owner setup dependency; do not repeatedly retry unchanged absent credentials, widen providers or buy a plan upgrade.

Full delivery remains incomplete: the3000-member plan is not sealed, pagination/contract enumeration is still running, identity/support/alias work and coverage reconciliation remain. Use final COMPLETE or COMPLETE_WITH_DOCUMENTED_GAPS only after the mission's full verified terminal accounting. Repairable technical failures remain operational.

Previous checkpoint retained at [v65](history/INGESTION_COMPLETION_STATE_v65.md).
